import datetime as dt
import calendar
from collections import defaultdict


# ============================================================
# SOLVEUR RH – VERSION 1 (STABLE)
# ============================================================
# RÈGLES APPLIQUÉES :
# - Bloc SEMAINE : Lundi → Jeudi (40h)
# - Bloc WEEK-END : Vendredi → Dimanche (30h)
# - 1 personne par bloc
# - Pas deux blocs consécutifs pour une même personne
# - Attribution uniquement si dispo sur TOUS les jours du bloc
# - Pas d’optimisation avancée (V1 volontairement simple)
# ============================================================


import datetime as dt
import calendar


def generate_planning(
    *,
    year: int,
    month: int,
    users: dict,
    availability_by_user: dict,
    contract_hours: dict
):
    """
    Génère un planning mensuel basé sur :
    - disponibilités (True = dispo)
    - règles RH blocs semaine / week-end
    """

    blocks = []
    warnings = []

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    block_id = 0

    for w_idx, week in enumerate(weeks, start=1):
        # Bloc semaine (Lundi → Jeudi)
        week_days = [d for d in week if d.month == month and d.weekday() <= 3]
        if week_days:
            blocks.append({
                "id": block_id,
                "week": w_idx,
                "type": "week",
                "start": week_days[0],
                "end": week_days[-1],
                "hours": len(week_days) * 10,
                "assigned_to": None,
                "status": "unassigned",
            })
            block_id += 1

        # Bloc week-end (Vendredi → Dimanche)
        weekend_days = [d for d in week if d.month == month and d.weekday() >= 4]
        if weekend_days:
            blocks.append({
                "id": block_id,
                "week": w_idx,
                "type": "weekend",
                "start": weekend_days[0],
                "end": weekend_days[-1],
                "hours": len(weekend_days) * 10,
                "assigned_to": None,
                "status": "unassigned",
            })
            block_id += 1

    # Tentative d’affectation simple (V1)
    for block in blocks:
        for email, avail in availability_by_user.items():
            days = [
                d.isoformat()
                for d in (
                    block["start"] + dt.timedelta(days=i)
                    for i in range((block["end"] - block["start"]).days + 1)
                )
            ]

            if all(avail.get(day) is True for day in days):
                block["assigned_to"] = email
                block["status"] = "assigned"
                break

        if block["assigned_to"] is None:
            warnings.append(
                f"Bloc {block['type']} semaine {block['week']} non couvert"
            )

    return {
        "blocks": blocks,
        "warnings": warnings,
    }