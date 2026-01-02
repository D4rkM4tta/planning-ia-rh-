import firebase_admin
from firebase_admin import credentials, auth, firestore
import streamlit as st
import json

# ================= FIREBASE INIT =================
if not firebase_admin._apps:
    # Charger la clé depuis Streamlit Secrets
    firebase_key_dict = json.loads(st.secrets["firebase_key"])
    cred = credentials.Certificate(firebase_key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()
USERS = db.collection("users")
LOCKS = db.collection("planning_locks")
PLANNINGS = db.collection("plannings")


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

    email = auth_user.get("email")
    doc = USERS.document(email).get()

    if not doc.exists:
        return False

    return bool(doc.to_dict().get("admin", False))


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


# ================= USERS =================
def get_all_users():
    return {d.id: d.to_dict() for d in USERS.stream()}


# ================= PLANNING LOCK =================
def is_planning_locked(year, month):
    doc = LOCKS.document(f"{year}_{month}").get()
    return doc.exists


def lock_planning(year, month, planning_data):
    LOCKS.document(f"{year}_{month}").set({"locked": True})
    PLANNINGS.document(f"{year}_{month}").set(planning_data)


def load_locked_planning(year, month):
    doc = PLANNINGS.document(f"{year}_{month}").get()
    return doc.to_dict() if doc.exists else None