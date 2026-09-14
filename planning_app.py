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
    set_planning_lock,
    is_planning_locked,
)

from components.calendar_availability import availability_calendar
from planner_engine import generate_planning
from planning_exports import export_planning_excel_calendar_colored
from planning_exports import export_planning_ical
from planning_stats import render_hours_dashboard
from theme import (
    inject_css,
    user_theme,
    esc,
    CARD,
    TEXT,
    TEXT_SOFT,
    TEXT_MUTED,
    DANGER_BG,
    DANGER_FG,
    DANGER_LINE,
    OK_BG,
    OK_FG,
    WARN_BG,
    WARN_FG,
    NEUTRAL_BG,
    NEUTRAL_FG,
)

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="Planning IA RH",
    page_icon="📅",
    layout="wide",
)

inject_css()

# Amplitude 9h → 19h, 1h de repas non comptabilisée
HOURS_PER_DAY = 9

MONTH_LABELS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}

DOW = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


# ============================================================
# UTILITAIRES
# ============================================================
def month_label(month: int) -> str:
    return MONTH_LABELS.get(month, str(month))


def display_name(users: dict, email: str) -> str:
    """Nom d'affichage robuste même si l'utilisateur n'existe plus."""
    if not email:
        return "—"
    return users.get(email, {}).get("name") or email.split("@")[0]


def short_name(users: dict, email: str) -> str:
    """Prénom seul, pour tenir dans une cellule de calendrier."""
    return display_name(users, email).split(" ")[0]


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
    override = users.get(user_email, {}).get(f"hours_{year}_{month}")
    return int(override) if override is not None else int(computed_hours)


