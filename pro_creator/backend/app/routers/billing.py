from datetime import datetime, timedelta, timezone
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.auth import get_current_user, require_owner, require_role
from app.config import (
    ADMIN_2FA_ENABLED,
    ADMIN_DASHBOARD_PASSWORD,
    JWT_ALGORITHM,
    JWT_SECRET,
    STRIPE_CANCEL_URL,
    STRIPE_PRICE_ID_MODERATE,
    STRIPE_PRICE_ID_PRO,
    STRIPE_PRICE_ID_STUDIO,
    STRIPE_SECRET_KEY,
    STRIPE_SUCCESS_URL,
    STRIPE_WEBHOOK_SECRET,
)
from app.database import get_session
from app.models import CreditLedgerEntry, User, utc_now
from app.schemas import (
    Admin2FAStatusResponse,
    AdminAccessVerifyRequest,
    AdminAccessVerifyResponse,
    AdminSubscriptionListResponse,
    AdminSubscriptionUpdateRequest,
    CreditPlan,
    CreditPlanListResponse,
    CreditBalanceResponse,
    CreditsConsumeRequest,
    CreditsPurchaseRequest,
    CreditsRefundRequest,
    CreditsReserveRequest,
    StripeCheckoutSessionResponse,
)
from app.services.credits import (
    consume_credits as consume_credits_service,
    expire_credits,
    get_or_create_subscription,
    grant_credits,
    refund_credits,
    reserve_credits,
)
from app.tenant import current_tenant_id

router = APIRouter(prefix="/billing", tags=["Billing"])
ADMIN_ACCESS_TOKEN_TTL_SECONDS = 15 * 60

try:
    import stripe
except Exception:
    stripe = None

PLAN_CATALOG: list[CreditPlan] = [
    CreditPlan(
        id="moderate",
        name="Moderate",
        credits=500,
        price_usd=15,
        stripe_price_id=STRIPE_PRICE_ID_MODERATE or None,
        checkout_enabled=bool(STRIPE_PRICE_ID_MODERATE),
    ),
    CreditPlan(
        id="pro",
        name="Pro",
        credits=2000,
        price_usd=49,
        popular=True,
        stripe_price_id=STRIPE_PRICE_ID_PRO or None,
        checkout_enabled=bool(STRIPE_PRICE_ID_PRO),
    ),
    CreditPlan(
        id="studio",
        name="Studio",
        credits=6000,
        price_usd=119,
        stripe_price_id=STRIPE_PRICE_ID_STUDIO or None,
        checkout_enabled=bool(STRIPE_PRICE_ID_STUDIO),
    ),
]


def _is_stripe_ready() -> bool:
    return bool(stripe and STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)


