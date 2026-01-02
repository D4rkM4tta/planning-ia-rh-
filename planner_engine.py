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


def generate_planning(
    year: int,
    month: int,
    users: dict,
    availability_by_user: dict,
    contract_hours: dict,
):
    """
    users: { email: {name, contract_hours, ...} }
    availability_by_user: { email: { 'YYYY-MM-DD': True/False } }
    contract_hours: { email: int }
    """

    # -------------------------------
    # 1️⃣ Construire les blocs du mois
    # -------------------------------
    blocks = []

    cal = calendar.Calendar(firstweekday=0)  # Lundi
    weeks = cal.monthdatescalendar(year, month)

    for week_index, week in enumerate(weeks, start=1):
        # Bloc semaine (Lundi → Jeudi)
        week_days = week[0:4]
        if any(d.month == month for d in week_days):
            blocks.append({
                "week": week_index,
                "type": "week",
                "start": week_days[0],
                "end": week_days[-1],
                "days": [d for d in week_days if d.month == month],
                "hours": 40,
                "assigned_to": None,
                "status": "UNASSIGNED",
            })

        # Bloc week-end (Vendredi → Dimanche)
        weekend_days = week[4:7]
        if any(d.month == month for d in weekend_days):
            blocks.append({
                "week": week_index,
                "type": "weekend",
                "start": weekend_days[0],
                "end": weekend_days[-1],
                "days": [d for d in weekend_days if d.month == month],
                "hours": 30,
                "assigned_to": None,
                "status": "UNASSIGNED",
            })

    # ------------------------------------
    # 2️⃣ Préparer le suivi par utilisateur
    # ------------------------------------
    last_block_index = {}              # dernier bloc travaillé par user
    hours_worked = defaultdict(int)    # heures cumulées
    warnings = []

    # ------------------------------------
    # 3️⃣ Attribution des blocs (simple)
    # ------------------------------------
    for idx, block in enumerate(blocks):
        assigned = False

        for email in users.keys():
            # ⛔ règle : pas deux blocs consécutifs
            if last_block_index.get(email) == idx - 1:
                continue

            # ⛔ vérifier disponibilité complète du bloc
            avail = availability_by_user.get(email, {})
            is_available = True
            for d in block["days"]:
                if avail.get(d.isoformat()) is not True:
                    is_available = False
                    break

            if not is_available:
                continue

            # ✅ attribution
            block["assigned_to"] = email
            block["status"] = "ASSIGNED"
            last_block_index[email] = idx
            hours_worked[email] += block["hours"]
            assigned = True
            break

        if not assigned:
            block["status"] = "UNCOVERED"
            warnings.append(
                f"Bloc {block['type']} semaine {block['week']} "
                f"({block['start'].strftime('%d/%m')} → {block['end'].strftime('%d/%m')}) non couvert"
            )

    # ------------------------------------
    # 4️⃣ Alertes RH simples
    # ------------------------------------
    for email, hours in hours_worked.items():
        contract = contract_hours.get(email, 0)
        if contract and hours > contract:
            warnings.append(
                f"{users[email].get('name', email)} dépasse son contrat "
                f"({hours}h / {contract}h)"
            )

    # ------------------------------------
    # 5️⃣ Résultat final
    # ------------------------------------
    return {
        "blocks": blocks,
        "hours_worked": dict(hours_worked),
        "warnings": warnings,
    }