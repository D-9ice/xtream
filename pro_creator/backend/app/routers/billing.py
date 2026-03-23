from datetime import datetime, timedelta, timezone
import base64
import binascii
import hashlib
import hmac
import struct

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.auth import get_current_user, require_owner, require_role
from app.config import (
    ADMIN_2FA_ENABLED,
    ADMIN_2FA_TOTP_SECRET,
    ADMIN_DASHBOARD_PASSWORD,
    ENVIRONMENT,
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
    AdminBillingSettingsUpdateRequest,
    AdminSubscriptionListResponse,
    AdminSubscriptionUpdateRequest,
    BillingPricingSettingsResponse,
    CharacterSlotPurchaseRequest,
    CreditPlan,
    CreditPlanListResponse,
    CreditBalanceResponse,
    CreditsConsumeRequest,
    CreditsPurchaseRequest,
    CreditsRefundRequest,
    CreditsReserveRequest,
    StripeCheckoutSessionResponse,
)
from app.services.app_settings import (
    get_character_slot_policy_payload,
    get_or_create_settings,
    get_plan_settings_payload,
    update_billing_settings,
)
from app.services.character_slots import build_character_slot_summary, purchase_character_slot_pack
from app.services.credits import (
    consume_credits as consume_credits_service,
    expire_credits,
    get_or_create_subscription,
    grant_credits,
    refund_credits,
    reserve_credits,
)
from app.tenant import current_tenant_id
from app.tenant import reset_current_tenant_id, set_current_tenant_id

router = APIRouter(prefix="/billing", tags=["Billing"])
ADMIN_ACCESS_TOKEN_TTL_SECONDS = 15 * 60
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6

try:
    import stripe
except Exception:
    stripe = None

def _is_stripe_ready() -> bool:
    return bool(stripe and STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)


def _default_stripe_price_id(plan_id: str) -> str | None:
    if plan_id == "moderate":
        return STRIPE_PRICE_ID_MODERATE or None
    if plan_id == "pro":
        return STRIPE_PRICE_ID_PRO or None
    if plan_id == "studio":
        return STRIPE_PRICE_ID_STUDIO or None
    return None


def _plan_catalog(session: Session) -> list[CreditPlan]:
    settings = get_or_create_settings(session)
    plans: list[CreditPlan] = []
    for item in get_plan_settings_payload(settings):
        plan_id = str(item["id"])
        stripe_price_id = item["stripe_price_id"] or _default_stripe_price_id(plan_id)
        plans.append(
            CreditPlan(
                id=plan_id,
                name=str(item["name"]),
                credits=int(item["credits"]),
                price_usd=int(item["price_usd"]),
                base_character_slots=int(item["base_character_slots"]),
                popular=plan_id == "pro",
                stripe_price_id=stripe_price_id,
                checkout_enabled=bool(stripe_price_id and _is_stripe_ready()),
            )
        )
    return plans


def _get_plan_by_id(session: Session, plan_id: str) -> CreditPlan:
    plan = next((item for item in _plan_catalog(session) if item.id == plan_id), None)
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


def _normalize_totp_secret(secret: str) -> bytes:
    cleaned = "".join(secret.strip().split()).upper()
    if not cleaned:
        raise ValueError("empty TOTP secret")
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    try:
        return base64.b32decode(cleaned + padding, casefold=True)
    except binascii.Error as exc:
        raise ValueError("invalid base32 TOTP secret") from exc


def _totp_code(secret: bytes, timestamp: int) -> str:
    counter = timestamp // TOTP_STEP_SECONDS
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )
    otp = binary % (10 ** TOTP_DIGITS)
    return str(otp).zfill(TOTP_DIGITS)


def _verify_totp(secret_text: str, otp_code: str, now: datetime | None = None) -> bool:
    try:
        secret = _normalize_totp_secret(secret_text)
    except ValueError:
        return False

    cleaned_code = "".join((otp_code or "").strip().split())
    if not cleaned_code.isdigit() or len(cleaned_code) != TOTP_DIGITS:
        return False
    current = int((now or datetime.now(timezone.utc)).timestamp())
    # Accept one step drift in each direction for clock skew.
    for delta in (-TOTP_STEP_SECONDS, 0, TOTP_STEP_SECONDS):
        if hmac.compare_digest(_totp_code(secret, current + delta), cleaned_code):
            return True
    return False


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


def _to_credit_response(session: Session, user: User, subscription) -> CreditBalanceResponse:
    return CreditBalanceResponse(
        email=user.email,
        plan_name=subscription.plan_name,
        status=subscription.status,
        credits_balance=subscription.credits_balance,
        credits_reserved=subscription.credits_reserved,
        credits_used_total=subscription.credits_used_total,
        renewal_date=subscription.renewal_date,
        extra_character_slots=subscription.extra_character_slots,
        character_slots=build_character_slot_summary(session=session, subscription=subscription),
    )


