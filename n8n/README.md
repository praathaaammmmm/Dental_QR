# CRM QR Delivery — n8n Setup Guide

This guide is written for the clinic administrator setting up email/WhatsApp delivery,
not a developer. No coding is required — only filling in a few settings.

## A. What this workflow does

1. A patient registers (or staff resends a QR) — the CRM records this and queues it.
2. Once a minute, the CRM's own scheduled job sends the queued item to n8n.
3. n8n sends the patient their email (WhatsApp is not turned on yet — see section E).
4. n8n tells the CRM whether the message was sent successfully or failed.
5. The result appears on the CRM's **Delivery** screen (Admin CRM → Delivery).

The CRM never sends messages itself and never talks to email/WhatsApp providers directly
— n8n is the only thing that ever sends a message. The CRM only ever hands n8n the
information needed for one message and waits to be told the result.

## B. Importing the workflow

1. Open n8n.
2. Go to **Workflows**.
3. Choose **Import from File**.
4. Select `n8n/crm-qr-delivery.json` from this repository.
5. Open the imported workflow (named **CRM QR Delivery**).
6. Configure the two credentials it asks for (see sections C and D below).
7. Click **Activate** (top-right toggle) to turn the workflow on.
8. Open the **CRM Delivery Webhook** node and copy its **Production URL** — you'll need
   it in the next step.

## C. CRM environment configuration

1. Open the CRM's `.env` file (create it from `.env.example` if you haven't already —
   never commit `.env` to source control).
2. Find `N8N_WEBHOOK_URL=` and paste the production Webhook URL you copied in step B.8.
3. Find `N8N_WEBHOOK_SECRET=` and set it to a long random value. **This is the exact
   same value you must use in n8n's "CRM Delivery Shared Secret" credential** (section D)
   — both sides need to match. Do not print or share this value outside your password
   manager / secrets store.
4. Restart the FastAPI backend so it picks up the new settings.

## D. Email setup

The imported workflow's **Send Email** node needs one SMTP-style credential in n8n:

1. In n8n, open the **Send Email** node.
2. Under Credentials, choose **Create New Credential** → pick your provider:
   - **SMTP** (recommended) — use the clinic's own email account (host, port, username,
     password from your email provider).
   - **Gmail** or **Microsoft Outlook** — only if the clinic already uses one of these
     for its email; you'll sign in via that provider's own login flow.
3. Save the credential. It stays stored inside n8n only — it is never written into the
   CRM codebase, `.env`, or this workflow file.
4. Also open the **CRM Delivery Webhook** and **Notify CRM (Callback)** nodes and set the
   **CRM Delivery Shared Secret** credential:
   - Credential type: **Header Auth**
   - Header name: `X-N8N-Webhook-Secret`
   - Header value: the exact same secret you put in the CRM's `N8N_WEBHOOK_SECRET`
     (section C.3).
5. Optionally set the `CLINIC_FROM_EMAIL` variable in your n8n instance's environment
   (used by the Send Email node's "from" address); if you skip this, set the From Email
   directly on the node instead.

## B.1 Re-importing after the "Route By Channel" fix

An earlier version of `n8n/crm-qr-delivery.json` configured the **Route By Channel**
Switch node with a parameter shape (`mode: "expression"` plus an `outputKey` string) that
belongs to an older Switch node generation. On current n8n versions this makes the node
try to push each item into an output array that doesn't exist, and every execution fails
at that node with:

```
Cannot read properties of undefined (reading 'push')
```

The node has been rebuilt to use the current Switch node's **rules** mode (three routing
rules: `EMAIL`, `WHATSAPP`, and a fallback output for anything else). If you already
imported the old version of this workflow:

1. **Do not** try to fix the node by hand in the n8n editor — re-import the file instead,
   since the node's whole parameter shape changed, not just one field.
2. In n8n, open the existing **CRM QR Delivery** workflow and **deactivate** it (top-right
   toggle).
3. Re-import `n8n/crm-qr-delivery.json` the same way as section B (**Workflows → Import
   from File**). n8n will ask whether to create a new workflow or overwrite the existing
   one by ID — updating the existing workflow in place is fine and preserves its
   Executions history; you do not need to delete it first.
4. Re-open the **CRM Delivery Webhook**, **Send Email**, and **Notify CRM (Callback)**
   nodes and reattach the **CRM Delivery Shared Secret** and email credentials — importing
   a workflow file never carries real credential values with it (see the Security notes at
   the bottom of this file), only the credential *name* reference, so n8n may show these
   nodes as needing their credential re-selected from the list.
