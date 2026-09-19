from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete
from sqlmodel import Session, select

from app.models import VisitEvent
from app.schemas import (
    VisitAnalyticsBreakdownResponse,
    VisitAnalyticsDailyPointResponse,
    VisitAnalyticsSummaryResponse,
    VisitAnalyticsTopPathResponse,
    VisitEventCreateRequest,
    VisitEventResponse,
)
from app.tenant import current_tenant_id

BOT_MARKERS: tuple[tuple[str, str], ...] = (
    ("googlebot", "user_agent:googlebot"),
    ("bingbot", "user_agent:bingbot"),
    ("duckduckbot", "user_agent:duckduckbot"),
    ("yandexbot", "user_agent:yandexbot"),
    ("baiduspider", "user_agent:baiduspider"),
    ("slurp", "user_agent:slurp"),
    ("crawler", "user_agent:crawler"),
    ("spider", "user_agent:spider"),
    ("bot", "user_agent:bot"),
    ("headless", "user_agent:headless"),
    ("playwright", "user_agent:playwright"),
    ("puppeteer", "user_agent:puppeteer"),
    ("selenium", "user_agent:selenium"),
    ("scrapy", "user_agent:scrapy"),
    ("curl", "user_agent:curl"),
    ("wget", "user_agent:wget"),
    ("python-requests", "user_agent:python-requests"),
    ("httpclient", "user_agent:httpclient"),
    ("postman", "user_agent:postman"),
    ("lighthouse", "user_agent:lighthouse"),
)

MOBILE_MARKERS = ("android", "iphone", "ipod", "mobile", "mobi")
TABLET_MARKERS = ("ipad", "tablet", "kindle", "playbook", "silk")
VISIT_DEDUP_WINDOW_SECONDS = 3


def detect_bot(user_agent: str | None, bot_hint: bool = False) -> tuple[bool, str | None]:
    if bot_hint:
        return True, "client_hint"
    normalized = (user_agent or "").strip().lower()
    if not normalized:
        return False, None
    for marker, reason in BOT_MARKERS:
        if marker in normalized:
            return True, reason
    return False, None


def detect_device_type(
    user_agent: str | None,
    is_bot: bool = False,
    device_hint: str | None = None,
) -> str:
    if is_bot:
        return "bot"
    normalized_hint = (device_hint or "").strip().lower()
    if normalized_hint in {"desktop", "mobile", "tablet"}:
        return normalized_hint
    normalized = (user_agent or "").strip().lower()
    if not normalized:
        return "unknown"
    if any(marker in normalized for marker in TABLET_MARKERS):
        return "tablet"
    if any(marker in normalized for marker in MOBILE_MARKERS):
        return "mobile"
    return "desktop"


def normalize_country_code(country_hint: str | None) -> str | None:
    if not country_hint:
        return None
    normalized = country_hint.strip().upper()
    if not normalized or normalized in {"UNKNOWN", "N/A", "NONE", "NULL"}:
        return None
    separators = ("-", "_")
    for separator in separators:
        if separator in normalized:
            parts = [part for part in normalized.split(separator) if part]
            if parts:
                normalized = parts[-1]
                break
    if len(normalized) >= 2 and normalized[:2].isalpha():
        return normalized[:2]
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    return None


def _normalize_path(path: str) -> str:
    clean = path.strip()
    if not clean.startswith("/"):
        clean = f"/{clean}"
    return clean[:512]


def _find_recent_duplicate_visit(session: Session, payload: VisitEventCreateRequest, *, tenant_id: str, is_bot: bool, bot_reason: str | None, device_type: str, country_code: str | None) -> VisitEvent | None:
    created_at_floor = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=VISIT_DEDUP_WINDOW_SECONDS)
    path = _normalize_path(payload.path)
    event_type = payload.event_type.strip().lower() or "page_view"
    recent_events = session.exec(
        select(VisitEvent)
        .where(
            VisitEvent.tenant_id == tenant_id,
            VisitEvent.path == path,
            VisitEvent.referrer == (payload.referrer or None),
            VisitEvent.user_agent == (payload.user_agent or None),
            VisitEvent.device_type == device_type,
            VisitEvent.country_code == country_code,
            VisitEvent.page_title == (payload.page_title or None),
            VisitEvent.session_id == (payload.session_id or None),
            VisitEvent.event_type == event_type,
            VisitEvent.is_bot == is_bot,
            VisitEvent.bot_reason == bot_reason,
            VisitEvent.created_at >= created_at_floor,
        )
        .order_by(VisitEvent.created_at.desc())
    ).all()
    return recent_events[0] if recent_events else None


def _to_response(event: VisitEvent) -> VisitEventResponse:
    return VisitEventResponse(
        visit_id=event.visit_id,
        path=event.path,
        referrer=event.referrer,
        device_type=event.device_type,
        country_code=event.country_code,
        page_title=event.page_title,
        session_id=event.session_id,
        event_type=event.event_type,
        is_bot=event.is_bot,
        bot_reason=event.bot_reason,
        created_at=event.created_at,
    )


