# gitmgf — Product Requirements Document (PRD)

| | |
|---|---|
| **Product** | gitmgf — <https://gitmgf.com> |
| **Owner** | Diogo (product owner, admin) |
| **Status** | Draft v0.2 — MVP scope (v0.2: hosted calculators removed; gitmgf is a listing repository only) |
| **Date** | 2026-11-16 |
| **Companion doc** | `TECH_SPEC.md` (how), `CLAUDE.md` (build conventions) |

---

## 1. Summary

gitmgf is a bilingual (European Portuguese first, English second) portal where clinicians and anyone building tools for clinicians **publish, discover and reuse** the digital tools they made: desktop apps, web apps, online calculators, spreadsheet templates, scripts, browser extensions and AI prompts. Its focus is **primary care (MGF / Medicina Geral e Familiar) and residency (Internato)**, without excluding hospital care.

Think "a curated, searchable app shelf for clinician-made tools", where:

- every tool has a clean page (what it does, who it's for, where to get it, license, data handling);
- gitmgf is a **repository of listings only**: it never hosts, runs or distributes the tools themselves — it keeps a descriptive page, screenshots and links to where the author publishes the tool (GitHub/GitLab, website, app store, cloud drive);
- discovery is driven by **search + a popularity score** built from real use (clicks after search, outbound clicks, stars, GitHub activity), with recency decay;
- every submission is **reviewed by a moderator** before it goes public.

## 2. Problem

- Portuguese clinicians build many useful tools (Excel templates for indicators, Internato portfolio helpers, scores, scripts for SClinic / MIM@UF exports, calculators), but they are scattered across WhatsApp groups, personal GitHubs, Google Drive links and word of mouth.
- People who need a tool can't find it; people who built one get no visibility, feedback or credit.
- No place answers "is this tool still maintained, open source, and what does it do with patient data?"
- Existing international directories (MDCalc, app stores, GitHub topics) are not in PT-PT and don't reflect Portuguese workflows (SNS, ULS, Internato de MGF, bureaucracy such as CIT, atestados, SICO, PEM, RSE).

## 3. Goals and non-goals

### 3.1 Goals (MVP)

1. **G1 — Publish:** anyone can create an account and submit a tool in under 10 minutes.
2. **G2 — Discover:** a visitor finds a relevant tool with one search or one category click, in PT or EN, with or without accents.
3. **G3 — Trust:** every public tool has passed moderation and shows license, maintenance signals, care setting and patient-data handling.
4. **G4 — Rank by real use:** popular, recently-used tools surface first; gaming is hard.
5. **G5 — Compliance by design:** GDPR, EU Digital Services Act (hosting-service duties), no tracking cookies, clear disclaimers.

### 3.2 Non-goals (MVP)

- Not a code host (no git hosting despite the name; repos stay on GitHub/GitLab/Codeberg).
- **No hosting of tools of any kind** — no installers, zips, spreadsheets, HTML calculators or web apps are uploaded to or served by gitmgf. Listings link to where the author publishes the tool. (Screenshots are the only files users upload.)
- No comments, public author profiles, blog/"explorations" posts, collections, or messaging (Phase 2, §12).
- No clinical validation of tools. Moderation checks guideline compliance, not clinical correctness.
- No payments, ads, or paid placement.
- No native mobile app (responsive web only).
- No public API (Phase 2).

## 4. Users and personas

| Persona | Description | Main jobs |
|---|---|---|
| **Interna/o de MGF** (resident) — consumer **and** maker | Young, tech-friendly, under time pressure; uses tools daily and often builds them too (Internato portfolio helpers, exam study aids, indicator spreadsheets, scripts, AI prompts, calculators made during the residency) | Find tools fast; star favourites; **publish and maintain their own tools**, get visibility and credit early in their career (e.g. for the curriculum); see how colleagues use them |
| **Médica/o especialista "maker"** | Specialist who builds tools as a side hobby (Python, Excel, JS); often more established, mentors residents | Publish, update, see usage of their tools; get credit |
| **Curious clinician (consumer)** | Not technical; wants a calculator or bureaucracy helper that works | Search in PT, open tool, trust signals |
| **Non-clinician builder** | Engineer, nurse, pharmacist, student building for clinicians | Publish; needs clear guidelines |
| **International visitor** | Uses the EN interface | Browse and find tools usable outside Portugal |
| **Moderator** | Trusted volunteer clinician | Review submissions and edits; handle reports |
| **Admin** | Diogo + 1–2 others | Manage users, roles, categories, settings; see stats |

Anyone can register and publish (no professional verification in MVP). Users self-declare a profession; this is shown on the tool page as context, not as a credential.

## 5. Scope overview (MVP feature list)

| # | Feature | Priority |
|---|---|---|
| F1 | Accounts: magic link email, GitHub OAuth, Google OAuth | Must |
| F2 | Onboarding: name, profession, specialty, terms acceptance | Must |
| F3 | Tool submission & editing (draft → review → published) | Must |
| F4 | Tool page (rich listing, screenshots, links, trust signals) | Must |
| F5 | *(Removed in v0.2 — gitmgf does not host tools; ID kept so other references stay stable)* | — |
| F6 | Categories (flat, multi-select) + free tags | Must |
| F7 | Search with filters and sort, accent-insensitive, PT/EN | Must |
| F8 | Popularity score (clicks after search, outbound clicks, stars, GitHub stars, recency decay) | Must |
| F9 | Stars (one per user per tool) | Must |
| F10 | Moderation queue (new tools, edits, reports) | Must |
| F11 | Report / flag a tool (DSA notice-and-action) | Must |
| F12 | Admin: users & roles, categories, settings, stats, audit log | Must |
| F13 | Bilingual UI (PT-PT default, EN); bilingual listing content (PT required, EN optional) | Must |
| F14 | GitHub repo sync (stars, last commit, license, archived) | Must |
| F15 | "My tools" dashboard with per-tool usage stats | Should |
| F16 | Legal pages: Terms, Privacy, Disclaimer, Submission guidelines, About, Contact | Must |
| F17 | GDPR self-service: export my data, delete my account | Must |
| F18 | SEO: sitemap, hreflang, OpenGraph, RSS of new tools | Should |
| F19 | Transactional emails (login, submission received/approved/rejected, tool hidden) | Must |
| F20 | Certification & compliance badges (CE, MDR, RGPD, ISO, AI Act…) — coloured when present, grey slashed when absent | Must |

## 6. Functional requirements

### F1 — Accounts and authentication

- Sign-in methods: **magic link by email**, **GitHub OAuth**, **Google OAuth**. No passwords.
- One account per email. If an OAuth login returns a *verified* email matching an existing account, the provider is linked to that account. Otherwise a new account is created.
- Users can link/unlink providers in settings (must keep at least one working method; email magic link always works).
- Magic link: valid 15 minutes, single use. Requests are rate-limited. The response is always "if the email exists/is valid, we sent a link" (no account enumeration).
- Sessions last 30 days (sliding). "Sign out everywhere" available.
- Suspended users cannot sign in; they see a neutral message.

**Acceptance:** a new user can sign up with each of the 3 methods; an existing email user who later uses GitHub with the same verified email ends up in the same account.

### F2 — Onboarding and profile (private settings)

After first sign-in the user completes:

- Display name (required), handle (auto-suggested, unique, used in URLs later).
- Profession (required, enum): Médico/a especialista, Médico/a interno/a, Enfermeiro/a, Farmacêutico/a, Estudante de Medicina, Outro profissional de saúde, Engenheiro/a / Developer, Outro.
- Specialty (optional, from categories marked as specialties — see F6 note) and workplace (optional free text, e.g. "USF X, ULS Y").
- GitHub username (optional, prefilled from GitHub OAuth).
- Preferred interface language.
- Acceptance of Terms + Submission Guidelines (versioned; re-acceptance required when version changes).

Public exposure in MVP: only **display name, profession, specialty and (optional) GitHub link** appear on the user's tool pages. No public profile page in MVP.

### F3 — Tool submission and lifecycle

**Tool fields**

| Field | Req. | Notes |
|---|---|---|
| Title PT | ✔ | ≤ 80 chars |
| Title EN | | ≤ 80 chars |
| Short summary PT | ✔ | ≤ 200 chars, shown on cards/search |
| Short summary EN | | |
| Description PT | ✔ | Markdown (sanitised), ≤ 20 000 chars |
| Description EN | | |
| Tool type | ✔ | Web app · Online calculator · Desktop app · Mobile app · Spreadsheet/template · Script/library · Browser extension · AI prompt/assistant · Dataset · Other |
| Categories | ✔ | 1–5 from flat list (F6) |
| Tags | | 0–10 free tags (lowercase, normalised) |
| Care setting | ✔ | Primary care · Hospital care · Both · Not applicable |
| Platforms | ✔ | Multi: Web, Windows, macOS, Linux, Android, iOS, Excel, Google Sheets, LibreOffice, Other |
| Tool languages | ✔ | Multi: PT, EN, ES, FR, Other |
| Links | ≥1 | Website/app URL · Repository URL · Download/releases URL · Documentation URL (http/https only). |
| License | ✔ | SPDX picker (MIT, GPL-3.0, AGPL-3.0, Apache-2.0, BSD-3-Clause, MPL-2.0, CC-BY-4.0, CC-BY-SA-4.0, …) or "Proprietary / closed source" or "Unknown" |
| Pricing | ✔ | Free · Freemium · Paid |
| Patient data handling | ✔ | Does not process patient data · Processes data locally only · Sends data to a server · Unknown |
| Certifications & compliance | ✔ (section) | Per-certification declaration with evidence — see **F20**. Default is "not present" for every item; the author switches on only what the tool really has |
| Intended use | ✔ | 1–3 sentences: who should use it, for what, limitations |
| Version / last release | | free text |
| Screenshots | | 0–5 images (PNG/JPG/WebP ≤ 2 MB each), alt text required |
| Declarations | ✔ | Checkboxes: "I'm the author or authorised to publish"; "Screenshots and content contain no patient-identifiable data"; "I accept that gitmgf does not validate clinical correctness" |

**Derived badges:** *Open source* (OSI license AND public repo URL), *Free*, *Maintained* (GitHub push < 12 months), *Archived* (GitHub archived), *New* (published < 30 days). Certification badges (CE, MDR, RGPD, …) are a separate badge row described in F20.

**Lifecycle (state machine)**

```
draft ──submit──▶ pending ──approve──▶ published ──hide (mod)──▶ hidden
  ▲                  │                    │  ▲                     │
  └──── edit ◀── rejected ◀──reject───────┘  └──── unhide (mod) ───┘
                                    published ──archive (owner)──▶ archived (unlisted, page still reachable with banner)
any state ──delete (owner/admin)──▶ deleted (soft delete, purged after 30 days)
```

- **Edits to a published tool** create a *pending revision*. The published version stays live and unchanged until a moderator approves the revision. Owner sees "Alteração pendente de revisão".
- Rejection and hiding always include a **written reason** (template + free text), emailed to the owner (DSA "statement of reasons").
- Owner can withdraw a pending submission back to draft.
- Max 3 pending submissions per user at a time (anti-spam).

**Acceptance:** a draft is invisible to the public; a pending tool is visible only to owner + moderators; an approved tool appears in search within 1 minute; editing a published tool does not change the public page until approval.

### F4 — Tool page

Content: title, summary, badges, primary CTA, screenshots gallery, description (Markdown), **certification badge row + "Conformidade e certificações" panel (F20)**, metadata panel (type, platforms, languages, care setting, license, pricing, patient data, version, categories, tags), author block (name, profession, specialty, GitHub link), GitHub panel if linked (stars, last commit, open issues, archived), dates (published, last updated), star button + count, "Report a problem" link, disclaimer footer.

Primary CTA priority: **Open app** (website) › **Download** › **View code**. All of them leave gitmgf; the tool page says so ("Vai abrir um site externo"). All outbound links go through the tracking redirect (F8).

If the current UI is EN and the listing has no EN text, show PT text with a small "PT" language label.

### F6 — Categories and tags

- **One flat list**, multi-select (1–5 per tool), managed by admins (create, rename, reorder, deactivate; bilingual name + description).
- Initial seed (PT / EN):

  *Purpose:* Internato / Residency · Burocracia e documentação / Paperwork & documentation · Gestão clínica / Clinical management · Indicadores e dados / Indicators & data · Apoio à decisão clínica / Clinical decision support · Calculadoras e scores / Calculators & scores · Prescrição e terapêutica / Prescribing & therapeutics · Rastreios e prevenção / Screening & prevention · Educação para a saúde / Patient education · Ensino e formação / Teaching & training · Investigação / Research · Produtividade / Productivity · Inteligência artificial / Artificial intelligence · Telemedicina / Telehealth · Outros / Other

  *Specialties:* Medicina Geral e Familiar · Medicina Interna · Cardiologia · Hematologia · Endocrinologia e Diabetes · Pneumologia · Gastrenterologia · Nefrologia · Neurologia · Psiquiatria e Saúde Mental · Pediatria · Ginecologia e Obstetrícia · Saúde Materna e Planeamento Familiar · Dermatologia · Reumatologia · Doenças Infecciosas · Oncologia · Geriatria · Cuidados Paliativos · Saúde Pública · Medicina do Trabalho · Urgência e Emergência · Ortopedia · Oftalmologia · Otorrinolaringologia · Urologia · Medicina Física e de Reabilitação

  (The list is flat for tools; the UI may visually show purposes before specialties via `sort_order`. Specialty entries carry an internal flag only so the profile "specialty" dropdown can list them.)
- **Tags:** free, normalised (lowercase, trimmed, accents kept for display but matched accent-insensitively), max 10 per tool. Admins can merge/delete tags.

### F7 — Search and browse

- Single search box on every page; results update as you type (debounced) and work without JavaScript (plain GET form).
- Searches title, summary, description, tags and categories in **both languages**, accent-insensitive ("calculo" finds "cálculo"), prefix matching ("diab" finds "diabetes").
- Filters: categories (multi), tool type, platform, care setting, license (open source only toggle), pricing (free only toggle), tool language, **certifications** (multi: e.g. "CE", "MDR", "RGPD" — only tools where the item is *present and valid*).
- Sort: **Relevance** (default with a query: text match blended with popularity) · **Popular** (default without a query) · **Newest** · **Most starred** · **Recently updated**.
- Filter/sort state lives in the URL (shareable, back-button safe).
- Category pages = search pre-filtered by category.
- Home: search box, popular tools, newest tools, category grid.
- Zero-result searches are logged for admins (to see unmet needs).

**Acceptance:** "escala de risco cardiovascular" and "SCORE2" both return a SCORE2 calculator tagged appropriately; results return in < 300 ms server time with 5 000 tools.

### F8 — Popularity score

Signals (all anonymous-friendly, no cookies):

| Signal | Weight | Decay |
|---|---|---|
| Click on a tool from search results ("click after search") | 3 | yes |
| Outbound click (open app/download/repo/docs) from anywhere | 2 | yes |
| Star by a logged-in user | 4 | no (counts while starred) |
| GitHub stars of linked repo | 5 × log10(1 + stars) | n/a |

- Recency decay: exponential, **half-life 30 days** (an interaction 30 days old counts half).
- Anti-gaming: the same visitor counts once per tool per signal per day; the owner's own clicks don't count; known bots are ignored; moderators can reset a tool's score.
- Weights and half-life are admin-tunable settings.
- Score recomputed every 15 minutes; search relevance blends text match with log(score).
- Authors see their own tool's 30/90-day counts (search clicks, outbound clicks, views, stars) in "My tools".

### F9 — Stars

Logged-in users can star/unstar a tool (one per user per tool); "My stars" list in the user menu. Star count shown publicly. Owners can't star their own tools.

### F10 — Moderation

- Queue tabs: **New submissions**, **Edits (revisions)**, **Reports**.
- Review screen shows all fields, links (clickable, with domain shown), screenshots, and for revisions a **field-level diff** vs the published version.
- Actions: Approve · Reject (reason required) · Request changes (= reject with reason, tool returns to draft) · Hide/Unhide published tool · Reset score.
- Reason templates (PT/EN): incomplete information; broken/unsafe link; patient data visible; duplicates existing tool; not related to healthcare; guideline violation; misleading clinical claims; copyright/license problem.
- All moderation actions are written to the audit log and emailed to the owner.
- Moderators cannot moderate their own tools.

Moderation checklist (shown on review screen): links work and point to what is described; no patient-identifiable data in text/screenshots; intended use and data handling declared plausibly; license coherent with repo; links point to the author's own publication place (not to file-sharing mirrors or URL shorteners); no ads/spam; **every certification marked present has evidence that opens and matches the tool, manufacturer and class (F20); a tool that sends patient data to a server and has no RGPD declaration gets a "changes requested" unless the author explains why.**

### F11 — Reports (notice and action)

- "Report a problem" on every tool page, open to **anyone** (DSA notices can come from any person): logged-in users submit directly; anonymous visitors must give an email (except for reports about child sexual abuse material, which may stay anonymous) and pass a simple anti-spam challenge (honeypot + time check, no third-party CAPTCHA).
- Reasons: Broken link · Incorrect or dangerous clinical content · Security or privacy concern · Incorrect certification claim · Spam · Copyright / license violation · Illegal content · Other. Free-text details required (≥ 20 chars).
- Reporter gets an acknowledgement email and an outcome email (resolved/dismissed).
- Tools with ≥ 3 open "dangerous content" or "security" reports are automatically hidden pending review, and moderators are emailed.

### F12 — Administration

- **Users:** search, view, change role (user / moderator / admin), suspend/unsuspend (with reason), delete.
- **Categories & tags:** CRUD, reorder, merge tags.
- **Certification catalogue (F20):** create/edit/deactivate items, PT/EN names and help text, short badge label, which detail fields are required, whether the badge is always shown (core row) or only when present, order.
- **Settings:** scoring weights and half-life, max pending per user, auto-hide threshold, site banner message (PT/EN), registration open/closed.
- **Stats:** totals (users, tools by status), signups/submissions per week, top tools, top searches, **zero-result searches**, moderation backlog age.
- **Audit log:** every role change, moderation decision, suspension, deletion, settings change.
- Bootstrap: first admin created by CLI command or `ADMIN_EMAILS` env var.

### Roles and permissions

| Action | Visitor | User | Moderator | Admin |
|---|:-:|:-:|:-:|:-:|
| Browse, search, open tools | ✔ | ✔ | ✔ | ✔ |
| Star, report | | ✔ | ✔ | ✔ |
| Submit / edit / archive / delete own tools | | ✔ | ✔ | ✔ |
| See pending tools of others, review queue | | | ✔ | ✔ |
| Approve / reject / hide / reset score | | | ✔ (not own) | ✔ (not own) |
| Handle reports | | | ✔ | ✔ |
| Manage users, roles, suspensions | | | | ✔ |
| Manage categories, tags, settings | | | | ✔ |
| View stats & audit log | | | stats only | ✔ |

### F13 — Languages

- UI fully translated: **PT-PT (default)** and **EN**. Language in URL prefix (`/pt/…`, `/en/…`) with `hreflang` alternates; language switcher keeps the current page.
- First visit to `/` redirects based on `Accept-Language` (pt* → `/pt/`, else `/en/`); choice remembered in a functional cookie and in user settings.
- Strictly **European Portuguese** wording and spelling (utilizador, ecrã, ficheiro, registar, equipa, contacto, telemóvel). No PT-BR.
- Listing content: PT required, EN optional (see F3/F4).
- Emails sent in the user's preferred language.

### F14 — GitHub sync

For repo URLs on github.com: nightly fetch of stars, forks, open issues, last push date, license (SPDX), archived flag, default branch. Shown on the tool page and used for badges and score. Failures don't break the page. Other forges (GitLab, Codeberg) are links only in MVP.

### F15 — "My tools"

List of own tools with status, pending revision indicator, rejection reason, 30/90-day stats, quick actions (edit, submit, withdraw, archive, delete).

### F16 — Legal and trust pages

- **Termos de utilização / Terms**, **Política de privacidade / Privacy**, **Aviso legal / Disclaimer**, **Normas de submissão / Submission guidelines**, **Sobre / About**, **Contacto / Contact** (DSA single point of contact).
- Persistent footer disclaimer: tools are published by their authors; gitmgf does not validate clinical correctness; tools do not replace clinical judgement; check local protocols.
- Privacy by default: no analytics cookies, no third-party trackers, no external fonts/CDNs. Only essential cookies (session, CSRF, language) → no cookie banner required; a short cookie notice in the privacy policy.

### F17 — GDPR self-service

- **Export my data** (JSON: profile, linked providers, tools, revisions, stars, reports filed).
- **Delete my account**: confirmation step; tools are unpublished immediately and purged with the account after 30 days (see Q4); stars removed (counts updated); reports kept but anonymised.
- Search and click logs use a daily-rotating salted hash of IP+User-Agent, never raw IPs; raw events retained 180 days, then only daily aggregates.

### F18 — SEO and sharing

`sitemap.xml` (published tools + categories, both languages), `robots.txt`, canonical + hreflang, OpenGraph/Twitter cards per tool (first screenshot or generated default), RSS/Atom feed of newly published tools per language. Server-rendered HTML for every public page.

### F19 — Emails

Magic link · Welcome · Submission received · Approved · Rejected / changes requested (with reason) · Revision approved/rejected · Tool hidden (statement of reasons) / unhidden · Report acknowledgement and outcome · Moderators: new item in queue (daily digest) · Account deletion confirmation. Plain, bilingual templates; no tracking pixels.

### F20 — Certification and compliance badges

Clinicians need to see at a glance whether a tool carries European certifications (CE, MDR, RGPD…). Every tool shows a **badge row** where each item is either:

| State | Look | Meaning |
|---|---|---|
| **Present** | Coloured badge, small check icon, label with detail (e.g. `MDR IIa`) | Author declared it, gave the required evidence, and a moderator approved it; not expired |
| **Absent** | Grey badge with a **diagonal slash** and muted text | Not declared, rejected by moderation, or expired |

Not colour-only: the slash, an icon and an accessible label ("Com marcação CE" / "Sem marcação CE") carry the meaning. Tooltips stay neutral, e.g. *"O autor não declarou marcação CE para esta ferramenta."* — "absent" means "not declared", not "required and missing".

**Catalogue (admin-managed, seed below).** *Core* items are always shown (present or slashed) on cards and tool pages; *additional* items are shown only when present.

| Badge | Name (PT / EN) | Row | Type | Required details when present |
|---|---|---|---|---|
| `CE` | Marcação CE / CE marking | Core | Third-party or self-declared (depends on class) | Legal basis (MDR · IVDR · MDD/AIMDD legacy), manufacturer name, EU Declaration of Conformity URL; optional Basic UDI-DI, EUDAMED link |
| `MDR` | Dispositivo médico — Regulamento (UE) 2017/745 / Medical device — MDR | Core | Self-declared (class I) or notified body (IIa, IIb, III) | Class (I · IIa · IIb · III); notified body number (4 digits) and certificate number if class ≠ I; valid until; evidence URL |
| `RGPD` | Conformidade RGPD (autodeclarada) / GDPR compliance (self-declared) | Core | Self-declared | Privacy policy URL; where personal data is stored (no personal data stored · EU/EEA · outside EEA with safeguards); DPA available on request (yes/no); optional DPO contact |
| `IVDR` | Dispositivo médico para diagnóstico in vitro — Reg. (UE) 2017/746 / IVD — IVDR | Additional | Self-declared (A) or notified body (B–D) | Class (A · B · C · D); NB number + certificate if ≠ A; valid until; evidence URL |
| `ISO 13485` | Sistema de gestão da qualidade (dispositivos médicos) / QMS for medical devices | Additional | Third-party | Certification body, certificate number, valid until, evidence URL |
| `ISO 27001` | Segurança da informação / Information security (ISO/IEC 27001) | Additional | Third-party | As above |
| `ISO 27701` | Gestão da privacidade / Privacy information management (ISO/IEC 27701) | Additional | Third-party | As above |
| `IEC 62304` | Ciclo de vida de software de dispositivo médico / Medical device software lifecycle | Additional | Self-declared | Evidence URL or statement |
| `Europrivacy` | Selo europeu de proteção de dados / European Data Protection Seal (GDPR Art. 42) | Additional | Third-party | Certificate number, valid until, registry URL |
| `AI Act` | Conformidade com o Regulamento da IA (UE) 2024/1689 / EU AI Act conformity | Additional | Self-declared or third-party | Risk category declared by provider (high-risk · transparency obligations · minimal), evidence URL |
| `Acessível` | Acessibilidade EN 301 549 / WCAG 2.1 AA / Accessibility | Additional | Self-declared | Accessibility statement URL |
| `SPMS` | Certificação SPMS (ex.: software de prescrição) / SPMS certification (Portugal) | Additional | Third-party | Certificate/reference, evidence URL |
| `EHDS` | Sistema RSE conforme o EHDS — Reg. (UE) 2025/327 / EHDS EHR system | Additional, **inactive at launch** | Third-party / self-declared | To define when obligations apply |

Admins can add items (e.g. national schemes), edit texts, change core/additional, and deactivate items without a deploy.

**Rules**

- Every item defaults to *absent*. The submission form has a "Certificações e conformidade" section with one toggle per active item; turning one on reveals its detail fields.
- "Present" requires all required fields; URLs must open (moderator checks), and the notified body number must be 4 digits.
- Coherence helpers: switching on MDR or IVDR switches on CE with the matching legal basis; MDR class ≠ I without a notified body number blocks submission; "sends patient data to a server" without RGPD shows a warning to the author and moderator; AI-type tools or the "Inteligência artificial" category show a hint about the AI Act badge.
- Certification changes on a published tool always go through a **revision** (moderator approval); removing a certification is applied immediately (it can only make the listing more conservative).
- **Expiry:** items with *valid until* turn back to *absent* (tooltip "Expirado em …") the day after expiry; the author is emailed 30 days before and on the day.
- Moderators can reject a single certification claim while approving the rest of the tool, with a reason.
- Anyone can report a false claim (report reason "Certificação incorreta / Incorrect certification claim").

**Where it appears**

- **Tool card:** compact core row (CE · MDR · RGPD), present or slashed.
- **Tool page:** core row + any present additional badges under the title; a **"Conformidade e certificações"** panel listing every present item with its details (class, notified body, certificate, validity, legal basis, "autodeclarado" vs "certificado por organismo notificado n.º XXXX") and evidence links, followed by the absent core items.
- **Search filters:** "Certificações" multi-select (present and not expired only).
- **Moderator review:** checklist per claimed item with the evidence links.
- Panel disclaimer: *"Informação declarada pelo autor. A gitmgf verifica a existência das evidências indicadas, mas não certifica nem garante a conformidade da ferramenta."*

**Acceptance:** a tool with MDR class IIa (NB 0123, valid until 2028-05-01) shows coloured `CE` and `MDR IIa`, slashed `RGPD`, and appears under the CE and MDR filters; on 2028-05-02 the MDR badge turns slashed with "Expirado em 01/05/2028" and the tool leaves the MDR filter.

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | p95 server time < 300 ms for public pages; HTML+CSS+JS < 100 KB (excl. images); works on 3G |
| Scale (MVP) | 5 000 users, 2 000 tools, 50 req/s peak on a 2 vCPU / 4 GB VPS |
| Availability | 99.5 % monthly; daily backups, point-in-time DB replication; RPO ≤ 1 min, RTO ≤ 4 h |
| Accessibility | WCAG 2.1 AA; keyboard navigable; works without JS for browse/search/read |
| Devices | Mobile-first responsive; latest 2 versions of major browsers |
| Security | OWASP ASVS L1 baseline; strict CSP; CSRF protection; rate limits; no user-supplied code or tool files served |
| Privacy | GDPR; EU hosting; data minimisation; no third-party requests from pages |
| Maintainability | Single repo, typed Python, automated tests for permissions/state machine/scoring/search, one-command deploy |

## 8. Legal and regulatory notes (to confirm with a lawyer before launch)

- **GDPR:** controller = Diogo / the entity running gitmgf. Lawful bases: contract (account), legitimate interest (security logs, aggregate stats). Need DPA with email provider and VPS host (both EU).
- **EU Digital Services Act:** gitmgf stores user content, so it is a hosting service. The DSA hosting-provider duties — **notice-and-action (Art. 16)** and **statement of reasons (Art. 17)** — apply regardless of size; the heavier online-platform duties and transparency reporting have exemptions for micro and small enterprises. F10, F11 and F19 are designed to cover Art. 16–17; Terms must meet Art. 14; a contact point is needed (Art. 11–12).
- **Medical Device Regulation (EU 2017/745):** software with a medical purpose (e.g. a calculator that informs diagnosis or treatment) may be a medical device. gitmgf positions itself as a directory, and authors declare certifications with evidence (F20). Displaying a CE/MDR claim that is false could mislead clinicians, which is why "present" badges need evidence and moderator review, and why every badge links to its evidence rather than asserting conformity on gitmgf's behalf. Because gitmgf **never hosts or distributes** the tools (it only links to them), it stays a directory rather than a party "making available" software; still, confirm the wording of listings and disclaimers with a lawyer (INFARMED context).
- **Content license:** listing text and screenshots stay the author's; authors grant gitmgf a licence to display them (Terms).

## 9. Success metrics (first 6 months)

| Metric | Target |
|---|---|
| Published tools | ≥ 60 |
| Registered users | ≥ 500 |
| Monthly active visitors | ≥ 2 000 |
| Searches leading to a click (search CTR) | ≥ 40 % |
| Zero-result search rate | < 15 % |
| Median time from submission to decision | < 72 h |
| Share of open-source tools | ≥ 50 % |
| Tools with EN text | ≥ 30 % |

## 10. User stories (MVP, prioritised)

1. As a visitor, I search "baixa médica" and see relevant tools ranked by usefulness, so I can solve my problem now.
2. As a visitor, I filter by "Open source", "Free" and type "Online calculator" to find calculators I can open right away.
3. As a visitor using EN, I see the interface in English and know when a tool's text is only in PT.
4. As a resident, I sign in with Google in one click and star tools to find them later.
4a. As a resident, I publish the portfolio/indicator helper I built during my Internato, so other residents can use it and I can show it in my curriculum.
5. As a maker, I sign in with GitHub, paste my repo URL, fill the form and submit in under 10 minutes.
6. As a maker, I link my online calculator (hosted on my own site or GitHub Pages) and add screenshots so people see what it does before opening it.
7. As a maker, I get an email when my tool is approved, or a clear reason if it's rejected.
8. As a maker, I edit my published tool and the old version stays live until approval.
9. As a maker, I see how many people found my tool through search and opened it in the last 30 days.
10. As a moderator, I review a queue with diffs and a checklist, and approve/reject with one reason template.
11. As a moderator, I get notified when a tool is reported for dangerous content, and I can hide it immediately.
12. As an admin, I promote a user to moderator and see this in the audit log.
13. As an admin, I add the category "Medicina Desportiva" in PT and EN without a deploy.
14. As an admin, I see the top zero-result searches to know which tools the community is missing.
14a. As a clinician, I see at a glance on every card whether a tool has CE marking, MDR certification and an RGPD declaration — coloured if yes, grey and slashed if not — and can open the evidence.
14b. As a maker of a CE-marked tool, I enter the class, notified body number and Declaration of Conformity link so my tool shows verified badges and appears under the "CE" filter.
15. As a user, I export my data and delete my account myself.

## 11. Release plan

| Milestone | Content | Exit criteria |
|---|---|---|
| **M0 Foundation** | Repo, config, DB, migrations, base layout, i18n, health check, Docker | `docker compose up` serves bilingual home |
| **M1 Auth** | Magic link, GitHub, Google, sessions, onboarding, roles | All 3 logins work; admin bootstrap |
| **M2 Tools** | Submission form, drafts, screenshots, certification section + badge row (F20), tool page, my tools | Draft→pending flow; tool page renders |
| **M3 Moderation & Admin** | Queue, revisions + diff, reasons, emails, admin users/categories/settings, audit | Full lifecycle works end-to-end |
| **M4 Search & Browse** | FTS, filters, sort, home, category pages | Acceptance tests of F7 pass |
| **M5 Scoring** | Tracking redirects, stars, events, aggregation, score job, GitHub sync | Scores update; anti-gaming tests pass |
| **M6 Trust & Compliance** | Reports, auto-hide, certification expiry job + emails, legal pages, GDPR export/delete, SEO, RSS | DSA/GDPR checklist done |
| **M7 Hardening & Launch** | Security headers, rate limits, backups, monitoring, seed content, content review | Closed beta with ~20 clinicians, then public launch |

Seed content before launch: ~15–20 tools from known Portuguese authors (contact them directly), so search isn't empty on day one.

## 12. Phase 2 backlog (post-MVP)

Comments/discussion per tool · Public author profiles · "Explorações" — short posts about tech adventures · Verified-clinician badge (cédula profissional) · Specialty curators · Collections/curated lists ("Kit do interno de 1.º ano") · Co-authors / organisations (e.g. USF, APMGF group) · Tool changelog/versions · GitLab/Codeberg sync · Public read API + embeddable cards · Weekly newsletter of new tools · Usage feedback ("worked for me") · Tool health checker (dead links).

## 13. Open questions for the product owner

| # | Question | Default if unanswered |
|---|---|---|
| Q2 | Transactional email provider (EU): Brevo, Scaleway TEM, Postmark, Amazon SES (eu-west)? | Brevo or Scaleway TEM |
| Q3 | Legal entity / controller named in Terms & Privacy (personal name, association, company)? | Personal, to revisit |
| Q4 | On account deletion: delete the user's tools, or keep them as "former author" if open source? | Delete (simplest, GDPR-clean) |
| Q5 | Initial moderators — who, and target response time? | Diogo + 2 invited clinicians; 72 h |
| Q6 | Is a honeypot + time-check enough for anonymous reports, or do you want a self-hosted CAPTCHA (e.g. ALTCHA proof-of-work)? | Honeypot + time check; add ALTCHA if spam appears |
| Q7 | Relationship with mgfhub.com (cross-links, shared branding, SSO later)? | Cross-link in footer only |
| Q8 | Seek APMGF / Digital Health Study Group endorsement or partnership? | Pursue informally after beta |
| Q9 | Logo, colour palette, tone of voice? | Clean clinical look, git-inspired mark, neutral palette with one accent |
| Q10 | Minimum age to register (GDPR, PT = 13 for info-society services)? | 18+ in Terms (professional audience) |
| Q11 | Certification badges: is "absent" (grey slashed) enough, or do you want a third neutral state "not applicable" (e.g. RGPD for a calculator that processes no personal data)? | Two states as requested; tooltip text adapts (see F20) |
| Q12 | Which certifications form the always-visible core row? | CE · MDR · RGPD (others shown only when present) |
