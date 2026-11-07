import pytest

from civilai import create_app
from civilai.extensions import db
from civilai.models import AuthorityComplaint, Category, Complaint, User
from civilai.services import classify_text


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False,
    })
    yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    client.get("/login")
    return client


def csrf(client):
    with client.session_transaction() as session:
        return session["csrf_token"]


def test_demo_password_is_hashed_and_login_works(client):
    with client.application.app_context():
        user = User.query.filter_by(email="citizen@civilai.local").first()
        assert user.password_hash != "Citizen123!"
        assert user.check_password("Citizen123!")
    token = csrf(client)
    response = client.post("/login", data={"csrf_token": token, "email": "citizen@civilai.local", "password": "Citizen123!"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_admin_login_requires_admin_role_and_opens_control_room(client):
    token = csrf(client)
    citizen_attempt = client.post("/admin/login", data={"csrf_token": token, "email": "citizen@civilai.local", "password": "Citizen123!"})
    assert citizen_attempt.status_code == 200
    assert b"active administrator account" in citizen_attempt.data
    token = csrf(client)
    admin_attempt = client.post("/admin/login", data={"csrf_token": token, "email": "a95381718@gmail.com", "password": "anand@9762"})
    assert admin_attempt.status_code == 302
    assert admin_attempt.headers["Location"].endswith("/admin")


def test_admin_can_change_password_when_signed_in(client):
    token = csrf(client)
    login = client.post("/admin/login", data={"csrf_token": token, "email": "a95381718@gmail.com", "password": "anand@9762"})
    assert login.status_code == 302
    token = csrf(client)
    changed = client.post("/admin/account/password", data={
        "csrf_token": token,
        "current_password": "anand@9762",
        "new_password": "NewAdminPass123!",
        "confirm_password": "NewAdminPass123!",
    })
    assert changed.status_code == 302
    with client.application.app_context():
        assert User.query.filter_by(email="a95381718@gmail.com").first().check_password("NewAdminPass123!")


def test_admin_security_word_recovers_password(client):
    token = csrf(client)
    response = client.post("/admin/verify-security", data={
        "csrf_token": token,
        "email": "a95381718@gmail.com",
        "security_word": "KRISHNA",
        "new_password": "RecoveredAdmin123!",
        "confirm_password": "RecoveredAdmin123!",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")


def test_rule_classifier_routes_pothole_and_handles_unknown():
    result = classify_text("Unsafe lane", "A deep pothole is blocking the lane outside school.")
    assert result["category"] == "Road damage and potholes"
    assert result["department"] == "Road maintenance"
    unknown = classify_text("Something strange", "This description has no route words.")
    assert unknown["matched"] is False


def test_complaint_accepts_short_descriptive_title(client):
    token = csrf(client)
    client.post("/login", data={"csrf_token": token, "email": "citizen@civilai.local", "password": "Citizen123!"})
    token = csrf(client)
    response = client.post("/complaints/new", data={
        "csrf_token": token,
        "title": "pothole",
        "description": "A deep pothole is blocking the lane outside the school.",
        "address": "14th Cross, near the school",
        "area": "Jayanagar",
        "category_id": "1",
        "reviewed": "yes",
    })
    assert response.status_code == 302
    assert "/complaints/" in response.headers["Location"]


def test_civic_assistant_returns_solution_and_complaint_route(client):
    token = csrf(client)
    client.post("/login", data={"csrf_token": token, "email": "citizen@civilai.local", "password": "Citizen123!"})
    token = csrf(client)
    response = client.post("/api/civic-assistant", json={"message": "There is a pothole outside the library"}, headers={"X-CSRFToken": token})
    assert response.status_code == 200
    assert response.json["needs_complaint"] is True
    assert response.json["suggested_category"] == "Road damage and potholes"
    assert response.json["complaint_url"].endswith("/complaints/new")
    private = client.post("/api/civic-assistant", json={"message": "My wifi is not working"}, headers={"X-CSRFToken": token})
    assert private.status_code == 200
    assert private.json["needs_complaint"] is False


def test_authority_receiver_is_idempotent(client):
    payload = {
        "source_public_id": "CIV-TEST-001",
        "idempotency_key": "idem-test-001",
        "title": "Streetlight out",
        "description": "The public light is out.",
        "category": "Streetlight faults",
        "department": "Electrical maintenance",
        "address": "Test Road",
    }
    headers = {"Authorization": "Bearer demo-authority-token"}
    first = client.post("/mock-authority/api/complaints", json=payload, headers=headers)
    second = client.post("/mock-authority/api/complaints", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json["authority_reference"] == second.json["authority_reference"]
    with client.application.app_context():
        assert AuthorityComplaint.query.count() == 2  # fixture demo + submitted test record


def test_citizen_cannot_open_admin_or_other_user_records(client):
    with client.application.app_context():
        other = User(name="Other Citizen", email="other@civilai.local", role="CITIZEN")
        other.set_password("Other123!")
        db.session.add(other)
        db.session.flush()
        category = Category.query.first()
        db.session.add(Complaint(public_id="CIV-OTHER-001", user_id=other.id, title="Private case", original_description="Private case details", final_description="Private case details", category_id=category.id, department_id=category.default_department_id, address="Private Road", idempotency_key="private-test-key"))
        db.session.commit()
    token = csrf(client)
    client.post("/login", data={"csrf_token": token, "email": "citizen@civilai.local", "password": "Citizen123!"})
    assert client.get("/admin").status_code == 302
    assert client.get("/complaints/CIV-OTHER-001").status_code == 302
