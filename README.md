# gitmgf

A bilingual (PT-PT first, EN) portal where clinicians publish and discover the digital tools they built, focused on primary care (MGF) and residency (Internato). Listings only: gitmgf never hosts or runs the tools themselves.

- **What & why:** [`PRD.md`](PRD.md) · **How:** [`TECH_SPEC.md`](TECH_SPEC.md) · **Conventions:** [`CLAUDE.md`](CLAUDE.md)
- **Decisions:** [`docs/DECISIONS.md`](docs/DECISIONS.md) · **Operations:** [`docs/RUNBOOK.md`](docs/RUNBOOK.md) · **Changes:** [`docs/CHANGELOG.md`](docs/CHANGELOG.md)

Stack: Python 3.12 · FastAPI (sync) · Jinja2 · HTMX · SQLAlchemy 2 + Alembic · SQLite (WAL) + Litestream · Babel · Docker Compose · Caddy. No Node, no CDN, no external fonts, no analytics.

## Accounts (MVP)

- **Sign-in:** email + password (scrypt hashes, rate-limited). No OAuth, no magic links.
- **Registration:** invite-only by default. Admins create invite links in **Administração → Convites** or with `python -m app.cli invite`. Registration can be opened to everyone in **Administração → Definições → Registos abertos**.
- **Bootstrap:** addresses in `ADMIN_EMAILS` can register without an invite and become admins.
- **Forgotten password:** an admin generates a one-time set-password link (48 h) from the user's admin page and sends it to the person.
- **Email is optional:** without `SMTP_HOST`, notifications stay in the outbox (**Administração → Emails**); authors see status and rejection reasons in **As minhas ferramentas**.

See decision D26 in [`docs/DECISIONS.md`](docs/DECISIONS.md).

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

Open http://localhost:8000/register and create an account with the address you put in `ADMIN_EMAILS` (no invite needed). To try another account, create an invite in **Administração → Convites** and open the link in a private window.

In dev, notifications are printed in the terminal and listed at `/dev/emails`. Or run everything in Docker: `docker compose up --build`.

Useful CLI commands (`python -m app.cli --help`):

| Command | What it does |
|---|---|
| `create-admin EMAIL` | Create or promote an admin and print a one-time set-password link |
| `invite [--email E] [--uses N] [--days D] [--note T]` | Create a registration invite and print its link |
| `seed categories` / `seed certifications` | Upsert the reference data (`--if-empty` on container start) |
| `seed demo` | Fictional demo data (refuses to run in prod) |
| `reindex` | Rebuild the search index |
| `check-config` | Report what would block a production start |
| `settings list` / `get` / `set` | Read and change site settings |
| `jobs …` | Run a scheduler job once |

## Checks

```bash
pytest -q                      # 325 tests: permissions matrix, auth, lifecycle, search, scoring, GDPR, legal…
ruff check . && ruff format --check .
mypy app/services
make i18n                      # after changing any user-facing string
```

## Deploy

See [`docs/RUNBOOK.md`](docs/RUNBOOK.md). In short, on an Ubuntu 24.04 VPS with Docker:

```bash
git clone https://github.com/diogocarapito/gitmgf.git && cd gitmgf
cp .env.example .env && nano .env     # SECRET_KEY, ADMIN_EMAILS, DOMAIN, BASE_URL, ACME_EMAIL, LEGAL_*
./deploy/deploy.sh
```

Then register at `https://<your domain>/register` with the `ADMIN_EMAILS` address.

## Layout

```
app/            FastAPI app: routers (thin), services (business rules), models, forms, templates, static
migrations/     Alembic (FTS5 index and expression indexes written by hand)
seeds/          categories.yaml, certifications.yaml
content/legal/  Terms, Privacy, Guidelines, Disclaimer, About, Contact (pt prevails, en translations)
deploy/         Caddyfile, prod compose, Litestream, entrypoint, VPS setup and deploy scripts
docs/           decisions, runbook, changelog, design references (mockup, logo)
scripts/        maintenance helpers (translation catalogue)
tests/          pytest suite
```
