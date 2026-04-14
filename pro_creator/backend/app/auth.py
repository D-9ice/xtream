from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    AUTH_REQUIRED,
    JWT_ALGORITHM,
    JWT_SECRET,
)
from app.database import get_session
from app.models import User
from app.services.app_settings import get_or_create_settings
from app.services.credits import has_owner_mode_access
from app.tenant import current_tenant_id

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])


def create_access_token(subject: str, role: str, tenant_id: str | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "role": role, "tenant_id": tenant_id or current_tenant_id(), "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(select(User).where(User.email == email)).first()


def authenticate_user(session: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(session, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def _auth_disabled() -> bool:
    # Kept for compatibility; prefer _auth_is_required(session) in request paths.
    return not AUTH_REQUIRED


def _auth_is_required(session: Session) -> bool:
    if AUTH_REQUIRED:
        return True
    settings = get_or_create_settings(session)
    return bool(settings.auth_required)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    if not _auth_is_required(session):
        user = session.exec(select(User).limit(1)).first()
        if not user:
            user = User(
                email=ADMIN_EMAIL,
                hashed_password=get_password_hash(ADMIN_PASSWORD),
                role="admin",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("sub")
        token_tenant = str(payload.get("tenant_id") or "").strip().lower()
        if email is None:
            raise credentials_exception
        if token_tenant and token_tenant != current_tenant_id():
            raise HTTPException(status_code=403, detail="Token tenant does not match request tenant")
    except JWTError as exc:
        raise credentials_exception from exc

    user = get_user_by_email(session, email)
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


def require_role(required_role: str):
    def _role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return _role_dependency


def require_owner(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> User:
    """
    Owner access is stricter than role=admin.
    Owner mode must be enabled in settings, and the current user's email must be listed
    if an allowlist is configured.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Owner access required")

    if not has_owner_mode_access(session, current_user):
        raise HTTPException(status_code=403, detail="Owner access required")
    return current_user


def require_admin_dashboard_access(
    admin_access_token: str | None = Header(None, alias="X-Admin-Access-Token"),
) -> str:
    if not admin_access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin access token")
    try:
        payload = jwt.decode(admin_access_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin access token") from exc
    if payload.get("scope") != "admin_dashboard":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin access scope")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin access token")
    return subject
