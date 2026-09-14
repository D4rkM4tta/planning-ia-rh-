import html
import streamlit as st
import calendar
import datetime as dt

from firebase_client import (
    login_user,
    logout_user,
    is_admin,
    load_availability,
    save_availability,
    get_all_users,
    load_planning_proposals,
    save_planning_proposal,
    load_monthly_hours,
    save_monthly_hours,
    reset_monthly_hours,
    load_cumul_adjustment,
    save_cumul_adjustment,
    set_planning_lock,
    is_planning_locked,
)

from components.calendar_availability import availability_calendar
from planner_engine import generate_planning
from planning_exports import (
    export_planning_excel_calendar_colored,
)
from planning_exports import export_planning_ical
from planning_stats import render_contract_vs_realized_chart

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(page_title="Planning IA RH", layout="wide")

# Amplitude 9h → 19h, 1h de repas non comptabilisée
HOURS_PER_DAY = 9

COLORS = [
    "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
    "#43A047", "#E53935", "#6D4C41", "#1E88E5"
]

MONTH_LABELS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}

# ============================================================
# UTILITAIRES
# ============================================================
def esc(value) -> str:
    """Échappe une valeur avant injection dans du HTML."""
    return html.escape(str(value if value is not None else ""))


def month_label(month: int) -> str:
    return MONTH_LABELS.get(month, str(month))


def build_user_colors(users: dict) -> dict:
    return {u: COLORS[i % len(COLORS)] for i, u in enumerate(users)}


def display_name(users: dict, email: str) -> str:
    """Nom d'affichage robuste même si l'utilisateur n'existe plus."""
    if not email:
        return "—"
    return users.get(email, {}).get("name") or email.split("@")[0]


def normalize_availability(raw: dict) -> dict:
    return {str(k)[:10]: True for k, v in raw.items() if v is True}


def compute_hours(planning_blocks):
    stats = {}
    for block in planning_blocks:
        user = block["assigned_to"]
        if not user:
            continue
        stats.setdefault(user, {"days": 0, "hours": 0})
        stats[user]["days"] += len(block["days"])
        stats[user]["hours"] += len(block["days"]) * HOURS_PER_DAY
    return stats


def month_hours_for_user(users: dict, user_email: str, year: int, month: int,
                         computed_hours: int) -> int:
    """
    Heures retenues pour un mois : l'ajustement manuel admin s'il
    existe, sinon les heures calculées depuis le planning.
    """
    override = users.get(user_email, {}).get(f"hours_{year}_{month}")
    return int(override) if override is not None else int(computed_hours)


def compute_year_cumulative(users: dict, year: int, up_to_month: int,
                            only_locked: bool):
    """
    Cumul annuel par collaborateur, de janvier jusqu'au mois demandé.

    only_locked=True  → ne compte que les plannings verrouillés
                        (chiffre de référence, figé)
    only_locked=False → compte aussi les plannings générés non
                        verrouillés (aperçu avant validation)

    Les ajustements mensuels admin sont pris en compte.
    Retourne (cumul_par_user, liste_des_mois_retenus).
    """
    cumulative = {}
    months_used = []

    for m in range(1, up_to_month + 1):
        proposals = load_planning_proposals(year, m)
        proposal = proposals.get("current")
        if not proposal:
            continue
        if only_locked and not proposal.get("locked"):
            continue

        months_used.append(m)
        stats = compute_hours(proposal["planning"]["blocks"])

        for user_email in users:
            computed = stats.get(user_email, {}).get("hours", 0)
            retained = month_hours_for_user(users, user_email, year, m, computed)
            if retained:
                cumulative[user_email] = cumulative.get(user_email, 0) + retained

    return cumulative, months_used


def last_locked_month(year: int) -> int | None:
    """
    Numéro du dernier mois verrouillé de l'année, indépendamment
    du mois actuellement sélectionné.
    """
    for m in range(12, 0, -1):
        proposals = load_planning_proposals(year, m)
        proposal = proposals.get("current")
        if proposal and proposal.get("locked"):
            return m
    return None


