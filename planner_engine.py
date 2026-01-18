import calendar
import datetime as dt
import random
from collections import defaultdict

# ============================================================
# OUTILS
# ============================================================

def daterange(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)


def month_blocks(year: int, month: int):
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    blocks = []
    block_id = 1

    for week in weeks:
        week_days = week[0:4]
        if any(d.month == month for d in week_days):
            start, end = week_days[0], week_days[-1]
            blocks.append({
                "id": block_id,
                "type": "week",
                "start": start,
                "end": end,
                "days": [d.isoformat() for d in daterange(start, end)],
                "assigned_to": None,
            })
            block_id += 1

        weekend_days = week[4:7]
        if any(d.month == month for d in weekend_days):
            start, end = weekend_days[0], weekend_days[-1]
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
# SOLVEUR INTERNE
# ============================================================

def _solve_once(
    blocks,
    users,
    availability_by_user,
    forced_assignments,
    target_hours,
    tolerance=0.15,
):
    eligible = defaultdict(list)
    block_by_id = {b["id"]: b for b in blocks}

    # 🔒 Détection des blocs forcés
    forced_block_owner = {}
    for block in blocks:
        forced_users = {
            forced_assignments[d]
            for d in block["days"]
            if d in forced_assignments
        }
        if len(forced_users) == 1:
            forced_block_owner[block["id"]] = forced_users.pop()
        elif len(forced_users) > 1:
            return None, -1

    # 🎯 Éligibilité
    for block in blocks:
        for u, avail in availability_by_user.items():
            if block["id"] in forced_block_owner:
                if forced_block_owner[block["id"]] == u:
                    eligible[u].append(block["id"])
            else:
                if all(d in avail for d in block["days"]):
                    eligible[u].append(block["id"])

    assigned_by_user = defaultdict(set)
    hours_by_user = defaultdict(int)
    assigned_blocks = set()
    overflow_used = defaultdict(bool)  # ⭐ NOUVEAU

    def violates_consecutive(u, block):
        for b_id in assigned_by_user[u]:
            prev = block_by_id[b_id]
            if prev["end"] + dt.timedelta(days=1) >= block["start"]:
                return True
        return False

    def violates_hours(u, block_days):
        projected = hours_by_user[u] + len(block_days) * 10
        max_hours = target_hours[u] * (1 + tolerance)

        if projected <= max_hours:
            return False

        # ⭐ AUTORISATION UNIQUE DE DÉPASSEMENT
        if not overflow_used[u]:
            return False

        return True

    # 1️⃣ FORÇAGE ADMIN
    for block in blocks:
        if block["id"] not in forced_block_owner:
            continue
        u = forced_block_owner[block["id"]]
        block["assigned_to"] = u
        assigned_blocks.add(block["id"])
        assigned_by_user[u].add(block["id"])
        hours_by_user[u] += len(block["days"]) * 10

    users_sorted = list(users)
    random.shuffle(users_sorted)

    # 2️⃣ ATTRIBUTION PRINCIPALE
    for u in users_sorted:
        for block in blocks:
            if block["id"] in assigned_blocks:
                continue
            if block["id"] not in eligible[u]:
                continue
            if violates_consecutive(u, block):
                continue

            projected = hours_by_user[u] + len(block["days"]) * 10
            max_hours = target_hours[u] * (1 + tolerance)

            if projected > max_hours:
                if overflow_used[u]:
                    continue
                overflow_used[u] = True

            block["assigned_to"] = u
            assigned_blocks.add(block["id"])
            assigned_by_user[u].add(block["id"])
            hours_by_user[u] = projected
            break

    # 3️⃣ REMPLISSAGE FINAL
    for block in blocks:
        if block["assigned_to"]:
            continue
        random.shuffle(users_sorted)
        for u in users_sorted:
            if block["id"] not in eligible[u]:
                continue
            if violates_consecutive(u, block):
                continue

            projected = hours_by_user[u] + len(block["days"]) * 10
            max_hours = target_hours[u] * (1 + tolerance)

            if projected > max_hours:
                if overflow_used[u]:
                    continue
                overflow_used[u] = True

            block["assigned_to"] = u
            assigned_by_user[u].add(block["id"])
            hours_by_user[u] = projected
            break

    covered = sum(1 for b in blocks if b["assigned_to"])
    return blocks, covered


# ============================================================
# SOLVEUR FINAL
# ============================================================

def generate_planning(
    *,
    year: int,
    month: int,
    users: dict,
    availability_by_user: dict,
    forced_assignments: dict,
    attempts: int = 80,
):
    target_hours = {
        u: int(data["monthly_hours"])
        for u, data in users.items()
    }

    base_blocks = month_blocks(year, month)
    best_blocks = None
    best_score = -1

    for _ in range(attempts):
        blocks = [{**b, "assigned_to": None} for b in base_blocks]
        random.shuffle(blocks)

        solved, score = _solve_once(
            blocks,
            list(users.keys()),
            availability_by_user,
            forced_assignments,
            target_hours,
        )

        if solved and score > best_score:
            best_blocks = solved
            best_score = score

        if best_score == len(blocks):
            break

    return {
        "blocks": best_blocks or [],
        "warnings": [],
    }