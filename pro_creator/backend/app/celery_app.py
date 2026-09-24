from celery import Celery

from app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

celery_app = Celery(
    "pro_creator",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    imports=("app.tasks",),
    beat_schedule={
        "run-due-orchestration-schedules": {
            "task": "pro_creator.run_due_schedules",
            "schedule": 60.0,
        },
        "reconcile-orchestration-jobs": {
            "task": "pro_creator.reconcile_orchestration_jobs",
            "schedule": 30.0,
        },
    },
)
