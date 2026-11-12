# EcoCraft API contract

Base URL: `http://127.0.0.1:5000/api`. Requests/responses use JSON except the multipart image upload. Protected routes require `Authorization: Bearer <accessToken>`. The frontend holds tokens in tab memory; authentication does not use cookies.

## Access and shared-data rules

Customer and artist are the only publicly registrable roles. An artist must be approved before login/access. Admin privileges come from an existing authorized account, never a registration field.

All mutations require the configured write opt-in. In shared `ecocraft`, ordinary mutations also require an eligible new `WEB26-` customer/artist and record ownership. Seeded admins may approve only eligible new artists/products. Original seeds remain read-only. A token authenticates the user; it does not bypass these checks.

## Endpoints

Paths below are relative to `/api`.

| Method | Path | Access and behavior |
| --- | --- | --- |
| GET | `/health` | Public Flask status; no database access. |
| GET | `/health/db` | Public read-only Atlas ping. |
| POST | `/auth/register` | Public, write-gated customer/artist creation. |
| POST | `/auth/login` | Public authentication; returns JWT and public user. |
| GET | `/auth/me` | Authenticated public profile. |
| PATCH | `/auth/me` | Eligible user's own first/last name or mobile only. |
| GET | `/admin/artists` | Admin artist list; optional `status`, `page`; 20/page. |
| PATCH | `/admin/artists/<id>/approval` | Admin moderation of eligible new artist. |
| GET | `/products` | Public approved/listed catalog; optional `search`, `category`, `page`; 20/page. |
| GET | `/products/mine` | Artist's own listings, up to 200. |
| POST | `/products` | Eligible approved artist creates pending, unlisted product. |
| PATCH | `/products/<id>` | Owning artist edits eligible product and resubmits for approval. |
| DELETE | `/products/<id>` | Owning artist deletes unused product; references cause 409. |
| POST | `/products/image-upload` | Eligible approved artist multipart upload; no product/database insert. |
| GET | `/admin/products` | Admin product list; `status` defaults to `pending_review`, or use `approved`, `rejected`, `all`; up to 100. |
| PATCH | `/admin/products/<id>/review` | Admin approves/lists or rejects eligible new product; optional commission. |
| GET | `/cart` | Customer's own cart or empty cart shape. |
| POST | `/cart/items` | Customer adds eligible approved product/quantity. |
| PATCH | `/cart/items/<productId>` | Customer changes existing cart item quantity. |
| DELETE | `/cart/items/<productId>` | Customer removes own cart item. |
| POST | `/orders/checkout` | Customer simulated transaction-based checkout. |
| GET | `/orders/mine` | Customer's own order history, up to 100. |
| GET | `/orders/sales` | Artist's own order items, up to 100 orders; retains original item indices. |
| PATCH | `/orders/<id>/items/<index>/cancel` | Customer cancels own active unshipped item; restores stock once. |
| PATCH | `/orders/<id>/items/<index>/ship` | Owning artist advances item shipped/delivered. |
| GET | `/products/<id>/reviews` | Public product reviews, up to 100. |
| POST | `/reviews` | Eligible customer creates verified review of active purchased item. |
| PATCH | `/reviews/<id>` | Customer edits own eligible review rating/comment. |
| DELETE | `/reviews/<id>` | Customer deletes own eligible review. |
| GET | `/analytics/categories` | Public MongoDB category aggregation, up to 30 groups. |

## Request examples and field rules

Customer registration:

```json
{"role":"customer","email":"buyer@example.test","password":"example-only-password","firstName":"Demo","lastName":"Buyer"}
```

Artist registration adds `originStory` and sets `role` to `artist`. Password length is 10–128 characters. Registration returns 201 with `message`/`user`; new artists start at `request_received`. Duplicate email/user ID returns 409. Never put real account passwords in repository examples.

Login accepts `email` and `password`, returning `accessToken`, `tokenType: "Bearer"`, `expiresIn` (seconds) and `user`. Public users expose `id`, `userID`, `email`, `role`, `personalInfo`, and optional `artistProfile`; they do not expose password hashes. Profile PATCH accepts only `firstName`, `lastName`, `mobile`.

Product creation:

```json
{"title":"Recycled Tote","description":"Handmade from reclaimed fabric.","price":"25.50","category":"Accessories","materials":["Cotton"],"quantityAvailable":5,"tags":["recycled"],"images":["https://example.test/tote.png"]}
```

Required: title, description, price, category, nonempty materials, and integer quantity. Price has at most two decimal places, range 0.01–9999999.99. Inventory range is 0–100000. Optional fields include dimensions, care instructions, tags, images (up to 8 HTTPS URLs), sustainability, copyright text and return policy; exact limits are in `parse_product()`. PATCH accepts a nonempty subset of those fields. Clients cannot submit artist ownership, approval, listing or commission fields. Direct inventory replacement is blocked after ordering, except an unchanged quantity may be omitted from the update.

Artist approval accepts `{"status":"approved"}` or `rejected`, `waiting_for_documents`, `received_documents`. Product review accepts `{"status":"approved","commissionRate":10}` or `rejected`, with optional commission from 0–100 (at most two decimal places).

Image upload accepts `multipart/form-data` with field `file`, PNG/JPEG/WebP up to 4 MB. Successful response is **201** with `{"url":"https://res.cloudinary.com/..."}`. Save that URL separately through product create/update. No Cloudinary credentials are returned. Missing configuration returns 503; rejected/unreachable hosting returns 502. An upload can remain unused if product saving ultimately fails.

Cart POST accepts `productId` and integer `quantity` (1–100). Quantity PATCH accepts `quantity`; stock is checked server-side. Checkout accepts `shippingAddress` containing nonempty `street`, `city`, `state`, `zipCode`, `country`. Prices, totals, artist payout and commission are calculated server-side. Checkout returns 201 with `order`/`message`; it decreases stock and clears the cart atomically.

Shipping accepts `{"status":"shipped","trackingNumber":"EXAMPLE-123"}`, then `{"status":"delivered"}`. Tracking is optional and may be set only when marking shipped. Pending → shipped → delivered is the only supported progression. Cancellation requires an active pending-shipping item; shipped/delivered items cannot be cancelled.

Review POST requires `productId`, `orderId`, integer `rating` (1–5), and optional `comment` up to 1000 characters. The order must belong to the customer and contain the active item. Delivery is not required by current rules. Duplicate reviews for the same purchase are rejected by the database index. Review PATCH accepts rating/comment; DELETE removes the review.

## Responses and errors

Product/order/review documents use `_id` strings; the public user projection uses `id`. Money is serialized as two-decimal strings and dates as ISO strings. Success envelopes use names such as `product`, `products`, `cart`, `order`, `orders`, `sales`, `review`, `reviews`, `artists`, `categories`. Category results contain `category`, `productCount`, `averagePrice` and a top-level `pipelineStages` array.

Errors generally use:

```json
{"error":{"code":"VALIDATION_ERROR","message":"Description of the problem"}}
```

Health configuration/connection errors instead expose `status: "unavailable"` and an error code without credentials. Common statuses: 400 invalid input; 401 missing/invalid/expired credentials; 403 role, approval, disabled-write or seed protection; 404 missing eligible resource; 409 duplicate/reference/stock/state conflict; 413 request too large; 502 upload service failure; 503 unavailable/unconfigured service. The normal JSON body limit is 16 KB; only the image endpoint raises its multipart limit.