# ============================================================
# ANALYSE RH — WEEKENDS & JOURS FÉRIÉS
# ============================================================
def compute_weekends_and_holidays(blocks, year: int, month: int):
    # Jours fériés France à date fixe
    FIXED_HOLIDAYS = {
        dt.date(year, 1, 1),
        dt.date(year, 5, 1),
        dt.date(year, 5, 8),
        dt.date(year, 7, 14),
        dt.date(year, 8, 15),
        dt.date(year, 11, 1),
        dt.date(year, 11, 11),
        dt.date(year, 12, 25),
    }

    weekends_count = {}
    holidays_count = {}

    for block in blocks:
        user = block["assigned_to"]
        if not user:
            continue

        for d in block["days"]:
            day = dt.date.fromisoformat(d)

            if day.year != year or day.month != month:
                continue

            if day.weekday() >= 5:
                weekends_count[user] = weekends_count.get(user, 0) + 1

            if day in FIXED_HOLIDAYS:
                holidays_count[user] = holidays_count.get(user, 0) + 1

    return weekends_count, holidays_count


# ============================================================
# SESSION
# ============================================================
st.session_state.setdefault("auth_user", None)
st.session_state.setdefault("forced_assignments", {})

# ============================================================
# LOGIN
# ============================================================
def login_screen():
    st.title("🔐 Connexion Planning IA RH")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Mot de passe", type="password", key="login_pwd")
    if st.button("Se connecter", key="login_btn"):
        if login_user(email, password):
            st.rerun()
        else:
            st.error("Identifiants incorrects")


if not st.session_state.auth_user:
    login_screen()
    st.stop()

current_email = st.session_state.auth_user["email"]
admin = is_admin()
users = get_all_users()
user_colors = build_user_colors(users)

st.success(f"Connecté : **{current_email}** — {'Admin' if admin else 'Utilisateur'}")

if st.button("Se déconnecter", key="logout_btn"):
    logout_user()
    st.rerun()

# ============================================================
# ONGLETS
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📌 Mes disponibilités",
    "📋 Admin",
    "📅 Planning",
    "📜 Règles RH",
    "⏱️ Heures",
    "🔒 Planning validé",
])

# ============================================================
# TAB 1 — DISPONIBILITÉS
# ============================================================
with tab1:
    year = st.selectbox("Année", [2026, 2027], index=0, key="user_year")
    month = st.selectbox(
        "Mois",
        list(range(1, 13)),
        index=2,
        format_func=month_label,
        key="user_month",
    )

    availability_calendar(
        email=current_email,
        year=year,
        month=month,
        load_fn=load_availability,
        save_fn=save_availability,
        is_admin=admin,
        users=users,
        forced_assignments=st.session_state.forced_assignments,
    )

# ============================================================
# TAB 2 — ADMIN
# ============================================================
with tab2:
    if not admin:
        st.info("🔒 Onglet réservé aux administrateurs.")
    else:
        year_admin = st.selectbox("Année", [2026, 2027], index=0, key="admin_year")
        month_admin = st.selectbox(
            "Mois",
            list(range(1, 13)),
            index=2,
            format_func=month_label,
            key="admin_month",
        )

        availability_by_user = {
            u: normalize_availability(load_availability(u, year_admin, month_admin))
            for u in users
        }

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(year_admin, month_admin)

        dispo_by_day = {}
        for u, days in availability_by_user.items():
            for d in days:
                dispo_by_day.setdefault(d, []).append(u)

        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day.month != month_admin:
                    cols[i].markdown(
                        f"<div style='opacity:.3'>{day.day}</div>",
                        unsafe_allow_html=True,
                    )
                    continue

                inner = "".join(
                    f"<div style='background:{user_colors.get(u, '#546E7A')};color:white;"
                    f"border-radius:6px;padding:2px 6px;margin:2px 0;"
                    f"font-size:11px;text-align:center;'>"
                    f"{esc(display_name(users, u))}</div>"
                    for u in dispo_by_day.get(day.isoformat(), [])
                )

                cols[i].markdown(
                    f"<div style='min-height:90px;background:#ECEFF1;border-radius:8px;padding:6px'>"
                    f"<strong>{day.day}</strong>{inner}</div>",
                    unsafe_allow_html=True
                )

