import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.database import engine
from app.models import OrchestrationJob, OrchestrationSchedule
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



def test_schedule_creation_persists_owner_user_id() -> None:
    client = TestClient(app)
    project_id = "schedule-owner-test"
    response = client.post(
        "/orchestration/schedules",
        json={"project_id": project_id, "cadence_days": 1},
    )
    assert response.status_code == 200
    with Session(engine) as session:
        schedule = session.exec(
            select(OrchestrationSchedule).where(
                OrchestrationSchedule.project_id == project_id
            )
        ).first()
        assert schedule is not None
        assert schedule.user_id is not None


def test_generic_queue_cancel_sets_persisted_cancel_request(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(orchestration, "ENABLE_CELERY", True)
    monkeypatch.setattr(orchestration, "_dispatch_job", lambda job: f"cancel-task-{job.id}")
    revoked: list[str] = []
    monkeypatch.setattr(
        orchestration.celery_app.control,
        "revoke",
        lambda task_id, terminate=False: revoked.append(task_id),
    )

    queued = client.post(
        "/orchestration/queue",
        json={
            "project_id": "cancel-test-project",
            "kind": "workflow_production",
            "topic": "Cancel test",
            "duration_minutes": 1,
            "tone": "neutral",
        },
    )
    assert queued.status_code == 200
    job_id = queued.json()["id"]

    cancelled = client.post(f"/orchestration/queue/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancel_requested"
    assert revoked == [f"cancel-task-{job_id}"]

    with Session(engine) as session:
        job = session.get(OrchestrationJob, job_id)
        assert job is not None
        payload = json.loads(job.payload or "{}")
        assert payload["cancel_requested"] is True


def test_workflow_task_cancel_check_reads_payload() -> None:
    job = OrchestrationJob(
        id=999,
        project_id="cancel-payload-test",
        kind="workflow_production",
        status="processing",
        payload=json.dumps({"cancel_requested": True}),
    )

    class _Session:
        @staticmethod
        def refresh(_job):
            return None

    assert tasks._workflow_job_cancel_requested(_Session(), job) is True



def test_schedule_rejects_non_positive_cadence() -> None:
    client = TestClient(app)
    response = client.post(
        "/orchestration/schedules",
        json={"project_id": "invalid-cadence", "cadence_days": 0},
    )
    assert response.status_code == 422



def test_enqueue_dispatches_immediately_when_celery_enabled(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(orchestration, "ENABLE_CELERY", True)
    monkeypatch.setattr(orchestration, "_dispatch_job", lambda job: f"task-{job.id}")

    response = client.post(
        "/orchestration/queue",
        json={
            "project_id": "direct-dispatch-test",
            "kind": "workflow_production",
            "topic": "Dispatch immediately",
            "duration_minutes": 1,
            "tone": "neutral",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["task_id"] == f"task-{payload['id']}"
    assert payload["attempts"] == 1



def test_retry_failed_job_redispatches_under_celery(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(orchestration, "ENABLE_CELERY", True)
    monkeypatch.setattr(orchestration, "_dispatch_job", lambda job: f"retry-task-{job.id}")

    with Session(engine) as session:
        job = OrchestrationJob(
            tenant_id="default",
            project_id="retry-test-project",
            kind="workflow_production",
            status="failed",
            attempts=1,
            max_attempts=3,
            last_error="synthetic failure",
            payload=json.dumps({"user_id": 1}),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = int(job.id or 0)

    response = client.post(f"/orchestration/queue/{job_id}/retry")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processing"
    assert payload["attempts"] == 2
    assert payload["task_id"] == f"retry-task-{job_id}"
    assert payload["last_error"] is None


def test_retry_rejects_job_at_max_attempts(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr(orchestration, "ENABLE_CELERY", True)

    with Session(engine) as session:
        job = OrchestrationJob(
            tenant_id="default",
            project_id="retry-limit-project",
            kind="workflow_production",
            status="failed",
            attempts=3,
            max_attempts=3,
            last_error="final failure",
            payload=json.dumps({"user_id": 1}),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = int(job.id or 0)

    response = client.post(f"/orchestration/queue/{job_id}/retry")
    assert response.status_code == 400
    assert "Maximum orchestration attempts reached" in response.json()["detail"]
