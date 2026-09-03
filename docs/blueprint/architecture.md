# Architecture

## System shape

The pilot is a server-rendered FastAPI application. Clinic browsers communicate with one application server. The server owns authentication, validation, QR issuance, expiry, redemption, delivery jobs, auditing, and database access.

```text
Clinic browser / phone
        |
      HTTPS
        |
FastAPI application
  |       |        |
Database  Job queue  Protected QR storage
             |
       Email + WhatsApp providers
             |
      Delivery-status webhooks
```

## Confirmed hosting profile

- Hosting: Railway
- Expected volume: approximately 500 new registrations per week
- Usage pattern: each registration creates one patient-specific, one-time QR coupon
- Capacity assessment: this is a light workload; correctness, delivery reliability, backups, and security matter more than horizontal scale

The Railway project should contain:

```text
Public FastAPI web service
        |
Railway private network
   ├── PostgreSQL service
   └── Delivery worker service
        |
Email and WhatsApp providers
```

Start with one web instance and one small worker. Redis is optional at this volume; a PostgreSQL outbox/job table is simpler and keeps delivery jobs durable. Add Redis only if operational needs justify another service.

## Recommended technology stack

- Python 3.12
- FastAPI and Uvicorn
- Jinja2 templates with minimal JavaScript
- SQLAlchemy 2 and Alembic migrations
- Railway PostgreSQL using its private `DATABASE_URL`; do not use SQLite on Railway
- PostgreSQL-backed durable delivery outbox for the pilot
- Official transactional email provider or SMTP
- Official WhatsApp Business Cloud API
- Pytest for automated tests

## Proposed project structure

```text
app/
├── routes/             # HTTP pages and form endpoints
├── services/           # patients, coupons, delivery and auditing
├── security/           # passwords, sessions, CSRF and rate limits
├── templates/          # web and email templates
├── static/             # styles, scanner script and clinic assets
├── models/             # database models
├── schemas/            # validated input/output models
├── jobs/               # email/WhatsApp delivery and retries
├── config.py
├── database.py
├── exceptions.py
└── main.py
migrations/             # Alembic migrations
tests/
scripts/                # admin setup, backup, restore and cleanup
docs/
```

## Core data entities

- `ClinicAccount`: shared username, password hash, enabled state, password-change timestamp
- `Patient`: identifiers and minimum contact information
- `Consent`: channel, status, timestamp, source, and policy version
- `Offer`: name, description, validity, active state
- `Coupon`: patient, offer, opaque token hash, status, expiry, redemption details
- `Delivery`: channel, attempt count, provider ID, status, error code, timestamps
- `AuditEvent`: actor label, action, target, request ID, timestamp, safe metadata

## Security boundaries

- Browser input is untrusted and always validated.
- Provider webhooks are untrusted until their signatures are verified.
- Secrets come only from environment variables or a secret manager.
- QR tokens are bearer credentials; logs and analytics must never expose them.
- Files are served only after authentication and database authorization checks.
- Database and backup access is restricted to the application and operator.

## Key flows

### Registration

Validate input → save patient/coupon transaction → generate protected QR → commit → enqueue email and WhatsApp jobs → show confirmation.

### Validation and redemption

Normalize token → retrieve coupon → calculate current state → show minimum necessary patient/offer data → confirm → atomic status update → audit result.

### Delivery

Claim idempotent job → send through provider → save provider ID/status → accept verified webhook updates → retry temporary failures with limits.

## Railway deployment

- Deploy the application from a private GitHub repository or a controlled Railway CLI workflow.
- Provision Railway PostgreSQL and reference its private `DATABASE_URL` from the application and worker.
- Run Alembic as the Railway pre-deploy migration command.
- Give only the web service a public domain; the database and worker remain private.
- Configure the public base URL and HTTPS-only cookies from the final Railway domain or clinic custom domain.
- Store secrets in Railway service variables, never in repository files.
- Do not rely on the web container filesystem for permanent QR storage. Prefer generating QR images on demand from the protected token, or use protected persistent/object storage with retention cleanup.
- Expose only the verified provider-webhook endpoints publicly; clinic pages remain authenticated.
- Configure health checks, structured logs, database backups, and an external uptime check.

## Workload profile

- Approximately 500 registrations are expected during Sunday each week rather than evenly throughout the week.
- Each registration may create two outbound delivery jobs: email and WhatsApp.
- Size and test for short concurrent registration and QR-validation bursts, not only the low weekly average.
- Registration commits independently of provider availability; durable delivery jobs handle sending and retries afterward.
- One web service, one private worker, and Railway PostgreSQL are appropriate for the pilot when verified by load testing. Redis is not required initially because PostgreSQL can provide the durable delivery outbox.
