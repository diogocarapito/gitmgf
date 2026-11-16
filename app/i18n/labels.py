"""Translatable labels for enum values. Values are msgids; translate with `_()` at render time."""

from app.i18n import N_

PROFESSION = {
    "specialist": N_("Médico/a especialista"),
    "resident": N_("Médico/a interno/a"),
    "nurse": N_("Enfermeiro/a"),
    "pharmacist": N_("Farmacêutico/a"),
    "med_student": N_("Estudante de Medicina"),
    "other_health": N_("Outro profissional de saúde"),
    "engineer": N_("Engenheiro/a / Developer"),
    "other": N_("Outro"),
}

ROLE = {"user": N_("Utilizador"), "moderator": N_("Moderador/a"), "admin": N_("Administrador/a")}

USER_STATUS = {"active": N_("Ativo"), "suspended": N_("Suspenso"), "deleted": N_("Eliminado")}

TOOL_STATUS = {
    "draft": N_("Rascunho"),
    "pending": N_("Em revisão"),
    "published": N_("Publicada"),
    "rejected": N_("Rejeitada"),
    "hidden": N_("Ocultada"),
    "archived": N_("Arquivada"),
    "deleted": N_("Eliminada"),
}

TOOL_TYPE = {
    "webapp": N_("Aplicação web"),
    "calculator": N_("Calculadora online"),
    "desktop": N_("Aplicação de computador"),
    "mobile": N_("Aplicação móvel"),
    "spreadsheet": N_("Folha de cálculo / modelo"),
    "script": N_("Script / biblioteca"),
    "extension": N_("Extensão de navegador"),
    "ai_prompt": N_("Prompt / assistente de IA"),
    "dataset": N_("Conjunto de dados"),
    "other": N_("Outro"),
}

# Short labels for cards and chips
TOOL_TYPE_SHORT = {
    "webapp": N_("Webapp"),
    "calculator": N_("Calculadora"),
    "desktop": N_("Desktop"),
    "mobile": N_("Móvel"),
    "spreadsheet": N_("Modelo"),
    "script": N_("Script"),
    "extension": N_("Extensão"),
    "ai_prompt": N_("IA"),
    "dataset": N_("Dados"),
    "other": N_("Outro"),
}

TOOL_TYPE_ICON = {
    "webapp": "globe",
    "calculator": "calculator",
    "desktop": "monitor",
    "mobile": "smartphone",
    "spreadsheet": "table",
    "script": "code",
    "extension": "puzzle",
    "ai_prompt": "sparkles",
    "dataset": "database",
    "other": "box",
}

CARE_SETTING = {
    "primary": N_("Cuidados de saúde primários"),
    "hospital": N_("Cuidados hospitalares"),
    "both": N_("Primários e hospitalares"),
    "na": N_("Não aplicável"),
}

PLATFORM = {
    "web": N_("Web"),
    "windows": N_("Windows"),
    "macos": N_("macOS"),
    "linux": N_("Linux"),
    "android": N_("Android"),
    "ios": N_("iOS"),
    "excel": N_("Excel"),
    "gsheets": N_("Google Sheets"),
    "libreoffice": N_("LibreOffice"),
    "other": N_("Outra"),
}

TOOL_LANGUAGE = {
    "pt": N_("Português"),
    "en": N_("Inglês"),
    "es": N_("Espanhol"),
    "fr": N_("Francês"),
    "other": N_("Outra"),
}

PRICING = {"free": N_("Gratuita"), "freemium": N_("Freemium"), "paid": N_("Paga")}

PATIENT_DATA = {
    "none": N_("Não trata dados de utentes"),
    "local_only": N_("Trata dados apenas localmente"),
    "server": N_("Envia dados para um servidor"),
    "unknown": N_("Desconhecido"),
}

LINK_KIND = {
    "website": N_("Abrir aplicação"),
    "download": N_("Transferir"),
    "repo": N_("Ver código"),
    "docs": N_("Documentação"),
}

LINK_FIELD = {
    "website_url": N_("Site ou aplicação (URL)"),
    "repo_url": N_("Repositório (URL)"),
    "download_url": N_("Transferência / versões (URL)"),
    "docs_url": N_("Documentação (URL)"),
}

ASSURANCE = {
    "self_declared": N_("autodeclarado"),
    "third_party": N_("certificado por terceiros"),
    "mixed": N_("misto"),
}

CLAIM_STATE = {"pending": N_("Em revisão"), "approved": N_("Aprovada"), "rejected": N_("Rejeitada")}

REPORT_REASON = {
    "broken_link": N_("Ligação quebrada"),
    "dangerous_content": N_("Conteúdo clínico incorreto ou perigoso"),
    "security_privacy": N_("Problema de segurança ou privacidade"),
    "incorrect_certification": N_("Certificação incorreta"),
    "spam": N_("Spam"),
    "copyright": N_("Violação de direitos de autor / licença"),
    "illegal": N_("Conteúdo ilegal"),
    "other": N_("Outro"),
}

REPORT_STATUS = {"open": N_("Aberta"), "resolved": N_("Resolvida"), "dismissed": N_("Arquivada sem ação")}

