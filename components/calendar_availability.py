import calendar
import datetime as dt

import streamlit as st

from theme import esc, abbrev, TEXT, TEXT_SOFT, TEXT_MUTED, NEUTRAL_BG, NEUTRAL_FG

HOURS_PER_DAY = 9

# Vert = disponible, rouge = indisponible
AV_BG = "#9FE1CB"
AV_FG = "#04342C"
UN_BG = "#F3A3A3"
UN_FG = "#3D0F0F"

DOW = [
    ("Lun", "L"), ("Mar", "M"), ("Mer", "M"), ("Jeu", "J"),
    ("Ven", "V"), ("Sam", "S"), ("Dim", "D"),
]


def month_weeks(year: int, month: int):
    return calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)


def dow_row() -> str:
    return (
        '<div class="av-dow">'
        + "".join(
            f'<div>{full}<span class="av-dow-s">{sh}</span></div>'
            for full, sh in DOW
        )
        + "</div>"
    )


def inject_availability_css() -> None:
    """Styles de la saisie des disponibilités. À appeler une fois par page."""
    st.markdown(
        f"""
<style>
.av-dow {{
  display: grid; grid-template-columns: repeat(7, 1fr);
  gap: 5px; margin-bottom: 4px;
}}
.av-dow div {{
  font-size: 11px; color: {TEXT_MUTED};
  text-align: center; letter-spacing: .03em;
}}
.av-dow-s {{display: none;}}

.av-grid {{display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px;}}
.av-cell {{
  border-radius: 8px; min-height: 46px; padding: 13px 2px;
  text-align: center; font-size: 15px; font-weight: 500;
}}
.av-locked {{
  background: {NEUTRAL_BG}; border-radius: 8px;
  padding: 7px 2px; text-align: center; min-height: 46px;
}}
.av-locked-n {{font-size: 14px; color: {NEUTRAL_FG};}}
.av-locked-u {{font-size: 10px; color: {TEXT_SOFT}; margin-top: 1px;}}
.av-off {{
  text-align: center; padding: 13px 2px;
  font-size: 13px; color: #40444B; min-height: 46px;
}}

/* Boutons de la grille en mode saisie */
div[class*="st-key-avd-"] button {{
  width: 100%; min-height: 46px; padding: 0;
  border: none !important; border-radius: 8px;
  font-size: 15px; font-weight: 500;
  transition: filter .12s ease;
}}
div[class*="st-key-avd-"] button:hover {{filter: brightness(1.07);}}
div[class*="st-key-avd-"] {{margin-bottom: 5px;}}

.av-sum {{
  display: flex; gap: 22px; flex-wrap: wrap;
  padding: 11px 0 3px; margin-top: 6px;
  border-top: 1px solid {NEUTRAL_BG};
}}
.av-sum-l {{font-size: 11px; color: {TEXT_MUTED};}}
.av-sum-v {{font-size: 17px; color: {TEXT}; margin-top: 1px;}}
.av-key {{
  display: flex; gap: 14px; flex-wrap: wrap;
  font-size: 11px; color: {TEXT_SOFT}; margin: 4px 0 10px;
}}
.av-key span span {{
  display: inline-block; width: 9px; height: 9px;
  border-radius: 3px; margin-right: 5px;
}}

@media (max-width: 640px) {{
  .av-dow {{gap: 3px;}}
  .av-dow div {{font-size: 0;}}
  .av-dow-s {{display: inline; font-size: 9px;}}
  .av-grid {{gap: 3px;}}
  .av-cell {{min-height: 38px; padding: 10px 1px;
             font-size: 13px; border-radius: 6px;}}
  .av-locked {{padding: 5px 1px; min-height: 38px; border-radius: 6px;}}
  .av-locked-n {{font-size: 12px;}}
  .av-locked-u {{font-size: 9px;}}
  .av-off {{min-height: 38px; font-size: 11px; padding: 10px 1px;}}
  .av-sum {{gap: 16px;}}
  .av-sum-v {{font-size: 14px;}}

  /* Streamlit empile les colonnes sur mobile : on l'en empêche
     dans la grille de saisie, sinon la semaine devient une liste
     de sept lignes et le calendrier disparaît. */
  div[class*="st-key-avgrid-"] div[data-testid="stHorizontalBlock"] {{
    flex-wrap: nowrap !important; gap: 3px !important;
  }}
  div[class*="st-key-avgrid-"] div[data-testid="stColumn"] {{
    min-width: 0 !important; flex: 1 1 0 !important; width: auto !important;
  }}
  div[class*="st-key-avd-"] button {{
    min-height: 38px; font-size: 13px;
  }}
  div[class*="st-key-avd-"] {{margin-bottom: 3px;}}
}}
</style>
""",
        unsafe_allow_html=True,
    )


def availability_legend() -> str:
    return (
        f'<div class="av-key">'
        f'<span><span style="background:{AV_BG}"></span>Disponible</span>'
        f'<span><span style="background:{UN_BG}"></span>Indisponible</span>'
        f'<span><span style="background:{NEUTRAL_BG}"></span>Forcé</span>'
        f'</div>'
    )


def _forced_cell(day, users, forced_user) -> str:
    name = users.get(forced_user, {}).get(
        "name", forced_user.split("@")[0]
    ).split(" ")[0]
    return (
        f'<div class="av-locked">'
        f'<div class="av-locked-n">{day.day}</div>'
        f'<div class="av-locked-u">{esc(abbrev(name))}</div></div>'
    )


