import streamlit as st
import datetime as dt
import pandas as pd


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
                realized[user] = realized.get(user, 0) + 10

    rows = []
    for u, info in users.items():
        rows.append({
            "Collaborateur": info["name"],
            "Contrat (h)": info.get("monthly_hours", 140),
            "Réalisé (h)": realized.get(u, 0),
        })

    df = pd.DataFrame(rows)

    st.bar_chart(
        df.set_index("Collaborateur")[["Contrat (h)", "Réalisé (h)"]],
        height=320,
    )