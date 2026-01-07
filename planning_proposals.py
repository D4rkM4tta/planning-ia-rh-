import datetime as dt
from firebase_client import db

# ============================================================
# OUTILS DE SERIALISATION (OBLIGATOIRE POUR FIRESTORE)
# ============================================================

def serialize_blocks(blocks):
    return [{
        "id": b["id"],
        "type": b["type"],
        "start": b["start"].isoformat(),
        "end": b["end"].isoformat(),
        "days": b["days"],
        "assigned_to": b["assigned_to"],
    } for b in blocks]


def deserialize_blocks(blocks):
    restored = []
    for b in blocks:
        restored.append({
            "id": b["id"],
            "type": b["type"],
            "start": dt.date.fromisoformat(b["start"]),
            "end": dt.date.fromisoformat(b["end"]),
            "days": b["days"],
            "assigned_to": b["assigned_to"],
        })
    return restored


# ============================================================
# FIRESTORE — PROPOSITIONS DE PLANNING
# ============================================================

def _ref(year: int, month: int):
    return db.collection("planning_proposals").document(f"{year}-{month:02d}")


# ------------------------------------------------------------
# SAUVEGARDE D’UNE PROPOSITION
# ------------------------------------------------------------
def save_planning_proposal(year, month, index, planning, created_by):
    ref = _ref(year, month)

    ref.collection("items").document(f"proposal_{index}").set({
        "blocks": serialize_blocks(planning["blocks"]),
        "created_by": created_by,
        "created_at": dt.datetime.utcnow().isoformat(),
        "status": "PROPOSED",   # PROPOSED | VALIDATED | REJECTED
        "votes": {},            # email -> True / False
    })


# ------------------------------------------------------------
# CHARGEMENT DES PROPOSITIONS
# ------------------------------------------------------------
def load_planning_proposals(year, month):
    ref = _ref(year, month)
    proposals = {}

    for doc in ref.collection("items").stream():
        data = doc.to_dict()
        data["blocks"] = deserialize_blocks(data["blocks"])
        proposals[doc.id] = data

    return proposals


# ------------------------------------------------------------
# VOTE UTILISATEUR
# ------------------------------------------------------------
def vote_planning(year, month, proposal_id, email, vote: bool):
    _ref(year, month) \
        .collection("items") \
        .document(proposal_id) \
        .update({f"votes.{email}": vote})


# ------------------------------------------------------------
# VALIDATION ADMIN (UN SEUL GAGNANT)
# ------------------------------------------------------------
def validate_planning(year, month, proposal_id):
    col = _ref(year, month).collection("items")

    # Tous rejetés
    for doc in col.stream():
        col.document(doc.id).update({"status": "REJECTED"})

    # Celui validé
    col.document(proposal_id).update({"status": "VALIDATED"})