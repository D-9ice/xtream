import json

from fastapi.testclient import TestClient

from app.main import app
from app.models import OrchestrationJob
from app.routers import orchestration


def test_celery_full_dispatch_uses_full_pipeline_task(monkeypatch) -> None:
    captured: dict[str, tuple] = {}

    class _Result:
        id = "task-123"

    class _Task:
        @staticmethod
        def delay(*args):
            captured["args"] = args
            return _Result()

    monkeypatch.setattr(orchestration.celery_tasks, "full_pipeline_task", _Task())

    job = OrchestrationJob(
        project_id="proj-1",
        kind="full",
        payload=json.dumps(
            {
                "topic": "topic",
                "duration_minutes": 1.5,
                "tone": "bold",
                "export_preset": "youtube",
                "voice_text": "voice text",
                "image_prompt": "image prompt",
            }
        ),
    )
    task_id = orchestration._dispatch_job(job)
    assert task_id == "task-123"
    assert captured["args"] == (
        "proj-1",
        "topic",
        1.5,
        "bold",
        "youtube",
        "voice text",
        "image prompt",
    )


def test_celery_factory_mode_dispatch_uses_factory_mode_task(monkeypatch) -> None:
    captured: dict[str, tuple] = {}

    class _Result:
        id = "factory-task-123"

    class _Task:
        @staticmethod
        def delay(*args):
            captured["args"] = args
            return _Result()

    monkeypatch.setattr(orchestration.celery_tasks, "factory_mode_task", _Task())

    job = OrchestrationJob(
        id=42,
        project_id="factory-mode",
        kind="factory_mode",
        payload=json.dumps(
            {
                "user_id": 7,
                "titles": ["One", "Two"],
                "duration_minutes": 10,
                "genre": "Adventure",
            }
        ),
    )
    task_id = orchestration._dispatch_job(job)
    assert task_id == "factory-task-123"
    assert captured["args"] == (42,)


def test_runner_status_reports_worker_managed_mode(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(orchestration, "ENABLE_CELERY", True)

    status_res = client.get("/orchestration/queue/runner/status")
    assert status_res.status_code == 200
    payload = status_res.json()
    assert payload["enabled"] is False
    assert payload["running"] is False
    assert "disabled when ENABLE_CELERY=true" in payload["detail"]

    start_res = client.post("/orchestration/queue/runner/start")
    assert start_res.status_code == 400
    assert "disabled when ENABLE_CELERY=true" in start_res.json()["detail"]
