"""Pure metadata tests for complete unique-index requirements; no database connection."""
from scripts.audit_rules import index_has_single_field_unique, index_warnings


def test_exact_unique_index_is_valid():
    assert index_has_single_field_unique({"keys": [["customerId", 1]], "unique": True}, "customerId")


def test_non_unique_or_partial_index_is_not_enough():
    assert not index_has_single_field_unique({"keys": [["customerId", 1]], "unique": False}, "customerId")
    assert not index_has_single_field_unique({"keys": [["customerId", 1]], "unique": True, "partialFilterExpression": {"active": True}}, "customerId")


def test_missing_uniqueness_is_reported():
    example = {
        "users": [
            {"keys": [["email", 1]], "unique": True},
            {"keys": [["userID", 1]], "unique": True},
        ],
        "cart": [{"keys": [["_id", 1]], "unique": True}],
    }
    warnings = index_warnings(example)
    assert "NOT VERIFIED: unique index on cart.customerId" in warnings
    assert not any("users.email" in message for message in warnings)
