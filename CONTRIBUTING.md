# Working on EcoCraft

EcoCraft is a shared class project. Please keep changes focused and review them with the team before merging. The existing Flask backend, frontend and MongoDB schema are already integrated; changes to any one of those areas can affect the others.

## Before you change anything

- Create a branch for your work instead of editing the main branch directly.
- Read the root [README](README.md), especially the database write safeguards.
- Keep your personal `.env`, virtual environment and credentials on your computer.
- Do not change or delete the original seeded Atlas records as part of a test.

## Test your changes

Run the Python suite after backend or shared-model changes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For frontend changes, also run:

```powershell
node scripts/test_frontend_auth.cjs
node scripts/test_frontend_images.cjs
node --check app/static/marketplace.js
```

If you change an API contract, update [docs/API_CONTRACT.md](docs/API_CONTRACT.md). If you change setup or a user-facing feature, update the README or relevant guide. For manual workflow checks, use the [test plan](docs/TEST_PLAN.md).

## Database and security

The shared database is `ecocraft`. Only newly eligible demo accounts and their related documents should be used for write testing. The original user and product records must remain unchanged. Routine tests should not run admin-creation scripts, database preparation scripts, or the separate database recreation script.

`.gitignore` excludes `.env`, local environments, caches, database backups and editor/runtime state. It does not erase a secret already committed in Git history. If credentials were accidentally committed, rotate them and correct the repository history before publishing.

## Opening a pull request

Describe what changed, why it was needed, and how you tested it. Include screenshots only for user-interface changes, and make sure they do not reveal credentials, private customer details, or access tokens. Avoid committing generated files or outdated setup notes.

The class team should agree on repository visibility, attribution and licensing before making the project public.
