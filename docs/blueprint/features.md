# Features and User Flows

## 1. Centralized login

Staff enters the clinic username and password. On success, the server rotates the session, creates a secure authenticated cookie, and opens the dashboard. Repeated failures are rate-limited. Sessions expire after inactivity.

## 2. Dashboard

Show total registrations and active, redeemed, expired, and cancelled coupons. Display recent activity and delivery failures that require attention. Never show complete tokens.

## 3. Patient registration

Collect name, mobile, optional email, age, gender, city, doctor, campaign, offer, and separate email/WhatsApp consent. Validate all fields, show understandable errors, and prevent accidental duplicate submission.

## 4. Offer and QR issuance

Create a unique coupon with a cryptographically random opaque token and server-controlled expiry. Generate a QR containing only the token or an HTTPS validation URL carrying that token. Provide protected view, print, and download actions.

## 5. Automatic confirmation delivery

After registration commits:

- Queue an email containing confirmation details and the QR image.
- Queue a WhatsApp confirmation and QR when valid consent and provider messaging permission exist.
- Record `QUEUED`, `SENT`, `DELIVERED`, `FAILED`, or `SKIPPED` independently for each channel.
- Permit a controlled resend without issuing another coupon.

WhatsApp cannot send an unrestricted business-initiated message outside the provider's allowed customer-service window. The system must either use an approved initiation method or let the patient initiate the conversation before sending a free-form confirmation.

## 6. QR scanning and validation

Staff can scan through the device camera or paste the token. The server returns exactly one state: valid, redeemed, expired, cancelled, or invalid. Only authenticated staff can see patient information.

## 7. One-time redemption

For a valid coupon, show a confirmation screen and optional operator-name field. Redemption must be an atomic update that succeeds only while the coupon is active and unexpired. A second request must fail safely.

## 8. Patient and coupon search

Search by patient name, normalized mobile number, patient ID, or coupon ID. Filter by offer, campaign, delivery state, and coupon state. Tokens must not be searchable or displayed in full.

## 9. Audit history

Record login events, registration, QR issuance, validation result, redemption, cancellation, delivery attempts, resend, password change, backup, and restore. With centralized login, events identify the shared clinic account; an optional operator name can improve traceability.

## 10. Administration

- Change centralized password
- Rotate all sessions
- Enable or disable offers
- Cancel a coupon with a reason
- View failed deliveries and resend
- Export a minimal operational report
- Start and verify backups

## End-to-end workflow

```text
Central login
    ↓
Register patient + capture consent
    ↓
Select offer
    ↓
Save patient and create one-time coupon
    ↓
Generate secure QR
    ↓
Queue email and eligible WhatsApp confirmation
    ↓
Patient presents QR
    ↓
Staff scans or enters token
    ↓
Server validates state and expiry
    ↓
Staff confirms redemption
    ↓
Atomic update to REDEEMED + audit event
    ↓
Any later scan reports ALREADY USED
```

