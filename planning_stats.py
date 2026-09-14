import streamlit as st
import datetime as dt
import pandas as pd

# Aligné sur planner_engine.py et planning_app.py : 1 jour = 9 heures
HOURS_PER_DAY = 9


def render_contract_vs_realized_chart(*, users, blocks, year, month):
    """
    Graphique Contrat mensuel VS Heures réalisées
    """

    # Heures réalisées
    realized = {}

    for block in blocks:
        user = block["assigned_to"]
        if not user:
            continue

        for day_iso in block["days"]:
            day = dt.date.fromisoformat(day_iso)
            if day.year == year and day.month == month:
                realized[user] = realized.get(user, 0) + HOURS_PER_DAY

    rows = []
    for u, info in users.items():
        rows.append({
            "Collaborateur": info.get("name", u),
            "Contrat (h)": int(info.get("monthly_hours") or 0),
            "Réalisé (h)": realized.get(u, 0),
        })

    if not rows:
        st.info("Aucun collaborateur à afficher.")
        return

    df = pd.DataFrame(rows)

    st.bar_chart(
        df.set_index("Collaborateur")[["Contrat (h)", "Réalisé (h)"]],
        height=320,
    )