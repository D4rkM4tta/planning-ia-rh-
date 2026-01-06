import firebase_admin
from firebase_admin import credentials, auth, firestore
import streamlit as st

# ================= FIREBASE INIT =================
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

db = firestore.client()

USERS = db.collection("users")
LOCKS = db.collection("planning_locks")
FORCED = db.collection("forced_assignments")


# ================= AUTH =================
def login_user(email, password):
    try:
        user = auth.get_user_by_email(email)
        st.session_state.auth_user = {
            "uid": user.uid,
            "email": email
        }
        return True
    except Exception:
        return False


def logout_user():
    st.session_state.auth_user = None


def is_admin():
    auth_user = st.session_state.get("auth_user")
    if not auth_user:
        return False

    doc = USERS.document(auth_user["email"]).get()
    return bool(doc.exists and doc.to_dict().get("admin", False))


# ================= USERS =================
def get_all_users():
    return {d.id: d.to_dict() for d in USERS.stream()}


# ================= AVAILABILITÉS =================
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


# ================= FORÇAGE ADMIN =================
def load_forced_assignments(year, month):
    doc = FORCED.document(f"{year}_{month}").get()
    return doc.to_dict() if doc.exists else {}


def save_forced_assignment(year, month, day_iso, email):
    FORCED.document(f"{year}_{month}").set(
        {day_iso: email},
        merge=True
    )


# ================= PLANNING LOCK =================
def is_planning_locked(year, month):
    return LOCKS.document(f"{year}_{month}").get().exists


def lock_planning(year, month, planning_data, hours_by_user):
    LOCKS.document(f"{year}_{month}").set({"locked": True})