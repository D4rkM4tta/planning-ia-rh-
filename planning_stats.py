import streamlit as st
import datetime as dt
import pandas as pd

# Amplitude 9h → 19h, 1h de repas non comptabilisée
HOURS_PER_DAY = 9


def render_contract_vs_realized_chart(*, users, blocks, year, month):
    """
    Tableau Contrat mensuel VS Heures réalisées, avec écart et
    taux de réalisation. Plus lisible qu'un histogramme pour
    comparer deux valeurs par collaborateur.
    """

    # Heures réalisées sur le mois
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
        contract = int(info.get("monthly_hours") or 0)
        done = realized.get(u, 0)
        gap = done - contract
        # Pourcentage (et non ratio) : ProgressColumn formate la
        # valeur telle quelle, sans la multiplier par 100.
        pct = (done / contract * 100) if contract else 0.0

        rows.append({
            "Collaborateur": info.get("name", u),
            "Contrat": contract,
            "Réalisé": done,
            "Écart": gap,
            "Taux": round(min(pct, 150.0), 1),
        })

    if not rows:
        st.info("Aucun collaborateur à afficher.")
        return

    df = pd.DataFrame(rows).sort_values("Écart")

    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Collaborateur": st.column_config.TextColumn(width="medium"),
            "Contrat": st.column_config.NumberColumn(
                "📄 Contrat",
                format="%d h",
                help="Contrat horaire mensuel",
            ),
            "Réalisé": st.column_config.NumberColumn(
                "⏱️ Réalisé",
                format="%d h",
                help="Heures planifiées sur le mois (9 h par jour)",
            ),
            "Écart": st.column_config.NumberColumn(
                "± Écart",
                format="%+d h",
                help="Réalisé moins contrat",
            ),
            "Taux": st.column_config.ProgressColumn(
                "Taux de réalisation",
                min_value=0,
                max_value=150,
                format="%.0f%%",
                help="Réalisé rapporté au contrat (plafonné à 150 %)",
            ),
        },
    )

    total_contract = int(df["Contrat"].sum())
    total_done = int(df["Réalisé"].sum())
    total_gap = total_done - total_contract

    c1, c2, c3 = st.columns(3)
    c1.metric("Contrat total", f"{total_contract} h")
    c2.metric("Réalisé total", f"{total_done} h")
    c3.metric(
        "Écart global",
        f"{total_gap:+d} h",
        delta=f"{total_gap:+d} h",
        delta_color="inverse",
    )