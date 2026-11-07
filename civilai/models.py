from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="CITIZEN")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    complaints = db.relationship("Complaint", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, value):
        self.password_hash = generate_password_hash(value)

    def check_password(self, value):
        return check_password_hash(self.password_hash, value)


class AdminRecoveryCode(db.Model):
    __tablename__ = "admin_recovery_codes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    user = db.relationship("User")


class Department(db.Model):
    __tablename__ = "departments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.String(250), nullable=False, default="")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    categories = db.relationship("Category", back_populates="department")


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), unique=True, nullable=False)
    description = db.Column(db.String(250), nullable=False, default="")
    default_department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    department = db.relationship("Department", back_populates="categories")
    complaints = db.relationship("Complaint", back_populates="category")


class Complaint(db.Model):
    __tablename__ = "complaints"
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    original_description = db.Column(db.Text, nullable=False)
    final_description = db.Column(db.Text, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    address = db.Column(db.String(250), nullable=False)
    area = db.Column(db.String(120), nullable=False, default="")
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    internal_state = db.Column(db.String(30), nullable=False, default="DRAFT", index=True)
    authority_status = db.Column(db.String(30), nullable=True)
    authority_reference = db.Column(db.String(60), nullable=True, index=True)
    authority_received_at = db.Column(db.DateTime(timezone=True), nullable=True)
    idempotency_key = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    user = db.relationship("User", back_populates="complaints")
    category = db.relationship("Category", back_populates="complaints")
    department = db.relationship("Department")
    attachments = db.relationship("Attachment", back_populates="complaint", cascade="all, delete-orphan")
    submissions = db.relationship("Submission", back_populates="complaint", cascade="all, delete-orphan")
    status_history = db.relationship("ComplaintStatusHistory", back_populates="complaint", cascade="all, delete-orphan", order_by="ComplaintStatusHistory.created_at")


class Attachment(db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(120), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    complaint = db.relationship("Complaint", back_populates="attachments")


class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    idempotency_key = db.Column(db.String(80), nullable=False, index=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    state = db.Column(db.String(30), nullable=False)
    authority_reference = db.Column(db.String(60), nullable=True)
    response_status_code = db.Column(db.Integer, nullable=True)
    error_details = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    complaint = db.relationship("Complaint", back_populates="submissions")


class ComplaintStatusHistory(db.Model):
    __tablename__ = "complaint_status_history"
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey("complaints.id"), nullable=False, index=True)
    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    note = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    complaint = db.relationship("Complaint", back_populates="status_history")


class AuthorityComplaint(db.Model):
    __tablename__ = "authority_complaints"
    id = db.Column(db.Integer, primary_key=True)
    authority_reference = db.Column(db.String(60), unique=True, nullable=False, index=True)
    source_public_id = db.Column(db.String(32), nullable=False, index=True)
    idempotency_key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    description_snapshot = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(140), nullable=False)
    department = db.Column(db.String(140), nullable=False)
    address = db.Column(db.String(250), nullable=False)
    area = db.Column(db.String(120), nullable=False, default="")
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    current_status = db.Column(db.String(30), nullable=False, default="RECEIVED", index=True)
    received_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    status_history = db.relationship("AuthorityStatusHistory", back_populates="authority_complaint", cascade="all, delete-orphan", order_by="AuthorityStatusHistory.created_at")


class AuthorityStatusHistory(db.Model):
    __tablename__ = "authority_status_history"
    id = db.Column(db.Integer, primary_key=True)
    authority_complaint_id = db.Column(db.Integer, db.ForeignKey("authority_complaints.id"), nullable=False)
    previous_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    note = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    authority_complaint = db.relationship("AuthorityComplaint", back_populates="status_history")
