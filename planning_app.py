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
    load_monthly_hours,      # ✅ AJOUT
    save_monthly_hours,      # ✅ AJOUT
)

from components.calendar_availability import availability_calendar
from planner_engine import generate_planning
from planning_exports import (
    export_planning_excel_calendar_colored,
)
from planning_exports import export_planning_ical

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(page_title="Planning IA RH", layout="wide")

# ============================================================
# UTILITAIRES
# ============================================================
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
        stats[user]["hours"] += len(block["days"]) * 9
    return stats


def compute_cumulative_hours(year: int, month: int):
    cumulative = {}
    for m in range(1, month + 1):
        proposals = load_planning_proposals(year, m)
        proposal = proposals.get("current")
        if not proposal:
            continue
        stats = compute_hours(proposal["planning"]["blocks"])
        for user, data in stats.items():
            cumulative.setdefault(user, 0)
            cumulative[user] += data["hours"]
    return cumulative


def compute_rolling_12_months(year: int, month: int):
    rolling = {}
    for i in range(12):
        y = year
        m = month - i
        if m <= 0:
            m += 12
            y -= 1
        proposals = load_planning_proposals(y, m)
        proposal = proposals.get("current")
        if not proposal:
            continue
        stats = compute_hours(proposal["planning"]["blocks"])
        for user, data in stats.items():
            rolling.setdefault(user, 0)
            rolling[user] += data["hours"]
    return rolling
# ============================================================
# ANALYSE RH — WEEKENDS & JOURS FÉRIÉS
# ============================================================
def compute_weekends_and_holidays(blocks, year: int, month: int):
    import datetime as dt

    # Jours fériés France fixes (suffisant pour ton besoin actuel)
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

            # Week-end
            if day.weekday() >= 5:
                weekends_count[user] = weekends_count.get(user, 0) + 1

            # Jour férié
            if day in FIXED_HOLIDAYS:
                holidays_count[user] = holidays_count.get(user, 0) + 1

    return weekends_count, holidays_count
# ============================================================
# SESSION
# ============================================================
st.session_state.setdefault("auth_user", None)
st.session_state.setdefault("forced_assignments", {})
st.session_state.setdefault("planning_locked", False)

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

st.success(f"Connecté : **{current_email}** — {'Admin' if admin else 'Utilisateur'}")

if st.button("Se déconnecter", key="logout_btn"):
    logout_user()
    st.rerun()

