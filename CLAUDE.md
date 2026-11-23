# CLAUDE.md — gitmgf

gitmgf.com: a bilingual (PT-PT first, EN) portal where clinicians publish and discover tools they built for clinical work, focused on primary care (MGF) and residency (Internato).

**Read first:** `PRD.md` (what & why) and `TECH_SPEC.md` (how). Work milestone by milestone (TECH_SPEC §21). Don't start a milestone until the previous one meets its Definition of Done.

## Stack (do not change without logging a decision in `docs/DECISIONS.md`)

Python 3.12 · pip + requirements.txt · FastAPI (sync handlers) · Jinja2 · HTMX 2 (vendored) · SQLAlchemy 2.0 + Alembic · SQLite (WAL) · Babel · Authlib · Pillow · nh3 · APScheduler · Typer · pytest · ruff · Docker Compose · Caddy · Litestream.

No Node, no frontend framework, no CDN, no external fonts, no analytics scripts.

## Commands

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt         # install (runtime + dev)
alembic upgrade head                         # migrate
python -m app.cli seed categories            # seed taxonomy
python -m app.cli seed certifications        # seed certification catalogue
python -m app.cli seed demo                  # dev data
uvicorn app.main:app --reload                # run dev server
pytest -q                                    # tests
ruff check . && ruff format --check .
mypy app/services
make i18n                                    # pybabel extract + update + compile
docker compose up --build                    # full dev stack
```

Dependencies: runtime packages go in `requirements.txt`, test/tooling in `requirements-dev.txt`, always pinned with `==`. Never use uv, poetry or pipenv. Never add a package without pinning it in the right file.

## Conventions

- **Layers:** routers are thin (parse input, call a service, render). Business rules live in `app/services/`. Templates contain no business logic beyond display conditions.
- **State changes to tools only via `services.tools.transition()`.** Never set `tool.status` directly elsewhere.
- **Permissions only via `services/permissions.py`.** Hidden resources return 404, not 403.
- **Every mutating action** by a moderator/admin writes `audit_log` and, if it affects an owner, enqueues an email with the reason.
- **FTS index** must be updated through `services.search.reindex_tool()` / `remove_tool()` — never write `tool_search` elsewhere.
- **Never pass user input to FTS `MATCH` directly**; use the query builder.
- **Certification badges:** presence is decided only by `services.certifications.is_present()` / `badges_for()` (approved and not expired). Never render the official CE mark graphic or EU emblem — text labels only.
- **No inline `<script>` or `style=`** (strict CSP). No `hx-on`. JS goes in `static/js/app.js`.
- **Every page works without JS**; HTMX is progressive enhancement. Routes return a partial when `HX-Request` is set.
- **All user-facing strings are translatable** (`_()` / `{% trans %}`), both PT and EN filled in before a milestone is done.
- **Editorial texts and emails live in `content/<page>/<name>.md` + `<name>_en.md`** (D37, guide in `content/README.md`), read with `site_text("page/name")` in templates; short UI strings (buttons, labels, errors) stay in gettext.
- Timestamps UTC in DB; display in Europe/Lisbon with Babel.
- Type hints everywhere; `Mapped[]` models; Pydantic models for forms.
- Small commits per feature; conventional commit messages (`feat:`, `fix:`, `test:`, `docs:`).
- Write tests alongside features; permission matrix and state machine tests are non-negotiable.

## European Portuguese (PT-PT) — mandatory wording

Use PT-PT, never PT-BR. Preferred terms:

| Use (PT-PT) | Avoid (PT-BR) | EN |
|---|---|---|
| utilizador | usuário | user |
| ecrã | tela | screen |
| ficheiro | arquivo | file |
| registar / registo | cadastrar / cadastro | register / sign-up |
| iniciar sessão / terminar sessão | fazer login / logout | sign in / sign out |
| palavra-passe | senha | password |
| equipa | time | team |
| contacto | contato | contact |
| telemóvel | celular | mobile phone |
| transferir | baixar | download |
| partilhar | compartilhar | share |
| definições | configurações | settings |
| pesquisar / pesquisa | buscar / busca | search |
| guardar | salvar | save |
| submeter ferramenta | enviar ferramenta | submit tool |
| moderação, moderador/a | — | moderation, moderator |
| denunciar / reportar problema | — | report a problem |
| utente | paciente (in SNS context prefer "utente") | patient |
| interno/a, Internato | residente | resident, residency |
| Medicina Geral e Familiar (MGF) | — | General Practice / Family Medicine |
| cuidados de saúde primários | atenção primária | primary care |

Tone: clear, friendly, professional; address the reader as **"tu"** (D39): "Submete a tua ferramenta", "Indica um email válido", "Já tens conta?". Never "você" or formal third-person imperatives ("Submeta a sua…"). Buttons and labels stay in the infinitive ("Pesquisar ferramentas"). Legal pages (`content/legal/`) keep their own register.

## Security reminders

- gitmgf is a listing repository only: never add features that upload, store, serve or execute tools or user code. Screenshots are the only user files.
- Uploaded images are always re-encoded; never serve the original bytes.
- `/go/` redirects only to URLs stored on published/archived tools.
- `next` parameters must be relative paths (`/…`, not `//…`).
- Never log raw IPs, tokens or full emails.

## When unsure

Prefer the simplest implementation that satisfies the PRD acceptance criteria. If a requirement is ambiguous, pick the PRD default listed in §13 "Open questions", implement it, and note it in `docs/DECISIONS.md`.
