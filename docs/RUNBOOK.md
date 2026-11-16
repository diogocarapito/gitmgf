# gitmgf — Operations runbook

Production runs as one Docker Compose stack on a single EU VPS (TECH_SPEC §1, §20):

| Service | What it does |
|---|---|
| `caddy` | TLS (Let's Encrypt), HTTP→HTTPS, `www`→apex, gzip/zstd, serves `/media/*` (screenshots), proxies the rest to `app` |
| `app` | FastAPI + uvicorn (2 workers). Runs migrations and first-time seeds on start |
| `scheduler` | APScheduler jobs: email outbox (1 min, only when SMTP is set), scores (15 min), salt rotation, GitHub sync, retention, certification expiry, moderator digest, heartbeat |
| `litestream` | Continuous SQLite replication to S3-compatible storage (profile `backup`) |

All state lives in the `gitmgf_data` volume: `/data/gitmgf.db` (+ WAL) and `/data/media/`.

**Accounts (MVP, D26):** email + password sign-in, invite-only registration, admin-issued reset links. No OAuth, no magic links. SMTP is optional.

---

## 1. First deployment

### 1.1 What you need

| | Required | Notes |
|---|---|---|
| **VPS** in the EU | yes | Ubuntu 24.04, 2 vCPU / 4 GB (e.g. Hetzner CX22/CPX21, Falkenstein or Helsinki) |
| **DNS** | yes | `A`/`AAAA` for `gitmgf.com` and `www.gitmgf.com` → the VPS. Optional CAA record allowing `letsencrypt.org` |
| **Object storage** in the EU | recommended | For Litestream backups (e.g. Hetzner Object Storage): a private bucket and an access key |
| **Transactional email** | optional | Brevo or Scaleway TEM. Without it, notifications stay in the outbox (Administração → Emails) |

Sign processor agreements (DPAs) with the hosting and storage providers (and the email provider, if you add one) — content/legal/NOTES.md §2.

### 1.2 Provision the server (once, as root)

Read the script first. Use your laptop's public key (`cat ~/.ssh/id_ed25519.pub`):

```bash
ssh root@gitmgf.com
curl -fsSL https://raw.githubusercontent.com/diogocarapito/gitmgf/main/deploy/setup-vps.sh -o setup-vps.sh
less setup-vps.sh
bash setup-vps.sh deploy "ssh-ed25519 AAAA… you@laptop"
exit
```

It installs Docker, enables `ufw` (22/80/443 only), unattended security upgrades and fail2ban, and creates a `deploy` user with key-only SSH.

### 1.3 Configure and start (as `deploy`)

```bash
ssh deploy@gitmgf.com
git clone https://github.com/diogocarapito/gitmgf.git && cd gitmgf
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # paste as SECRET_KEY
nano .env
./deploy/deploy.sh
```

Fill in `.env`:

| Variable | Value |
|---|---|
| `SECRET_KEY` | the 64 hex characters printed above |
| `ADMIN_EMAILS` | your email (may register without an invite; promoted to admin) |
| `DOMAIN`, `BASE_URL` | `gitmgf.com`, `https://gitmgf.com` |
| `ACME_EMAIL` | your email (Let's Encrypt notices) |
| `LEGAL_*` | at least `CONTROLLER_NAME`, `CONTROLLER_TAX_ID`, `CONTROLLER_ADDRESS`; review the prefilled ones |
| `SMTP_HOST` | **leave empty** unless you have an email provider |
| `GITHUB_CLIENT_*`, `GOOGLE_CLIENT_*` | not used any more — delete these lines if present |

`deploy.sh` builds the image, runs `check-config` (fails on an unsafe `SECRET_KEY`, a non-https `BASE_URL`, or unfilled legal placeholders), then starts the stack. Caddy obtains the HTTPS certificate on first start (DNS must already point at the server). The backup profile is enabled automatically once `LITESTREAM_BUCKET` is set.

### 1.4 First admin

Open `https://gitmgf.com/pt/register` and create an account with the address in `ADMIN_EMAILS`: it needs no invite and is promoted to admin on sign-in (audit-logged). Complete onboarding, then check **Administração → Definições** (legal values, banner, limits).

Alternative from the server (prints a one-time link, valid 48 h, to set the password):

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env run --rm app cli create-admin you@example.org
```

### 1.5 Smoke test

- `curl -fsS https://gitmgf.com/healthz` → `{"status":"ok",…}`
- Create an invite (Administração → Convites), open it in a private window, register a second account and sign in.
- Make that account a moderator (Administração → Utilizadores), submit a tool with a screenshot from your account, approve it from the moderator account, and find it in search.
- `https://gitmgf.com/.well-known/security.txt` shows the security contact.

---

## 2. Accounts and access

### Invites

- **Create:** Administração → Convites → *Novo convite*. Options: lock to one email, number of uses (e.g. 20 for a beta group), validity in days. The link is shown **once** — copy it and send it by message or personal email.
- **From the server:** `dc run --rm app cli invite --uses 20 --days 30 --note "Beta MGF"` (add `--email someone@example.org` to lock it).
- **Revoke:** Administração → Convites → *Revogar*.
- **Open registration to everyone:** Administração → Definições → *Registos abertos*. Invites are then optional.

### Publishing your own tool (admins, no second moderator yet)

Moderators can't approve their own tools on the site. While you are the only moderator, submit the tool for review as usual, then on the server:

```bash
dc run --rm app cli approve-own-tool <slug-or-id> --as you@example.org
```

It publishes the pending tool, approves its certification claims, indexes it for search, syncs GitHub, and records `self_approved` in the audit log (D27). Once you have a second moderator, use the normal review instead.

### Forgotten passwords

There is no self-service reset without email. When someone asks:

1. Confirm it is really them (e.g. by a channel you already know).
2. Administração → Utilizadores → the user → *Gerar ligação para definir palavra-passe*.
3. Send them the link. It works once, for 48 hours; generating a new one invalidates the previous one. Setting the password signs out their other sessions.

Users change their own password in **Definições → Palavra-passe**.

### Roles and suspensions

- Administração → Utilizadores → the user → change role (user / moderator / admin). The last admin can't be demoted.
- *Suspender* (with a reason) blocks sign-in and ends all sessions; *Levantar suspensão* restores access.

### Notifications without email

Approval, rejection, hide and report-outcome messages are still generated. Without SMTP they are kept in **Administração → Emails** (pruned after 30 days) and never sent. Authors see their tool status and the moderation reason in **As minhas ferramentas**; for important decisions (e.g. hiding a tool), contact the author directly.

To turn email on later: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` in `.env`, verify the domain with SPF, DKIM and DMARC, and redeploy. Queued messages from the last 30 days will then be sent.

---

## 3. Everyday operations

Shorthand used below:

```bash
alias dc='docker compose -f deploy/docker-compose.prod.yml --env-file .env --profile backup'
```

| Task | Command |
|---|---|
| Status | `dc ps` |
| Logs | `dc logs -f app` · `dc logs -f scheduler` · `dc exec caddy tail -f /var/log/caddy/access.log` |
| Deploy a new version | `./deploy/deploy.sh --pull` |
| Roll back | `git checkout <previous-sha> && ./deploy/deploy.sh` (migrations are forward-only; see §6) |
| Run a job now | `dc run --rm app cli jobs recompute-scores` (also `send-outbox`, `sync-github`, `prune`, `cert-expiry`, `mod-digest`) |
| Create an invite | `dc run --rm app cli invite --uses 5` |
| Change an account's email | `dc run --rm app cli change-email old@example.org new@example.org` (then update `ADMIN_EMAILS` if it was listed) |
| Set a password for someone | `dc run --rm app cli create-admin <email>` for admins; for others, the button on their admin page |
| Rebuild search index | `dc run --rm app cli reindex` |
| Change a setting | `dc run --rm app cli settings set reports.auto_hide_threshold 3 --json` |
| SQLite shell (read-only) | `dc exec app sqlite3 -readonly /data/gitmgf.db` |
| Check config | `dc run --rm app cli check-config` |

### Changing legal texts

1. Edit `content/legal/pt/*.md` (prevailing) and the `en/` translations.
2. If users must accept again, bump `version` in `pt/terms.md` front matter **and** `terms.current_version` (Administração → Definições). Everyone is sent through onboarding on next sign-in.
3. Keep Privacy §9 (retention) in sync with `app/services/gdpr.py` — `tests/test_legal.py` checks it.

### Translations

`make i18n` extracts strings, merges them into `app/locales/en/LC_MESSAGES/messages.po` and compiles. Fill new `msgstr` entries (msgids are the PT-PT text). `tests/test_i18n.py` fails on any untranslated or fuzzy entry.

---

## 4. Backups and restore

### What is backed up

| Data | How | Retention |
|---|---|---|
| SQLite DB | Litestream streams WAL changes to the bucket (RPO ≈ seconds), daily snapshot | 30 days (`retention: 720h`) |
| Screenshots `/data/media` | Nightly `rclone sync` (below) | 30 days of versions in the bucket (lifecycle rule) |

Nightly media sync (crontab of `deploy`, 03:00):

```cron
0 3 * * * docker run --rm -v gitmgf_data:/data:ro -e RCLONE_CONFIG_S3_TYPE=s3 -e RCLONE_CONFIG_S3_PROVIDER=Other -e RCLONE_CONFIG_S3_ENDPOINT=$ENDPOINT -e RCLONE_CONFIG_S3_ACCESS_KEY_ID=$KEY -e RCLONE_CONFIG_S3_SECRET_ACCESS_KEY=$SECRET rclone/rclone:1.68 sync /data/media s3:$BUCKET/media
```

Add a bucket lifecycle rule that expires non-current versions after 30 days (Privacy §9: backups ≤ 30 days).

### Restore drill (quarterly; required before launch)

```bash
dc stop app scheduler litestream
# 1. Restore the database from the replica into the volume
dc run --rm --no-deps --entrypoint litestream litestream restore -if-replica-exists -o /data/gitmgf.restored.db /data/gitmgf.db
dc run --rm --no-deps app sh -c 'sqlite3 /data/gitmgf.restored.db "PRAGMA integrity_check;"'   # expect: ok
dc run --rm --no-deps app sh -c 'mv /data/gitmgf.db /data/gitmgf.broken.db; rm -f /data/gitmgf.db-wal /data/gitmgf.db-shm; mv /data/gitmgf.restored.db /data/gitmgf.db'
# 2. Restore media (if needed): rclone sync s3:$BUCKET/media /data/media
dc up -d
dc run --rm app cli reindex
```

Record the date, duration (RTO target ≤ 4 h) and any issues in `docs/CHANGELOG.md`.

---

## 5. Monitoring

- **Uptime**: external check on `https://gitmgf.com/healthz` every minute (Uptime Kuma, Better Stack, Healthchecks.io). Returns 503 when the DB is unreadable or disk free < 10 %.
- **Scheduler heartbeat**: set `HEALTHCHECK_PING_URL` (e.g. a Healthchecks.io check with a 10-minute grace period).
- **Sign-in abuse**: repeated failures are rate-limited (10 per email and 30 per IP per 15 minutes); watch `dc logs app | grep "POST /pt/login"` for spikes.
- **Outbox**: Administração → Emails. With SMTP configured, `failed` rows retry with backoff up to 5 times.
- **Moderation backlog**: Administração → Estatísticas shows the oldest queued item (target < 72 h). The daily moderator digest is only emailed when SMTP is set — otherwise check the queue yourself.
- **Disk**: `df -h` and `docker system df`; prune old images with `docker image prune`.

---

## 6. Migrations

- Create: `alembic revision --autogenerate -m "…"` (check the result; FTS5 and expression indexes are written by hand). `migrations/env.py` turns SQLite foreign keys off while migrating so table rebuilds never cascade-delete.
- Migrations run automatically when `app` starts. Before a risky migration, take a consistent copy: `dc exec app sqlite3 /data/gitmgf.db ".backup /data/pre-migration.db"`.
- To roll back code across a migration, restore that copy (SQLite migrations here are forward-only).

---

## 7. Incidents

| Situation | Action |
|---|---|
| Dangerous tool reported | It auto-hides at 3 open dangerous/security reports. Otherwise hide it from its moderation page (the reason is recorded for the author), then close the reports. |
| Patient data published | Hide immediately; contact the author to remove it; delete affected screenshots via a revision or by deleting the tool. Assess whether a GDPR breach notification is needed (72 h). |
| Account compromise | Administração → Utilizadores → suspend (ends all sessions). After confirming identity, lift the suspension and send a set-password link. |
| Password database exposure | Passwords are salted scrypt hashes, but treat it as a breach: send everyone a set-password link (or clear `password_hash` and do it on request), assess GDPR notification. |
| Leaked `SECRET_KEY` | Rotate it in `.env` and redeploy (it signs form stamps). To sign everyone out: `dc exec app sqlite3 /data/gitmgf.db "DELETE FROM sessions;"`. |
| Authority order / DSA notice | Handle via `CONTACT_EMAIL`; log the decision with `audit_log` action `appeal.decided` or a moderation action. |
| Appeal (Terms §8.4) | A moderator who did not take the original decision reviews it within a reasonable time; record the outcome in the audit log. |

---

## 8. Launch checklist

- [ ] DNS, TLS, `www` redirect working; HSTS header present
- [ ] `check-config` passes; all legal placeholders reviewed by a lawyer (content/legal/NOTES.md §2)
- [ ] First admin registered; 2 moderators invited and onboarded (PRD Q5)
- [ ] Invite flow and set-password link tested end to end
- [ ] Litestream replicating; media sync cron installed; **restore drill done**
- [ ] Uptime check and scheduler heartbeat alerting
- [ ] 15–20 seed tools from known authors published (PRD §11)
- [ ] Lighthouse accessibility ≥ 95 on home, search, tool page and editor
- [ ] Closed beta with ~20 clinicians (invite-only), then decide whether to open registration
- [ ] Later: email (SMTP + SPF/DKIM/DMARC), then TOTP two-factor for moderators and admins