# ============================================================
# ONGLET
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
    month = st.selectbox("Mois", list(range(1, 13)), index=2, key="user_month")

    availability_calendar(
        email=current_email,
        year=year,
        month=month,
        load_fn=load_availability,
        save_fn=save_availability,
        is_admin=admin,
        users=get_all_users(),
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
        month_admin = st.selectbox("Mois", list(range(1, 13)), index=2, key="admin_month")

        users = get_all_users()
        availability_by_user = {
            u: normalize_availability(load_availability(u, year_admin, month_admin))
            for u in users
        }

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(year_admin, month_admin)

        COLORS = [
            "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
            "#43A047", "#E53935", "#6D4C41", "#1E88E5"
        ]
        user_colors = {u: COLORS[i % len(COLORS)] for i, u in enumerate(users)}

        dispo_by_day = {}
        for u, days in availability_by_user.items():
            for d in days:
                dispo_by_day.setdefault(d, []).append(u)

        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day.month != month_admin:
                    cols[i].markdown(f"<div style='opacity:.3'>{day.day}</div>", unsafe_allow_html=True)
                    continue

                inner = "".join(
                    f"<div style='background:{user_colors[u]};color:white;border-radius:6px;"
                    f"padding:2px 6px;margin:2px 0;font-size:11px;text-align:center;'>"
                    f"{users[u]['name']}</div>"
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
    month_v = st.selectbox("Mois", list(range(1, 13)), index=2, key="view_month")

    if admin and not st.session_state.planning_locked:
        if st.button("🚀 Générer / Régénérer le planning", key="generate_planning"):
            users = get_all_users()
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
            st.success("✅ Planning généré")
            st.rerun()

    proposals = load_planning_proposals(year_v, month_v)
    proposal = proposals.get("current")

    if not proposal:
        st.info("Aucun planning généré.")
    else:
        blocks = proposal["planning"]["blocks"]
        users = get_all_users()

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(year_v, month_v)

        day_map = {}
        for block in blocks:
            cur = block["start"]
            while cur <= block["end"]:
                if cur.month == month_v:
                    day_map[cur.isoformat()] = block["assigned_to"]
                cur += dt.timedelta(days=1)

        COLORS = [
            "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
            "#43A047", "#E53935", "#6D4C41", "#1E88E5"
        ]
        user_colors = {u: COLORS[i % len(COLORS)] for i, u in enumerate(users)}

        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day.month != month_v:
                    cols[i].markdown(f"<div style='opacity:.3'>{day.day}</div>", unsafe_allow_html=True)
                    continue

                assigned = day_map.get(day.isoformat())
                if assigned:
                    cols[i].markdown(
                        f"<div style='background:{user_colors[assigned]};color:white;"
                        f"border-radius:10px TAB3;padding:8px;text-align:center;font-size:12px'>"
                        f"{day.day}<br>{users[assigned]['name']}</div>",
                        unsafe_allow_html=True
                    )
                else:
                    cols[i].markdown(
                        f"<div style='border:2px dashed #D32F2F;color:#B71C1C;"
                        f"border-radius:10px;padding:8px;text-align:center;font-size:11px'>"
                        f"{day.day}<br>NON COUVERT</div>",
                        unsafe_allow_html=True
                    )

    if admin:
        if not st.session_state.planning_locked:
            if st.button("🔒 Verrouiller le planning", key="lock_planning"):
                st.session_state.planning_locked = True
                st.success("Planning verrouillé")
        else:
            st.success("🔒 Planning verrouillé")

# ============================================================
# TAB 4 — RÈGLES RH
# ============================================================
with tab4:
    st.markdown("""
<div style="background:#263238;color:white;padding:16px;border-radius:10px">
<b>📜 Règles RH</b><br>
- 1 jour = <b>9 heures</b><br>
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
    if "blocks" in locals():
        monthly_stats = compute_hours(blocks)
        cumulative_stats = compute_cumulative_hours(year_v, month_v)
        rolling_stats = compute_rolling_12_months(year_v, month_v)

        # ➕ NOUVEAU : compteurs RH
        weekends_stats, holidays_stats = compute_weekends_and_holidays(
            blocks,
            year_v,
            month_v,
        )

        for user_email, user_info in users.items():
            if not admin and user_email != current_email:
                continue

            # 🔹 Contrat horaire mensuel (Firestore)
            contract_hours = int(user_info.get("monthly_hours") or 0)

            # 🔹 Heures calculées depuis le planning
            computed_hours = monthly_stats.get(user_email, {}).get("hours", 0)

            # 🔹 Heures mensuelles ajustées (Firestore)
            stored_hours = load_monthly_hours(user_email, year_v, month_v)
            month_hours = stored_hours if stored_hours is not None else computed_hours

            # 🔧 Correction des cumuls (évite double comptage)
            raw_cumulative = cumulative_stats.get(user_email, 0)
            corrected_cumulative = raw_cumulative - computed_hours + month_hours

            raw_rolling = rolling_stats.get(user_email, 0)
            corrected_rolling = raw_rolling - computed_hours + month_hours

            col_left, col_right = st.columns([3, 1])

            with col_left:
                st.markdown(
                    f"""
**{user_info['name']}**

📄 **Contrat horaire mensuel** : {contract_hours} h  
⏱️ **Heures du mois** : {month_hours} h  
🟪 **Week-ends effectués** : {weekends_stats.get(user_email, 0)}  
🟥 **Jours fériés** : {holidays_stats.get(user_email, 0)}  
📊 **Cumul année** : {corrected_cumulative} h  
🔄 **Glissant 12 mois** : {corrected_rolling} h
""",
                )

            with col_right:
                new_hours = st.number_input(
                    "Heures du mois",
                    min_value=0,
                    max_value=300,
                    step=1,
                    value=int(month_hours),
                    key=f"hours_{user_email}_{year_v}_{month_v}",
                )

                if new_hours != month_hours:
                    save_monthly_hours(user_email, year_v, month_v, int(new_hours))
                    st.rerun()
    else:
        st.info("Aucun planning disponible.")

# ============================================================
# TAB 6 — PLANNINGS VERROUILLÉS
# ============================================================
with tab6:
    st.markdown("## 🔒 Plannings verrouillés")

    users = get_all_users()
    found = False

    for year_locked in [2026, 2027]:
        for month_locked in range(1, 13):
            proposals = load_planning_proposals(year_locked, month_locked)
            proposal = proposals.get("current")

            if not proposal:
                continue

            found = True
            blocks = proposal["planning"]["blocks"]

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
                        📅 {calendar.month_name[month_locked]} {year_locked}
                    </h3>
                </div>
                """,
                unsafe_allow_html=True
            )

            # ====================================================
            # ➕ BOUTONS EXPORT (CORRIGÉ)
            # ====================================================
            col_a, col_b, _ = st.columns([2, 2, 6])

            with col_a:
                excel_buffer = export_planning_excel_calendar_colored(
                    blocks=blocks,
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
                    planning=proposal["planning"],
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
            # AFFICHAGE CALENDRIER (INCHANGÉ)
            # ====================================================
            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdatescalendar(year_locked, month_locked)

            COLORS = [
                "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
                "#43A047", "#E53935", "#6D4C41", "#1E88E5"
            ]
            user_colors = {u: COLORS[i % len(COLORS)] for i, u in enumerate(users)}

            day_map = {}
            for blk in blocks:
                cur = blk["start"]
                while cur <= blk["end"]:
                    if cur.month == month_locked:
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
                                {day.day}<br>{users[assigned]['name']}
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