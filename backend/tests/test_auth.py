"""Phase 2 — authentication & RBAC (docs/14_PHASE2_SECURITY_SPEC.md).

Uses the `client` fixture, which already registered as the first user (auto-admin) — see conftest.py. These
tests use a *second* `TestClient(app)` when they need to check unauthenticated or non-admin behaviour, since the
fixture's client always carries a valid admin token by default.
"""

from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password
from app.main import app

from .conftest import definition

PW = "Correct-Horse-1!"


def register(client, username, display_name=None, password=PW):
    return client.post("/api/auth/register",
                       json={"username": username, "password": password, "display_name": display_name or username})


def login(client, username, password=PW):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# ---------------------------------------------------------------- password hashing


def test_password_hash_is_salted_and_verifiable():
    h1 = hash_password("hunter2")
    h2 = hash_password("hunter2")
    assert h1 != h2  # different salt each time
    assert verify_password("hunter2", h1) and verify_password("hunter2", h2)
    assert not verify_password("wrong", h1)


def test_password_hash_survives_garbage_input():
    assert not verify_password("x", "not-a-valid-hash")
    assert not verify_password("x", "pbkdf2_sha256$bad$bad$bad")


# ---------------------------------------------------------------- registration / login


def test_first_user_is_admin_second_is_not(client):
    # `client` fixture already registered "test-bootstrap" as user #1 (admin).
    r = register(client, "regular-alice")
    assert r.status_code == 201 and r.json()["user"]["roles"] == []


def test_duplicate_username_rejected(client):
    register(client, "dupe-user")
    r = register(client, "dupe-user")
    assert r.status_code == 409 and r.json()["code"] == "AUTH001"


def test_username_format_enforced(client):
    for bad in ("a", "ab", "AB CD", "has space", "semi;colon"):
        r = register(client, bad)
        assert r.status_code == 422, bad


def test_blank_display_name_rejected(client):
    r = client.post("/api/auth/register", json={"username": "blank-name", "password": PW, "display_name": "   "})
    assert r.status_code == 422 and r.json()["code"] == "AUTH009"


def test_short_password_rejected(client):
    r = register(client, "short-pw-user", password="short")
    assert r.status_code == 422


def test_login_wrong_password_rejected(client):
    register(client, "wp-user")
    r = login(client, "wp-user", "totally-wrong")
    assert r.status_code == 401 and r.json()["code"] == "AUTH003"


def test_login_unknown_user_rejected(client):
    r = login(client, "nobody-here")
    assert r.status_code == 401 and r.json()["code"] == "AUTH003"


def test_login_case_insensitive_username(client):
    register(client, "casey")
    r = login(client, "CaSeY")
    assert r.status_code == 200


def test_account_locks_after_repeated_failures(client):
    register(client, "lockout-user")
    for _ in range(5):
        r = login(client, "lockout-user", "wrong")
        assert r.status_code == 401
    r = login(client, "lockout-user", "wrong")
    assert r.status_code == 423 and r.json()["code"] == "AUTH002"
    r = login(client, "lockout-user", PW)  # even the right password is locked out
    assert r.status_code == 423


def test_successful_login_resets_failure_counter(client):
    register(client, "reset-user")
    for _ in range(3):
        login(client, "reset-user", "wrong")
    assert login(client, "reset-user", PW).status_code == 200
    for _ in range(4):  # would have tripped the 5-attempt lock if the counter hadn't reset
        r = login(client, "reset-user", "wrong")
        assert r.status_code == 401


# ---------------------------------------------------------------- sessions


def test_no_token_is_401():
    with TestClient(app) as anon:
        r = anon.get("/api/scorecards")
        assert r.status_code == 401 and r.json()["code"] == "AUTH004"


