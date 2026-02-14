from __future__ import annotations

from sqlmodel import Session, select

from app.models import AppSettings, utc_now


def get_or_create_settings(session: Session) -> AppSettings:
    settings = session.exec(select(AppSettings).where(AppSettings.id == 1)).first()
    if settings:
        return settings
    settings = AppSettings(id=1, auth_required=False)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def set_auth_required(session: Session, enabled: bool) -> AppSettings:
    settings = get_or_create_settings(session)
    settings.auth_required = bool(enabled)
    settings.updated_at = utc_now()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings

