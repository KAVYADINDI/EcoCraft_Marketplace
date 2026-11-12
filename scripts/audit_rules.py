"""Pure-Python checks for expected EcoCraft indexes and schemas.

These helpers are intentionally dependency-free so they can be tested offline.
"""

COLLECTION_NAMES = ("users", "products", "cart", "orders", "reviews")
REQUIRED_UNIQUE = {
    "users": ("email", "userID"),
    "cart": ("customerId",),
}


def index_has_single_field_unique(index, field):
    """Require a full single-field unique index; partial uniqueness is insufficient."""
    keys = index.get("keys", [])
    # A partial unique index is NOT a general unique constraint.
    return (
        index.get("unique", False) is True
        and len(keys) == 1
        and keys[0][0] == field
        and "partialFilterExpression" not in index
    )


def index_warnings(indexes_by_collection):
    """Report missing or unreadable required account/cart uniqueness constraints."""
    warnings = []
    for collection, fields in REQUIRED_UNIQUE.items():
        # None means the query was not permitted: don't claim index missing.
        indexes = indexes_by_collection.get(collection)
        if indexes is None:
            warnings.append(f"UNVERIFIED: indexes on {collection} were not readable")
            continue
        for field in fields:
            if not any(index_has_single_field_unique(index, field) for index in indexes):
                warnings.append(f"NOT VERIFIED: unique index on {collection}.{field}")
    return warnings
