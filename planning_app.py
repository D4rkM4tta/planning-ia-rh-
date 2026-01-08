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
    is_planning_locked,
    lock_planning,
    load_planning_proposals,
    save_planning_proposal,
    vote_planning,
    validate_planning,
)

from components.calendar_availability import availability_calendar
from planner_engine import generate_planning

st.set_page_config(page_title="Planning IA RH", layout="wide")

# ============================================================
# UTILITAIRES
# ============================================================
def normalize_availability(raw: dict) -> dict:
    return {str(k)[:10]: True for k, v in raw.items() if v is True}


def compute_hours(blocks):
    stats = {}
    for block in blocks:
        user = block["assigned_to"]
        if not user:
            continue
        stats.setdefault(user, {"days": 0, "hours": 0})
        stats[user]["days"] += len(block["days"])
        stats[user]["hours"] += len(block["days"]) * 10
    return stats


# ============================================================
# SESSION
# ============================================================
for key, default in {
    "auth_user": None,
    "forced_assignments": {},
}.items():
    st.session_state.setdefault(key, default)


# ============================================================
# LOGIN
# ============================================================
def login_screen():
    st.title("🔐 Connexion Planning IA RH")
    email = st.text_input("Email")
    password = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if login_user(email, password):
            st.rerun()
        else:
            st.error("Identifiants incorrects")


if not st.session_state.auth_user:
    login_screen()
    st.stop()


email = st.session_state.auth_user["email"]
admin = is_admin()

st.success(f"Connecté : **{email}** — {'Admin' if admin else 'Utilisateur'}")

if st.button("Se déconnecter"):
    logout_user()
    st.rerun()


# ============================================================
# ONGLET
# ============================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📌 Mes disponibilités",
    "📋 Admin",
    "📅 Plannings proposés",
    "📜 Règles RH",
    "⏱️ Heures",
])

# ============================================================
# TAB 1 — DISPONIBILITÉS
# ============================================================
with tab1:
    year = st.selectbox("Année", [2026, 2027], index=0, key="user_year")
    month = st.selectbox("Mois", list(range(1, 13)), index=2, key="user_month")

    if is_planning_locked(year, month):
        st.info("🔒 Planning verrouillé")
    else:
        availability_calendar(
            email=email,
            year=year,
            month=month,
            load_fn=load_availability,
            save_fn=save_availability,
            is_admin=admin,
            users=get_all_users(),
            forced_assignments=st.session_state.forced_assignments,
        )


# ============================================================
# TAB 2 — ADMIN (PREVIEW DISPOS + GÉNÉRATION)
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

        st.subheader("📅 Disponibilités équipe")

        COLORS = [
            "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
            "#43A047", "#E53935", "#6D4C41", "#1E88E5"
        ]
        user_colors = {u: COLORS[i % len(COLORS)] for i, u in enumerate(users)}

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
                    cols[i].markdown(f"<div style='opacity:.3'>{day.day}</div>", unsafe_allow_html=True)
                    continue

                inner = "".join(
                    f"<div style='background:{user_colors[u]};color:white;"
                    f"border-radius:6px;padding:2px 6px;margin:2px 0;"
                    f"font-size:11px;text-align:center;'>"
                    f"{users[u]['name']}</div>"
                    for u in dispo_by_day.get(day.isoformat(), [])
                )

                cols[i].markdown(
                    f"<div style='min-height:90px;background:#ECEFF1;border-radius:8px;padding:6px'>"
                    f"<strong>{day.day}</strong>{inner}</div>",
                    unsafe_allow_html=True
                )

        st.divider()

        if st.button("🚀 Générer 5 plannings"):
            for i in range(5):
                planning = generate_planning(
                    year=year_admin,
                    month=month_admin,
                    users=users,
                    availability_by_user=availability_by_user,
                    forced_assignments=st.session_state.forced_assignments,
                )
                save_planning_proposal(year_admin, month_admin, i + 1, planning, email)

            st.success("✅ 5 plannings générés et proposés")


