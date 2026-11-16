# Changelog

## 0.2.0 — 2026-11-16 · Password login, invite-only registration

- Email + password sign-in (scrypt, rate-limited); registration by invite link (Administração → Convites, `cli invite`), with an option to open it to everyone.
- Admin-issued one-time set-password links; `cli create-admin` prints one; password change in Definições.
- Removed magic links and GitHub/Google OAuth. SMTP is now optional; notifications wait in Administração → Emails.
- Terms and Privacy (PT/EN) updated accordingly. See D26.

## 0.1.0 — 2026-11-16 · MVP (M0–M7)

- **M0 Foundation** — FastAPI + Jinja2 + HTMX, SQLite (WAL) with Alembic, `/pt` and `/en` routing with hreflang, design system from the mockup (light/dark, mobile-first), SVG logo, legal pages from Markdown, `/healthz`.
- **M1 Auth** — magic link (prefetch-safe POST confirmation), GitHub and Google OAuth with account linking by verified email, server-side sessions, CSRF, onboarding with versioned Terms acceptance, `ADMIN_EMAILS` bootstrap.
- **M2 Tools** — full submission form, drafts, revisions for published tools, screenshots (re-encoded WebP), certification claims with field schemas and coherence rules, tool page with trust signals.
- **M3 Moderation & admin** — queue (new, edits, reports), field-level diffs, per-claim decisions, reason templates in the owner's language with DSA statement of reasons, users/roles/suspension, categories, tags (merge), certification catalogue, settings, audit log.
- **M4 Search** — FTS5 accent-insensitive prefix search over PT/EN text, tags and categories; filters (incl. certifications, AND semantics); popularity-blended ranking; live HTMX results that also work without JS. ~3 ms per query at 2 000 tools.
- **M5 Scoring** — cookie-less daily-salted visitor hash, `/r/` and `/go/` tracking redirects (no open redirect), stars, daily aggregates, decayed score, GitHub sync, author stats, scheduler.
- **M6 Trust & compliance** — anonymous/logged-in reports with honeypot + timing, auto-hide at threshold, certification expiry emails, GDPR export/deletion and retention purge, sitemap, Atom feed, security.txt, guidelines/disclaimer/about/contact pages.
- **M7 Hardening** — strict CSP and security headers, rate limits, prod startup guard, Docker image, prod compose with Caddy + Litestream, VPS setup and deploy scripts, CI, runbook.
