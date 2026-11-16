"""Development-only routes (never mounted when APP_ENV=prod)."""

from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.deps import DB
from app.models import EmailOutbox
from app.templating import render

pages = APIRouter()


@pages.get("/dev/emails")
def outbox(request: Request, db: DB) -> Response:
    rows = db.scalars(select(EmailOutbox).order_by(EmailOutbox.id.desc()).limit(50)).all()
    return render(request, "dev/emails.html", {"rows": rows})
