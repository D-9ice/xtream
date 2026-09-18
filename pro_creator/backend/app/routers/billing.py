from datetime import datetime, timedelta, timezone
import base64
import binascii
import hashlib
import hmac
import json
import struct

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from jose import JWTError, jwt
from sqlalchemy import delete, func
from sqlmodel import Session, select
import requests

from app.auth import get_current_user, require_owner, require_role
from app.config import (
    ADMIN_2FA_ENABLED,
    ADMIN_2FA_TOTP_SECRET,
    ADMIN_DASHBOARD_PASSWORD,
    ENVIRONMENT,
    FACTORY_MODE_ONE_TIME_PRICE_USD,
    FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID,
    FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS,
    FACTORY_MODE_SUBSCRIPTION_PRICE_USD,
    FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID,
    JWT_ALGORITHM,
    JWT_SECRET,
    PAYSTACK_CALLBACK_URL,
    PAYSTACK_CURRENCY,
    PAYSTACK_SECRET_KEY,
    STRIPE_CANCEL_URL,
    STRIPE_PRICE_ID_MODERATE,
    STRIPE_PRICE_ID_PRO,
    STRIPE_PRICE_ID_STUDIO,
    STRIPE_SECRET_KEY,
    STRIPE_SUCCESS_URL,
    STRIPE_WEBHOOK_SECRET,
)
from app.database import get_session
from app.models import CreditLedgerEntry, HiddenReceipt, SocialAccountConnection, SocialPublishJob, SubscriptionAccount, User, utc_now
from app.schemas import (
    Admin2FAStatusResponse,
    AdminAccessVerifyRequest,
    AdminAccessVerifyResponse,
    AdminBillingSettingsUpdateRequest,
    AdminSubscriptionListResponse,
    AdminSubscriptionUpdateRequest,
    AdminUserBulkDeleteResponse,
    AdminUserDeleteResponse,
    BillingCheckoutSessionResponse,
    BillingPricingSettingsResponse,
    BillingReceiptItem,
    BillingReceiptDeleteResponse,
    BillingReceiptListResponse,
    BillingTransactionRecordItem,
    BillingTransactionRecordClearResponse,
    BillingTransactionRecordListResponse,
    CharacterSlotPurchaseRequest,
    CreditPlan,
    CreditPlanListResponse,
    CreditBalanceResponse,
    CreditsConsumeRequest,
    CreditsPurchaseRequest,
    CreditsRefundRequest,
    CreditsReserveRequest,
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
    grant_factory_mode_access,
    get_or_create_subscription,
    has_factory_mode_access,
    grant_credits,
    refund_credits,
    reserve_credits,
    revoke_factory_mode_access,
)
from app.services.receipt_email import send_purchase_receipt_email
from app.tenant import current_tenant_id
from app.tenant import reset_current_tenant_id, set_current_tenant_id
from app.utils.logger import get_logger

router = APIRouter(prefix="/billing", tags=["Billing"])
ADMIN_ACCESS_TOKEN_TTL_SECONDS = 24 * 60 * 60
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
logger = get_logger(__name__)

try:
    import stripe
except Exception:
    stripe = None

def _is_stripe_ready() -> bool:
    return bool(stripe and STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET)


def _is_paystack_ready() -> bool:
    return bool(PAYSTACK_SECRET_KEY.strip())


def _is_stripe_configured() -> bool:
    return bool(STRIPE_SECRET_KEY.strip() and STRIPE_WEBHOOK_SECRET.strip())


def _default_stripe_price_id(plan_id: str) -> str | None:
    if plan_id == "moderate":
        return STRIPE_PRICE_ID_MODERATE or None
    if plan_id == "pro":
        return STRIPE_PRICE_ID_PRO or None
    if plan_id == "studio":
        return STRIPE_PRICE_ID_STUDIO or None
    if plan_id == "factory_one_time":
        return FACTORY_MODE_ONE_TIME_STRIPE_PRICE_ID or None
    if plan_id == "factory_subscription":
        return FACTORY_MODE_SUBSCRIPTION_STRIPE_PRICE_ID or None
    return None


