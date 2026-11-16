# gitmgf — Technical Specification

| | |
|---|---|
| **Version** | v0.1 (MVP) — 2026-11-16 |
| **Implements** | `PRD.md` v0.2 (feature IDs F1–F20, F5 removed; milestones M0–M7) |
| **Audience** | Claude Code and human developers |

> Rule of thumb: when this spec and the PRD disagree on *behaviour*, the PRD wins; when they disagree on *implementation*, this spec wins. Record any deviation in `docs/DECISIONS.md`.

---

## 1. Architecture overview

```
                       ┌─────────────────────────── VPS (EU, 2 vCPU / 4 GB) ─────────────────────────────┐
 Browser ── HTTPS ──▶  │ Caddy (TLS, compression, static /media, security headers)                      │
                       │   ├── gitmgf.com ───────────▶ app  (FastAPI + Jinja2 + HTMX, uvicorn ×2)        │
                       │   │                               │                                             │
                       │                                   ▼                                             │
                       │   scheduler (same image) ──▶ SQLite /data/gitmgf.db (WAL) ◀── litestream ──▶ S3 (EU)│
                       │      score job, GitHub sync,      /data/media (screenshots only)                │
                       │      email outbox, pruning                                                      │
                       └─────────────────────────────────────────────────────────────────────────────────┘
 External: SMTP provider (EU) · GitHub OAuth + REST API · Google OAuth
```

- **Server-rendered** HTML (Jinja2). HTMX adds partial updates (live search, star toggle, load more, inline form validation). Every public page works without JavaScript.
- **One SQLite database** in WAL mode, shared by the `app` and `scheduler` containers through a volume. Continuous replication with **Litestream** to EU S3-compatible storage.
- **No Node build step.** CSS hand-written; HTMX and icons vendored into `static/`.
- **Listings only.** gitmgf never stores, serves or executes tools or user code. The only user-uploaded files are screenshots, which are re-encoded (§12). Every "open" action is an outbound link through the tracking redirect (§9).

## 2. Stack and dependencies

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | `venv` + `pip`; dependencies pinned in `requirements.txt` (runtime) and `requirements-dev.txt` (tests/tooling); `pyproject.toml` only for tool config (ruff, pytest, mypy) |
| Web | FastAPI, uvicorn[standard], python-multipart | **Sync** route handlers (SQLite + threadpool is simplest and fast enough) |
| Templates | Jinja2 + `jinja2.ext.i18n` | Autoescape on |
| Frontend | HTMX 2.x (vendored), small vanilla JS file, hand-written CSS | No inline scripts/styles (strict CSP) |
| ORM / migrations | SQLAlchemy 2.0 (typed `Mapped[]`), Alembic (`render_as_batch=True`) | Enums stored as strings with CHECK constraints |
| Settings | pydantic-settings | `.env` |
| Validation | Pydantic v2 form models | Re-render form with errors |
| OAuth | Authlib (Starlette client) + httpx | GitHub, Google (OIDC) |
| i18n | Babel (extraction, `.po/.mo`, date/number formatting) | Locales `pt_PT`, `en` |
| Markdown | markdown-it-py (commonmark + table + linkify, `html=False`) + **nh3** sanitiser | Rendered HTML cached in DB |
| Images | Pillow | Re-encode to WebP, strip metadata |
| Rate limiting | `limits` (in-memory storage) via small dependency | Single app host |
| Scheduler | APScheduler 3.x (BlockingScheduler) in `scheduler` container | Jobs are also exposed as CLI commands |
| CLI | Typer | Run as `python -m app.cli …` |
| Email | stdlib `smtplib` (SSL/STARTTLS) + DB outbox | Provider: Brevo / Scaleway TEM (EU) |
| Slugs | python-slugify | |
| Tests | pytest, pytest-cov, httpx (TestClient), respx, time-machine | |
| Quality | ruff (lint + format), mypy (strict on `app/services`) | pre-commit |
| Infra | Docker, Docker Compose, Caddy 2, Litestream | GitHub Actions CI/CD, image in GHCR |

### 2.1 Dependency management (pip)

- Python 3.12 virtual environment: `python3.12 -m venv .venv && source .venv/bin/activate`.
- `requirements.txt`: runtime packages only, every line pinned with `==` (e.g. `fastapi==X.Y.Z`). Used by the Docker image.
- `requirements-dev.txt`: first line `-r requirements.txt`, then test and tooling packages, also pinned.
- Adding a dependency: `pip install <pkg>`, then add `<pkg>==<installed version>` by hand to the right file (check with `pip show <pkg>`). Don't dump `pip freeze` wholesale — it mixes dev, runtime and transitive packages.
- Upgrading: bump the pin, `pip install -r requirements-dev.txt`, run the test suite, commit. Dependabot (`package-ecosystem: pip`) opens these PRs automatically.
- Optional later hardening: generate hash-pinned files (`pip install --require-hashes`) if supply-chain risk becomes a concern.
- The app is **not** installed as a package; run it from the repo root (`python -m app.cli`, `uvicorn app.main:app`).

## 3. Repository layout

```
gitmgf/
├── app/
│   ├── main.py                 # app factory, middleware, routers, error handlers
│   ├── config.py               # Settings (pydantic-settings)
│   ├── db.py                   # engine, session dependency, SQLite pragmas
│   ├── models/                 # SQLAlchemy models (one file per aggregate)
│   │   ├── user.py  tool.py  taxonomy.py  moderation.py  tracking.py  system.py
│   ├── forms/                  # Pydantic form models + validators
│   ├── routers/
│   │   ├── public.py           # home, search, category, tool page, static pages, feeds
│   │   ├── auth.py             # magic link, OAuth, logout, onboarding
│   │   ├── me.py               # settings, my tools, tool editor, stars, GDPR
│   │   ├── mod.py              # moderation queue & actions
│   │   ├── admin.py            # users, taxonomy, settings, stats, audit
│   │   ├── tracking.py         # /r/ and /go/ redirects, star toggle
│   │   └── system.py           # healthz, sitemap, robots
│   ├── services/
│   │   ├── auth.py  sessions.py  csrf.py  permissions.py
│   │   ├── tools.py            # lifecycle state machine, revisions, slugs
│   │   ├── search.py           # FTS indexing & query building
│   │   ├── scoring.py          # aggregation + score computation
│   │   ├── tracking.py         # visitor hash, bot filter, event insert
│   │   ├── github.py           # repo URL parsing + sync
│   │   ├── certifications.py   # catalogue, claim validation, badge computation, expiry
│   │   ├── media.py            # image processing
│   │   ├── markdown.py  email.py  audit.py  settings_store.py  ratelimit.py
│   ├── i18n/
│   │   ├── __init__.py         # locale resolution, gettext install, url helpers
│   │   └── labels.py           # translated labels for enums
│   ├── templates/
│   │   ├── base.html  _macros.html
│   │   ├── partials/           # tool_card, search_results, star_button, flash, pagination, form_errors…
│   │   ├── public/ auth/ me/ mod/ admin/ pages/ emails/
│   ├── static/
│   │   ├── css/app.css  js/app.js  vendor/htmx.min.js  icons/sprite.svg  fonts/
│   ├── locales/{pt_PT,en}/LC_MESSAGES/messages.po
│   ├── jobs.py                 # job functions (used by scheduler + CLI)
│   ├── scheduler.py            # APScheduler entry point
│   └── cli.py                  # Typer app
├── migrations/                 # Alembic
├── seeds/categories.yaml       # initial category list (PT/EN)
├── seeds/certifications.yaml   # certification catalogue (PRD F20)
├── content/legal/{pt,en}/*.md  # Terms, Privacy, Disclaimer, Guidelines, About (Markdown)
├── tests/
├── deploy/ Caddyfile  litestream.yml  docker-compose.prod.yml
├── requirements.txt            # runtime deps, pinned with ==
├── requirements-dev.txt        # -r requirements.txt + pytest, ruff, mypy, respx, time-machine, pip-audit
├── Dockerfile  docker-compose.yml  .env.example  babel.cfg  pyproject.toml (tool config only)  Makefile
├── docs/DECISIONS.md
├── PRD.md  TECH_SPEC.md  CLAUDE.md
```

