from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import parse_qsl, quote, urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import (
    CREDITS_COST_VIDEO_EXPORT,
    JWT_SECRET,
    OWNER_EMAIL_ALLOWLIST,
    SOCIAL_TIKTOK_CLIENT_KEY,
    SOCIAL_TIKTOK_CLIENT_SECRET,
    SOCIAL_PUBLISH_MAX_ATTEMPTS,
    SOCIAL_PUBLISH_RETRY_BACKOFF_SECONDS,
    SOCIAL_YOUTUBE_CLIENT_ID,
    SOCIAL_YOUTUBE_CLIENT_SECRET,
)
from app.models import Project, SocialAccountConnection, SocialPublishJob, User, utc_now
from app.services.credits import consume_credits
from app.storage import project_key, storage_client

PLATFORM_KEYS = {"youtube", "instagram", "facebook", "x", "tiktok"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_platform(value: str) -> str:
    platform = value.strip().lower()
    if platform not in PLATFORM_KEYS:
        raise HTTPException(status_code=400, detail=f"Unsupported social platform: {value}")
    return platform


def _clean_optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _clean_metadata(metadata: dict[str, str] | None) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in (metadata or {}).items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            cleaned[key_text] = value_text
    return cleaned


def _derive_legacy_stream(secret: str, salt: str, length: int) -> bytes:
    """Compatibility only: decrypt pre-hardening token rows."""
    seed = hashlib.sha256(f"{secret}::{salt}".encode("utf-8")).digest()
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(seed, f"{salt}:{counter}".encode("utf-8"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _social_fernet() -> Fernet:
    # Preserve the existing JWT-secret dependency so deployed connections survive
    # without introducing an unsynchronised second secret during this migration.
    digest = hashlib.sha256(f"procreator-social-v2::{JWT_SECRET}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_secret(value: str | None) -> str | None:
    clean = _clean_optional_text(value)
    if clean is None:
        return None
    token = _social_fernet().encrypt(clean.encode("utf-8")).decode("ascii")
    return f"v2:{token}"


def _decrypt_legacy_secret(value: str) -> str | None:
    try:
        salt, encoded = value.split(":", 1)
        cipher = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        stream = _derive_legacy_stream(JWT_SECRET, salt, len(cipher))
        plain = bytes(a ^ b for a, b in zip(cipher, stream))
        return plain.decode("utf-8")
    except Exception:
        return None


def _decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("v2:"):
        try:
            return _social_fernet().decrypt(value[3:].encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeDecodeError):
            return None
    return _decrypt_legacy_secret(value)


def _json_text(value: Any, default: Any) -> str:
    try:
        return json.dumps(value if value is not None else default)
    except Exception:
        return json.dumps(default)


def _parse_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed if parsed is not None else default


def connection_to_payload(connection: SocialAccountConnection) -> dict[str, Any]:
    return {
        "connection_id": connection.connection_id,
        "platform": connection.platform,
        "account_label": connection.account_label,
        "account_identifier": connection.account_identifier,
        "access_token": _decrypt_secret(connection.access_token_encrypted) or "",
        "access_token_secret": _decrypt_secret(connection.access_token_secret_encrypted),
        "refresh_token": _decrypt_secret(connection.refresh_token_encrypted),
        "client_key": _decrypt_secret(connection.client_key_encrypted),
        "client_secret": _decrypt_secret(connection.client_secret_encrypted),
        "token_expires_at": connection.token_expires_at,
        "scopes": list(_parse_json(connection.scopes_json, [])),
        "metadata": dict(_parse_json(connection.metadata_json, {})),
        "enabled": connection.enabled,
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }


def connection_to_response(connection: SocialAccountConnection) -> dict[str, Any]:
    payload = connection_to_payload(connection)
    payload.pop("access_token", None)
    payload.pop("access_token_secret", None)
    payload.pop("refresh_token", None)
    payload.pop("client_key", None)
    payload.pop("client_secret", None)
    payload["enabled"] = bool(connection.enabled) or not _connection_has_publish_credentials(connection)
    return payload


def job_to_payload(job: SocialPublishJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "project_id": job.project_id,
        "connection_id": job.connection_id,
        "platform": job.platform,
        "status": job.status,
        "remote_post_id": job.remote_post_id,
        "published_url": job.published_url,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "published_at": job.published_at,
    }


def _get_project(session: Session, project_id: str) -> Project:
    project = session.exec(select(Project).where(Project.project_id == project_id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_video_key(project_id: str) -> str:
    if storage_client.exists(project_key(project_id, "video/final.mp4")):
        return project_key(project_id, "video/final.mp4")
    if storage_client.exists(project_key(project_id, "video/imported.mp4")):
        return project_key(project_id, "video/imported.mp4")
    raise HTTPException(status_code=400, detail="No finished video is available for publishing")


def _get_video_public_url(project_id: str) -> str:
    return storage_client.public_url(_get_video_key(project_id))


def _video_bytes(project_id: str) -> bytes:
    data = storage_client.read_bytes(_get_video_key(project_id))
    if not data:
        raise HTTPException(status_code=400, detail="Finished video is empty")
    return data


def _build_message(project: Project, message: str | None, title: str | None) -> str:
    primary = _clean_optional_text(message) or _clean_optional_text(title) or project.title
    idea = _clean_optional_text(project.idea_prompt) or _clean_optional_text(project.topic)
    if idea:
        return f"{primary}\n\n{idea}"
    return primary


def _publish_fingerprint(
    *,
    tenant_id: str,
    user_id: int,
    project_id: str,
    connection_id: str,
    message: str,
) -> str:
    canonical = "\n".join(
        [
            tenant_id,
            str(user_id),
            project_id,
            connection_id,
            message.strip(),
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _matching_publish_jobs(
    *,
    session: Session,
    current_user: User,
    project_id: str,
    connection_id: str,
    platform: str,
    fingerprint: str,
) -> list[SocialPublishJob]:
    tenant_id = getattr(current_user, "tenant_id", "default")
    jobs = session.exec(
        select(SocialPublishJob).where(
            SocialPublishJob.tenant_id == tenant_id,
            SocialPublishJob.user_id == (current_user.id or 0),
            SocialPublishJob.project_id == project_id,
            SocialPublishJob.connection_id == connection_id,
            SocialPublishJob.platform == platform,
        ).order_by(SocialPublishJob.created_at.desc())
    ).all()
    return [
        job
        for job in jobs
        if str(_parse_json(job.payload_json, {}).get("idempotency_key") or "") == fingerprint
    ]


def _publish_failure_status(exc: Exception) -> str:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return "uncertain"
    if isinstance(exc, requests.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code is None or status_code >= 500:
            return "uncertain"
    return "failed"


def _create_job(
    *,
    session: Session,
    current_user: User,
    project_id: str,
    platform: str,
    connection_id: str,
    payload: dict[str, Any],
) -> SocialPublishJob:
    job = SocialPublishJob(
        tenant_id=getattr(current_user, "tenant_id", "default"),
        user_id=current_user.id or 0,
        project_id=project_id,
        platform=platform,
        connection_id=connection_id,
        status="queued",
        payload_json=_json_text(payload, {}),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _finish_job(
    *,
    session: Session,
    job: SocialPublishJob,
    status: str,
    published_url: str | None = None,
    remote_post_id: str | None = None,
    error_message: str | None = None,
) -> SocialPublishJob:
    job.status = status
    job.published_url = published_url
    job.remote_post_id = remote_post_id
    job.error_message = error_message
    job.updated_at = _utc_now()
    if status == "complete":
        job.published_at = _utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_connections(session: Session, current_user: User) -> list[SocialAccountConnection]:
    tenant_id = getattr(current_user, "tenant_id", "default")
    return session.exec(
        select(SocialAccountConnection).where(
            SocialAccountConnection.tenant_id == tenant_id,
            SocialAccountConnection.user_id == (current_user.id or 0),
        ).order_by(SocialAccountConnection.created_at.desc())
    ).all()


def list_admin_connections(session: Session, current_user: User) -> list[SocialAccountConnection]:
    return list_connections(session, current_user)


def _refresh_connection_access_token_if_needed(
    session: Session,
    connection: SocialAccountConnection,
) -> SocialAccountConnection:
    expires_at = connection.token_expires_at
    if not expires_at:
        return connection
    if expires_at > (_utc_now() + timedelta(minutes=2)):
        return connection

    refresh_token = _decrypt_secret(connection.refresh_token_encrypted)
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail=f"{connection.platform.title()} authorization expired; reconnect this account",
        )

    if connection.platform == "youtube":
        if not SOCIAL_YOUTUBE_CLIENT_ID or not SOCIAL_YOUTUBE_CLIENT_SECRET:
            raise HTTPException(status_code=503, detail="YouTube OAuth refresh credentials are not configured")
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": SOCIAL_YOUTUBE_CLIENT_ID,
                "client_secret": SOCIAL_YOUTUBE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = _clean_optional_text(payload.get("access_token"))
        if not access_token:
            raise HTTPException(status_code=502, detail="YouTube token refresh returned no access token")
        connection.access_token_encrypted = _encrypt_secret(access_token) or ""
        connection.token_expires_at = _utc_now() + timedelta(seconds=max(60, int(payload.get("expires_in") or 3600)))
        if payload.get("refresh_token"):
            connection.refresh_token_encrypted = _encrypt_secret(str(payload["refresh_token"]))

    elif connection.platform == "tiktok":
        if not SOCIAL_TIKTOK_CLIENT_KEY or not SOCIAL_TIKTOK_CLIENT_SECRET:
            raise HTTPException(status_code=503, detail="TikTok OAuth refresh credentials are not configured")
        response = requests.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": SOCIAL_TIKTOK_CLIENT_KEY,
                "client_secret": SOCIAL_TIKTOK_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = _clean_optional_text(payload.get("access_token"))
        if not access_token:
            raise HTTPException(status_code=502, detail="TikTok token refresh returned no access token")
        connection.access_token_encrypted = _encrypt_secret(access_token) or ""
        connection.token_expires_at = _utc_now() + timedelta(seconds=max(60, int(payload.get("expires_in") or 86400)))
        if payload.get("refresh_token"):
            connection.refresh_token_encrypted = _encrypt_secret(str(payload["refresh_token"]))
    else:
        raise HTTPException(
            status_code=401,
            detail=f"{connection.platform.title()} authorization expired; reconnect this account",
        )

    connection.updated_at = _utc_now()
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return connection


def _connection_has_publish_credentials(connection: SocialAccountConnection) -> bool:
    access_token = _decrypt_secret(connection.access_token_encrypted)
    access_token_secret = _decrypt_secret(connection.access_token_secret_encrypted)
    refresh_token = _decrypt_secret(connection.refresh_token_encrypted)
    client_key = _decrypt_secret(connection.client_key_encrypted)
    client_secret = _decrypt_secret(connection.client_secret_encrypted)
    if connection.platform == "x":
        return bool(access_token and access_token_secret and client_key and client_secret)
    return bool(access_token or access_token_secret or refresh_token or client_key or client_secret)


def _shared_social_user_ids(session: Session) -> list[int]:
    query = select(User).where(User.role == "admin")
    if OWNER_EMAIL_ALLOWLIST:
        allowlist = [email.strip().lower() for email in OWNER_EMAIL_ALLOWLIST if email.strip()]
        if allowlist:
            query = query.where(User.email.in_(allowlist))
    users = session.exec(query).all()
    return [user.id for user in users if user.id is not None]


def _shared_connection_for_platform(
    session: Session,
    current_user: User,
    platform: str,
    account_identifier: str | None = None,
) -> SocialAccountConnection | None:
    tenant_id = getattr(current_user, "tenant_id", "default")
    shared_user_ids = _shared_social_user_ids(session)
    if not shared_user_ids:
        return None
    base_query = select(SocialAccountConnection).where(
        SocialAccountConnection.tenant_id == tenant_id,
        SocialAccountConnection.user_id.in_(shared_user_ids),
        SocialAccountConnection.platform == platform,
        SocialAccountConnection.enabled.is_(True),
    )
    if account_identifier:
        exact_match = session.exec(
            base_query.where(SocialAccountConnection.account_identifier == account_identifier).order_by(
                SocialAccountConnection.updated_at.desc()
            )
        ).first()
        if exact_match:
            return exact_match
    return session.exec(base_query.order_by(SocialAccountConnection.updated_at.desc())).first()


def _resolve_publish_connection(
    session: Session,
    current_user: User,
    connection: SocialAccountConnection,
) -> SocialAccountConnection:
    if _connection_has_publish_credentials(connection):
        return connection
    shared = _shared_connection_for_platform(
        session,
        current_user,
        connection.platform,
        connection.account_identifier,
    )
    if shared and _connection_has_publish_credentials(shared):
        return shared
    return connection


def upsert_connection(
    session: Session,
    current_user: User,
    *,
    connection_id: str | None,
    platform: str,
    account_label: str,
    account_identifier: str | None,
    access_token: str | None,
    access_token_secret: str | None = None,
    refresh_token: str | None = None,
    client_key: str | None = None,
    client_secret: str | None = None,
    token_expires_at: datetime | None = None,
    scopes: list[str] | None = None,
    metadata: dict[str, str] | None = None,
    enabled: bool = True,
) -> SocialAccountConnection:
    platform = _normalize_platform(platform)
    tenant_id = getattr(current_user, "tenant_id", "default")
    scopes_json = _json_text(scopes or [], [])
    metadata_json = _json_text(_clean_metadata(metadata), {})
    existing = None
    if connection_id:
        existing = session.exec(
            select(SocialAccountConnection).where(
                SocialAccountConnection.connection_id == connection_id,
                SocialAccountConnection.tenant_id == tenant_id,
                SocialAccountConnection.user_id == (current_user.id or 0),
            )
        ).first()
    if existing is None:
        access_token_value = _clean_optional_text(access_token)
        enabled_state = bool(enabled)
        existing = SocialAccountConnection(
            tenant_id=tenant_id,
            user_id=current_user.id or 0,
            platform=platform,
            account_label=account_label.strip(),
            account_identifier=_clean_optional_text(account_identifier),
            access_token_encrypted=_encrypt_secret(access_token_value) or "",
            access_token_secret_encrypted=_encrypt_secret(access_token_secret),
            refresh_token_encrypted=_encrypt_secret(refresh_token),
            client_key_encrypted=_encrypt_secret(client_key),
            client_secret_encrypted=_encrypt_secret(client_secret),
            token_expires_at=token_expires_at,
            scopes_json=scopes_json,
            metadata_json=metadata_json,
            enabled=enabled_state,
        )
        session.add(existing)
    else:
        access_token_value = _clean_optional_text(access_token)
        existing.platform = platform
        existing.account_label = account_label.strip()
        existing.account_identifier = _clean_optional_text(account_identifier)
        if access_token_value is not None:
            existing.access_token_encrypted = _encrypt_secret(access_token_value) or ""
        if access_token_secret is not None:
            existing.access_token_secret_encrypted = _encrypt_secret(access_token_secret)
        if refresh_token is not None:
            existing.refresh_token_encrypted = _encrypt_secret(refresh_token)
        if client_key is not None:
            existing.client_key_encrypted = _encrypt_secret(client_key)
        if client_secret is not None:
            existing.client_secret_encrypted = _encrypt_secret(client_secret)
        existing.token_expires_at = token_expires_at
        existing.scopes_json = scopes_json
        existing.metadata_json = metadata_json
        existing.enabled = bool(enabled)
        existing.updated_at = _utc_now()
        session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def delete_connection(session: Session, current_user: User, connection_id: str) -> None:
    tenant_id = getattr(current_user, "tenant_id", "default")
    connection = session.exec(
        select(SocialAccountConnection).where(
            SocialAccountConnection.connection_id == connection_id,
            SocialAccountConnection.tenant_id == tenant_id,
            SocialAccountConnection.user_id == (current_user.id or 0),
        )
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Social connection not found")
    session.delete(connection)
    session.commit()


def list_publish_jobs(session: Session, current_user: User, project_id: str | None = None) -> list[SocialPublishJob]:
    tenant_id = getattr(current_user, "tenant_id", "default")
    query = select(SocialPublishJob).where(
        SocialPublishJob.tenant_id == tenant_id,
        SocialPublishJob.user_id == (current_user.id or 0),
    )
    if project_id:
        query = query.where(SocialPublishJob.project_id == project_id)
    return session.exec(query.order_by(SocialPublishJob.created_at.desc())).all()


def _oauth_percent_encode(value: str) -> str:
    return quote(value, safe="~-._")


def _oauth1_authorization_header(
    *,
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    extra_params: dict[str, str] | None = None,
) -> str:
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": base64.urlsafe_b64encode(os.urandom(18)).decode("utf-8").rstrip("="),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    params: list[tuple[str, str]] = list(parse_qsl(parsed.query, keep_blank_values=True))
    if extra_params:
        params.extend((str(key), str(value)) for key, value in extra_params.items())
    params.extend(oauth_params.items())
    encoded_params = "&".join(
        f"{_oauth_percent_encode(key)}={_oauth_percent_encode(value)}"
        for key, value in sorted(params, key=lambda item: (item[0], item[1]))
    )
    base_string = "&".join(
        [
            method.upper(),
            _oauth_percent_encode(base_url),
            _oauth_percent_encode(encoded_params),
        ]
    )
    signing_key = f"{_oauth_percent_encode(consumer_secret)}&{_oauth_percent_encode(token_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    oauth_params["oauth_signature"] = signature
    header = ", ".join(
        f'{key}="{_oauth_percent_encode(value)}"' for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {header}"


def _x_api_call(
    *,
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> requests.Response:
    extra_params: dict[str, str] = {}
    if params:
        extra_params.update({str(key): str(value) for key, value in params.items()})
    if data:
        extra_params.update({str(key): str(value) for key, value in data.items()})
    auth_header = _oauth1_authorization_header(
        method=method,
        url=url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=token,
        token_secret=token_secret,
        extra_params=extra_params,
    )
    headers = {"Authorization": auth_header}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    request_kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": timeout,
    }
    if params:
        request_kwargs["params"] = params
    if data:
        request_kwargs["data"] = data
    if json_body is not None:
        request_kwargs["json"] = json_body
    response = requests.request(method, url, **request_kwargs)
    response.raise_for_status()
    return response


def _publish_to_youtube(
    *,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> tuple[str, str | None]:
    access_token = _decrypt_secret(connection.access_token_encrypted)
    if not access_token:
        raise HTTPException(status_code=400, detail="YouTube access token is missing")
    video_bytes = _video_bytes(project.project_id)
    metadata = _parse_json(connection.metadata_json, {})
    snippet = {
        "title": _clean_optional_text(metadata.get("title")) or project.title,
        "description": message,
        "tags": metadata.get("tags", []),
        "categoryId": metadata.get("category_id", "22"),
    }
    status = {
        "privacyStatus": metadata.get("privacy_status", "public"),
        "selfDeclaredMadeForKids": bool(metadata.get("made_for_kids", False)),
    }
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    init_response = requests.post(
        init_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(video_bytes)),
        },
        json={"snippet": snippet, "status": status},
        timeout=90,
    )
    init_response.raise_for_status()
    upload_url = init_response.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube resumable upload did not return an upload URL")
    upload_response = requests.put(
        upload_url,
        headers={"Content-Type": "video/mp4", "Authorization": f"Bearer {access_token}"},
        data=video_bytes,
        timeout=300,
    )
    upload_response.raise_for_status()
    payload = upload_response.json()
    video_id = payload.get("id") or payload.get("videoId")
    if not video_id:
        raise RuntimeError("YouTube upload did not return a video id")
    return str(video_id), f"https://www.youtube.com/watch?v={video_id}"


def _publish_to_facebook(
    *,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> tuple[str, str | None]:
    access_token = _decrypt_secret(connection.access_token_encrypted)
    if not access_token:
        raise HTTPException(status_code=400, detail="Facebook access token is missing")
    page_id = _clean_optional_text(connection.account_identifier)
    if not page_id:
        raise HTTPException(status_code=400, detail="Facebook page/account id is required")
    video_url = _get_video_public_url(project.project_id)
    metadata = _parse_json(connection.metadata_json, {})
    payload = {
        "file_url": video_url,
        "description": message,
        "published": "true",
    }
    if metadata.get("title"):
        payload["title"] = str(metadata["title"])
    response = requests.post(
        f"https://graph.facebook.com/v21.0/{page_id}/videos",
        data={**payload, "access_token": access_token},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    remote_id = str(data.get("id") or data.get("video_id") or "")
    published_url = f"https://www.facebook.com/{page_id}/videos/{remote_id}" if remote_id else None
    return remote_id, published_url


def _publish_to_instagram(
    *,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> tuple[str, str | None]:
    access_token = _decrypt_secret(connection.access_token_encrypted)
    if not access_token:
        raise HTTPException(status_code=400, detail="Instagram access token is missing")
    ig_user_id = _clean_optional_text(connection.account_identifier)
    if not ig_user_id:
        raise HTTPException(status_code=400, detail="Instagram user id is required")
    video_url = _get_video_public_url(project.project_id)
    create_response = requests.post(
        f"https://graph.facebook.com/v21.0/{ig_user_id}/media",
        data={
            "media_type": "VIDEO",
            "video_url": video_url,
            "caption": message,
            "access_token": access_token,
        },
        timeout=120,
    )
    create_response.raise_for_status()
    creation_id = str(create_response.json().get("id") or "")
    if not creation_id:
        raise RuntimeError("Instagram media container was not created")
    publish_response = requests.post(
        f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=120,
    )
    publish_response.raise_for_status()
    data = publish_response.json()
    remote_id = str(data.get("id") or creation_id)
    return remote_id, f"https://www.instagram.com/p/{remote_id}/"


def _x_upload_media_bytes(
    *,
    video_bytes: bytes,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
) -> str:
    init_url = "https://upload.twitter.com/1.1/media/upload.json"
    init_response = _x_api_call(
        method="POST",
        url=init_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=token,
        token_secret=token_secret,
        data={
            "command": "INIT",
            "media_type": "video/mp4",
            "media_category": "tweet_video",
            "total_bytes": str(len(video_bytes)),
        },
        timeout=120,
    )
    media_id = str(init_response.json().get("media_id_string") or "")
    if not media_id:
        raise RuntimeError("X media INIT did not return a media_id")

    chunk_size = 4 * 1024 * 1024
    for index, start in enumerate(range(0, len(video_bytes), chunk_size)):
        chunk = video_bytes[start : start + chunk_size]
        auth_header = _oauth1_authorization_header(
            method="POST",
            url=init_url,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            token=token,
            token_secret=token_secret,
            extra_params={"command": "APPEND", "media_id": media_id, "segment_index": str(index)},
        )
        multipart_response = requests.post(
            init_url,
            headers={"Authorization": auth_header},
            files={"media": ("video.mp4", chunk, "video/mp4")},
            data={
                "command": "APPEND",
                "media_id": media_id,
                "segment_index": str(index),
            },
            timeout=120,
        )
        multipart_response.raise_for_status()

    finalize_response = _x_api_call(
        method="POST",
        url=init_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=token,
        token_secret=token_secret,
        data={"command": "FINALIZE", "media_id": media_id},
        timeout=120,
    )
    finalize_payload = finalize_response.json()
    processing_info = finalize_payload.get("processing_info") or {}
    state = processing_info.get("state")
    if state in {"pending", "in_progress"}:
        check_after_secs = int(processing_info.get("check_after_secs") or 5)
        deadline = time.time() + 180
        status_url = f"{init_url}?command=STATUS&media_id={media_id}"
        while time.time() < deadline:
            time.sleep(max(1, min(check_after_secs, 10)))
            status_response = _x_api_call(
                method="GET",
                url=status_url,
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                token=token,
                token_secret=token_secret,
                timeout=60,
            )
            status_payload = status_response.json()
            processing_info = status_payload.get("processing_info") or {}
            state = processing_info.get("state")
            if state == "succeeded":
                break
            if state == "failed":
                raise RuntimeError(f"X media processing failed: {processing_info.get('error', {})}")
        else:
            raise RuntimeError("X media processing timed out")
    return media_id


def _publish_to_x(
    *,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> tuple[str, str | None]:
    token = _decrypt_secret(connection.access_token_encrypted)
    token_secret = _decrypt_secret(connection.access_token_secret_encrypted)
    consumer_key = _decrypt_secret(connection.client_key_encrypted)
    consumer_secret = _decrypt_secret(connection.client_secret_encrypted)
    if not token or not token_secret:
        raise HTTPException(status_code=400, detail="X OAuth token and token secret are required")
    if not consumer_key or not consumer_secret:
        raise HTTPException(
            status_code=400,
            detail="X consumer key and consumer secret are required for direct publishing",
        )
    media_id = _x_upload_media_bytes(
        video_bytes=_video_bytes(project.project_id),
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=token,
        token_secret=token_secret,
    )
    tweet_response = _x_api_call(
        method="POST",
        url="https://api.x.com/1.1/statuses/update.json",
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=token,
        token_secret=token_secret,
        data={
            "status": message,
            "media_ids": media_id,
        },
        timeout=120,
    )
    tweet_payload = tweet_response.json()
    tweet_id = str(tweet_payload.get("id_str") or tweet_payload.get("id") or "")
    return tweet_id or media_id, f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None


def _tiktok_api_call(
    *,
    method: str,
    url: str,
    access_token: str,
    json_body: dict[str, Any] | None = None,
    timeout: int = 90,
) -> requests.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json; charset=UTF-8"
    request_kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
    if json_body is not None:
        request_kwargs["json"] = json_body
    response = requests.request(method, url, **request_kwargs)
    response.raise_for_status()
    if json_body is not None:
        try:
            payload = response.json()
        except ValueError:
            return response
        error = dict(payload.get("error") or {})
        error_code = str(error.get("code") or "").strip().lower()
        if error_code and error_code not in {"ok", "success", "0"}:
            message = error.get("message") or "unknown error"
            raise RuntimeError(f"TikTok API error: {message}")
    return response


def _tiktok_creator_info(access_token: str) -> dict[str, Any]:
    response = _tiktok_api_call(
        method="POST",
        url="https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        access_token=access_token,
        json_body={},
        timeout=90,
    )
    payload = response.json()
    return dict(payload.get("data") or {})


def _tiktok_upload_video_bytes(upload_url: str, video_bytes: bytes) -> None:
    if not video_bytes:
        raise HTTPException(status_code=400, detail="TikTok video payload is empty")
    total = len(video_bytes)
    if total < 5 * 1024 * 1024:
        chunks = [video_bytes]
    else:
        chunk_size = min(64 * 1024 * 1024, max(5 * 1024 * 1024, total // 2))
        chunk_count = max(1, total // chunk_size)
        chunks = []
        offset = 0
        for index in range(chunk_count):
            if index == chunk_count - 1:
                chunk = video_bytes[offset:]
            else:
                chunk = video_bytes[offset : offset + chunk_size]
            chunks.append(chunk)
            offset += len(chunk)
    offset = 0
    for chunk in chunks:
        end = offset + len(chunk) - 1
        response = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end}/{total}",
            },
            data=chunk,
            timeout=300,
        )
        response.raise_for_status()
        offset = end + 1


def _tiktok_poll_publish_status(access_token: str, publish_id: str) -> dict[str, Any]:
    deadline = time.time() + 300
    status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        response = _tiktok_api_call(
            method="POST",
            url=status_url,
            access_token=access_token,
            json_body={"publish_id": publish_id},
            timeout=90,
        )
        payload = dict(response.json().get("data") or {})
        last_payload = payload
        status = str(payload.get("status") or "")
        if status == "PUBLISH_COMPLETE":
            return payload
        if status == "FAILED":
            raise RuntimeError(f"TikTok publish failed: {payload.get('fail_reason') or 'unknown error'}")
        time.sleep(5)
    raise RuntimeError(f"TikTok publish timed out: {json.dumps(last_payload)}")


def _publish_to_tiktok(
    *,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> tuple[str, str | None]:
    access_token = _decrypt_secret(connection.access_token_encrypted)
    if not access_token:
        raise HTTPException(status_code=400, detail="TikTok access token is missing")

    video_bytes = _video_bytes(project.project_id)
    video_size = len(video_bytes)
    creator_info = _tiktok_creator_info(access_token)
    privacy_options = [str(option) for option in creator_info.get("privacy_level_options") or []]
    metadata = _parse_json(connection.metadata_json, {})
    preferred_privacy = _clean_optional_text(metadata.get("privacy_level")) or "SELF_ONLY"
    if preferred_privacy not in privacy_options:
        preferred_privacy = "SELF_ONLY" if "SELF_ONLY" in privacy_options else (privacy_options[0] if privacy_options else "SELF_ONLY")

    chunk_size = video_size if video_size < 5 * 1024 * 1024 else min(64 * 1024 * 1024, max(5 * 1024 * 1024, video_size // 2))
    total_chunk_count = max(1, video_size // chunk_size)

    response = _tiktok_api_call(
        method="POST",
        url="https://open.tiktokapis.com/v2/post/publish/video/init/",
        access_token=access_token,
        json_body={
            "post_info": {
                "title": message[:2200],
                "privacy_level": preferred_privacy,
                "disable_duet": bool(metadata.get("disable_duet", creator_info.get("duet_disabled", False))),
                "disable_comment": bool(metadata.get("disable_comment", creator_info.get("comment_disabled", False))),
                "disable_stitch": bool(metadata.get("disable_stitch", creator_info.get("stitch_disabled", False))),
                "is_aigc": bool(metadata.get("is_aigc", True)),
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        },
        timeout=90,
    )
    init_payload = dict(response.json().get("data") or {})
    publish_id = str(init_payload.get("publish_id") or "")
    upload_url = _clean_optional_text(init_payload.get("upload_url"))
    if not publish_id:
        raise RuntimeError("TikTok publish init did not return a publish id")
    if not upload_url:
        raise RuntimeError("TikTok publish init did not return an upload URL")

    _tiktok_upload_video_bytes(upload_url, video_bytes)
    status_payload = _tiktok_poll_publish_status(access_token, publish_id)
    post_ids = status_payload.get("publicaly_available_post_id") or []
    post_id = str(post_ids[0]) if post_ids else None
    username = _clean_optional_text(creator_info.get("creator_username"))
    published_url = f"https://www.tiktok.com/@{username}/video/{post_id}" if username and post_id else (
        f"https://www.tiktok.com/@{username}" if username else None
    )
    return publish_id, published_url


def _rate_limit_retry_delay(exc: Exception, attempt: int) -> float | None:
    """Return a safe retry delay only when the remote request was explicitly rate-limited.

    Timeouts, connection failures, and 5xx responses are deliberately not retried
    here because the remote platform may already have accepted the post.
    """
    if not isinstance(exc, requests.HTTPError) or exc.response is None:
        return None
    if exc.response.status_code != 429:
        return None
    retry_after = exc.response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(60.0, max(0.25, float(retry_after)))
        except (TypeError, ValueError):
            pass
    return min(
        60.0,
        SOCIAL_PUBLISH_RETRY_BACKOFF_SECONDS * (2 ** max(0, attempt - 1)),
    )


def _publish_remote_once(
    *,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> tuple[str, str | None]:
    if connection.platform == "youtube":
        return _publish_to_youtube(project=project, connection=connection, message=message)
    if connection.platform == "instagram":
        return _publish_to_instagram(project=project, connection=connection, message=message)
    if connection.platform == "facebook":
        return _publish_to_facebook(project=project, connection=connection, message=message)
    if connection.platform == "x":
        return _publish_to_x(project=project, connection=connection, message=message)
    if connection.platform == "tiktok":
        return _publish_to_tiktok(project=project, connection=connection, message=message)
    raise RuntimeError(f"Unsupported platform: {connection.platform}")


def _publish_connection(
    *,
    session: Session,
    current_user: User,
    project: Project,
    connection: SocialAccountConnection,
    message: str,
) -> SocialPublishJob:
    tenant_id = getattr(current_user, "tenant_id", "default")
    fingerprint = _publish_fingerprint(
        tenant_id=tenant_id,
        user_id=current_user.id or 0,
        project_id=project.project_id,
        connection_id=connection.connection_id,
        message=message,
    )
    matching_jobs = _matching_publish_jobs(
        session=session,
        current_user=current_user,
        project_id=project.project_id,
        connection_id=connection.connection_id,
        platform=connection.platform,
        fingerprint=fingerprint,
    )
    for existing in matching_jobs:
        if existing.status in {"complete", "queued", "processing", "uncertain"}:
            return existing

    previous_attempts = 0
    for existing in matching_jobs:
        payload = _parse_json(existing.payload_json, {})
        try:
            previous_attempts = max(previous_attempts, int(payload.get("attempt") or 0))
        except (TypeError, ValueError):
            continue

    publish_connection = _resolve_publish_connection(session, current_user, connection)
    publish_connection = _refresh_connection_access_token_if_needed(session, publish_connection)
    payload = {
        "message": message,
        "platform": publish_connection.platform,
        "account_identifier": publish_connection.account_identifier,
        "idempotency_key": fingerprint,
        "attempt": previous_attempts + 1,
    }
    job = _create_job(
        session=session,
        current_user=current_user,
        project_id=project.project_id,
        platform=publish_connection.platform,
        connection_id=connection.connection_id,
        payload=payload,
    )
    job.status = "processing"
    job.updated_at = _utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)

    try:
        if not connection.enabled and _connection_has_publish_credentials(connection):
            raise RuntimeError("Connection is disabled")
        remote_id = ""
        published_url: str | None = None
        last_error: Exception | None = None
        transport_attempts = 0
        for transport_attempt in range(1, SOCIAL_PUBLISH_MAX_ATTEMPTS + 1):
            transport_attempts = transport_attempt
            try:
                remote_id, published_url = _publish_remote_once(
                    project=project,
                    connection=publish_connection,
                    message=message,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                delay = _rate_limit_retry_delay(exc, transport_attempt)
                if delay is None or transport_attempt >= SOCIAL_PUBLISH_MAX_ATTEMPTS:
                    raise
                time.sleep(delay)
        if last_error is not None:
            raise last_error
        payload["transport_attempts"] = transport_attempts
        job.payload_json = _json_text(payload, {})
        session.add(job)
        session.commit()
        consume_credits(
            session=session,
            user=current_user,
            amount=CREDITS_COST_VIDEO_EXPORT,
            reason=f"social publish to {publish_connection.platform}",
            action="social.publish",
            reference_id=project.project_id,
            provider=publish_connection.platform,
            model="direct",
        )
        return _finish_job(
            session=session,
            job=job,
            status="complete",
            remote_post_id=remote_id,
            published_url=published_url,
        )
    except Exception as exc:
        return _finish_job(
            session=session,
            job=job,
            status=_publish_failure_status(exc),
            error_message=str(exc),
        )

def publish_to_connections(
    *,
    session: Session,
    current_user: User,
    project_id: str,
    connection_ids: Iterable[str],
    message: str | None = None,
    title: str | None = None,
) -> list[SocialPublishJob]:
    project = _get_project(session, project_id)
    text = _build_message(project, message, title)
    tenant_id = getattr(current_user, "tenant_id", "default")
    connections = session.exec(
        select(SocialAccountConnection).where(
            SocialAccountConnection.tenant_id == tenant_id,
            SocialAccountConnection.user_id == (current_user.id or 0),
            SocialAccountConnection.connection_id.in_(list(connection_ids)),
        )
    ).all()
    if not connections:
        raise HTTPException(status_code=400, detail="No matching social connections were selected")
    jobs = [_publish_connection(session=session, current_user=current_user, project=project, connection=conn, message=text) for conn in connections]
    return jobs


def publish_to_all_connections(
    *,
    session: Session,
    current_user: User,
    project_id: str,
    message: str | None = None,
    title: str | None = None,
) -> list[SocialPublishJob]:
    project = _get_project(session, project_id)
    text = _build_message(project, message, title)
    connections = list_connections(session, current_user)
    if not connections:
        raise HTTPException(status_code=400, detail="No connected social accounts found")
    return [
        _publish_connection(session=session, current_user=current_user, project=project, connection=connection, message=text)
        for connection in connections
    ]
