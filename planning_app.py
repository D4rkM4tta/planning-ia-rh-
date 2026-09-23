import streamlit as st
import calendar
import datetime as dt

from firebase_client import (
    login_user,
    logout_user,
    is_admin,
    load_availability,
    save_availability,
    load_forced_assignments,
    save_forced_assignment,
    get_all_users,
    load_planning_proposals,
    save_planning_proposal,
    set_planning_lock,
    is_planning_locked,
)

from components.calendar_availability import (
    inject_availability_css,
    availability_legend,
    render_availability_static,
    render_availability_editor,
)
from planner_engine import generate_planning
from planning_exports import export_planning_excel_calendar_colored
from planning_exports import export_planning_ical
from planning_stats import render_hours_dashboard
from theme import (
    inject_css,
    user_theme,
    esc,
    abbrev,
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
inject_availability_css()

# Amplitude 9h → 19h, 1h de repas non comptabilisée
HOURS_PER_DAY = 9

YEARS = [2026, 2027]

MONTH_LABELS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}

DOW = [
    ("Lun", "L"), ("Mar", "M"), ("Mer", "M"), ("Jeu", "J"),
    ("Ven", "V"), ("Sam", "S"), ("Dim", "D"),
]


# ============================================================
# UTILITAIRES
# ============================================================
def month_label(month: int) -> str:
    return MONTH_LABELS.get(month, str(month))


def display_name(users: dict, email: str) -> str:
    if not email:
        return "—"
    return users.get(email, {}).get("name") or email.split("@")[0]


def short_name(users: dict, email: str) -> str:
    return display_name(users, email).split(" ")[0]


def dow_header() -> list:
    return [
        f'<div class="pl-dow">{full}<span class="pl-dow-s">{sh}</span></div>'
        for full, sh in DOW
    ]


def name_cell(full: str, color: str) -> str:
    return (
        f'<div class="pl-name" style="color:{color}">{esc(full)}'
        f'<span class="pl-name-s">{esc(abbrev(full))}</span></div>'
    )


def normalize_availability(raw: dict) -> dict:
    return {str(k)[:10]: True for k, v in raw.items() if v is True}


def availability_of(users: dict, email: str, year: int, month: int) -> set:
    """
    Disponibilités lues depuis le cache utilisateurs, sans requête
    Firestore supplémentaire : la vue déroulante parcourt beaucoup
    de mois.
    """
    raw = users.get(email, {}).get(f"availability_{year}_{month}", {}) or {}
    return {str(k)[:10] for k, v in raw.items() if v is True}


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
# RENDU DU CALENDRIER DE PLANNING
# ============================================================
def render_calendar(*, users, theme, day_map, year, month,
                    uncovered_label="Non couvert", show_legend=True,
                    show_stats=True):
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    parts = ['<div class="pl-grid">']
    parts += dow_header()
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
                    f'{name_cell(short_name(users, assigned), c["fg"])}'
                    f'</div>'
                )
            else:
                parts.append(
                    f'<div class="pl-cell" style="background:{DANGER_BG};'
                    f'border:1.5px dashed {DANGER_LINE}">'
                    f'<div class="pl-num" style="color:{DANGER_FG}">{day.day}</div>'
                    f'<div class="pl-name" style="color:{DANGER_FG}">'
                    f'{uncovered_label}<span class="pl-name-s">—</span>'
                    f'</div></div>'
                )

    parts.append("</div>")

    if show_legend:
        present = sorted({u for u in day_map.values() if u})
        if present:
            chips = []
            for u in present:
                c = theme.get(u, {})
                first = short_name(users, u)
                chips.append(
                    f'<span class="pl-chip" style="background:'
                    f'{c.get("bg", "#D3D1C7")};color:{c.get("fg", "#2C2C2A")}">'
                    f'{esc(abbrev(first))} · {esc(display_name(users, u))}</span>'
                )
            parts.append(f'<div class="pl-legend">{"".join(chips)}</div>')

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
                 badge_bg: str = OK_BG, badge_fg: str = OK_FG,
                 top: int = 0):
    chip = ""
    if badge:
        chip = (
            f'<span class="pl-badge" style="background:{badge_bg};'
            f'color:{badge_fg}">{esc(badge)}</span>'
        )
    st.markdown(
        f'<div class="pl-head" style="margin-top:{top}px">'
        f'<div class="pl-title">{esc(title)}{chip}</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# SESSION
# ============================================================
st.session_state.setdefault("auth_user", None)
st.session_state.setdefault("forced_assignments", {})
st.session_state.setdefault("av_edit", None)


# ============================================================
# LOGIN
# ============================================================
def login_screen():
    st.markdown("<div style='height:4vh'></div>", unsafe_allow_html=True)
    left, mid, right = st.columns([1, 1.6, 1])

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
head_left, head_right = st.columns([4, 1])

with head_left:
    role_bg, role_fg = (WARN_BG, WARN_FG) if admin else (NEUTRAL_BG, NEUTRAL_FG)
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;'
        f'margin-bottom:2px;flex-wrap:wrap">'
        f'<span style="font-size:18px;font-weight:500;color:{TEXT}">'
        f'Planning IA RH</span>'
        f'<span class="pl-badge" style="background:{role_bg};color:{role_fg};'
        f'margin:0">{"Admin" if admin else "Collaborateur"}</span></div>'
        f'<div style="font-size:12px;color:{TEXT_MUTED}">{esc(current_email)}</div>',
        unsafe_allow_html=True,
    )