## 4. Configuration (`.env`)

| Variable | Example | Purpose |
|---|---|---|
| `APP_ENV` | `dev` / `prod` | Toggles secure cookies, debug, email backend |
| `SECRET_KEY` | 64 random bytes (hex) | Signing (OAuth state cookie, CSRF) |
| `BASE_URL` | `https://gitmgf.com` | Absolute links, OAuth callbacks |
| `DATA_DIR` | `/data` | DB and media (screenshots) live under it |
| `DATABASE_PATH` | `/data/gitmgf.db` | |
| `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` | | `APP_ENV=dev` → console email backend |
| `GITHUB_CLIENT_ID` `GITHUB_CLIENT_SECRET` | | OAuth |
| `GOOGLE_CLIENT_ID` `GOOGLE_CLIENT_SECRET` | | OAuth (OIDC) |
| `GITHUB_API_TOKEN` | optional | Repo sync (5 000 req/h instead of 60) |
| `ADMIN_EMAILS` | `a@x.pt,b@y.pt` | Auto-promote to admin on login |
| `LITESTREAM_REPLICA_URL` `LITESTREAM_ACCESS_KEY_ID` `LITESTREAM_SECRET_ACCESS_KEY` | | Backup replica |
| `HEALTHCHECK_PING_URL` | optional | Scheduler heartbeat |

## 5. Database

### 5.1 SQLite setup

On every connection (SQLAlchemy `connect` event):

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -20000;   -- ~20 MB
```

- All timestamps stored as UTC ISO-8601 (`DateTime(timezone=True)` with a UTC type decorator).
- IDs: integer autoincrement primary keys internally; public URLs use slugs. Search session IDs use ULIDs.
- JSON columns via `sqlalchemy.JSON` (SQLite JSON1).
- Enums: `Enum(..., native_enum=False, create_constraint=True)`.
- Keep write transactions short; never hold a transaction open during network I/O (email, GitHub).

### 5.2 Entity overview

```
users ─┬─< oauth_accounts
       ├─< sessions
       ├─< tools ─┬─< tool_categories >── categories
       │          ├─< tool_tags >── tags
       │          ├─< tool_media
       │          ├─< tool_revisions
       │          ├─1 tool_github
       │          ├─< tool_certifications >── certifications
       │          ├─< tool_daily_stats
       │          ├─< interaction_events
       │          └─< reports
       ├─< stars >── tools
       └─< audit_log