@router.get("/me", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def get_my_credits(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = get_or_create_subscription(session, current_user)
    return _to_credit_response(session, current_user, subscription)


@router.get("/plans", response_model=CreditPlanListResponse, dependencies=[Depends(get_current_user)])
def list_credit_plans(session: Session = Depends(get_session)) -> CreditPlanListResponse:
    return CreditPlanListResponse(plans=_plan_catalog(session))


@router.post(
    "/purchase/checkout",
    response_model=StripeCheckoutSessionResponse,
    dependencies=[Depends(get_current_user)],
)
def create_checkout_session(
    payload: CreditsPurchaseRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StripeCheckoutSessionResponse:
    if not _is_stripe_ready():
        raise HTTPException(status_code=503, detail="Stripe checkout is not configured")
    plan = _get_plan_by_id(session, payload.plan_id)
    if not plan.stripe_price_id:
        raise HTTPException(status_code=400, detail="Selected plan has no Stripe price configured")

    tenant_id = current_tenant_id()
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
                "tenant_id": tenant_id,
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
    if ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="Mock credit purchase is disabled in production")
    plan = _get_plan_by_id(session, payload.plan_id)
    subscription = grant_credits(
        session=session,
        user=current_user,
        amount=plan.credits,
        reason=f"mock purchase {plan.id}",
        action="billing.purchase.mock",
        reference_id=payload.plan_id,
    )
    return _to_credit_response(session, current_user, subscription)


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

    metadata = checkout_session.get("metadata") or {}
    tenant_id = str(metadata.get("tenant_id", "")).strip().lower() or current_tenant_id()
    tenant_token = set_current_tenant_id(tenant_id)
    already_applied = session.exec(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.tenant_id == tenant_id,
            CreditLedgerEntry.action == "billing.purchase.stripe",
            CreditLedgerEntry.reference_id == stripe_session_id,
        )
    ).first()
    if already_applied:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "idempotent": True}

    plan_id = str(metadata.get("plan_id", "")).strip().lower()
    user_email = str(metadata.get("user_email", "")).strip().lower()
    if not user_email:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "ignored": "missing metadata"}
    try:
        plan = _get_plan_by_id(session, plan_id)
    except HTTPException:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "ignored": "unknown plan"}

    user = session.exec(select(User).where(User.email == user_email)).first()
    if not user:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "ignored": "user not found"}

    try:
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
                "tenant_id": tenant_id,
            },
        )
    finally:
        reset_current_tenant_id(tenant_token)
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
    return _to_credit_response(session, current_user, subscription)


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
    return _to_credit_response(session, current_user, subscription)


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
    return _to_credit_response(session, current_user, subscription)


@router.post(
    "/character-slots/purchase",
    response_model=CreditBalanceResponse,
    dependencies=[Depends(get_current_user)],
)
def purchase_character_slots(
    payload: CharacterSlotPurchaseRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = purchase_character_slot_pack(
        session=session,
        user=current_user,
        pack_count=payload.pack_count,
    )
    return _to_credit_response(session, current_user, subscription)


@router.get(
    "/admin/2fa/status",
    response_model=Admin2FAStatusResponse,
    dependencies=[Depends(require_owner)],
)
def get_admin_2fa_status() -> Admin2FAStatusResponse:
    if ADMIN_2FA_ENABLED:
        if not ADMIN_2FA_TOTP_SECRET:
            return Admin2FAStatusResponse(
                enabled=True,
                method="totp",
                detail="2FA is enabled but ADMIN_2FA_TOTP_SECRET is missing.",
            )
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
    if not hmac.compare_digest(payload.password, ADMIN_DASHBOARD_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid admin dashboard password")
    if ADMIN_2FA_ENABLED:
        if not ADMIN_2FA_TOTP_SECRET:
            raise HTTPException(status_code=500, detail="Admin 2FA secret is not configured")
        if not payload.otp_code:
            raise HTTPException(status_code=400, detail="OTP code is required")
        if not _verify_totp(ADMIN_2FA_TOTP_SECRET, payload.otp_code):
            raise HTTPException(status_code=401, detail="Invalid OTP code")
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
        items.append(_to_credit_response(session, user, subscription))
    return AdminSubscriptionListResponse(items=items)


@router.get(
    "/admin/pricing",
    response_model=BillingPricingSettingsResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def get_admin_billing_settings(session: Session = Depends(get_session)) -> BillingPricingSettingsResponse:
    settings = get_or_create_settings(session)
    policy = get_character_slot_policy_payload(settings)
    return BillingPricingSettingsResponse(
        plans=_plan_catalog(session),
        free_base_character_slots=int(policy["free_base_slots"]),
        character_slot_addon_size=int(policy["addon_pack_size"]),
        character_slot_addon_cost_credits=int(policy["addon_pack_cost_credits"]),
    )


@router.patch(
    "/admin/pricing",
    response_model=BillingPricingSettingsResponse,
    dependencies=[Depends(require_owner_dashboard_access)],
)
def update_admin_billing_settings(
    payload: AdminBillingSettingsUpdateRequest,
    session: Session = Depends(get_session),
) -> BillingPricingSettingsResponse:
    try:
        settings = update_billing_settings(
            session,
            moderate_credits=payload.moderate_credits,
            moderate_price_usd=payload.moderate_price_usd,
            moderate_base_character_slots=payload.moderate_base_character_slots,
            moderate_stripe_price_id=payload.moderate_stripe_price_id,
            pro_credits=payload.pro_credits,
            pro_price_usd=payload.pro_price_usd,
            pro_base_character_slots=payload.pro_base_character_slots,
            pro_stripe_price_id=payload.pro_stripe_price_id,
            studio_credits=payload.studio_credits,
            studio_price_usd=payload.studio_price_usd,
            studio_base_character_slots=payload.studio_base_character_slots,
            studio_stripe_price_id=payload.studio_stripe_price_id,
            free_base_character_slots=payload.free_base_character_slots,
            character_slot_addon_size=payload.character_slot_addon_size,
            character_slot_addon_cost_credits=payload.character_slot_addon_cost_credits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    policy = get_character_slot_policy_payload(settings)
    return BillingPricingSettingsResponse(
        plans=_plan_catalog(session),
        free_base_character_slots=int(policy["free_base_slots"]),
        character_slot_addon_size=int(policy["addon_pack_size"]),
        character_slot_addon_cost_credits=int(policy["addon_pack_cost_credits"]),
    )


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
    return _to_credit_response(session, user, subscription)
