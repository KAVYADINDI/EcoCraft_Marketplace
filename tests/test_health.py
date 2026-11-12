"""Offline health, configuration and unauthenticated-mutation regression checks."""
from app import create_app


def test_flask_health_without_atlas(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_db_health_requires_configuration(client):
    response = client.get("/api/health/db")
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "DATABASE_NOT_CONFIGURED"


def test_db_health_ping_with_fake_client():
    class FakeAdmin:
        def command(self, command):
            assert command == "ping"
            return {"ok": 1}

    class FakeClient:
        admin = FakeAdmin()

    app = create_app({"TESTING": True, "MONGO_URI": "mongodb://unused", "MONGO_DB_NAME": "ecocraft_test"})
    app.extensions["mongo_client"] = FakeClient()
    response = app.test_client().get("/api/health/db")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ecocraft_test"}


def test_product_mutation_requires_authentication(client):
    # The earlier Phase-1 assertion expected 404 before product routes existed.
    # Product CRUD now exists: unauthorized writes must be rejected with 401.
    response = client.post("/api/products", json={"title": "not-created"})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"
