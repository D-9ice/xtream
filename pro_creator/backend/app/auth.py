from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    AUTH_REQUIRED,
    ENVIRONMENT,
    JWT_ALGORITHM,
    JWT_SECRET,
    OWNER_EMAIL_ALLOWLIST,
)
from app.database import get_session
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password[:72])


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.exec(select(User).where(User.email == email)).first()


def authenticate_user(session: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(session, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def _auth_disabled() -> bool:
    return not AUTH_REQUIRED


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    if _auth_disabled():
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
        if email is None:
            raise credentials_exception
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


def require_owner(current_user: User = Depends(get_current_user)) -> User:
    """
    Owner access is stricter than role=admin.
    In production, OWNER_EMAIL_ALLOWLIST must be set and the current user's email must be listed.
    In non-production, an empty allowlist means "allow admins" for easier local dev.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Owner access required")

    allowlist = set(OWNER_EMAIL_ALLOWLIST or [])
    if not allowlist:
        if ENVIRONMENT != "production":
            return current_user
        raise HTTPException(
            status_code=500,
            detail="OWNER_EMAIL_ALLOWLIST must be set in production to use owner features",
        )

    if current_user.email.strip().lower() not in allowlist:
        raise HTTPException(status_code=403, detail="Owner access required")
    return current_user