5. **Activate** the workflow again.
6. Retest with a fresh registration (section H) — the previous failure happened before
   **Send Email**, so no patient was ever emailed by the broken version; nothing needs to
   be undone on the email side.

## E. WhatsApp setup

WhatsApp is **not active** in the imported workflow. The "WhatsApp Branch" is a clearly
labeled placeholder that always reports a (non-permanent) failure back to the CRM, so a
patient never silently misses a notification — the failure is visible on the CRM's
Delivery screen instead.

To turn WhatsApp on later, you will need one of:
- **Meta WhatsApp Cloud API** — requires a Meta Business account, a verified WhatsApp
  Business phone number, and Meta-approved message templates.
- **Twilio WhatsApp** — requires a Twilio account and Twilio's own WhatsApp sender
  approval process.

Either provider requires template approval before you can message patients who haven't
messaged you first — this is a WhatsApp platform rule, not something this CRM or n8n can
bypass. Once you have approved credentials, replace the "WhatsApp Branch (Not Configured -
Placeholder)" node with the real provider node, wire its success output the same way the
Email branch's success output is wired (into a "Build SENT Callback" step), and its error
output the same way (into a "Build FAILED Callback" step).

## F. Dispatcher scheduling

The CRM's delivery dispatcher is a separate scheduled job — it does not run automatically
with the web server. Run it manually to test:

```powershell
py -m app.delivery_job
```

(Exact command confirmed from `app/delivery_job.py` and the project README — this is not
a new or different command.)

### Scheduling it every minute with Windows Task Scheduler

1. Open **Task Scheduler** → **Create Task** (not "Basic Task", so you get the Triggers tab).
2. **General** tab: name it e.g. "CRM Delivery Dispatch"; select "Run whether user is
   logged on or not" if this is a server machine.
3. **Triggers** tab → **New** → Begin the task **On a schedule** → **Daily**, then check
   **Repeat task every** and set it to **1 minute**, for a duration of **Indefinitely**.
4. **Actions** tab → **New** → **Start a program**:
   - **Program/script**: the full path to your project's Python executable, e.g.
     `C:\Users\<you>\smritiraj_dentistry_qr\smritiraj_qr_system\.venv\Scripts\python.exe`
   - **Add arguments**: `-m app.delivery_job`
   - **Start in**: the full path to the project folder, e.g.
     `C:\Users\<you>\smritiraj_dentistry_qr\smritiraj_qr_system`
5. Save the task. Its recommended trigger frequency is **every 1 minute**, matching the
   CRM's documented dispatcher interval.

## G. Local versus cloud connectivity

