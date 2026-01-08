import firebase_admin
from firebase_admin import credentials, auth, firestore
import streamlit as st
import datetime as dt

# ============================================================
# INIT FIREBASE
# ============================================================
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

USERS = db.collection("users")
LOCKS = db.collection("planning_locks")
FORCED = db.collection("forced_assignments")
PROPOSALS = db.collection("planning_proposals")


# ============================================================
# AUTH
# ============================================================
def login_user(email, password):
    try:
        user = auth.get_user_by_email(email)
        st.session_state.auth_user = {
            "uid": user.uid,
            "email": email,
        }
        return True
    except Exception:
        return False


def logout_user():
    st.session_state.auth_user = None


def is_admin():
    u = st.session_state.get("auth_user")
    if not u:
        return False
    doc = USERS.document(u["email"]).get()
    return bool(doc.exists and doc.to_dict().get("admin", False))


# ============================================================
# USERS
# ============================================================
def get_all_users():
    return {d.id: d.to_dict() for d in USERS.stream()}


# ============================================================
# DISPONIBILITÉS
# ============================================================
def load_availability(email, year, month):
    doc = USERS.document(email).get()
    if not doc.exists:
        return {}
    return doc.to_dict().get(f"availability_{year}_{month}", {})


def save_availability(email, year, month, availability):
    USERS.document(email).set(
        {f"availability_{year}_{month}": availability},
        merge=True
    )


# ============================================================
# FORÇAGE ADMIN (OPTIONNEL)
# ============================================================
def load_forced_assignments(year, month):
    doc = FORCED.document(f"{year}_{month}").get()
    return doc.to_dict() if doc.exists else {}


def save_forced_assignment(year, month, day_iso, email):
    FORCED.document(f"{year}_{month}").set(
        {day_iso: email},
        merge=True
    )


# ============================================================
# PLANNING LOCK
# ============================================================
def is_planning_locked(year, month):
    return LOCKS.document(f"{year}_{month}").get().exists


def lock_planning(year, month, planning_data):
    LOCKS.document(f"{year}_{month}").set({
        "locked": True,
        "validated_at": dt.datetime.utcnow().isoformat()
    })


# ============================================================
# SERIALISATION PLANNING
# ============================================================
def serialize_planning(planning):
    """
    Convert datetime.date -> ISO string
    """
    blocks = []
    for b in planning["blocks"]:
        blocks.append({
            **b,
            "start": b["start"].isoformat(),
            "end": b["end"].isoformat(),
        })
    return {"blocks": blocks}


def deserialize_planning(planning):
    """
    Convert ISO string -> datetime.date
    """
    for b in planning["blocks"]:
        if isinstance(b["start"], str):
            b["start"] = dt.date.fromisoformat(b["start"])
        if isinstance(b["end"], str):
            b["end"] = dt.date.fromisoformat(b["end"])
    return planning


# ============================================================
# PLANNINGS PROPOSÉS
# ============================================================
def save_planning_proposal(year, month, index, planning, created_by):
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    ref.set({}, merge=True)

    ref.collection("proposals").document(f"proposal_{index}").set({
        "planning": serialize_planning(planning),
        "created_by": created_by,
        "created_at": dt.datetime.utcnow().isoformat(),
        "status": "PROPOSED",   # PROPOSED | VALIDATED | REJECTED
        "votes": {},            # email -> True / False
    })


def load_planning_proposals(year, month):
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    proposals = {}

    for doc in ref.collection("proposals").stream():
        data = doc.to_dict()

        # Sécurité structure
        if "planning" not in data:
            continue

        data["planning"] = deserialize_planning(data["planning"])
        data.setdefault("votes", {})
        data.setdefault("status", "PROPOSED")

        proposals[doc.id] = data

    return proposals


# ============================================================
# VOTE
# ============================================================
def vote_planning(year, month, proposal_id, email, vote: bool):
    PROPOSALS.document(f"{year}-{month:02d}") \
        .collection("proposals") \
        .document(proposal_id) \
        .update({f"votes.{email}": vote})


# ============================================================
# VALIDATION ADMIN
# ============================================================
def validate_planning(year, month, proposal_id):
    col = PROPOSALS.document(f"{year}-{month:02d}").collection("proposals")

    # Tous rejetés
    for doc in col.stream():
        col.document(doc.id).update({"status": "REJECTED"})

    # Celui-ci validé
    col.document(proposal_id).update({"status": "VALIDATED"})