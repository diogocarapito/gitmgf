# gitmgf

A bilingual (PT-PT first, EN) portal where clinicians publish and discover the digital tools they built, focused on primary care (MGF) and residency (Internato). Listings only: gitmgf never hosts or runs the tools themselves.

- **What & why:** [`PRD.md`](PRD.md) · **How:** [`TECH_SPEC.md`](TECH_SPEC.md) · **Conventions:** [`CLAUDE.md`](CLAUDE.md)
- **Decisions:** [`docs/DECISIONS.md`](docs/DECISIONS.md) · **Operations:** [`docs/RUNBOOK.md`](docs/RUNBOOK.md)

Stack: Python 3.12 · FastAPI (sync) · Jinja2 · HTMX · SQLAlchemy 2 + Alembic · SQLite (WAL) + Litestream · Babel · Docker Compose · Caddy. No Node, no CDN, no external fonts, no analytics.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.cli seed categories
python -m app.cli seed certifications
python -m app.cli seed demo          # optional: 30 fictional tools, users and usage
pybabel compile -d app/locales -D messages
ADMIN_EMAILS=you@example.org uvicorn app.main:app --reload
```

Open http://localhost:8000. Sign-in links are printed in the terminal (and listed at `/pt/dev/emails`) because no SMTP server is configured in dev. Or run everything in Docker: `docker compose up --build`.

## Checks

```bash
pytest -q                      # 321 tests: permissions matrix, lifecycle, search, scoring, GDPR, legal…
ruff check . && ruff format --check .
mypy app/services
make i18n                      # after changing any user-facing string
```

## Deploy

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md). In short, on an Ubuntu 24.04 VPS with Docker:

```bash
cp .env.example .env && nano .env
./deploy/deploy.sh
```

## Layout

```
app/            FastAPI app: routers (thin), services (business rules), models, forms, templates, static
migrations/     Alembic (FTS5 index and expression indexes written by hand)
seeds/          categories.yaml, certifications.yaml
content/legal/  Terms, Privacy, Guidelines, Disclaimer, About, Contact (pt prevails, en translations)
deploy/         Caddyfile, prod compose, Litestream, entrypoint, VPS setup and deploy scripts
docs/           decisions, runbook, design references (mockup, logo)
tests/          pytest suite
```
