import json
import os
import sys
import time
import urllib.error
import urllib.request


API_BASE = os.environ.get("PC_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def _request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
    url = f"{API_BASE}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def wait_for_health(timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            status, body = _request("GET", "/health")
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return
            last = (status, body)
        except Exception as e:
            last = repr(e)
        time.sleep(2)
    raise RuntimeError(f"backend /health not ready after {timeout_s}s, last={last}")


def main() -> int:
    wait_for_health()

    mode = os.environ.get("PC_SMOKE_MODE", "basic").strip().lower()

    # Create a project.
    status, project = _request("POST", "/project/create", {"title": "CI Smoke", "topic": "integration"})
    assert status == 200, (status, project)
    project_id = project["project_id"]

    # Generate script (writes to S3/MinIO + DB).
    status, script = _request(
        "POST",
        "/script/generate",
        {"project_id": project_id, "topic": "integration", "duration_minutes": 0.5, "tone": "neutral"},
    )
    assert status == 200, (status, script)
    assert script.get("scenes"), "expected scenes"

    # Ensure script is retrievable from storage.
    status, stored = _request("GET", f"/project/{project_id}/script")
    assert status == 200, (status, stored)
    assert isinstance(stored, dict) and stored.get("script", "").strip(), "expected stored script text"

    if mode == "full":
        # Validate the async path (Celery worker + broker + result backend).
        status, job = _request(
            "POST",
            "/orchestration/queue",
            {
                "project_id": project_id,
                "kind": "script",
                "topic": "integration async",
                "duration_minutes": 0.25,
                "tone": "neutral",
            },
        )
        assert status == 200, (status, job)
        job_id = job["id"]

        deadline = time.time() + 90
        last = None
        while time.time() < deadline:
            # This endpoint both dispatches and reaps finished Celery results.
            _request("POST", "/orchestration/queue/process?limit=1")

            status, queue = _request("GET", "/orchestration/queue")
            assert status == 200, (status, queue)
            item = next((it for it in queue.get("items", []) if it.get("id") == job_id), None)
            if item:
                last = item
                if item.get("status") in {"complete", "failed"}:
                    break
            time.sleep(2)

        assert last is not None, "expected to find queued job"
        assert last.get("status") == "complete", f"expected complete, got {last}"

    # Delete all projects should work and return empty list after.
    status, deleted = _request("DELETE", "/project/")
    assert status == 200, (status, deleted)

    status, projects = _request("GET", "/project/")
    assert status == 200, (status, projects)
    assert isinstance(projects, list) and len(projects) == 0, f"expected no projects after delete-all, got {len(projects)}"

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"ASSERTION FAILED: {e}", file=sys.stderr)
        raise
