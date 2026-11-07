import hmac
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, send_from_directory, session

from .extensions import db, login_manager
from .models import AdminRecoveryCode, AuthorityComplaint, AuthorityStatusHistory, Category, Complaint, ComplaintStatusHistory, Department, User, utcnow

load_dotenv()


def create_app(test_config=None):
    database_url = os.getenv("DATABASE_URL", "")
    engine_options = {}
    if not database_url:
        database_url = "sqlite:///civilai.db"
    else:
        database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        if database_url.startswith("mysql"):
            parsed = urlsplit(database_url)
            query = parse_qsl(parsed.query, keep_blank_values=True)
            has_ssl_query = any(key in {"ssl", "ssl_ca", "ssl_mode"} for key, _ in query)
            if has_ssl_query:
                query = [(key, value) for key, value in query if key not in {"ssl", "ssl_ca", "ssl_mode"}]
                database_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
                engine_options = {"connect_args": {"ssl": {"check_hostname": False, "verify_mode": "none"}}}
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "civilai-local-development-key"),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTHORITY_API_TOKEN=os.getenv("AUTHORITY_API_TOKEN", "demo-authority-token"),
        ADMIN_EMAIL=os.getenv("ADMIN_EMAIL", "a95381718@gmail.com").strip().lower(),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_UPLOAD_MB", "8")) * 1024 * 1024,
        UPLOAD_FOLDER=str(Path(app.instance_path) / "uploads"),
        SESSION_COOKIE_SAMESITE="None",
        SESSION_COOKIE_SECURE=True,
    )
    if test_config:
        app.config.update(test_config)
        if str(app.config.get("SQLALCHEMY_DATABASE_URI", "")).startswith("sqlite"):
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = test_config.get("SQLALCHEMY_ENGINE_OPTIONS", {})
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Sign in to access your civic desk."
    login_manager.login_message_category = "notice"

    from .routes import admin_bp, authority_bp, auth_bp, citizen_bp, main_bp, receiver_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(citizen_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(authority_bp)
    app.register_blueprint(receiver_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def csrf_guard():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"} or request.path.startswith("/mock-authority/api/"):
            return None
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        expected = session.get("csrf_token")
        if not expected or not token or not hmac.compare_digest(token, expected):
            if request.is_json:
                return jsonify({"success": False, "message": "Your session token is missing or expired."}), 400
            abort(400, description="Your form session expired. Refresh the page and try again.")
        return None

    @app.context_processor
    def inject_globals():
        if "csrf_token" not in session:
            session["csrf_token"] = os.urandom(24).hex()
        return {"csrf_token": session["csrf_token"], "year": 2026}

    @app.get("/healthz")
    def healthz():
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "ok", "service": "civilai", "database": "ok"}
        except Exception:
            db.session.rollback()
            return {"status": "degraded", "service": "civilai", "database": "unavailable"}, 503

    @app.get("/manus-routes.json")
    def route_manifest():
        return send_from_directory(str(Path(app.root_path).parent / "public"), "manus-routes.json")

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", message=getattr(error, "description", "The request could not be completed.")), 400

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()
        seed_data()
    return app


def seed_data():
    department_specs = [
        ("Road maintenance", "Potholes, road-surface damage, and street access."),
        ("Sanitation", "Garbage collection and neighborhood cleanliness."),
        ("Electrical maintenance", "Streetlights and public electrical fixtures."),
        ("Water services", "Water mains, supply, and leakage reports."),
        ("Drainage services", "Drains, sewage, flooding, and overflow."),
        ("Public works", "Parks, footpaths, and shared public areas."),
        ("Manual routing", "Cases needing a human routing decision."),
    ]
    for name, description in department_specs:
        if not Department.query.filter_by(name=name).first():
            db.session.add(Department(name=name, description=description))
    db.session.flush()
    category_specs = [
        ("Road damage and potholes", "Road surface and access issues.", "Road maintenance"),
        ("Garbage collection and sanitation", "Waste collection and sanitation issues.", "Sanitation"),
        ("Streetlight faults", "Public lighting issues.", "Electrical maintenance"),
        ("Water leakage", "Water pipe and leakage issues.", "Water services"),
        ("Drainage and sewage", "Drainage and sewage issues.", "Drainage services"),
        ("Public-area maintenance", "Parks and shared-space issues.", "Public works"),
        ("Other or unclassified", "Cases requiring manual routing.", "Manual routing"),
    ]
    for name, description, department_name in category_specs:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name, description=description, default_department_id=Department.query.filter_by(name=department_name).first().id))
    users = [
        ("Ananya Rao", "citizen@civilai.local", "Citizen123!", "CITIZEN"),
        ("CIVILAI Admin", os.getenv("ADMIN_EMAIL", "a95381718@gmail.com").strip().lower(), "anand@9762", "ADMIN"),
        ("Receiving Desk", "desk@civilai.local", "Authority123!", "AUTHORITY"),
    ]
    admin_email = os.getenv("ADMIN_EMAIL", "a95381718@gmail.com").strip().lower()
    legacy_admin = User.query.filter_by(email="admin@civilai.local").first()
    current_admin = User.query.filter_by(email=admin_email).first()
    if legacy_admin and not current_admin:
        legacy_admin.email = admin_email
    for name, email, password, role in users:
        if not User.query.filter_by(email=email).first():
            user = User(name=name, email=email, role=role)
            user.set_password(password)
            db.session.add(user)
    db.session.commit()
    admin_user = User.query.filter_by(email=admin_email, role="ADMIN").first()
    if admin_user and not AdminRecoveryCode.query.filter_by(user_id=admin_user.id).first():
        db.session.add(AdminRecoveryCode(
            user_id=admin_user.id,
            code_hash="scrypt:32768:8:1$ZdbwmWyd2tc9Uead$269a36e58d3a92780d58ae4dc5f935c3ba4e94d2bc5fd21b217c7f298602bbc7be0c39a3221e1dcdecd6d41419adc3e1a368a285cfa9761b93b23ae5095f8db2",
            expires_at=utcnow().replace(year=9999),
        ))
        db.session.commit()
    citizen = User.query.filter_by(email="citizen@civilai.local").first()
    road_category = Category.query.filter_by(name="Road damage and potholes").first()
    road_department = Department.query.filter_by(name="Road maintenance").first()
    if citizen and road_category and road_department and not Complaint.query.filter_by(public_id="CIV-DEMO-001").first():
        demo = Complaint(
            public_id="CIV-DEMO-001",
            user_id=citizen.id,
            title="Pothole cluster outside the community library",
            original_description="Three deep potholes have formed outside the community library. Two-wheelers are swerving into the bus lane, especially after rain.",
            final_description="Three deep potholes have formed outside the community library. Two-wheelers are swerving into the bus lane, especially after rain.",
            category_id=road_category.id,
            department_id=road_department.id,
            address="18th Main, outside the community library",
            area="Jayanagar",
            internal_state="SUBMITTED",
            authority_status="IN_PROGRESS",
            authority_reference="AUTH-DEMO-001",
            authority_received_at=utcnow(),
            idempotency_key="demo-seed-idempotency",
            reviewed_at=utcnow(),
        )
        db.session.add(demo)
        db.session.flush()
        db.session.add(ComplaintStatusHistory(complaint_id=demo.id, new_status="READY", changed_by=citizen.id, note="Citizen reviewed the complaint details."))
        db.session.add(ComplaintStatusHistory(complaint_id=demo.id, previous_status="READY", new_status="SUBMITTED", changed_by=citizen.id, note="Authority acknowledgement received."))
        authority_demo = AuthorityComplaint(
            authority_reference="AUTH-DEMO-001",
            source_public_id=demo.public_id,
            idempotency_key=demo.idempotency_key,
            title=demo.title,
            description_snapshot=demo.final_description,
            category=road_category.name,
            department=road_department.name,
            address=demo.address,
            area=demo.area,
            current_status="IN_PROGRESS",
        )
        db.session.add(authority_demo)
        db.session.flush()
        db.session.add(AuthorityStatusHistory(authority_complaint_id=authority_demo.id, new_status="RECEIVED", note="Accepted by simulated authority receiving desk."))
        db.session.add(AuthorityStatusHistory(authority_complaint_id=authority_demo.id, previous_status="RECEIVED", new_status="UNDER_REVIEW", note="Receiving desk reviewed the snapshot."))
        db.session.add(AuthorityStatusHistory(authority_complaint_id=authority_demo.id, previous_status="UNDER_REVIEW", new_status="IN_PROGRESS", note="Road maintenance work is in progress."))
        db.session.commit()
