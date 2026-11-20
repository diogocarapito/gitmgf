# Legal pages — notes for the owner (not published)

Files: `legal/privacy.md`, `legal/terms.md` (prevailing versions), `legal/privacy_en.md`, `legal/terms_en.md` (translations). How to edit: `content/README.md`.
Version `2026-11` must match the `terms.current_version` site setting. Bump both when the text changes in a way that needs re-acceptance.

## 1. Placeholders to fill

Placeholders use `[[KEY]]`. They are replaced at render time from site settings `legal.<KEY>` (TECH_SPEC §13a). The app refuses to start in `prod` if any placeholder in `content/legal/` has no value.

| Key | What to put | Suggestion |
|---|---|---|
| `CONTROLLER_NAME` | Legal name of whoever runs gitmgf (person, association or company) | Decide Q3 in the PRD first |
| `CONTROLLER_TAX_ID` | NIF / NIPC | |
| `CONTROLLER_ADDRESS` | Postal address (can be a professional or domicile address) | |
| `PRIVACY_EMAIL` | Mailbox for privacy requests | `privacidade@gitmgf.com` |
| `CONTACT_EMAIL` | DSA single point of contact + general contact | `contacto@gitmgf.com` |
| `SECURITY_EMAIL` | Vulnerability reports | `seguranca@gitmgf.com` (also publish `/.well-known/security.txt`) |
| `DPO_STATEMENT` / `DPO_STATEMENT_EN` | DPO sentence | PT: "Não foi designado um encarregado de proteção de dados, por não ser obrigatório para o tratamento realizado (art. 37.º do RGPD). Para qualquer questão sobre privacidade, use o contacto acima." EN: "No data protection officer has been appointed, as one is not required for this processing (GDPR Art. 37). For any privacy question, use the contact above." |
| `HOSTING_PROVIDER`, `HOSTING_LOCATION` | VPS company and country | e.g. Hetzner Online GmbH, Germany/Finland |
| `EMAIL_PROVIDER`, `EMAIL_PROVIDER_LOCATION` | Transactional email company and country | e.g. Brevo (France) or Scaleway (France) |
| `BACKUP_PROVIDER`, `BACKUP_LOCATION` | Object storage for Litestream/backups | Can be the same as hosting |
| `AUTO_HIDE_THRESHOLD` | Number of reports that trigger auto-hide | Rendered from `reports.auto_hide_threshold` (default 3), so the text never drifts from the setting |
| `SITE_CODE_LICENSE_STATEMENT` / `_EN` | Licence of gitmgf's own code | If open-sourced: "O código-fonte da gitmgf está disponível em [repo] sob a licença AGPL-3.0." Otherwise leave empty |
| `COURT_DISTRICT` | Court district | e.g. "Lisboa", or the controller's district |
| `ADR_STATEMENT` / `_EN` | Alternative dispute resolution (RAL) sentence | **Lawyer to confirm** whether it applies (the service is free and may not be run by a trader). If needed, name a RAL entity (e.g. CNIACC or a regional arbitration centre) and link the Livro de Reclamações Eletrónico. Otherwise remove section 17.3 |

## 2. Things to confirm with a lawyer before launch

1. Who the controller is (person vs. association vs. company) and whether consumer-law items (RAL entity, Livro de Reclamações) apply.
2. Whether the liability wording in Terms §14 is acceptable under the Portuguese general contract terms law (Decreto-Lei n.º 446/85).
3. Listing tools with CE/MDR claims under the Medical Device Regulation (PRD §8) and INFARMED's practice — gitmgf only links to tools and never hosts them.
4. Whether volunteer moderators should sign a confidentiality agreement (they see emails and reports) — recommended.
5. Processor agreements (DPAs) signed with the hosting, email and backup providers; keep copies.
6. The record of processing activities (art. 30.º RGPD). Not mandatory for small organisations in every case, but cheap to keep: derive it from Privacy §3, §4, §7 and §9.

## 3. Still to write

- `guidelines.md` (Normas de Submissão / Submission Guidelines) — referenced by the Terms: what's accepted, patient-data rules, certification evidence, link rules (links must point to the author's own publication place — repo, website, store — not file-sharing mirrors or URL shorteners; downloads must come from the author's release page).
- `disclaimer.md` (Aviso legal), `about.md`, `contact.md`.
- Email templates for the DSA statement of reasons (Terms §9.3) must contain: measure, facts, rule, whether automated means or a report were involved, and how to appeal (6 months).
