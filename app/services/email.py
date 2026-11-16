"""Transactional email through a DB outbox (TECH_SPEC §17).

Rows are rendered when queued; `deliver_queued()` sends them (immediately in a background task,
and every minute from the scheduler). Exponential backoff, max 5 attempts.
"""

import logging
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_engine, utcnow
from app.models import EmailOutbox
from app.models.enums import EmailStatus

log = logging.getLogger("gitmgf.email")

MAX_ATTEMPTS = 5
# Test/dev inspection: messages "sent" by the memory backend.
SENT: list[EmailMessage] = []


def enqueue(db: Session, to: str, template: str, context: dict[str, Any], locale: str) -> EmailOutbox:
    from app.templating import render_email

    subject, text, html = render_email(template, context, locale)
    row = EmailOutbox(
        to_email=to,
        locale=locale,
        template=template,
        context=_json_safe(context),
        subject=subject[:200],
        body_text=text,
        body_html=html,
        next_attempt_at=utcnow(),
    )
    db.add(row)
    return row


def _json_safe(context: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v if isinstance(v, (str, int, float, bool, type(None))) else str(v) for k, v in context.items()
    }


def build_message(row: EmailOutbox) -> EmailMessage:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = row.subject
    msg["From"] = settings.smtp_from
    msg["To"] = row.to_email
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from.split("@")[-1].strip("> ") or None)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(row.body_text)
    msg.add_alternative(row.body_html, subtype="html")
    return msg


def _send(msg: EmailMessage) -> None:
    settings = get_settings()
    backend = settings.email_backend
    if backend == "memory":
        SENT.append(msg)
        return
    if backend == "console":
        body = msg.get_body(preferencelist=("plain",))
        content = body.get_content() if body is not None else ""
        log.info("email to=%s subject=%s\n%s", "***", msg["Subject"], content)
        print(f"\n----- EMAIL -----\nSubject: {msg['Subject']}\n\n{content}-----------------\n", flush=True)
        return
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=15) as smtp:
            _login_and_send(smtp, msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=context)
            _login_and_send(smtp, msg)


def _login_and_send(smtp: smtplib.SMTP, msg: EmailMessage) -> None:
    settings = get_settings()
    if settings.smtp_user:
        smtp.login(settings.smtp_user, settings.smtp_password)
    smtp.send_message(msg)


def _claim(db: Session, row: EmailOutbox) -> bool:
    """Atomically bump attempts so two workers never send the same row."""
    result = db.execute(
        update(EmailOutbox)
        .where(
            EmailOutbox.id == row.id,
            EmailOutbox.attempts == row.attempts,
            EmailOutbox.status != EmailStatus.sent,
        )
        .values(attempts=row.attempts + 1, next_attempt_at=utcnow() + timedelta(minutes=10))
    )
    db.commit()
    return bool(getattr(result, "rowcount", 0))


def deliver_queued(db: Session | None = None, limit: int = 50) -> int:
    if get_settings().email_backend == "none":
        return 0  # kept queued until SMTP is configured
    own = db is None
    if own:
        get_engine()
        db = SessionLocal()
    assert db is not None
    sent = 0
    try:
        now = utcnow()
        rows = db.scalars(
            select(EmailOutbox)
            .where(
                EmailOutbox.status.in_([EmailStatus.queued, EmailStatus.failed]),
                EmailOutbox.attempts < MAX_ATTEMPTS,
                or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= now),
            )
            .order_by(EmailOutbox.id)
            .limit(limit)
        ).all()
        for row in rows:
            if not _claim(db, row):
                continue
            db.refresh(row)
            try:
                _send(build_message(row))
            except Exception as exc:
                row.status = EmailStatus.failed
                row.last_error = f"{type(exc).__name__}: {exc}"[:500]
                row.next_attempt_at = utcnow() + timedelta(minutes=2**row.attempts)
                log.warning("email %s failed (attempt %s): %s", row.id, row.attempts, type(exc).__name__)
            else:
                row.status = EmailStatus.sent
                row.sent_at = utcnow()
                row.last_error = None
                sent += 1
            db.commit()
    finally:
        if own:
            db.close()
    return sent
