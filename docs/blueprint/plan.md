# Delivery Plan

## Deadline

Clinic-ready controlled pilot: Saturday, 5 September 2026.

## Phase 0 — Decisions and access

- Create the Railway project and private GitHub repository.
- Provision Railway PostgreSQL and separate web and delivery-worker services.
- Obtain clinic branding and final offer wording.
- Confirm pilot data fields and consent language.
- Obtain email provider and WhatsApp Business access.
- Choose backup destination and pilot operator.

Exit condition: the Railway staging environment is reachable, PostgreSQL is private, and missing provider credentials have named owners.

## Phase 1 — Secure foundation

- Restructure configuration by environment.
- Add centralized account with hashed password.
- Add secure sessions, inactivity timeout, CSRF, login rate limiting, trusted hosts, and security headers.
- Add consistent validation and safe exception handling.
- Introduce migrations and production database configuration.

Exit condition: unauthenticated access, CSRF attempts, weak configuration, and repeated login attempts fail safely.

## Phase 2 — Core clinic workflow

- Complete patient registration and consent capture.
- Create offers, coupons, secure tokens, expiry states, and protected QR storage.
- Complete dashboard, patient search, QR scanning, validation, cancellation, and atomic redemption.
- Add audit events for every critical action.

Exit condition: the full workflow passes locally, including double-redemption and expiry tests.

## Phase 3 — Email and WhatsApp

- Create branded confirmation content.
- Send QR through the email provider.
- Integrate official WhatsApp delivery within provider rules.
- Add durable jobs, idempotency, retries, webhooks, delivery states, and resend controls.

Exit condition: real test recipients receive both messages and delivery outcomes appear in the dashboard.

## Phase 4 — Deployment and recovery

- Configure HTTPS and production startup.
- Protect database and generated files.
- Add encrypted backup, restore, cleanup, and secret-rotation procedures.
- Disable debug output and unnecessary API documentation.
- Prepare a short operator guide.

Exit condition: a clean deployment can be restored from backup and used from every intended clinic device.

## Phase 5 — Saturday acceptance test

Run with at least two clinic devices and two staff members:

1. Log in and verify inactivity timeout.
2. Register test patients with valid and invalid data.
3. Confirm email and WhatsApp delivery.
4. Scan QR from another phone.
5. Redeem once and reject the second attempt.
6. Verify invalid, expired, and cancelled states.
7. Simulate a provider outage and verify queued retry.
8. Restart the application and confirm persistence.
9. Back up, restore, and verify a test record.
10. Load-test at least 500 Sunday registrations together with concurrent QR validations and queued deliveries.

## Launch gate

Do not load real patient data if authentication, CSRF, one-time redemption, HTTPS/network restriction, backup restoration, safe error handling, or the CI/CD deployment pipeline fails. Before production launch, explicitly notify the owner that the pipeline and launch checklist are ready and obtain confirmation to proceed. If WhatsApp is unavailable, launch with email and printed/downloadable QR while clearly marking WhatsApp as unavailable.

Before launch, stop and review this gate with the user. A successful Railway deployment or passing unit tests alone is not approval to launch.
