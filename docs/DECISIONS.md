# Decisions log

D1–D10 are in TECH_SPEC §23. Deviations and implementation choices made while building the MVP:

| # | Decision | Reason |
|---|---|---|
| D11 | gettext msgids are the European Portuguese strings; only an `en` catalogue exists (`app/locales/en`). PT renders msgids directly. | PT-PT is the primary language and copy is written in context in the templates (TECH_SPEC §11.4 already uses PT msgids). `tests/test_i18n.py` fails on any untranslated or fuzzy EN entry. |
| D12 | OAuth uses Authlib's PKCE/token primitives with a **sync** httpx client, not Authlib's async Starlette client. State + PKCE verifier live in the signed `gitmgf_oauth` cookie (itsdangerous, 10 min). | Keeps every route handler synchronous (D2) and avoids Authlib's deprecated httpx integration. |
| D13 | CSRF is enforced by a global FastAPI dependency (`deps.csrf_protect`) rather than body-reading middleware; middleware only issues the cookie. | The dependency shares Starlette's cached parsed form with the handler, so the body is read once (multipart included). Behaviour matches TECH_SPEC §6.4. |
| D14 | Post-redirect messages use `?flash=<key>` mapped to translated strings (`labels.FLASH`). | No flash cookie, so the cookie table in Privacy §6 stays exact. |
| D15 | Emails are rendered when queued and stored in `email_outbox.body_text/body_html`; one gettext template per email (`templates/emails/<name>.txt`, HTML generated from it) instead of `.{lang}.txt` files. Added `next_attempt_at` for backoff. | The sender needs no template context; one template per message keeps PT/EN in the same catalogue. |
| D16 | Certification detail fields are server-rendered for every catalogue item and shown/hidden by `app.js`; there is no `/me/cert-fields/{code}` endpoint. | Same no-JS behaviour as the spec (all fields shown, ignored if unchecked) without a round trip per toggle. |
| D17 | `reports.locale` stores the reporter's language. | Acknowledgement and outcome emails go out in the language the report was filed in. |
| D18 | Legal placeholders resolve from site setting `legal.<KEY>`, falling back to env `LEGAL_<KEY>`. | A first prod deploy can satisfy the startup check from `.env` before any admin exists. |
| D19 | "My tools" and the editor live in `routers/editor.py`; `routers/me.py` keeps settings, stars and GDPR. | `me.py` was getting too large. |
| D20 | The logo is an SVG recreated from the supplied raster PDF; the wordmark is Roboto Slab (Apache-2.0) glyphs converted to paths. No font file is shipped. | Crisp at any size, dark-mode variant, and no external or self-hosted font needed. |
| D21 | FTS rows use `rowid = tools.id` (the `tool_id` column is kept). | Join on rowid is the fastest FTS5 lookup. |
