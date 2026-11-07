import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from .extensions import db
from .models import AdminRecoveryCode, AuthorityComplaint, AuthorityStatusHistory, Category, Department, User, utcnow


RULES = [
    {"category": "Road damage and potholes", "department": "Road maintenance", "keywords": ["pothole", "potholes", "road damage", "broken road", "crater", "asphalt"], "explanation": "The description contains road-surface language.", "strength": 0.94},
    {"category": "Garbage collection and sanitation", "department": "Sanitation", "keywords": ["garbage", "waste", "uncollected", "dump", "litter", "sanitation"], "explanation": "The description points to waste or collection service.", "strength": 0.92},
    {"category": "Streetlight faults", "department": "Electrical maintenance", "keywords": ["streetlight", "street light", "lamp", "dark road", "light pole", "bulb"], "explanation": "The description contains public-lighting language.", "strength": 0.91},
    {"category": "Water leakage", "department": "Water services", "keywords": ["leak", "leaking", "water pipe", "burst pipe", "water flowing", "pipeline"], "explanation": "The description points to a water-network issue.", "strength": 0.93},
    {"category": "Drainage and sewage", "department": "Drainage services", "keywords": ["drain", "sewage", "sewer", "overflow", "blocked drain", "flooding"], "explanation": "The description contains drainage or sewage language.", "strength": 0.9},
    {"category": "Public-area maintenance", "department": "Public works", "keywords": ["park", "footpath", "bench", "playground", "public toilet", "open space"], "explanation": "The description points to a public-area maintenance issue.", "strength": 0.83},
]


def normalize(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def classify_text(title, description):
    text = normalize(f"{title} {description}")
    best = None
    best_hits = []
    for rule in RULES:
        hits = [keyword for keyword in rule["keywords"] if normalize(keyword) in text]
        if len(hits) > len(best_hits):
            best = rule
            best_hits = hits
    if not best or not best_hits:
        return {"matched": False, "category": "Other or unclassified", "department": "Manual routing", "explanation": "No confident rule match. Choose a category manually before saving.", "strength": 0.0, "hits": []}
    return {"matched": True, "category": best["category"], "department": best["department"], "explanation": best["explanation"], "strength": best["strength"], "hits": best_hits}


def civic_assistant(message):
    """Return safe, topic-specific guidance without inventing authority actions."""
    text = normalize(message)
    if not text:
        return {
            "intent": "needs_context",
            "reply": "Tell me what is happening and where it is happening. For example: ‘There is a pothole outside the library.’",
            "solution": "Add the issue, its location, and how long it has been affecting people.",
            "needs_complaint": False,
            "suggested_category": None,
            "department": None,
            "complaint_prompt": "",
        }

    personal_markers = ["inside my house", "my wifi", "my internet", "my appliance", "my phone", "my laptop"]
    if any(marker in text for marker in personal_markers):
        return {
            "intent": "private_issue",
            "reply": "That sounds like a private household or device issue rather than a civic-service case.",
            "solution": "Try the service provider’s support or a qualified technician. CIVILAI can help with public roads, lighting, sanitation, water, drainage, and shared spaces.",
            "needs_complaint": False,
            "suggested_category": None,
            "department": None,
            "complaint_prompt": "",
        }

    result = classify_text("", text)
    guidance = {
        "Road damage and potholes": ("Keep a safe distance from the damaged section and warn others only if it is safe to do so.", "Road damage that creates a traffic or injury risk should be reported so the road desk can inspect it."),
        "Garbage collection and sanitation": ("Keep household waste sealed and separate sharp or hazardous items. Do not burn or dump it elsewhere.", "If collection is missed or waste is accumulating in a public area, file a complaint with the location and a photo if available."),
        "Streetlight faults": ("Use a lit alternative route after dark and avoid stopping beneath damaged poles or exposed wiring.", "A failed public light needs an electrical maintenance inspection. Report the pole or nearest landmark."),
        "Water leakage": ("Avoid contact with standing water and keep children away from the leak. If it is on your property, close the local valve if safe.", "A public pipe leak should be reported quickly because it can damage roads and interrupt supply."),
        "Drainage and sewage": ("Do not walk or drive through moving or contaminated water. Keep drains and manholes clear from a safe distance.", "Overflowing drains, sewage, and flooding need an authority response. Include the nearest landmark and whether access is blocked."),
        "Public-area maintenance": ("Use another entrance or shared space if there is a safety risk, and avoid damaged play equipment or structures.", "A damaged park, footpath, bench, toilet, or shared facility should be reported for inspection."),
    }
    if result["matched"]:
        solution, complaint_prompt = guidance[result["category"]]
        return {
            "intent": "civic_issue",
            "reply": f"This sounds like {result['category'].lower()}.",
            "solution": solution,
            "needs_complaint": True,
            "suggested_category": result["category"],
            "department": result["department"],
            "complaint_prompt": complaint_prompt,
        }
    return {
        "intent": "unknown_civic_issue",
        "reply": "I could not confidently match that to a civic-service topic yet.",
        "solution": "Add the public place, the visible problem, and who is affected. Do not include passwords, ID numbers, or other sensitive details.",
        "needs_complaint": True,
        "suggested_category": "Other or unclassified",
        "department": "Manual routing",
        "complaint_prompt": "If this is a public issue that needs someone to inspect or repair it, register a complaint and the civic desk can route it manually.",
    }


def set_admin_security_word(user, word):
    """Persist the admin recovery word as a hash; never store the original word."""
    AdminRecoveryCode.query.filter_by(user_id=user.id).delete()
    recovery = AdminRecoveryCode(
        user_id=user.id,
        code_hash=generate_password_hash((word or "").strip().upper()),
        expires_at=datetime(9999, 12, 31, tzinfo=timezone.utc),
    )
    db.session.add(recovery)
    db.session.commit()


def verify_admin_security_word(user, word):
    recovery = AdminRecoveryCode.query.filter_by(user_id=user.id, consumed_at=None).order_by(AdminRecoveryCode.created_at.desc()).first()
    if not recovery:
        return False
    if recovery.attempts >= 5 and (utcnow() - recovery.created_at).total_seconds() < 900:
        return False
    if recovery.attempts >= 5:
        recovery.attempts = 0
    valid = check_password_hash(recovery.code_hash, (word or "").strip().upper())
    recovery.attempts = 0 if valid else recovery.attempts + 1
    db.session.commit()
    return valid


def get_or_create_category(category_name, department_name):
    department = Department.query.filter_by(name=department_name).first()
    if not department:
        department = Department(name=department_name, description=f"Responsible desk for {department_name.lower()} cases.")
        db.session.add(department)
        db.session.flush()
    category = Category.query.filter_by(name=category_name).first()
    if not category:
        category = Category(name=category_name, description=f"Configurable demonstration category for {category_name.lower()}.", department=department)
        db.session.add(category)
        db.session.flush()
    return category, department


def save_upload(file_storage, upload_root, max_bytes):
    if not file_storage or not file_storage.filename:
        return None
    allowed = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "pdf": "application/pdf", "webp": "image/webp"}
    original = file_storage.filename
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in allowed:
        raise ValueError("Only PNG, JPG, WEBP, and PDF attachments are supported.")
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > max_bytes:
        raise ValueError(f"Attachments must be smaller than {max_bytes // (1024 * 1024)} MB.")
    if file_storage.mimetype and file_storage.mimetype != allowed[extension]:
        raise ValueError("The attachment content type does not match its file extension.")
    safe = secure_filename(original) or f"attachment.{extension}"
    storage_key = f"{uuid.uuid4().hex}_{safe}"
    Path(upload_root).mkdir(parents=True, exist_ok=True)
    file_storage.save(Path(upload_root) / storage_key)
    return {"original_filename": original, "storage_key": storage_key, "content_type": allowed[extension], "size_bytes": size}


def submit_to_authority(complaint, app):
    """Submit over HTTP to the separate in-process receiver endpoint."""
    port = os.getenv("PORT", "3000")
    base = os.getenv("AUTHORITY_BASE_URL", f"http://127.0.0.1:{port}")
    payload = {
        "source_public_id": complaint.public_id,
        "idempotency_key": complaint.idempotency_key,
        "title": complaint.title,
        "description": complaint.final_description,
        "category": complaint.category.name,
        "department": complaint.department.name,
        "address": complaint.address,
        "area": complaint.area,
        "latitude": complaint.latitude,
        "longitude": complaint.longitude,
    }
    try:
        response = requests.post(
            f"{base}/mock-authority/api/complaints",
            json=payload,
            headers={"Authorization": f"Bearer {app.config['AUTHORITY_API_TOKEN']}"},
            timeout=3,
        )
        data = response.json()
        return response.status_code, data
    except (requests.RequestException, ValueError) as exc:
        return 503, {"success": False, "message": "The simulated authority receiver is temporarily unavailable.", "error": str(exc)[:120]}


def accept_authority_payload(payload):
    required = ["source_public_id", "idempotency_key", "title", "description", "category", "department", "address"]
    missing = [field for field in required if not normalize(payload.get(field))]
    if missing:
        return None, {"success": False, "message": f"Missing required fields: {', '.join(missing)}."}, 400
    existing = AuthorityComplaint.query.filter_by(idempotency_key=payload["idempotency_key"]).first()
    if existing:
        return existing, {"success": True, "authority_reference": existing.authority_reference, "status": existing.current_status, "received_at": existing.received_at.isoformat(), "message": "Existing acknowledgement returned for this idempotent submission."}, 200
    year = datetime.now(timezone.utc).year
    sequence = AuthorityComplaint.query.count() + 1
    reference = f"AUTH-{year}-{sequence:06d}"
    record = AuthorityComplaint(
        authority_reference=reference,
        source_public_id=payload["source_public_id"],
        idempotency_key=payload["idempotency_key"],
        title=payload["title"][:180],
        description_snapshot=payload["description"],
        category=payload["category"][:140],
        department=payload["department"][:140],
        address=payload["address"][:250],
        area=(payload.get("area") or "")[:120],
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        current_status="RECEIVED",
    )
    db.session.add(record)
    db.session.flush()
    db.session.add(AuthorityStatusHistory(authority_complaint_id=record.id, new_status="RECEIVED", note="Accepted by simulated authority receiving desk."))
    db.session.commit()
    return record, {"success": True, "authority_reference": reference, "status": "RECEIVED", "received_at": record.received_at.isoformat(), "message": "Complaint received by the simulated authority system."}, 201


STATUS_LABELS = {
    "DRAFT": "Draft",
    "READY": "Ready to submit",
    "SUBMITTING": "Submitting",
    "SUBMITTED": "Accepted by authority",
    "SUBMISSION_FAILED": "Submission needs attention",
    "RECEIVED": "Received",
    "UNDER_REVIEW": "Under review",
    "IN_PROGRESS": "In progress",
    "RESOLVED": "Resolved",
    "REJECTED": "Rejected",
}

AUTHORITY_TRANSITIONS = {"RECEIVED": {"UNDER_REVIEW", "REJECTED"}, "UNDER_REVIEW": {"IN_PROGRESS", "REJECTED"}, "IN_PROGRESS": {"RESOLVED", "REJECTED"}, "REJECTED": {"UNDER_REVIEW"}, "RESOLVED": set()}
