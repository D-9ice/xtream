from passlib.context import CryptContext
from sqlmodel import Session, select

from app.config import ADMIN_BOOTSTRAP_SYNC, ADMIN_EMAIL, ADMIN_PASSWORD
from app.database import engine
from app.models import User
from app.services.app_settings import get_or_create_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed_admin_user() -> None:
    """
    Bootstrap the owner/admin account from environment configuration.

    Normal startup is non-destructive: an existing owner password is left untouched.
    Set ADMIN_BOOTSTRAP_SYNC=true for one controlled restart when establishing or
    recovering owner credentials. That one-time sync:
      - creates the owner if missing,
      - resets the configured owner password if the account already exists,
      - restores role=admin and is_active=true,
      - enables persisted owner mode.

    After successful owner login, set ADMIN_BOOTSTRAP_SYNC=false and restart again.
    """
    normalized_email = ADMIN_EMAIL.strip().lower()

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == normalized_email)).first()

        if existing is None:
            user = User(
                email=normalized_email,
                hashed_password=pwd_context.hash(ADMIN_PASSWORD[:72]),
                role="admin",
                is_active=True,
            )
            session.add(user)
        elif ADMIN_BOOTSTRAP_SYNC:
            existing.hashed_password = pwd_context.hash(ADMIN_PASSWORD[:72])
            existing.role = "admin"
            existing.is_active = True
            session.add(existing)

        if ADMIN_BOOTSTRAP_SYNC:
            settings = get_or_create_settings(session)
            settings.owner_mode_enabled = True
            session.add(settings)

        session.commit()
