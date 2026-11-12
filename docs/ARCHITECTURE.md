# Architecture and data flow

## Application boundaries

`app.create_app()` loads local environment settings, applies optional test overrides, configures CORS, and registers Flask blueprints. Importing the app does not open a database connection. `app/db.py` lazily creates one PyMongo client per Flask application and reuses it through `app.extensions`.

The browser loads `marketplace.html` and its existing CSS/JavaScript. JavaScript sends same-origin `/api` requests to Flask. JWT access tokens are held in tab memory and sent as Bearer headers; refreshing the tab requires signing in again. The browser does not connect to Atlas or receive database/Cloudinary secrets. `/demo` is a retained localhost-only account-testing interface.

## Validation, authentication and authorization

- `validation.py` handles registration and profile allowlists, names, email and password lengths. Password hashes are created/checked server-side with Werkzeug.
- `marketplace_core.py` validates product data, addresses, prices, integers and commission rates. These pure helpers have no Flask or database dependency.
- `security.py` verifies JWT issuer, signature and expiration, reloads the account from MongoDB, checks its current role, and denies unapproved artists.
- Write routes apply both configuration opt-in and record eligibility/ownership checks. Enabling writes alone does not authorize a seeded-record mutation.
- In shared `ecocraft`, editable customer/artist records must have server-generated `WEB26-` identifiers. Seeded admins can moderate newly created artists/products, but cannot rewrite original seed profiles/products.
- Strict Atlas collection validators and unique indexes add database constraints. They supplement application checks rather than replacing authorization.

## Document model

`users` embeds personal and artist profile data. Each `products.artistId` references its artist. `cart` embeds item references/quantities and has one unique document per customer. `orders` embeds item-level financial/shipping data and product snapshots so historical purchases retain their original description and price. `reviews` references its customer, product and purchased order; a unique compound index prevents duplicate verified reviews.

`parse_product()` returns Python `Decimal` values for validation/calculation. Product routes convert prices to BSON `Decimal128` before persistence. Currency calculations use explicit two-decimal rounding; `commissionRate: 10` means 10 percent. JSON responses serialize BSON IDs as strings, money as two-decimal strings, and datetimes as ISO strings.

## Product and image lifecycle

Artist creation sets `pending_review` and `listProduct=false`; editing resubmits for review. Admin approval lists the product. Physical deletion is blocked when carts, orders or reviews reference the product. Ordered products also reject direct inventory replacement.

File uploads use a protected artist endpoint with the same write/seed guards. Its multipart body limit is raised independently of the normal 16 KB JSON limit. The adapter checks a 4 MB file-size limit and PNG/JPEG/WebP signatures, then sends a server-authenticated request to Cloudinary. Only the resulting HTTPS URL is stored on the product. Signature checks do not fully decode an image. Existing HTTPS URLs bypass uploading. Unchanged image arrays are preserved during edits; unused uploaded images are not automatically deleted.

## Orders and transactions

Checkout uses one MongoDB session/transaction to read the cart, recheck product availability/artist eligibility, conditionally decrement stock, insert an order with server-calculated totals, and clear the cart. Insufficient stock or another error aborts the transaction. There is no nontransactional fallback.

Inventory decreases at checkout. Shipping changes the artist's own item from `pending → shipped → delivered`; it does not decrement stock again. When all active items are delivered, the overall order becomes `completed`. Artist responses expose only their own item details while preserving original item indices.

Cancellation requires an active unshipped item and runs stock restoration, cancellation marking, and total/status recalculation in a transaction. A repeated cancellation is rejected. Reviews require an active purchased item and may be created before delivery under the current coursework rules.

Cart add/quantity operations use read-modify-write arrays outside transactions. Concurrent cart edits deserve separate testing; offline tests and successful manual checkout do not establish concurrency guarantees.

## Aggregation

`GET /api/analytics/categories` runs MongoDB `$match` on approved/listed products, `$group` by category with count and average price, `$sort` by count/category, and `$limit` to 30 groups. Grouping happens in MongoDB, not in browser or Python code.

## Test and utility boundaries

Pytest uses fake database clients and mocked hosting or pure logic. Node scripts simulate DOM events/API responses. Neither is a live write test. The owner's manual workflow observations are recorded separately from automated verification in the README and test plan.

The saved audit contains schema/index metadata and counts, not customer documents. `build_recreation_script.py` is an offline generator that rewrites the local JavaScript deliverable. The generated script itself is destructive only within the explicitly guarded `ecocraft_submission_dev` target. Development-schema and admin utilities perform their own opt-in writes and must not be run during routine checks.
