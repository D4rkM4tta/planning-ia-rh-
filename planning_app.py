import streamlit as st
import pandas as pd

from firebase_client import (
    login_user, logout_user, is_admin,
    load_availability, save_availability,
    get_all_users,
    is_planning_locked,
    lock_planning,
    load_locked_planning
)

from components.calendar_availability import availability_calendar
from planner_engine import generate_planning

st.set_page_config(page_title="Planning IA RH", layout="wide")

# ================= SESSION =================
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None


# ================= LOGIN =================
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


# ================= CONNECTÉ =================
email = st.session_state.auth_user["email"]
admin = is_admin()

st.success(f"Connecté : **{email}** — {'Admin' if admin else 'Utilisateur'}")

if st.button("Se déconnecter"):
    logout_user()
    st.rerun()


tab1, tab2 = st.tabs(["📌 Mes disponibilités", "📋 Admin"])


# ================= TAB 1 : UTILISATEUR =================
with tab1:
    year = st.selectbox("Année", [2026, 2027], index=0, key="user_year")
    month = st.selectbox("Mois", list(range(1, 13)), index=2, key="user_month")

    locked = is_planning_locked(year, month)

    if locked:
        st.info("🔒 Le planning de ce mois est verrouillé. Les disponibilités ne peuvent plus être modifiées.")
    else:
        availability_calendar(
            email=email,
            year=year,
            month=month,
            load_fn=load_availability,
            save_fn=save_availability
        )


# ================= TAB 2 : ADMIN =================
with tab2:
    if not admin:
        st.warning("Accès réservé à l’administrateur")
        st.stop()

    st.header("👥 Disponibilités équipe")

    year_admin = st.selectbox("Année (Admin)", [2026, 2027], index=0, key="admin_year")
    month_admin = st.selectbox("Mois (Admin)", list(range(1, 13)), index=2, key="admin_month")

    users = get_all_users()

    if not users:
        st.info("Aucun utilisateur enregistré")
        st.stop()

    # ===== COLLECTE DES DONNÉES =====
    availability_by_user = {}
    contract_hours = {}
    table_data = []

    for u_email, info in users.items():
        avail = load_availability(u_email, year_admin, month_admin)
        dispo_days = [d for d, v in avail.items() if v is True]

        availability_by_user[u_email] = avail
        contract_hours[u_email] = info.get("contract_hours", 0)

        table_data.append({
            "Nom": info.get("name", u_email.split("@")[0]),
            "Email": u_email,
            "Jours disponibles": len(dispo_days)
        })

    st.subheader("📊 Synthèse des disponibilités")
    st.dataframe(pd.DataFrame(table_data), use_container_width=True)

    # ===== VÉRIFICATION GLOBALE =====
    total_dispos = sum(
        sum(1 for v in avail.values() if v is True)
        for avail in availability_by_user.values()
    )

    if total_dispos == 0:
        st.warning(
            "⚠️ Aucune disponibilité renseignée pour ce mois.\n\n"
            "Le planning ne peut pas être généré."
        )
        st.stop()

    st.divider()
    st.subheader("🧠 Génération du planning")

    # ===== GÉNÉRATION =====
    if st.button("🚀 Générer le planning (aperçu)"):
        result = generate_planning(
            year=year_admin,
            month=month_admin,
            users=users,
            availability_by_user=availability_by_user,
            contract_hours=contract_hours
        )

        st.session_state.generated_planning = result
        st.success("Planning généré (aperçu)")

    # ===== AFFICHAGE =====
    if "generated_planning" in st.session_state:
        result = st.session_state.generated_planning

        st.divider()
        st.subheader("📅 Aperçu du planning")

        blocks_data = []
        hours_by_user = {}

        for b in result["blocks"]:
            user_assigned = b["assigned_to"]

            if user_assigned:
                hours_by_user[user_assigned] = (
                    hours_by_user.get(user_assigned, 0) + b["hours"]
                )

            blocks_data.append({
                "Semaine": b["week"],
                "Bloc": "Lundi → Jeudi" if b["type"] == "week" else "Vendredi → Dimanche",
                "Du": b["start"].strftime("%d/%m"),
                "Au": b["end"].strftime("%d/%m"),
                "Affecté à": (
                    users[user_assigned]["name"]
                    if user_assigned else "❌ NON COUVERT"
                ),
                "Heures": b["hours"],
                "Statut": b["status"]
            })

        st.dataframe(pd.DataFrame(blocks_data), use_container_width=True)

        # ===== HEURES =====
        st.subheader("⏱ Heures par collaborateur")
        for u, h in hours_by_user.items():
            st.write(f"• {users[u]['name']} : **{h} h**")

        # ===== ALERTES RH =====
        if result["warnings"]:
            st.subheader("⚠️ Alertes RH")
            for w in result["warnings"]:
                st.write("•", w)
        else:
            st.success("✅ Tous les blocs sont couverts")

        st.divider()
        st.subheader("🔒 Validation définitive")

        if st.button("🔒 Valider et verrouiller le planning"):
            lock_planning(
                year_admin,
                month_admin,
                planning_data=result["blocks"],
                hours_by_user=hours_by_user
            )

            st.success(
                f"🔒 Planning {month_admin:02d}/{year_admin} VALIDÉ\n"
                "Les disponibilités sont désormais verrouillées."
            )