# ============================================================
# TAB 3 — PLANNINGS PROPOSÉS (VOTES + HEURES PAR PLANNING)
# ============================================================
with tab3:
    year_v = st.selectbox("Année", [2026, 2027], index=0, key="view_year")
    month_v = st.selectbox("Mois", list(range(1, 13)), index=2, key="view_month")

    proposals = load_planning_proposals(year_v, month_v)

    if not proposals:
        st.info("Aucun planning proposé pour ce mois.")
        st.stop()

    users = get_all_users()
    total_users = len(users)

    COLORS = [
        "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
        "#43A047", "#E53935", "#6D4C41", "#1E88E5"
    ]
    user_colors = {u: COLORS[i % len(COLORS)] for i, u in enumerate(users)}

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year_v, month_v)

    for pid, proposal in proposals.items():
        st.divider()
        st.subheader(f"📅 {pid.replace('_', ' ').title()}")

        blocks = proposal["planning"]["blocks"]

        # -------------------------------
        # PREVIEW PLANNING (INCHANGÉ)
        # -------------------------------
        day_map = {}
        for block in blocks:
            cur = block["start"]
            while cur <= block["end"]:
                if cur.month == month_v:
                    day_map[cur.isoformat()] = block["assigned_to"]
                cur += dt.timedelta(days=1)

        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day.month != month_v:
                    cols[i].markdown(f"<div style='opacity:.3'>{day.day}</div>", unsafe_allow_html=True)
                    continue

                u = day_map.get(day.isoformat())
                if u:
                    html = (
                        f"<div style='background:{user_colors[u]};color:white;"
                        f"border-radius:10px;padding:8px;text-align:center;font-size:12px'>"
                        f"{day.day}<br>{users[u]['name']}</div>"
                    )
                else:
                    html = (
                        f"<div style='border:2px dashed #D32F2F;color:#B71C1C;"
                        f"border-radius:10px;padding:8px;text-align:center;font-size:11px'>"
                        f"{day.day}<br>NON COUVERT</div>"
                    )
                cols[i].markdown(html, unsafe_allow_html=True)

        # -------------------------------
        # 🆕 COMPTEUR HEURES PAR PLANNING
        # -------------------------------
        st.markdown("### 📊 Heures mensuelles (ce planning)")

        hours_stats = compute_hours(blocks)

        for u, data in hours_stats.items():
            st.markdown(
                f"""
                <div style="
                    background:{user_colors[u]};
                    color:white;
                    padding:8px;
                    border-radius:8px;
                    margin-bottom:6px;
                    font-size:13px;
                ">
                    <strong>{users[u]['name']}</strong> — ⏱️ {data['hours']} h
                </div>
                """,
                unsafe_allow_html=True
            )

        # -------------------------------
        # VOTES (INCHANGÉ)
        # -------------------------------
        votes = proposal.get("votes", {})
        up = sum(1 for v in votes.values() if v is True)
        down = sum(1 for v in votes.values() if v is False)

        st.markdown(f"### 🗳️ Votes : {len(votes)} / {total_users}")
        st.write(f"👍 {up} | 👎 {down}")

        if len(votes) == total_users:
            st.success("🟢 Tous les votes ont été exprimés")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Je valide", key=f"ok_{pid}"):
                vote_planning(year_v, month_v, pid, email, True)
                st.rerun()
        with c2:
            if st.button("❌ Je rejette", key=f"no_{pid}"):
                vote_planning(year_v, month_v, pid, email, False)
                st.rerun()

        if admin:
            if st.button("🔒 Valider ce planning", key=f"admin_{pid}"):
                validate_planning(year_v, month_v, pid)
                lock_planning(year_v, month_v, blocks)
                st.success("Planning validé définitivement")
                st.rerun()


# ============================================================
# TAB 4 — RÈGLES RH
# ============================================================
with tab4:
    st.markdown("""
### 📜 Règles RH
- 1 jour = **10 heures**
- Pas de blocs consécutifs
- Disponibilités strictes
- Forçage admin prioritaire
- Tous les collaborateurs doivent apparaître
""")


# ============================================================
# TAB 5 — HEURES
# ============================================================
with tab5:
    proposals = load_planning_proposals(year_v, month_v)
    validated = next((p for p in proposals.values() if p["status"] == "VALIDATED"), None)

    if not validated:
        st.info("Aucun planning validé.")
    else:
        stats = compute_hours(validated["planning"]["blocks"])

        for u, data in stats.items():
            if not admin and u != email:
                continue
            st.markdown(
                f"""
                <div style="background:#ECEFF1;padding:12px;border-radius:10px">
                    <strong>{users[u]['name']}</strong><br>
                    📅 {data['days']} jours<br>
                    ⏱️ {data['hours']} heures
                </div>
                """,
                unsafe_allow_html=True
            )