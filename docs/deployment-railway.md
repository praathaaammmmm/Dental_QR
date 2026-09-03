# Railway Deployment Preparation

This is a preparation checklist, not authorization to launch production.

## Planned services

- `web`: public FastAPI service built from the repository Dockerfile
- `Postgres`: private Railway PostgreSQL service
- `worker`: private delivery worker added when email and WhatsApp jobs are implemented

## Web-service settings

- Source: `ichadlakshya/smirtiraj_dentistry_qr_`, branch `main`
- Start command: use the Dockerfile command
- Pre-deploy command: `alembic upgrade head`
- Health-check path: `/ready`
- Health-check timeout: 300 seconds
- Restart policy: on failure
- Initial replicas: one, in the Railway region closest to the clinic and database

Railway deprecated `railway.toml` for new services in 2026. Configure these settings in the Railway service initially. The mandatory CI/CD and infrastructure pipeline will capture and verify them before launch.

## Required production variables

```text
APP_ENV=production
CLINIC_USERNAME=smritiraj-clinic
CLINIC_PASSWORD_HASH=<generated Argon2 hash>
SESSION_SECRET_KEY=<generated random secret>
SESSION_MAX_AGE_SECONDS=1800
SESSION_HTTPS_ONLY=true
SESSION_VERSION=1
ALLOWED_HOSTS=<final domain>,healthcheck.railway.app
DATABASE_URL=<reference to the private Railway PostgreSQL DATABASE_URL>
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT_SECONDS=30
PUBLIC_BASE_URL=https://<final Railway or clinic domain>
```

Messaging variables remain disabled or empty until their provider integrations are implemented and verified.

## Safety checks before the first deployment

1. Confirm the GitHub repository contains no `.env`, database, backup, log, or QR files.
2. Generate production credentials locally and enter them only in Railway Variables.
3. Provision PostgreSQL before the web service.
4. Reference Railway's private database variable rather than copying it into source.
5. Confirm the pre-deploy migration succeeds.
6. Confirm `/ready` returns HTTP 200 and actually reaches PostgreSQL.
7. Keep public API documentation disabled before real-patient launch.
8. Complete backup restoration, security tests, load tests, and the CI/CD launch gate.

## Rollback rule

Application rollback and database rollback are separate decisions. Do not automatically run Alembic downgrades during a failed application deploy. Restore the previous application release first; use a reviewed forward migration or tested database recovery procedure if schema repair is required.
