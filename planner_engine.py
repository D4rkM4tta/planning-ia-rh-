import datetime as dt
import calendar
from collections import defaultdict

# -------------------------------------------------
# Définition des blocs
# -------------------------------------------------
def get_blocks(year, month):
    """
    Retourne une liste ordonnée de blocs :
    {
        index: int,
        type: "WEEK" | "WEEKEND",
        days: [date, ...]
    }
    """
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    blocks = []
    idx = 0

    for week in weeks:
        # Bloc semaine : Lun → Jeu
        week_days = [d for d in week[:4] if d.month == month]
        if week_days:
            blocks.append({
                "index": idx,
                "type": "WEEK",
                "days": week_days
            })
            idx += 1

        # Bloc week-end : Ven → Dim
        weekend_days = [d for d in week[4:] if d.month == month]
        if weekend_days:
            blocks.append({
                "index": idx,
                "type": "WEEKEND",
                "days": weekend_days
            })
            idx += 1

    return blocks


# -------------------------------------------------
# Solveur principal
# -------------------------------------------------
def generate_planning(year, month, availabilities):
    """
    availabilities = {
        "email": {
            "YYYY-MM-DD": True | False
        }
    }
    """

    blocks = get_blocks(year, month)

    planning = {}
    warnings = []

    last_block_for_user = {}
    worked_days = defaultdict(int)

    for block in blocks:
        block_assigned = False

        for email, dispo in availabilities.items():

            # 1️⃣ Vérifier disponibilité complète du bloc
            if not all(dispo.get(d.isoformat()) is True for d in block["days"]):
                continue

            # 2️⃣ Vérifier règle RH : pas de bloc consécutif
            last = last_block_for_user.get(email)
            if last is not None and block["index"] == last + 1:
                continue

            # ✅ Affectation
            for d in block["days"]:
                planning[d] = email
                worked_days[email] += 1

            last_block_for_user[email] = block["index"]
            block_assigned = True
            break

        if not block_assigned:
            warnings.append(
                f"Bloc {block['type']} ({block['days'][0]} → {block['days'][-1]}) non couvert"
            )
            for d in block["days"]:
                planning[d] = "NON COUVERT"

    return {
        "planning": planning,
        "worked_days": dict(worked_days),
        "warnings": warnings
    }