# Smriti Raj Dentistry — Patient-Specific QR Offer Management System

A local FastAPI + SQLite prototype for campaign registrations and patient-specific complimentary offers.

## Offers
1. Free In-House Zirconia Crown
2. Free In-House Aligner Scan

Each registration creates:
- a patient record
- exactly one selected offer
- a unique opaque `SRD-...` secure token
- a unique QR image
- a 10-day server-time expiry
- a one-time-use state stored in the database

The QR payload contains only the secure token; patient information is not embedded in the QR.

## Windows setup

Open PowerShell in this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Generate secure admin/clinic-login values:

```powershell
py scripts/create_clinic_credentials.py
```

Copy the generated values into `.env`. Never commit `.env` or paste the real password into source code or chat.

Then run:

```powershell
py -m uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Authentication and account setup

The application has one shared login page at `/login`. It accepts either an administrator account or an active staff account, then automatically sends the user to the appropriate workspace.

### Administrator account

This is the single administrator account for the Admin CRM, campaign management, analytics, staff management, and other admin-only functions. Its credentials come only from the environment:

- `CLINIC_USERNAME`
- `CLINIC_PASSWORD_HASH` (an Argon2 hash)

Use `py scripts/create_clinic_credentials.py` to generate the values, then place them in the local `.env` file or your deployment environment. The default username is `smritiraj-clinic`. This account is not stored in `staff_users`.

### Staff accounts

Hospital staff use the same `/login` page to enter the registration workspace, where they can register patients and validate or redeem QR offers. Their credentials are stored as Argon2 password hashes in the `staff_users` database table. An administrator creates and manages these accounts in **Admin CRM → Staff**.

## Development seed data

After the app has been started at least once:

```powershell
py seed.py
```

This adds clearly marked development test data:
- Rahul Sharma — Zirconia Crown
- Amit Kumar — Aligner Scan
- Neha Singh — Zirconia Crown

## Complete workflow test

1. Log in.
2. Click **Register Patient**.
3. Enter the patient information.
4. Select exactly one offer.
5. Click **REGISTER PATIENT & GENERATE QR**.
6. The system stores the patient and offer and generates a unique QR.
7. Download or print the QR.
8. Go to **Scan / Validate QR**.
9. Use the camera scanner where supported, or paste/type the token printed/generated for the QR.
10. A valid active QR displays the patient and offer to the authenticated clinic user.
11. Click **REDEEM OFFER** and confirm.
12. Scan/validate the same token again. It must show **OFFER ALREADY USED**.
13. Search the patient in **Patients**.
14. Check **Offers** for the QR status.

## Security behavior

- QR contains only an opaque cryptographically random token.
- Patient name, mobile, email, age, etc. are never placed into the QR payload.
- Validation is always server-side against SQLite.
- Server-side UTC time controls the 10-day validity window.
- Redemption uses a conditional database update requiring `status = ACTIVE` and `expires_at > now`.
- Therefore, two simultaneous redemption requests cannot both transition the same coupon from ACTIVE to REDEEMED.
- Secrets are loaded from environment variables and are not hard-coded into source.

## Email and WhatsApp delivery (n8n)

Actual email/WhatsApp sending is handled by n8n, not FastAPI directly — see
[`n8n/README.md`](n8n/README.md) for the full setup guide (importing the workflow,
credentials, dispatcher scheduling, and an end-to-end test checklist), and
[`docs/blueprint/n8n-delivery-contract.md`](docs/blueprint/n8n-delivery-contract.md) for
the payload/callback contract.

Local prototype mode prepares/logs the intended email data and QR file; it does not require an email provider.

Later, configure:

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
```

No SMTP credentials should be committed to source control.

## WhatsApp

The prototype does not use unofficial automation. It creates a prefilled `wa.me` link and records the action as prepared.

For production, replace `app/whatsapp_service.py` with the official WhatsApp Business Cloud API integration and keep credentials in environment variables.

## Important local-network note

`127.0.0.1` works only on the same computer. If you want a phone/tablet at a campaign to access the local server over Wi-Fi, bind Uvicorn to the computer's LAN interface and use the computer's LAN IP as `PUBLIC_BASE_URL`. The QR in this prototype contains only the opaque token, so camera scanning can also be used as a token input.

## Tests

Run:

```powershell
py -m pytest -q
```

## Encrypted SQLite backups

Backups never fall back to plaintext. Generate a local Fernet key once and put
it in your uncommitted `.env` file:

```powershell
py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```text
BACKUP_ENCRYPTION_KEY=<generated key>
BACKUP_DIR=backups
BACKUP_RETENTION_DAYS=30
```

Run the scheduled job daily from Task Scheduler or the private worker:

```powershell
py -m app.backup_job
```

The job snapshots SQLite safely, encrypts the artifact with Fernet, records a
checksum of the encrypted file, and keeps the configured retention window.
Keep the key outside the backup directory and copy encrypted artifacts to a
separate protected location. The SQLite backup job intentionally refuses a
non-SQLite database; use the managed PostgreSQL backup process after migration.

## QR delivery dispatch and expiry sweep jobs

Two more externally scheduled jobs, run the same way as the backup job:

```powershell
py -m app.delivery_job
py -m app.expiry_job
```

`app.delivery_job` sends queued QR notifications (registration, manual resend, and
retries) to n8n and must run every **1 minute** in production-like environments — it is
the only place the app makes outbound delivery HTTP calls; registration and manual resend
only ever write a durable `PREPARED` record. `app.expiry_job` expires stale QR offers and
triggers 24–48h expiry reminders; running it every few minutes is sufficient. See
`docs/blueprint/n8n-delivery-contract.md` for the full delivery payload/callback contract,
required for whoever builds the actual n8n workflows.

## Database migrations

Local development may create SQLite tables automatically for convenience. Staging and production never create tables at application startup; apply Alembic migrations first:

```powershell
py -m alembic upgrade head
```

Check that the models and migrations agree:

```powershell
py -m alembic check
```

## Railway deployment preparation

The repository includes a non-root production `Dockerfile`, PostgreSQL support, Alembic migrations, `/health` liveness, and `/ready` database readiness. Follow `docs/deployment-railway.md` when the deployment step is approved. Do not deploy with real patient data before the security, backup, pipeline, and launch gates pass.

The test suite covers:
- registration
- QR token creation
- uniqueness
- 10-day expiry
- valid QR
- invalid QR
- redemption
- second redemption
- different offers
- patient search

## Project structure

```text
smritiraj_qr_system/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── auth.py
│   ├── qr_service.py
│   ├── coupon_service.py
│   ├── email_service.py
│   ├── whatsapp_service.py
│   ├── audit_service.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── patients.py
│   │   ├── coupons.py
│   │   └── validation.py
│   ├── templates/
│   └── static/
├── generated_qr/
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
├── seed.py
└── README.md
```

## Production migration path

The application is intentionally modular. SQLite can later be replaced with PostgreSQL by changing `DATABASE_URL`. SMTP and official WhatsApp Cloud API can be configured independently. Before public deployment, add HTTPS, stronger multi-user authentication/authorization, CSRF protection, rate limiting, encrypted backups, proper secrets management, and a privacy/retention policy appropriate for patient data.
