import datetime as dt
import copy
import requests
import streamlit as st
import firebase_admin

from firebase_admin import credentials, auth, firestore
from datetime import timezone

# ============================================================
# INIT FIREBASE
# ============================================================
try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

USERS = db.collection("users")
PROPOSALS = db.collection("planning_proposals")
FORCED = db.collection("forced_assignments")


# ============================================================
# NORMALISATION DES EMAILS
# ============================================================
def normalize_email(email: str | None) -> str:
    """
    Firebase Auth ignore la casse des emails, mais les identifiants
    de documents Firestore y sont sensibles : sans normalisation,
    une connexion avec une majuscule crée un document distinct
    (doublon d'utilisateur). Tous les accès Firestore passent par
    cette fonction.
    """
    return (email or "").strip().lower()


# ============================================================
# AUTH
# ============================================================
def _verify_password_with_firebase(email: str, password: str) -> str | None:
    """
    Vérifie le mot de passe via l'API REST Firebase Auth
    (signInWithPassword). Le SDK Admin ne peut PAS valider un
    mot de passe : il faut passer par cette API.

    Retourne l'uid si les identifiants sont valides, sinon None.
    """
    api_key = st.secrets["firebase_web_api_key"]
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:"
        f"signInWithPassword?key={api_key}"
    )
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    return response.json().get("localId")


def login_user(email: str, password: str | None = None) -> bool:
    email = normalize_email(email)

    if not email or not password:
        return False

    uid = _verify_password_with_firebase(email, password)
    if uid is None:
        return False

    st.session_state.auth_user = {
        "uid": uid,
        "email": email,
    }
    return True


def logout_user() -> None:
    st.session_state.auth_user = None


def is_admin() -> bool:
    user = st.session_state.get("auth_user")
    if not user:
        return False

    doc = USERS.document(normalize_email(user["email"])).get()
    if not doc.exists:
        return False

    data = doc.to_dict() or {}
    # Deux conventions coexistent en base : un booléen `admin`
    # et un champ texte `role`. On accepte les deux.
    return bool(data.get("admin")) or data.get("role") == "admin"


# ============================================================
# USERS
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def get_all_users() -> dict:
    """
    Liste des collaborateurs.
    Mise en cache 60s pour éviter de relire Firestore à chaque
    interaction Streamlit (le script est réexécuté à chaque clic).
    """
    return {doc.id: doc.to_dict() for doc in USERS.stream()}


def invalidate_users_cache() -> None:
    """À appeler après toute écriture sur un document utilisateur."""
    get_all_users.clear()


# ============================================================
# DISPONIBILITÉS
# ============================================================
def load_availability(email: str, year: int, month: int) -> dict:
    doc = USERS.document(normalize_email(email)).get()
    if not doc.exists:
        return {}
    return doc.to_dict().get(f"availability_{year}_{month}", {})


def save_availability(email: str, year: int, month: int,
                      availability: dict) -> None:
    """
    Remplace intégralement les disponibilités du mois.

    set(..., merge=True) fusionne les maps en profondeur : les jours
    retirés survivraient à l'enregistrement. On supprime donc le
    champ avant de le réécrire, pour que décocher un jour soit bien
    pris en compte.
    """
    field = f"availability_{year}_{month}"
    ref = USERS.document(normalize_email(email))

    ref.set({field: firestore.DELETE_FIELD}, merge=True)
    if availability:
        ref.set({field: availability}, merge=True)

    invalidate_users_cache()


# ============================================================
# FORÇAGE ADMIN
# ============================================================
def save_forced_assignment(
    year: int,
    month: int,
    day_iso: str,
    email: str | None,
) -> None:
    ref = FORCED.document(f"{year}_{month}")
    if email is None:
        # set(..., merge=True) fonctionne même si le document
        # n'existe pas encore, contrairement à update().
        ref.set({day_iso: firestore.DELETE_FIELD}, merge=True)
    else:
        ref.set({day_iso: normalize_email(email)}, merge=True)
    invalidate_forced_cache()


@st.cache_data(ttl=60, show_spinner=False)
def load_forced_assignments(year: int, month: int) -> dict:
    """
    Forçages d'un mois. Mis en cache : la vue déroulante affiche
    une vingtaine de mois, ce qui ferait autant de lectures
    Firestore à chaque interaction sans cela.
    """
    ref = FORCED.document(f"{year}_{month}")
    doc = ref.get()
    return doc.to_dict() if doc.exists else {}


def invalidate_forced_cache() -> None:
    """À appeler après toute écriture sur un forçage."""
    load_forced_assignments.clear()


# ============================================================
# SERIALISATION PLANNING
# ============================================================
def serialize_planning(planning: dict) -> dict:
    return {
        "blocks": [
            {
                **block,
                "start": block["start"].isoformat(),
                "end": block["end"].isoformat(),
            }
            for block in planning.get("blocks", [])
        ]
    }