magic_link_tokens · search_queries · email_outbox · site_settings · tool_search (FTS5)
```

### 5.3 Tables

**users**

| Column | Type | Constraints / notes |
|---|---|---|
| id | int PK | |
| email | text | unique, lowercase |
| email_verified_at | datetime | null until magic link / verified OAuth email |
| display_name | text | 2–80 |
| handle | text | unique, `[a-z0-9-]{3,30}` |
| profession | enum | `specialist, resident, nurse, pharmacist, med_student, other_health, engineer, other` |
| specialty_category_id | int FK categories | nullable |
| workplace | text | nullable, ≤ 120 |
| github_username | text | nullable |
| locale | enum `pt`/`en` | default `pt` |
| role | enum | `user, moderator, admin` default `user` |
| status | enum | `active, suspended, deleted` |
| suspended_reason | text | nullable |
| onboarded_at | datetime | null → redirect to onboarding |
| terms_version | text | accepted version |
| terms_accepted_at | datetime | |
| created_at, updated_at, last_login_at | datetime | |
| deleted_at | datetime | soft delete; purge job after 30 days |

**oauth_accounts** — id, user_id FK (cascade), provider enum `github|google`, provider_user_id text, provider_email text, created_at. Unique (provider, provider_user_id).

**magic_link_tokens** — id, email, token_hash (sha256 hex, unique), next_path text (validated relative path), expires_at, used_at, created_at. Index on email.

**sessions** — id text PK = sha256(cookie token), user_id FK (cascade), csrf_secret text, created_at, last_seen_at, expires_at, user_agent (≤ 200 chars). Index on user_id.

**categories** — id, slug unique, name_pt, name_en, description_pt, description_en, icon (sprite id), sort_order int, is_active bool, is_specialty bool (only used to populate the profile "specialty" dropdown; categories stay one flat list for tools).

**tags** — id, slug unique (normalised: lowercase, trimmed, spaces → `-`), label (display, accents kept), usage_count int (denormalised), created_at.

**tools**

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| slug | text unique | from `title_pt`; immutable after first publish (admin may change → add `slug_redirects` later) |
| owner_id | FK users | |
| status | enum | `draft, pending, published, rejected, hidden, archived, deleted` |
| tool_type | enum | `webapp, calculator, desktop, mobile, spreadsheet, script, extension, ai_prompt, dataset, other` |
| title_pt / title_en | text | en nullable |
| summary_pt / summary_en | text | ≤ 200 |
| description_pt / description_en | text | Markdown source |
| description_html_pt / description_html_en | text | sanitised render cache |
| intended_use | text | ≤ 600 |
| care_setting | enum | `primary, hospital, both, na` |
| platforms | JSON list[str] | `web, windows, macos, linux, android, ios, excel, gsheets, libreoffice, other` |
| tool_languages | JSON list[str] | `pt, en, es, fr, other` |
| website_url, repo_url, download_url, docs_url | text | nullable, http(s) only, ≤ 500 |
| license_spdx | text | SPDX id, `proprietary` or `unknown` |
| is_open_source | bool | computed on save: OSI-approved SPDX **and** `repo_url` present |
| pricing | enum | `free, freemium, paid` |
| patient_data | enum | `none, local_only, server, unknown` |
| version_label | text | nullable |
| rejection_reason | text | last reason shown to owner |
| score | float | default 0 |
| score_log | float | `ln(1 + score)`, used in search ranking |
| score_reset_at | datetime | events before this are ignored |
| stars_count | int | denormalised |
| declarations_accepted_at | datetime | |
| created_at, updated_at, submitted_at, published_at, last_content_update_at | datetime | |
| deleted_at | datetime | |

Indexes: `(status, score DESC)`, `(status, published_at DESC)`, `(owner_id)`, `(status, stars_count DESC)`.

**tool_categories** (tool_id, category_id) PK both. **tool_tags** (tool_id, tag_id) PK both.

**tool_media** — id, tool_id FK, revision_id FK nullable (pending media belonging to a revision), state enum `live|pending|removed`, file_name (uuid.webp), thumb_name, width, height, alt_text_pt, alt_text_en, sort_order, created_at.

**tool_revisions** — id, tool_id FK, submitted_by FK users, data JSON (full snapshot of editable fields incl. `category_ids`, `tags`, `media_order`, `certifications` = list of `{code, details}`), status enum `pending|approved|rejected|withdrawn`, reviewer_id, review_reason, created_at, reviewed_at. Constraint: at most one `pending` revision per tool (partial unique index `WHERE status='pending'`).

**stars** — (user_id, tool_id) PK, created_at.

**tool_github** — tool_id PK FK, owner, repo, stars, forks, open_issues, pushed_at, license_spdx, archived bool, default_branch, etag, fetched_at, last_error.

**certifications** (catalogue, admin-managed — PRD F20)

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| code | text unique | `ce, mdr, rgpd, ivdr, iso13485, iso27001, iso27701, iec62304, europrivacy, ai_act, a11y, spms, ehds` |
| badge_label | text | Short label, e.g. `CE`, `MDR`, `RGPD` |
| label_template | text | Optional, e.g. `MDR {class}` → "MDR IIa" |
| name_pt / name_en | text | Full name |
| help_pt / help_en | text | Shown in the submission form (Markdown) |
| assurance_default | enum | `self_declared, third_party, mixed` |
| field_schema | JSON | List of field definitions (below) |
| is_core | bool | Always shown (present or slashed) |
| is_active | bool | Inactive items are hidden everywhere and not selectable |
| sort_order | int | |
| created_at, updated_at | datetime | |

`field_schema` item: `{ "key": "class", "type": "enum|text|url|date|bool|nb_number", "label_pt": "...", "label_en": "...", "required": true, "required_if": {"class": ["IIa","IIb","III"]}, "options": ["I","IIa","IIb","III"], "assurance_if": {"class": {"I": "self_declared", "*": "third_party"}} }`. A field with `"key": "valid_until"` and type `date` is mirrored into `tool_certifications.valid_until`; a field with `"key": "evidence_url"` into `evidence_url`.

**tool_certifications** (one row per *declared* item; absence = no row)

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| tool_id | FK tools | cascade |
| certification_id | FK certifications | |
| state | enum | `pending, approved, rejected` (moderation of this claim) |
| details | JSON | Validated against `field_schema` |
| assurance | enum | `self_declared, third_party` (resolved from details) |
| evidence_url | text | Mirrored from details |
| valid_until | date | Nullable; mirrored from details |
| review_reason | text | When rejected |
| reviewed_by, reviewed_at | | |
| expiry_notified_at | datetime | T-30 email sent |
| created_at, updated_at | datetime | |

Unique (tool_id, certification_id). Index (certification_id, state, valid_until).

**interaction_events** — id, tool_id FK, kind enum `search_click|outbound_click|view`, link_kind enum nullable `website|repo|download|docs`, search_id text nullable, position int nullable, visitor_hash text, user_id nullable, day date, created_at. **Unique (tool_id, kind, visitor_hash, day)** → `INSERT OR IGNORE` gives per-day dedupe. Index (day), (tool_id, day).

**tool_daily_stats** — (tool_id, day) PK, search_clicks, outbound_clicks, views int.

**search_queries** — id ULID PK, q text (normalised, ≤ 200), locale, filters JSON, sort, results_count int, visitor_hash, created_at, updated_at. Index (created_at), (results_count, created_at).

**reports** — id, tool_id FK, reporter_id FK nullable, reporter_email text nullable (required if anonymous, except when `csam=true`), csam bool default false ("relates to child sexual abuse material" — DSA Art. 16(2)(c) lets these reporters stay anonymous; such reports jump to the top of the queue), reason enum `broken_link|dangerous_content|security_privacy|incorrect_certification|spam|copyright|illegal|other`, details text (20–2 000), status enum `open|resolved|dismissed`, handled_by FK nullable, resolution_note, created_at, resolved_at, visitor_hash.

**audit_log** — id, actor_id FK nullable (null = system), action text (e.g. `tool.approve`, `user.role_change`), target_type, target_id, details JSON, created_at. Append-only (no update/delete in code).

**email_outbox** — id, to_email, locale, template, context JSON, subject, status enum `queued|sent|failed`, attempts int, last_error, created_at, sent_at.

**site_settings** — key text PK, value JSON, updated_at, updated_by. Keys and defaults:

| Key | Default |
|---|---|
| `score.w_search_click` | 3 |
| `score.w_outbound_click` | 2 |
| `score.w_star` | 4 |
| `score.w_github` | 5 |
| `score.half_life_days` | 30 |
| `search.beta_popularity` | 1.0 |
| `limits.max_pending_per_user` | 3 |
| `reports.auto_hide_threshold` | 3 |
| `site.registration_open` | true |
| `site.banner_pt` / `site.banner_en` | "" |
| `terms.current_version` | "2026-11" |
| `tracking.daily_salt` / `tracking.salt_day` | rotated by job |

Cached in-process for 60 s.

**tool_search** — FTS5 virtual table (see §8).

## 6. Authentication, sessions, authorisation

### 6.1 Magic link

1. `POST /auth/magic-link` (email, `next`) → rate limits: 5/h per email, 20/h per IP. Always responds with the same "check your email" page.
2. Generate `token = secrets.token_urlsafe(32)`; store `sha256(token)`, `expires_at = now + 15 min`.
3. Email link `BASE_URL/auth/magic/{token}` (sent immediately via BackgroundTasks, outbox as fallback).
4. `GET /auth/magic/{token}` → shows a confirmation page with a **POST button** ("Entrar") — prevents email scanners that prefetch links from consuming the token. `POST` validates (exists, unused, not expired), marks used, finds or creates user by email, sets `email_verified_at`, creates session.

### 6.2 OAuth (GitHub, Google)

- Authlib Starlette client; state + PKCE stored in a short-lived signed cookie (`gitmgf_oauth`, 10 min).
- Callback: fetch profile + **verified** email (GitHub: `/user/emails`, pick primary verified; Google: OIDC `email_verified`).
- Linking rule: existing `oauth_accounts` match → that user. Else if verified email matches an existing user → link and log in. Else create user (prefill display_name, github_username).
- Unverified email → refuse with a message to use magic link.

### 6.3 Sessions

- Cookie `gitmgf_session` = random 32-byte token; DB stores sha256. `HttpOnly; Secure; SameSite=Lax; Path=/`; 30-day sliding expiry (`last_seen_at` updated at most once per 5 min).
- New session on every login (fixation protection). Logout deletes the row. "Sign out everywhere" deletes all rows for the user.
- After login: if `onboarded_at` is null or `terms_version` ≠ current → redirect to `/{lang}/onboarding`.
- `ADMIN_EMAILS` → set role `admin` on login (and audit-log it once).
- Suspended/deleted users: login refused; existing sessions deleted at suspension.

### 6.4 CSRF

- Cookie `gitmgf_csrf` (random, HttpOnly, SameSite=Lax) set by middleware if absent.
- Templates render the token in `<meta name="csrf-token">`, in every `<form>` as hidden `csrf_token`, and on `<body hx-headers='{"X-CSRF-Token": "…"}'>` for HTMX.
- Middleware rejects any `POST/PUT/PATCH/DELETE` whose header or form field doesn't match the cookie (constant-time compare) **and** whose `Origin`/`Referer` (when present) isn't `BASE_URL`. OAuth callbacks are GET and exempt.

### 6.5 Authorisation

`services/permissions.py` exposes pure functions used by route dependencies and templates:

```python
can_view_tool(user, tool) -> bool          # published/archived: everyone; draft/rejected: owner+mod; pending/hidden: owner+mod
can_edit_tool(user, tool) -> bool          # owner (not if deleted); admin
can_moderate(user, tool) -> bool           # role in {moderator, admin} and user.id != tool.owner_id
can_admin(user) -> bool                    # role == admin
```

Dependencies: `current_user` (optional), `require_user`, `require_moderator`, `require_admin`. Unauthorised → 404 for hidden resources (don't leak existence), 403 otherwise. Permission matrix tests are mandatory (§16).

## 7. Tool lifecycle and moderation

### 7.1 State transitions (`services/tools.py`)

| From | Action | Actor | To | Side effects |
|---|---|---|---|---|
| — | create | user | draft | slug generated |
| draft, rejected | submit | owner | pending | validate full form; check pending limit; email owner "received"; queue digest |
| pending | withdraw | owner | draft | |
| pending | approve | mod | published | `published_at`; index FTS; email; audit |
| pending | reject | mod | rejected | reason required; email; audit |
| published | edit | owner | published + revision(pending) | old content stays live |
| revision pending | approve | mod | published | apply snapshot, media swap, re-index, email, audit |
| revision pending | reject | mod | — | revision rejected, email with reason |
| published | hide | mod / auto | hidden | remove from FTS; email with statement of reasons; audit |
| hidden | unhide | mod | published | re-index; email |
| published | archive | owner | archived | removed from FTS & listings; page reachable with banner |
| archived | unarchive | owner | published | re-index (no re-review if content unchanged) |
| any | delete | owner/admin | deleted | remove from FTS; purge after 30 days (job) |

Implement as one function `transition(tool, action, actor, reason=None)` that checks an allowed-transition table and raises `InvalidTransition`. Every transition writes `audit_log` and enqueues the matching email.

Drafts and rejected tools are edited in place. Published tools are edited through `tool_revisions` (the editor loads the pending revision if one exists, else the live data).

### 7.2 Revision diff

`services/tools.diff(live: dict, proposed: dict) -> list[FieldDiff]` — scalar fields: old/new; long text: `difflib.SequenceMatcher` word-level diff rendered with `<ins>/<del>`; lists (categories, tags, platforms): added/removed chips; media: thumbnails added/removed.

### 7.3 Moderation queue

`/{lang}/mod` tabs with counts: new (`tools.status='pending'`), edits (`tool_revisions.status='pending'`), reports (`status='open'`). Sorted oldest first; show age. Moderators' own tools are listed but actions disabled.

Reason templates live in `app/i18n/labels.py` (`REJECTION_REASONS`) with PT/EN text; the moderator picks one and may add free text; the stored reason is the final rendered text in the owner's locale.

Daily 08:00 (Europe/Lisbon) digest email to moderators if queue is non-empty; immediate email on auto-hide.

## 8. Search

### 8.1 Index

```sql
CREATE VIRTUAL TABLE tool_search USING fts5(
  title_pt, title_en, summary_pt, summary_en,
  description_pt, description_en, tags, categories,
  tool_id UNINDEXED,
  tokenize = "unicode61 remove_diacritics 2",
  prefix = '2 3'
);
```

- Only `published` tools are indexed. `services/search.reindex_tool(tool_id)` deletes and re-inserts the row; called on approve, revision approve, unhide, unarchive, category rename/deactivate (for affected tools), tag merge. `python -m app.cli reindex` rebuilds everything.
- `categories` column contains both PT and EN names; `tags` contains labels; descriptions use the Markdown **source** stripped of syntax.

### 8.2 Query building

1. Normalise input: NFKC, lowercase, trim, max 200 chars.
2. Tokens = `re.findall(r"\w+", q)` (Unicode), keep first 8, drop 1-char tokens unless numeric.
3. FTS expression: each token as `"tok"*` joined by spaces (AND). No user-supplied FTS syntax ever reaches `MATCH`.
4. If 0 results → retry with `OR`; UI shows "Sem resultados exatos — a mostrar resultados parciais".

### 8.3 Ranking

```sql
SELECT t.id, bm25(tool_search, 10, 10, 5, 5, 1, 1, 4, 3) AS text_rank
FROM tool_search
JOIN tools t ON t.id = tool_search.tool_id
WHERE tool_search MATCH :expr
  AND <filters on t>
