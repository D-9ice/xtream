import json

from fastapi.testclient import TestClient

from app.main import app
from app.models import OrchestrationJob
from app.routers import orchestration
import app.tasks as tasks


def test_celery_full_dispatch_uses_workflow_production_task(monkeypatch) -> None:
    captured: dict[str, tuple] = {}

    class _Result:
        id = "task-123"

    class _Task:
        @staticmethod
        def delay(*args):
            captured["args"] = args
            return _Result()

    monkeypatch.setattr(orchestration.celery_tasks, "workflow_production_task", _Task())

    job = OrchestrationJob(
        id=17,
        project_id="proj-1",
        kind="full",
        payload=json.dumps({"user_id": 7, "export_preset": "youtube"}),
    )
    task_id = orchestration._dispatch_job(job)
    assert task_id == "task-123"
    assert captured["args"] == (17,)


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


def test_schedule_runner_skips_when_distributed_lock_is_held(monkeypatch) -> None:
    class _Lock:
        def acquire(self, blocking=False):
            assert blocking is False
            return False

        def release(self):
            raise AssertionError("unacquired scheduler lock must not be released")

    class _RedisClient:
        def lock(self, *args, **kwargs):
            assert args[0] == "procreator:scheduler:run_due_schedules"
            return _Lock()

    class _RedisFactory:
        @staticmethod
        def from_url(*_args, **_kwargs):
            return _RedisClient()

    monkeypatch.setattr(tasks, "Redis", _RedisFactory)
    assert tasks.run_due_schedules_task.run() == {
        "queued_job_ids": [],
        "count": 0,
        "skipped": "scheduler_lock_held",
    }