def record_visit(session: Session, payload: VisitEventCreateRequest) -> VisitEvent:
    is_bot, bot_reason = detect_bot(payload.user_agent, payload.bot_hint)
    device_type = detect_device_type(payload.user_agent, is_bot, payload.device_hint)
    country_code = normalize_country_code(payload.country_hint)
    tenant_id = current_tenant_id()
    duplicate_event = _find_recent_duplicate_visit(
        session,
        payload,
        tenant_id=tenant_id,
        is_bot=is_bot,
        bot_reason=bot_reason,
        device_type=device_type,
        country_code=country_code,
    )
    if duplicate_event is not None:
        return duplicate_event
    event = VisitEvent(
        tenant_id=tenant_id,
        path=_normalize_path(payload.path),
        referrer=(payload.referrer or None),
        user_agent=(payload.user_agent or None),
        device_type=device_type,
        country_code=country_code,
        page_title=(payload.page_title or None),
        session_id=(payload.session_id or None),
        event_type=payload.event_type.strip().lower() or "page_view",
        is_bot=is_bot,
        bot_reason=bot_reason,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def summarize_visits(session: Session, window_days: int = 30) -> VisitAnalyticsSummaryResponse:
    tenant = current_tenant_id()
    events = session.exec(
        select(VisitEvent)
        .where(VisitEvent.tenant_id == tenant)
        .order_by(VisitEvent.created_at.asc())
    ).all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last_24h_cutoff = now - timedelta(days=1)
    last_7d_cutoff = now - timedelta(days=7)
    window_cutoff = now - timedelta(days=max(1, window_days))

    total_visits = len(events)
    human_visits = sum(1 for event in events if not event.is_bot)
    bot_visits = total_visits - human_visits
    unique_sessions = len({event.session_id for event in events if event.session_id})
    unique_paths = len({event.path for event in events})
    visits_last_24h = sum(1 for event in events if event.created_at >= last_24h_cutoff)
    visits_last_7d = sum(1 for event in events if event.created_at >= last_7d_cutoff)

    path_counter: Counter[str] = Counter()
    path_humans: Counter[str] = Counter()
    path_bots: Counter[str] = Counter()
    device_counter: Counter[str] = Counter()
    device_humans: Counter[str] = Counter()
    device_bots: Counter[str] = Counter()
    country_counter: Counter[str] = Counter()
    country_humans: Counter[str] = Counter()
    country_bots: Counter[str] = Counter()
    for event in events:
        path_counter[event.path] += 1
        device_label = event.device_type or "unknown"
        country_label = event.country_code or "unknown"
        device_counter[device_label] += 1
        country_counter[country_label] += 1
        if event.is_bot:
            path_bots[event.path] += 1
            device_bots[device_label] += 1
            country_bots[country_label] += 1
        else:
            path_humans[event.path] += 1
            device_humans[device_label] += 1
            country_humans[country_label] += 1

    top_paths = [
        VisitAnalyticsTopPathResponse(
            path=path,
            visits=visits,
            human_visits=path_humans[path],
            bot_visits=path_bots[path],
        )
        for path, visits in path_counter.most_common(10)
    ]

    top_devices = [
        VisitAnalyticsBreakdownResponse(
            label=device,
            visits=visits,
            human_visits=device_humans[device],
            bot_visits=device_bots[device],
        )
        for device, visits in device_counter.most_common(10)
    ]
    top_countries = [
        VisitAnalyticsBreakdownResponse(
            label=country,
            visits=visits,
            human_visits=country_humans[country],
            bot_visits=country_bots[country],
        )
        for country, visits in country_counter.most_common(10)
    ]

    recent_visits = [_to_response(event) for event in events[-10:]][::-1]

    daily_buckets: dict[object, dict[str, int]] = defaultdict(lambda: {"visits": 0, "human_visits": 0, "bot_visits": 0})
    for event in events:
        if event.created_at < window_cutoff:
            continue
        day = event.created_at.date()
        bucket = daily_buckets[day]
        bucket["visits"] += 1
        if event.is_bot:
            bucket["bot_visits"] += 1
        else:
            bucket["human_visits"] += 1

    daily_visits = [
        VisitAnalyticsDailyPointResponse(
            day=day,
            visits=data["visits"],
            human_visits=data["human_visits"],
            bot_visits=data["bot_visits"],
        )
        for day, data in sorted(daily_buckets.items(), key=lambda item: item[0])
    ]

    return VisitAnalyticsSummaryResponse(
        total_visits=total_visits,
        human_visits=human_visits,
        bot_visits=bot_visits,
        unique_sessions=unique_sessions,
        unique_paths=unique_paths,
        visits_last_24h=visits_last_24h,
        visits_last_7d=visits_last_7d,
        top_paths=top_paths,
        top_devices=top_devices,
        top_countries=top_countries,
        recent_visits=recent_visits,
        daily_visits=daily_visits,
    )


def clear_visits(session: Session) -> int:
    tenant_id = current_tenant_id()
    existing = session.exec(
        select(VisitEvent).where(VisitEvent.tenant_id == tenant_id)
    ).all()
    deleted_count = len(existing)
    if deleted_count:
        session.exec(delete(VisitEvent).where(VisitEvent.tenant_id == tenant_id))
        session.commit()
    return deleted_count
