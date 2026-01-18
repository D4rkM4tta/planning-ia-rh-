import streamlit as st
import calendar
import datetime as dt

# ✅ AJOUT CRITIQUE
from firebase_client import save_forced_assignment, load_forced_assignments


def availability_calendar(
    *,
    email: str,
    year: int,
    month: int,
    load_fn,
    save_fn,
    is_admin: bool,
    users: dict,
    forced_assignments: dict,
):
    """
    Calendrier de saisie des disponibilités.
    - Utilisateur : saisie simple
    - Admin : saisie + forçage + annulation forçage
    """

    # ==================================================
    # 🔒 SYNC FORÇAGES DEPUIS FIRESTORE (CRITIQUE)
    # ==================================================
    forced_assignments.update(load_forced_assignments(year, month))

    session_key = f"availability_{email}_{year}_{month}"

    if session_key not in st.session_state:
        st.session_state[session_key] = load_fn(email, year, month)

    availability = st.session_state[session_key]

    st.subheader(f"📆 {calendar.month_name[month]} {year}")

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    # --------------------------------------------------
    # EN-TÊTES
    # --------------------------------------------------
    headers = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    cols = st.columns(7)
    for i, h in enumerate(headers):
        cols[i].markdown(f"**{h}**")

    # --------------------------------------------------
    # CALENDRIER
    # --------------------------------------------------
    for week in weeks:
        cols = st.columns(7)

        for i, day in enumerate(week):
            if day.month != month:
                cols[i].markdown(
                    f"<div style='opacity:0.3;text-align:center'>{day.day}</div>",
                    unsafe_allow_html=True,
                )
                continue

            day_key = day.isoformat()
            forced_user = forced_assignments.get(day_key)

            # ==============================================
            # 🔒 JOUR FORCÉ (VISIBLE PAR TOUS)
            # ==============================================
            if forced_user:
                name = users.get(forced_user, {}).get(
                    "name", forced_user.split("@")[0]
                )

                cols[i].markdown(
                    f"""
                    <div style="
                        background:#263238;
                        color:white;
                        border-radius:8px;
                        padding:6px;
                        text-align:center;
                        font-size:12px;
                    ">
                        <strong>{day.day}</strong><br>
                        {name}<br>
                        🔒 Forcé
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                continue

            # ==============================================
            # DISPONIBILITÉ CLASSIQUE
            # ==============================================
            btn_key = f"{email}-{year}-{month}-{day_key}"

            if cols[i].button(str(day.day), key=btn_key):
                current = availability.get(day_key)

                if current is None:
                    availability[day_key] = True
                elif current is True:
                    availability[day_key] = False
                else:
                    availability.pop(day_key, None)

                save_fn(email, year, month, availability)

            state = availability.get(day_key)
            color = "#B0BEC5"
            if state is True:
                color = "#43A047"
            elif state is False:
                color = "#E53935"

            cols[i].markdown(
                f"""
                <div style="
                    height:14px;
                    margin-top:-24px;
                    background:{color};
                    border-radius:6px;
                "></div>
                """,
                unsafe_allow_html=True,
            )

    # --------------------------------------------------
    # 🧷 FORÇAGE ADMIN (PERSISTANT)
    # --------------------------------------------------
    if is_admin:
        st.divider()
        st.subheader("🧷 Forcer / Annuler un jour (admin)")

        c1, c2, c3 = st.columns([2, 3, 2])

        forced_day = c1.date_input(
            "Jour",
            value=dt.date(year, month, 1),
            min_value=dt.date(year, month, 1),
            max_value=dt.date(year, month, calendar.monthrange(year, month)[1]),
            key=f"force-day-{year}-{month}",
        )

        user_labels = {
            info.get("name", mail.split("@")[0]): mail
            for mail, info in users.items()
        }

        forced_label = c2.selectbox(
            "Collaborateur",
            options=list(user_labels.keys()),
            key=f"force-user-{year}-{month}",
        )

        day_key = forced_day.isoformat()

        # ➕ FORCER (🔥 PERSISTÉ)
        if c3.button("🔒 Forcer", key=f"force-btn-{day_key}"):
            forced_assignments[day_key] = user_labels[forced_label]
            save_forced_assignment(year, month, day_key, user_labels[forced_label])
            st.success(
                f"{forced_day.strftime('%d/%m')} forcé pour {forced_label}"
            )

        # ➖ ANNULER (🔥 PERSISTÉ)
        if day_key in forced_assignments:
            if st.button(
                "🗑 Annuler le forçage",
                key=f"unforce-{day_key}",
            ):
                forced_assignments.pop(day_key, None)
                save_forced_assignment(year, month, day_key, None)
                st.success(
                    f"Forçage annulé pour le {forced_day.strftime('%d/%m')}"
                )