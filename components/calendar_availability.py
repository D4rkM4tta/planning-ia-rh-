import calendar
import datetime as dt

import streamlit as st

from firebase_client import save_forced_assignment, load_forced_assignments
from theme import (
    esc,
    abbrev,
    TEXT,
    TEXT_SOFT,
    TEXT_MUTED,
    NEUTRAL_BG,
    NEUTRAL_FG,
)

HOURS_PER_DAY = 9

# Vert = disponible, rouge = indisponible
AV_BG = "#9FE1CB"
AV_FG = "#04342C"
UN_BG = "#F3A3A3"
UN_FG = "#3D0F0F"

MONTH_LABELS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}

DOW = [
    ("Lun", "L"), ("Mar", "M"), ("Mer", "M"), ("Jeu", "J"),
    ("Ven", "V"), ("Sam", "S"), ("Dim", "D"),
]


def _day_key(year: int, month: int, day: int) -> str:
    """Clé de bouton, utilisable telle quelle comme classe CSS."""
    return f"avd-{year}-{month:02d}-{day:02d}"


def _inject_css(year: int, month: int, states: dict, weeks) -> None:
    """
    Styles de la grille. Chaque bouton est colorié individuellement
    via la classe .st-key-<clé> que Streamlit pose sur son conteneur.
    """
    rules = []
    for week in weeks:
        for day in week:
            if day.year != year or day.month != month:
                continue
            cls = _day_key(year, month, day.day)
            available = states.get(day.isoformat(), False)
            bg, fg = (AV_BG, AV_FG) if available else (UN_BG, UN_FG)
            rules.append(
                f'.st-key-{cls} button {{background:{bg} !important;'
                f'color:{fg} !important;}}'
            )

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

/* Cases du calendrier : le bouton occupe toute la cellule */
div[class*="st-key-avd-"] button {{
  width: 100%; min-height: 46px; padding: 0;
  border: none !important; border-radius: 8px;
  font-size: 15px; font-weight: 500;
  transition: filter .12s ease;
}}
div[class*="st-key-avd-"] button:hover {{filter: brightness(1.07);}}
div[class*="st-key-avd-"] {{margin-bottom: 5px;}}

{"".join(rules)}

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
.av-sum {{
  display: flex; gap: 22px; flex-wrap: wrap;
  padding: 12px 0 3px; margin-top: 6px;
  border-top: 1px solid {NEUTRAL_BG};
}}
.av-sum-l {{font-size: 11px; color: {TEXT_MUTED};}}
.av-sum-v {{font-size: 17px; color: {TEXT}; margin-top: 1px;}}
.av-key {{
  display: flex; gap: 14px; flex-wrap: wrap;
  font-size: 11px; color: {TEXT_SOFT}; margin: 6px 0 10px;
}}
.av-key span span {{
  display: inline-block; width: 9px; height: 9px;
  border-radius: 3px; margin-right: 5px;
}}

