# gitmgf — Operations runbook

Production runs as one Docker Compose stack on a single EU VPS (TECH_SPEC §1, §20):

| Service | What it does |
|---|---|
| `caddy` | TLS (Let's Encrypt), HTTP→HTTPS, `www`→apex, gzip/zstd, serves `/media/*` (screenshots), proxies the rest to `app` |
| `app` | FastAPI + uvicorn (2 workers). Runs migrations and first-time seeds on start |
| `scheduler` | APScheduler jobs: email outbox (1 min), scores (15 min), salt rotation, GitHub sync, retention, certification expiry, moderator digest, heartbeat |
| `litestream` | Continuous SQLite replication to S3-compatible storage (profile `backup`) |

All state lives in the `gitmgf_data` volume: `/data/gitmgf.db` (+ WAL) and `/data/media/`.

---

## 1. First deployment

### 1.1 Accounts and DNS

1. **VPS** in the EU, Ubuntu 24.04, 2 vCPU / 4 GB (e.g. Hetzner CX22/CPX21 in Falkenstein or Helsinki).
2. **Object storage** in the EU for backups (e.g. Hetzner Object Storage): create a private bucket and an access key.
3. **Transactional email** (EU): Brevo or Scaleway TEM. Verify the domain and add the **SPF, DKIM and DMARC** records they give you.
4. **DNS**: `A`/`AAAA` records for `gitmgf.com` and `www.gitmgf.com` → the VPS. Add a CAA record allowing `letsencrypt.org`.
5. Optional: GitHub and Google OAuth apps (callbacks `https://gitmgf.com/auth/github/callback` and `https://gitmgf.com/auth/google/callback`).
6. Sign processor agreements (DPAs) with the hosting, email and storage providers (content/legal/NOTES.md §2).

### 1.2 Provision the server

As root on the new VPS (read the script first):

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/gitmgf/main/deploy/setup-vps.sh -o setup-vps.sh
less setup-vps.sh
bash setup-vps.sh deploy "ssh-ed25519 AAAA… you@laptop"
```

It installs Docker, enables `ufw` (22/80/443 only), unattended security upgrades, fail2ban, and key-only SSH for the `deploy` user.

### 1.3 Configure and start

```bash
ssh deploy@gitmgf.com
git clone https://github.com/<you>/gitmgf.git && cd gitmgf
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # paste as SECRET_KEY
nano .env                                                   # fill everything (see comments)
../deploy/deploy.sh/deploy/deploy.sh
```

`deploy.sh` builds the image, runs `check-config` (fails on unsafe secrets, a non-https `BASE_URL`, missing SMTP, or unfilled legal placeholders), then starts the stack. The backup profile is enabled automatically once `LITESTREAM_BUCKET` is set.

### 1.4 First admin

Either put your email in `ADMIN_EMAILS` (promoted on sign-in, audit-logged), or:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env run --rm app cli create-admin you@example.org
```

Then sign in at `https://gitmgf.com/pt/login`, complete onboarding, and check **Administração → Definições** (legal values, banner, limits).

### 1.5 Smoke test

- `curl -fsS https://gitmgf.com/healthz` → `{"status":"ok",…}`
- Request a magic link and confirm the email arrives (check SPF/DKIM pass in the headers).
- Submit a tool with a screenshot, approve it from a second (moderator) account, and find it in search.
- `https://gitmgf.com/.well-known/security.txt` shows the security contact.

---

## 2. Everyday operations

Shorthand used below:

```bash
alias dc='docker compose -f deploy/docker-compose.prod.yml --env-file .env --profile backup'
```

| Task | Command |
|---|---|
| Status | `dc ps` |
| Logs | `dc logs -f app` · `dc logs -f scheduler` · `dc exec caddy tail -f /var/log/caddy/access.log` |
| Deploy a new version | `./deploy/deploy.sh --pull` |
| Roll back | `git checkout <previous-sha> && ./deploy/deploy.sh` (migrations are forward-only; see §5) |
| Run a job now | `dc run --rm app cli jobs recompute-scores` (also `send-outbox`, `sync-github`, `prune`, `cert-expiry`, `mod-digest`) |
| Too many emails for the provider's plan | Administração → Emails → *Tipos de email*: switch off optional types (D42); account access emails stay on |
| Remove past visits/clicks by moderators and admins (D40) | `dc run --rm app cli purge-staff-events` (rebuilds daily stats and scores; safe to repeat) |
| Rebuild search index | `dc run --rm app cli reindex` |
| Change a setting | `dc run --rm app cli settings set reports.auto_hide_threshold 3 --json` |
| SQLite shell (read-only) | `dc exec app sqlite3 -readonly /data/gitmgf.db` |
| Check config | `dc run --rm app cli check-config` |

### Changing legal texts

1. Edit `content/legal/*.md` (prevailing) and the `*_en.md` translations next to them (`content/README.md`).
2. If users must accept again, bump `version` in `content/legal/terms.md` front matter **and** `terms.current_version` (Administração → Definições). Everyone is sent through onboarding on next sign-in.
3. Keep Privacy §9 (retention) in sync with `app/services/gdpr.py` — `tests/test_legal.py` checks it.

### Translations

`make i18n` extracts strings, merges them into `app/locales/en/LC_MESSAGES/messages.po` and compiles. Fill new `msgstr` entries (msgids are the PT-PT text). `tests/test_i18n.py` fails on any untranslated or fuzzy entry.

---

## 3. Backups and restore

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

### Restore drill (quarterly; required before launch — M7 definition of done)

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

Record the date, duration (RTO target ≤ 4 h) and any issues in the changelog.

---

## 4. Monitoring

- **Uptime**: external check on `https://gitmgf.com/healthz` every minute (Uptime Kuma, Better Stack, Healthchecks.io). Returns 503 when the DB is unreadable or disk free < 10 %.
- **Scheduler heartbeat**: set `HEALTHCHECK_PING_URL` (e.g. a Healthchecks.io check with a 10-minute grace period).
- **Email**: `dc exec app sqlite3 -readonly /data/gitmgf.db "select status, count(*) from email_outbox group by 1"` — `failed` rows retry with backoff up to 5 times.
- **Moderation backlog**: Administração → Estatísticas shows the oldest queued item (target < 72 h).
- **Disk**: `df -h` and `docker system df`; prune old images with `docker image prune`.

---

## 5. Migrations

- Create: `alembic revision --autogenerate -m "…"` (check the result; FTS5 and expression indexes are written by hand).
- Migrations run automatically when `app` starts. Before a risky migration, take a consistent copy: `dc exec app sqlite3 /data/gitmgf.db ".backup /data/pre-migration.db"`.
- To roll back code across a migration, restore that copy (SQLite migrations here are forward-only).

---

## 6. Incidents

| Situation | Action |
|---|---|
| Dangerous tool reported | It auto-hides at 3 open dangerous/security reports. Otherwise hide it from its moderation page (the author receives the statement of reasons), then close the reports. |
| Patient data published | Hide immediately; ask the author to remove it; delete affected screenshots via a revision or by deleting the tool. Assess whether a GDPR breach notification is needed (72 h). |
| Account compromise | Administração → Utilizadores → suspend (kills all sessions). Ask the user to secure their email/OAuth account. |
| Leaked secret | Rotate `SECRET_KEY` (signs out everyone and invalidates OAuth state), SMTP and OAuth secrets; redeploy. |
| Authority order / DSA notice | Handle via `CONTACT_EMAIL`; log the decision with `audit_log` action `appeal.decided` or a moderation action. |
| Appeal (Terms §8.4) | A moderator who did not take the original decision reviews it within a reasonable time; record the outcome in the audit log. |

---

## 7. Launch checklist (M7)

- [ ] DNS, TLS, `www` redirect working; HSTS header present
- [ ] SPF, DKIM, DMARC pass for transactional email
- [ ] `check-config` passes; all legal placeholders reviewed by a lawyer (content/legal/NOTES.md §2)
- [ ] Litestream replicating; media sync cron installed; **restore drill done**
- [ ] Uptime check and scheduler heartbeat alerting
- [ ] First admin and 2 moderators onboarded (PRD Q5)
- [ ] 15–20 seed tools from known authors published (PRD §11)
- [ ] Lighthouse accessibility ≥ 95 on home, search, tool page and editor
- [ ] Closed beta with ~20 clinicians, then public launch
