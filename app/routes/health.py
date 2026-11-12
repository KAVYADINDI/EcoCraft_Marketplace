"""Small, read-only endpoints for checking the local app and Atlas connection."""
from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

from ..db import DatabaseConfigurationError, get_client

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def server_health():
    """Verify Flask itself is running; does NOT require MongoDB."""
    return jsonify(status="ok", service="ecocraft-backend", phase="integrated-marketplace"), 200


@health_bp.get("/health/db")
def database_health():
    """Read-only ping. Do not expose connection URI or credentials in errors."""
    try:
        client = get_client()
        client.admin.command("ping")
    except DatabaseConfigurationError:
        return jsonify(status="unavailable", error={"code": "DATABASE_NOT_CONFIGURED"}), 503
    except (PyMongoError, ValueError, OSError):
        current_app.logger.warning("Atlas ping failed; verify network, database credentials and cluster")
        return jsonify(status="unavailable", error={"code": "DATABASE_UNREACHABLE"}), 503

    return jsonify(status="ok", database=current_app.config["MONGO_DB_NAME"]), 200
