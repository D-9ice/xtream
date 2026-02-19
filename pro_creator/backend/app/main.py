from contextlib import asynccontextmanager
from collections import defaultdict, deque
from threading import Lock
from time import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from fastapi.responses import Response
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import (
    ADMIN_PASSWORD,
    ALLOWED_ORIGINS,
    API_TITLE,
    DATABASE_URL,
    ENVIRONMENT,
    JWT_SECRET,
    PROJECTS_DIR,
    RATE_LIMIT_AUTH_REQUESTS,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_HEAVY_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    STORAGE_BACKEND,
    TENANT_HEADER_NAME,
    validate_external_service_config,
)
from app.database import init_db
from app.seed import seed_admin_user
from app.routers import auth, billing, editor, image, orchestration, project, script, video, voice
from app.tenant import current_tenant_id, reset_current_tenant_id, set_current_tenant_id

@asynccontextmanager
async def lifespan(_: FastAPI):
    if ENVIRONMENT == "production":
        if JWT_SECRET in {"dev-secret-change-me", "change-me"}:
            raise RuntimeError("JWT_SECRET must be set for production")
        if ADMIN_PASSWORD == "ChangeMe123!":
            raise RuntimeError("ADMIN_PASSWORD must be set for production")
        if "change-me-db-password" in DATABASE_URL:
            raise RuntimeError("DATABASE_URL must use a non-default DB password")
    validate_external_service_config()
    init_db()
    seed_admin_user()
    yield


app = FastAPI(title=API_TITLE, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STORAGE_BACKEND == "local":
    app.mount("/projects", StaticFiles(directory=PROJECTS_DIR), name="projects")


_rate_limit_lock = Lock()
_rate_limit_store: dict[str, deque[float]] = defaultdict(deque)
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)


def _rate_limit_hit(key: str, limit: int) -> bool:
    now = time()
    floor = now - RATE_LIMIT_WINDOW_SECONDS
    with _rate_limit_lock:
        bucket = _rate_limit_store[key]
        while bucket and bucket[0] < floor:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
    return False


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    tenant_token = set_current_tenant_id(request.headers.get(TENANT_HEADER_NAME))
    try:
        if not RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        method = request.method.upper()
        ip = request.client.host if request.client else "unknown"

        auth_paths = ("/auth/login", "/auth/register", "/auth/change-password")
        heavy_prefixes = (
            "/script/",
            "/voice/",
            "/image/",
            "/video/",
            "/orchestration/",
        )

        tenant_id = current_tenant_id()

        if method == "POST" and path in auth_paths:
            if _rate_limit_hit(f"auth:{tenant_id}:{ip}:{path}", RATE_LIMIT_AUTH_REQUESTS):
                response = JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
                http_requests_total.labels(method=method, path=path, status="429").inc()
                return response
        elif method == "POST" and path.startswith(heavy_prefixes):
            if _rate_limit_hit(f"heavy:{tenant_id}:{ip}", RATE_LIMIT_HEAVY_REQUESTS):
                response = JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
                http_requests_total.labels(method=method, path=path, status="429").inc()
                return response

        response = await call_next(request)
        http_requests_total.labels(
            method=method,
            path=path,
            status=str(response.status_code),
        ).inc()
        return response
    finally:
        reset_current_tenant_id(tenant_token)


@app.get("/")
def root():
    return {"message": "Pro Creator Backend Running"}


app.include_router(project.router)
app.include_router(script.router)
app.include_router(voice.router)
app.include_router(image.router)
app.include_router(video.router)
app.include_router(orchestration.router)
app.include_router(auth.router)
app.include_router(editor.router)
app.include_router(billing.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
