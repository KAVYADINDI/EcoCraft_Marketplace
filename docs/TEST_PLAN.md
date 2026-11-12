# Testing EcoCraft

The professor's main requirement is to demonstrate MongoDB operations **through the web application**. Atlas or Compass is useful for checking the result, but it does not replace clicking through the website.

## Automated tests

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node scripts/test_frontend_auth.cjs
node scripts/test_frontend_images.cjs
```

The test suite covers validation, permissions, route behavior and key calculations. The Node.js scripts exercise frontend login and image-handling logic. These checks do not write to the shared database.

To check a running Flask server without modifying Atlas data:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_api.py
```

`smoke_api.py` has a separate `--write --admin-email` mode that creates fresh accounts and other demo records. Use it only after a team-approved backup and a deliberate write opt-in. It is **not** an ordinary read-only check and does not clean up every created record.

## Browser and MongoDB checklist

Use newly registered accounts and new products. Keep the original seeded records unchanged.

| Area | What to try in the website | What to verify |
| --- | --- | --- |
| Connectivity | Open the site, `/api/health`, and `/api/health/db`. | Flask runs and can reach the configured MongoDB database. |
| Catalog | Search by name and filter by category. | Only approved, listed products appear; search narrows the results. |
| Aggregation | Open **Insights** and refresh the category report. | Data comes from `/api/analytics/categories` and its MongoDB aggregation pipeline. |
| Registration | Create a customer and an artist. Try a duplicate email and invalid fields. | New account documents are saved; invalid/duplicate submissions are rejected. |
| Artist approval | Attempt artist login before approval; approve through the admin dashboard. | Pending login is blocked; the newly created artist's onboarding status changes to `approved`. |
| Product CREATE | As an approved artist, submit a product and optional image. | `products` contains the correct artist reference, Decimal128 price and pending status. |
| Product UPDATE | Edit the new listing. | Updated values persist and the product returns to pending review. |
| Product DELETE | Delete an unused new product. | It disappears; a referenced product cannot be deleted. |
| Product approval | Approve the new listing and set commission as admin. | Product becomes public and is searchable; commission rate is saved. |
| Cart CRUD | Add the new approved product, change quantity, remove it and add it again. | `cart.items` changes match the website. Invalid quantities are rejected. |
| Checkout | Place a demo order with a shipping address. | `orders` gains an order, stock decreases and the cart clears. No payment is collected. |
| Cancellation | Cancel an active, unshipped order item. | Stock is restored once; repeating the cancellation is rejected. |
| Shipping | As artist, mark your own item shipped and then delivered. | Item and order status update correctly; other artists' order items remain private. |
| Reviews | As a purchasing customer, add, edit and delete a review. | `reviews` changes; duplicate and unauthorized reviews are rejected. |
| Permissions | Attempt a request as the wrong role and try editing seeded data. | Unauthorized or protected writes are refused. |

### Validation examples

Try a negative price, fractional inventory quantity, missing required product fields, invalid email, rating outside 1–5, and an unknown ObjectId. The backend should reject invalid input without persisting a partial update. Read-only verification can use Atlas; do not modify seed records to test validation.

### Additional cases worth checking

A successful browser demo is evidence of a working happy path, not proof of every edge case. Before any public deployment, transaction rollback, concurrent cart edits, inventory races, and upload cleanup would need more rigorous testing. Atlas must support transactions for checkout and cancellation.

## Database recreation requirement

`scripts/recreate_demo.js` is provided for the database recreation deliverable. It rebuilds only `ecocraft_submission_dev`. It should never be run against the shared `ecocraft` database or as part of routine tests. Inspect its target and permissions before running it intentionally.