def _plan_catalog(session: Session) -> list[CreditPlan]:
    settings = get_or_create_settings(session)
    plans: list[CreditPlan] = []
    for item in get_plan_settings_payload(settings):
        plan_id = str(item["id"])
        stripe_price_id = item["stripe_price_id"] or _default_stripe_price_id(plan_id)
        checkout_providers: list[str] = []
        if stripe_price_id and _is_stripe_configured():
            checkout_providers.append("stripe")
        if _is_paystack_ready():
            checkout_providers.append("paystack")
        plans.append(
            CreditPlan(
                id=plan_id,
                name=str(item["name"]),
                kind=str(item.get("kind") or "credits"),
                credits=int(item["credits"]),
                price_usd=int(item["price_usd"]),
                base_character_slots=int(item["base_character_slots"]),
                popular=plan_id == "pro",
                stripe_price_id=stripe_price_id,
                checkout_providers=checkout_providers,
                checkout_enabled=bool(checkout_providers),
                access_mode=str(item.get("access_mode") or "").strip() or None,
                access_days=int(item["access_days"]) if item.get("access_days") is not None else None,
                description=str(item.get("description") or "").strip() or None,
            )
        )
    return plans


def _get_plan_by_id(session: Session, plan_id: str) -> CreditPlan:
    plan = next((item for item in _plan_catalog(session) if item.id == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


def _ledger_entry_to_receipt(entry: CreditLedgerEntry) -> BillingReceiptItem:
    metadata = _ledger_entry_metadata(entry)
    plan_id = str(metadata.get("plan_id", "")).strip().lower() or None
    plan_kind = str(metadata.get("plan_kind", "")).strip().lower() or None
    access_mode = str(metadata.get("access_mode", "")).strip().lower() or None
    purchase_label = str(metadata.get("purchase_label", "")).strip() or None
    provider = (
        entry.provider
        or str(metadata.get("provider", "")).strip().lower()
        or ("paystack" if (entry.action or "").endswith("paystack") else "stripe" if (entry.action or "").endswith("stripe") else None)
    )
    return BillingReceiptItem(
        receipt_id=int(entry.id or 0),
        created_at=entry.created_at,
        kind=entry.kind,
        action=entry.action,
        amount=entry.amount,
        reason=entry.reason,
        reference_id=entry.reference_id,
        provider=provider,
        balance_after=entry.balance_after,
        reserved_after=entry.reserved_after,
        plan_id=plan_id,
        plan_kind=plan_kind,
        access_mode=access_mode,
        purchase_label=purchase_label,
        metadata=metadata,
    )


def _ledger_entry_to_transaction_record(entry: CreditLedgerEntry) -> BillingTransactionRecordItem:
    metadata = _ledger_entry_metadata(entry)
    provider = (
        entry.provider
        or str(metadata.get("provider", "")).strip().lower()
        or ("paystack" if (entry.action or "").endswith("paystack") else "stripe" if (entry.action or "").endswith("stripe") else None)
    )
    return BillingTransactionRecordItem(
        record_id=int(entry.id or 0),
        created_at=entry.created_at,
        kind=entry.kind,
        action=entry.action,
        amount=entry.amount,
        reason=entry.reason,
        reference_id=entry.reference_id,
        provider=provider,
        balance_after=entry.balance_after,
        reserved_after=entry.reserved_after,
        metadata=metadata,
    )


def _ledger_entry_metadata(entry: CreditLedgerEntry) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if entry.metadata_json:
        try:
            parsed = json.loads(entry.metadata_json)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            metadata = parsed
    return metadata


def _normalize_checkout_provider(provider: str | None) -> str:
    clean = (provider or "stripe").strip().lower()
    if clean not in {"stripe", "paystack"}:
        raise HTTPException(status_code=400, detail=f"Unsupported checkout provider: {provider}")
    return clean


def _plan_kind(plan: CreditPlan) -> str:
    return (getattr(plan, "kind", "credits") or "credits").strip().lower()


def _is_factory_access_plan(plan: CreditPlan) -> bool:
    return _plan_kind(plan) == "factory_access"


def _factory_access_mode(plan: CreditPlan) -> str:
    return (getattr(plan, "access_mode", None) or "one_time").strip().lower()


def _factory_access_period_days(plan: CreditPlan) -> int:
    if _factory_access_mode(plan) == "subscription":
        return max(1, int(getattr(plan, "access_days", None) or FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS))
    return 0


def _factory_access_item_description(plan: CreditPlan) -> str:
    access_mode = _factory_access_mode(plan)
    if access_mode == "subscription":
        duration_days = _factory_access_period_days(plan)
        return f"Factory Mode subscription access for {duration_days} days"
    return "Factory Mode one-time access"


def _grant_factory_purchase(
    *,
    session: Session,
    user: User,
    plan: CreditPlan,
    provider: str,
    reference_id: str,
    metadata: dict[str, object],
) -> None:
    access_mode = _factory_access_mode(plan)
    renewal_days = _factory_access_period_days(plan)
    grant_factory_mode_access(
        session=session,
        user=user,
        access_mode=access_mode,
        reason=f"factory mode {access_mode} purchase {plan.id}",
        action=f"billing.purchase.factory.{access_mode}",
        reference_id=reference_id,
        provider=provider,
        metadata={
            **metadata,
            "plan_id": plan.id,
            "plan_kind": "factory_access",
            "access_mode": access_mode,
            "purchase_label": plan.name,
        },
        renewal_days=renewal_days or None,
    )
    _send_purchase_receipt_email(
        user=user,
        plan=plan,
        provider=provider,
        amount=float(plan.price_usd),
        currency="USD" if provider == "stripe" else PAYSTACK_CURRENCY or "GHS",
        reference_id=reference_id,
        item_description=_factory_access_item_description(plan),
    )


def _paystack_amount_for_plan(plan: CreditPlan) -> int:
    return max(1, int(plan.price_usd) * 100)


def _send_purchase_receipt_email(
    *,
    user: User,
    plan: CreditPlan,
    provider: str,
    amount: float,
    currency: str,
    reference_id: str,
    item_description: str | None = None,
) -> None:
    try:
        send_purchase_receipt_email(
            recipient_email=user.email,
            plan_name=plan.name,
            credits=plan.credits,
            item_description=item_description,
            provider=provider,
            amount=amount,
            currency=currency,
            reference_id=reference_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to send receipt email for %s plan via %s (%s): %s",
            plan.id,
            provider,
            reference_id,
            exc,
        )


def _paystack_api_call(
    *,
    method: str,
    path: str,
    json_body: dict[str, object] | None = None,
    timeout: int = 60,
) -> dict[str, object]:
    response = requests.request(
        method,
        f"https://api.paystack.co{path}",
        headers={
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY.strip()}",
            "Content-Type": "application/json",
        },
        json=json_body,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Paystack API returned an invalid payload")
    if not payload.get("status", False):
        raise RuntimeError(str(payload.get("message") or "Paystack API request failed"))
    return payload


def _create_paystack_checkout_session(
    *,
    plan: CreditPlan,
    current_user: User,
    tenant_id: str,
) -> tuple[str, str]:
    plan_kind = _plan_kind(plan)
    amount = _paystack_amount_for_plan(plan)
    response = _paystack_api_call(
        method="POST",
        path="/transaction/initialize",
        json_body={
            "email": current_user.email,
            "amount": amount,
            "currency": PAYSTACK_CURRENCY,
            "callback_url": PAYSTACK_CALLBACK_URL,
            "metadata": {
                "plan_id": plan.id,
                "plan_kind": plan_kind,
                "credits": str(plan.credits),
                "user_id": str(current_user.id or 0),
                "user_email": current_user.email,
                "tenant_id": tenant_id,
                "provider": "paystack",
                "access_mode": _factory_access_mode(plan) if plan_kind == "factory_access" else None,
            },
        },
        timeout=60,
    )
    data = response.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError("Paystack initialization returned an invalid response")
    checkout_url = str(data.get("authorization_url") or "").strip()
    reference = str(data.get("reference") or data.get("access_code") or "").strip()
    if not checkout_url or not reference:
        raise RuntimeError("Paystack initialization did not return a checkout URL")
    return reference, checkout_url


def _verify_paystack_signature(payload: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = hmac.new(
        PAYSTACK_SECRET_KEY.strip().encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_paystack_transaction(reference: str) -> dict[str, object]:
    response = _paystack_api_call(
        method="GET",
        path=f"/transaction/verify/{reference}",
        timeout=60,
    )
    data = response.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError("Paystack verification returned an invalid payload")
    return data


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
        owner_mode_enabled=bool(get_or_create_settings(session).owner_mode_enabled),
        factory_mode_status="active" if has_factory_mode_access(subscription, session=session, user=user) else "inactive",
        factory_mode_access=subscription.factory_mode_access,
        factory_mode_renewal_date=subscription.factory_mode_renewal_date,
        factory_mode_purchased_at=subscription.factory_mode_purchased_at,
        character_slots=build_character_slot_summary(session=session, subscription=subscription),
    )


def _delete_user_account(session: Session, user: User) -> None:
    tenant_id = current_tenant_id()
    user_id = user.id or 0
    with session.no_autoflush:
        subscription = session.exec(
            select(SubscriptionAccount).where(
                SubscriptionAccount.user_id == user_id,
                SubscriptionAccount.tenant_id == tenant_id,
            )
        ).first()
        if subscription and subscription.id is not None:
            session.exec(
                delete(CreditLedgerEntry).where(
                    CreditLedgerEntry.subscription_id == subscription.id,
                    CreditLedgerEntry.tenant_id == tenant_id,
                )
            )
            session.exec(
                delete(SubscriptionAccount).where(
                    SubscriptionAccount.id == subscription.id,
                    SubscriptionAccount.tenant_id == tenant_id,
                )
            )

        session.exec(
            delete(HiddenReceipt).where(
                HiddenReceipt.user_id == user_id,
                HiddenReceipt.tenant_id == tenant_id,
            )
        )
        session.exec(
            delete(SocialAccountConnection).where(
                SocialAccountConnection.user_id == user_id,
                SocialAccountConnection.tenant_id == tenant_id,
            )
        )
        session.exec(
            delete(SocialPublishJob).where(
                SocialPublishJob.user_id == user_id,
                SocialPublishJob.tenant_id == tenant_id,
            )
        )
        session.exec(
            delete(User).where(
                User.id == user_id,
            )
        )


@router.get("/me", response_model=CreditBalanceResponse, dependencies=[Depends(get_current_user)])
def get_my_credits(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CreditBalanceResponse:
    subscription = get_or_create_subscription(session, current_user)
    return _to_credit_response(session, current_user, subscription)


@router.get("/receipts", response_model=BillingReceiptListResponse, dependencies=[Depends(get_current_user)])
def list_my_receipts(
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BillingReceiptListResponse:
    tenant_id = current_tenant_id()
    user_id = current_user.id or 0
    hidden_receipt_ids = set(
        session.exec(
            select(HiddenReceipt.ledger_entry_id).where(
                HiddenReceipt.tenant_id == tenant_id,
                HiddenReceipt.user_id == user_id,
            )
        ).all()
    )
    entries = session.exec(
        select(CreditLedgerEntry)
        .where(
            CreditLedgerEntry.tenant_id == tenant_id,
            CreditLedgerEntry.user_id == user_id,
            CreditLedgerEntry.action.like("billing.purchase.%"),
        )
        .order_by(CreditLedgerEntry.created_at.desc())
    ).all()
    visible_entries = [entry for entry in entries if entry.id not in hidden_receipt_ids]
    return BillingReceiptListResponse(items=[_ledger_entry_to_receipt(entry) for entry in visible_entries[:limit]])


@router.get("/records", response_model=BillingTransactionRecordListResponse, dependencies=[Depends(get_current_user)])
def list_my_transaction_records(
    limit: int = Query(50, ge=1, le=100),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BillingTransactionRecordListResponse:
    tenant_id = current_tenant_id()
    user_id = current_user.id or 0
    entries = session.exec(
        select(CreditLedgerEntry)
        .where(
            CreditLedgerEntry.tenant_id == tenant_id,
            CreditLedgerEntry.user_id == user_id,
        )
        .order_by(CreditLedgerEntry.created_at.desc())
    ).all()
    return BillingTransactionRecordListResponse(
        items=[_ledger_entry_to_transaction_record(entry) for entry in entries[:limit]]
    )


@router.delete(
    "/records",
    response_model=BillingTransactionRecordClearResponse,
    dependencies=[Depends(get_current_user)],
)
def clear_my_transaction_records(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BillingTransactionRecordClearResponse:
    settings = get_or_create_settings(session)
    if settings.billing_receipts_live_mode:
        raise HTTPException(status_code=400, detail="Transaction records can only be cleared in test mode")
    tenant_id = current_tenant_id()
    user_id = current_user.id or 0
    entries = session.exec(
        select(CreditLedgerEntry)
        .where(
            CreditLedgerEntry.tenant_id == tenant_id,
            CreditLedgerEntry.user_id == user_id,
        )
        .order_by(CreditLedgerEntry.created_at.desc())
    ).all()
    deleted_ids = [int(entry.id) for entry in entries if entry.id is not None]
    if deleted_ids:
        session.exec(
            delete(HiddenReceipt).where(
                HiddenReceipt.tenant_id == tenant_id,
                HiddenReceipt.user_id == user_id,
                HiddenReceipt.ledger_entry_id.in_(deleted_ids),
            )
        )
        for entry in entries:
            session.delete(entry)
        session.commit()
    return BillingTransactionRecordClearResponse(
        deleted=True,
        deleted_count=len(deleted_ids),
        deleted_ids=deleted_ids,
    )


@router.delete(
    "/receipts/{receipt_id}",
    response_model=BillingReceiptDeleteResponse,
    dependencies=[Depends(get_current_user)],
)
def delete_my_receipt(
    receipt_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BillingReceiptDeleteResponse:
    tenant_id = current_tenant_id()
    user_id = current_user.id or 0
    entry = session.get(CreditLedgerEntry, receipt_id)
    if not entry or entry.tenant_id != tenant_id or entry.user_id != user_id:
        raise HTTPException(status_code=404, detail="receipt not found")
    if not (entry.action or "").startswith("billing.purchase."):
        raise HTTPException(status_code=400, detail="Only billing purchase receipts can be deleted")
    settings = get_or_create_settings(session)
    deleted_permanently = not settings.billing_receipts_live_mode
    if settings.billing_receipts_live_mode:
        existing_visibility = session.exec(
            select(HiddenReceipt).where(
                HiddenReceipt.tenant_id == tenant_id,
                HiddenReceipt.user_id == user_id,
                HiddenReceipt.ledger_entry_id == receipt_id,
            )
        ).first()
        if existing_visibility is None:
            session.add(
                HiddenReceipt(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    ledger_entry_id=receipt_id,
                )
            )
    else:
        hidden_rows = session.exec(
            select(HiddenReceipt).where(
                HiddenReceipt.tenant_id == tenant_id,
                HiddenReceipt.user_id == user_id,
                HiddenReceipt.ledger_entry_id == receipt_id,
            )
        ).all()
        for hidden_row in hidden_rows:
            session.delete(hidden_row)
        session.delete(entry)
    session.commit()
    return BillingReceiptDeleteResponse(
        deleted=True,
        receipt_id=receipt_id,
        deleted_permanently=deleted_permanently,
    )


@router.get("/plans", response_model=CreditPlanListResponse)
def list_credit_plans(session: Session = Depends(get_session)) -> CreditPlanListResponse:
    return CreditPlanListResponse(plans=_plan_catalog(session))


@router.post(
    "/purchase/checkout",
    response_model=BillingCheckoutSessionResponse,
    dependencies=[Depends(get_current_user)],
)
def create_checkout_session(
    payload: CreditsPurchaseRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> BillingCheckoutSessionResponse:
    plan = _get_plan_by_id(session, payload.plan_id)
    provider = _normalize_checkout_provider(payload.provider)
    if provider not in plan.checkout_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Selected plan is not available with {provider} checkout",
        )

    tenant_id = current_tenant_id()
    plan_kind = _plan_kind(plan)
    purchase_metadata = {
        "plan_id": plan.id,
        "plan_kind": plan_kind,
        "credits": str(plan.credits),
        "user_id": str(current_user.id),
        "user_email": current_user.email,
        "tenant_id": tenant_id,
        "provider": provider,
        "access_mode": _factory_access_mode(plan) if plan_kind == "factory_access" else None,
    }
    if provider == "stripe":
        if not _is_stripe_ready():
            raise HTTPException(status_code=503, detail="Stripe checkout is not configured")
        if not plan.stripe_price_id:
            raise HTTPException(status_code=400, detail="Selected plan has no Stripe price configured")

        stripe.api_key = STRIPE_SECRET_KEY
        try:
            checkout_session = stripe.checkout.Session.create(
                mode="subscription" if plan_kind == "factory_access" and _factory_access_mode(plan) == "subscription" else "payment",
                line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
                success_url=STRIPE_SUCCESS_URL,
                cancel_url=STRIPE_CANCEL_URL,
                customer_email=current_user.email,
                metadata={k: v for k, v in purchase_metadata.items() if v is not None},
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Stripe session creation failed: {exc}") from exc

        return BillingCheckoutSessionResponse(
            provider="stripe",
            session_id=checkout_session.id,
            checkout_url=checkout_session.url,
        )

    if not _is_paystack_ready():
        raise HTTPException(status_code=503, detail="Paystack checkout is not configured")
    try:
        reference, checkout_url = _create_paystack_checkout_session(
            plan=plan,
            current_user=current_user,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Paystack session creation failed: {exc}") from exc

    return BillingCheckoutSessionResponse(
        provider="paystack",
        session_id=reference,
        checkout_url=checkout_url,
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
    if _is_factory_access_plan(plan):
        raise HTTPException(status_code=400, detail="Mock purchase is only available for credit plans")
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
        logger.warning("Stripe webhook rejected: missing signature")
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        logger.warning("Stripe webhook rejected: invalid signature or payload (%s)", exc)
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
            CreditLedgerEntry.reference_id == stripe_session_id,
            CreditLedgerEntry.action.like("billing.purchase.%"),
        )
    ).first()
    if already_applied:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "idempotent": True}

    plan_id = str(metadata.get("plan_id", "")).strip().lower()
    plan_kind = str(metadata.get("plan_kind", "")).strip().lower() or "credits"
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
        if plan_kind == "factory_access":
            _grant_factory_purchase(
                session=session,
                user=user,
                plan=plan,
                provider="stripe",
                reference_id=stripe_session_id,
                metadata={
                    "stripe_session_id": stripe_session_id,
                    "stripe_customer": checkout_session.get("customer"),
                    "stripe_payment_intent": checkout_session.get("payment_intent"),
                    "tenant_id": tenant_id,
                },
            )
            return {"received": True, "granted": True}
        grant_credits(
            session=session,
            user=user,
            amount=plan.credits,
            reason=f"stripe purchase {plan.id}",
            action="billing.purchase.stripe",
            reference_id=stripe_session_id,
            provider="stripe",
            metadata={
                "stripe_session_id": stripe_session_id,
                "stripe_customer": checkout_session.get("customer"),
                "stripe_payment_intent": checkout_session.get("payment_intent"),
                "plan_id": plan.id,
                "plan_kind": plan_kind,
                "tenant_id": tenant_id,
                "purchase_label": plan.name,
            },
        )
        _send_purchase_receipt_email(
            user=user,
            plan=plan,
            provider="stripe",
            amount=float(plan.price_usd),
            currency="USD",
            reference_id=stripe_session_id,
            item_description=f"{plan.credits} credits",
        )
    finally:
        reset_current_tenant_id(tenant_token)
    return {"received": True, "granted": True}


@router.post("/paystack/webhook")
async def paystack_webhook(
    request: Request,
    session: Session = Depends(get_session),
):
    if not _is_paystack_ready():
        raise HTTPException(status_code=503, detail="Paystack webhook is not configured")

    payload = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not _verify_paystack_signature(payload, signature):
        logger.warning("Paystack webhook rejected: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid Paystack signature")

    try:
        event = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        logger.warning("Paystack webhook rejected: invalid payload (%s)", exc)
        raise HTTPException(status_code=400, detail=f"Invalid Paystack webhook payload: {exc}") from exc

    if str(event.get("event") or "").strip().lower() != "charge.success":
        return {"received": True}

    data = event.get("data") or {}
    if not isinstance(data, dict):
        return {"received": True, "ignored": "invalid payload"}

    reference = str(data.get("reference") or "").strip()
    if not reference:
        return {"received": True, "ignored": "missing reference"}

    try:
        transaction = _verify_paystack_transaction(reference)
    except Exception as exc:
        logger.warning("Paystack verification failed for reference %s: %s", reference, exc)
        raise HTTPException(status_code=502, detail=f"Paystack verification failed: {exc}") from exc

    if str(transaction.get("status") or "").strip().lower() != "success":
        return {"received": True, "ignored": "transaction not successful"}

    metadata = transaction.get("metadata") or data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    plan_id = str(metadata.get("plan_id", "")).strip().lower()
    plan_kind = str(metadata.get("plan_kind", "")).strip().lower() or "credits"
    user_email = str(metadata.get("user_email", "")).strip().lower()
    if not plan_id or not user_email:
        return {"received": True, "ignored": "missing metadata"}

    tenant_id = str(metadata.get("tenant_id", "")).strip().lower() or current_tenant_id()
    tenant_token = set_current_tenant_id(tenant_id)
    try:
        plan = _get_plan_by_id(session, plan_id)
    except HTTPException:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "ignored": "unknown plan"}

    expected_amount = _paystack_amount_for_plan(plan)
    actual_amount = int(transaction.get("amount") or 0)
    if actual_amount != expected_amount:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "ignored": "amount mismatch"}

    already_applied = session.exec(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.tenant_id == tenant_id,
            CreditLedgerEntry.reference_id == reference,
            CreditLedgerEntry.action.like("billing.purchase.%"),
        )
    ).first()
    if already_applied:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "idempotent": True}

    user = session.exec(select(User).where(User.email == user_email)).first()
    if not user:
        reset_current_tenant_id(tenant_token)
        return {"received": True, "ignored": "user not found"}

    try:
        if plan_kind == "factory_access":
            _grant_factory_purchase(
                session=session,
                user=user,
                plan=plan,
                provider="paystack",
                reference_id=reference,
                metadata={
                    "paystack_reference": reference,
                    "paystack_transaction_id": transaction.get("id"),
                    "paystack_amount": actual_amount,
                    "paystack_currency": transaction.get("currency"),
                    "tenant_id": tenant_id,
                },
            )
            return {"received": True, "granted": True}
        grant_credits(
            session=session,
            user=user,
            amount=plan.credits,
            reason=f"paystack purchase {plan.id}",
            action="billing.purchase.paystack",
            reference_id=reference,
            provider="paystack",
            metadata={
                "paystack_reference": reference,
                "paystack_transaction_id": transaction.get("id"),
                "paystack_amount": actual_amount,
                "paystack_currency": transaction.get("currency"),
                "plan_id": plan.id,
                "plan_kind": plan_kind,
                "tenant_id": tenant_id,
                "purchase_label": plan.name,
            },
        )
        _send_purchase_receipt_email(
            user=user,
            plan=plan,
            provider="paystack",
            amount=actual_amount / 100.0,
            currency=str(transaction.get("currency") or PAYSTACK_CURRENCY or "GHS"),
            reference_id=reference,
            item_description=f"{plan.credits} credits",
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
    dependencies=[Depends(require_role("admin"))],
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
    dependencies=[Depends(require_role("admin"))],
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
    dependencies=[Depends(require_admin_dashboard_access)],
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
    dependencies=[Depends(require_admin_dashboard_access)],
)
def get_admin_billing_settings(session: Session = Depends(get_session)) -> BillingPricingSettingsResponse:
    settings = get_or_create_settings(session)
    policy = get_character_slot_policy_payload(settings)
    return BillingPricingSettingsResponse(
        plans=_plan_catalog(session),
        owner_mode_enabled=bool(settings.owner_mode_enabled),
        receipts_live_mode=bool(settings.billing_receipts_live_mode),
        free_base_character_slots=int(policy["free_base_slots"]),
        character_slot_addon_size=int(policy["addon_pack_size"]),
        character_slot_addon_cost_credits=int(policy["addon_pack_cost_credits"]),
    )


@router.patch(
    "/admin/pricing",
    response_model=BillingPricingSettingsResponse,
    dependencies=[Depends(require_admin_dashboard_access)],
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
            factory_one_time_price_usd=payload.factory_one_time_price_usd,
            factory_one_time_stripe_price_id=payload.factory_one_time_stripe_price_id,
            factory_subscription_price_usd=payload.factory_subscription_price_usd,
            factory_subscription_stripe_price_id=payload.factory_subscription_stripe_price_id,
            owner_mode_enabled=payload.owner_mode_enabled,
            receipts_live_mode=payload.receipts_live_mode,
            free_base_character_slots=payload.free_base_character_slots,
            character_slot_addon_size=payload.character_slot_addon_size,
            character_slot_addon_cost_credits=payload.character_slot_addon_cost_credits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    policy = get_character_slot_policy_payload(settings)
    return BillingPricingSettingsResponse(
        plans=_plan_catalog(session),
        owner_mode_enabled=bool(settings.owner_mode_enabled),
        receipts_live_mode=bool(settings.billing_receipts_live_mode),
        free_base_character_slots=int(policy["free_base_slots"]),
        character_slot_addon_size=int(policy["addon_pack_size"]),
        character_slot_addon_cost_credits=int(policy["addon_pack_cost_credits"]),
    )


@router.post(
    "/admin/users/{email}/update",
    response_model=CreditBalanceResponse,
    dependencies=[Depends(require_admin_dashboard_access)],
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
        normalized_status = payload.status.strip().lower()
        subscription.status = normalized_status
        user.is_active = normalized_status == "active"
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
    current_factory_access = (subscription.factory_mode_access or "none").strip().lower()
    if payload.factory_mode_access is not None or payload.factory_mode_renewal_date is not None:
        requested_access = (payload.factory_mode_access or subscription.factory_mode_access or "none").strip().lower()
        if requested_access not in {"none", "one_time", "subscription"}:
            raise HTTPException(status_code=400, detail="factory_mode_access must be none, one_time, or subscription")
        if requested_access == "none":
            if current_factory_access != "none" or subscription.factory_mode_status != "inactive":
                subscription = revoke_factory_mode_access(
                    session=session,
                    user=user,
                    reason="admin factory mode revoke",
                    action="admin_update_factory_mode",
                    reference_id=email,
                    provider="admin",
                    metadata={
                        "email": email,
                        "factory_mode_access": "none",
                    },
                )
        else:
            if current_factory_access != requested_access or subscription.factory_mode_status != "active":
                subscription = grant_factory_mode_access(
                    session=session,
                    user=user,
                    access_mode=requested_access,
                    reason="admin factory mode grant",
                    action="admin_update_factory_mode",
                    reference_id=email,
                    provider="admin",
                    metadata={
                        "email": email,
                        "factory_mode_access": requested_access,
                    },
                    renewal_days=FACTORY_MODE_SUBSCRIPTION_PERIOD_DAYS if requested_access == "subscription" else None,
                )
            if requested_access == "subscription" and payload.factory_mode_renewal_date is not None:
                subscription.factory_mode_renewal_date = payload.factory_mode_renewal_date
                subscription.updated_at = utc_now()
                session.add(subscription)
                session.commit()
                session.refresh(subscription)
    elif payload.factory_mode_renewal_date is not None and subscription.factory_mode_access == "subscription":
        subscription.factory_mode_renewal_date = payload.factory_mode_renewal_date
        subscription.updated_at = utc_now()
        session.add(subscription)
        session.commit()
        session.refresh(subscription)

    subscription.updated_at = utc_now()
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return _to_credit_response(session, user, subscription)


@router.delete(
    "/admin/users/{email}",
    response_model=AdminUserDeleteResponse,
    dependencies=[Depends(require_admin_dashboard_access)],
)
def delete_admin_user(
    email: str,
    session: Session = Depends(get_session),
) -> AdminUserDeleteResponse:
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    _delete_user_account(session, user)
    session.commit()
    return AdminUserDeleteResponse(deleted=True, email=email)


@router.delete(
    "/admin/users/actions/purge-test-purchases",
    response_model=AdminUserBulkDeleteResponse,
    dependencies=[Depends(require_admin_dashboard_access)],
)
def clear_test_purchases(session: Session = Depends(get_session)) -> AdminUserBulkDeleteResponse:
    users = session.exec(
        select(User)
        .where(func.lower(User.email).like("test-%"))
        .order_by(User.created_at.desc())
    ).all()
    deleted_emails: list[str] = []
    for user in users:
        deleted_emails.append(user.email)
        _delete_user_account(session, user)
    session.commit()
    return AdminUserBulkDeleteResponse(deleted_count=len(deleted_emails), deleted_emails=deleted_emails)