ORDER BY (text_rank - :beta * t.score_log) ASC     -- bm25 is negative; lower is better
LIMIT 20 OFFSET :offset;
```

Sorts without a query or with explicit sort: `popular` → `score DESC`; `new` → `published_at DESC`; `stars` → `stars_count DESC`; `updated` → `last_content_update_at DESC`. Tie-breaker always `id DESC`.

### 8.4 Filters

| Param | Values | SQL |
|---|---|---|
| `cat` (repeatable) | category slugs | `EXISTS (tool_categories … slug IN …)` (OR within) |
| `type` | tool_type | equality |
| `platform` (repeatable) | platforms | `EXISTS (SELECT 1 FROM json_each(t.platforms) WHERE value IN (…))` |
| `setting` | primary/hospital | `care_setting IN (:v, 'both')` |
| `oss=1` | | `is_open_source = 1` |
| `free=1` | | `pricing = 'free'` |
| `cert` (repeatable) | certification codes | **AND**: one `EXISTS` per code on `tool_certifications` with `state='approved' AND (valid_until IS NULL OR valid_until >= date('now'))` |
| `lang` | tool language | json_each |
| `sort` | relevance/popular/new/stars/updated | |
| `page` | int ≥ 1 | 20 per page, max page 50 |

All params validated through a Pydantic model; unknown values ignored.

### 8.5 UI behaviour (HTMX)

```html
<form action="/pt/search" method="get" role="search"
      hx-get="/pt/search" hx-target="#results" hx-select="#results" hx-swap="outerHTML"
      hx-push-url="true" hx-trigger="input changed delay:400ms from:#q, change from:.filter, submit">
