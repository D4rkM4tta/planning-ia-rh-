import streamlit as st
import calendar
import datetime as dt


def admin_calendar(year: int, month: int, schedule: dict):
    st.subheader(f"📅 Planning — {calendar.month_name[month]} {year}")

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    for week in weeks:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day.month != month:
                cols[i].markdown(
                    f"<div style='opacity:0.3;text-align:center'>{day.day}</div>",
                    unsafe_allow_html=True
                )
                continue

            day_str = day.isoformat()
            assigned = schedule.get(day_str, "NON COUVERT")

            if assigned == "NON COUVERT":
                color = "#D32F2F"  # rouge
            else:
                color = "#1976D2"  # bleu

            cols[i].markdown(
                f"""
                <div style="
                    border-radius:8px;
                    padding:6px;
                    background:{color};
                    color:white;
                    text-align:center;
                    font-size:14px;
                ">
                    <strong>{day.day}</strong><br>
                    {assigned}
                </div>
                """,
                unsafe_allow_html=True
            )