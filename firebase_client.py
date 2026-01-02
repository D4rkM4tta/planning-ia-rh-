import firebase_admin
from firebase_admin import credentials, auth, firestore
import streamlit as st

# 🔐 Initialisation Firebase (une seule fois)
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()
USERS = db.collection("users")


# ================= AUTH =================
def login_user(email, password):
    try:
        user = auth.get_user_by_email(email)
        st.session_state.auth_user = {
            "email": email
        }
        return True
    except Exception:
        return False


def logout_user():
    st.session_state.auth_user = None


def is_admin():
    user = st.session_state.get("auth_user")
    if not user:
        return False

    email = user.get("email")
    doc = USERS.document(email).get()
    if not doc.exists:
        return False

    return bool(doc.to_dict().get("admin", False))


# ================= DISPONIBILITÉS =================
def load_availability(email, year, month):
    doc = USERS.document(email).get()
    if not doc.exists:
        return {}

    key = f"availability_{year}_{month}"
    return doc.to_dict().get(key, {})


def save_availability(email, year, month, availability):
    key = f"availability_{year}_{month}"
    USERS.document(email).set({key: availability}, merge=True)


# ================= ADMIN =================
def get_all_users():
    return {d.id: d.to_dict() for d in USERS.stream()}

def load_planning(year: int, month: int):
    doc_id = f"{year}-{str(month).zfill(2)}"
    doc = firestore.client().collection("planning").document(doc_id).get()

    if not doc.exists:
        return {}

    data = doc.to_dict()
    return data.get("schedule", {})

# -------- PLANNING / VERROUILLAGE -------- #

PLANNINGS = db.collection("plannings")

def is_planning_locked(year, month):
    doc = PLANNINGS.document(f"{year}_{month:02d}").get()
    if not doc.exists:
        return False
    return doc.to_dict().get("status") == "locked"


def lock_planning(year, month, planning_data, hours_by_user):
    PLANNINGS.document(f"{year}_{month:02d}").set({
        "status": "locked",
        "planning": planning_data,
        "hours_by_user": hours_by_user,
        "validated_at": firestore.SERVER_TIMESTAMP
    })


def load_locked_planning(year, month):
    doc = PLANNINGS.document(f"{year}_{month:02d}").get()
    if not doc.exists:
        return None
    return doc.to_dict()