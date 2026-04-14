from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from email.message import EmailMessage
import smtplib

from app.config import (
    ADMIN_EMAIL,
    EMAIL_FROM_ADDRESS,
    EMAIL_FROM_NAME,
    EMAIL_REPLY_TO,
    EMAIL_SMTP_HOST,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_USERNAME,
    EMAIL_SMTP_USE_SSL,
    EMAIL_SMTP_USE_TLS,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _format_amount(amount: float, currency: str) -> str:
    clean_currency = (currency or "").strip().upper() or "USD"
    if clean_currency == "USD":
        return f"${amount:,.2f}"
    return f"{clean_currency} {amount:,.2f}"


def _provider_label(provider: str) -> str:
    return "Paystack / MoMo" if provider.strip().lower() == "paystack" else "Stripe"


def _build_text_receipt(
    *,
    recipient_email: str,
    plan_name: str,
    credits: int,
    item_description: str,
    provider: str,
    amount: float,
    currency: str,
    reference_id: str,
    purchased_at: datetime,
) -> str:
    lines = [
        "Pro Creator payment receipt",
        "",
        f"Recipient: {recipient_email}",
        f"Plan: {plan_name}",
        f"Item: {item_description}",
    ]
    if credits > 0:
        lines.append(f"Credits: {credits}")
    lines.extend(
        [
            f"Provider: {_provider_label(provider)}",
            f"Amount: {_format_amount(amount, currency)}",
            f"Reference: {reference_id}",
            f"Purchased at: {purchased_at.astimezone(timezone.utc).isoformat()}",
            "",
            "Your purchase has been confirmed successfully. You can review this transaction in the app's receipt history.",
        ]
    )
    return "\n".join(lines)


def _build_html_receipt(
    *,
    recipient_email: str,
    plan_name: str,
    credits: int,
    item_description: str,
    provider: str,
    amount: float,
    currency: str,
    reference_id: str,
    purchased_at: datetime,
) -> str:
    amount_label = _format_amount(amount, currency)
    provider_label = _provider_label(provider)
    timestamp = purchased_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""
    <html>
      <body style="margin:0;padding:0;background:#050816;color:#e2e8f0;font-family:Arial,sans-serif;">
        <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
          <div style="border:1px solid rgba(34,211,238,0.25);border-radius:20px;background:rgba(2,6,23,0.92);padding:28px;">
            <div style="font-size:12px;letter-spacing:0.35em;text-transform:uppercase;color:#94a3b8;">Pro Creator</div>
            <h1 style="margin:12px 0 8px;font-size:28px;line-height:1.2;color:#ffffff;">Payment receipt</h1>
            <p style="margin:0 0 20px;color:#cbd5e1;">Your purchase has been confirmed and credits were added to your account.</p>
            <div style="border:1px solid rgba(51,65,85,0.9);border-radius:16px;padding:18px;background:rgba(15,23,42,0.72);">
              <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Recipient:</strong> {recipient_email}</p>
              <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Plan:</strong> {plan_name}</p>
              <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Item:</strong> {item_description}</p>
              {f'<p style="margin:0 0 10px;"><strong style="color:#ffffff;">Credits:</strong> {credits}</p>' if credits > 0 else ''}
              <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Provider:</strong> {provider_label}</p>
              <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Amount:</strong> {amount_label}</p>
              <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Reference:</strong> {reference_id}</p>
              <p style="margin:0;"><strong style="color:#ffffff;">Purchased at:</strong> {timestamp}</p>
            </div>
            <p style="margin:18px 0 0;color:#94a3b8;font-size:13px;line-height:1.6;">
              Your purchase has been confirmed successfully. You can view this receipt again in the app's receipt history.
            </p>
          </div>
        </div>
      </body>
    </html>
    """


def build_purchase_receipt_email(
    *,
    recipient_email: str,
    plan_name: str,
    credits: int,
    item_description: str | None = None,
    provider: str,
    amount: float,
    currency: str,
    reference_id: str,
    purchased_at: datetime | None = None,
) -> EmailMessage:
    timestamp = purchased_at or datetime.now(timezone.utc)
    subject = f"Pro Creator receipt for {plan_name} plan"
    clean_item_description = (item_description or "").strip() or (f"{credits} credits" if credits > 0 else "Purchase")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>"
    message["To"] = recipient_email
    if EMAIL_REPLY_TO:
        message["Reply-To"] = EMAIL_REPLY_TO
    message.set_content(
        _build_text_receipt(
            recipient_email=recipient_email,
            plan_name=plan_name,
            credits=credits,
            item_description=clean_item_description,
            provider=provider,
            amount=amount,
            currency=currency,
            reference_id=reference_id,
            purchased_at=timestamp,
        )
    )
    message.add_alternative(
        _build_html_receipt(
            recipient_email=recipient_email,
            plan_name=plan_name,
            credits=credits,
            item_description=clean_item_description,
            provider=provider,
            amount=amount,
            currency=currency,
            reference_id=reference_id,
            purchased_at=timestamp,
        ),
        subtype="html",
    )
    return message


def send_purchase_receipt_email(
    *,
    recipient_email: str,
    plan_name: str,
    credits: int,
    item_description: str | None = None,
    provider: str,
    amount: float,
    currency: str,
    reference_id: str,
    purchased_at: datetime | None = None,
) -> bool:
    if not EMAIL_SMTP_HOST:
        logger.info("Receipt email skipped because EMAIL_SMTP_HOST is not configured")
        return False

    message = build_purchase_receipt_email(
        recipient_email=recipient_email,
        plan_name=plan_name,
        credits=credits,
        item_description=item_description,
        provider=provider,
        amount=amount,
        currency=currency,
        reference_id=reference_id,
        purchased_at=purchased_at,
    )

    smtp_client: smtplib.SMTP | smtplib.SMTP_SSL
    if EMAIL_SMTP_USE_SSL:
        smtp_client = smtplib.SMTP_SSL(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30)
    else:
        smtp_client = smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30)
    try:
        smtp_client.ehlo()
        if EMAIL_SMTP_USE_TLS and not EMAIL_SMTP_USE_SSL:
            smtp_client.starttls()
            smtp_client.ehlo()
        if EMAIL_SMTP_USERNAME:
            smtp_client.login(EMAIL_SMTP_USERNAME, EMAIL_SMTP_PASSWORD)
        smtp_client.send_message(message)
        logger.info("Sent receipt email to %s for reference %s", recipient_email, reference_id)
        return True
    finally:
        smtp_client.quit()


def build_feedback_email(
    *,
    sender_email: str,
    subject: str,
    message: str,
    page: str | None = None,
    project_id: str | None = None,
) -> EmailMessage:
    clean_subject = (subject or "").strip() or "User feedback"
    clean_message = (message or "").strip()
    safe_sender_email = escape(sender_email or "unknown")
    safe_subject = escape(clean_subject)
    safe_page = escape(page) if page else None
    safe_project_id = escape(project_id) if project_id else None
    safe_message = escape(clean_message).replace("\n", "<br />")
    message_obj = EmailMessage()
    message_obj["Subject"] = f"Pro Creator feedback: {clean_subject}"
    message_obj["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>"
    message_obj["To"] = ADMIN_EMAIL
    if EMAIL_REPLY_TO:
        message_obj["Reply-To"] = EMAIL_REPLY_TO
    if sender_email:
        message_obj["Reply-To"] = sender_email
    text_lines = [
        "Pro Creator user feedback",
        "",
        f"From: {sender_email or 'unknown'}",
        f"Subject: {clean_subject}",
    ]
    if page:
        text_lines.append(f"Page: {page}")
    if project_id:
        text_lines.append(f"Project: {project_id}")
    text_lines.extend(["", clean_message])
    message_obj.set_content("\n".join(text_lines))
    message_obj.add_alternative(
        f"""
        <html>
          <body style="margin:0;padding:0;background:#050816;color:#e2e8f0;font-family:Arial,sans-serif;">
            <div style="max-width:640px;margin:0 auto;padding:32px 20px;">
              <div style="border:1px solid rgba(34,211,238,0.25);border-radius:20px;background:rgba(2,6,23,0.92);padding:28px;">
                <div style="font-size:12px;letter-spacing:0.35em;text-transform:uppercase;color:#94a3b8;">Pro Creator</div>
                <h1 style="margin:12px 0 8px;font-size:28px;line-height:1.2;color:#ffffff;">User feedback</h1>
                <p style="margin:0 0 20px;color:#cbd5e1;">A user submitted feedback from inside the app.</p>
                <div style="border:1px solid rgba(51,65,85,0.9);border-radius:16px;padding:18px;background:rgba(15,23,42,0.72);">
                  <p style="margin:0 0 10px;"><strong style="color:#ffffff;">From:</strong> {safe_sender_email}</p>
                  <p style="margin:0 0 10px;"><strong style="color:#ffffff;">Subject:</strong> {safe_subject}</p>
                  {f'<p style="margin:0 0 10px;"><strong style="color:#ffffff;">Page:</strong> {safe_page}</p>' if safe_page else ''}
                  {f'<p style="margin:0 0 10px;"><strong style="color:#ffffff;">Project:</strong> {safe_project_id}</p>' if safe_project_id else ''}
                  <p style="margin:0;color:#cbd5e1;">{safe_message}</p>
                </div>
              </div>
            </div>
          </body>
        </html>
        """,
        subtype="html",
    )
    return message_obj


def send_feedback_email(
    *,
    sender_email: str,
    subject: str,
    message: str,
    page: str | None = None,
    project_id: str | None = None,
) -> bool:
    if not EMAIL_SMTP_HOST:
        logger.info("Feedback email skipped because EMAIL_SMTP_HOST is not configured")
        return False

    feedback_message = build_feedback_email(
        sender_email=sender_email,
        subject=subject,
        message=message,
        page=page,
        project_id=project_id,
    )

    smtp_client: smtplib.SMTP | smtplib.SMTP_SSL
    if EMAIL_SMTP_USE_SSL:
        smtp_client = smtplib.SMTP_SSL(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30)
    else:
        smtp_client = smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30)
    try:
        smtp_client.ehlo()
        if EMAIL_SMTP_USE_TLS and not EMAIL_SMTP_USE_SSL:
            smtp_client.starttls()
            smtp_client.ehlo()
        if EMAIL_SMTP_USERNAME:
            smtp_client.login(EMAIL_SMTP_USERNAME, EMAIL_SMTP_PASSWORD)
        smtp_client.send_message(feedback_message)
        logger.info("Sent feedback email from %s", sender_email)
        return True
    finally:
        smtp_client.quit()
