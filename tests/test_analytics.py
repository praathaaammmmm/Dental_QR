from datetime import timedelta

from app.audit_service import audit
from app.auth import password_hasher
from app.database import SessionLocal
from app.models import PatientOffer, StaffUser
from app.reporting.service import daily_time_series, default_chart_mode, staff_performance
from app.time_utils import utc_now


def _register(client, name: str, mobile: str):
    response = client.post("/patients/register", data={
        "full_name": name, "mobile": mobile, "campaign_id": "1",
        "offer_id": "1", "beneficiary_category": "CGHS", "consent_given": "true",
    })
    assert response.status_code == 200


def test_time_series_uses_grouped_registration_and_redemption_dates(client):
    _register(client, "Analytics One", "9010000001")
    _register(client, "Analytics Two", "9010000002")
    now = utc_now()
    db = SessionLocal()
    try:
        first, second = db.query(PatientOffer).order_by(PatientOffer.id).all()
        first.created_at = now - timedelta(days=1)
        second.created_at = now
        first.status = "REDEEMED"
        first.redeemed_at = now
        db.commit()

        # Wide margin so the Asia/Kolkata-vs-UTC day boundary can never exclude either
        # timestamp; the day-bucket keys asserted below are still the literal UTC dates
        # `daily_time_series` groups by, unaffected by the range filter's own margin.
        series = daily_time_series(db, start=(now - timedelta(days=2)).date(), end=(now + timedelta(days=1)).date())
        registrations = {row["day"]: row["count"] for row in series["registrations"]}
        redemptions = {row["day"]: row["count"] for row in series["redemptions"]}
        assert registrations[str((now - timedelta(days=1)).date())] == 1
        assert registrations[str(now.date())] == 1
        assert redemptions[str(now.date())] == 1
    finally:
        db.close()


def test_staff_performance_aggregates_audit_events_by_username(client):
    db = SessionLocal()
    try:
        first = StaffUser(username="analytics-one", password_hash=password_hasher.hash("password"), role="staff")
        second = StaffUser(username="analytics-two", password_hash=password_hasher.hash("password"), role="staff")
        db.add_all([first, second])
        db.flush()
        audit(db, "analytics-one", "PATIENT_REGISTERED")
        audit(db, "analytics-one", "PATIENT_REGISTERED")
        audit(db, "analytics-one", "QR_REDEEMED")
        audit(db, "analytics-two", "QR_REDEEMED")
        db.commit()

        rows = {row["username"]: row for row in staff_performance(db)}
        assert rows["analytics-one"]["registrations"] == 2
        assert rows["analytics-one"]["redemptions"] == 1
        assert rows["analytics-two"]["registrations"] == 0
        assert rows["analytics-two"]["redemptions"] == 1
    finally:
        db.close()


def test_admin_dashboard_and_csv_exports_are_available_to_admin_only(client):
    _register(client, "Export Patient", "9010000003")
    dashboard = client.get("/admin/dashboard")
    assert dashboard.status_code == 200
    assert 'id="analytics-chart"' in dashboard.text
    assert "<style>" not in dashboard.text, (
        "the dashboard's Content-Security-Policy is style-src 'self', which silently "
        "drops inline <style> blocks in real browsers -- chart CSS must live in style.css"
    )
    assert 'id="analytics-loading"' in dashboard.text
    assert 'id="analytics-empty"' in dashboard.text
    assert 'class="chart-legend"' in dashboard.text
    assert 'class="chart-dot registrations"' in dashboard.text
    assert 'class="chart-dot redemptions"' in dashboard.text
    campaign_csv = client.get("/admin/reports/campaigns.csv")
    patient_csv = client.get("/admin/reports/patients.csv")
    assert campaign_csv.status_code == 200 and "Campaign" in campaign_csv.text
    assert patient_csv.status_code == 200 and "Export Patient" in patient_csv.text

    db = SessionLocal()
    try:
        db.add(StaffUser(username="analytics-staff", password_hash=password_hasher.hash("password"), role="staff"))
        db.commit()
    finally:
        db.close()
    client.post("/logout")
    response = client.post("/staff/login", data={"username": "analytics-staff", "password": "password"}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/admin/reports/patients.csv", follow_redirects=False).status_code == 403


def test_dashboard_chart_css_is_served_from_the_external_stylesheet(client):
    """The chart's legend/dot/loading styling must live in the externally-served
    stylesheet (allowed by style-src 'self'), not an inline <style> tag on the page
    (silently dropped by the same CSP), or the legend renders as unstyled, cramped text."""
    stylesheet = client.get("/static/style.css")
    assert stylesheet.status_code == 200
    assert ".chart-legend{display:flex" in stylesheet.text
    assert ".chart-dot.registrations{background:#08aa91}" in stylesheet.text
    assert ".chart-dot.redemptions{background:#51419a}" in stylesheet.text
    assert ".chart-loading{" in stylesheet.text
    assert ".chart-mode-btn" in stylesheet.text
    assert '.chart-mode-btn[aria-pressed="true"]' in stylesheet.text


def test_dashboard_chart_has_bars_and_line_mode_toggle_beside_the_legend(client):
    """Both chart-type controls must exist beside the legend, be clearly labelled,
    keyboard-focusable (plain <button>s), and expose their pressed state for a11y."""
    dashboard = client.get("/admin/dashboard")
    assert dashboard.status_code == 200
    text = dashboard.text
    assert '<style>' not in text
    assert 'class="chart-controls"' in text
    assert 'class="chart-mode-toggle" role="group" aria-label="Chart type"' in text
    assert '<button type="button" id="chart-mode-bars" class="chart-mode-btn" aria-pressed="false" hidden>Bars</button>' in text
    assert '<button type="button" id="chart-mode-line" class="chart-mode-btn" aria-pressed="false" hidden>Line</button>' in text


def test_dashboard_chart_script_renders_both_modes_from_the_same_embedded_data(client):
    """Both rendering paths must exist client-side and read from the single embedded
    `values` series (no second network round-trip / no separate data source per mode)."""
    dashboard = client.get("/admin/dashboard")
    text = dashboard.text
    assert "const series = " in text
    assert "const renderBars = wireHover =>" in text
    assert "const renderLine = wireHover =>" in text
    assert "const RENDERERS = { bars: renderBars, line: renderLine };" in text
    assert "barsBtn.addEventListener('click'" in text
    assert "lineBtn.addEventListener('click'" in text
    # Both toggle handlers call the same renderChart(mode) against the same `values` --
    # switching redraws in place rather than re-fetching the page.
    assert "renderChart(mode)" in text


def test_default_chart_mode_is_bars_up_to_seven_dates_else_line():
    """Pure unit test of the server-side default-mode decision (app/reporting/service.py)
    -- the single source of truth the dashboard route embeds into the page. "Displayed
    dates" is the union of registration/redemption day labels, not a raw calendar span."""
    seven_days = {"registrations": [{"day": f"2026-01-0{n}", "count": 1} for n in range(1, 8)], "redemptions": []}
    eight_days = {"registrations": [{"day": f"2026-01-0{n}", "count": 1} for n in range(1, 9)], "redemptions": []}
    assert default_chart_mode(seven_days) == "bars"
    assert default_chart_mode(eight_days) == "line"

    # A registration day and a disjoint redemption day both count toward the displayed total.
    mixed = {"registrations": [{"day": "2026-01-01", "count": 1}], "redemptions": [{"day": "2026-01-02", "count": 1}]}
    assert default_chart_mode(mixed) == "bars"


def test_dashboard_embeds_the_server_decided_default_mode_for_the_client_toggle_to_read(client):
    """The client doesn't recompute the default -- it reads the exact value the dashboard
    route computed from this page's own time_series, so it can never drift from it."""
    dashboard = client.get("/admin/dashboard")
    text = dashboard.text
    assert 'data-default-mode="bars"' in text or 'data-default-mode="line"' in text
    assert "chart.dataset.defaultMode === 'line' ? 'line' : 'bars'" in text
