# n8n QR delivery contract

This document is the reference for building the actual n8n workflows later. It describes
the FastAPI boundary that already exists: the outbound payload FastAPI sends to n8n, the
callback payload n8n must send back, authentication, and the delivery state machine.
**No n8n workflow, SMTP, SendGrid, SES, or WhatsApp Cloud API integration is built yet** —
this contract is what any future implementation of those must conform to.

## Ownership

- **FastAPI owns**: patient registration, QR validity, `DeliveryLog` records, delivery
  state transitions, retry logic, callback authentication, audit trail.
- **n8n owns**: email provider orchestration, WhatsApp provider orchestration, provider
  delivery-status webhooks, and calling FastAPI's callback endpoint.

## Durable outbox pattern

FastAPI never calls n8n from a request path. Registration and manual resend only ever
write a `PREPARED` `DeliveryLog` row (a durable local record) and commit — no network call
happens inline, so a slow or unavailable n8n endpoint can never block or roll back a
registration or a staff action. A separate scheduled worker, `app/delivery_job.py`, is the
only place outbound HTTP calls to n8n are made. Run it every 1 minute in production-like
environments:

```
* * * * * cd /path/to/app && python -m app.delivery_job
```

## Delivery intents and attempts

- A **delivery intent** (`delivery_intent_key`) is created once per logical delivery: one
  per channel at registration (email and/or WhatsApp), one per manual resend, one per
  expiry reminder. It is shared by every retry attempt for that same intent and is not
  unique — it groups rows together, it does not identify a single row.
- Each **attempt** is one `DeliveryLog` row, with a unique `idempotency_key` sent to n8n
  and required on the matching callback. `attempt_number` starts at 1 and increments by 1
  for each retry of the same intent. A manual resend is always a **new intent** starting at
  attempt 1 — it never continues the retry count of the original registration delivery.

## State machine

```
PREPARED → SENDING → SENT → DELIVERED
PREPARED → SENDING → FAILED
SENT → FAILED
FAILED → (new row, same delivery_intent_key, attempt_number + 1) → PREPARED
```

No row ever moves backward, and no row is ever mutated to represent a retry — a retry is
always a new row. Old `FAILED` rows are permanent history.

**Dispatcher-driven transitions** (internal, not via callback):

| From | To | Trigger |
|---|---|---|
| `PREPARED` | `SENDING` | dispatcher atomically claims the row |
| `SENDING` | `SENT` | `trigger_delivery` call to n8n succeeds |
| `SENDING` | `FAILED` | `trigger_delivery` call fails, or stale-dispatch recovery |

**Callback-driven transitions (Option A)** — chosen because no known provider in this
project's scope reports `DELIVERED` before a `SENT` confirmation is persisted:

| From | To |
|---|---|
| `SENDING` | `SENT` |
| `SENDING` | `FAILED` |
| `SENT` | `DELIVERED` |
| `SENT` | `FAILED` |

Any other transition request (e.g. `SENDING → DELIVERED`, or anything out of a terminal
state) is rejected with `409`. A callback reporting the row's **current** status again is
a safe no-op (`200 {"status": "ok", "noop": true}`) — no field mutation, no duplicate audit
entry.

## Dispatcher claiming and the callback race

The dispatcher claims work with a single conditional `UPDATE`:

```sql
UPDATE delivery_logs SET status='SENDING', dispatched_at=:now
WHERE id=:id AND status='PREPARED'
```

Only one worker can win each row (`rowcount == 1`), so two dispatcher processes running
concurrently, or the same dispatcher run twice, never double-claim a row.

**After** the dispatcher calls n8n, it persists the outcome with another conditional update:

```sql
UPDATE delivery_logs SET status=:new_status, ... WHERE id=:id AND status='SENDING'
```

This matters because an n8n callback can race ahead of the dispatcher's own outcome-persist
step and already move the row to `SENT`/`DELIVERED`/`FAILED` first. If that happens, the
conditional update above matches zero rows — the dispatcher does **not** overwrite the
callback's result; it simply does nothing further for that row. This is covered by
`tests/test_delivery_dispatch.py::test_dispatcher_does_not_overwrite_row_already_resolved_by_racing_callback`.

## Stale `SENDING` recovery

`DELIVERY_STALE_SENDING_SECONDS` (default `300`). At the start of every dispatcher tick,
any `SENDING` row whose `dispatched_at` is older than this timeout is moved to `FAILED`
with a safe reason and left `retryable` (unless already known permanent), so the normal
retry process picks it up as a new attempt on the same intent.

**At-least-once delivery tradeoff, accepted deliberately**: if n8n actually received and
sent the notification but the dispatcher process crashed before persisting `SENT`, the
stale-recovery sweep will mark that row `FAILED` and a later retry may cause the patient to
receive a duplicate message. This is accepted in favor of never silently losing a
notification.

## Unconfigured n8n

If `N8N_WEBHOOK_URL` is not set, the dispatcher performs stale-recovery only and returns
without claiming or sending anything — `PREPARED` rows are left untouched, never falsely
marked `SENT` or `FAILED`.

## Retry policy

