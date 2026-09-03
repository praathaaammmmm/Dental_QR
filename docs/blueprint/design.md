# Design System and Screen Specification

## Design goals

The interface should feel calm, clinical, trustworthy, and quick to operate. Doctors and reception staff must understand status and the next action without training.

## Visual direction

- Primary: deep teal `#0F5C5E`
- Primary dark: `#093F41`
- Accent: warm gold `#C89B3C`
- Background: soft off-white `#F7F8F6`
- Surface: white `#FFFFFF`
- Text: charcoal `#1F2933`
- Muted text: `#66737F`
- Success: `#16794A`
- Warning: `#A86400`
- Danger: `#B42318`
- Border: `#D7DEDE`

Final colors must be checked for WCAG AA contrast.

## Typography

- Use a locally served, highly legible sans-serif or the operating-system font stack.
- Base text: 16px minimum.
- Form labels: 14–16px with medium weight.
- Page title: 28–32px.
- Avoid thin font weights and decorative type for operational content.

## Layout rules

- Responsive single-column forms on phones and two-column forms on larger screens.
- Maximum content width around 1200px.
- Minimum 44px touch targets.
- Persistent navigation for Dashboard, Register, Patients, Validate QR, Offers, and Logout.
- Keep the primary action visible and use only one primary action per screen.

## Status presentation

Never communicate status by color alone. Use color, icon, heading, and explanation:

- `VALID` — green check, “Offer valid”
- `REDEEMED` — neutral/blue history icon, “Offer already used”
- `EXPIRED` — amber clock, “Offer expired”
- `CANCELLED` — red stop icon, “Offer cancelled”
- `INVALID` — red warning, “QR not recognized”

## Required screens

### Login

Clinic logo, centralized username/password, show-password control, concise errors, and no default-credential hint.

### Dashboard

Status summary, recent registrations, failed deliveries, and prominent Register Patient and Scan QR actions.

### Registration

Clearly grouped patient, campaign, offer, and consent sections. Preserve valid input after errors. Show a submission-progress state and block duplicate clicks.

### Registration result

Show coupon ID, offer, expiry, QR preview, email status, WhatsApp status, and print/download/resend actions. Do not display the raw token.

### Scanner and validation result

Large camera region, manual-entry fallback, permission help, and a high-contrast result card. Redemption requires a deliberate confirmation step.

### Patients and offers

Fast search, useful filters, readable tables/cards, pagination, and masked contact data in lists.

## Content style

- Use direct labels: “Register patient”, “Validate QR”, “Redeem offer”.
- State what happened and what to do next.
- Avoid technical terms, stack traces, provider payloads, or security jargon.
- Confirm destructive or irreversible actions such as cancellation and redemption.

