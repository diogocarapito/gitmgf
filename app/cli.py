"""Command line: `python -m app.cli --help`."""

import json
from pathlib import Path
from typing import Any

import typer
import yaml
from sqlalchemy import select

from app.db import SessionLocal, get_engine
from app.models import Category, User
from app.models.enums import Role
from app.services import audit, certifications, legal, search, settings_store

ROOT = Path(__file__).resolve().parents[1]
cli = typer.Typer(help="gitmgf management commands", no_args_is_help=True)
seed_cli = typer.Typer(help="Seed reference data", no_args_is_help=True)
jobs_cli = typer.Typer(help="Run scheduler jobs once", no_args_is_help=True)
settings_cli = typer.Typer(help="Read and change site settings", no_args_is_help=True)
cli.add_typer(seed_cli, name="seed")
cli.add_typer(jobs_cli, name="jobs")
cli.add_typer(settings_cli, name="settings")


def _session() -> Any:
    get_engine()
    return SessionLocal()


def seed_categories_from(path: Path) -> int:
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    with _session() as db:
        for item in items:
            cat = db.scalar(select(Category).where(Category.slug == item["slug"]))
            if cat is None:
                cat = Category(slug=item["slug"])
                db.add(cat)
            cat.name_pt = item["name_pt"]
            cat.name_en = item["name_en"]
            cat.description_pt = item.get("description_pt")
            cat.description_en = item.get("description_en")
            cat.is_specialty = bool(item.get("is_specialty", False))
            cat.sort_order = int(item.get("sort_order", 0))
            cat.icon = item.get("icon")
        db.commit()
    return len(items)


def seed_certifications_from(path: Path) -> int:
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    with _session() as db:
        count = certifications.seed(db, items)
        db.commit()
    return count


@seed_cli.command("categories")
def seed_categories(path: Path = ROOT / "seeds" / "categories.yaml") -> None:
    """Upsert the category list by slug (never deletes)."""
    typer.echo(f"categories: {seed_categories_from(path)}")


@seed_cli.command("certifications")
def seed_certifications(path: Path = ROOT / "seeds" / "certifications.yaml") -> None:
    """Upsert the certification catalogue by code."""
    typer.echo(f"certifications: {seed_certifications_from(path)}")


@seed_cli.command("demo")
def seed_demo(tools: int = 30) -> None:
    """Development data: users, tools, stars and events. Refuses to run in prod."""
    from app.config import get_settings
    from app.demo import seed_demo_data

    if get_settings().is_prod:
        typer.echo("refusing to seed demo data in prod", err=True)
        raise typer.Exit(1)
    with _session() as db:
        created = seed_demo_data(db, tools)
        db.commit()
    typer.echo(f"demo tools: {created}")


@cli.command("create-admin")
def create_admin(email: str) -> None:
    """Create (or promote) an admin. They complete onboarding on first sign-in."""
    address = email.strip().lower()
    with _session() as db:
        user = db.scalar(select(User).where(User.email == address))
        if user is None:
            user = User(email=address, display_name="", role=Role.admin)
            db.add(user)
            db.flush()
            audit.log(db, None, "user.create_admin", "user", user.id, via="cli")
        elif user.role != Role.admin:
            audit.log(
                db, None, "user.role_change", "user", user.id, old=user.role.value, new="admin", via="cli"
            )
            user.role = Role.admin
        db.commit()
    typer.echo(f"admin ready: {address}")


@cli.command("reindex")
def reindex() -> None:
    """Rebuild the full-text search index."""
    with _session() as db:
        count = search.rebuild(db)
        db.commit()
    typer.echo(f"indexed: {count}")


@cli.command("check-config")
def check_config() -> None:
    """Report configuration problems (the same checks that block a prod start)."""
    from app.config import get_settings

    settings = get_settings()
    problems = settings.config_errors()
    with _session() as db:
        missing = legal.missing_placeholders(db)
        version = legal.terms_version()
        current = settings_store.get(db, "terms.current_version")
    if missing:
        problems.append("legal placeholders without value: " + ", ".join(sorted(missing)))
    if version != current:
        problems.append(f"terms.md version {version!r} != terms.current_version {current!r}")
    typer.echo(f"APP_ENV={settings.app_env} BASE_URL={settings.base_url} DB={settings.db_path}")
    typer.echo(
        f"email backend: {settings.email_backend}; GitHub OAuth: {settings.github_enabled}; Google OAuth: {settings.google_enabled}"
    )
    if problems:
        for problem in problems:
            typer.echo(f"  ✗ {problem}")
        raise typer.Exit(1)
    typer.echo("  ✓ configuration OK")


@settings_cli.command("get")
def settings_get(key: str) -> None:
    with _session() as db:
        typer.echo(json.dumps(settings_store.get(db, key), ensure_ascii=False))


@settings_cli.command("set")
def settings_set(
    key: str, value: str, as_json: bool = typer.Option(False, "--json", help="Parse VALUE as JSON")
) -> None:
    """e.g. `settings set legal.CONTROLLER_NAME "Diogo …"` or `settings set reports.auto_hide_threshold 3 --json`."""
    parsed: Any = json.loads(value) if as_json else value
    with _session() as db:
        settings_store.set_value(db, key, parsed, None)
        db.commit()
    typer.echo(f"{key} = {json.dumps(parsed, ensure_ascii=False)}")


@settings_cli.command("list")
def settings_list() -> None:
    with _session() as db:
        for key in sorted(settings_store.DEFAULTS):
            typer.echo(f"{key} = {json.dumps(settings_store.get(db, key), ensure_ascii=False)}")
        for key in settings_store.LEGAL_KEYS:
            typer.echo(
                f"legal.{key} = {json.dumps(settings_store.get(db, 'legal.' + key), ensure_ascii=False)}"
            )


@jobs_cli.command("send-outbox")
def job_send_outbox() -> None:
    from app import jobs

    typer.echo(f"sent: {jobs.send_outbox()}")


@jobs_cli.command("recompute-scores")
def job_recompute_scores() -> None:
    from app import jobs

    typer.echo(f"scored: {jobs.recompute_scores()}")


@jobs_cli.command("rotate-salt")
def job_rotate_salt() -> None:
    from app import jobs

    jobs.rotate_salt()
    typer.echo("salt rotated")


@jobs_cli.command("sync-github")
def job_sync_github(tool: int | None = typer.Option(None, "--tool", help="Only this tool id")) -> None:
    from app import jobs

    typer.echo(f"github: {jobs.sync_github(tool)}")


@jobs_cli.command("prune")
def job_prune() -> None:
    from app import jobs

    typer.echo(f"pruned: {jobs.prune()}")


@jobs_cli.command("cert-expiry")
def job_cert_expiry() -> None:
    from app import jobs

    typer.echo(f"certifications: {jobs.cert_expiry()}")


@jobs_cli.command("mod-digest")
def job_mod_digest() -> None:
    from app import jobs

    typer.echo(f"digests: {jobs.mod_digest()}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
