import streamlit as st
import datetime as dt
import pandas as pd

from firebase_client import (
    save_monthly_hours,
    save_cumul_adjustment,
    reset_monthly_hours,
)
from theme import esc, rate_color, gap_color, TEXT_SOFT, TEXT, TEXT_MUTED

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


def _build_rows(users, blocks, year, month, weekends_stats, holidays_stats,
                weekends_year, holidays_year, cumul_locked, cumul_preview,
                admin, current_email):
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
            "WE mois": int(weekends_stats.get(email, 0)),
            "WE année": int(weekends_year.get(email, 0)),
            "Fériés mois": int(holidays_stats.get(email, 0)),
            "Fériés année": int(holidays_year.get(email, 0)),
            "Cumul année": int(cumul_locked.get(email, 0)) + adjustment,
            "Aperçu": int(cumul_preview.get(email, 0)) + adjustment,
            "Corr. cumul": adjustment,
        })

    return rows


def _render_cards(df, year, month_name, ref_month_name, locked_count):
    total_contract = int(df["Contrat"].sum())
    total_retained = int(df["Heures mois"].sum())
    total_gap = total_retained - total_contract
    total_cumul = int(df["Cumul année"].sum())
    total_we = int(df["WE année"].sum())
    total_hol = int(df["Fériés année"].sum())

    gap_col = gap_color(total_gap)
    sub = (f"arrêté à {ref_month_name.lower()}" if ref_month_name
           else "aucun mois verrouillé")

    st.markdown(
        f'<div class="pl-cards">'
        f'<div class="pl-card"><div class="pl-card-l">Cumul validé {year}</div>'
        f'<div class="pl-card-v">{total_cumul} h</div>'
        f'<div class="pl-card-s">{sub} · {locked_count} mois</div></div>'
        f'<div class="pl-card"><div class="pl-card-l">'
        f'Contrat {month_name.lower()}</div>'
        f'<div class="pl-card-v">{total_contract} h</div>'
        f'<div class="pl-card-s">{len(df)} collaborateur(s)</div></div>'
        f'<div class="pl-card"><div class="pl-card-l">'
        f'Écart {month_name.lower()}</div>'
        f'<div class="pl-card-v" style="color:{gap_col}">{total_gap:+d} h</div>'
        f'<div class="pl-card-s">{total_retained} h retenues</div></div>'
        f'<div class="pl-card"><div class="pl-card-l">Week-ends {year}</div>'
        f'<div class="pl-card-v">{total_we}</div>'
        f'<div class="pl-card-s">jours travaillés</div></div>'
        f'<div class="pl-card"><div class="pl-card-l">Fériés {year}</div>'
        f'<div class="pl-card-v">{total_hol}</div>'
        f'<div class="pl-card-s">jours travaillés</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_readonly(df, theme, year, month_name):
    """
    Vue lecture seule pour les non-admins.
    Tableau sur grand écran, cartes empilées sur mobile :
    les deux sont émis, le CSS n'en montre qu'un.
    """
    head = (
        f'<div class="pl-tr pl-th">'
        f'<div>Collaborateur</div>'
        f'<div style="text-align:right">Contrat</div>'
        f'<div style="text-align:right">Retenu</div>'
        f'<div style="text-align:right">Écart</div>'
        f'<div style="text-align:right">WE<br>'
        f'<span style="font-size:9px">mois · an</span></div>'
        f'<div style="text-align:right">Fériés<br>'
        f'<span style="font-size:9px">mois · an</span></div>'
        f'<div style="text-align:right">Cumul {year}</div>'
        f'<div>Taux</div></div>'
    )

    rows_html = []
    cards_html = []

    for _, r in df.iterrows():
        dot = theme.get(r["_email"], {}).get("dot", "#888780")
        gap = int(r["Écart"])
        gap_col = gap_color(gap)
        pct = float(r["Taux"])
        bar = rate_color(pct)
        width = min(pct, 100)
        flag = (' <span style="font-size:10px;color:#EF9F27">ajusté</span>'
                if r["_ajuste"] else "")

        rows_html.append(
            f'<div class="pl-tr">'
            f'<div><span class="pl-dot" style="background:{dot}"></span>'
            f'{esc(r["Collaborateur"])}{flag}</div>'
            f'<div style="text-align:right;color:{TEXT_SOFT}">'
            f'{int(r["Contrat"])} h</div>'
            f'<div style="text-align:right">{int(r["Heures mois"])} h</div>'
            f'<div style="text-align:right;color:{gap_col}">{gap:+d} h</div>'
            f'<div style="text-align:right">{int(r["WE mois"])} · '
            f'<span style="color:{TEXT_SOFT}">{int(r["WE année"])}</span></div>'
            f'<div style="text-align:right">{int(r["Fériés mois"])} · '
            f'<span style="color:{TEXT_SOFT}">{int(r["Fériés année"])}</span></div>'
            f'<div style="text-align:right">{int(r["Cumul année"])} h</div>'
            f'<div style="display:flex;align-items:center;gap:9px">'
            f'<span class="pl-bar"><span style="width:{width}%;'
            f'background:{bar}"></span></span>'
            f'<span style="font-size:11px;color:{TEXT_SOFT};min-width:34px;'
            f'text-align:right">{pct:.0f} %</span></div>'
            f'</div>'
        )

        cards_html.append(
            f'<div class="pl-ucard">'
            f'<div class="pl-ucard-top">'
            f'<div style="display:flex;align-items:center;gap:7px">'
            f'<span class="pl-dot" style="background:{dot};margin:0"></span>'
            f'<span style="font-size:13px;color:{TEXT}">'
            f'{esc(r["Collaborateur"])}</span>{flag}</div>'
            f'<span style="font-size:11px;color:{gap_col}">{gap:+d} h</span>'
            f'</div>'
            f'<div style="display:flex;align-items:center;gap:9px;'
            f'margin-bottom:6px">'
            f'<span class="pl-bar"><span style="width:{width}%;'
            f'background:{bar}"></span></span>'
            f'<span style="font-size:10px;color:{TEXT_SOFT}">'
            f'{pct:.0f} %</span></div>'
            f'<div class="pl-ucard-meta">'
            f'<span>{month_name} : {int(r["Heures mois"])} h '
            f'/ {int(r["Contrat"])} h</span>'
            f'<span>Cumul {year} : {int(r["Cumul année"])} h</span></div>'
            f'<div class="pl-ucard-meta">'
            f'<span>WE {int(r["WE mois"])} mois · '
            f'{int(r["WE année"])} an</span>'
            f'<span>Fériés {int(r["Fériés mois"])} mois · '
            f'{int(r["Fériés année"])} an</span></div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="pl-tbl">{head}{"".join(rows_html)}</div>'
        f'<div class="pl-ucards">{"".join(cards_html)}</div>',
        unsafe_allow_html=True,
    )


def _render_editor(df, year, month, month_name):
    """Tableau éditable, pour l'admin."""
    st.caption(
        "Les colonnes « Heures retenues » et « Corr. cumul » sont "
        "modifiables directement. Les colonnes annuelles cumulent "
        "les mois verrouillés depuis janvier."
    )

    visible = [
        "Collaborateur", "Contrat", "Réalisé", "Heures mois", "Écart",
        "Taux", "WE mois", "WE année", "Fériés mois", "Fériés année",
        "Cumul année", "Aperçu", "Corr. cumul",
    ]

    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        column_order=visible,
        column_config={
            "Collaborateur": st.column_config.TextColumn(width="medium"),
            "Contrat": st.column_config.NumberColumn("Contrat", format="%d h"),
            "Réalisé": st.column_config.NumberColumn(
                "Réalisé", format="%d h",
                help=f"Calcul automatique issu du planning de {month_name}",
            ),
            "Heures mois": st.column_config.NumberColumn(
                "Heures retenues", format="%d h",
                min_value=0, max_value=400, step=1,
            ),
            "Écart": st.column_config.NumberColumn("Écart", format="%+d h"),
            "Taux": st.column_config.ProgressColumn(
                "Taux", min_value=0, max_value=150, format="%.0f%%",
            ),
            "WE mois": st.column_config.NumberColumn(
                "WE mois", format="%d",
                help=f"Samedis et dimanches travaillés en {month_name}",
            ),
            "WE année": st.column_config.NumberColumn(
                f"WE {year}", format="%d",
                help="Cumul sur les mois verrouillés depuis janvier",
            ),
            "Fériés mois": st.column_config.NumberColumn(
                "Fériés mois", format="%d",
                help=f"Jours fériés travaillés en {month_name}",
            ),
            "Fériés année": st.column_config.NumberColumn(
                f"Fériés {year}", format="%d",
                help="Cumul sur les mois verrouillés depuis janvier",
            ),
            "Cumul année": st.column_config.NumberColumn(
                f"Cumul {year}", format="%d h",
            ),
            "Aperçu": st.column_config.NumberColumn("Aperçu", format="%d h"),
            "Corr. cumul": st.column_config.NumberColumn(
                "Corr. cumul", format="%+d h",
                min_value=-2000, max_value=2000, step=1,
                help="Ajout ou retrait appliqué au cumul annuel.",
            ),
        },
        disabled=[
            "Collaborateur", "Contrat", "Réalisé", "Écart", "Taux",
            "WE mois", "WE année", "Fériés mois", "Fériés année",
            "Cumul année", "Aperçu",
        ],
        key=f"hours_editor_{year}_{month}",
    )

    if st.button("Enregistrer", key=f"save_hours_{year}_{month}",
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
            st.info("Aucune modification à enregistrer.")

    adjusted = df[df["_ajuste"]]
    if not adjusted.empty:
        with st.expander(
            f"Heures ajustées manuellement en {month_name} "
            f"({len(adjusted)})"
        ):
            st.caption(
                "Réinitialiser rétablit le calcul automatique du planning."
            )
            for _, row in adjusted.iterrows():
                c1, c2 = st.columns([3, 1])
                c1.write(
                    f"**{row['Collaborateur']}** — {row['Heures mois']} h "
                    f"saisies (automatique : {row['Réalisé']} h)"
                )
                if c2.button("Réinitialiser",
                             key=f"reset_{row['_email']}_{year}_{month}"):
                    reset_monthly_hours(row["_email"], year, month)
                    st.rerun()


def render_hours_dashboard(
    *,
    users: dict,
    theme: dict,
    blocks,
    year: int,
    month: int,
    month_name: str,
    ref_month_name: str | None,
    locked_count: int,
    pending_months: list,
    weekends_stats: dict,
    holidays_stats: dict,
    weekends_year: dict,
    holidays_year: dict,
    cumul_locked: dict,
    cumul_preview: dict,
    admin: bool,
    current_email: str,
):
    """
    Synthèse des heures : cartes de totaux, puis détail.

    Chaque compteur existe en version mensuelle (le mois analysé)
    et annuelle (cumul des mois verrouillés depuis janvier), pour
    les heures comme pour les week-ends et les jours fériés.
    """
    rows = _build_rows(
        users, blocks, year, month, weekends_stats, holidays_stats,
        weekends_year, holidays_year, cumul_locked, cumul_preview,
        admin, current_email,
    )

    if not rows:
        st.info("Aucun collaborateur à afficher.")
        return

    df = pd.DataFrame(rows).sort_values("Écart").reset_index(drop=True)

    _render_cards(df, year, month_name, ref_month_name, locked_count)

    if pending_months:
        st.caption(
            "Aperçu incluant les mois générés non verrouillés : "
            + ", ".join(pending_months)
        )

    if admin:
        _render_editor(df, year, month, month_name)
    else:
        _render_readonly(df, theme, year, month_name)