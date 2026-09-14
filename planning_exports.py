import datetime as dt
import calendar
from io import BytesIO
import xlsxwriter

# ============================================================
# CONSTANTES RH
# ============================================================
# Amplitude de travail : 9h → 19h (1h de repas non comptabilisée)
WORK_START_HOUR = 9
WORK_END_HOUR = 19
TIMEZONE = "Europe/Paris"


def export_planning_excel_calendar_colored(
    *,
    blocks,
    users,
    user_colors,
    year,
    month,
):
    """
    Export Excel lisible en format calendrier :
    - colonnes = Lun → Dim
    - lignes = semaines
    - cellule = Nom collaborateur
    - couleur = couleur UI
    """

    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer)
    worksheet = workbook.add_worksheet("Planning")

    # =========================================================
    # STYLES
    # =========================================================
    header_fmt = workbook.add_format({
        "bold": True,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })

    empty_fmt = workbook.add_format({
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })

    # Styles par utilisateur
    user_formats = {}
    for email, color in user_colors.items():
        user_formats[email] = workbook.add_format({
            "bg_color": color,
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "text_wrap": True,
        })

    # Style de repli si un utilisateur assigné n'a pas de couleur connue
    fallback_fmt = workbook.add_format({
        "bg_color": "#546E7A",
        "font_color": "#FFFFFF",
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "text_wrap": True,
    })

    uncovered_fmt = workbook.add_format({
        "border": 1,
        "align": "center",
        "valign": "vcenter",
        "font_color": "#B71C1C",
    })

    # =========================================================
    # EN-TÊTES
    # =========================================================
    headers = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    for col, h in enumerate(headers):
        worksheet.write(0, col, h, header_fmt)
        worksheet.set_column(col, col, 22)

    # =========================================================
    # MAPPING JOUR → UTILISATEUR
    # =========================================================
    day_map = {}
    for block in blocks:
        user = block["assigned_to"]
        if not user:
            continue
        for d in block["days"]:
            day = dt.date.fromisoformat(d)
            if day.year == year and day.month == month:
                day_map[day] = user

    # =========================================================
    # CALENDRIER
    # =========================================================
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    row = 1
    for week in weeks:
        for col, day in enumerate(week):
            if day.month != month or day.year != year:
                worksheet.write(row, col, "", empty_fmt)
                continue

            user = day_map.get(day)

            if user:
                name = users.get(user, {}).get("name", user)
                worksheet.write(
                    row,
                    col,
                    f"{day.day}\n{name}",
                    user_formats.get(user, fallback_fmt),
                )
            else:
                worksheet.write(
                    row,
                    col,
                    f"{day.day}\nNON COUVERT",
                    uncovered_fmt,
                )

        worksheet.set_row(row, 70)
        row += 1

    workbook.close()
    buffer.seek(0)
    return buffer


def _escape_ical(text: str) -> str:
    """Échappe les caractères spéciaux selon la RFC 5545."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def export_planning_ical(planning: dict, users: dict, year: int, month: int):
    """
    Export iCal personnalisé :
    - Un utilisateur voit uniquement SON planning
    - Un admin voit tout le planning

    Les événements couvrent l'amplitude réelle 9h → 19h (Europe/Paris).
    """

    import streamlit as st
    from uuid import uuid4

    auth_user = st.session_state.get("auth_user") or {}
    current_user = auth_user.get("email")
    is_admin = bool(users.get(current_user, {}).get("admin", False))

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Planning IA RH//EN",
        "CALSCALE:GREGORIAN",
    ]

    for block in planning.get("blocks", []):
        assigned = block.get("assigned_to")
        if not assigned:
            continue

        # 🔥 Filtrage clé : un non-admin ne voit que son propre planning
        if not is_admin and assigned != current_user:
            continue

        name = users.get(assigned, {}).get("name", assigned)

        cur = block["start"]
        end = block["end"]

        while cur <= end:
            if cur.year == year and cur.month == month:
                start_dt = dt.datetime.combine(cur, dt.time(WORK_START_HOUR, 0))
                end_dt = dt.datetime.combine(cur, dt.time(WORK_END_HOUR, 0))

                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{uuid4()}@planning-ia-rh",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART;TZID={TIMEZONE}:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND;TZID={TIMEZONE}:{end_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{_escape_ical(f'Mondial IRE — {name}')}",
                    "DESCRIPTION:Amplitude 9h-19h (1h de repas non comptabilisée)",
                    "END:VEVENT",
                ])

            cur += dt.timedelta(days=1)

    lines.append("END:VCALENDAR")

    # RFC 5545 : les lignes doivent être séparées par CRLF
    return "\r\n".join(lines).encode("utf-8")