def deserialize_planning(planning: dict) -> dict:
    planning = copy.deepcopy(planning)
    for block in planning.get("blocks", []):
        if isinstance(block.get("start"), str):
            block["start"] = dt.date.fromisoformat(block["start"])
        if isinstance(block.get("end"), str):
            block["end"] = dt.date.fromisoformat(block["end"])
    return planning


# ============================================================
# PLANNING UNIQUE
# ============================================================
def save_planning_proposal(
    year: int,
    month: int,
    _index: str,
    planning: dict,
    created_by: str,
) -> None:
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    ref.set(
        {
            "planning": serialize_planning(planning),
            "created_by": normalize_email(created_by),
            "created_at": dt.datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )
    invalidate_planning_cache()


@st.cache_data(ttl=60, show_spinner=False)
def load_planning_proposals(year: int, month: int) -> dict:
    """
    Charge le planning d'un mois.
    Mis en cache : les onglets Heures et Plannings bouclent sur
    une vingtaine de mois, ce qui ferait autant de lectures
    Firestore à chaque clic sans cela.
    """
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    doc = ref.get()

    if not doc.exists:
        return {}

    data = doc.to_dict() or {}
    if "planning" not in data:
        return {}

    data["planning"] = deserialize_planning(data["planning"])
    data["locked"] = bool(data.get("locked", False))
    return {"current": data}


def invalidate_planning_cache() -> None:
    """À appeler après toute écriture sur un planning."""
    load_planning_proposals.clear()


# ============================================================
# VERROUILLAGE DU PLANNING (PERSISTANT)
# ============================================================
def set_planning_lock(
    year: int,
    month: int,
    locked: bool,
    email: str | None = None,
) -> None:
    """
    Verrouille ou déverrouille le planning d'un mois.
    L'état est stocké dans Firestore (et non en session), afin
    d'être partagé entre tous les utilisateurs et conservé
    après rechargement de la page.
    """
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    payload = {"locked": bool(locked)}

    if locked:
        payload["locked_by"] = normalize_email(email)
        payload["locked_at"] = dt.datetime.now(timezone.utc).isoformat()

    ref.set(payload, merge=True)
    invalidate_planning_cache()


def is_planning_locked(year: int, month: int) -> bool:
    proposals = load_planning_proposals(year, month)
    proposal = proposals.get("current")
    return bool(proposal and proposal.get("locked"))


# ============================================================
# HEURES MENSUELLES (AJUSTABLES)
# ============================================================
def load_monthly_hours(email: str, year: int, month: int) -> int | None:
    """
    Retourne les heures mensuelles ajustées si elles existent,
    sinon None
    """
    doc = USERS.document(normalize_email(email)).get()
    if not doc.exists:
        return None

    return doc.to_dict().get(f"hours_{year}_{month}")


def save_monthly_hours(email: str, year: int, month: int, hours: int) -> None:
    """
    Sauvegarde les heures mensuelles ajustées
    """
    USERS.document(normalize_email(email)).set(
        {f"hours_{year}_{month}": int(hours)},
        merge=True,
    )
    invalidate_users_cache()


def reset_monthly_hours(email: str, year: int, month: int) -> None:
    """
    Supprime l'ajustement manuel : on repasse sur les heures
    calculées depuis le planning.
    """
    USERS.document(normalize_email(email)).set(
        {f"hours_{year}_{month}": firestore.DELETE_FIELD},
        merge=True,
    )
    invalidate_users_cache()


# ============================================================
# CORRECTION DU CUMUL ANNUEL (ADMIN)
# ============================================================
def load_cumul_adjustment(email: str, year: int) -> int:
    """
    Correction manuelle (en heures, positive ou négative) appliquée
    au cumul annuel d'un collaborateur. Sert à intégrer un historique
    antérieur à l'application, ou à corriger un écart constaté.
    """
    doc = USERS.document(normalize_email(email)).get()
    if not doc.exists:
        return 0

    return int(doc.to_dict().get(f"cumul_adjustment_{year}") or 0)


def save_cumul_adjustment(email: str, year: int, hours: int) -> None:
    USERS.document(normalize_email(email)).set(
        {f"cumul_adjustment_{year}": int(hours)},
        merge=True,
    )
    invalidate_users_cache()


# ============================================================
# HEURES RÉELLES (MOIS PAR MOIS)
# ============================================================
def load_actual_month_hours(email: str, year: int, month: int) -> int | None:
    """
    Heures réellement effectuées pour un utilisateur sur un mois donné
    (corrigées manuellement si besoin)
    """
    doc = USERS.document(normalize_email(email)).get()
    if not doc.exists:
        return None

    return doc.to_dict().get(f"actual_hours_{year}_{month}")


def save_actual_month_hours(
    email: str,
    year: int,
    month: int,
    hours: int,
) -> None:
    """
    Sauvegarde des heures réellement effectuées pour un mois donné
    """
    USERS.document(normalize_email(email)).set(
        {f"actual_hours_{year}_{month}": int(hours)},
        merge=True,
    )
    invalidate_users_cache()