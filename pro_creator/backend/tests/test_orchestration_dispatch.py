import json

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
