import streamlit as st
import calendar
import datetime as dt
import pandas as pd
from io import BytesIO

from firebase_client import (
    login_user,
    logout_user,
    is_admin,
    load_availability,
    save_availability,
    get_all_users,
    is_planning_locked,
    lock_planning,
)

from components.calendar_availability import availability_calendar
from planner_engine import generate_planning

st.set_page_config(page_title="Planning IA RH", layout="wide")

# ============================================================
# NORMALISATION DES DISPONIBILITÉS (CRITIQUE)
# ============================================================
def normalize_availability(raw: dict) -> dict:
    normalized = {}
    for raw_key, value in raw.items():
        if value is not True:
            continue
        try:
            normalized[str(raw_key)[:10]] = True
        except Exception:
            continue
    return normalized


# ============================================================
# EXPORT EXCEL (STABLE)
# ============================================================
def export_excel(blocks, users):
    rows = []
    for block in blocks:
        current = block["start"]
        while current <= block["end"]:
            rows.append({
                "Date": current.strftime("%Y-%m-%d"),
                "Jour": current.strftime("%A"),
                "Bloc": f"Bloc {block['id']}",
                "Collaborateur": (
                    users[block["assigned_to"]]["name"]
                    if block["assigned_to"] else "NON COUVERT"
                )
            })
            current += dt.timedelta(days=1)

    df = pd.DataFrame(rows)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return output


# ============================================================
# CALCUL DES HEURES (1 jour = 10h)
# ============================================================
def compute_hours(blocks):
    stats = {}
    for block in blocks:
        user = block["assigned_to"]
        if not user:
            continue

        days = len(block["days"])
        hours = days * 10

        if user not in stats:
            stats[user] = {"days": 0, "hours": 0}

        stats[user]["days"] += days
        stats[user]["hours"] += hours

    return stats


# ============================================================
# SESSION
# ============================================================
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "forced_assignments" not in st.session_state:
    st.session_state.forced_assignments = {}

if "generated_planning" not in st.session_state:
    st.session_state.generated_planning = None


# ============================================================
# LOGIN
# ============================================================
def login_screen():
    st.title("🔐 Connexion Planning IA RH")
    email = st.text_input("Email")
    password = st.text_input("Mot de passe", type="password")

    if st.button("Se connecter"):
        if login_user(email, password):
            st.success("Connexion réussie")
            st.rerun()
        else:
            st.error("Identifiants incorrects")


if st.session_state.auth_user is None:
    login_screen()
    st.stop()


# ============================================================
# CONNECTÉ
# ============================================================
email = st.session_state.auth_user["email"]
admin = is_admin()

st.success(f"Connecté : **{email}** — {'Admin' if admin else 'Utilisateur'}")

if st.button("Se déconnecter"):
    logout_user()
    st.rerun()


tab1, tab2, tab3, tab4 = st.tabs([
    "📌 Mes disponibilités",
    "📋 Admin",
    "📜 Règles RH",
    "⏱️ Heures",
])


