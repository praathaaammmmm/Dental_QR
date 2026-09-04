import httpx

from app import n8n_service


def test_trigger_delivery_returns_pending_when_unconfigured(monkeypatch):
    monkeypatch.setattr(n8n_service, "N8N_WEBHOOK_URL", "")
    result = n8n_service.trigger_delivery({"event": "TEST"})
    assert result == {"status": "PENDING", "reason": "N8N_WEBHOOK_URL is not configured"}


def test_trigger_delivery_posts_payload_with_secret_header_and_returns_sent(monkeypatch):
    monkeypatch.setattr(n8n_service, "N8N_WEBHOOK_URL", "https://n8n.example/webhook")
    monkeypatch.setattr(n8n_service, "N8N_WEBHOOK_SECRET", "shh")
    captured = {}

    class FakeResponse:
        content = b'{"execution_id": "exec-1"}'

        def raise_for_status(self):
            pass

        def json(self):
            return {"execution_id": "exec-1"}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    result = n8n_service.trigger_delivery({"event": "TEST", "idempotency_key": "dlv_1"})

    assert result == {"status": "SENT", "workflow_id": "exec-1"}
    assert captured["url"] == "https://n8n.example/webhook"
    assert captured["headers"]["X-N8N-Webhook-Secret"] == "shh"
    assert captured["json"]["idempotency_key"] == "dlv_1"


def test_trigger_delivery_returns_failed_with_safe_reason_on_exception(monkeypatch):
    monkeypatch.setattr(n8n_service, "N8N_WEBHOOK_URL", "https://n8n.example/webhook")

    def fake_post(*args, **kwargs):
        raise httpx.ConnectTimeout("connection refused with secret api-key=super-secret")

    monkeypatch.setattr(httpx, "post", fake_post)
    result = n8n_service.trigger_delivery({"event": "TEST"})

    assert result["status"] == "FAILED"
    assert "reason" in result
    assert len(result["reason"]) <= 255
