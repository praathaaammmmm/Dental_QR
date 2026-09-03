# Smriti Raj Dentistry QR Offer System — PRD

## Product goal

Deliver a clinic-ready pilot by Saturday, 5 September 2026 that lets authorized clinic staff register patients, issue a patient-specific dental offer, deliver a confirmation and QR code, validate it at the clinic, and redeem it exactly once.

## Target users

- Clinic administrator using the shared clinic login
- Doctors and reception staff using the authenticated clinic session
- Patients receiving and presenting their offer QR

## Core problem

The clinic needs a simple and reliable way to issue complimentary offers without reusable paper coupons, expose minimal patient information in the QR, and confirm whether an offer is valid, expired, cancelled, or already redeemed.

## Pilot scope

- One centralized clinic login; no individual user accounts
- Patient registration and consent capture
- Offer selection
- Unique opaque QR token and downloadable QR image
- Ten-day validity calculated by the server
- Automatic confirmation email with QR
- WhatsApp confirmation with QR through the official WhatsApp Business platform
- Camera scanning and manual token entry
- Atomic, one-time redemption
- Dashboard, patient search, filters, delivery status, and audit history
- Backup and restore procedure
- Railway-hosted deployment backed by PostgreSQL
- Capacity for approximately 500 registrations and one-time QR coupons per week

## Out of scope for the Saturday pilot

- Individual doctor accounts and granular roles
- Billing, appointment scheduling, or electronic health records
- Clinical diagnosis or treatment notes
- Multiple clinics or franchises
- Native Android or iOS applications
- Advanced analytics

## Success criteria

- Staff can complete registration and generate a QR in under two minutes.
- A valid QR can be scanned from a phone and redeemed once.
- A second redemption attempt is rejected.
- Invalid, expired, cancelled, and redeemed states are clearly distinguished.
- Email delivery is queued automatically and its outcome is recorded.
- WhatsApp delivery follows provider rules and records sent/failed status.
- No patient details are embedded in the QR.
- The system can be backed up and restored before pilot launch.

## Functional requirements

1. Require centralized authentication for every clinic screen.
2. Validate and normalize all registration inputs server-side.
3. Record patient consent for email and WhatsApp separately.
4. Create one patient, one selected offer, one coupon, and one random token in a transaction.
5. Never store patient information inside the QR payload.
6. Queue delivery only after successful database commit.
7. Allow staff to resend a failed confirmation without creating a new coupon.
8. Validate expiry and coupon state on the server.
9. Redeem through an atomic database update.
10. Record security and business events in the audit log.

## Non-functional requirements

- Responsive on clinic computers and modern phones
- HTTPS for any network-accessible deployment
- Secure cookies, CSRF protection, rate limiting, and security headers
- Friendly error messages without internal stack traces
- Structured logs with secrets and patient data redacted
- Automated tests for the complete critical workflow
- Support approximately 500 registrations concentrated on Sunday without losing registrations or issuing duplicate coupons
- Keep registration responsive while email and WhatsApp delivery runs asynchronously

## Open decisions

- Email provider and verified sender
- WhatsApp Business account, phone number, access token, and messaging eligibility
- Clinic branding, address, support number, and final offer text
- Backup destination and responsible operator
