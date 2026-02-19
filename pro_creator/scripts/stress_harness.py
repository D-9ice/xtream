import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_BASE = os.environ.get("PC_API_BASE", "http://127.0.0.1:8000").rstrip("/")
TENANTS = [t.strip() for t in os.environ.get("PC_STRESS_TENANTS", "tenant-a,tenant-b").split(",") if t.strip()]
REQUESTS_PER_TENANT = max(1, int(os.environ.get("PC_STRESS_REQUESTS_PER_TENANT", "12")))
CONCURRENCY = max(1, int(os.environ.get("PC_STRESS_CONCURRENCY", "4")))
EXPECT_RATE_LIMIT = os.environ.get("PC_EXPECT_RATE_LIMIT", "true").lower() == "true"
REPORT_PATH = Path(os.environ.get("PC_STRESS_REPORT", "artifacts/stress-report.json"))


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    tenant_id: str | None = None,
) -> tuple[int, dict | str]:
    url = f"{API_BASE}{path}"
    headers: dict[str, str] = {}
    data = None
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
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


def _wait_for_health(timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    last: Any = None
    while time.time() < deadline:
        try:
            status, payload = _request("GET", "/health")
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return
            last = (status, payload)
        except Exception as exc:
            last = repr(exc)
        time.sleep(2)
    raise RuntimeError(f"Backend health failed: {last}")


def _create_project(tenant_id: str, suffix: str) -> str:
    status, body = _request(
        "POST",
        "/project/create",
        {"title": f"Stress {tenant_id} {suffix}", "topic": "stress harness"},
        tenant_id=tenant_id,
    )
    assert status == 200, (status, body)
    assert isinstance(body, dict)
    return str(body["project_id"])


def _exercise_paths(tenant_id: str, project_id: str, idx: int) -> int:
    status, _ = _request(
        "POST",
        "/script/generate",
        {
            "project_id": project_id,
            "topic": f"stress topic {idx}",
            "duration_minutes": 0.25,
            "tone": "neutral",
        },
        tenant_id=tenant_id,
    )
    if status >= 400:
        return status

    status, _ = _request(
        "POST",
        "/orchestration/queue",
        {
            "project_id": project_id,
            "kind": "script",
            "topic": f"queued stress topic {idx}",
            "duration_minutes": 0.25,
            "tone": "neutral",
        },
        tenant_id=tenant_id,
    )
    if status >= 400:
        return status

    status, _ = _request(
        "POST",
        "/billing/consume",
        {"amount": 1, "reason": f"stress-request-{idx}"},
        tenant_id=tenant_id,
    )
    return status


def _quota_scenario(tenant_id: str) -> dict[str, int]:
    # First consume nearly all credits, then verify insufficient-credits on overflow.
    status_one, _ = _request(
        "POST",
        "/billing/consume",
        {"amount": 950, "reason": "stress-quota-preload"},
        tenant_id=tenant_id,
    )
    status_two, _ = _request(
        "POST",
        "/billing/consume",
        {"amount": 80, "reason": "stress-quota-overflow"},
        tenant_id=tenant_id,
    )
    return {"preload_status": status_one, "overflow_status": status_two}


def main() -> int:
    started_at = time.time()
    _wait_for_health()

    report: dict[str, Any] = {
        "api_base": API_BASE,
        "tenants": {},
        "started_at_epoch": started_at,
        "expect_rate_limit": EXPECT_RATE_LIMIT,
    }

    project_ids: dict[str, str] = {}
    for tenant in TENANTS:
        project_ids[tenant] = _create_project(tenant, "base")

    for tenant in TENANTS:
        statuses: list[int] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [
                pool.submit(_exercise_paths, tenant, project_ids[tenant], i)
                for i in range(REQUESTS_PER_TENANT)
            ]
            for future in concurrent.futures.as_completed(futures):
                statuses.append(int(future.result()))

        counts: dict[str, int] = {}
        for status in statuses:
            key = str(status)
            counts[key] = counts.get(key, 0) + 1

        quota = _quota_scenario(tenant)
        report["tenants"][tenant] = {
            "project_id": project_ids[tenant],
            "requests": REQUESTS_PER_TENANT,
            "status_counts": counts,
            "quota": quota,
        }

    # Tenant isolation check for billing balances:
    balances: dict[str, int] = {}
    for tenant in TENANTS:
        status, body = _request("GET", "/billing/me", tenant_id=tenant)
        assert status == 200, (status, body)
        assert isinstance(body, dict)
        balances[tenant] = int(body["credits_balance"])
    report["billing_balances"] = balances
    report["isolation_ok"] = len(set(balances.values())) == len(balances)

    any_429 = any("429" in tenant_data["status_counts"] for tenant_data in report["tenants"].values())
    report["rate_limit_seen"] = any_429
    if EXPECT_RATE_LIMIT and not any_429:
        raise AssertionError("Expected at least one 429 rate-limit response, but none observed.")

    # Quota overflow should return 402 for each tenant.
    for tenant, tenant_data in report["tenants"].items():
        overflow = int(tenant_data["quota"]["overflow_status"])
        if overflow != 402:
            raise AssertionError(f"Expected 402 overflow for {tenant}, got {overflow}")

    report["completed_at_epoch"] = time.time()
    report["duration_seconds"] = round(report["completed_at_epoch"] - started_at, 2)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"ASSERTION FAILED: {exc}", file=sys.stderr)
        raise
