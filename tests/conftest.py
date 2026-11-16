import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_TMP = Path(tempfile.mkdtemp(prefix="gitmgf-tests-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-0123456789",
        "BASE_URL": "http://testserver",
        "DATA_DIR": str(_TMP / "data"),
        "DATABASE_PATH": str(_TMP / "data" / "unused.db"),
        "ADMIN_EMAILS": "boss@example.org",
        "GITHUB_CLIENT_ID": "gh-id",
        "GITHUB_CLIENT_SECRET": "gh-secret",
        "GOOGLE_CLIENT_ID": "g-id",
        "GOOGLE_CLIENT_SECRET": "g-secret",
    }
)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import i18n  # noqa: E402
from app.db import SessionLocal, init_engine, utcnow  # noqa: E402
from app.models import User  # noqa: E402
from app.models.enums import Locale, Profession, Role  # noqa: E402
from app.services import email, ratelimit, sessions, settings_store  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _compile_catalogs() -> None:
    from babel.messages.mofile import write_mo
    from babel.messages.pofile import read_po

    for po in (ROOT / "app" / "locales").glob("*/LC_MESSAGES/messages.po"):
        with po.open("rb") as f:
            catalog = read_po(f)
        with po.with_suffix(".mo").open("wb") as f:
            write_mo(f, catalog)
    i18n.clear_cache()


@pytest.fixture(scope="session")
def template_db() -> Path:
    _compile_catalogs()
    path = _TMP / "template.db"
    engine = init_engine(path)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["configure_logging"] = False
    command.upgrade(cfg, "head")
    from app.cli import seed_categories_from, seed_certifications_from

    seed_categories_from(ROOT / "seeds" / "categories.yaml")
    seed_certifications_from(ROOT / "seeds" / "certifications.yaml")
    engine.dispose()
    return path


@pytest.fixture
def db_path(template_db: Path, tmp_path: Path) -> Iterator[Path]:
    path = tmp_path / "test.db"
    shutil.copy(template_db, path)
    engine = init_engine(path)
    settings_store.invalidate()
    ratelimit.reset()
    email.SENT.clear()
    yield path
    engine.dispose()


@pytest.fixture
def db(db_path: Path) -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app, base_url="http://testserver", follow_redirects=False) as c:
        yield c


def make_user(
    db: Session,
    email_addr: str = "user@example.org",
    role: Role = Role.user,
    onboarded: bool = True,
    name: str = "Ana Utilizadora",
    locale: Locale = Locale.pt,
) -> User:
    user = User(email=email_addr, display_name=name, role=role, locale=locale, email_verified_at=utcnow())
    if onboarded:
        user.handle = email_addr.split("@")[0].replace(".", "-")[:30].ljust(3, "x")
        user.profession = Profession.resident
        user.onboarded_at = utcnow()
        user.terms_version = settings_store.DEFAULTS["terms.current_version"]
        user.terms_accepted_at = utcnow()
    db.add(user)
    db.commit()
    return user


def get_cookie(client: TestClient, name: str) -> str | None:
    values = [c.value for c in client.cookies.jar if c.name == name]
    return values[-1] if values else None


def clear_cookie(client: TestClient, name: str) -> None:
    for c in list(client.cookies.jar):
        if c.name == name:
            client.cookies.jar.clear(c.domain, c.path, c.name)


def login(client: TestClient, db: Session, user: User) -> None:
    token = sessions.create(db, user, "pytest")
    db.commit()
    clear_cookie(client, "gitmgf_session")
    client.cookies.set("gitmgf_session", token)


def csrf_token(client: TestClient) -> str:
    token = get_cookie(client, "gitmgf_csrf")
    if not token:
        client.get("/healthz")
        token = get_cookie(client, "gitmgf_csrf")
    assert token
    return token


def post(client: TestClient, url: str, data: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    payload = dict(data or {})
    payload.setdefault("csrf_token", csrf_token(client))
    return client.post(url, data=payload, **kwargs)
