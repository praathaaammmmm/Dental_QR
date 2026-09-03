# Security Baseline

## Purpose

This document defines the minimum security controls required before the Smriti Raj Dentistry QR system handles real patient information. The Saturday release is a controlled pilot, not a claim of full regulatory certification.

## Launch-blocking controls

The pilot must not use real patient data unless all of the following pass:

- No default username, password, signing key, encryption key, or provider credential
- Centralized password stored only as an Argon2id or bcrypt hash
- HTTPS for any access beyond the server computer
- Authenticated access to all patient, coupon, QR, audit, and administration pages
- Secure session cookie with `HttpOnly`, `Secure`, and suitable `SameSite` settings
- Session rotation after login and expiration after inactivity
- Login rate limiting and temporary lockout/backoff
- CSRF protection on every state-changing request
- Strict server-side input validation
- Atomic one-time redemption
- QR tokens absent from logs and routine screens
- Safe error responses with no stack traces or database details
- Tested backup and restore
- `.env`, database files, backups, and generated QRs excluded from version control

## Centralized login

- Use one clinic username and one strong clinic password.
- Never compare against or store a plaintext password.
- Require at least 14 characters and reject known placeholder values.
- Keep the password hash outside source code, preferably in the database or a protected bootstrap secret.
- Rotate the session identifier after successful login.
- Expire inactive sessions after a configurable period.
- Provide a way to rotate the session signing key and force logout everywhere.
- Do not expose whether a username or password was incorrect.
- Record successful and failed login events without recording submitted credentials.

Because the account is shared, audit records identify the clinic account rather than a specific doctor. An optional operator-name field may be recorded during registration or redemption, but it is not an authentication factor.

## Application controls

- Permit only configured hostnames.
- Set Content Security Policy, frame protection, MIME-sniffing protection, referrer policy, and appropriate permissions policy.
- Restrict CORS; same-origin server-rendered pages generally do not need broad CORS.
- Disable debug mode and public API documentation in the pilot environment unless explicitly required.
- Enforce request-size and field-length limits.
- Use parameterized SQLAlchemy queries.
- Return generic user errors and write redacted operational details to protected logs.
- Generate a request ID for tracing failures without exposing patient data.

## QR and coupon controls

- Generate at least 256 bits of randomness for bearer tokens.
- Put no patient or offer details directly in the QR.
- Prefer storing a cryptographic hash of the raw token.
- Never show or log complete raw tokens.
- Use server-side UTC time for expiry.
- Redeem with one conditional database update requiring `ACTIVE` and `expires_at > now`.
- Do not accept coupon state, expiry, patient ID, or offer ID from the QR as authoritative.
- Store generated QR files outside public static directories.
- Verify database ownership before serving any QR file.
- Remove QR files according to the retention policy.

## Messaging controls

- Send only after applicable consent is recorded.
- Use official email and WhatsApp providers.
- Store provider tokens only in environment secrets or a secret manager.
- Use idempotency keys so retries cannot create duplicate messages.
- Verify webhook signatures before accepting delivery updates.
- Do not include unnecessary patient or treatment information in confirmations.
- Mask recipient addresses and provider errors in dashboards and logs.
- Treat a delivery failure independently from coupon creation.

## Database and backup controls

- Use a dedicated, least-privileged database account in hosted deployments.
- Do not expose the database port publicly.
- Restrict database, QR, backup, and log directories to the service account and operator.
- Encrypt backups and protect the encryption key separately.
- Test restoration before launch and periodically afterward.
- Use migrations for schema changes and make a backup before applying them.

## Secrets inventory

- Session signing key
- Centralized password hash or bootstrap secret
- Database password
- CSRF secret if separately configured
- Email credential/API key
- WhatsApp access token
- WhatsApp application secret and webhook verification token
- Backup encryption key

Every secret requires an owner, storage location, rotation method, and revocation process.

## Required security tests

- Unauthenticated access redirects or rejects correctly.
- Login rate limiting activates.
- Session identifier changes after login.
- Expired sessions cannot access protected pages.
- Requests without valid CSRF tokens fail.
- Malformed and oversized inputs fail safely.
- Invalid, expired, cancelled, and redeemed QRs are distinguished.
- Concurrent redemption produces exactly one success.
- Path traversal cannot retrieve arbitrary files.
- Tokens and secrets do not appear in logs.
- Forged webhooks are rejected.
- Duplicate delivery jobs do not duplicate messages.
- Backup restoration produces a usable application.

## Vulnerability reporting

Until a permanent contact is chosen, security problems should be reported directly to the designated clinic system owner and must not include real patient information in ordinary email or chat. Record the report time, affected system, observed behavior, and safe reproduction steps.