# ============================================================
# TAB 1 — DISPONIBILITÉS
# ============================================================
with tab1:
    year = st.selectbox("Année", [2026, 2027], index=0)
    month = st.selectbox("Mois", list(range(1, 13)), index=2)

    if is_planning_locked(year, month):
        st.info("🔒 Le planning est verrouillé.")
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
# TAB 2 — ADMIN
# ============================================================
with tab2:
    if not admin:
        st.warning("Accès réservé à l’administrateur")
        st.stop()

    st.header("👥 Disponibilités équipe")

    year_admin = st.selectbox("Année", [2026, 2027], index=0, key="admin_year")
    month_admin = st.selectbox("Mois", list(range(1, 13)), index=2, key="admin_month")

    users = get_all_users()

    availability_by_user = {
        u: normalize_availability(load_availability(u, year_admin, month_admin))
        for u in users
    }

    # ========================================================
    # PREVIEW DES DISPONIBILITÉS (RESTAURÉE)
    # ========================================================
    st.divider()
    st.subheader("📅 Disponibilités renseignées")

    COLORS = [
        "#FB8C00", "#3949AB", "#00ACC1", "#8E24AA",
        "#43A047", "#E53935", "#6D4C41", "#1E88E5"
    ]

    user_colors = {
        email: COLORS[i % len(COLORS)]
        for i, email in enumerate(users)
    }

    dispo_by_day = {}
    for u, avail in availability_by_user.items():
        for d in avail:
            dispo_by_day.setdefault(d, []).append(u)

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year_admin, month_admin)

    headers = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    cols = st.columns(7)
    for i, h in enumerate(headers):
        cols[i].markdown(f"**{h}**")

    for week in weeks:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day.month != month_admin:
                cols[i].markdown(
                    f"<div style='opacity:0.3;text-align:center'>{day.day}</div>",
                    unsafe_allow_html=True
                )
                continue

            inner = ""
            for u in dispo_by_day.get(day.isoformat(), []):
                inner += (
                    f"<div style='background:{user_colors[u]};"
                    "color:white;border-radius:6px;"
                    "padding:2px 6px;margin:2px 0;"
                    "font-size:11px;text-align:center;'>"
                    f"{users[u]['name']}</div>"
                )

            cols[i].markdown(
                f"""
                <div style="min-height:90px;
                            padding:6px;
                            border-radius:8px;
                            background:#ECEFF1;">
                    <strong>{day.day}</strong>
                    {inner}
                </div>
                """,
                unsafe_allow_html=True
            )

    # ========================================================
    # GÉNÉRATION DU PLANNING
    # ========================================================
    st.divider()
    st.subheader("🧠 Génération du planning")

    if st.button("🚀 Générer / Relancer le planning"):
        st.session_state.generated_planning = generate_planning(
            year=year_admin,
            month=month_admin,
            users=users,
            availability_by_user=availability_by_user,
            forced_assignments=st.session_state.forced_assignments,
        )
        st.success("Planning généré")

    if st.session_state.generated_planning:
        result = st.session_state.generated_planning

        st.divider()
        st.subheader("📅 Planning généré")

        day_assignments = {}
        for block in result["blocks"]:
            current = block["start"]
            while current <= block["end"]:
                if current.month == month_admin:
                    day_assignments[current.isoformat()] = block["assigned_to"]
                current += dt.timedelta(days=1)

        for week in weeks:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day.month != month_admin:
                    cols[i].markdown(
                        f"<div style='opacity:0.3;text-align:center'>{day.day}</div>",
                        unsafe_allow_html=True
                    )
                    continue

                user = day_assignments.get(day.isoformat())
                if user:
                    html = f"""
                    <div style="background:{user_colors[user]};
                        color:white;border-radius:10px;
                        padding:10px;text-align:center;">
                        <div>{day.day}</div>
                        <div>{users[user]['name']}</div>
                    </div>
                    """
                else:
                    html = f"""
                    <div style="background:#F5F5F5;
                        color:#B71C1C;border:2px dashed #D32F2F;
                        border-radius:10px;padding:10px;text-align:center;">
                        <div>{day.day}</div>
                        <div>NON COUVERT</div>
                    </div>
                    """

                cols[i].markdown(html, unsafe_allow_html=True)

        excel = export_excel(result["blocks"], users)
        st.download_button(
            "📊 Export Excel",
            excel,
            file_name=f"planning_{year_admin}_{month_admin}.xlsx",
        )

        if st.button("🔒 Valider et verrouiller le planning"):
            lock_planning(year_admin, month_admin, planning_data=result["blocks"])
            st.success("Planning verrouillé 🔒")


# ============================================================
# TAB 3 — RÈGLES RH
# ============================================================
with tab3:
    st.header("📜 Règles RH")
    st.markdown("""
- 1 jour travaillé = **10 heures**
- Une personne **ne peut pas faire deux blocs consécutifs**
- Les disponibilités sont **strictes**
- Le forçage admin est **prioritaire**
- Chaque collaborateur doit apparaître **au moins une fois**
""")


# ============================================================
# TAB 4 — HEURES
# ============================================================
with tab4:
    st.header("⏱️ Heures mensuelles")

    if not st.session_state.generated_planning:
        st.info("Générez un planning pour afficher les heures.")
        st.stop()

    result = st.session_state.generated_planning
    stats = compute_hours(result["blocks"])

    st.markdown("**Règle : 1 jour travaillé = 10 heures**")
    st.divider()

    total = 0
    for u, data in stats.items():
        total += data["hours"]
        with st.container(border=True):
            st.markdown(f"### {users[u]['name']}")
            st.write(f"📅 Jours travaillés : {data['days']}")
            st.write(f"⏱️ Heures : **{data['hours']} h**")

    st.divider()
    st.markdown(f"### ⏱️ Total équipe : **{total} heures**")