```

- Full page on normal GET; when `HX-Request` header is present the route returns only `partials/search_results.html` (also fine with `hx-select`).
- "Mostrar mais" button: `hx-get` next page, `hx-swap="outerHTML"` replacing itself with the next cards + new button.
- Result links point to `/r/{search_id}/{tool_id}?pos={n}` (see §9).

### 8.6 Search logging

A `search_queries` row is written when a query string or filter is present. To avoid logging every keystroke: if the same `visitor_hash` has a row from the last 30 s whose `q` is a prefix of (or extends) the new `q`, **update** that row instead of inserting. Return its ULID as `search_id`.

## 9. Tracking and scoring

### 9.1 Visitor identity (no cookies)

```
visitor_hash = sha256(daily_salt + client_ip + user_agent)[:32]
```

- `daily_salt` = 32 random bytes stored in `site_settings`, replaced at 00:00 UTC (old value discarded) → hashes can't be linked across days or reversed.
- `client_ip` from `X-Forwarded-For` as set by Caddy (uvicorn `--proxy-headers --forwarded-allow-ips` limited to the Caddy container network).
- Bot filter: skip events if UA is empty or matches `/(bot|crawl|spider|slurp|preview|facebookexternalhit|curl|wget|python-requests|httpx|headless|monitor)/i`.

### 9.2 Endpoints

| Route | Logs | Redirects to |
|---|---|---|
| `GET /r/{search_id}/{tool_id}?pos=n` | `search_click` | `/{lang}/t/{slug}` (lang from referer/cookie) |
| `GET /go/{tool_id}/{link_kind}?s={search_id}` | `outbound_click` (+ `search_click` if `s` present and valid) | stored URL of that kind |
| tool page render | `view` (only for author stats) | — |

- **No open redirect**: `/go/` only redirects to a URL stored on a `published`/`archived` tool; 404 otherwise.
- Events are skipped when `user_id == tool.owner_id`.
- Insert with `INSERT OR IGNORE` on the unique key → one event per visitor/tool/kind/day.
- Redirect links carry `rel="nofollow"`; `/r/` and `/go/` are disallowed in `robots.txt`.
- Response: `302` with `Cache-Control: no-store`, `Referrer-Policy: no-referrer` for outbound.

### 9.3 Stars

`POST /t/{tool_id}/star` (HTMX) toggles, updates `stars_count`, returns `partials/star_button.html`. Rate limit 60/min/user. Owners get 403.

### 9.4 Score job (every 15 min, `jobs.recompute_scores`)

1. Aggregate `interaction_events` for today and yesterday into `tool_daily_stats` (upsert counts).
2. For each published tool:

```
H = half_life_days
decay(d) = 0.5 ** ((today - d).days / H)
usage    = Σ_{days d in last 365, d ≥ score_reset_at} (w_sc · search_clicks_d + w_oc · outbound_clicks_d) · decay(d)
score    = usage + w_star · stars_count + w_gh · log10(1 + github_stars)
score_log = ln(1 + score)
```

3. Bulk `UPDATE tools SET score, score_log`. Computed in Python (2 000 tools × 365 rows is trivial); no dependency on SQLite math functions.

Unit tests cover: decay at 0/30/60 days, dedupe, owner exclusion, bot exclusion, reset.

### 9.5 Retention (`jobs.prune`, daily 04:00)

Retention must match the Privacy Policy §9 (`content/legal/*/privacy.md`) — change both together:

- `interaction_events`, `search_queries`: 180 days
- `magic_link_tokens`: 1 day · expired `sessions`: on expiry
- sent `email_outbox`: 30 days
- `deleted` users/tools: purge after 30 days (files included)
- `reports`: delete 2 years after `resolved_at`; on account deletion set `reporter_id = NULL`, `reporter_email = NULL`
- `audit_log`: delete after 3 years; on account deletion replace `actor_id`/target user ids with a pseudonymous `deleted-user-<hash>` marker in `details`
- Caddy access logs: 14 days (`log { output file … { roll_keep_for 336h } }`)
- Backups: Litestream `retention: 720h` (30 days); file backups pruned to 30 days

## 10. GitHub sync (`jobs.sync_github`, daily 03:30)

- Parse `repo_url` with `^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$`; store owner/repo in `tool_github` on save.
- `GET https://api.github.com/repos/{owner}/{repo}` with `If-None-Match: etag`, `Authorization: Bearer GITHUB_API_TOKEN` when configured, 10 s timeout, 1 request/second.
- Store stars, forks, open_issues, pushed_at, license.spdx_id, archived, default_branch, etag, fetched_at. 404 → `last_error="not_found"` (shown to owner in My tools).
- Also run for a single tool right after approval (background task).
- Badges: *Maintained* if `pushed_at` < 365 days; *Archived* if `archived`.

## 11. Certifications and compliance badges (PRD F20)

### 11.1 Service API (`services/certifications.py`)

```python
@dataclass(frozen=True)
class Badge:
    code: str
    label: str                 # "MDR IIa"
    name: str                  # localized full name
    present: bool
    expired: bool              # declared+approved but valid_until < today
    assurance: str | None      # self_declared | third_party
    details: dict | None       # for the panel
    evidence_url: str | None

def validate_claim(cert: Certification, details: dict) -> tuple[dict, list[FieldError]]
def coherence_warnings(tool_data: dict, claims: dict[str, dict]) -> list[Warning]
def badges_for(tool_ids: list[int], lang: str) -> dict[int, list[Badge]]   # one query; core items always included
def is_present(tc: ToolCertification, today: date) -> bool                  # state == approved and (valid_until is None or valid_until >= today)
```

- `badges_for` returns, per tool: all **core** items (present or absent, ordered by `sort_order`) followed by **additional** items that are present. Cards render only the core part; the tool page renders all.
- Labels: `label_template.format(**details)` falling back to `badge_label`.
- Expired is treated as absent for display, filters and search, with tooltip "Expirado em {date}".

### 11.2 Form & validation

- Submission form section "Certificações e conformidade": one checkbox per active item (core first). Checking it reveals its fields via `hx-get="/me/cert-fields/{code}"` (also server-rendered when JS is off: all fields shown, ignored if unchecked).
- Validation by `field_schema`: required/required_if; `url` must be http(s); `nb_number` must match `^\d{4}$`; `date` ISO; `enum` in options.
- Coherence (server-side, `coherence_warnings` + hard rules):
  - MDR or IVDR checked → CE auto-checked with `legal_basis` = MDR/IVDR (author can't uncheck CE while MDR/IVDR is checked).
  - MDR class ∈ {IIa, IIb, III} or IVDR class ∈ {B, C, D} without NB number/certificate → blocking error.
  - `patient_data = server` and RGPD absent → warning (non-blocking) shown to author and on the moderator screen.
  - `tool_type = ai_prompt` or category `inteligencia-artificial` → hint suggesting the AI Act item.
- New tool / draft: claims saved as `tool_certifications` with `state=pending`.
- Published tool: **additions or changes** go into the revision snapshot (`certifications` list); **removals** are applied immediately (row deleted, audit-logged, FTS untouched).

### 11.3 Moderation

- Review screens list each claim with its details, clickable evidence links (domain shown) and a per-claim *Approve / Reject (reason)* control, default *Approve*.
- Approving the tool or revision approves all claims not individually rejected. Rejected claims are emailed to the owner with the reason; the tool can still be published without them.
- Mod checklist items for claims: evidence opens; manufacturer/product name matches; class and NB number match the certificate; validity date matches.
- Phase 2: validate NB numbers against the EU NANDO list and link EUDAMED entries automatically.

### 11.4 Rendering

Macro `cert_badge(badge, size="sm|md")` in `_macros.html`:

```html
<!-- present -->
<span class="cert cert--present" title="{{ badge.name }} — {{ _('declarado pelo autor') if badge.assurance == 'self_declared' else _('certificado por terceiros') }}">
  <svg class="cert__icon" aria-hidden="true"><use href="/static/icons/sprite.svg#check"></use></svg>
  <span>{{ badge.label }}</span>
  <span class="visually-hidden">{{ _('Com') }} {{ badge.name }}</span>
</span>
<!-- absent / expired -->
<span class="cert cert--absent" title="{{ tooltip }}">
  <span aria-hidden="true">{{ badge.label }}</span>
  <span class="visually-hidden">{{ _('Sem') }} {{ badge.name }}</span>
</span>
```

CSS (in `app.css`, no inline styles):

```css
.cert { display:inline-flex; align-items:center; gap:.25rem; padding:.1rem .45rem;
        border-radius:.35rem; font-size:.75rem; font-weight:600; letter-spacing:.02em;
        border:1px solid transparent; position:relative; }
.cert--present { background:var(--cert-present-bg); color:var(--cert-present-fg); }
.cert--absent  { color:var(--cert-absent-fg); border-color:var(--cert-absent-border);
                 background:
                   linear-gradient(to top right, transparent calc(50% - .75px),
                                   var(--cert-absent-fg) calc(50% - .75px),
                                   var(--cert-absent-fg) calc(50% + .75px),
                                   transparent calc(50% + .75px)); }
```

Tokens: `--cert-present-bg` (deep blue), `--cert-present-fg` (white), `--cert-absent-fg` (grey ≥ 3:1 against background — decorative-plus-text, real meaning carried by visually-hidden text), dark-mode variants. Badges are plain text labels — **never** the official CE mark graphic or the EU emblem (D10).

Tool page panel `partials/cert_panel.html`: present items as a definition list (label, full name, assurance, class, legal basis, NB number + certificate, valid until, evidence link `rel="nofollow noopener"`), then absent core items in muted text, then the disclaimer from PRD F20.

### 11.5 Seed (`seeds/certifications.yaml`, excerpt)

```yaml
- code: ce
  badge_label: CE
  name_pt: Marcação CE
  name_en: CE marking
  is_core: true
  assurance_default: mixed
  sort_order: 10
  field_schema:
    - {key: legal_basis, type: enum, options: [MDR, IVDR, MDD_legacy, AIMDD_legacy], required: true,
       label_pt: Base legal, label_en: Legal basis}
    - {key: manufacturer, type: text, required: true, label_pt: Fabricante, label_en: Manufacturer}
    - {key: evidence_url, type: url, required: true,
       label_pt: Declaração UE de Conformidade (URL), label_en: EU Declaration of Conformity (URL)}
    - {key: basic_udi_di, type: text, required: false, label_pt: Basic UDI-DI, label_en: Basic UDI-DI}
- code: mdr
  badge_label: MDR
  label_template: "MDR {class}"
  name_pt: Dispositivo médico — Regulamento (UE) 2017/745
  name_en: Medical device — Regulation (EU) 2017/745
  is_core: true
  assurance_default: mixed
  sort_order: 20
  field_schema:
    - {key: class, type: enum, options: [I, IIa, IIb, III], required: true, label_pt: Classe, label_en: Class,
       assurance_if: {class: {I: self_declared, "*": third_party}}}
    - {key: nb_number, type: nb_number, required_if: {class: [IIa, IIb, III]},
       label_pt: N.º do organismo notificado, label_en: Notified body number}
    - {key: certificate_no, type: text, required_if: {class: [IIa, IIb, III]},
       label_pt: N.º do certificado, label_en: Certificate number}
    - {key: valid_until, type: date, required_if: {class: [IIa, IIb, III]}, label_pt: Válido até, label_en: Valid until}
    - {key: evidence_url, type: url, required: true, label_pt: Evidência (URL), label_en: Evidence (URL)}
- code: rgpd
  badge_label: RGPD
  name_pt: Conformidade RGPD (autodeclarada)
  name_en: GDPR compliance (self-declared)
  is_core: true
  assurance_default: self_declared
  sort_order: 30
  field_schema:
    - {key: evidence_url, type: url, required: true, label_pt: Política de privacidade (URL), label_en: Privacy policy (URL)}
    - {key: data_location, type: enum, options: [no_personal_data, eu_eea, outside_eea_safeguards], required: true,
       label_pt: Localização dos dados pessoais, label_en: Personal data location}
    - {key: dpa_available, type: bool, required: false, label_pt: Acordo de tratamento de dados disponível, label_en: DPA available}
    - {key: dpo_contact, type: text, required: false, label_pt: Contacto do EPD, label_en: DPO contact}
# additional (is_core: false): ivdr, iso13485, iso27001, iso27701, iec62304, europrivacy, ai_act, a11y, spms
# inactive at launch (is_active: false): ehds
```

## 12. Media (screenshots)

- Upload ≤ 2 MB each, ≤ 5 per tool; accept PNG/JPEG/WebP by **content sniffing** (Pillow `Image.open` + `verify`), not extension. `Image.MAX_IMAGE_PIXELS = 25_000_000`.
- Re-encode: strip EXIF/metadata, convert to RGB(A), resize to max width 1600 px → WebP q=82; thumbnail 480 px. File names `uuid4().webp`.
- Stored at `/data/media/tools/{tool_id}/`, served by Caddy at `/media/…` with `Cache-Control: public, max-age=31536000, immutable` and `X-Content-Type-Options: nosniff`.
- Alt text required (PT; EN optional). Drag-free reorder via up/down buttons (HTMX).

## 13. Internationalisation

- URL prefix `/{lang}` with `lang ∈ {pt, en}` on all page routes; non-page endpoints (`/auth/*` callbacks, `/r/`, `/go/`, `/media/`, `/healthz`) have no prefix.
- `GET /` → 302 to `/pt/` or `/en/` using: `gitmgf_lang` cookie › user `locale` › `Accept-Language` (any `pt*` → pt) › `pt`.
- Language switcher links to the same path with the other prefix; sets `gitmgf_lang` cookie (1 year, functional).
- `<html lang="pt-PT">` / `lang="en"`; `<link rel="alternate" hreflang="pt-PT|en|x-default">` on every public page.
- Strings: `_()` in Python, `{% trans %}` in Jinja; `pybabel extract/update/compile` via `make i18n`. CI fails if `.po` files have untranslated or fuzzy entries.
- Locale `pt_PT` for Babel (dates like "16 de novembro de 2026").
- Listing content: helper `localized(tool, "title", lang)` returns EN if present and lang = en, else PT plus a flag `is_fallback` → template shows a "PT" pill.
- Enum labels: `app/i18n/labels.py` maps enum values → lazy gettext strings.
- Emails use the recipient's `locale`.

## 13a. Legal pages

- Source: `content/legal/{pt,en}/{terms,privacy,guidelines,disclaimer,about,contact}.md` with YAML front matter (`title`, `version`, `last_updated`). `content/legal/NOTES.md` is never published.
- Rendering: strip front matter → replace `[[KEY]]` placeholders with site settings `legal.<KEY>` (`AUTO_HIDE_THRESHOLD` from `reports.auto_hide_threshold`) → Markdown → nh3. Cached per (page, lang, settings hash).
- Startup check in `prod`: any unresolved `[[KEY]]` → refuse to start with a clear error.
- The PT version prevails; the EN pages show a banner saying so.
- Onboarding and re-acceptance store `terms_version` = front-matter `version` of `pt/terms.md`.
- Appeals (Terms §9.4) arrive by email reply or `CONTACT_EMAIL`; moderators log the outcome with `audit_log` action `appeal.decided` (who decided must differ from the original decider). A dedicated appeals UI is Phase 2.
- `/.well-known/security.txt` served from settings (`legal.SECURITY_EMAIL`, expiry 1 year).

## 14. Routes

### Public (`routers/public.py`, `routers/system.py`)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Locale redirect |
| GET | `/{lang}/` | Home |
| GET | `/{lang}/search` | Search page / partial |
| GET | `/{lang}/c/{category_slug}` | Category listing (search pre-filtered) |
| GET | `/{lang}/t/{slug}` | Tool page |
| GET/POST | `/{lang}/t/{slug}/report` | Report form (anonymous allowed) |
| GET | `/{lang}/p/{page}` | Static pages: `about, terms, privacy, disclaimer, guidelines, contact` (from `content/legal`) |
| GET | `/{lang}/feed.xml` | Atom feed of newest tools |
| GET | `/sitemap.xml`, `/robots.txt`, `/healthz` | |
| GET | `/api/tags/suggest?q=` | HTMX tag autocomplete (JSON-free: returns `<option>` list) |

### Tracking (`routers/tracking.py`)

`GET /r/{search_id}/{tool_id}` · `GET /go/{tool_id}/{link_kind}` · `POST /t/{tool_id}/star`

### Auth (`routers/auth.py`)

| Method | Path |
|---|---|
| GET | `/{lang}/login` |
| POST | `/auth/magic-link` |
| GET/POST | `/auth/magic/{token}` |
| GET | `/auth/{provider}/start` · `/auth/{provider}/callback` |
| POST | `/auth/logout` · `/auth/logout-all` |
| GET/POST | `/{lang}/onboarding` |

### Me (`routers/me.py`, login required)

| Method | Path |
|---|---|
| GET/POST | `/{lang}/me/settings` (profile, language, linked accounts) |
| POST | `/me/providers/{provider}/unlink` |
| GET | `/{lang}/me/tools` |
| GET/POST | `/{lang}/me/tools/new` |
| GET/POST | `/{lang}/me/tools/{id}/edit` |
| POST | `/me/tools/{id}/submit` · `/withdraw` · `/archive` · `/unarchive` · `/delete` |
| POST | `/me/tools/{id}/media` · `/me/media/{id}/delete` · `/me/media/{id}/move` |
| GET | `/me/cert-fields/{code}` (HTMX: detail fields for one certification) |
| GET | `/{lang}/me/tools/{id}/stats` |
| GET | `/{lang}/me/stars` |
| GET | `/me/export.json` |
| GET/POST | `/{lang}/me/delete-account` |

### Moderation (`routers/mod.py`, moderator+)

| Method | Path |
|---|---|
| GET | `/{lang}/mod?tab=new\|edits\|reports` |
| GET | `/{lang}/mod/tools/{id}` · `/{lang}/mod/revisions/{id}` · `/{lang}/mod/reports/{id}` |
| POST | `/mod/tools/{id}/approve\|reject\|hide\|unhide\|reset-score` |
| POST | `/mod/revisions/{id}/approve\|reject` |
| POST | `/mod/reports/{id}/resolve\|dismiss` |

### Admin (`routers/admin.py`, admin only)

| Method | Path |
|---|---|
| GET | `/{lang}/admin` (stats dashboard) |
| GET | `/{lang}/admin/users?q=&role=&status=` · `/{lang}/admin/users/{id}` |
| POST | `/admin/users/{id}/role` · `/suspend` · `/unsuspend` · `/delete` |
| GET/POST | `/{lang}/admin/categories` · `/{lang}/admin/categories/{id}` · POST `/admin/categories/{id}/move` |
| GET/POST | `/{lang}/admin/tags` · POST `/admin/tags/merge` |
| GET/POST | `/{lang}/admin/certifications` · `/{lang}/admin/certifications/{id}` · POST `/admin/certifications/{id}/move` |
| GET/POST | `/{lang}/admin/settings` |
| GET | `/{lang}/admin/searches` (top + zero-result, 7/30/90 days) |
| GET | `/{lang}/admin/audit?actor=&action=` |

## 15. Frontend conventions

- `base.html`: skip link, header (logo, search, language switch, user menu), flash region (`aria-live="polite"`), main, footer (disclaimer, legal links, mgfhub.com link).
- HTMX config via meta (no inline JS): `<meta name="htmx-config" content='{"allowEval":false,"includeIndicatorStyles":false,"historyCacheSize":0}'>`. No `hx-on` attributes.
- Partial responses: route checks `request.headers.get("HX-Request")`; flash messages via out-of-band swap (`hx-swap-oob="true"` on `#flash`).
- Validation errors: forms re-render with `422` and field errors; HTMX forms target the form element itself.
- CSS: design tokens as custom properties (colours, spacing, radius, font sizes), light + dark (`prefers-color-scheme`), mobile-first, focus-visible outlines, contrast ≥ 4.5:1. System font stack or self-hosted Atkinson Hyperlegible (OFL) — no external font CDNs.
- Icons: vendored SVG sprite (e.g. Lucide, ISC license) used via `<svg><use href="/static/icons/sprite.svg#icon"></use></svg>`.
- Tool card: title, summary, type icon, badges (OSS, Free, New, Maintained, Archived), **certification core row (§11)**, categories (max 3 + "+n"), stars, platforms.
- Static asset cache-busting: `?v={git_sha}`.

## 16. Security checklist

| Area | Measure |
|---|---|
| Transport | Caddy auto-TLS, HSTS `max-age=31536000; includeSubDomains`, HTTP→HTTPS, `www` → apex |
| Main CSP | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; frame-src 'none'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'` |
| Other headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` minimal, `Cross-Origin-Opener-Policy: same-origin` |
| Cookies | Secure, HttpOnly, SameSite=Lax; `__Host-` prefix in prod (`__Host-gitmgf_session`) |
| CSRF | §6.4 |
| XSS | Jinja autoescape; Markdown `html=False` + nh3 allow-list; links get `rel="nofollow ugc noopener noreferrer"` |
| URLs | Only `http`/`https`; length ≤ 500; displayed with domain; no `javascript:`/`data:` |
| Uploads | Size limits enforced by Caddy (`request_body max_size 12MB`) and app; content sniffing; re-encoding; screenshots are the only user files and are never served as uploaded |
| Redirects | `next` param must be a relative path starting with `/` and not `//`; `/go/` uses stored URLs only |
| Rate limits | magic link (5/h email, 20/h IP), reports (10/day visitor), tool create (10/day user), star (60/min), search (120/min IP), login callbacks (30/min IP) |
| Enumeration | magic-link response identical; hidden resources return 404 |
| Secrets | `.env` never committed; Docker secrets or env in prod |
| Dependencies | Exact pins (`==`) in `requirements*.txt`; Dependabot (pip ecosystem) for update PRs; `pip-audit -r requirements.txt` in CI |
| Logging | JSON logs, request id, no raw IPs, no emails at INFO level, no tokens |
| Backups | Litestream continuous (30-day retention); nightly `sqlite3 .backup` + `restic`/`rclone` of `/data/media` to EU storage, pruned to 30 days; quarterly restore test |
| Admin safety | Admins can't demote themselves if they're the last admin; all admin actions audited |

## 17. Email

- Templates in `templates/emails/{template}.{lang}.txt` + `.html` (simple, no images, no tracking).
- Enqueue → `email_outbox` row; try immediate send in `BackgroundTasks`; scheduler retries `queued/failed` every minute with exponential backoff (max 5 attempts).
- `APP_ENV=dev` → console backend (prints to log) and a dev route `/dev/emails` listing the outbox.
- Templates: `magic_link, welcome, submission_received, tool_approved, tool_rejected, revision_approved, revision_rejected, tool_hidden, tool_unhidden, cert_expiring, cert_expired, report_ack, report_outcome, mod_digest, mod_auto_hide, account_deleted`.

## 18. Scheduler jobs (`app/jobs.py`)

| Job | Schedule (Europe/Lisbon) | CLI |
|---|---|---|
| `send_outbox` | every 1 min | `python -m app.cli jobs send-outbox` |
| `recompute_scores` | every 15 min | `python -m app.cli jobs recompute-scores` |
| `rotate_salt` | 00:00 UTC | `python -m app.cli jobs rotate-salt` |
| `sync_github` | daily 03:30 | `python -m app.cli jobs sync-github [--tool ID]` |
| `prune` | daily 04:00 | `python -m app.cli jobs prune` |
| `cert_expiry` | daily 05:00 | `python -m app.cli jobs cert-expiry` (emails at T-30 days and on expiry day; audit-logs expiries) |
| `mod_digest` | daily 08:00 | `python -m app.cli jobs mod-digest` |
| heartbeat | every 5 min | pings `HEALTHCHECK_PING_URL` |

Other CLI: `python -m app.cli create-admin EMAIL`, `python -m app.cli seed categories`, `python -m app.cli seed certifications`, `python -m app.cli seed demo` (dev only: 30 fake tools, users, events), `python -m app.cli reindex`, `python -m app.cli check-config`.

## 19. Testing

| Suite | Must cover |
|---|---|
| `test_permissions.py` | Full PRD role matrix (parametrised visitor/user/owner/mod/admin × each route) |
| `test_tool_lifecycle.py` | Every allowed transition; every forbidden transition raises; revisions keep live content; pending limit |
| `test_auth.py` | Magic link single-use/expiry/prefetch-safe; OAuth linking by verified email (respx-mocked); suspended login; session rotation; ADMIN_EMAILS |
| `test_csrf.py` | Missing/invalid token rejected; HTMX header accepted |
| `test_search.py` | Accent-insensitivity, prefix, PT/EN fields, filters, OR fallback, FTS injection strings (`"`, `*`, `NEAR`, `-`) don't error, ranking blends popularity |
| `test_tracking_scoring.py` | Dedupe per day, owner/bot exclusion, decay maths, reset, open-redirect protection |
| `test_media.py` | Non-image rejected, EXIF stripped, size limits |
| `test_i18n.py` | Locale redirect, hreflang present, PT fallback pill, no untranslated strings in templates (`pybabel` check) |
| `test_gdpr.py` | Export contains all user data; deletion unpublishes tools, removes stars (counts updated), anonymises reports, purge job removes files |
| `test_certifications.py` | Field-schema validation per item (required, `required_if`, NB number regex, URL); MDR/IVDR auto-enable CE; class ≠ I without NB blocks submit; present only when approved and not expired (time-machine across `valid_until`); core items always rendered (absent = slashed); additional items hidden when absent; `cert` filter AND semantics; removal on published tool is immediate, additions go through revision; per-claim reject; aria-labels present |
| `test_reports.py` | Anonymous report requires email (unless `csam`) + passes honeypot; auto-hide at threshold |
| `test_legal.py` | Every `[[KEY]]` placeholder in `content/legal/` has a value in prod config; front matter `version` equals `terms.current_version`; retention job matches Privacy §9 table |

Coverage target ≥ 85 % for `app/services`. CI (GitHub Actions): ruff, mypy, pytest, `pybabel compile --check`, `pip-audit`, Docker build.

## 20. Deployment

### 20.1 Docker

- `Dockerfile`: `python:3.12-slim`, `pip install --no-cache-dir -r requirements.txt` (copy `requirements.txt` before the source for layer caching), non-root user, `pybabel compile`, entrypoint runs `alembic upgrade head` then `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips="*"` (only reachable from the Docker network).
- `docker-compose.yml` (dev): `app` with `--reload`, mounted source, console email, SQLite in `./data`.
- `deploy/docker-compose.prod.yml`: services `caddy`, `app`, `scheduler` (`python -m app.scheduler`), `litestream` (`litestream replicate`); volumes `data:/data`, `caddy_data`, `caddy_config`; `restart: unless-stopped`; healthchecks.

### 20.2 Caddyfile (sketch)

```caddy
{
  email admin@gitmgf.com
}

www.gitmgf.com {
  redir https://gitmgf.com{uri} permanent
}

gitmgf.com {
  encode zstd gzip
  request_body {
    max_size 12MB
  }
  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Content-Type-Options "nosniff"
    -Server
  }
  handle_path /media/* {
    root * /data/media
    header Cache-Control "public, max-age=31536000, immutable"
    file_server
  }
  handle {
    # /static/* is served by the app (StaticFiles) with long cache + ?v= cache-busting
    reverse_proxy app:8000
  }
}

```

(Main-site CSP and other app-specific headers are set by FastAPI middleware so they can vary per route.)

### 20.3 Hosting & operations

- VPS in the EU (e.g. Hetzner Falkenstein/Helsinki), Ubuntu 24.04 LTS, 2 vCPU / 4 GB, firewall 22/80/443, SSH keys only, unattended-upgrades.
- Object storage in the EU for Litestream + file backups (Hetzner Object Storage, Scaleway, Backblaze EU).
- CI/CD: on tag `v*` → build image → push to GHCR → SSH deploy `docker compose pull && docker compose up -d`; migrations run in the app entrypoint.
- Monitoring: external uptime check on `/healthz` (checks DB read + disk free > 10 %), scheduler heartbeat, Caddy access logs rotated, optional error tracking (self-hosted GlitchTip or Sentry EU region).
- DNS: `gitmgf.com`, `www.gitmgf.com` → VPS; CAA record for Let's Encrypt; SPF/DKIM/DMARC for the email provider.

## 21. Implementation plan for Claude Code

Work milestone by milestone. Each milestone ends with: tests green, ruff/mypy clean, `docs/DECISIONS.md` updated, a short demo note in `docs/CHANGELOG.md`.

| Milestone | Tasks | Definition of done |
|---|---|---|
| **M0 Foundation** | venv + `requirements.txt` / `requirements-dev.txt` + Makefile; settings; db + pragmas; Alembic baseline; base layout + CSS tokens; i18n plumbing (`/{lang}` prefix, switcher, Babel); static pages from Markdown; `/healthz`; Dockerfile + dev compose; CI | `docker compose up` → `/pt/` and `/en/` render; CI passes |
| **M1 Auth** | users/sessions/oauth/magic tables; magic link flow; GitHub + Google OAuth; CSRF; onboarding; settings page; roles + permission helpers; `create-admin`; console email + outbox | `test_auth`, `test_csrf`, `test_permissions` (auth parts) pass |
| **M2 Tools** | taxonomy models + seed; certification catalogue + seed; tool model + form (all PRD fields incl. certification section with conditional fields via HTMX); drafts; slug; Markdown render; media upload; tool page; my tools; lifecycle service (create/submit/withdraw/archive/delete) | `test_tool_lifecycle` (owner parts), `test_media` pass |
| **M3 Moderation & Admin** | mod queue; approve/reject/hide/unhide; revisions + diff (incl. certification changes); per-claim certification approve/reject; reason templates; emails; audit log; admin users/categories/tags/certifications/settings | Full lifecycle end-to-end; audit entries for every action |
| **M4 Search & Browse** | FTS table + reindex hooks; query builder; filters/sort (incl. `cert`); HTMX live search; home page; category pages; search logging | `test_search` passes; < 300 ms with `seed demo` ×100 |
| **M5 Scoring** | `/r/` and `/go/`; visitor hash + salt rotation; events; stars; daily stats; score job; GitHub sync; scheduler container; my-tools stats | `test_tracking_scoring` passes; scores visible change after job |
| **M6 Trust & Compliance** | reports (anonymous + logged-in), auto-hide; certification expiry job + emails; legal page content; GDPR export/delete + purge; sitemap, hreflang, OpenGraph, Atom feed | `test_reports`, `test_gdpr`, `test_i18n`, `test_certifications` pass |
| **M7 Hardening & Launch** | security headers middleware; rate limits; prod compose + Caddy + Litestream; backup/restore runbook (`docs/RUNBOOK.md`); accessibility pass (axe); seed real categories; load test | Restore drill succeeded; Lighthouse a11y ≥ 95; checklist §16 ticked |

## 22. Seeds

`seeds/categories.yaml` (excerpt — full list in PRD F6):

```yaml
- slug: internato
  name_pt: Internato
  name_en: Residency
  is_specialty: false
  sort_order: 10
- slug: burocracia
  name_pt: Burocracia e documentação
  name_en: Paperwork & documentation
  is_specialty: false
  sort_order: 20
- slug: gestao-clinica
  name_pt: Gestão clínica
  name_en: Clinical management
  is_specialty: false
  sort_order: 30
- slug: medicina-geral-familiar
  name_pt: Medicina Geral e Familiar
  name_en: General Practice / Family Medicine
  is_specialty: true
  sort_order: 200
- slug: cardiologia
  name_pt: Cardiologia
  name_en: Cardiology
  is_specialty: true
  sort_order: 210
- slug: hematologia
  name_pt: Hematologia
  name_en: Haematology
  is_specialty: true
  sort_order: 220
```

## 23. Decisions log (initial)

| # | Decision | Reason |
|---|---|---|
| D1 | SQLite + WAL + Litestream instead of PostgreSQL | MVP scale, single VPS, zero-ops backups; migration path to Postgres via SQLAlchemy |
| D2 | Sync FastAPI handlers | SQLite driver is sync; simpler code; threadpool sufficient |
| D3 | No cookies for tracking; daily-salted hash | GDPR/ePrivacy: avoids consent banner |
| D4 | No hosting of tools — listings and outbound links only (v0.2) | Removes the biggest security risk (running untrusted user code) and regulatory exposure (MDR "making available"); simpler ops and storage |
| D5 | Edits to published tools go through revisions | Moderation without downtime of the live page |
| D6 | Flat category list with `is_specialty` flag only for the profile dropdown | Keeps product decision (flat, multi-select) while allowing a specialty picker |
| D7 | Magic-link confirmation POST step | Email security scanners prefetch links |
| D8 | No Node toolchain | Fewer moving parts; HTMX + plain CSS enough |
| D9 | Certification catalogue is data (`certifications.field_schema`), not code; "present" computed at read time from `state` + `valid_until` | New schemes without deploys; expiry needs no state mutation, so filters can't drift |
| D10 | Badges are text labels, never the official CE mark graphic or EU emblem | Those symbols have legal format/usage rules; gitmgf must not appear to affix or endorse conformity |
