from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
    require_role,
)
from app.config import AUTH_REQUIRED, ENVIRONMENT
from app.database import get_session
from app.models import User
from app.services.app_settings import get_or_create_settings, set_auth_required
from app.schemas import (
    AuthGateStatusResponse,
    AuthGateUpdateRequest,
    PasswordChangeRequest,
    PasswordChangeResponse,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.get("/gate/status", response_model=AuthGateStatusResponse)
def get_auth_gate_status(session: Session = Depends(get_session)) -> AuthGateStatusResponse:
    if AUTH_REQUIRED:
        return AuthGateStatusResponse(enabled=True, source="env")
    settings = get_or_create_settings(session)
    return AuthGateStatusResponse(enabled=bool(settings.auth_required), source="db")


@router.patch("/gate", response_model=AuthGateStatusResponse)
def update_auth_gate(
    payload: AuthGateUpdateRequest,
    session: Session = Depends(get_session),
    _: object = Depends(require_role("admin")),
) -> AuthGateStatusResponse:
    # Only allow runtime gate toggles outside production. In production,
    # this should be an infrastructure decision (AUTH_REQUIRED=true).
    if ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Auth gate cannot be changed in production")
    settings = set_auth_required(session, payload.enabled)
    return AuthGateStatusResponse(enabled=bool(settings.auth_required), source="db")


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> TokenResponse:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.email, user.role)
    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/users", response_model=UserResponse)
def create_user(
    payload: UserCreateRequest,
    session: Session = Depends(get_session),
    _: object = Depends(require_role("admin")),
) -> UserResponse:
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserResponse(email=user.email, role=user.role, is_active=user.is_active)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@router.post("/change-password", response_model=PasswordChangeResponse)
def change_password(
    payload: PasswordChangeRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PasswordChangeResponse:
    gate_required = AUTH_REQUIRED or bool(get_or_create_settings(session).auth_required)
    # In local/open mode (gate off) we allow setting a password without knowing the old one,
    # so a fresh install can bootstrap credentials. In production, always require current password.
    if ENVIRONMENT == "production" or gate_required:
        if not verify_password(payload.current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = get_password_hash(payload.new_password)
    session.add(current_user)
    session.commit()
    return PasswordChangeResponse(status="updated")