with head_right:
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    if st.button("Déconnexion", key="logout_btn", use_container_width=True):
        logout_user()
        st.rerun()

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ============================================================
# ONGLETS
# ============================================================
tab_feed, tab_admin, tab_rules, tab_hours = st.tabs([
    "Plannings",
    "Admin",
    "Règles",
    "Heures",
])


# ============================================================
# QUELS MOIS AFFICHER
# ============================================================
def months_to_show():
    """
    Mois verrouillés (y compris passés) + tous les mois à venir,
    dans l'ordre chronologique.
    """
    today = dt.date.today()
    out = []
    for y in YEARS:
        for m in range(1, 13):
            locked = is_planning_locked(y, m)
            upcoming = (y, m) >= (today.year, today.month)
            if locked or upcoming:
                out.append((y, m, locked))
    return out


# ============================================================
# ONGLET PRINCIPAL — FIL DES MOIS
# ============================================================
with tab_feed:
    editing = st.session_state.av_edit

    st.caption(
        "Les mois verrouillés affichent le planning définitif. "
        "Sur les mois à venir, indiquez vos disponibilités : "
        "elles ne sont visibles que par vous et l'administrateur."
    )
    st.markdown(availability_legend(), unsafe_allow_html=True)

    feed = months_to_show()

    if not feed:
        st.info("Aucun mois à afficher.")

    for y, m, locked in feed:
        proposals = load_planning_proposals(y, m)
        proposal = proposals.get("current")
        forced = load_forced_assignments(y, m) or {}

        # ---------- En-tête du mois ----------
        if locked:
            month_header(f"{month_label(m)} {y}", "Verrouillé", top=26)
        elif proposal:
            month_header(f"{month_label(m)} {y}", "Planning proposé",
                         NEUTRAL_BG, NEUTRAL_FG, top=26)
        else:
            month_header(f"{month_label(m)} {y}", "À venir",
                         NEUTRAL_BG, NEUTRAL_FG, top=26)

        st.markdown('<div class="pl-wrap">', unsafe_allow_html=True)

        # ---------- Mois verrouillé : le planning ----------
        if locked:
            blocks_l = proposal["planning"]["blocks"]
            render_calendar(
                users=users, theme=theme,
                day_map=build_day_map(blocks_l, y, m),
                year=y, month=m, uncovered_label="—",
            )
            st.markdown("</div>", unsafe_allow_html=True)

            col_a, col_b = st.columns(2)
            with col_a:
                st.download_button(
                    label="Excel",
                    data=export_planning_excel_calendar_colored(
                        blocks=blocks_l, users=users,
                        user_colors={e: c["dot"] for e, c in theme.items()},
                        year=y, month=m,
                    ),
                    file_name=f"planning_{y}_{m:02d}.xlsx",
                    mime=("application/vnd.openxmlformats-officedocument"
                          ".spreadsheetml.sheet"),
                    key=f"excel_{y}_{m}",
                    use_container_width=True,
                )
            with col_b:
                st.download_button(
                    label="iCal",
                    data=export_planning_ical(
                        planning=proposal["planning"], users=users,
                        year=y, month=m,
                    ),
                    file_name=f"planning_{y}_{m:02d}.ics",
                    mime="text/calendar",
                    key=f"ical_{y}_{m}",
                    use_container_width=True,
                )

            if admin:
                if st.button("Déverrouiller", key=f"unlock_{y}_{m}"):
                    set_planning_lock(y, m, False)
                    st.rerun()
            continue

        # ---------- Mois à venir : mes disponibilités ----------
        stored = availability_of(users, current_email, y, m)

        if editing == (y, m):
            render_availability_editor(
                email=current_email, year=y, month=m,
                forced=forced, users=users,
                save_fn=save_availability, stored_days=stored,
            )
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            render_availability_static(
                year=y, month=m, selected=stored,
                forced=forced, users=users,
            )
            st.markdown("</div>", unsafe_allow_html=True)

            if st.button("Modifier mes disponibilités",
                         key=f"edit_{y}_{m}", use_container_width=True):
                st.session_state.av_edit = (y, m)
                st.rerun()

        # ---------- Actions administrateur ----------
        if admin:
            a1, a2 = st.columns(2)

            if a1.button("Générer le planning", key=f"gen_{y}_{m}",
                         use_container_width=True):
                availability_by_user = {
                    u: normalize_availability(load_availability(u, y, m))
                    for u in users
                }
                planning = generate_planning(
                    year=y, month=m, users=users,
                    availability_by_user=availability_by_user,
                    forced_assignments=forced,
                )
                save_planning_proposal(y, m, "current", planning, current_email)
                for warning in planning.get("warnings", []):
                    st.warning(warning)
                st.rerun()

            if proposal:
                if a2.button("Verrouiller", key=f"lock_{y}_{m}",
                             type="primary", use_container_width=True):
                    set_planning_lock(y, m, True, current_email)
                    st.rerun()

            if proposal:
                with st.expander("Voir le planning proposé"):
                    render_calendar(
                        users=users, theme=theme,
                        day_map=build_day_map(
                            proposal["planning"]["blocks"], y, m
                        ),
                        year=y, month=m,
                    )

            with st.expander(f"Forçage administrateur ({len(forced)} jour(s))"):
                last_day = calendar.monthrange(y, m)[1]
                f1, f2 = st.columns(2)

                fday = f1.date_input(
                    "Jour", value=dt.date(y, m, 1),
                    min_value=dt.date(y, m, 1),
                    max_value=dt.date(y, m, last_day),
                    format="DD/MM/YYYY", key=f"fd_{y}_{m}",
                )

                labels = {
                    info.get("name", mail.split("@")[0]): mail
                    for mail, info in users.items()
                }
                chosen = f2.selectbox("Collaborateur", options=sorted(labels),
                                      key=f"fu_{y}_{m}")

                dkey = fday.isoformat()
                g1, g2 = st.columns(2)

                if g1.button("Forcer ce jour", key=f"fb_{y}_{m}",
                             use_container_width=True):
                    save_forced_assignment(y, m, dkey, labels[chosen])
                    st.rerun()

                if dkey in forced:
                    if g2.button("Annuler le forçage", key=f"ub_{y}_{m}",
                                 use_container_width=True):
                        save_forced_assignment(y, m, dkey, None)
                        st.rerun()

                if forced:
                    lines = []
                    for d in sorted(forced):
                        who = users.get(forced[d], {}).get(
                            "name", forced[d].split("@")[0]
                        )
                        pretty = dt.date.fromisoformat(d).strftime("%d/%m")
                        lines.append(
                            f'<div style="font-size:12px;color:{TEXT_SOFT};'
                            f'padding:2px 0">{pretty} — {esc(who)}</div>'
                        )
                    st.markdown("".join(lines), unsafe_allow_html=True)