# Moderation reason templates (TECH_SPEC §7.3) — the final text is stored in the owner's locale.
REJECTION_REASONS = {
    "incomplete": N_("Informação incompleta: faltam dados necessários para avaliar a ferramenta."),
    "broken_link": N_("Ligação quebrada ou insegura: uma ou mais ligações não abrem ou não são seguras."),
    "patient_data": N_(
        "Dados de utentes visíveis: o texto ou as capturas de ecrã contêm dados que podem identificar utentes."
    ),
    "duplicate": N_("Duplicado: já existe uma ficha para esta ferramenta."),
    "not_health": N_("Fora do âmbito: a ferramenta não está relacionada com a saúde."),
    "guidelines": N_("Violação das Normas de Submissão."),
    "misleading": N_("Alegações clínicas enganadoras."),
    "copyright": N_("Problema de direitos de autor ou de licença."),
    "certification": N_(
        "Certificação sem evidência válida: a evidência indicada não abre ou não corresponde à ferramenta, fabricante ou classe."
    ),
    "other": N_("Outro motivo (ver detalhes)."),
}

SORTS = {
    "relevance": N_("Relevância"),
    "popular": N_("Populares"),
    "new": N_("Mais recentes"),
    "stars": N_("Mais estrelas"),
    "updated": N_("Atualizadas recentemente"),
}

LICENSES = [
    ("MIT", "MIT"),
    ("GPL-3.0-only", "GPL-3.0"),
    ("GPL-2.0-only", "GPL-2.0"),
    ("AGPL-3.0-only", "AGPL-3.0"),
    ("LGPL-3.0-only", "LGPL-3.0"),
    ("Apache-2.0", "Apache-2.0"),
    ("BSD-3-Clause", "BSD-3-Clause"),
    ("BSD-2-Clause", "BSD-2-Clause"),
    ("MPL-2.0", "MPL-2.0"),
    ("EUPL-1.2", "EUPL-1.2"),
    ("ISC", "ISC"),
    ("Unlicense", "Unlicense"),
    ("CC0-1.0", "CC0-1.0"),
    ("CC-BY-4.0", "CC BY 4.0"),
    ("CC-BY-SA-4.0", "CC BY-SA 4.0"),
    ("CC-BY-NC-4.0", "CC BY-NC 4.0"),
    ("CC-BY-NC-SA-4.0", "CC BY-NC-SA 4.0"),
    ("proprietary", N_("Proprietária / código fechado")),
    ("unknown", N_("Desconhecida")),
]

# OSI-approved licences (open-source badge needs one of these and a public repository)
OSI_LICENSES = {
    "MIT", "GPL-3.0-only", "GPL-2.0-only", "AGPL-3.0-only", "LGPL-3.0-only", "Apache-2.0",
    "BSD-3-Clause", "BSD-2-Clause", "MPL-2.0", "EUPL-1.2", "ISC", "Unlicense",
}  # fmt: skip

LICENSE_LABEL = dict(LICENSES)

# Messages shown after a redirect (`?flash=<key>`): stateless, no flash cookie needed.
FLASH = {
    "saved": ("ok", N_("Alterações guardadas.")),
    "linked": ("ok", N_("Conta associada.")),
    "unlinked": ("ok", N_("Conta desassociada. Pode continuar a entrar com a ligação por email.")),
    "provider_taken": ("danger", N_("Essa conta já está associada a outro utilizador da gitmgf.")),
    "signed_out_all": ("ok", N_("Sessão terminada em todos os dispositivos.")),
    "draft_saved": ("ok", N_("Rascunho guardado.")),
    "submitted": ("ok", N_("Ferramenta submetida para revisão. Vai receber um email com a decisão.")),
    "revision_submitted": ("ok", N_("Alteração submetida. A versão publicada mantém-se até à aprovação.")),
    "revision_withdrawn": ("ok", N_("Alteração pendente retirada.")),
    "withdrawn": ("ok", N_("Submissão retirada. A ferramenta voltou a rascunho.")),
    "archived": ("ok", N_("Ferramenta arquivada.")),
    "unarchived": ("ok", N_("Ferramenta publicada novamente.")),
    "deleted": ("ok", N_("Ferramenta eliminada.")),
    "media_added": ("ok", N_("Captura de ecrã adicionada.")),
    "media_removed": ("ok", N_("Captura de ecrã removida.")),
    "cert_removed": ("ok", N_("Certificação removida.")),
    "approved": ("ok", N_("Aprovado.")),
    "rejected": ("ok", N_("Rejeitado. O autor foi notificado.")),
    "hidden": ("ok", N_("Ferramenta ocultada. O autor foi notificado.")),
    "unhidden": ("ok", N_("Ferramenta visível novamente.")),
    "score_reset": ("ok", N_("Pontuação reposta.")),
    "report_closed": ("ok", N_("Denúncia fechada. O denunciante foi notificado.")),
    "reported": ("ok", N_("Obrigado. Recebemos a sua denúncia e vamos analisá-la.")),
    "role_changed": ("ok", N_("Função alterada.")),
    "suspended": ("ok", N_("Utilizador suspenso.")),
    "unsuspended": ("ok", N_("Suspensão levantada.")),
    "user_deleted": ("ok", N_("Conta eliminada.")),
    "account_deleted": (
        "ok",
        N_("A sua conta foi eliminada. Os dados serão apagados definitivamente em 30 dias."),
    ),
    "merged": ("ok", N_("Etiquetas fundidas.")),
    "forbidden_last_admin": ("danger", N_("Não é possível retirar o último administrador.")),
    "pending_limit": (
        "danger",
        N_("Atingiu o limite de submissões pendentes. Aguarde a revisão das anteriores."),
    ),
    "rate_limited": ("danger", N_("Demasiados pedidos. Aguarde um pouco e tente novamente.")),
}
