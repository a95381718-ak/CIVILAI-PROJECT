import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_

from .extensions import db
from .models import Attachment, AuthorityComplaint, AuthorityStatusHistory, Category, Complaint, ComplaintStatusHistory, Department, Submission, User, utcnow
from .services import AUTHORITY_TRANSITIONS, STATUS_LABELS, accept_authority_payload, civic_assistant, classify_text, get_or_create_category, save_upload, set_admin_security_word, submit_to_authority, verify_admin_security_word

main_bp = Blueprint("main", __name__)
auth_bp = Blueprint("auth", __name__)
citizen_bp = Blueprint("citizen", __name__)
admin_bp = Blueprint("admin", __name__)
authority_bp = Blueprint("authority", __name__)
receiver_bp = Blueprint("receiver", __name__)


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("This desk is restricted to an authorized role.", "error")
                return redirect(url_for("main.index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def owns_complaint(public_id):
    complaint = Complaint.query.filter_by(public_id=public_id).first_or_404()
    if current_user.role == "CITIZEN" and complaint.user_id != current_user.id:
        return None
    return complaint


def format_datetime(value):
    return value.strftime("%d %b %Y · %H:%M") if value else "—"


@main_bp.get("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "ADMIN":
            return redirect(url_for("admin.overview"))
        if current_user.role == "AUTHORITY":
            return redirect(url_for("authority.overview"))
        return redirect(url_for("citizen.dashboard"))
    return render_template("auth/login.html", landing=True)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.is_active and user.check_password(password):
            login_user(user, remember=False)
            flash(f"Good to see you, {user.name.split()[0]}.", "success")
            return redirect(url_for("main.index"))
        flash("That email and password combination was not recognised.", "error")
    return render_template("auth/login.html")


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated and current_user.role == "ADMIN":
        return redirect(url_for("admin.overview"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.is_active and user.role == "ADMIN" and user.check_password(password):
            logout_user()
            login_user(user, remember=False)
            flash(f"Control room ready, {user.name.split()[0]}.", "success")
            return redirect(url_for("admin.overview"))
        if user and user.is_active and user.role == "ADMIN":
            flash("Password not recognised. Use your security word to create a new one.", "notice")
            return redirect(url_for("auth.admin_verify_security", email=user.email))
        flash("Use an active administrator account to enter the control room.", "error")
    return render_template("auth/admin_login.html")


@auth_bp.route("/admin/forgot-password", methods=["GET", "POST"])
def admin_forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter(func.lower(User.email) == email, User.role == "ADMIN", User.is_active.is_(True)).first()
        if user:
            flash("Enter your security word to continue.", "notice")
        else:
            flash("If that administrator account exists, recovery can continue with its security word.", "notice")
        return redirect(url_for("auth.admin_verify_security", email=email))
    return render_template("auth/admin_forgot_password.html")


@auth_bp.route("/admin/verify-security", methods=["GET", "POST"])
def admin_verify_security():
    email = (request.values.get("email") or "").strip().lower()
    if request.method == "POST":
        user = User.query.filter(func.lower(User.email) == email, User.role == "ADMIN", User.is_active.is_(True)).first()
        new_password = request.form.get("new_password") or ""
        confirmation = request.form.get("confirm_password") or ""
        if not user or not verify_admin_security_word(user, request.form.get("security_word")):
            flash("That security word is incorrect or temporarily locked after too many attempts.", "error")
        elif len(new_password) < 10:
            flash("Use a new password with at least 10 characters.", "error")
        elif new_password != confirmation:
            flash("The new password and confirmation do not match.", "error")
        else:
            user.set_password(new_password)
            db.session.commit()
            login_user(user, remember=False)
            flash("Your administrator password has been changed.", "success")
            return redirect(url_for("admin.overview"))
    return render_template("auth/admin_verify_security.html", email=email)


@admin_bp.route("/admin/account/password", methods=["GET", "POST"])
@role_required("ADMIN")
def admin_change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirmation = request.form.get("confirm_password") or ""
        if not current_user.check_password(current_password):
            flash("Your current password is incorrect.", "error")
        elif len(new_password) < 10:
            flash("Use a new password with at least 10 characters.", "error")
        elif new_password != confirmation:
            flash("The new password and confirmation do not match.", "error")
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash("Your administrator password has been changed.", "success")
            return redirect(url_for("admin.overview"))
    return render_template("admin/change_password.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if len(name) < 2 or "@" not in email:
            flash("Add your name and a valid email address.", "error")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("An account already exists for that email.", "error")
        else:
            user = User(name=name[:120], email=email[:180], role="CITIZEN")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Your citizen desk is ready.", "success")
            return redirect(url_for("citizen.dashboard"))
    return render_template("auth/register.html")


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "notice")
    return redirect(url_for("auth.login"))


@citizen_bp.get("/dashboard")
@role_required("CITIZEN")
def dashboard():
    query = Complaint.query.filter_by(user_id=current_user.id)
    total = query.count()
    awaiting = query.filter(Complaint.internal_state.in_(["DRAFT", "READY", "SUBMITTING", "SUBMISSION_FAILED"])).count()
    resolved = query.filter_by(authority_status="RESOLVED").count()
    recent = query.order_by(Complaint.updated_at.desc()).limit(4).all()
    return render_template("citizen/dashboard.html", total=total, awaiting=awaiting, resolved=resolved, recent=recent, status_labels=STATUS_LABELS)


@citizen_bp.route("/complaints/new", methods=["GET", "POST"])
@role_required("CITIZEN")
def new_complaint():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        address = (request.form.get("address") or "").strip()
        area = (request.form.get("area") or "").strip()
        category_id = request.form.get("category_id")
        reviewed = request.form.get("reviewed") == "yes"
        missing = []
        if not title or len(title) < 3:
            missing.append("a short complaint title")
        if not description or len(description) < 30:
            missing.append("a description of at least 30 characters")
        if not address:
            missing.append("the problem location")
        if not category_id:
            missing.append("a problem category")
        if not reviewed:
            missing.append("the review confirmation")
        if missing:
            flash("Before saving, add " + ", ".join(missing[:-1]) + (" and " if len(missing) > 1 else "") + missing[-1] + ".", "error")
            return render_template("citizen/new_complaint.html", categories=categories, form=request.form)
        category = db.session.get(Category, int(category_id))
        if not category:
            flash("Choose a valid category from the list.", "error")
            return render_template("citizen/new_complaint.html", categories=categories, form=request.form)
        try:
            latitude = float(request.form.get("latitude")) if request.form.get("latitude") else None
            longitude = float(request.form.get("longitude")) if request.form.get("longitude") else None
        except ValueError:
            latitude = longitude = None
        complaint = Complaint(
            public_id=f"CIV-{datetime.now(timezone.utc).strftime('%y%m')}-{secrets.token_hex(3).upper()}",
            user_id=current_user.id,
            title=title[:180],
            original_description=description,
            final_description=description,
            category_id=category.id,
            department_id=category.default_department_id,
            address=address[:250],
            area=area[:120],
            latitude=latitude,
            longitude=longitude,
            internal_state="READY",
            idempotency_key=secrets.token_urlsafe(32),
            reviewed_at=utcnow(),
        )
        db.session.add(complaint)
        db.session.flush()
        db.session.add(ComplaintStatusHistory(complaint_id=complaint.id, new_status="READY", changed_by=current_user.id, note="Citizen reviewed the complaint details."))
        for uploaded in request.files.getlist("attachments"):
            if uploaded and uploaded.filename:
                try:
                    saved = save_upload(uploaded, current_app.config["UPLOAD_FOLDER"], current_app.config["MAX_CONTENT_LENGTH"])
                    db.session.add(Attachment(complaint_id=complaint.id, uploaded_by=current_user.id, **saved))
                except ValueError as error:
                    db.session.rollback()
                    flash(str(error), "error")
                    return render_template("citizen/new_complaint.html", categories=categories, form=request.form)
        db.session.commit()
        flash("Complaint saved to your desk. It is ready for explicit submission.", "success")
        return redirect(url_for("citizen.complaint_detail", public_id=complaint.public_id))
    return render_template("citizen/new_complaint.html", categories=categories, form={})


@citizen_bp.post("/api/complaints/analyze")
@role_required("CITIZEN")
def analyze():
    payload = request.get_json(silent=True) or {}
    return jsonify(classify_text(payload.get("title"), payload.get("description")))


@citizen_bp.post("/api/civic-assistant")
@role_required("CITIZEN")
def civic_assistant_api():
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if len(message) > 1200:
        return jsonify({"success": False, "message": "Keep the message under 1200 characters."}), 400
    answer = civic_assistant(message)
    answer["success"] = True
    answer["complaint_url"] = url_for("citizen.new_complaint") if answer["needs_complaint"] else None
    return jsonify(answer)


@citizen_bp.get("/complaints")
@role_required("CITIZEN")
def complaints():
    query = Complaint.query.filter_by(user_id=current_user.id)
    status = request.args.get("status")
    if status:
        query = query.filter(or_(Complaint.internal_state == status, Complaint.authority_status == status))
    records = query.order_by(Complaint.updated_at.desc()).all()
    return render_template("citizen/complaints.html", complaints=records, status_labels=STATUS_LABELS, selected_status=status)


@citizen_bp.get("/complaints/<public_id>")
@login_required
def complaint_detail(public_id):
    complaint = owns_complaint(public_id)
    if not complaint:
        flash("That complaint is not available from this desk.", "error")
        return redirect(url_for("citizen.complaints"))
    return render_template("citizen/complaint_detail.html", complaint=complaint, status_labels=STATUS_LABELS)


@citizen_bp.post("/complaints/<public_id>/submit")
@role_required("CITIZEN")
def submit_complaint(public_id):
    complaint = owns_complaint(public_id)
    if not complaint:
        return redirect(url_for("citizen.complaints"))
    if complaint.internal_state == "SUBMITTED":
        flash("This complaint already has an authority acknowledgement.", "notice")
        return redirect(url_for("citizen.complaint_receipt", public_id=public_id))
    attempt_number = len(complaint.submissions) + 1
    submission = Submission(complaint_id=complaint.id, idempotency_key=complaint.idempotency_key, attempt_number=attempt_number, state="SUBMITTING")
    complaint.internal_state = "SUBMITTING"
    db.session.add(submission)
    db.session.commit()
    code, data = submit_to_authority(complaint, current_app)
    if data.get("success"):
        complaint.internal_state = "SUBMITTED"
        complaint.authority_reference = data.get("authority_reference")
        complaint.authority_status = data.get("status", "RECEIVED")
        complaint.authority_received_at = datetime.fromisoformat(data["received_at"])
        submission.state = "ACCEPTED"
        submission.authority_reference = complaint.authority_reference
        submission.response_status_code = code
        submission.completed_at = utcnow()
        db.session.add(ComplaintStatusHistory(complaint_id=complaint.id, previous_status="SUBMITTING", new_status="SUBMITTED", changed_by=current_user.id, note="Authority acknowledgement received."))
        db.session.commit()
        flash("The simulated authority has acknowledged your complaint.", "success")
        return redirect(url_for("citizen.complaint_receipt", public_id=public_id))
    complaint.internal_state = "SUBMISSION_FAILED"
    submission.state = "FAILED"
    submission.response_status_code = code
    submission.error_details = (data.get("message") or "Receiver did not acknowledge the complaint.")[:300]
    submission.completed_at = utcnow()
    db.session.add(ComplaintStatusHistory(complaint_id=complaint.id, previous_status="SUBMITTING", new_status="SUBMISSION_FAILED", changed_by=current_user.id, note=submission.error_details))
    db.session.commit()
    flash("The complaint is saved, but the simulated authority has not accepted it yet. You can retry safely.", "error")
    return redirect(url_for("citizen.complaint_detail", public_id=public_id))


@citizen_bp.post("/complaints/<public_id>/retry")
@role_required("CITIZEN")
def retry_complaint(public_id):
    return submit_complaint(public_id)


@citizen_bp.get("/complaints/<public_id>/receipt")
@role_required("CITIZEN")
def complaint_receipt(public_id):
    complaint = owns_complaint(public_id)
    if not complaint or complaint.internal_state != "SUBMITTED":
        flash("A receipt is available only after the simulated authority accepts the complaint.", "error")
        return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    return render_template("citizen/receipt.html", complaint=complaint)


@admin_bp.get("/admin")
@role_required("ADMIN")
def overview():
    return render_template("admin/overview.html", total=Complaint.query.count(), submitted=Complaint.query.filter_by(internal_state="SUBMITTED").count(), failed=Complaint.query.filter_by(internal_state="SUBMISSION_FAILED").count(), authority_total=AuthorityComplaint.query.count(), departments=Department.query.order_by(Department.name).all(), categories=Category.query.order_by(Category.name).all(), recent=Complaint.query.order_by(Complaint.updated_at.desc()).limit(8).all(), status_labels=STATUS_LABELS)


@authority_bp.get("/authority")
@role_required("AUTHORITY", "ADMIN")
def overview_authority():
    records = AuthorityComplaint.query.order_by(AuthorityComplaint.updated_at.desc()).all()
    counts = {status: AuthorityComplaint.query.filter_by(current_status=status).count() for status in ["RECEIVED", "UNDER_REVIEW", "IN_PROGRESS", "RESOLVED"]}
    return render_template("authority/overview.html", records=records, counts=counts, status_labels=STATUS_LABELS)


@authority_bp.post("/authority/complaints/<reference>/status")
@role_required("AUTHORITY", "ADMIN")
def update_authority_status(reference):
    record = AuthorityComplaint.query.filter_by(authority_reference=reference).first_or_404()
    new_status = (request.form.get("status") or "").strip()
    if new_status not in AUTHORITY_TRANSITIONS.get(record.current_status, set()):
        flash(f"{record.current_status.replace('_', ' ').title()} cannot move directly to {new_status.replace('_', ' ').title()}.", "error")
        return redirect(url_for("authority.overview"))
    previous = record.current_status
    record.current_status = new_status
    record.updated_at = utcnow()
    db.session.add(AuthorityStatusHistory(authority_complaint_id=record.id, previous_status=previous, new_status=new_status, changed_by=current_user.id, note="Status updated by receiving desk."))
    complaint = Complaint.query.filter_by(public_id=record.source_public_id).first()
    if complaint:
        complaint.authority_status = new_status
        db.session.add(ComplaintStatusHistory(complaint_id=complaint.id, previous_status=previous, new_status=new_status, changed_by=current_user.id, note="Authority status synchronized."))
    db.session.commit()
    flash(f"Authority status updated to {new_status.replace('_', ' ').title()}.", "success")
    return redirect(url_for("authority.overview"))


@receiver_bp.post("/mock-authority/api/complaints")
def receive_complaint():
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {current_app.config['AUTHORITY_API_TOKEN']}"
    if auth != expected:
        return jsonify({"success": False, "message": "Internal integration authentication failed."}), 401
    payload = request.get_json(silent=True) or {}
    _, response, code = accept_authority_payload(payload)
    return jsonify(response), code
