import streamlit as st
import datetime as dt
import pandas as pd

from firebase_client import (
    save_monthly_hours,
    save_cumul_adjustment,
    reset_monthly_hours,
)

# Amplitude 9h → 19h, 1h de repas non comptabilisée
HOURS_PER_DAY = 9


def compute_realized(blocks, year: int, month: int) -> dict:
    """Heures réellement planifiées sur le mois, par collaborateur."""
    realized = {}
    for block in blocks:
        user = block.get("assigned_to")
        if not user:
            continue
        for day_iso in block["days"]:
            day = dt.date.fromisoformat(day_iso)
            if day.year == year and day.month == month:
                realized[user] = realized.get(user, 0) + HOURS_PER_DAY
    return realized


def render_hours_dashboard(
    *,
    users: dict,
    blocks,
    year: int,
    month: int,
    month_label: str,
    weekends_stats: dict,
    holidays_stats: dict,
    cumul_locked: dict,
    cumul_preview: dict,
    admin: bool,
    current_email: str,
):
    """
    Tableau unique regroupant, par collaborateur :
    contrat, réalisé du mois, écart, taux, week-ends, jours fériés,
    cumul annuel validé et aperçu.

    Pour l'admin, les colonnes « Heures mois » et « Corr. cumul »
    sont éditables directement dans le tableau, avec enregistrement
    groupé.
    """

    realized = compute_realized(blocks, year, month)

    rows = []
    for email, info in users.items():
        if not admin and email != current_email:
            continue

        contract = int(info.get("monthly_hours") or 0)
        done = int(realized.get(email, 0))

        override = info.get(f"hours_{year}_{month}")
        retained = int(override) if override is not None else done

        adjustment = int(info.get(f"cumul_adjustment_{year}") or 0)
        pct = (retained / contract * 100) if contract else 0.0

        rows.append({
            "_email": email,
            "_ajuste": override is not None,
            "Collaborateur": info.get("name", email),
            "Contrat": contract,
            "Réalisé": done,
            "Heures mois": retained,
            "Écart": retained - contract,
            "Taux": round(min(pct, 150.0), 1),
            "WE": int(weekends_stats.get(email, 0)),
            "Fériés": int(holidays_stats.get(email, 0)),
            "Cumul année": int(cumul_locked.get(email, 0)) + adjustment,
            "Aperçu": int(cumul_preview.get(email, 0)) + adjustment,
            "Corr. cumul": adjustment,
        })

    if not rows:
        st.info("Aucun collaborateur à afficher.")
        return

    df = pd.DataFrame(rows).sort_values("Écart").reset_index(drop=True)

    visible_columns = [
        "Collaborateur", "Contrat", "Réalisé", "Heures mois", "Écart",
        "Taux", "WE", "Fériés", "Cumul année", "Aperçu", "Corr. cumul",
    ]

    column_config = {
        "Collaborateur": st.column_config.TextColumn(width="medium"),
        "Contrat": st.column_config.NumberColumn(
            "📄 Contrat", format="%d h",
            help="Contrat horaire mensuel",
        ),
        "Réalisé": st.column_config.NumberColumn(
            "⏱️ Réalisé", format="%d h",
            help=f"Heures planifiées en {month_label} ({HOURS_PER_DAY} h par jour)",
        ),
        "Heures mois": st.column_config.NumberColumn(
            "✏️ Heures retenues", format="%d h", min_value=0, max_value=400, step=1,
            help="Heures comptabilisées pour le mois. Modifiable pour "
                 "corriger le calcul automatique.",
        ),
        "Écart": st.column_config.NumberColumn(
            "± Écart", format="%+d h",
            help="Heures retenues moins contrat",
        ),
        "Taux": st.column_config.ProgressColumn(
            "Taux", min_value=0, max_value=150, format="%.0f%%",
            help="Heures retenues rapportées au contrat (plafonné à 150 %)",
        ),
        "WE": st.column_config.NumberColumn(
            "🟪 WE", format="%d",
            help="Samedis et dimanches travaillés dans le mois",
        ),
        "Fériés": st.column_config.NumberColumn(
            "🟥 Fériés", format="%d",
            help="Jours fériés travaillés dans le mois",
        ),
        "Cumul année": st.column_config.NumberColumn(
            f"📊 Cumul {year}", format="%d h",
            help="Somme des mois verrouillés depuis janvier, correction incluse",
        ),
        "Aperçu": st.column_config.NumberColumn(
            "🔎 Aperçu", format="%d h",
            help="Cumul incluant les mois générés mais non verrouillés",
        ),
        "Corr. cumul": st.column_config.NumberColumn(
            "± Corr. cumul", format="%+d h", min_value=-2000, max_value=2000, step=1,
            help="Ajout ou retrait appliqué au cumul annuel. Sert à intégrer "
                 "un historique antérieur à l'application.",
        ),
    }

    # --------------------------------------------------------
    # LECTURE SEULE (non-admin)
    # --------------------------------------------------------
    if not admin:
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_order=visible_columns,
            column_config=column_config,
        )
        _render_totals(df)
        return

    # --------------------------------------------------------
    # ÉDITION (admin)
    # --------------------------------------------------------
    st.caption(
        "✏️ Les colonnes **Heures retenues** et **Corr. cumul** sont "
        "modifiables directement dans le tableau. Pensez à enregistrer."
    )

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        column_order=visible_columns,
        column_config=column_config,
        disabled=[
            "Collaborateur", "Contrat", "Réalisé", "Écart",
            "Taux", "WE", "Fériés", "Cumul année", "Aperçu",
        ],
        key=f"hours_editor_{year}_{month}",
    )

    col_save, col_info = st.columns([1, 3])

    if col_save.button("💾 Enregistrer", key=f"save_hours_{year}_{month}",
                       type="primary"):
        changes = 0

        for i in range(len(df)):
            email = df.at[i, "_email"]

            new_month = int(edited.at[i, "Heures mois"])
            if new_month != int(df.at[i, "Heures mois"]):
                save_monthly_hours(email, year, month, new_month)
                changes += 1

            new_adj = int(edited.at[i, "Corr. cumul"])
            if new_adj != int(df.at[i, "Corr. cumul"]):
                save_cumul_adjustment(email, year, new_adj)
                changes += 1

        if changes:
            st.success(f"{changes} modification(s) enregistrée(s).")
            st.rerun()
        else:
            col_info.info("Aucune modification à enregistrer.")

    _render_totals(df)

    # --------------------------------------------------------
    # RETOUR AU CALCUL AUTOMATIQUE
    # --------------------------------------------------------
    adjusted = df[df["_ajuste"]]

    if not adjusted.empty:
        with st.expander(
            f"↩︎ Heures ajustées manuellement en {month_label} "
            f"({len(adjusted)} collaborateur(s))"
        ):
            st.caption(
                "Ces collaborateurs ont des heures saisies à la main. "
                "Réinitialiser rétablit le calcul automatique issu du planning."
            )
            for _, row in adjusted.iterrows():
                c1, c2 = st.columns([3, 1])
                c1.write(
                    f"**{row['Collaborateur']}** — "
                    f"{row['Heures mois']} h saisies "
                    f"(calcul automatique : {row['Réalisé']} h)"
                )
                if c2.button(
                    "↩︎ Auto",
                    key=f"reset_{row['_email']}_{year}_{month}",
                ):
                    reset_monthly_hours(row["_email"], year, month)
                    st.rerun()


def _render_totals(df: pd.DataFrame) -> None:
    total_contract = int(df["Contrat"].sum())
    total_retained = int(df["Heures mois"].sum())
    total_gap = total_retained - total_contract

    c1, c2, c3 = st.columns(3)
    c1.metric("Contrat total", f"{total_contract} h")
    c2.metric("Heures retenues", f"{total_retained} h")
    c3.metric(
        "Écart global",
        f"{total_gap:+d} h",
        delta=f"{total_gap:+d} h",
        delta_color="inverse",
    )