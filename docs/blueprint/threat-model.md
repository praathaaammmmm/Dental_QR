# Threat Model

## Protected assets

- Patient identity and contact information
- Offer eligibility and redemption state
- Raw QR bearer tokens
- Centralized login and active sessions
- Email and WhatsApp credentials
- Database, backups, logs, and audit history
- Availability of the registration and validation workflow

## Trust boundaries

```text
Patient or clinic browser
        ↓ untrusted input
Web application
        ↓ restricted credentials
Database and protected file storage
        ↓ external provider boundary
Email and WhatsApp services
        ↓ signed but untrusted callbacks
Webhook endpoints
```

## Principal threats and mitigations

| Threat | Impact | Required mitigation |
|---|---|---|
| Shared password guessed | Full clinic access | Strong hash, strong password, rate limits, secure transport, rotation |
| Session cookie stolen | Unauthorized access | HTTPS, secure cookie flags, short inactivity timeout, session rotation |
| CSRF attack | Unauthorized registration, resend, cancellation, or redemption | Per-session CSRF tokens and same-origin checks |
| QR token guessed or leaked | Unauthorized validation/redemption | High-entropy token, token hashing, no logging, minimal exposure |
| QR reused | Multiple redemptions | Atomic conditional update and unique database constraints |
| SQL/script injection | Data disclosure or browser compromise | Validated fields, SQLAlchemy parameters, auto-escaping, CSP |
| File path manipulation | Arbitrary file disclosure | Server-generated names, canonical-path validation, database ownership checks |
| Provider credential theft | Fraudulent messages or data access | Secret storage, least privilege, rotation, redacted logs |
| Forged webhook | False delivery state | Provider signature verification and replay protection |
| Duplicate background job | Repeated patient messages | Stable idempotency key and unique delivery constraints |
| Database/backup theft | Patient-data disclosure | Access control, device/disk protection, encrypted backups |
| Accidental staff disclosure | Privacy incident | Minimal displays, masking, operator guidance, automatic logout |
| Service/provider outage | Clinic workflow interruption | Local print/download fallback, durable retries, tested recovery |
| Malicious dependency | Application compromise | Locked dependencies, audits, minimal packages, controlled updates |

## Abuse cases to test

- Repeated password attempts from one and multiple addresses
- Reusing an old session after logout or secret rotation
- Posting a redemption from another website
- Editing coupon IDs in URLs
- Supplying encoded traversal sequences in QR file routes
- Entering HTML/script payloads in patient fields
- Redeeming the same coupon concurrently
- Replaying webhook events
- Triggering repeated resend requests
- Searching with oversized or malformed values
- Accessing backups, `.env`, logs, database files, or generated QRs through HTTP

## Residual risk

A centralized account cannot prove which doctor performed an action. The pilot accepts this limitation. Capture an optional operator name for important actions and restrict knowledge of the shared password to authorized clinic staff.

