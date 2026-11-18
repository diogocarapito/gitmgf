# Changelog

## 0.4.0 — 2026-11-19 · Blog, cards with screenshots, support email

- Blog at `/blog` (Markdown in `content/blog/`), first article on building gitmgf with Claude Pro and Claude Code.
- Tool cards show the first screenshot; the form explains it. Certification badges share the badge line on cards and tool pages. Categorias first in the Explorar filters.
- Optional public support email on tools, shown as "Contactar suporte" next to "Reportar problema".
- Reports: "Material desadequado" reason replaces the CSAM checkbox (D31); "Material de abuso sexual de crianças" is a reason that clears and blocks the email field, so those reports stay anonymous (D34).
- "Sugerir melhoria": suggestions and feature requests to authors by email and in a new Notificações page with an unread bell (D32).
- Profile photos and public profile pages at `/u/<handle>` with the person's published tools (D33).
- Estatísticas area for moderators and admins: overview, searches and per-category statistics (D35).

## 0.3.0 — 2026-11-18 · Open registration with email codes

- Registration is open (with SMTP): name, email, profession, specialty, password and terms in one form, then a 6-digit code by email; the account is created only after the code. No separate onboarding step.
- *Esqueceu-se da palavra-passe?* now emails a 6-digit code (15 min) and the new password is set on the same screen.
- Taken emails and unknown accounts behave the same as free/known ones; owners get an "account exists" email.
- `cli emails [--retry]` shows the outbox with SMTP errors; `create-user --send` reports real delivery failures.
- Terms §3.2 and Privacy updated (PT/EN). See D30.

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
