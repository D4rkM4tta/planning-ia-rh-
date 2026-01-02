#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Planning mensuel – Mars 2026
Version 2.0 : aucune personne ne travaille deux semaines consécutives,
quelle que soit la combinaison de blocs (B1 / B2).
"""

import csv
import datetime
from _typeshed import SupportsDunderGT, SupportsDunderLT
from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Any

# --------------------------------------------------------------
# 1️⃣ Données d’entrée
# --------------------------------------------------------------
Person = namedtuple("Person", ["name", "start", "end"])

people = [
    Person("Claire",    datetime.date(2026, 3, 1),  datetime.date(2026, 3, 15)),
    Person("Leila",     datetime.date(2026, 3, 1),  datetime.date(2026, 3, 5)),
    Person("Leila",     datetime.date(2026, 3, 20), datetime.date(2026, 3, 31)),
    Person("Franck",    datetime.date(2026, 3, 6),  datetime.date(2026, 3, 10)),
    Person("Stéphanie",datetime.date(2026, 3, 14), datetime.date(2026, 3, 20)),
    Person("Aïssa",     datetime.date(2026, 3, 24), datetime.date(2026, 3, 31)),
    Person("Philippe",  datetime.date(2026, 3, 1),  datetime.date(2026, 3, 31)),
]

# --------------------------------------------------------------
# 2️⃣ Helpers
# --------------------------------------------------------------
def daterange(start_date, end_date):
    """Yield each date between start_date and end_date inclusive."""
    for n in range((end_date - start_date).days + 1):
        yield start_date + datetime.timedelta(days=n)


def week_start(date):
    """Return Monday of the week containing `date`."""
    return date - datetime.timedelta(days=date.weekday())


def is_available(person, start, end):
    """True iff the whole interval fits inside the person's availability."""
    return person.start <= start and person.end >= end


# --------------------------------------------------------------
# 3️⃣ Variables de suivi
# --------------------------------------------------------------
MONTH = 3
YEAR  = 2026

first_day = datetime.date(YEAR, MONTH, 1)
# Calcul du dernier jour du mois (générique)
next_month = datetime.date(YEAR, MONTH % 12 + 1, 1)
last_day   = next_month - datetime.timedelta(days=1)

schedule = {}                     # {date: (person, bloc)}
day_counter   = defaultdict(int) # nb de jours travaillés
hour_counter  = defaultdict(int) # heures = jours * 10
weekend_days  = defaultdict(int) # sam./dim. travaillés

# Set contenant les personnes qui ont travaillé **la semaine précédente**
last_week_people = set()

