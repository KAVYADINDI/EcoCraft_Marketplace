"""Read-only admin artist listing; approval mutations are in routes/marketplace.py."""
from flask import Blueprint, jsonify, request
from pymongo.errors import PyMongoError

from ..db import get_database
from ..security import api_error, auth_required, public_user

admin_bp = Blueprint("admin", __name__)
STATUSES = {"request_received", "waiting_for_documents", "received_documents", "approved", "rejected"}


@admin_bp.get("/artists")
@auth_required("admin")
def artist_requests():
    """List onboarding profiles for admins, newest first, with status filtering and pagination."""
    status = request.args.get("status")
    if status and status not in STATUSES:
        return api_error("VALIDATION_ERROR", "Unknown onboarding status", 400)
    page_arg = request.args.get("page", "1")
    if not page_arg.isdecimal() or not (1 <= int(page_arg) <= 1000):
        return api_error("VALIDATION_ERROR", "page must be between 1 and 1000", 400)
    page = int(page_arg)
    filter_doc = {"role": "artist"}
    if status:
        filter_doc["artistProfile.onboardingStatus"] = status
    try:
        docs = (get_database().users.find(filter_doc)
                .sort("_id", -1).skip((page - 1) * 20).limit(20))
        artists = [public_user(user) for user in docs]
    except PyMongoError:
        return api_error("DATABASE_UNAVAILABLE", "Could not list artists", 503)
    return jsonify(artists=artists, page=page, pageSize=20), 200
