import firebase_admin
from firebase_admin import credentials, auth, firestore
import streamlit as st
import datetime as dt

if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

USERS = db.collection("users")
LOCKS = db.collection("planning_locks")
PROPOSALS = db.collection("planning_proposals")


def login_user(email, password):
    try:
        user = auth.get_user_by_email(email)
        st.session_state.auth_user = {"uid": user.uid, "email": email}
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


def get_all_users():
    return {d.id: d.to_dict() for d in USERS.stream()}


def load_availability(email, year, month):
    doc = USERS.document(email).get()
    return doc.to_dict().get(f"availability_{year}_{month}", {}) if doc.exists else {}


def save_availability(email, year, month, availability):
    USERS.document(email).set(
        {f"availability_{year}_{month}": availability},
        merge=True
    )


def is_planning_locked(year, month):
    return LOCKS.document(f"{year}_{month}").get().exists


def lock_planning(year, month, planning_data):
    LOCKS.document(f"{year}_{month}").set({"locked": True})


def serialize_planning(planning):
    return {
        "blocks": [
            {
                **b,
                "start": b["start"].isoformat(),
                "end": b["end"].isoformat(),
            }
            for b in planning["blocks"]
        ]
    }


def load_planning_proposals(year, month):
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    proposals = {}

    for doc in ref.collection("proposals").stream():
        data = doc.to_dict()
        if "planning" not in data:
            continue

        for b in data["planning"]["blocks"]:
            b["start"] = dt.date.fromisoformat(b["start"])
            b["end"] = dt.date.fromisoformat(b["end"])

        data["blocks"] = data["planning"]["blocks"]
        proposals[doc.id] = data

    return proposals


def save_planning_proposal(year, month, index, planning, created_by):
    ref = PROPOSALS.document(f"{year}-{month:02d}")
    ref.set({}, merge=True)

    ref.collection("proposals").document(f"proposal_{index}").set({
        "planning": serialize_planning(planning),
        "created_by": created_by,
        "created_at": dt.datetime.utcnow().isoformat(),
        "status": "PROPOSED",
        "votes": {},
    })


def vote_planning(year, month, proposal_id, email, vote):
    PROPOSALS.document(f"{year}-{month:02d}") \
        .collection("proposals") \
        .document(proposal_id) \
        .update({f"votes.{email}": vote})


def validate_planning(year, month, proposal_id):
    col = PROPOSALS.document(f"{year}-{month:02d}").collection("proposals")
    for doc in col.stream():
        col.document(doc.id).update({"status": "REJECTED"})
    col.document(proposal_id).update({"status": "VALIDATED"})