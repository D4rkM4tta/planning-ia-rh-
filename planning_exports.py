import datetime as dt
import calendar
from io import BytesIO
import xlsxwriter


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
            if day.month != month:
                worksheet.write(row, col, "", empty_fmt)
                continue

            user = day_map.get(day)

            if user:
                name = users[user]["name"]
                worksheet.write(
                    row,
                    col,
                    f"{day.day}\n{name}",
                    user_formats[user],
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