# ============================================================
# TAB 3 — PLANNING
# ============================================================
with tab3:
    year_v = st.selectbox("Année", [2026, 2027], index=0, key="view_year")
    month_v = st.selectbox(
        "Mois",
        list(range(1, 13)),
        index=2,
        format_func=month_label,
        key="view_month",
    )

    locked_v = is_planning_locked(year_v, month_v)

    if admin and not locked_v:
        if st.button("🚀 Générer / Régénérer le planning", key="generate_planning"):
            availability_by_user = {
                u: normalize_availability(load_availability(u, year_v, month_v))
                for u in users
            }

            planning = generate_planning(
                year=year_v,
                month=month_v,
                users=users,
                availability_by_user=availability_by_user,
                forced_assignments=st.session_state.forced_assignments,
            )

            save_planning_proposal(year_v, month_v, "current", planning, current_email)

            for warning in planning.get("warnings", []):
                st.warning(warning)

            st.success("✅ Planning généré")
            st.rerun()

    proposals = load_planning_proposals(year_v, month_v)
    proposal = proposals.get("current")

    if not proposal:
        st.info("Aucun planning généré.")
    else:
        blocks = proposal["planning"]["blocks"]

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(year_v, month_v)

        day_map = {}
        for block in blocks:
            if not block["assigned_to"]:
                continue
            cur = block["start"]
            while cur <= block["end"]:
                if cur.month == month_v and cur.year == year_v:
                    day_map[cur.isoformat()] = block["assigned_to"]
                cur += dt.timedelta(days=1)

        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day.month != month_v:
                    cols[i].markdown(
                        f"<div style='opacity:.3'>{day.day}</div>",
                        unsafe_allow_html=True,
                    )
                    continue

                assigned = day_map.get(day.isoformat())
                if assigned:
                    cols[i].markdown(
                        f"<div style='background:{user_colors.get(assigned, '#546E7A')};"
                        f"color:white;border-radius:10px;padding:8px;text-align:center;"
                        f"font-size:12px'>"
                        f"{day.day}<br>{esc(display_name(users, assigned))}</div>",
                        unsafe_allow_html=True
                    )
                else:
                    cols[i].markdown(
                        f"<div style='border:2px dashed #D32F2F;color:#B71C1C;"
                        f"border-radius:10px;padding:8px;text-align:center;font-size:11px'>"
                        f"{day.day}<br>NON COUVERT</div>",
                        unsafe_allow_html=True
                    )

    # --------------------------------------------------------
    # VERROUILLAGE (PERSISTANT EN BASE)
    # --------------------------------------------------------
    if admin and proposal:
        st.divider()
        if not locked_v:
            st.caption(
                "Une fois verrouillé, ce planning ne peut plus être régénéré "
                "et ses heures entrent dans le cumul annuel de référence."
            )
            if st.button("🔒 Verrouiller le planning", key="lock_planning"):
                set_planning_lock(year_v, month_v, True, current_email)
                st.rerun()
        else:
            locked_by = proposal.get("locked_by") or "—"
            locked_at = (proposal.get("locked_at") or "")[:10]
            st.success(f"🔒 Planning verrouillé par {locked_by} le {locked_at}")

            if st.button("🔓 Déverrouiller", key="unlock_planning"):
                set_planning_lock(year_v, month_v, False)
                st.rerun()

# ============================================================
# TAB 4 — RÈGLES RH
# ============================================================
with tab4:
    st.markdown("""
<div style="background:#263238;color:white;padding:16px;border-radius:10px">
<b>📜 Règles RH</b><br>
- Amplitude <b>9h → 19h</b>, soit <b>9 heures</b> comptabilisées (1h de repas non comptée)<br>
- Pas de blocs consécutifs<br>
- Disponibilités strictes<br>
- Forçage admin prioritaire<br>
- Tous les collaborateurs doivent apparaître
</div>
""", unsafe_allow_html=True)

