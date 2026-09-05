"""Outbound delivery boundary. n8n owns email/WhatsApp provider integration."""
import httpx
from ..config import N8N_WEBHOOK_SECRET, N8N_WEBHOOK_URL

def trigger_delivery(payload: dict) -> dict:
    if not N8N_WEBHOOK_URL:
        return {"status": "PENDING", "reason": "N8N_WEBHOOK_URL is not configured"}
    headers = {"X-N8N-Webhook-Secret": N8N_WEBHOOK_SECRET} if N8N_WEBHOOK_SECRET else {}
    try:
        response = httpx.post(N8N_WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        body = response.json() if response.content else {}
        return {"status": "SENT", "workflow_id": body.get("workflow_id") or body.get("execution_id")}
    except Exception as exc:
        return {"status": "FAILED", "reason": str(exc)[:255]}