def _get_plan_by_id(plan_id: str) -> CreditPlan:
    plan = next((item for item in PLAN_CATALOG if item.id == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


def _create_admin_access_token(email: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ADMIN_ACCESS_TOKEN_TTL_SECONDS)
    payload = {
        "sub": email,
        "scope": "admin_dashboard",
        "exp": expires_at,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


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


def require_owner_dashboard_access(
    current_user: User = Depends(require_owner),
    token_subject: str = Depends(require_admin_dashboard_access),
) -> User:
    # Prevent token sharing between admins: token must be issued for the same user.
    if token_subject.strip().lower() != current_user.email.strip().lower():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin access token does not match user")
    return current_user


def _to_credit_response(user: User, subscription) -> CreditBalanceResponse:
    return CreditBalanceResponse(
        email=user.email,
        plan_name=subscription.plan_name,
        status=subscription.status,
        credits_balance=subscription.credits_balance,
        credits_reserved=subscription.credits_reserved,
        credits_used_total=subscription.credits_used_total,
        renewal_date=subscription.renewal_date,
    )


@router.get("/me", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def get_my_credits(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = get_or_create_subscription(session, current_user)
    return _to_credit_response(current_user, subscription)


@router.get("/plans", response_model=CreditPlanListResponse, dependencies=[Depends(get_current_user)])
def list_credit_plans() -> CreditPlanListResponse:
    plans = [
        plan.model_copy(update={"checkout_enabled": bool(plan.stripe_price_id and _is_stripe_ready())})
        for plan in PLAN_CATALOG
    ]
    return CreditPlanListResponse(plans=plans)


@router.post(
    "/purchase/checkout",
    response_model=StripeCheckoutSessionResponse,
    dependencies=[Depends(get_current_user)],
)
def create_checkout_session(
    payload: CreditsPurchaseRequest,
    current_user: User = Depends(get_current_user),
) -> StripeCheckoutSessionResponse:
    if not _is_stripe_ready():
        raise HTTPException(status_code=503, detail="Stripe checkout is not configured")
    plan = _get_plan_by_id(payload.plan_id)
    if not plan.stripe_price_id:
        raise HTTPException(status_code=400, detail="Selected plan has no Stripe price configured")

    stripe.api_key = STRIPE_SECRET_KEY
    try:
        checkout_session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
            customer_email=current_user.email,
            metadata={
                "plan_id": plan.id,
                "credits": str(plan.credits),
                "user_id": str(current_user.id),
                "user_email": current_user.email,
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe session creation failed: {exc}") from exc

    return StripeCheckoutSessionResponse(
        session_id=checkout_session.id,
        checkout_url=checkout_session.url,
    )


@router.post("/purchase/mock", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def purchase_credits_mock(
    payload: CreditsPurchaseRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    plan = _get_plan_by_id(payload.plan_id)
    subscription = grant_credits(
        session=session,
        user=current_user,
        amount=plan.credits,
        reason=f"mock purchase {plan.id}",
        action="billing.purchase.mock",
        reference_id=payload.plan_id,
    )
    return _to_credit_response(current_user, subscription)


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(get_session),
):
    if not _is_stripe_ready():
        raise HTTPException(status_code=503, detail="Stripe webhook is not configured")

    stripe.api_key = STRIPE_SECRET_KEY
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe webhook: {exc}") from exc

    if event.get("type") not in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        return {"received": True}

    checkout_session = event.get("data", {}).get("object", {})
    stripe_session_id = checkout_session.get("id")
    payment_status = checkout_session.get("payment_status")
    if not stripe_session_id or payment_status != "paid":
        return {"received": True}

    already_applied = session.exec(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.tenant_id == current_tenant_id(),
            CreditLedgerEntry.action == "billing.purchase.stripe",
            CreditLedgerEntry.reference_id == stripe_session_id,
        )
    ).first()
    if already_applied:
        return {"received": True, "idempotent": True}

    metadata = checkout_session.get("metadata") or {}
    plan_id = str(metadata.get("plan_id", "")).strip().lower()
    user_email = str(metadata.get("user_email", "")).strip().lower()
    plan = next((item for item in PLAN_CATALOG if item.id == plan_id), None)
    if not plan or not user_email:
        return {"received": True, "ignored": "missing metadata"}

    user = session.exec(select(User).where(User.email == user_email)).first()
    if not user:
        return {"received": True, "ignored": "user not found"}

    grant_credits(
        session=session,
        user=user,
        amount=plan.credits,
        reason=f"stripe purchase {plan.id}",
        action="billing.purchase.stripe",
        reference_id=stripe_session_id,
        metadata={
            "stripe_session_id": stripe_session_id,
            "stripe_customer": checkout_session.get("customer"),
            "stripe_payment_intent": checkout_session.get("payment_intent"),
            "plan_id": plan.id,
        },
    )
    return {"received": True, "granted": True}


@router.post("/consume", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def consume_credits(
    payload: CreditsConsumeRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = consume_credits_service(
        session=session,
        user=current_user,
        amount=payload.amount,
        from_reserved=payload.from_reserved,
        reason=payload.reason,
        action="manual_consume",
    )
    return _to_credit_response(current_user, subscription)


@router.post("/reserve", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def reserve_my_credits(
    payload: CreditsReserveRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = reserve_credits(
        session=session,
        user=current_user,
        amount=payload.amount,
        reason=payload.reason,
        action="manual_reserve",
    )
    return _to_credit_response(current_user, subscription)


@router.post("/refund", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def refund_my_credits(
    payload: CreditsRefundRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = refund_credits(
        session=session,
        user=current_user,
        amount=payload.amount,
        to_reserved=payload.to_reserved,
        reason=payload.reason,
        action="manual_refund",
    )
    return _to_credit_response(current_user, subscription)


@router.get(
    "/admin/2fa/status",
    response_model=Admin2FAStatusResponse,
    dependencies=[Depends(require_owner)],
)
def get_admin_2fa_status() -> Admin2FAStatusResponse:
    if ADMIN_2FA_ENABLED:
        return Admin2FAStatusResponse(
            enabled=True,
            method="totp",
            detail="2FA is enabled for admin dashboard access.",
        )
    return Admin2FAStatusResponse(
        enabled=False,
        method="totp",
        detail="2FA is currently disabled. Password-only admin access is active.",
    )


@router.post(
    "/admin/access/verify",
    response_model=AdminAccessVerifyResponse,
    dependencies=[Depends(require_owner)],
)
def verify_admin_dashboard_access(
    payload: AdminAccessVerifyRequest,
    current_user: User = Depends(get_current_user),
) -> AdminAccessVerifyResponse:
    if ADMIN_2FA_ENABLED:
        if not payload.otp_code:
            raise HTTPException(status_code=400, detail="OTP code is required")
        raise HTTPException(status_code=501, detail="Admin 2FA verification is not implemented yet")
    if not hmac.compare_digest(payload.password, ADMIN_DASHBOARD_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid admin dashboard password")
    token = _create_admin_access_token(current_user.email)
    return AdminAccessVerifyResponse(access_token=token, expires_in_seconds=ADMIN_ACCESS_TOKEN_TTL_SECONDS)


@router.get(
    "/admin/users",
    response_model=AdminSubscriptionListResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def list_user_subscriptions(session: Session = Depends(get_session)) -> AdminSubscriptionListResponse:
    users = session.exec(select(User).order_by(User.created_at.desc())).all()
    items = []
    for user in users:
        subscription = get_or_create_subscription(session, user)
        items.append(_to_credit_response(user, subscription))
    return AdminSubscriptionListResponse(items=items)


@router.post(
    "/admin/users/{email}/update",
    response_model=CreditBalanceResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def update_user_subscription(
    email: str,
    payload: AdminSubscriptionUpdateRequest,
    session: Session = Depends(get_session),
) -> CreditBalanceResponse:
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    subscription = get_or_create_subscription(session, user)

    if payload.plan_name is not None:
        subscription.plan_name = payload.plan_name
    if payload.status is not None:
        subscription.status = payload.status
    if payload.credits_delta is not None:
        if payload.credits_delta >= 0:
            subscription = grant_credits(
                session=session,
                user=user,
                amount=payload.credits_delta,
                reason="admin delta grant",
                action="admin_update",
                reference_id=email,
            )
        else:
            subscription = expire_credits(
                session=session,
                user=user,
                amount=abs(payload.credits_delta),
                reason="admin delta expire",
                action="admin_update",
                reference_id=email,
            )
    if payload.credits_balance is not None:
        subscription.credits_balance = max(0, payload.credits_balance)
    if payload.renewal_date is not None:
        subscription.renewal_date = payload.renewal_date

    subscription.updated_at = utc_now()
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return _to_credit_response(user, subscription)
