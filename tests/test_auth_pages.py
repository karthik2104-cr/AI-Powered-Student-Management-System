"""Separate public pages, registration notices, and the local administrator."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import CREDENTIAL_FILE, bootstrap_admin
from app.database import SessionLocal
from app.main import app
from app.models import AdminNotification, User
from app.security import verify_password
from tests.support import login_admin, remove_test_admin


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _credentials() -> tuple[str, str]:
    assert CREDENTIAL_FILE.exists()
    values = {}
    for line in CREDENTIAL_FILE.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("note"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values["email"], values["password"]


def test_public_pages_keep_login_and_registration_apart(client):
    landing = client.get("/")
    login = client.get("/login")
    register = client.get("/register")
    admin_login = client.get("/admin/login")
    assert landing.status_code == 200
    assert "Student login" in landing.text
    assert "Create student account" in landing.text
    assert "Admin login" in landing.text
    assert 'id="login-form"' not in landing.text
    assert 'id="register-form"' not in login.text
    assert 'id="login-form"' not in register.text
    assert "Administrator login" in admin_login.text
    assert "password_hash" not in landing.text + login.text + admin_login.text

    dashboard = client.get("/admin/dashboard", follow_redirects=False)
    assert dashboard.status_code == 303
    assert dashboard.headers["location"] == "/admin/login"
    old_page = client.get("/app", follow_redirects=False)
    assert old_page.status_code == 303
    assert old_page.headers["location"] == "/"


def test_registration_creates_one_notification_without_secrets(client):
    health = client.get("/health")
    if health.json().get("academic_records") != "ready":
        pytest.skip(health.json().get("detail"))
    login_admin(client)
    suffix = uuid4().hex[:8]
    admission = f"NOTE{suffix}"
    email = f"notice-{suffix}@example.edu"
    payload = {
        "full_name": "Notice Student",
        "admission_number": admission,
        "email": email,
        "password": "student-pass-1",
        "password_confirmation": "student-pass-1",
        "department": "History",
        "year_or_semester": "1",
        "role": "admin",
    }
    created = client.post("/auth/register", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "student"
    assert "password" not in body
    assert "password_hash" not in created.text
    student_id = body["student_id"]

    notices = [row for row in client.get("/notifications").json() if row["student_id"] == student_id]
    assert len(notices) == 1
    notice = notices[0]
    assert notice["full_name"] == "Notice Student"
    assert notice["email"] == email
    assert notice["admission_number"] == admission
    assert notice["department"] == "Computer Science"
    assert notice["year_or_semester"] == "Semester 1"
    assert notice["registered_at"]
    assert notice["is_read"] is False
    for secret in ("password", "password_hash", "token", "token_hash"):
        assert secret not in notice

    duplicate = client.post("/auth/register", json=payload)
    assert duplicate.status_code == 409
    with SessionLocal() as session:
        stored = session.scalar(
            select(func.count()).select_from(AdminNotification).where(AdminNotification.student_id == student_id)
        )
    assert stored == 1

    guest = TestClient(app)
    guest.__enter__()
    try:
        assert guest.get("/notifications").status_code == 401
        assert guest.get("/registrations").status_code == 401
        denied_page = guest.get("/admin/dashboard", follow_redirects=False)
        assert denied_page.status_code == 303
    finally:
        guest.__exit__(None, None, None)

    student = TestClient(app)
    student.__enter__()
    try:
        signed_in = student.post("/auth/login", json={
            "email": email,
            "password": "student-pass-1",
            "portal": "student",
        })
        assert signed_in.status_code == 200
        assert student.get("/notifications").status_code == 403
        assert student.get("/registrations").status_code == 403
        assert student.get("/students").status_code == 403
        wrong_door = student.post("/auth/login", json={
            "email": email,
            "password": "student-pass-1",
            "portal": "admin",
        })
        assert wrong_door.status_code == 403
        blocked = student.get("/admin/dashboard", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"] == "/admin/login"
    finally:
        student.__exit__(None, None, None)

    directory = client.get("/registrations", params={"q": admission})
    assert directory.status_code == 200
    match = [row for row in directory.json()["items"] if row["id"] == student_id]
    assert len(match) == 1
    assert match[0]["account_status"] == "active"
    assert "password_hash" not in directory.text

    marked = client.post(f"/notifications/{notice['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    deleted = client.delete(f"/students/{student_id}")
    assert deleted.status_code == 204
    with SessionLocal() as session:
        remaining = session.scalar(
            select(func.count()).select_from(AdminNotification).where(AdminNotification.student_id == student_id)
        )
    assert remaining == 0
    client.post("/auth/logout")
    remove_test_admin()


def test_bootstrap_admin_is_hashed_and_can_change_password(client):
    health = client.get("/health")
    if health.json().get("academic_records") != "ready":
        pytest.skip(health.json().get("detail"))
    email, password = _credentials()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.role == "admin"
        original_hash = user.password_hash
        original_flag = user.must_change_password
        assert original_hash != password
        assert original_hash.startswith("$2")
        file_still_matches = verify_password(password, original_hash)
        assert bootstrap_admin(session) == "configured"
        session.refresh(user)
        assert user.password_hash == original_hash
        count = session.scalar(select(func.count()).select_from(User).where(User.email == email))
        assert count == 1

    if not file_still_matches:
        # The administrator has already replaced the generated password.
        # Leave that hash alone and exercise the change on the temporary test admin.
        _change_and_restore_test_admin_password(client)
        return

    try:
        signed_in = client.post("/auth/login", json={
            "email": email,
            "password": password,
            "portal": "admin",
        })
        assert signed_in.status_code == 200
        assert signed_in.json()["role"] == "admin"
        assert "password_hash" not in signed_in.text
        changed = client.post("/auth/password", json={
            "current_password": password,
            "new_password": "Replacement-pass-1",
            "new_password_confirmation": "Replacement-pass-1",
        })
        assert changed.status_code == 200
        client.post("/auth/logout")
        old_password = client.post("/auth/login", json={
            "email": email,
            "password": password,
            "portal": "admin",
        })
        assert old_password.status_code == 401
        new_password = client.post("/auth/login", json={
            "email": email,
            "password": "Replacement-pass-1",
            "portal": "admin",
        })
        assert new_password.status_code == 200
        assert new_password.json()["must_change_password"] is False
        page = client.get("/admin/dashboard")
        assert page.status_code == 200
        assert "Registration notifications" in page.text
    finally:
        client.post("/auth/logout")
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == email))
            user.password_hash = original_hash
            user.must_change_password = original_flag
            session.commit()
        restored = client.post("/auth/login", json={
            "email": email,
            "password": password,
            "portal": "admin",
        })
        assert restored.status_code == 200
        client.post("/auth/logout")


def _change_and_restore_test_admin_password(client):
    """Change the temporary administrator password, then restore its original hash."""
    from tests.support import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD

    login_admin(client)
    try:
        changed = client.post("/auth/password", json={
            "current_password": TEST_ADMIN_PASSWORD,
            "new_password": "Replacement-pass-1",
            "new_password_confirmation": "Replacement-pass-1",
        })
        assert changed.status_code == 200
        assert changed.json()["detail"] == "Password updated."
        client.post("/auth/logout")
        old_password = client.post("/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
            "portal": "admin",
        })
        assert old_password.status_code == 401
        new_password = client.post("/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": "Replacement-pass-1",
            "portal": "admin",
        })
        assert new_password.status_code == 200
        assert new_password.json()["must_change_password"] is False
    finally:
        client.post("/auth/logout")
        login_admin(client)
        client.post("/auth/logout")
        remove_test_admin()