# ============================================================
# ONGLET ADMIN — DISPONIBILITÉS CROISÉES
# ============================================================
with tab_admin:
    if not admin:
        st.info("Onglet réservé aux administrateurs.")
    else:
        c1, c2 = st.columns(2)
        year_admin = c1.selectbox("Année", YEARS, index=0, key="admin_year")
        month_admin = c2.selectbox("Mois", list(range(1, 13)),
                                   index=dt.date.today().month - 1,
                                   format_func=month_label, key="admin_month")

        dispo_by_day = {}
        for u in users:
            for d in availability_of(users, u, year_admin, month_admin):
                dispo_by_day.setdefault(d, []).append(u)

        month_header(f"Disponibilités — {month_label(month_admin)} {year_admin}")

        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(
            year_admin, month_admin
        )

        parts = ['<div class="pl-wrap"><div class="pl-grid">']
        parts += dow_header()
        parts.append('</div><div class="pl-grid">')

        for week in weeks:
            for day in week:
                if day.month != month_admin or day.year != year_admin:
                    parts.append(
                        f'<div class="pl-off"><div class="pl-num">{day.day}'
                        f'</div></div>'
                    )
                    continue

                inner = ""
                for u in dispo_by_day.get(day.isoformat(), []):
                    c = theme.get(u, {})
                    first = short_name(users, u)
                    inner += (
                        f'<div style="background:{c.get("bg", "#D3D1C7")};'
                        f'border-radius:5px;padding:1px 4px;margin-top:2px">'
                        f'{name_cell(first, c.get("fg", "#2C2C2A"))}</div>'
                    )

                parts.append(
                    f'<div class="pl-cell" style="background:{CARD};'
                    f'min-height:78px">'
                    f'<div class="pl-num" style="color:{TEXT_MUTED}">'
                    f'{day.day}</div>{inner}</div>'
                )

        parts.append("</div></div>")
        st.markdown("".join(parts), unsafe_allow_html=True)


# ============================================================
# ONGLET RÈGLES
# ============================================================
with tab_rules:
    st.markdown(
        f"""
<div class="pl-wrap" style="max-width:640px">
  <div style="font-size:16px;font-weight:500;margin-bottom:12px;color:{TEXT}">
    Règles RH</div>
  <div style="font-size:14px;color:{TEXT_SOFT};line-height:1.9">
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
# ONGLET HEURES
# ============================================================
with tab_hours:
    c1, c2 = st.columns(2)
    year_h = c1.selectbox("Année", YEARS, index=0, key="hours_year")
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
            f"Aucun planning généré pour {month_label(month_h)} {year_h}."
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