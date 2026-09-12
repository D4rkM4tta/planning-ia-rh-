# ============================================================
# BASELINE SOLVEUR V2 — AVEC FRAGMENTATION DE BLOCS
# Version validée fonctionnellement (forçage + marges + équité)
# + Fragmentation automatique en cas de forçage partiel
# Date : 2026-03
# ============================================================
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
# FRAGMENTATION DE BLOCS (NOUVEAU)
# ============================================================

def fragment_blocks_with_forced_assignments(blocks, forced_assignments):
    """
    Fragmente les blocs qui ont des forçages conflictuels
    (plusieurs utilisateurs différents forcés sur le même bloc).

    Retourne : (fragmented_blocks, error_message)
    - fragmented_blocks : list de blocs (possiblement fragmentés)
    - error_message : None si OK, sinon description du conflit irrésolvable
    """

    fragmented = []
    next_id = max((b["id"] for b in blocks), default=0) + 1

    for block in blocks:
        # 🔍 Identifier les forçages sur ce bloc
        forced_users_in_block = defaultdict(list)  # {user: [day1, day2, ...]}

        for day_iso in block["days"]:
            if day_iso in forced_assignments:
                user = forced_assignments[day_iso]
                forced_users_in_block[user].append(day_iso)

        # ✅ Cas 1 : Aucun forçage → bloc intact
        if not forced_users_in_block:
            fragmented.append(block)
            continue

        # ✅ Cas 2 : Un seul utilisateur forcé → bloc intact
        if len(forced_users_in_block) == 1:
            fragmented.append(block)
            continue

        # 🔴 Cas 3 : FORÇAGES MULTIPLES → Fragmenter
        # On fragmente par "plages continues de jours forcés à la même personne"
        days_in_block = block["days"]

        i = 0
        while i < len(days_in_block):
            day_iso = days_in_block[i]

            # Chercher tous les jours consécutifs avec le même forçage (ou pas de forçage)
            if day_iso in forced_assignments:
                # C'est un jour forcé → fragmenter autour
                user = forced_assignments[day_iso]

                # Créer un bloc d'1 jour pour ce jour forcé
                start_date = dt.date.fromisoformat(day_iso)
                fragmented.append({
                    "id": next_id,
                    "type": f"{block['type']}_fragment",
                    "start": start_date,
                    "end": start_date,
                    "days": [day_iso],
                    "assigned_to": None,
                })
                next_id += 1
                i += 1
            else:
                # Jour non-forcé → regrouper les jours consécutifs non-forcés
                j = i
                while j < len(days_in_block) and days_in_block[j] not in forced_assignments:
                    j += 1

                # Créer un bloc avec les jours [i:j]
                days_slice = days_in_block[i:j]
                start_date = dt.date.fromisoformat(days_slice[0])
                end_date = dt.date.fromisoformat(days_slice[-1])

                fragmented.append({
                    "id": next_id,
                    "type": f"{block['type']}_fragment",
                    "start": start_date,
                    "end": end_date,
                    "days": days_slice,
                    "assigned_to": None,
                })
                next_id += 1
                i = j

    return fragmented, None


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
            # ⚠️ Cela NE devrait JAMAIS arriver après fragmentation
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
    overflow_used = defaultdict(bool)

    def violates_consecutive(u, block):
        for b_id in assigned_by_user[u]:
            prev = block_by_id[b_id]
            if prev["end"] + dt.timedelta(days=1) >= block["start"]:
                return True
        return False

    def violates_hours(u, block_days):
        projected = hours_by_user[u] + len(block_days) * 9
        max_hours = target_hours[u] * (1 + tolerance)

        if projected <= max_hours:
            return False

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
        hours_by_user[u] += len(block["days"]) * 9

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

            projected = hours_by_user[u] + len(block["days"]) * 9
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

            projected = hours_by_user[u] + len(block["days"]) * 9
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

    # 🔥 FRAGMENTATION DES BLOCS (NOUVEAU)
    base_blocks, frag_error = fragment_blocks_with_forced_assignments(
        base_blocks,
        forced_assignments
    )

    if frag_error:
        return {
            "blocks": [],
            "warnings": [frag_error],
        }

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