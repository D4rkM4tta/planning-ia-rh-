import calendar
import datetime as dt
import random
from collections import defaultdict


# ============================================================
# OUTILS
# ============================================================

def daterange(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def month_blocks(year: int, month: int):
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    blocks = []
    block_id = 1

    for week in weeks:
        # Bloc semaine : lundi → jeudi
        week_days = week[0:4]
        if any(d.month == month for d in week_days):
            start = week_days[0]
            end = week_days[-1]
            blocks.append({
                "id": block_id,
                "type": "week",
                "start": start,
                "end": end,
                "days": [d.isoformat() for d in daterange(start, end)],
                "assigned_to": None,
            })
            block_id += 1

        # Bloc week-end : vendredi → dimanche
        weekend_days = week[4:7]
        if any(d.month == month for d in weekend_days):
            start = weekend_days[0]
            end = weekend_days[-1]
            blocks.append({
                "id": block_id,
                "type": "weekend",
                "start": start,
                "end": end,
                "days": [d.isoformat() for d in daterange(start, end)],
                "assigned_to": None,
            })
            block_id += 1

    return blocks


# ============================================================
# SOLVEUR INTERNE (UNE TENTATIVE)
# ============================================================

def _solve_once(blocks, users, availability_by_user, forced_assignments):
    eligible_blocks = defaultdict(list)

    for block in blocks:
        for user, avail in availability_by_user.items():
            if all(day in avail for day in block["days"]):
                eligible_blocks[user].append(block["id"])

    assigned_blocks = set()
    assigned_by_user = defaultdict(set)

    def violates_consecutive(user, block_id):
        return any(abs(block_id - b) == 1 for b in assigned_by_user[user])

    # 1️⃣ Forçage admin (ABSOLU)
    for block in blocks:
        for day in block["days"]:
            if day in forced_assignments:
                user = forced_assignments[day]
                block["assigned_to"] = user
                assigned_blocks.add(block["id"])
                assigned_by_user[user].add(block["id"])

    # 2️⃣ Priorité aux plus contraints
    users_sorted = sorted(
        users,
        key=lambda u: len(eligible_blocks.get(u, []))
    )

    random.shuffle(users_sorted)

    for user in users_sorted:
        for block in blocks:
            if block["id"] in assigned_blocks:
                continue
            if block["id"] not in eligible_blocks.get(user, []):
                continue
            if violates_consecutive(user, block["id"]):
                continue

            block["assigned_to"] = user
            assigned_blocks.add(block["id"])
            assigned_by_user[user].add(block["id"])
            break

    # 3️⃣ Remplissage final
    for block in blocks:
        if block["assigned_to"]:
            continue

        random.shuffle(users_sorted)

        for user in users_sorted:
            if block["id"] not in eligible_blocks.get(user, []):
                continue
            if violates_consecutive(user, block["id"]):
                continue

            block["assigned_to"] = user
            assigned_by_user[user].add(block["id"])
            break

    covered = sum(1 for b in blocks if b["assigned_to"])
    return blocks, covered


# ============================================================
# SOLVEUR MULTI-TENTATIVES (STABLE)
# ============================================================

def generate_planning(
    *,
    year: int,
    month: int,
    users: dict,
    availability_by_user: dict,
    forced_assignments: dict,
    attempts: int = 50,   # 👈 PARAMÈTRE CLÉ
):

    best_blocks = None
    best_score = -1

    base_blocks = month_blocks(year, month)

    for _ in range(attempts):
        # copie propre
        blocks = [
            {**b, "assigned_to": None}
            for b in base_blocks
        ]

        random.shuffle(blocks)

        solved, score = _solve_once(
            blocks,
            list(users.keys()),
            availability_by_user,
            forced_assignments,
        )

        if score > best_score:
            best_score = score
            best_blocks = solved

            # solution parfaite → stop
            if score == len(blocks):
                break

    # ALERTES
    warnings = []
    for u in users:
        if not any(b["assigned_to"] == u for b in best_blocks):
            warnings.append(f"{users[u]['name']} n’a pas été planifié")

    return {
        "blocks": best_blocks,
        "warnings": warnings,
    }