def compute_year_cumulative(users: dict, year: int, up_to_month: int,
                            only_locked: bool):
    """
    Cumul annuel par collaborateur, de janvier jusqu'au mois demandé.
    only_locked=True → uniquement les plannings verrouillés.
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
    for m in range(12, 0, -1):
        proposals = load_planning_proposals(year, m)
        proposal = proposals.get("current")
        if proposal and proposal.get("locked"):
            return m
    return None


def compute_weekends_and_holidays(blocks, year: int, month: int):
    FIXED_HOLIDAYS = {
        dt.date(year, 1, 1), dt.date(year, 5, 1), dt.date(year, 5, 8),
        dt.date(year, 7, 14), dt.date(year, 8, 15), dt.date(year, 11, 1),
        dt.date(year, 11, 11), dt.date(year, 12, 25),
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


def build_day_map(blocks, year: int, month: int) -> dict:
    day_map = {}
    for block in blocks:
        if not block.get("assigned_to"):
            continue
        cur = block["start"]
        while cur <= block["end"]:
            if cur.year == year and cur.month == month:
                day_map[cur.isoformat()] = block["assigned_to"]
            cur += dt.timedelta(days=1)
    return day_map


# ============================================================
# RENDU DU CALENDRIER
# ============================================================
def render_calendar(*, users, theme, day_map, year, month,
                    uncovered_label="Non couvert", show_legend=True,
                    show_stats=True):
    """Calendrier mensuel en une seule injection HTML."""
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    parts = ['<div class="pl-grid">']
    parts += [f'<div class="pl-dow">{d}</div>' for d in DOW]
    parts.append("</div>")
    parts.append('<div class="pl-grid">')

    covered = 0
    total = 0

    for week in weeks:
        for day in week:
            if day.year != year or day.month != month:
                parts.append(
                    f'<div class="pl-off"><div class="pl-num">{day.day}</div></div>'
                )
                continue

            total += 1
            assigned = day_map.get(day.isoformat())

            if assigned:
                covered += 1
                c = theme.get(assigned, {"bg": "#D3D1C7", "fg": "#2C2C2A",
                                         "dim": "#5F5E5A"})
                parts.append(
                    f'<div class="pl-cell" style="background:{c["bg"]}">'
                    f'<div class="pl-num" style="color:{c["dim"]}">{day.day}</div>'
                    f'<div class="pl-name" style="color:{c["fg"]}">'
                    f'{esc(short_name(users, assigned))}</div></div>'
                )
            else:
                parts.append(
                    f'<div class="pl-cell" style="background:{DANGER_BG};'
                    f'border:1.5px dashed {DANGER_LINE}">'
                    f'<div class="pl-num" style="color:{DANGER_FG}">{day.day}</div>'
                    f'<div class="pl-name" style="color:{DANGER_FG}">'
                    f'{uncovered_label}</div></div>'
                )

    parts.append("</div>")

    if show_legend:
        present = sorted({u for u in day_map.values() if u})
        if present:
            chips = "".join(
                f'<span class="pl-chip" style="background:'
                f'{theme.get(u, {}).get("bg", "#D3D1C7")};'
                f'color:{theme.get(u, {}).get("fg", "#2C2C2A")}">'
                f'{esc(display_name(users, u))}</span>'
                for u in present
            )
            parts.append(f'<div class="pl-legend">{chips}</div>')

    if show_stats and total:
        rate = round(covered / total * 100)
        hours = covered * HOURS_PER_DAY
        missing = total - covered
        miss_color = DANGER_FG if missing else TEXT
        parts.append(
            f'<div class="pl-stats">'
            f'<div><div class="pl-stat-l">Couverture</div>'
            f'<div class="pl-stat-v">{rate} %</div></div>'
            f'<div><div class="pl-stat-l">Heures</div>'
            f'<div class="pl-stat-v">{hours} h</div></div>'
            f'<div><div class="pl-stat-l">Non couverts</div>'
            f'<div class="pl-stat-v" style="color:{miss_color}">{missing} j</div></div>'
            f'</div>'
        )

    st.markdown("".join(parts), unsafe_allow_html=True)


def month_header(title: str, badge: str | None = None,
                 badge_bg: str = OK_BG, badge_fg: str = OK_FG):
    chip = ""
    if badge:
        chip = (
            f'<span class="pl-badge" style="background:{badge_bg};'
            f'color:{badge_fg}">{esc(badge)}</span>'
        )
    st.markdown(
        f'<div class="pl-head"><div class="pl-title">{esc(title)}{chip}</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# SESSION
# ============================================================
st.session_state.setdefault("auth_user", None)
st.session_state.setdefault("forced_assignments", {})


# ============================================================
# LOGIN
# ============================================================
def login_screen():
    st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
    left, mid, right = st.columns([1, 1.1, 1])

    with mid:
        st.markdown(
            f'<div style="width:46px;height:46px;border-radius:12px;'
            f'background:#B5D4F4;display:flex;align-items:center;'
            f'justify-content:center;font-size:23px;margin-bottom:14px">📅</div>'
            f'<div style="font-size:20px;font-weight:500;color:{TEXT}">'
            f'Planning IA RH</div>'
            f'<div style="font-size:13px;color:{TEXT_SOFT};margin-bottom:18px">'
            f'Connectez-vous pour accéder à vos plannings</div>',
            unsafe_allow_html=True,
        )

        email = st.text_input("Email", key="login_email",
                              placeholder="nom@exemple.fr")
        password = st.text_input("Mot de passe", type="password",
                                 key="login_pwd", placeholder="••••••••")

        if st.button("Se connecter", key="login_btn",
                     type="primary", use_container_width=True):
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
theme = user_theme(users)

# ============================================================
# BARRE SUPÉRIEURE
# ============================================================
head_left, head_right = st.columns([5, 1])

with head_left:
    role_bg, role_fg = (WARN_BG, WARN_FG) if admin else (NEUTRAL_BG, NEUTRAL_FG)
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;'
        f'margin-bottom:2px">'
        f'<span style="font-size:20px;font-weight:500;color:{TEXT}">'
        f'Planning IA RH</span>'
        f'<span class="pl-badge" style="background:{role_bg};color:{role_fg};'
        f'margin:0">{"Admin" if admin else "Collaborateur"}</span></div>'
        f'<div style="font-size:13px;color:{TEXT_MUTED}">{esc(current_email)}</div>',
        unsafe_allow_html=True,
    )

with head_right:
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    if st.button("Déconnexion", key="logout_btn", use_container_width=True):
        logout_user()
        st.rerun()

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# ============================================================
# ONGLETS
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Mes disponibilités",
    "Admin",
    "Planning",
    "Règles RH",
    "Heures",
    "Planning validé",
])

# ============================================================
# TAB 1 — DISPONIBILITÉS
# ============================================================
with tab1:
    c1, c2, _ = st.columns([1, 1, 3])
    year = c1.selectbox("Année", [2026, 2027], index=0, key="user_year")
    month = c2.selectbox("Mois", list(range(1, 13)), index=2,
                         format_func=month_label, key="user_month")

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
# TAB 2 — ADMIN (disponibilités croisées)
# ============================================================
with tab2:
    if not admin:
        st.info("Onglet réservé aux administrateurs.")
    else:
        c1, c2, _ = st.columns([1, 1, 3])
        year_admin = c1.selectbox("Année", [2026, 2027], index=0,
                                  key="admin_year")
        month_admin = c2.selectbox("Mois", list(range(1, 13)), index=2,
                                   format_func=month_label, key="admin_month")

        availability_by_user = {
            u: normalize_availability(load_availability(u, year_admin, month_admin))
            for u in users
        }

        dispo_by_day = {}
        for u, days in availability_by_user.items():
            for d in days:
                dispo_by_day.setdefault(d, []).append(u)

        month_header(f"Disponibilités — {month_label(month_admin)} {year_admin}")

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdatescalendar(year_admin, month_admin)

        parts = ['<div class="pl-wrap"><div class="pl-grid">']
        parts += [f'<div class="pl-dow">{d}</div>' for d in DOW]
        parts.append('</div><div class="pl-grid">')

        for week in weeks:
            for day in week:
                if day.month != month_admin or day.year != year_admin:
                    parts.append(
                        f'<div class="pl-off"><div class="pl-num">{day.day}</div></div>'
                    )
                    continue

                available = dispo_by_day.get(day.isoformat(), [])
                inner = "".join(
                    f'<div style="background:{theme.get(u, {}).get("bg", "#D3D1C7")};'
                    f'color:{theme.get(u, {}).get("fg", "#2C2C2A")};'
                    f'border-radius:5px;padding:1px 5px;margin-top:2px;'
                    f'font-size:10px">{esc(short_name(users, u))}</div>'
                    for u in available
                )
                parts.append(
                    f'<div class="pl-cell" style="background:{CARD};'
                    f'min-height:78px">'
                    f'<div class="pl-num" style="color:{TEXT_MUTED}">{day.day}</div>'
                    f'{inner}</div>'
                )

        parts.append("</div></div>")
        st.markdown("".join(parts), unsafe_allow_html=True)

# ============================================================
# TAB 3 — PLANNING
# ============================================================
with tab3:
    c1, c2, c3 = st.columns([1, 1, 3])
    year_v = c1.selectbox("Année", [2026, 2027], index=0, key="view_year")
    month_v = c2.selectbox("Mois", list(range(1, 13)), index=2,
                           format_func=month_label, key="view_month")

    locked_v = is_planning_locked(year_v, month_v)

    with c3:
        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
        if admin and not locked_v:
            if st.button("Générer le planning", key="generate_planning",
                         type="primary"):
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

                save_planning_proposal(year_v, month_v, "current",
                                       planning, current_email)

                for warning in planning.get("warnings", []):
                    st.warning(warning)

                st.rerun()

    proposals = load_planning_proposals(year_v, month_v)
    proposal = proposals.get("current")

    if locked_v:
        month_header(f"{month_label(month_v)} {year_v}", "Verrouillé")
    elif proposal:
        month_header(f"{month_label(month_v)} {year_v}", "Brouillon",
                     NEUTRAL_BG, NEUTRAL_FG)
    else:
        month_header(f"{month_label(month_v)} {year_v}")

    if not proposal:
        st.info("Aucun planning généré pour ce mois.")
    else:
        blocks = proposal["planning"]["blocks"]
        day_map = build_day_map(blocks, year_v, month_v)

        st.markdown('<div class="pl-wrap">', unsafe_allow_html=True)
        render_calendar(users=users, theme=theme, day_map=day_map,
                        year=year_v, month=month_v)
        st.markdown("</div>", unsafe_allow_html=True)

        if admin:
            st.markdown("<div style='height:14px'></div>",
                        unsafe_allow_html=True)
            if not locked_v:
                st.caption(
                    "Une fois verrouillé, ce planning ne peut plus être "
                    "régénéré et ses heures entrent dans le cumul annuel."
                )
                if st.button("Verrouiller le planning", key="lock_planning"):
                    set_planning_lock(year_v, month_v, True, current_email)
                    st.rerun()
            else:
                locked_by = proposal.get("locked_by") or "—"
                locked_at = (proposal.get("locked_at") or "")[:10]
                st.caption(f"Verrouillé par {locked_by} le {locked_at}")
                if st.button("Déverrouiller", key="unlock_planning"):
                    set_planning_lock(year_v, month_v, False)
                    st.rerun()

# ============================================================
# TAB 4 — RÈGLES RH
# ============================================================
with tab4:
    st.markdown(
        f"""
