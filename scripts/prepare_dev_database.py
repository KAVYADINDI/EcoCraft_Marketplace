"""One-time dev-only: copy schema/indexes, NO documents, from ecocraft to ecocraft_dev.

Run with database owner permission on Atlas. This script never writes to 'ecocraft'.
Do not run against shared project except with team agreement to create isolated dev DB.
"""
from pathlib import Path
import os
from dotenv import load_dotenv
from pymongo import MongoClient, IndexModel
from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = ("users", "products", "cart", "orders", "reviews")


def run():
    """Copy missing schema/index definitions to ecocraft_dev, never source documents or shared-db writes."""
    load_dotenv(ROOT / ".env", override=False)
    uri = os.environ.get("MONGO_URI", "")
    user = os.environ.get("MONGO_USERNAME", "")
    password = os.environ.get("MONGO_PASSWORD", "")
    if not uri or bool(user) != bool(password):
        print("Please configure MONGO_URI and matching credentials locally.")
        return 2
    client = MongoClient(uri, username=user or None, password=password or None, serverSelectionTimeoutMS=5000)
    try:
        source = client["ecocraft"]  # read-only
        target = client["ecocraft_dev"]  # changes only here
        metadata = {doc["name"]: doc.get("options", {}) for doc in source.list_collections() if doc["name"] in COLLECTIONS}
        if set(metadata) != set(COLLECTIONS):
            raise RuntimeError("Source ecocraft is missing one or more expected collections")
        existing = set(target.list_collection_names())
        for name in COLLECTIONS:
            if name in existing:
                print(f"SKIP existing dev collection {name}; do not overwrite")
                continue
            opts = metadata[name]
            create_opts = {key: opts[key] for key in ("validator", "validationLevel", "validationAction") if key in opts}
            target.create_collection(name, **create_opts)
            indices = []
            for idx in source[name].list_indexes():
                if idx["name"] == "_id_":
                    continue
                index_opts = {k: idx[k] for k in ("name", "unique", "sparse", "expireAfterSeconds", "partialFilterExpression", "collation") if k in idx}
                indices.append(IndexModel(list(idx["key"].items()), **index_opts))
            if indices:
                target[name].create_indexes(indices)
            print(f"CREATED dev-only collection: {name} with {len(indices)} secondary index(es)")
        print("Ready: ecocraft_dev schema and indexes; no source documents were copied.")
        return 0
    except (PyMongoError, RuntimeError) as err:
        print(f"Cannot prepare dev database ({type(err).__name__}); check database-user privileges.")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(run())
