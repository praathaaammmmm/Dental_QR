# Privacy and Data Retention

## Principles

- Collect the minimum information needed to issue and redeem the campaign offer.
- Explain why contact details are collected and how confirmations will be delivered.
- Record email and WhatsApp consent separately.
- Do not reuse campaign data for unrelated marketing without a valid basis and new consent.
- Do not place patient details inside QR codes.
- Restrict exports and access to authorized clinic operations.

## Proposed retention schedule

The clinic owner must approve the final periods after considering applicable Indian healthcare, privacy, tax, and legal obligations.

| Data | Proposed pilot retention |
|---|---|
| Raw QR image | Until coupon expiry plus 30 days |
| Coupon and redemption record | 12 months unless a longer legal/business period is approved |
| Patient campaign contact data | 12 months or earlier withdrawal/deletion where applicable |
| Delivery logs | 90 days, excluding required audit evidence |
| Security and audit logs | 12 months |
| Encrypted backups | Rolling 30 days |

## Patient-facing notice must state

- Clinic identity and contact point
- Information being collected
- Purpose of registration and QR issuance
- Email and WhatsApp delivery choices
- Retention period
- Who receives the information, including messaging providers
- How the patient can request correction, withdrawal, or deletion where applicable

## Operational rules

- Mask mobile and email in list views.
- Do not include age, gender, doctor, or campaign information in messages unless necessary.
- Do not copy real patient data into development, screenshots, bug reports, or chat tools.
- Log deletion and correction actions without retaining the deleted sensitive value.
- Delete expired QR files through a scheduled, audited cleanup job.
- Encrypt exports and set an expiry for shared files.

