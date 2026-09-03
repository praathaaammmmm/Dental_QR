# Build and Security Rules

## Non-negotiable rules

1. Never commit `.env`, credentials, access tokens, database files, backups, or generated patient QR images.
2. Never use placeholder secrets in a running pilot. Startup must fail when required secrets are absent or insecure.
3. Never embed patient data in a QR code.
4. Never log passwords, session cookies, complete QR tokens, provider access tokens, or full patient contact details.
5. Never trust browser fields, URL parameters, uploaded files, provider responses, or webhook payloads without validation.
6. Never reveal raw exceptions or database errors to users.
7. Never send email or WhatsApp without the applicable recorded consent.
8. Never make delivery success part of the coupon database transaction; provider failure must not lose a registration.
9. Never create duplicate coupons when retrying delivery.
10. Never redeem through a read-then-write sequence that permits concurrent double use.

## Authentication rules

- Use one centralized clinic account as requested.
- Store only a modern password hash, never the password itself.
- Rate-limit login attempts and record safe login events.
- Rotate the session identifier after login.
- Use `HttpOnly`, `Secure`, and appropriate `SameSite` cookie settings in HTTPS deployments.
- Expire inactive sessions and support forced logout of all sessions.
- Protect every state-changing form with CSRF tokens.

## Data rules

- Collect only information required for the campaign.
- Normalize mobile numbers and email addresses before saving.
- Define retention periods for patients, coupons, delivery logs, audit logs, and QR files.
- Restrict database and backup access.
- Encrypt backups and test restoration before launch.
- Treat health-related and contact information as sensitive.

## QR and redemption rules

- Generate tokens with a cryptographically secure random generator.
- Prefer storing a one-way hash of the token when practical.
- Compare tokens safely and avoid exposing token values in logs or dashboards.
- Evaluate expiry using server-side UTC time.
- Redemption succeeds only when status is `ACTIVE` and expiry is in the future.
- Record redemption time and the shared clinic identity; optionally capture operator name.

## Messaging rules

- Use official providers only.
- Verify WhatsApp webhook signatures.
- Use idempotency keys to avoid duplicate sends.
- Limit retries and distinguish temporary from permanent failures.
- Mask provider errors before displaying them to staff.
- Follow WhatsApp rules for business-initiated and customer-initiated messaging.

## Engineering rules

- Use database migrations; do not alter production schemas with automatic `create_all()` calls.
- Pin or lock dependencies and run dependency/security scanning.
- Keep routes thin; place business operations in services.
- Add tests for every security boundary and critical state transition.
- Review and test all generated code before pilot deployment.
- Make small, reviewable changes and preserve a known-good release for Saturday.

