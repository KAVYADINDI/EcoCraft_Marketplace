"""Shared ecocraft demo protection tests. All MongoDB calls are simulated."""

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from tests.fakes import FakeMongoClient

SECRET = "integration-test-only-secret-that-is-sufficiently-long"


@pytest.fixture()
def shared_app():
    app = create_app({
        "TESTING": True,
        "MONGO_URI": "mongodb://fake-only",
        "MONGO_DB_NAME": "ecocraft",
        "ENABLE_DEV_WRITES": False,
        "ENABLE_TEAM_DEMO_WRITES": True,
        "JWT_SECRET_KEY": SECRET,
    })
    app.extensions["mongo_client"] = FakeMongoClient()
    return app


@pytest.fixture()
def shared_client(shared_app):
    return shared_app.test_client()


def payload(role="customer"):
    val = dict(role=role, firstName="Test", lastName="Maker",
               email="new-web-user@example.test", password="test-demo-password-123")
    if role == "artist":
        val["originStory"] = "I reuse materials to create handmade products."
    return val


def login(client, email="new-web-user@example.test", password="test-demo-password-123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def headers(token):
    return {"Authorization": "Bearer " + token}


def test_shared_database_refuses_writes_unless_explicitly_enabled():
    app = create_app({"TESTING": True, "MONGO_DB_NAME": "ecocraft",
                      "ENABLE_DEV_WRITES": True, "ENABLE_TEAM_DEMO_WRITES": False})
    response = app.test_client().post("/api/auth/register", json=payload())
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "TEAM_DEMO_WRITES_DISABLED"


def test_frontend_created_customer_can_register_login_and_update(shared_client, shared_app):
    created = shared_client.post("/api/auth/register", json=payload())
    assert created.status_code == 201
    assert created.json["user"]["userID"].startswith("WEB26-CUS-")
    assert "passwordHash" not in created.get_data(as_text=True)
    db_user = shared_app.extensions["mongo_client"].database.users.find_one({"email": payload()["email"]})
    assert db_user is not None
    assert db_user["userID"] == created.json["user"]["userID"]
    assert db_user["passwordHash"] != payload()["password"]
    signed_in = login(shared_client)
    assert signed_in.status_code == 200
    response = shared_client.patch("/api/auth/me", json={"firstName": "Updated", "mobile": "555-0101"},
                                   headers=headers(signed_in.json["accessToken"]))
    assert response.status_code == 200
    assert response.json["user"]["personalInfo"]["firstName"] == "Updated"


def test_artist_pending_login_still_denied(shared_client):
    result = shared_client.post("/api/auth/register", json=payload("artist"))
    assert result.status_code == 201
    assert result.json["user"]["userID"].startswith("WEB26-ART-")
    assert "under review" in result.json["message"]
    assert login(shared_client).status_code == 403


def test_seeded_customer_profile_is_never_modified(shared_client, shared_app):
    users = shared_app.extensions["mongo_client"].database.users
    users.insert_one({"userID": "CUS001", "email": "seeded@example.test",
                      "passwordHash": generate_password_hash("seeded-test-password-123"),
                      "role": "customer", "personalInfo": {"firstName": "Original", "lastName": "Buyer"}})
    result = login(shared_client, "seeded@example.test", "seeded-test-password-123")
    assert result.status_code == 200
    response = shared_client.patch("/api/auth/me", json={"firstName": "ShouldNotSave"},
                                   headers=headers(result.json["accessToken"]))
    assert response.status_code == 403
    assert response.json["error"]["code"] == "SEEDED_RECORD_PROTECTED"
    assert users.find_one({"email": "seeded@example.test"})["personalInfo"]["firstName"] == "Original"


def test_existing_admin_cannot_modify_seed_profile(shared_client, shared_app):
    users = shared_app.extensions["mongo_client"].database.users
    users.insert_one({"userID": "ADM001", "email": "seed-admin@example.test",
                      "passwordHash": generate_password_hash("seed-admin-password-123"),
                      "role": "admin", "personalInfo": {"firstName": "Seed", "lastName": "Admin"}})
    result = login(shared_client, "seed-admin@example.test", "seed-admin-password-123")
    assert result.status_code == 200
    response = shared_client.patch("/api/auth/me", json={"firstName": "Overwrite"},
                                   headers=headers(result.json["accessToken"]))
    assert response.status_code == 403
    assert users.find_one({"userID": "ADM001"})["personalInfo"]["firstName"] == "Seed"


def test_user_cannot_choose_id_or_role_privilege(shared_client):
    data = payload()
    data["userID"] = "ADM001"
    assert shared_client.post("/api/auth/register", json=data).status_code == 400
    data = payload()
    data["role"] = "admin"
    assert shared_client.post("/api/auth/register", json=data).status_code == 400


def test_demo_route_local_only(shared_client):
    response = shared_client.get("/demo")
    assert response.status_code == 200
    assert b"Create account" in response.data
    forbidden = shared_client.get("/demo", environ_overrides={"REMOTE_ADDR": "10.0.0.5"})
    assert forbidden.status_code == 403


def test_public_registration_duplicate_email(shared_client):
    assert shared_client.post("/api/auth/register", json=payload()).status_code == 201
    assert shared_client.post("/api/auth/register", json=payload()).status_code == 409
