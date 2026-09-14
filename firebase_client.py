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
    doc = USERS.document(user["email"]).get()
    return bool(doc.exists and doc.to_dict().get("admin", False))

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
    doc = USERS.document(email).get()
    if not doc.exists:
        return {}
    return doc.to_dict().get(f"availability_{year}_{month}", {})


def save_availability(email: str, year: int, month: int, availability: dict) -> None:
    USERS.document(email).set(
        {f"availability_{year}_{month}": availability},
        merge=True,
    )
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
        ref.set({day_iso: email}, merge=True)


def load_forced_assignments(year: int, month: int) -> dict:
    ref = FORCED.document(f"{year}_{month}")
    doc = ref.get()
    return doc.to_dict() if doc.exists else {}

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
            "created_by": created_by,
            "created_at": dt.datetime.now(timezone.utc).isoformat(),
        },
        merge=True,
    )


def load_planning_proposals(year: int, month: int) -> dict:
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    doc = ref.get()

    if not doc.exists:
        return {}

    data = doc.to_dict() or {}
    if "planning" not in data:
        return {}

    data["planning"] = deserialize_planning(data["planning"])
    return {"current": data}

# ============================================================
# HEURES MENSUELLES (AJUSTABLES)
# ============================================================
def load_monthly_hours(email: str, year: int, month: int) -> int | None:
    """
    Retourne les heures mensuelles ajustées si elles existent,
    sinon None
    """
    doc = USERS.document(email).get()
    if not doc.exists:
        return None

    return doc.to_dict().get(f"hours_{year}_{month}")


def save_monthly_hours(email: str, year: int, month: int, hours: int) -> None:
    """
    Sauvegarde les heures mensuelles ajustées
    """
    USERS.document(email).set(
        {f"hours_{year}_{month}": int(hours)},
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
    doc = USERS.document(email).get()
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
    USERS.document(email).set(
        {f"actual_hours_{year}_{month}": int(hours)},
        merge=True,
    )
    invalidate_users_cache()