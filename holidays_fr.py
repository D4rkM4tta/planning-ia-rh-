"""
Jours fériés français, fêtes mobiles comprises.

Les trois fêtes mobiles (Lundi de Pâques, Ascension, Lundi de
Pentecôte) dépendent de la date de Pâques, calculée ici par
l'algorithme de Meeus pour le calendrier grégorien. Aucune
dépendance externe n'est nécessaire.
"""
import datetime as dt
from functools import lru_cache


def easter_sunday(year: int) -> dt.date:
    """Dimanche de Pâques (algorithme de Meeus / Jones / Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


@lru_cache(maxsize=32)
def french_holidays(year: int) -> dict:
    """
    Jours fériés d'une année, sous la forme {date: nom}.

    Les 11 jours fériés légaux applicables sur tout le territoire.
    L'Alsace-Moselle en compte deux de plus (Vendredi saint et
    26 décembre) ; ils ne sont pas inclus ici.
    """
    easter = easter_sunday(year)

    days = {
        dt.date(year, 1, 1): "Jour de l'An",
        easter + dt.timedelta(days=1): "Lundi de Pâques",
        dt.date(year, 5, 1): "Fête du Travail",
        dt.date(year, 5, 8): "Victoire 1945",
        easter + dt.timedelta(days=39): "Ascension",
        easter + dt.timedelta(days=50): "Lundi de Pentecôte",
        dt.date(year, 7, 14): "Fête nationale",
        dt.date(year, 8, 15): "Assomption",
        dt.date(year, 11, 1): "Toussaint",
        dt.date(year, 11, 11): "Armistice 1918",
        dt.date(year, 12, 25): "Noël",
    }

    return dict(sorted(days.items()))


def holidays_of_month(year: int, month: int) -> dict:
    """Jours fériés d'un mois donné, {date: nom}."""
    return {
        d: name
        for d, name in french_holidays(year).items()
        if d.month == month
    }


def is_holiday(day: dt.date) -> bool:
    return day in french_holidays(day.year)