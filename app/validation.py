"""Small pure validation helpers; frontend and backend agree on these fields."""
import re

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
NAME_MAX = 100


def require_json_object(value):
    """Identify JSON object payloads before accessing account fields."""
    return isinstance(value, dict)


def clean_email(value):
    """Normalize a syntactically valid email to lowercase, or return None."""
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return None
    return email


def clean_name(value):
    """Trim a nonempty name within the shared name-length limit, or return None."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not (1 <= len(name) <= NAME_MAX):
        return None
    return name


def validate_registration(payload):
    """Return normalized public-registration data or a validation message; deny privileged fields."""
    if not isinstance(payload, dict):
        return None, "JSON object expected"
    allowed = {"email", "password", "role", "firstName", "lastName", "originStory"}
    if set(payload) - allowed:
        return None, "Unknown registration fields are not permitted"
    role = payload.get("role")
    if not isinstance(role, str) or role not in {"customer", "artist"}:
        return None, "Only customer and artist accounts can register publicly"
    email = clean_email(payload.get("email"))
    first = clean_name(payload.get("firstName"))
    last = clean_name(payload.get("lastName"))
    password = payload.get("password")
    if not email or not first or not last:
        return None, "Valid email, firstName and lastName are required"
    if not isinstance(password, str) or not (10 <= len(password) <= 128):
        return None, "Password must be between 10 and 128 characters"
    story = payload.get("originStory")
    if role == "artist":
        if not isinstance(story, str) or not (1 <= len(story.strip()) <= 2000):
            return None, "Artist originStory must contain 1-2000 characters"
        story = story.strip()
    elif "originStory" in payload:
        return None, "originStory is only available for artist accounts"
    return {"email": email, "password": password, "role": role, "firstName": first, "lastName": last, "originStory": story}, None


def validate_profile_changes(payload):
    """Allow only editable personal fields and return dotted MongoDB update paths."""
    if not isinstance(payload, dict):
        return None, "JSON object expected"
    allowed = {"firstName", "lastName", "mobile"}
    if not payload or set(payload) - allowed:
        return None, "Only firstName, lastName and mobile may be updated"
    changes = {}
    for field in ("firstName", "lastName"):
        if field in payload:
            value = clean_name(payload[field])
            if value is None:
                return None, f"{field} must contain 1-100 characters"
            changes[f"personalInfo.{field}"] = value
    if "mobile" in payload:
        mobile = payload["mobile"]
        if not isinstance(mobile, str) or len(mobile.strip()) > 30:
            return None, "mobile must be a string up to 30 characters"
        changes["personalInfo.mobile"] = mobile.strip()
    return changes, None