@media (max-width: 640px) {{
  .av-dow {{gap: 3px;}}
  .av-dow div {{font-size: 0;}}
  .av-dow-s {{display: inline; font-size: 9px;}}
  div[class*="st-key-avd-"] button {{min-height: 38px; font-size: 13px;}}
  div[class*="st-key-avd-"] {{margin-bottom: 3px;}}
  .av-locked {{padding: 5px 1px; min-height: 38px; border-radius: 6px;}}
  .av-locked-n {{font-size: 12px;}}
  .av-locked-u {{font-size: 9px;}}
  .av-off {{min-height: 38px; font-size: 11px; padding: 10px 1px;}}
  .av-sum {{gap: 16px;}}
  .av-sum-v {{font-size: 14px;}}
}}
</style>
""",
        unsafe_allow_html=True,
    )


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
    Saisie des disponibilités par clic sur les jours.

    Vert = disponible, rouge = indisponible. Un mois vierge est
    entièrement indisponible. Les clics ne touchent pas la base :
    tout est enregistré en une seule écriture à la validation.
    """

    # ----------------------------------------------------------
    # FORÇAGES ADMIN (source de vérité : Firestore)
    # ----------------------------------------------------------
    forced = load_forced_assignments(year, month) or {}
    forced_assignments.clear()
    forced_assignments.update(forced)

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)

    # ----------------------------------------------------------
    # ÉTAT LOCAL : chargé une fois, modifié par les clics
    # ----------------------------------------------------------
    state_key = f"avstate::{email}::{year}::{month}"
    saved_key = f"avsaved::{email}::{year}::{month}"

    if state_key not in st.session_state:
        stored = load_fn(email, year, month) or {}
        st.session_state[state_key] = {
            k for k, v in stored.items() if v is True
        }
        st.session_state[saved_key] = set(st.session_state[state_key])

    selected = st.session_state[state_key]
    last_saved = st.session_state[saved_key]
    dirty = selected != last_saved

    states = {d: True for d in selected}
    _inject_css(year, month, states, weeks)

    # ----------------------------------------------------------
    # EN-TÊTE
    # ----------------------------------------------------------
    st.markdown(
        f'<div class="pl-head"><div class="pl-title">'
        f'{MONTH_LABELS[month]} {year}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="av-key">'
        f'<span><span style="background:{AV_BG}"></span>Disponible</span>'
        f'<span><span style="background:{UN_BG}"></span>Indisponible</span>'
        f'<span><span style="background:{NEUTRAL_BG}"></span>Forcé par l\'admin</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ----------------------------------------------------------
    # SÉLECTION RAPIDE
    # ----------------------------------------------------------
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

    if b1.button("Tout", key=f"av-all-{year}-{month}",
                 use_container_width=True):
        st.session_state[state_key] = days_of(lambda d: True)
        st.rerun()

    if b2.button("Semaine", key=f"av-week-{year}-{month}",
                 use_container_width=True, help="Lundi à jeudi"):
        st.session_state[state_key] = days_of(lambda d: d.weekday() <= 3)
        st.rerun()

    if b3.button("Week-end", key=f"av-we-{year}-{month}",
                 use_container_width=True, help="Vendredi à dimanche"):
        st.session_state[state_key] = days_of(lambda d: d.weekday() >= 4)
        st.rerun()

    if b4.button("Aucun", key=f"av-none-{year}-{month}",
                 use_container_width=True):
        st.session_state[state_key] = set()
        st.rerun()

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ----------------------------------------------------------
    # GRILLE
    # ----------------------------------------------------------
    st.markdown(
        '<div class="av-dow">'
        + "".join(
            f'<div>{full}<span class="av-dow-s">{sh}</span></div>'
            for full, sh in DOW
        )
        + "</div>",
        unsafe_allow_html=True,
    )

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
                name = users.get(forced_user, {}).get(
                    "name", forced_user.split("@")[0]
                ).split(" ")[0]
                cols[i].markdown(
                    f'<div class="av-locked">'
                    f'<div class="av-locked-n">{day.day}</div>'
                    f'<div class="av-locked-u">{esc(abbrev(name))}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                continue

            if cols[i].button(
                str(day.day),
                key=_day_key(year, month, day.day),
                use_container_width=True,
            ):
                if day_iso in selected:
                    selected.discard(day_iso)
                else:
                    selected.add(day_iso)
                st.rerun()

    # ----------------------------------------------------------
    # ENREGISTREMENT
    # ----------------------------------------------------------
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    label = ("Enregistrer mes disponibilités"
             if dirty else "Disponibilités à jour")

    if st.button(label, key=f"av-save-{year}-{month}",
                 type="primary" if dirty else "secondary",
                 disabled=not dirty, use_container_width=True):
        save_fn(email, year, month, {d: True for d in selected})
        st.session_state[saved_key] = set(selected)
        st.success(f"{len(selected)} jour(s) enregistré(s).")
        st.rerun()

    if dirty:
        st.caption("Modifications non enregistrées.")

    # ----------------------------------------------------------
    # RÉCAPITULATIF
    # ----------------------------------------------------------
    weekend_days = sum(
        1 for d in selected if dt.date.fromisoformat(d).weekday() >= 5
    )
    st.markdown(
        f'<div class="av-sum">'
        f'<div><div class="av-sum-l">Jours disponibles</div>'
        f'<div class="av-sum-v">{len(selected)}</div></div>'
        f'<div><div class="av-sum-l">Dont week-ends</div>'
        f'<div class="av-sum-v">{weekend_days}</div></div>'
        f'<div><div class="av-sum-l">Potentiel</div>'
        f'<div class="av-sum-v">{len(selected) * HOURS_PER_DAY} h</div></div>'
        f'<div><div class="av-sum-l">Jours forcés</div>'
        f'<div class="av-sum-v">{len(forced)}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ----------------------------------------------------------
    # FORÇAGE ADMIN
    # ----------------------------------------------------------
    if not is_admin:
        return

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    with st.expander(f"Forçage administrateur ({len(forced)} jour(s))"):
        st.caption(
            "Un jour forcé est attribué d'office à un collaborateur, "
            "sans tenir compte de ses disponibilités."
        )

        last_day = calendar.monthrange(year, month)[1]
        c1, c2 = st.columns(2)

        forced_day = c1.date_input(
            "Jour",
            value=dt.date(year, month, 1),
            min_value=dt.date(year, month, 1),
            max_value=dt.date(year, month, last_day),
            format="DD/MM/YYYY",
            key=f"force-day-{year}-{month}",
        )

        labels = {
            info.get("name", mail.split("@")[0]): mail
            for mail, info in users.items()
        }

        chosen = c2.selectbox(
            "Collaborateur",
            options=sorted(labels),
            key=f"force-user-{year}-{month}",
        )

        day_key = forced_day.isoformat()
        d1, d2 = st.columns(2)

        if d1.button("Forcer ce jour", key=f"force-btn-{year}-{month}",
                     use_container_width=True):
            save_forced_assignment(year, month, day_key, labels[chosen])
            st.rerun()

        if day_key in forced:
            if d2.button("Annuler le forçage",
                         key=f"unforce-btn-{year}-{month}",
                         use_container_width=True):
                save_forced_assignment(year, month, day_key, None)
                st.rerun()

        if forced:
            st.markdown("<div style='height:6px'></div>",
                        unsafe_allow_html=True)
            lines = []
            for d in sorted(forced):
                who = users.get(forced[d], {}).get(
                    "name", forced[d].split("@")[0]
                )
                pretty = dt.date.fromisoformat(d).strftime("%d/%m")
                lines.append(
                    f'<div style="font-size:12px;color:{TEXT_SOFT};'
                    f'padding:2px 0">{pretty} — {esc(who)}</div>'
                )
            st.markdown("".join(lines), unsafe_allow_html=True)