**"localhost"/"127.0.0.1" mean different machines depending on which side evaluates
them.** Two separate URLs are involved and they are not interchangeable:
- **CRM → n8n** (`N8N_WEBHOOK_URL` in the CRM's `.env`): the address the CRM's dispatcher
  uses to POST a delivery job to n8n's webhook.
- **n8n → CRM** (`N8N_CALLBACK_BASE_URL` in the CRM's `.env`, used to build the
  `callback_url` field the CRM sends n8n): the address n8n itself must use to POST the
  result back to the CRM's `/webhooks/n8n/delivery` endpoint. This is evaluated from
  **inside n8n's own process/container**, not from the CRM's machine.

- If n8n is running **on the same computer** as the CRM as a plain (non-Docker) local
  install, it can reach the CRM at `127.0.0.1` or `localhost` without any extra setup —
  leaving `N8N_CALLBACK_BASE_URL` unset (it falls back to `PUBLIC_BASE_URL`) is fine.
- If n8n is running **in Docker** (including Docker Desktop on Windows) while the CRM runs
  directly on the host, `localhost`/`127.0.0.1` inside the n8n container refers to **the
  n8n container itself**, not your Windows host — so a callback built from `127.0.0.1`
  will always fail with a connection-refused error from n8n's "Notify CRM (Callback)"
  node, even though the CRM is running and reachable from everywhere else. Set, in the
  CRM's `.env`:
  ```
  N8N_CALLBACK_BASE_URL=http://host.docker.internal:8000
  ```
  `host.docker.internal` is Docker Desktop's special DNS name that resolves to the host
  machine from inside any container — it is not something you configure in n8n, only in
  the CRM's own `.env`, since the CRM is the one that builds `callback_url` and hands it
  to n8n in the payload. Restart the CRM backend after changing it. This does **not**
  change `N8N_WEBHOOK_URL` — the CRM can continue reaching n8n at `localhost:5678` (or
  whatever port you've mapped) exactly as before.

  This alone is not enough: the CRM's `TrustedHostMiddleware` (`ALLOWED_HOSTS`) checks the
  `Host` header on every incoming request, including this callback, and rejects anything
  not on the allowlist with `400 Invalid host header` — a callback arriving with
  `Host: host.docker.internal:8000` is rejected the same way an attacker's forged Host
  header would be, until you explicitly allow it. In the CRM's `.env`, **append**
  `host.docker.internal` to your existing `ALLOWED_HOSTS` value — do not replace the list,
  add to it, since it still needs to keep serving `127.0.0.1`/`localhost` for your own
  browser access:
  ```env
  ALLOWED_HOSTS=127.0.0.1,localhost,healthcheck.railway.app,host.docker.internal
  ```
  Restart the CRM backend after changing it. Do not add `host.docker.internal` to a
  production `.env` — it only means anything on a machine that actually has Docker Desktop
  running locally, and `app/config.py`'s production validation already refuses an empty or
  wildcard `ALLOWED_HOSTS`, but it cannot detect an unnecessary local-only entry left in a
  production value, so remove it yourself before deploying.
- If you use **n8n Cloud** (n8n.io's hosted service), it runs on n8n's servers and
  **cannot reach `127.0.0.1` on your computer** — that address only means "this machine"
  to each computer individually.
- For n8n Cloud (or any n8n instance not on your machine/LAN) to call your CRM's callback
  endpoint, the CRM must be reachable at a real, publicly resolvable address — either a
  proper deployment (e.g. the Railway deployment this project already documents, in which
  case set `N8N_CALLBACK_BASE_URL` to that deployment's URL) or a secure temporary tunnel
  (e.g. a tool like ngrok) pointed at your local CRM while testing.
- **Never expose the CRM to the internet without the authentication it already has
  enabled** (its normal login, and the `X-N8N-Webhook-Secret` check on the callback
  endpoint). A tunnel makes the CRM reachable from outside — it does not replace the need
  for these existing protections, and you should not disable them to make testing easier.

## H. End-to-end test checklist

1. Start the CRM backend (`py -m uvicorn app.main:app --reload`, or however you normally
   run it).
2. Start (or open, if it's already running/hosted) n8n.
3. Activate the **CRM QR Delivery** workflow in n8n (section B.7).
4. Register a test patient in the CRM using a real test email address you can check.
5. On the CRM's **Delivery** screen, confirm a new row appears with status **PREPARED**.
6. Manually run the dispatcher once: `py -m app.delivery_job`.
7. In n8n, open **Executions** and confirm a new execution appears for this workflow.
8. Check the test email inbox and confirm the QR delivery email arrived.
9. Refresh the CRM's Delivery screen and confirm the row's status changed to **SENT** or
   **DELIVERED**.
10. To test failure handling: temporarily break the SMTP credential (e.g. wrong password),
    repeat steps 4–7, and confirm the CRM's Delivery screen shows **FAILED** with a
    reason. Restore the correct credential afterward.
11. Confirm retries behave as already documented in
    `docs/blueprint/n8n-delivery-contract.md` (up to 3 total attempts per delivery, 2
    minutes then 10 minutes apart) — you can observe this by leaving a failure in place
    across a few dispatcher runs and watching new attempt rows appear on the Delivery
    screen, rather than the same row being edited.

## Security notes

- This workflow file contains no passwords, API keys, tokens, phone numbers, email
  addresses, or patient data — only credential *references* (by name), which point at
  values stored securely inside n8n itself.
- n8n never queries the CRM's database. It only ever receives the one delivery job the
  CRM's dispatcher sends it, and only ever sends back a status update for that same job.
- The callback authentication (`X-N8N-Webhook-Secret`) is the only authentication
  mechanism used in either direction — this workflow does not add a second one.
- Do not enable `N8N_WEBHOOK_LEGACY_CALLBACK_COMPAT` in the CRM's `.env` unless you have
  a specific, documented reason to (see `docs/blueprint/n8n-delivery-contract.md`) — leave
  it `false`.
