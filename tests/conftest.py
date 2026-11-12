"""Shared offline Flask fixtures; ordinary tests explicitly disable Atlas connection configuration."""
import pytest


@pytest.fixture
def app():
    from app import create_app
    # No Atlas connection is created for ordinary unit tests.
    return create_app({"TESTING": True, "MONGO_URI": ""})


@pytest.fixture
def client(app):
    return app.test_client()
