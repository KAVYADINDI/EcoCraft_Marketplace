# EcoCraft - Sustainable Marketplace

EcoCraft is a web marketplace for handmade and sustainably made products. Artists can create and manage listings, customers can shop and leave reviews, and administrators can approve artists and products before they appear in the catalog.

We built EcoCraft for our NoSQL database project. The focus is on using MongoDB through a working web application—not entering CRUD commands manually in Compass. The interface talks to a Python/Flask backend, which handles validation, permissions, and MongoDB operations using PyMongo.

> **Course project:** Checkout creates a demo order and updates inventory; it does not collect payments. The shared database also protects the original seeded records from demo edits.

## What you can do

| Role | Main actions |
| --- | --- |
| Visitor | Browse approved products, search by keyword or category, read reviews, view category insights. |
| Customer | Register, sign in, manage a cart, place demo orders, cancel eligible unshipped items, and manage reviews of purchased products. |
| Artist | Register for approval, sign in after approval, create/edit/delete eligible listings, add product photos, and update shipping progress for their own order items. |
| Admin | Review artist applications, approve or reject new listings, and set product commission rates. |

The **Insights** page runs a MongoDB aggregation pipeline to group approved products by category and calculate product counts and average prices.

## Built with

- **Backend:** Python, Flask, PyMongo, JWT authentication
- **Database:** MongoDB Atlas (five collections: `users`, `products`, `cart`, `orders`, `reviews`)
- **Frontend:** HTML, CSS, JavaScript served by Flask
- **Images:** HTTPS image URLs; optional Cloudinary upload from the artist form
- **Tests:** pytest/unittest and Node.js frontend regression scripts

## Run locally

The steps below use **Windows PowerShell** from the project root. You'll need Python, access to a MongoDB Atlas database, and Node.js only if you want to run the JavaScript regression scripts.

1. Clone the repository and open the folder in VS Code (replace `USERNAME/REPOSITORY` with the actual GitHub location):

   ```powershell
   git clone https://github.com/USERNAME/REPOSITORY.git EcoCraft_Marketplace
   cd EcoCraft_Marketplace
   ```

   If you downloaded the repository as a ZIP instead, extract it and open the folder containing `app/`, `requirements.txt`, and `README.md`. Use that folder for the commands below.

2. Create a virtual environment and install the dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

3. Make a local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

   Edit `.env` with your own Atlas connection details and a randomly generated `JWT_SECRET_KEY` (at least 32 characters). The example file explains the required variables. **Do not commit `.env` or post connection details online.**

   By default, database writes are disabled. For the team's shared `ecocraft` database, enable demo writes only after backing up the data and agreeing on which new accounts to use:

   ```dotenv
   MONGO_DB_NAME=ecocraft
   ENABLE_TEAM_DEMO_WRITES=true
   ENABLE_DEV_WRITES=false
   ```

   The application limits permitted updates to newly registered demo accounts and their records. Existing seeded users and products are kept read-only. Enabling the flag does not remove the need for a backup or appropriate database permissions.

4. Start the application:

   ```powershell
   .\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000
   ```

5. Open **http://127.0.0.1:5000/** in your browser.

   Use `/api/health` to check the Flask service and `/api/health/db` to check the MongoDB connection. A successful database check returns `{"database":"ecocraft","status":"ok"}` when configured for the shared database.

   Product uploads from your computer also require Cloudinary settings in `.env`. You can use a direct HTTPS image URL instead; see [Product images](docs/PRODUCT_IMAGE_UPLOAD.md).

## Try the marketplace

A full demo is easiest to follow with three accounts: customer, artist, and an existing team admin. Public registration does **not** create administrator accounts.

1. Open **Explore** to browse and search the approved catalog. Open **Insights** to see the MongoDB category aggregation.
2. Register a customer and an artist. The new artist must be approved before signing in.
3. Sign in as a team admin, open **My studio / account**, and approve the new artist.
4. Sign in as that artist and submit a product. Add a photo if you have one. The product starts pending review.
5. Return as admin to approve the product and, if needed, set its commission rate.
6. As a customer, add the newly approved product to your cart, adjust quantity, and check out. Confirm the order and inventory change in Atlas.
7. Test the order workflow: an eligible item can be cancelled before shipping, or the artist can mark it shipped and then delivered. Customers can review products they purchased.

**Why the extra accounts?** Products from the original seeded dataset can be viewed, but the protected shared-database demo only allows purchases and edits involving newly eligible demo records.

## Tests

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node scripts/test_frontend_auth.cjs
node scripts/test_frontend_images.cjs
```

The Python and JavaScript suites check application behavior without changing the live Atlas data. To check your running server using read-only requests:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_api.py
```

The smoke-test script also supports an **explicit write mode**, which creates real demo records. Read [Testing and verification](docs/TEST_PLAN.md) before using it. Manual frontend testing and database inspection are part of the course demonstration; automated tests alone do not cover every live transaction scenario.

## MongoDB design

Our database uses five collections:

- `users`: customer, artist and administrator accounts, with embedded profile information
- `products`: artist-owned listings, inventory and approval details
- `cart`: one cart per customer, containing embedded product/quantity items
- `orders`: customer orders with embedded line-item and price snapshots
- `reviews`: reviews linked to a product, customer and purchased order

The project uses references between collections where data has an independent lifecycle, and embedding where related information is normally retrieved together. MongoDB validators and indexes enforce additional constraints, including unique emails and cart ownership.

Professor Yu's database recreation requirement is included as `scripts/recreate_demo.js`. **It recreates only the isolated `ecocraft_submission_dev` database**, not the shared `ecocraft` database. Do not run it as part of normal app startup.

## Project files

```text
app/                 Flask routes, validation, authentication and web UI
scripts/             Atlas audit, test helpers and isolated recreation script
tests/               Python test suite
reports/             Schema/index audit used by the tests
docs/                 API details, architecture, image setup and test checklist
.env.example         Configuration template (no working credentials)
requirements*.txt    Python dependencies
```

## Documentation

- [Architecture and database flow](docs/ARCHITECTURE.md)
- [API endpoints and validation](docs/API_CONTRACT.md)
- [Product images and Cloudinary setup](docs/PRODUCT_IMAGE_UPLOAD.md)
- [Testing and manual verification](docs/TEST_PLAN.md)
- [Contributing and repository guidelines](CONTRIBUTING.md)

## Notes

EcoCraft is a local coursework application, not a public shopping service. It does not process payments or provide password recovery, returns/refunds, or production audit logging. For a shared class demo, use only records the team has approved for testing, and keep the Atlas/Cloudinary secrets outside Git.
