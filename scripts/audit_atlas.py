"""Read-only Atlas schema audit, run with: python -m scripts.audit_atlas.

Only uses ping, listCollections, listIndexes and countDocuments (read operations).
No credentials or customer/artist documents are written into the report.
"""
import os
from pathlib import Path

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .audit_rules import COLLECTION_NAMES, index_warnings

ROOT = Path(__file__).resolve().parents[1]


def normalize_index(index):
    """Keep only schema-relevant index metadata, without recording application documents."""
    normalized = {
        "name": index.get("name"),
        "keys": [[key, value] for key, value in index.get("key", {}).items()],
        "unique": index.get("unique", False),
    }
    for key in ("partialFilterExpression", "sparse", "expireAfterSeconds"):
        if key in index:
            normalized[key] = index[key]
    return normalized


def run():
    """Read Atlas metadata/counts and replace the local sanitized audit JSON; never write to MongoDB."""
    load_dotenv(ROOT / ".env", override=False)
    uri = os.getenv("MONGO_URI", "").strip()
    username = os.getenv("MONGO_USERNAME", "")
    password = os.getenv("MONGO_PASSWORD", "")
    database_name = os.getenv("MONGO_DB_NAME", "ecocraft")
    if not uri or bool(username) != bool(password):
        print("CONFIG ERROR: Fill MONGO_URI and matching MongoDB credentials in local .env")
        return 2
    opts = {"serverSelectionTimeoutMS": 5000, "appname": "EcoCraft-ReadOnly-Audit"}
    if username:
        opts.update(username=username, password=password)
    try:
        client = MongoClient(uri, **opts)
    except (PyMongoError, ValueError):
        print("INVALID CONNECTION SETTINGS: check MONGO_URI and database-user credentials in .env")
        return 2

    output = {
        "database": database_name,
        "audit_type": "read-only",
        "collections": {},
        "warnings": [],
    }
    try:
        client.admin.command("ping")
        db = client[database_name]
        # Filter to our five app collections; intentionally skip system.profile.
        metadata = {
            item["name"]: item
            for item in db.list_collections()
            if item["name"] in COLLECTION_NAMES
        }
        indexes_by_collection = {}
        for name in COLLECTION_NAMES:
            item = metadata.get(name)
            if item is None:
                output["warnings"].append(f"MISSING: expected collection {name}")
                continue
            coll = db[name]
            indexes = None
            try:
                indexes = [normalize_index(idx) for idx in coll.list_indexes()]
            except PyMongoError:
                output["warnings"].append(f"UNVERIFIED: could not read {name} indexes")
            indexes_by_collection[name] = indexes
            try:
                count = coll.count_documents({})
            except PyMongoError:
                count = None
                output["warnings"].append(f"UNVERIFIED: could not count {name} documents")
            options = item.get("options", {})
            output["collections"][name] = {
                "document_count": count,
                "indexes": indexes,
                "validator": options.get("validator"),
                "validationLevel": options.get("validationLevel"),
                "validationAction": options.get("validationAction"),
            }
            if not options.get("validator"):
                output["warnings"].append(f"NOT VERIFIED: collection validator for {name}")
        output["warnings"].extend(index_warnings(indexes_by_collection))
    except PyMongoError as error:
        print(f"AUDIT ERROR: {type(error).__name__}: {error}")
        print("Check your Atlas IP access list, cluster address, credentials and database permissions.")
        return 1
    finally:
        client.close()

    report_path = ROOT / "reports" / "atlas_schema_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json_util.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved read-only audit: {report_path}")
    for name, details in output["collections"].items():
        print(f"  {name}: {details['document_count']} documents; {len(details['indexes']) if details['indexes'] is not None else '?'} indexes")
    for warning in output["warnings"]:
        print(f"  WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