def _summary(selected, forced) -> str:
    weekend_days = sum(
        1 for d in selected if dt.date.fromisoformat(d).weekday() >= 5
    )
    return (
        f'<div class="av-sum">'
        f'<div><div class="av-sum-l">Jours disponibles</div>'
        f'<div class="av-sum-v">{len(selected)}</div></div>'
        f'<div><div class="av-sum-l">Dont week-ends</div>'
        f'<div class="av-sum-v">{weekend_days}</div></div>'
        f'<div><div class="av-sum-l">Potentiel</div>'
        f'<div class="av-sum-v">{len(selected) * HOURS_PER_DAY} h</div></div>'
        f'<div><div class="av-sum-l">Jours forcés</div>'
        f'<div class="av-sum-v">{len(forced)}</div></div>'
        f'</div>'
    )


def render_availability_static(*, year, month, selected, forced, users):
    """
    Grille de disponibilités en lecture seule, en une seule
    injection HTML : rapide même avec une vingtaine de mois.
    """
    parts = [dow_row(), '<div class="av-grid">']

    for week in month_weeks(year, month):
        for day in week:
            if day.year != year or day.month != month:
                parts.append(f'<div class="av-off">{day.day}</div>')
                continue

            day_iso = day.isoformat()
            forced_user = forced.get(day_iso)

            if forced_user:
                parts.append(_forced_cell(day, users, forced_user))
                continue

            available = day_iso in selected
            bg, fg = (AV_BG, AV_FG) if available else (UN_BG, UN_FG)
            parts.append(
                f'<div class="av-cell" style="background:{bg};color:{fg}">'
                f'{day.day}</div>'
            )

    parts.append("</div>")
    parts.append(_summary(selected, forced))

    st.markdown("".join(parts), unsafe_allow_html=True)


def _day_key(year: int, month: int, day: int) -> str:
    return f"avd-{year}-{month:02d}-{day:02d}"


def render_availability_editor(*, email, year, month, forced, users,
                               save_fn, stored_days):
    """
    Grille cliquable. Un clic bascule l'état et recolore, mais
    n'écrit rien : la sauvegarde est une seule opération finale.
    """
    weeks = month_weeks(year, month)
    state_key = f"avstate::{email}::{year}::{month}"

    if state_key not in st.session_state:
        st.session_state[state_key] = set(stored_days)

    selected = st.session_state[state_key]
    dirty = selected != set(stored_days)

    # Couleurs des boutons, jour par jour
    rules = []
    for week in weeks:
        for day in week:
            if day.year != year or day.month != month:
                continue
            if day.isoformat() in forced:
                continue
            cls = _day_key(year, month, day.day)
            bg, fg = ((AV_BG, AV_FG) if day.isoformat() in selected
                      else (UN_BG, UN_FG))
            rules.append(
                f'.st-key-{cls} button {{background:{bg} !important;'
                f'color:{fg} !important;}}'
            )
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)

    def days_of(predicate):
        out = set()
        for week in weeks:
            for day in week:
                if day.year != year or day.month != month:
                    continue
                if day.isoformat() in forced:
                    continue
                if predicate(day):
                    out.add(day.isoformat())
        return out

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Tout", key=f"avq-all-{year}-{month}",
                 use_container_width=True):
        st.session_state[state_key] = days_of(lambda d: True)
        st.rerun()
    if b2.button("Sem.", key=f"avq-week-{year}-{month}",
                 use_container_width=True, help="Lundi à jeudi"):
        st.session_state[state_key] = days_of(lambda d: d.weekday() <= 3)
        st.rerun()
    if b3.button("W-E", key=f"avq-we-{year}-{month}",
                 use_container_width=True, help="Vendredi à dimanche"):
        st.session_state[state_key] = days_of(lambda d: d.weekday() >= 4)
        st.rerun()
    if b4.button("Aucun", key=f"avq-none-{year}-{month}",
                 use_container_width=True):
        st.session_state[state_key] = set()
        st.rerun()

    st.markdown(dow_row(), unsafe_allow_html=True)

    # Conteneur identifié : sert d'ancre au CSS qui empêche les
    # colonnes de s'empiler sur mobile.
    with st.container(key=f"avgrid-{year}-{month}"):
        for week in weeks:
            cols = st.columns(7, gap="small")
            for i, day in enumerate(week):
                if day.year != year or day.month != month:
                    cols[i].markdown(
                        f'<div class="av-off">{day.day}</div>',
                        unsafe_allow_html=True,
                    )
                    continue

                day_iso = day.isoformat()
                forced_user = forced.get(day_iso)

                if forced_user:
                    cols[i].markdown(
                        _forced_cell(day, users, forced_user),
                        unsafe_allow_html=True,
                    )
                    continue

                if cols[i].button(str(day.day),
                                  key=_day_key(year, month, day.day),
                                  use_container_width=True):
                    if day_iso in selected:
                        selected.discard(day_iso)
                    else:
                        selected.add(day_iso)
                    st.rerun()

    st.markdown(_summary(selected, forced), unsafe_allow_html=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    if c1.button("Enregistrer", key=f"avs-{year}-{month}",
                 type="primary", disabled=not dirty,
                 use_container_width=True):
        save_fn(email, year, month, {d: True for d in selected})
        del st.session_state[state_key]
        st.session_state["av_edit"] = None
        st.rerun()

    if c2.button("Annuler", key=f"avc-{year}-{month}",
                 use_container_width=True):
        del st.session_state[state_key]
        st.session_state["av_edit"] = None
        st.rerun()

    if dirty:
        st.caption("Modifications non enregistrées.")