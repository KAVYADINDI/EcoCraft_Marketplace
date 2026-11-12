"""Interactive one-time development admin seeding, never touches shared ecocraft."""
import getpass
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.security import generate_password_hash

from app.validation import clean_email, clean_name

ROOT = Path(__file__).resolve().parents[1]


def run():
    """Interactively insert a new dev admin only after the exact development-db/write checks pass."""
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("MONGO_DB_NAME") != "ecocraft_dev" or os.getenv("ENABLE_DEV_WRITES", "").lower() != "true":
        print("Refusing to create admin: set MONGO_DB_NAME=ecocraft_dev and ENABLE_DEV_WRITES=true")
        return 2
    email = clean_email(input("Development admin email: "))
    first = clean_name(input("First name: "))
    last = clean_name(input("Last name: "))
    password = getpass.getpass("New development-only password (not your Atlas password): ")
    if not email or not first or not last or not 10 <= len(password) <= 128:
        print("Invalid details (password length 10-128)")
        return 2
    uri = os.environ.get("MONGO_URI", "")
    username = os.environ.get("MONGO_USERNAME", "")
    db_password = os.environ.get("MONGO_PASSWORD", "")
    if not uri or bool(username) != bool(db_password):
        print("MongoDB credentials not configured")
        return 2
    client = MongoClient(uri, username=username or None, password=db_password or None, serverSelectionTimeoutMS=5000)
    try:
        db = client["ecocraft_dev"]
        if db.users.find_one({"email": email}):
            print("An account already exists for this email; no changes made")
            return 1
        db.users.insert_one({"userID": "ADM-" + uuid.uuid4().hex, "email": email, "passwordHash": generate_password_hash(password), "role": "admin", "personalInfo": {"firstName": first, "lastName": last}})
        print("Development admin created in ecocraft_dev ONLY")
        return 0
    except (DuplicateKeyError, PyMongoError) as err:
        print(f"Could not create dev admin: {type(err).__name__}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(run())