<div class="pl-wrap" style="max-width:640px">
  <div style="font-size:16px;font-weight:500;margin-bottom:12px;color:{TEXT}">
    Règles RH</div>
  <div style="font-size:14px;color:{TEXT_SOFT};line-height:2">
    <div>Amplitude <b style="color:{TEXT};font-weight:500">9h → 19h</b>, soit
      <b style="color:{TEXT};font-weight:500">9 heures</b> comptabilisées
      (1 h de repas non comptée)</div>
    <div>Pas de blocs consécutifs pour un même collaborateur</div>
    <div>Respect strict des disponibilités saisies</div>
    <div>Le forçage administrateur est prioritaire</div>
    <div>Tous les collaborateurs doivent apparaître au planning</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

# ============================================================
# TAB 5 — HEURES
# ============================================================
with tab5:
    c1, c2, _ = st.columns([1, 1, 3])
    year_h = c1.selectbox("Année", [2026, 2027], index=0, key="hours_year")
    month_h = c2.selectbox("Mois analysé", list(range(1, 13)),
                           index=dt.date.today().month - 1,
                           format_func=month_label, key="hours_month")

    proposals_h = load_planning_proposals(year_h, month_h)
    proposal_h = proposals_h.get("current")
    blocks_h = proposal_h["planning"]["blocks"] if proposal_h else []
    month_is_locked = bool(proposal_h and proposal_h.get("locked"))

    ref_month = last_locked_month(year_h)
    cumul_up_to = ref_month or 12

    cumul_locked, locked_months = compute_year_cumulative(
        users, year_h, cumul_up_to, only_locked=True
    )
    cumul_preview, preview_months = compute_year_cumulative(
        users, year_h, 12, only_locked=False
    )

    if month_is_locked:
        month_header(f"Heures — {month_label(month_h)} {year_h}", "Verrouillé")
    else:
        month_header(f"Heures — {month_label(month_h)} {year_h}",
                     "Brouillon", NEUTRAL_BG, NEUTRAL_FG)

    if not ref_month:
        st.warning(
            f"Aucun planning verrouillé en {year_h} : le cumul de référence "
            "est à 0. Les chiffres ci-dessous ne sont qu'un aperçu."
        )

    weekends_stats, holidays_stats = compute_weekends_and_holidays(
        blocks_h, year_h, month_h
    )

    if not blocks_h:
        st.info(
            f"Aucun planning généré pour {month_label(month_h)} {year_h}. "
            "Les colonnes du mois sont à zéro."
        )

    render_hours_dashboard(
        users=users,
        theme=theme,
        blocks=blocks_h,
        year=year_h,
        month=month_h,
        month_name=month_label(month_h),
        ref_month_name=month_label(ref_month) if ref_month else None,
        locked_count=len(locked_months),
        pending_months=[month_label(m) for m in preview_months
                        if m not in locked_months],
        weekends_stats=weekends_stats,
        holidays_stats=holidays_stats,
        cumul_locked=cumul_locked,
        cumul_preview=cumul_preview,
        admin=admin,
        current_email=current_email,
    )