- Maximum `N8N_DELIVERY_MAX_RETRIES` attempts per intent (default **3**).
- Backoff: **2 minutes** before attempt 2, **10 minutes** before attempt 3. No attempt 4.
- Only the **latest** attempt for an intent is ever eligible for retry, and only if it is
  `FAILED` and `retryable = true`.
- Retry row creation relies on a `UNIQUE(delivery_intent_key, attempt_number)` constraint;
  a conflicting concurrent creation raises `IntegrityError`, which is caught and rolled
  back — the next tick re-evaluates from current state rather than creating a duplicate.

## FastAPI → n8n payload

```json
{
  "event": "REGISTRATION_QR_DELIVERY",
  "idempotency_key": "dlv_3f9ab2c1d4e5",
  "delivery_intent_key": "int_7a1c9f0e2b3d",
  "channel": "EMAIL",
  "hospital": "Smriti Raj Dentistry",
  "registration_id": "SRD-CBD80549",
  "recipient": "patient@example.com",
  "patient_name": "Rahul Sharma",
  "service": "Free In-House Zirconia Crown",
  "campaign": "Sunday Camp — Sept",
  "expires_at": "2026-09-14T00:00:00+00:00",
  "qr_base64_png": "<...>",
  "callback_url": "https://<PUBLIC_BASE_URL>/webhooks/n8n/delivery"
}
```

`event` is `REGISTRATION_QR_DELIVERY` for a first attempt and `REGISTRATION_QR_DELIVERY_RETRY`
for a retry attempt (`attempt_number > 1`); expiry reminders use
`REGISTRATION_EXPIRY_REMINDER`. Only the recipient contact for the row's own channel is
included — never the other channel's contact info. No beneficiary category, no passwords
or secrets, no decoded/raw QR token — `qr_base64_png` is the same opaque, already-generated
QR PNG used elsewhere in the app. `callback_url` is always built from `PUBLIC_BASE_URL`,
never hardcoded in a workflow.

## n8n → FastAPI callback

`POST /webhooks/n8n/delivery`, header `X-N8N-Webhook-Secret: <N8N_WEBHOOK_SECRET>`
(constant-time compared). **Require HTTPS in front of this endpoint in every
production-like deployment** — Railway terminates TLS ahead of the app, matching the
existing `SESSION_HTTPS_ONLY`/`PUBLIC_BASE_URL` production gates in `app/config.py`.

```json
{
  "idempotency_key": "dlv_3f9ab2c1d4e5",
  "status": "SENT",
  "provider_message_id": "provider-id",
  "failure_reason": null,
  "permanent": false
}
```

- `idempotency_key` is **required** on every new callback. Missing → `400`. Unknown → `404`.
- `status` must be one of `SENT`, `DELIVERED`, `FAILED`. Anything else → `400`.
- `permanent` is only meaningful when `status` is `FAILED`: `true` sets `retryable = false`
  on that row, permanently excluding it from retry; `false`/omitted leaves it retryable.
  **FastAPI never inspects `failure_reason` text to infer permanence** — n8n must send the
  explicit `permanent` flag.
- Duplicate callbacks reporting the row's current terminal status return
  `200 {"status": "ok", "noop": true}` with no mutation and no duplicate audit log entry.

## Legacy callback compatibility

`N8N_WEBHOOK_LEGACY_CALLBACK_COMPAT` (default `false`) is a **temporary cutover switch
only**. All new attempt rows always carry an `idempotency_key` and are matched by it alone.
When explicitly enabled, a callback that supplies `registration_id` but no matching
`idempotency_key` may fall back to "the latest `DeliveryLog` for that registration where
`idempotency_key IS NULL`" — scoped so it can never match a modern, keyed row. This exists
only to drain in-flight callbacks for rows created before the delivery-intent migration
shipped, and should be turned back off once that cutover window has passed.

## Legacy `PENDING` status

Before this pipeline, `DeliveryLog.status` could be `PENDING` (meaning "recorded locally,
n8n was not configured, nothing was ever attempted"). The migration
(`20260905_0008_delivery_intent_and_idempotency`) rewrites any existing `PENDING` row to
`PREPARED` before adding the status `CHECK` constraint — this is a lossless, semantically
exact rename, not a guess. `PENDING` is no longer a valid stored value going forward; the
migration also inspects all existing distinct status values first and fails loudly,
identifying the offending value, if it finds anything it does not know how to handle.

## Suggested n8n workflow outline (not built yet)

1. Webhook trigger — validate `X-N8N-Webhook-Secret` against the shared secret.
2. Switch on `channel` — Email branch (SMTP/SendGrid/etc., attach `qr_base64_png`) /
   WhatsApp branch (WhatsApp Business Cloud API or a BSP, template message with the QR
   image).
3. On the provider accepting the send → call `callback_url` with
   `{idempotency_key, status: "SENT", provider_message_id}`.
4. On the provider's own delivery-status webhook (if available) → a separate n8n flow
   calls `callback_url` again with `status: "DELIVERED"`.
5. On failure → call `callback_url` with `status: "FAILED"`, `failure_reason`, and
   `permanent` set from the provider's own error classification (e.g. an invalid
   phone/email error is permanent; a transient 5xx or timeout is not).

Provider selection (SMTP vendor, WhatsApp Cloud API vs. a BSP) is an open business decision
for whoever implements the actual n8n workflows and is out of scope for this contract.