# ============================================================
# TAB 5 — HEURES
# ============================================================
with tab5:
    # Sélecteurs propres à cet onglet : il est autonome et n'est
    # plus piloté par le mois choisi dans l'onglet Planning.
    col_y, col_m = st.columns(2)

    year_h = col_y.selectbox(
        "Année",
        [2026, 2027],
        index=0,
        key="hours_year",
    )
    month_h = col_m.selectbox(
        "Mois analysé",
        list(range(1, 13)),
        index=dt.date.today().month - 1,
        format_func=month_label,
        key="hours_month",
    )

    proposals_h = load_planning_proposals(year_h, month_h)
    proposal_h = proposals_h.get("current")
    blocks_h = proposal_h["planning"]["blocks"] if proposal_h else []
    month_is_locked = bool(proposal_h and proposal_h.get("locked"))

    # Le cumul se cale automatiquement sur le dernier mois verrouillé
    # de l'année, indépendamment du mois analysé ci-dessus.
    ref_month = last_locked_month(year_h)
    cumul_up_to = ref_month or 12

    cumul_locked, locked_months = compute_year_cumulative(
        users, year_h, cumul_up_to, only_locked=True
    )
    cumul_preview, preview_months = compute_year_cumulative(
        users, year_h, 12, only_locked=False
    )

    if ref_month:
        st.info(
            f"📊 **Cumul de référence {year_h}** arrêté au "
            f"**{month_label(ref_month)}** (dernier planning verrouillé) — "
            f"{len(locked_months)} mois verrouillé(s)."
        )
    else:
        st.warning(
            f"Aucun planning verrouillé en {year_h} : le cumul de référence "
            "est à 0. Les chiffres ci-dessous ne sont qu'un aperçu."
        )

    pending = [month_label(m) for m in preview_months if m not in locked_months]
    if pending:
        st.caption(
            "🔎 Aperçu incluant les mois générés non verrouillés : "
            + ", ".join(pending)
        )

    monthly_stats = compute_hours(blocks_h)
    weekends_stats, holidays_stats = compute_weekends_and_holidays(
        blocks_h, year_h, month_h
    )

    st.divider()

    # ----- Contrat vs Réalisé (mois analysé) -----
    status = "🔒 verrouillé" if month_is_locked else "✏️ non verrouillé"
    st.markdown(
        f"#### 📊 Contrat vs réalisé — {month_label(month_h)} {year_h} "
        f"*({status})*"
    )

    if blocks_h:
        render_contract_vs_realized_chart(
            users=users,
            blocks=blocks_h,
            year=year_h,
            month=month_h,
        )
    else:
        st.info(
            f"Aucun planning généré pour {month_label(month_h)} {year_h}."
        )

    st.divider()
    st.markdown(f"#### 👥 Détail par collaborateur — {month_label(month_h)} {year_h}")

    for user_email, user_info in users.items():
        if not admin and user_email != current_email:
            continue

        contract_hours = int(user_info.get("monthly_hours") or 0)
        computed_hours = monthly_stats.get(user_email, {}).get("hours", 0)
        override = user_info.get(f"hours_{year_h}_{month_h}")
        month_hours = int(override) if override is not None else computed_hours

        adjustment = int(user_info.get(f"cumul_adjustment_{year_h}") or 0)
        ref_total = cumul_locked.get(user_email, 0) + adjustment
        preview_total = cumul_preview.get(user_email, 0) + adjustment

        col_left, col_right = st.columns([3, 2])

        with col_left:
            badge = " *(ajusté)*" if override is not None else ""
            st.markdown(
                f"""
**{user_info.get('name', user_email)}**

📄 **Contrat horaire mensuel** : {contract_hours} h  
⏱️ **Heures de {month_label(month_h)}** : {month_hours} h{badge}  
🟪 **Week-ends effectués** : {weekends_stats.get(user_email, 0)}  
🟥 **Jours fériés** : {holidays_stats.get(user_email, 0)}  
📊 **Cumul validé {year_h}** : **{ref_total} h**  
🔎 **Aperçu (non verrouillé inclus)** : {preview_total} h  
{f"➕ *dont correction manuelle : {adjustment:+d} h*" if adjustment else ""}
""",
            )

        with col_right:
            if not admin:
                st.caption("Seul un administrateur peut modifier ces compteurs.")
                st.divider()
                continue

            # ----- Ajustement du mois -----
            new_hours = st.number_input(
                f"Heures de {month_label(month_h)}",
                min_value=0,
                max_value=400,
                step=1,
                value=int(month_hours),
                key=f"hours_{user_email}_{year_h}_{month_h}",
            )

            c1, c2 = st.columns(2)

            if c1.button("💾 Mois", key=f"save_month_{user_email}_{year_h}_{month_h}"):
                save_monthly_hours(user_email, year_h, month_h, int(new_hours))
                st.rerun()

            if override is not None:
                if c2.button("↩︎ Auto", key=f"reset_month_{user_email}_{year_h}_{month_h}"):
                    reset_monthly_hours(user_email, year_h, month_h)
                    st.rerun()

            # ----- Correction du cumul annuel -----
            new_adjustment = st.number_input(
                f"Correction cumul {year_h} (h)",
                min_value=-2000,
                max_value=2000,
                step=1,
                value=adjustment,
                key=f"cumul_{user_email}_{year_h}",
                help=(
                    "Ajout ou retrait appliqué au cumul annuel. "
                    "Sert à intégrer un historique antérieur à l'application "
                    "ou à corriger un écart constaté."
                ),
            )

            if st.button("💾 Cumul", key=f"save_cumul_{user_email}_{year_h}"):
                save_cumul_adjustment(user_email, year_h, int(new_adjustment))
                st.rerun()

        st.divider()

# ============================================================
# TAB 6 — PLANNINGS VERROUILLÉS
# ============================================================
with tab6:
    st.markdown("## 🔒 Plannings verrouillés")

    found = False

    for year_locked in [2026, 2027]:
        for month_locked in range(1, 13):
            proposals_l = load_planning_proposals(year_locked, month_locked)
            proposal_l = proposals_l.get("current")

            if not proposal_l or not proposal_l.get("locked"):
                continue

            found = True
            blocks_l = proposal_l["planning"]["blocks"]

            st.markdown(
                f"""
                <div style="
                    margin-top:24px;
                    padding:12px;
                    border-radius:14px;
                    background:#263238;
                    color:white;
                ">
                    <h3 style="margin-bottom:12px;">
                        📅 {month_label(month_locked)} {year_locked}
                    </h3>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ====================================================
            # BOUTONS EXPORT
            # ====================================================
            col_a, col_b, _ = st.columns([2, 2, 6])

            with col_a:
                excel_buffer = export_planning_excel_calendar_colored(
                    blocks=blocks_l,
                    users=users,
                    user_colors=user_colors,
                    year=year_locked,
                    month=month_locked,
                )

                st.download_button(
                    label="📊 Export Excel",
                    data=excel_buffer,
                    file_name=f"planning_{year_locked}_{month_locked:02d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"excel_{year_locked}_{month_locked}",
                )

            with col_b:
                ical_bytes = export_planning_ical(
                    planning=proposal_l["planning"],
                    users=users,
                    year=year_locked,
                    month=month_locked,
                )

                st.download_button(
                    label="📆 Export iCal",
                    data=ical_bytes,
                    file_name=f"planning_{year_locked}_{month_locked:02d}.ics",
                    mime="text/calendar",
                    key=f"ical_{year_locked}_{month_locked}",
                )

            # ====================================================
            # AFFICHAGE CALENDRIER
            # ====================================================
            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdatescalendar(year_locked, month_locked)

            day_map = {}
            for blk in blocks_l:
                if not blk["assigned_to"]:
                    continue
                cur = blk["start"]
                while cur <= blk["end"]:
                    if cur.month == month_locked and cur.year == year_locked:
                        day_map[cur.isoformat()] = blk["assigned_to"]
                    cur += dt.timedelta(days=1)

            for week in weeks:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day.month != month_locked:
                        cols[i].markdown(
                            f"<div style='opacity:.3'>{day.day}</div>",
                            unsafe_allow_html=True
                        )
                        continue

                    assigned = day_map.get(day.isoformat())
                    if assigned:
                        cols[i].markdown(
                            f"""
                            <div style="
                                background:{user_colors.get(assigned, '#546E7A')};
                                color:white;
                                border-radius:10px;
                                padding:8px;
                                text-align:center;
                                font-size:12px;
                            ">
                                {day.day}<br>{esc(display_name(users, assigned))}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        cols[i].markdown(
                            f"""
                            <div style="
                                border:2px dashed #757575;
                                color:#757575;
                                border-radius:10px;
                                padding:8px;
                                text-align:center;
                                font-size:11px;
                            ">
                                {day.day}<br>—
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

    if not found:
        st.info("Aucun planning verrouillé.")