def test_garbage_token_is_401():
    with TestClient(app) as anon:
        r = anon.get("/api/scorecards", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401 and r.json()["code"] == "AUTH004"


def test_malformed_authorization_header_is_401():
    with TestClient(app) as anon:
        assert anon.get("/api/scorecards", headers={"Authorization": "not-bearer-scheme"}).status_code == 401
        assert anon.get("/api/scorecards", headers={"Authorization": "Bearer"}).status_code == 401


def test_logout_revokes_the_session(client):
    r = register(client, "logout-user")
    token = r.json()["token"]
    with TestClient(app) as c2:
        assert c2.get("/api/scorecards", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert c2.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
        r = c2.get("/api/scorecards", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401 and r.json()["code"] == "AUTH004"


def test_deactivated_user_session_stops_working(client):
    r = register(client, "deactivate-me")
    token, uid = r.json()["token"], r.json()["user"]["id"]
    with TestClient(app) as c2:
        assert c2.get("/api/scorecards", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    client.patch(f"/api/users/{uid}", json={"is_active": False})
    with TestClient(app) as c2:
        r = c2.get("/api/scorecards", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


def test_me_reports_the_logged_in_user(client):
    r = register(client, "whoami-user", "Who Am I")
    token = r.json()["token"]
    with TestClient(app) as c2:
        me = c2.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["username"] == "whoami-user" and me.json()["display_name"] == "Who Am I"


# ---------------------------------------------------------------- RBAC


def _as(username, display_name=None):
    def hdr(client):
        r = register(client, username, display_name)
        token = r.json()["token"] if r.status_code == 201 else login(client, username).json()["token"]
        return {"Authorization": f"Bearer {token}"}
    return hdr


def test_member_cannot_create_scorecard(client):
    headers = _as("plain-member")(client)
    body = {"code": "should-fail", "name": "x", "subject_type": "task",
            "version": {"purpose": "p", "scope": "s", "objective": "o", "rating_scale": "0-10-rag",
                       "target_score": 8, "parameters": []}}
    r = client.post("/api/scorecards", json=body, headers=headers)
    assert r.status_code == 403 and r.json()["code"] == "AUTH006"


def test_designer_role_grants_scorecard_creation(client):
    r = register(client, "new-designer")
    uid = r.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    body = {"code": "designer-made", "name": "x", "subject_type": "task",
            "version": {"purpose": "p", "scope": "s", "objective": "o", "rating_scale": "0-10-rag",
                       "target_score": 8, "parameters": []}}
    assert client.post("/api/scorecards", json=body, headers=headers).status_code == 403
    client.patch(f"/api/users/{uid}", json={"roles": ["designer"]})
    assert client.post("/api/scorecards", json=body, headers=headers).status_code == 201


def test_member_cannot_manage_users(client):
    headers = _as("nosy-member")(client)
    assert client.get("/api/users", headers=headers).status_code == 403


def test_admin_cannot_deactivate_self(client):
    r = client.get("/api/auth/me")
    r2 = client.patch(f"/api/users/{r.json()['id']}", json={"is_active": False})
    assert r2.status_code == 409 and r2.json()["code"] == "AUTH008"


def test_unknown_role_rejected(client):
    r = register(client, "role-target")
    uid = r.json()["user"]["id"]
    bad = client.patch(f"/api/users/{uid}", json={"roles": ["superhero"]})
    assert bad.status_code == 422 and bad.json()["code"] == "AUTH007"


def test_importer_role_gates_migration_commit(client, tmp_path):
    import io
    import zipfile

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Scorecard: X"])
    ws.append(["Scale: 0-10"])
    ws.append(["Target: 8"])
    ws.append([])
    ws.append(["KPI", "Weight", "10", "0"])
    ws.append(["Only", "1", "great", "bad"])
    buf = io.BytesIO()
    wb.save(buf)

    headers = _as("plain-importer")(client)
    files = [("files", ("x.xlsx", buf.getvalue(), "application/octet-stream"))]
    preview = client.post("/api/migrations/preview", files=files, headers=headers)
    assert preview.status_code == 200  # preview writes nothing, so it stays open to any member
    commit = client.post("/api/migrations/commit", files=files, headers=headers)
    assert commit.status_code == 403 and commit.json()["code"] == "AUTH006"
    del zipfile  # imported only to document the workbook format; not used directly


def test_diagnosis_notes_are_private_to_lead_and_the_person(client):
    a = _as("diag-alice", "Alice D")(client)
    lead = register(client, "diag-lead", "Lead D")
    lead_headers = {"Authorization": f"Bearer {lead.json()['token']}"}
    client.patch(f"/api/users/{lead.json()['user']['id']}", json={"roles": ["lead"]})

    client.post("/api/diagnoses", json={"person": "Alice D", "cause": "skill", "action": "train", "notes": "secret"},
               headers=lead_headers)
    as_alice = client.get("/api/diagnoses", headers=a).json()
    assert len(as_alice) == 1 and as_alice[0]["notes"] == "secret"
    other = _as("diag-bob", "Bob D")(client)
    as_bob = client.get("/api/diagnoses", headers=other).json()
    assert as_bob == []


def test_capability_level_is_private_to_lead_and_the_person(client):
    card = client.post("/api/scorecards", json=definition(code="cap-privacy-card")).json()

    a = _as("cap-alice", "Alice C")(client)
    lead = register(client, "cap-lead", "Lead C")
    lead_headers = {"Authorization": f"Bearer {lead.json()['token']}"}
    client.patch(f"/api/users/{lead.json()['user']['id']}", json={"roles": ["lead"]})

    client.post("/api/capabilities", json={"person": "Alice C", "scorecard": card["code"], "level": 3},
               headers=lead_headers)
    as_alice = client.get("/api/capabilities", headers=a).json()
    assert len(as_alice) == 1 and as_alice[0]["level"] == 3 and as_alice[0]["level_label"] == "Developing"
    other = _as("cap-bob", "Bob C")(client)
    as_bob = client.get("/api/capabilities?person=Alice C", headers=other).json()
    assert as_bob == []


def test_member_cannot_record_capability(client):
    card = client.post("/api/scorecards", json=definition(code="cap-member-card")).json()
    headers = _as("cap-member", "Member C")(client)
    r = client.post("/api/capabilities", json={"person": "Someone", "scorecard": card["code"], "level": 3},
                    headers=headers)
    assert r.status_code == 403 and r.json()["code"] == "AUTH006"
