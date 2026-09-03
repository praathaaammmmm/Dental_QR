# Incident Response

## What counts as an incident

- Lost or disclosed clinic password
- Suspicious login or session activity
- Patient information sent to the wrong recipient
- QR redeemed without authorization
- Leaked `.env`, database, backup, logs, or provider tokens
- Malware, dependency compromise, or unauthorized server access
- Missing, altered, or corrupted records
- Prolonged service or provider outage during clinic operations

## Immediate response

1. Stop further exposure without destroying evidence.
2. Record discovery time, reporter, affected environment, and visible symptoms.
3. Rotate the clinic password/session key if account access may be affected.
4. Revoke and rotate exposed provider or database credentials.
5. Disable affected messaging or public access when necessary.
6. Preserve protected logs and a database snapshot for investigation.
7. Identify affected patients and records.
8. Escalate to the clinic owner and designated technical contact.

## Recovery

- Patch or remove the root cause.
- Restore from a verified clean backup when integrity is uncertain.
- Test authentication, patient lookup, validation, redemption, and messaging.
- Monitor for renewed suspicious behavior.
- Re-enable services gradually and document the decision.

## Follow-up

- Maintain a timeline and list of affected data.
- Determine notification duties with qualified legal/privacy guidance.
- Notify affected people through an approved channel when required.
- Record corrective actions, owners, and deadlines.
- Add a regression test or operational control for the root cause.

## Saturday contact sheet

Before launch, fill in and keep offline:

- Clinic incident owner:
- Technical contact:
- Hosting contact:
- Email provider support:
- WhatsApp/Meta account owner:
- Backup location:
- Credential revocation instructions:

