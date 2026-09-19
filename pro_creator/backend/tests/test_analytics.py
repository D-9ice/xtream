from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.database import engine
from app.main import app
from app.services import app_settings


def analytics_client() -> TestClient:
    return TestClient(app, headers={"X-Tenant-ID": f"analytics-{uuid4().hex[:12]}"})


def _enable_owner_mode() -> bool:
    with Session(engine) as session:
        settings = app_settings.get_or_create_settings(session)
        previous = bool(settings.owner_mode_enabled)
        settings.owner_mode_enabled = True
        session.add(settings)
        session.commit()
        return previous


def _restore_owner_mode(previous: bool) -> None:
    with Session(engine) as session:
        settings = app_settings.get_or_create_settings(session)
        settings.owner_mode_enabled = previous
        session.add(settings)
        session.commit()


def test_visit_analytics_summary_tracks_humans_and_bots() -> None:
    client = analytics_client()
    previous_owner_mode = _enable_owner_mode()
    try:
        access_res = client.post(
            "/billing/admin/access/verify",
            json={"password": "ChangeMe123!"},
        )
        assert access_res.status_code == 200
        admin_token = access_res.json()["access_token"]

        human_res = client.post(
            "/analytics/visits",
            json={
                "path": "/",
                "referrer": "https://example.com",
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "device_hint": "desktop",
                "country_hint": "GH",
                "page_title": "X'tream",
                "session_id": "session-human-1",
                "event_type": "page_view",
                "bot_hint": False,
            },
        )
        assert human_res.status_code == 200
        human_payload = human_res.json()
        assert human_payload["is_bot"] is False
        assert human_payload["device_type"] == "desktop"
        assert human_payload["country_code"] == "GH"

        bot_res = client.post(
            "/analytics/visits",
            json={
                "path": "/factory-mode",
                "user_agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "device_hint": "desktop",
                "country_hint": "US",
                "session_id": "session-bot-1",
                "event_type": "page_view",
                "bot_hint": False,
            },
        )
        assert bot_res.status_code == 200
        bot_payload = bot_res.json()
        assert bot_payload["is_bot"] is True
        assert bot_payload["bot_reason"]
        assert bot_payload["device_type"] == "bot"
        assert bot_payload["country_code"] == "US"

        summary_res = client.get(
            "/analytics/summary?days=7",
            headers={"X-Admin-Access-Token": admin_token},
        )
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert summary["total_visits"] == 2
        assert summary["human_visits"] == 1
        assert summary["bot_visits"] == 1
        assert summary["unique_sessions"] == 2
        assert summary["unique_paths"] == 2
        assert summary["visits_last_24h"] == 2
        assert summary["visits_last_7d"] == 2
        assert len(summary["top_paths"]) == 2
        assert len(summary["top_devices"]) == 2
        assert len(summary["top_countries"]) == 2
        assert len(summary["recent_visits"]) == 2
        assert len(summary["daily_visits"]) == 1
        assert {item["label"] for item in summary["top_devices"]} == {"desktop", "bot"}
        assert {item["label"] for item in summary["top_countries"]} == {"GH", "US"}
    finally:
        _restore_owner_mode(previous_owner_mode)


def test_duplicate_visit_events_are_deduped_within_short_window() -> None:
    client = analytics_client()
    previous_owner_mode = _enable_owner_mode()
    payload = {
        "path": "/factory-mode",
        "referrer": "https://example.com",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "device_hint": "desktop",
        "country_hint": "GH",
        "page_title": "Factory Mode",
        "session_id": "session-human-dedupe",
        "event_type": "page_view",
        "bot_hint": False,
    }

    first_res = client.post("/analytics/visits", json=payload)
    assert first_res.status_code == 200
    first_payload = first_res.json()

    second_res = client.post("/analytics/visits", json=payload)
    assert second_res.status_code == 200
    second_payload = second_res.json()

    assert second_payload["visit_id"] == first_payload["visit_id"]

    try:
        access_res = client.post(
            "/billing/admin/access/verify",
            json={"password": "ChangeMe123!"},
        )
        assert access_res.status_code == 200
        admin_token = access_res.json()["access_token"]

        summary_res = client.get(
            "/analytics/summary?days=7",
            headers={"X-Admin-Access-Token": admin_token},
        )
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert summary["total_visits"] == 1
        assert summary["human_visits"] == 1
        assert summary["bot_visits"] == 0
    finally:
        _restore_owner_mode(previous_owner_mode)


def test_visit_analytics_rejects_oversized_payload() -> None:
    client = analytics_client()
    response = client.post(
        "/analytics/visits",
        json={
            "path": "/",
            "referrer": "https://example.com",
            "user_agent": "Mozilla/5.0",
            "page_title": "X'tream",
            "session_id": "x" * 100,
            "event_type": "page_view",
            "bot_hint": False,
            "payload": "x" * 9000,
        },
    )
    assert response.status_code == 413


def test_visit_analytics_rejects_unknown_fields() -> None:
    client = analytics_client()
    response = client.post(
        "/analytics/visits",
        json={
            "path": "/",
            "user_agent": "Mozilla/5.0",
            "session_id": "session-unknown-field",
            "event_type": "page_view",
            "bot_hint": False,
            "unexpected": "should-not-be-accepted",
        },
    )
    assert response.status_code == 422



def test_visit_analytics_reset_clears_current_tenant_history() -> None:
    client = analytics_client()
    previous_owner_mode = _enable_owner_mode()
    try:
        access_res = client.post(
            "/billing/admin/access/verify",
            json={"password": "ChangeMe123!"},
        )
        assert access_res.status_code == 200
        admin_headers = {"X-Admin-Access-Token": access_res.json()["access_token"]}

        visit_res = client.post(
            "/analytics/visits",
            json={
                "path": "/",
                "user_agent": "Mozilla/5.0",
                "device_hint": "desktop",
                "country_hint": "GH",
                "session_id": "analytics-reset-test",
                "event_type": "page_view",
                "bot_hint": False,
            },
        )
        assert visit_res.status_code == 200

        before = client.get("/analytics/summary", headers=admin_headers)
        assert before.status_code == 200
        assert before.json()["total_visits"] == 1

        reset = client.delete("/analytics/visits", headers=admin_headers)
        assert reset.status_code == 200
        assert reset.json()["deleted"] is True
        assert reset.json()["deleted_count"] == 1

        after = client.get("/analytics/summary", headers=admin_headers)
        assert after.status_code == 200
        payload = after.json()
        assert payload["total_visits"] == 0
        assert payload["human_visits"] == 0
        assert payload["bot_visits"] == 0
        assert payload["unique_sessions"] == 0
        assert payload["unique_paths"] == 0
        assert payload["daily_visits"] == []
    finally:
        _restore_owner_mode(previous_owner_mode)
