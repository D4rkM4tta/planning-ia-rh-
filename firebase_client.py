import datetime as dt
import copy
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
def login_user(email: str, _password: str | None = None) -> bool:
    try:
        user = auth.get_user_by_email(email)
        st.session_state.auth_user = {
            "uid": user.uid,
            "email": email,
        }
        return True
    except auth.UserNotFoundError:
        return False


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
def get_all_users() -> dict:
    return {doc.id: doc.to_dict() for doc in USERS.stream()}

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
        ref.update({day_iso: firestore.DELETE_FIELD})
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