# ============================================================
# TAB 6 — PLANNINGS VERROUILLÉS
# ============================================================
with tab6:
    found = False

    for year_locked in [2026, 2027]:
        for month_locked in range(1, 13):
            proposals_l = load_planning_proposals(year_locked, month_locked)
            proposal_l = proposals_l.get("current")

            if not proposal_l or not proposal_l.get("locked"):
                continue

            found = True
            blocks_l = proposal_l["planning"]["blocks"]
            day_map_l = build_day_map(blocks_l, year_locked, month_locked)

            st.markdown(
                f'<div class="pl-head" style="margin-top:22px">'
                f'<div class="pl-title">{month_label(month_locked)} '
                f'{year_locked}<span class="pl-badge" '
                f'style="background:{OK_BG};color:{OK_FG}">Verrouillé</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

            col_a, col_b, _ = st.columns([1.2, 1.2, 4])

            with col_a:
                excel_buffer = export_planning_excel_calendar_colored(
                    blocks=blocks_l,
                    users=users,
                    user_colors={e: c["dot"] for e, c in theme.items()},
                    year=year_locked,
                    month=month_locked,
                )
                st.download_button(
                    label="Export Excel",
                    data=excel_buffer,
                    file_name=f"planning_{year_locked}_{month_locked:02d}.xlsx",
                    mime=("application/vnd.openxmlformats-officedocument"
                          ".spreadsheetml.sheet"),
                    key=f"excel_{year_locked}_{month_locked}",
                    use_container_width=True,
                )

            with col_b:
                ical_bytes = export_planning_ical(
                    planning=proposal_l["planning"],
                    users=users,
                    year=year_locked,
                    month=month_locked,
                )
                st.download_button(
                    label="Export iCal",
                    data=ical_bytes,
                    file_name=f"planning_{year_locked}_{month_locked:02d}.ics",
                    mime="text/calendar",
                    key=f"ical_{year_locked}_{month_locked}",
                    use_container_width=True,
                )

            st.markdown('<div class="pl-wrap">', unsafe_allow_html=True)
            render_calendar(
                users=users, theme=theme, day_map=day_map_l,
                year=year_locked, month=month_locked,
                uncovered_label="—",
            )
            st.markdown("</div>", unsafe_allow_html=True)

    if not found:
        st.info("Aucun planning verrouillé pour l'instant.")