# --------------------------------------------------------------
# 4️⃣ Boucle principale – semaine par semaine
# --------------------------------------------------------------
current = first_day
while current <= last_day:
    # --------- Bloc 1 : Lundi‑Jeudi (4 jours) ----------
    blk1_start = week_start(current)                     # lundi
    blk1_end   = blk1_start + datetime.timedelta(days=3) # jeudi

    # Ajuster si le bloc déborde hors du mois
    if blk1_start.month != MONTH:
        blk1_start = datetime.date(YEAR, MONTH, 1)
    if blk1_end.month != MONTH:
        blk1_end = last_day

    # ----- Sélection du candidat pour le Bloc 1 -----
    chosen_b1 = None
    for p in people:
        if p.name in last_week_people:                 # interdiction de deux semaines consécutives
            continue
        if not is_available(p, blk1_start, blk1_end):
            continue
        if day_counter[p.name] + 4 > 7:                # max 7 jours/mois
            continue
        chosen_b1 = p
        break

    # Attribution du Bloc 1 (si possible)
    if chosen_b1:
        for d in daterange(blk1_start, blk1_end):
            schedule[d] = (chosen_b1.name, "B1")
        day_counter[chosen_b1.name]   += 4
        hour_counter[chosen_b1.name]  += 4 * 10
        # on retient la personne pour la mise à jour de `last_week_people` plus bas
        b1_person = chosen_b1.name
    else:
        b1_person = None   # aucun affectation possible (cas rare)

    # --------- Bloc 2 : Vendredi‑Dimanche (3 jours) ----------
    blk2_start = blk1_end + datetime.timedelta(days=1)   # vendredi
    blk2_end   = blk2_start + datetime.timedelta(days=2)   # dimanche

    # Si le vendredi n’appartient pas au mois, on passe à la semaine suivante
    if blk2_start.month != MONTH:
        current = blk1_start + datetime.timedelta(days=7)
        # on met à jour `last_week_people` (seul le Bloc 1 a pu être attribué)
        last_week_people = {b1_person} if b1_person else set()
        continue
    if blk2_end.month != MONTH:
        blk2_end = last_day

    # ----- Sélection du candidat pour le Bloc 2 -----
    chosen_b2 = None
    for p in people:
        if p.name in last_week_people:                 # même règle que pour le Bloc 1
            continue
        # On ne veut pas que la même personne fasse le Bloc 1 de la même semaine
        if b1_person and p.name == b1_person:
            continue
        if not is_available(p, blk2_start, blk2_end):
            continue
        if day_counter[p.name] + 3 > 7:
            continue
        chosen_b2 = p
        break

    # Attribution du Bloc 2 (si possible)
    if chosen_b2:
        for d in daterange(blk2_start, blk2_end):
            schedule[d] = (chosen_b2.name, "B2")
        day_counter[chosen_b2.name]   += 3
        hour_counter[chosen_b2.name]  += 3 * 10
        weekend_days[chosen_b2.name]  += 3          # tout le bloc 2 est week‑end
        b2_person = chosen_b2.name
    else:
        b2_person = None

    # --------- Mise à jour de la mémoire d’une semaine ----------
    # La prochaine semaine ne pourra pas contenir les personnes qui ont
    # travaillé cette semaine (dans B1 ou B2).
    last_week_people = {n for n in (b1_person, b2_person) if n}

    # Passer à la semaine suivante
    current = blk1_start + datetime.timedelta(days=7)

# --------------------------------------------------------------
# 5️⃣ Affichage du tableau mensuel
# --------------------------------------------------------------
def print_monthly_table():
    header = ["Jour"] + ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    rows = []

    day = first_day
    while day <= last_day:
        week = [str(day.day).rjust(2)]
        monday = week_start(day)
        for i in range(7):
            cur = monday + datetime.timedelta(days=i)
            if cur < first_day or cur > last_day:
                week.append("   ")
            else:
                person, blk = schedule.get(cur, ("-", "-"))
                week.append(f"{person[:3]}{blk}")
        rows.append(week)
        day = monday + datetime.timedelta(days=7)

    print(" | ".join(header))
    print("-" * (len(header) * 8))
    for r in rows:
        print(" | ".join(r))

print("\n=== PLANNING MENSUEL (Mars 2026) ===\n")
print_monthly_table()

# --------------------------------------------------------------
# 6️⃣ Récapitulatif statistique
# --------------------------------------------------------------
print("\n=== RÉCAPITULATIF PAR PERSONNE ===")
for p in sorted({p.name for p in people}):
    total_days = day_counter[p]
    total_hours = hour_counter[p]
    weekend = weekend_days[p]
    print(f"{p:<10} – Jours travaillés : {total_days:2d} "
          f"(week‑end : {weekend}) – Heures : {total_hours}")

# --------------------------------------------------------------
# 7️⃣ Export (CSV / iCal) – décommentez si besoin
# --------------------------------------------------------------
def export_csv(path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Jour", "Personne", "Bloc"])
        for d in sorted(schedule):
            person, blk = schedule[d]
            writer.writerow([d.isoformat(),
                             d.strftime("%A"),
                             person,
                             blk])
    print(f"\nCSV exporté vers : {path}")

def export_ical(path: Path):
    from uuid import uuid4
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lumo Scheduler//EN"
    ]
    d: SupportsDunderLT[Any] | SupportsDunderGT[Any] | Any
    for d in sorted(schedule):
        person, blk = schedule[d]
        uid = uuid4()
        start_dt = datetime.datetime.combine(d, datetime.time(9, 0))
        end_dt   = start_dt + datetime.timedelta(hours=10)
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{person} – {blk}",
            "END:VEVENT"
        ])
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(lines), encoding="utf-8")
    print(f"\niCal exporté vers : {path}")

# Exemple d’usage (décommentez) :
# export_csv(Path("planning_mars_2026.csv"))
# export_ical(Path("planning_mars_2026.ics"))