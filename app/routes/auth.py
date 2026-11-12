"""Customer/artist registration, JWT login and authenticated profile read/update."""
import uuid

from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_database
from ..security import api_error, auth_required, create_access_token, public_user, require_write_enabled, is_valid_jwt_secret, can_edit_user
from ..validation import clean_email, validate_profile_changes, validate_registration

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    """Create a new write-eligible customer/artist; artist onboarding starts pending."""
    protected = require_write_enabled()
    if protected is not None:
        return protected
    data, problem = validate_registration(request.get_json(silent=True))
    if problem:
        return api_error("VALIDATION_ERROR", problem, 400)
    role = data["role"]
    document = {
        "userID": ("WEB26-CUS-" if role == "customer" else "WEB26-ART-") + uuid.uuid4().hex,
        "email": data["email"],
        "passwordHash": generate_password_hash(data["password"]),
        "role": role,
        "personalInfo": {"firstName": data["firstName"], "lastName": data["lastName"]},
    }
    if role == "artist":
        document["artistProfile"] = {"originStory": data["originStory"], "onboardingStatus": "request_received"}
    try:
        result = get_database().users.insert_one(document)
    except DuplicateKeyError:
        return api_error("ACCOUNT_EXISTS", "Email or user identifier is already registered", 409)
    except PyMongoError:
        current_app.logger.exception("MongoDB registration failure")
        return api_error("DATABASE_UNAVAILABLE", "Could not create the account", 503)
    document["_id"] = result.inserted_id
    message = ("Your registration has been received and is currently under review. "
               "You will be notified once a decision has been made.") if role == "artist" else "Customer account created successfully."
    return jsonify(message=message, user=public_user(document)), 201


@auth_bp.post("/login")
def login():
    """Verify the password before revealing artist status, then issue an expiring token."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {"email", "password"}:
        return api_error("VALIDATION_ERROR", "Email and password are required", 400)
    email = clean_email(data.get("email"))
    password = data.get("password")
    if not email or not isinstance(password, str):
        return api_error("VALIDATION_ERROR", "Valid email and password are required", 400)
    if not is_valid_jwt_secret(current_app.config.get("JWT_SECRET_KEY", "")):
        return api_error("AUTH_NOT_CONFIGURED", "Set JWT_SECRET_KEY before using login", 503)
    try:
        user = get_database().users.find_one({"email": email})
    except PyMongoError:
        current_app.logger.exception("MongoDB login query failed")
        return api_error("DATABASE_UNAVAILABLE", "Database temporarily unavailable", 503)
    # Password first to avoid revealing onboarding status to random callers.
    if user is None or not check_password_hash(user.get("passwordHash", ""), password):
        return api_error("INVALID_CREDENTIALS", "Invalid email or password", 401)
    if user["role"] == "artist" and user.get("artistProfile", {}).get("onboardingStatus") != "approved":
        return api_error("ARTIST_NOT_APPROVED", "Your artist registration is still under review or has not been approved", 403)
    token, seconds = create_access_token(user)
    return jsonify(accessToken=token, tokenType="Bearer", expiresIn=seconds, user=public_user(user)), 200


@auth_bp.get("/me")
@auth_required()
def me():
    """Return the authenticated profile already reloaded by the authorization decorator."""
    return jsonify(user=public_user(g.current_user)), 200


@auth_bp.patch("/me")
@auth_required()
def update_my_profile():
    """Update only the eligible caller's allowlisted personal fields; preserve seeded profiles."""
    protected = require_write_enabled()
    if protected is not None:
        return protected
    if not can_edit_user(g.current_user):
        return api_error("SEEDED_RECORD_PROTECTED", "Original team sample accounts are read-only in this demo", 403)
    changes, problem = validate_profile_changes(request.get_json(silent=True))
    if problem:
        return api_error("VALIDATION_ERROR", problem, 400)
    try:
        db = get_database()
        db.users.update_one(
            {"_id": g.current_user["_id"], "userID": g.current_user["userID"]},
            {"$set": changes},
        )
        user = db.users.find_one({"_id": g.current_user["_id"]})
    except PyMongoError:
        current_app.logger.exception("MongoDB profile update failed")
        return api_error("DATABASE_UNAVAILABLE", "Could not update the profile", 503)
    return jsonify(user=public_user(user)), 200
