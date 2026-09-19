from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

import redis
import requests
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.config import (
    JWT_ALGORITHM,
    JWT_SECRET,
    REDIS_URL,
    SOCIAL_META_APP_ID,
    SOCIAL_META_APP_SECRET,
    SOCIAL_META_GRAPH_VERSION,
    SOCIAL_OAUTH_FRONTEND_ORIGIN,
    SOCIAL_TIKTOK_CLIENT_KEY,
    SOCIAL_TIKTOK_CLIENT_SECRET,
    SOCIAL_X_API_KEY,
    SOCIAL_X_API_SECRET,
    SOCIAL_YOUTUBE_CLIENT_ID,
    SOCIAL_YOUTUBE_CLIENT_SECRET,
)
from app.models import User
from app.services.social_publish import upsert_connection
from app.tenant import current_tenant_id

STATE_TTL_SECONDS = 10 * 60
PLATFORMS = {"youtube", "facebook", "instagram", "x", "tiktok"}
_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _frontend_callback(platform: str) -> str:
    return f"{SOCIAL_OAUTH_FRONTEND_ORIGIN}/?nav=publish&social_oauth={quote(platform)}"


def _encode_state(user: User, platform: str, *, nonce: str | None = None) -> str:
    payload = {
        "scope": "social_oauth",
        "sub": user.email,
        "uid": int(user.id or 0),
        "tenant": current_tenant_id(),
        "platform": platform,
        "nonce": nonce or secrets.token_urlsafe(24),
        "exp": int((_now() + timedelta(seconds=STATE_TTL_SECONDS)).timestamp()),
        "iat": int(_now().timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_state(state: str, user: User, platform: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired social authorization state") from exc
    if payload.get("scope") != "social_oauth":
        raise HTTPException(status_code=400, detail="Invalid social authorization state")
    if str(payload.get("sub") or "").strip().lower() != user.email.strip().lower():
        raise HTTPException(status_code=401, detail="Social authorization state does not match user")
    if str(payload.get("platform") or "") != platform:
        raise HTTPException(status_code=400, detail="Social authorization platform mismatch")
    if str(payload.get("tenant") or "") != current_tenant_id():
        raise HTTPException(status_code=403, detail="Social authorization tenant mismatch")
    return payload


def _require(value: str, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=503, detail=f"{label} is not configured")
    return cleaned


def _oauth1_encode(value: str) -> str:
    return quote(str(value), safe="~-._")


def _oauth1_signature(
    *,
    method: str,
    url: str,
    consumer_secret: str,
    token_secret: str = "",
    params: dict[str, str],
) -> str:
    encoded = sorted((_oauth1_encode(k), _oauth1_encode(v)) for k, v in params.items())
    param_string = "&".join(f"{k}={v}" for k, v in encoded)
    base_string = "&".join(
        [_oauth1_encode(method.upper()), _oauth1_encode(url), _oauth1_encode(param_string)]
    )
    signing_key = f"{_oauth1_encode(consumer_secret)}&{_oauth1_encode(token_secret)}"
    digest = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _oauth1_header(
    *,
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str | None = None,
    token_secret: str = "",
    extra_params: dict[str, str] | None = None,
) -> str:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    }
    if token:
        params["oauth_token"] = token
    if extra_params:
        params.update(extra_params)
    signature = _oauth1_signature(
        method=method,
        url=url,
        consumer_secret=consumer_secret,
        token_secret=token_secret,
        params=params,
    )
    params["oauth_signature"] = signature
    return "OAuth " + ", ".join(
        f'{_oauth1_encode(k)}="{_oauth1_encode(v)}"' for k, v in sorted(params.items())
    )


def begin_social_oauth(platform: str, user: User) -> dict[str, str]:
    platform = platform.strip().lower()
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported social platform")

    state = _encode_state(user, platform)
    redirect_uri = _frontend_callback(platform)

    if platform == "youtube":
        client_id = _require(SOCIAL_YOUTUBE_CLIENT_ID, "YouTube OAuth client ID")
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        return {"authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}", "state": state}

    if platform in {"facebook", "instagram"}:
        app_id = _require(SOCIAL_META_APP_ID, "Meta app ID")
        scopes = [
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
        ]
        if platform == "instagram":
            scopes.extend(["instagram_basic", "instagram_content_publish"])
        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(scopes),
            "state": state,
        }
        return {
            "authorization_url": f"https://www.facebook.com/{SOCIAL_META_GRAPH_VERSION}/dialog/oauth?{urlencode(params)}",
            "state": state,
        }

    if platform == "tiktok":
        client_key = _require(SOCIAL_TIKTOK_CLIENT_KEY, "TikTok client key")
        params = {
            "client_key": client_key,
            "response_type": "code",
            "scope": "user.info.basic,video.publish",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return {
            "authorization_url": f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}",
            "state": state,
        }

    consumer_key = _require(SOCIAL_X_API_KEY, "X API key")
    consumer_secret = _require(SOCIAL_X_API_SECRET, "X API secret")
    nonce = secrets.token_urlsafe(24)
    state = _encode_state(user, platform, nonce=nonce)
    callback = f"{redirect_uri}&state={quote(state)}"
    request_url = "https://api.x.com/oauth/request_token"
    header = _oauth1_header(
        method="POST",
        url=request_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        extra_params={"oauth_callback": callback},
    )
    response = requests.post(
        request_url,
        headers={"Authorization": header},
        data={"oauth_callback": callback},
        timeout=30,
    )
    response.raise_for_status()
    payload = dict(parse_qsl(response.text))
    request_token = payload.get("oauth_token")
    request_secret = payload.get("oauth_token_secret")
    if not request_token or not request_secret:
        raise HTTPException(status_code=502, detail="X did not return an OAuth request token")
    _redis.setex(f"social:x:req:{nonce}", STATE_TTL_SECONDS, request_secret)
    return {
        "authorization_url": f"https://api.x.com/oauth/authorize?oauth_token={quote(request_token)}",
        "state": state,
    }


def _token_expiry(expires_in: Any) -> datetime | None:
    try:
        seconds = int(expires_in)
    except Exception:
        return None
    return (_now() + timedelta(seconds=max(60, seconds))).replace(tzinfo=None)


def _complete_youtube(session: Session, user: User, code: str) -> Any:
    redirect_uri = _frontend_callback("youtube")
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": _require(SOCIAL_YOUTUBE_CLIENT_ID, "YouTube OAuth client ID"),
            "client_secret": _require(SOCIAL_YOUTUBE_CLIENT_SECRET, "YouTube OAuth client secret"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise HTTPException(status_code=502, detail="YouTube token exchange returned no access token")

    profile = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    profile.raise_for_status()
    items = profile.json().get("items") or []
    channel = items[0] if items else {}
    channel_id = str(channel.get("id") or "")
    title = str((channel.get("snippet") or {}).get("title") or "YouTube Channel")
    scopes = str(token.get("scope") or "").split()
    return upsert_connection(
        session,
        user,
        connection_id=None,
        platform="youtube",
        account_label=title,
        account_identifier=channel_id or None,
        access_token=access_token,
        refresh_token=str(token.get("refresh_token") or "") or None,
        token_expires_at=_token_expiry(token.get("expires_in")),
        scopes=scopes,
        metadata={"oauth": "google"},
        enabled=True,
    )


def _meta_pages(access_token: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"https://graph.facebook.com/{SOCIAL_META_GRAPH_VERSION}/me/accounts",
        params={
            "fields": "id,name,access_token,instagram_business_account{id,username}",
            "access_token": access_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    return list(response.json().get("data") or [])


def _complete_meta(session: Session, user: User, platform: str, code: str) -> Any:
    redirect_uri = _frontend_callback(platform)
    response = requests.get(
        f"https://graph.facebook.com/{SOCIAL_META_GRAPH_VERSION}/oauth/access_token",
        params={
            "client_id": _require(SOCIAL_META_APP_ID, "Meta app ID"),
            "client_secret": _require(SOCIAL_META_APP_SECRET, "Meta app secret"),
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()
    user_token = str(token.get("access_token") or "")
    if not user_token:
        raise HTTPException(status_code=502, detail="Meta token exchange returned no access token")
    pages = _meta_pages(user_token)
    if not pages:
        raise HTTPException(status_code=400, detail="No eligible Facebook Page was found for this account")

    if platform == "facebook":
        page = pages[0]
        page_id = str(page.get("id") or "")
        page_token = str(page.get("access_token") or user_token)
        return upsert_connection(
            session,
            user,
            connection_id=None,
            platform="facebook",
            account_label=str(page.get("name") or "Facebook Page"),
            account_identifier=page_id or None,
            access_token=page_token,
            scopes=["pages_show_list", "pages_read_engagement", "pages_manage_posts"],
            metadata={"oauth": "meta"},
            enabled=True,
        )

    page = next((item for item in pages if item.get("instagram_business_account")), None)
    if not page:
        raise HTTPException(
            status_code=400,
            detail="No Instagram professional account connected to a Facebook Page was found",
        )
    ig = dict(page.get("instagram_business_account") or {})
    ig_id = str(ig.get("id") or "")
    page_token = str(page.get("access_token") or user_token)
    return upsert_connection(
        session,
        user,
        connection_id=None,
        platform="instagram",
        account_label=str(ig.get("username") or page.get("name") or "Instagram"),
        account_identifier=ig_id or None,
        access_token=page_token,
        scopes=["instagram_basic", "instagram_content_publish"],
        metadata={"oauth": "meta", "facebook_page_id": str(page.get("id") or "")},
        enabled=True,
    )


def _complete_tiktok(session: Session, user: User, code: str) -> Any:
    redirect_uri = _frontend_callback("tiktok")
    response = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": _require(SOCIAL_TIKTOK_CLIENT_KEY, "TikTok client key"),
            "client_secret": _require(SOCIAL_TIKTOK_CLIENT_SECRET, "TikTok client secret"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()
    access_token = str(token.get("access_token") or "")
    if not access_token:
        raise HTTPException(status_code=502, detail="TikTok token exchange returned no access token")
    user_response = requests.get(
        "https://open.tiktokapis.com/v2/user/info/",
        params={"fields": "open_id,union_id,avatar_url,display_name,username"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    user_response.raise_for_status()
    user_data = dict((user_response.json().get("data") or {}).get("user") or {})
    account_identifier = str(user_data.get("open_id") or token.get("open_id") or "")
    label = str(user_data.get("display_name") or user_data.get("username") or "TikTok")
    scope_text = str(token.get("scope") or "")
    return upsert_connection(
        session,
        user,
        connection_id=None,
        platform="tiktok",
        account_label=label,
        account_identifier=account_identifier or None,
        access_token=access_token,
        refresh_token=str(token.get("refresh_token") or "") or None,
        token_expires_at=_token_expiry(token.get("expires_in")),
        scopes=[item for item in scope_text.split(",") if item],
        metadata={"oauth": "tiktok", "username": str(user_data.get("username") or "")},
        enabled=True,
    )


def _complete_x(
    session: Session,
    user: User,
    *,
    state_payload: dict[str, Any],
    oauth_token: str,
    oauth_verifier: str,
) -> Any:
    nonce = str(state_payload.get("nonce") or "")
    request_secret = _redis.get(f"social:x:req:{nonce}")
    if not request_secret:
        raise HTTPException(status_code=400, detail="X authorization request expired; connect again")
    access_url = "https://api.x.com/oauth/access_token"
    consumer_key = _require(SOCIAL_X_API_KEY, "X API key")
    consumer_secret = _require(SOCIAL_X_API_SECRET, "X API secret")
    header = _oauth1_header(
        method="POST",
        url=access_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        token=oauth_token,
        token_secret=request_secret,
        extra_params={"oauth_verifier": oauth_verifier},
    )
    response = requests.post(
        access_url,
        headers={"Authorization": header},
        data={"oauth_verifier": oauth_verifier},
        timeout=30,
    )
    response.raise_for_status()
    payload = dict(parse_qsl(response.text))
    access_token = str(payload.get("oauth_token") or "")
    access_secret = str(payload.get("oauth_token_secret") or "")
    if not access_token or not access_secret:
        raise HTTPException(status_code=502, detail="X token exchange returned incomplete credentials")
    _redis.delete(f"social:x:req:{nonce}")
    return upsert_connection(
        session,
        user,
        connection_id=None,
        platform="x",
        account_label=str(payload.get("screen_name") or "X"),
        account_identifier=str(payload.get("user_id") or payload.get("screen_name") or "") or None,
        access_token=access_token,
        access_token_secret=access_secret,
        client_key=consumer_key,
        client_secret=consumer_secret,
        scopes=["write"],
        metadata={"oauth": "x_oauth1", "screen_name": str(payload.get("screen_name") or "")},
        enabled=True,
    )


def complete_social_oauth(
    session: Session,
    user: User,
    *,
    platform: str,
    state: str,
    code: str | None = None,
    oauth_token: str | None = None,
    oauth_verifier: str | None = None,
):
    platform = platform.strip().lower()
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported social platform")
    state_payload = _decode_state(state, user, platform)

    if platform == "youtube":
        if not code:
            raise HTTPException(status_code=400, detail="YouTube authorization code is missing")
        return _complete_youtube(session, user, code)
    if platform in {"facebook", "instagram"}:
        if not code:
            raise HTTPException(status_code=400, detail="Meta authorization code is missing")
        return _complete_meta(session, user, platform, code)
    if platform == "tiktok":
        if not code:
            raise HTTPException(status_code=400, detail="TikTok authorization code is missing")
        return _complete_tiktok(session, user, code)

    if not oauth_token or not oauth_verifier:
        raise HTTPException(status_code=400, detail="X OAuth callback values are missing")
    return _complete_x(
        session,
        user,
        state_payload=state_payload,
        oauth_token=oauth_token,
        oauth_verifier=oauth_verifier,
    )
