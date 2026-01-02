import streamlit as st
import calendar
from typing import Dict


def availability_calendar(email: str, year: int, month: int, save_fn, load_fn):

    st.subheader(f"📆 {calendar.month_name[month]} {year}")

    session_key = f"availability_{email}_{year}_{month}"

    if session_key not in st.session_state:
        st.session_state[session_key] = load_fn(email, year, month)

    availability: Dict[str, bool] = st.session_state[session_key]

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    for week in weeks:
        cols = st.columns(7)
        for i, day in enumerate(week):

            if day.month != month:
                cols[i].markdown(
                    f"<div style='opacity:0.3;text-align:center'>{day.day}</div>",
                    unsafe_allow_html=True,
                )
                continue

            d_key = day.isoformat()

            # 🖱️ CLIC
            if cols[i].button(f"{day.day}", key=f"{email}-{d_key}"):

                current = availability.get(d_key)

                if current is None:
                    availability[d_key] = True
                elif current is True:
                    availability[d_key] = False
                else:
                    availability.pop(d_key)

                save_fn(email, year, month, availability)

            # ✅ LECTURE APRÈS MODIFICATION
            state = availability.get(d_key)

            if state is True:
                color = "#00C853"   # vert
            elif state is False:
                color = "#D50000"   # rouge
            else:
                color = "#9E9E9E"   # gris

            cols[i].markdown(
                f"""
                <div style="
                    height:18px;
                    margin-top:-28px;
                    background:{color};
                    border-radius:6px;
                "></div>
                """,
                unsafe_allow_html=True,
            )