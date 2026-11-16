"""Development data for `python -m app.cli seed demo` (never in prod). All names and tools are fictional."""

import random
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import today, utcnow
from app.models import Category, Star, Tool, ToolDailyStat, User
from app.models.enums import Locale, Profession, Role
from app.services import scoring, search, settings_store
from app.services import tools as tool_service

PEOPLE = [
    ("Ana Ribeiro", Profession.resident),
    ("Bruno Matos", Profession.specialist),
    ("Carla Nunes", Profession.specialist),
    ("Diana Lopes", Profession.resident),
    ("Eduardo Pires", Profession.engineer),
    ("Filipa Sousa", Profession.nurse),
    ("Gonçalo Teixeira", Profession.resident),
    ("Helena Costa", Profession.pharmacist),
]

# (title_pt, title_en, summary_pt, summary_en, type, categories, tags, platforms, license)
TOOLS: list[tuple[Any, ...]] = [
    (
        "Calculadora SCORE2",
        "SCORE2 calculator",
        "Risco cardiovascular a 10 anos segundo as tabelas europeias, com explicação dos resultados.",
        "10-year cardiovascular risk using the European charts, with an explanation of results.",
        "calculator",
        ["calculadoras-scores", "cardiologia"],
        ["score2", "risco cardiovascular", "prevenção"],
        ["web"],
        "MIT",
    ),
    (
        "Plano de vacinação",
        "Vaccination planner",
        "Verifica o esquema vacinal por idade e sugere doses em atraso de acordo com o PNV.",
        "Checks the schedule by age and suggests overdue doses following the national plan.",
        "webapp",
        ["rastreios-prevencao", "pediatria"],
        ["pnv", "vacinação"],
        ["web"],
        "GPL-3.0-only",
    ),
    (
        "Codificador ICPC-2",
        None,
        "Sugere códigos ICPC-2 a partir de texto livre do diagnóstico.",
        None,
        "webapp",
        ["burocracia", "medicina-geral-familiar"],
        ["icpc-2", "codificação"],
        ["web"],
        "MIT",
    ),
    (
        "Agenda de vigilâncias",
        "Surveillance planner",
        "Aplicação desktop para organizar consultas de vigilância da lista de utentes.",
        "Desktop app to organise follow-up visits for a patient list.",
        "desktop",
        ["gestao-clinica"],
        ["vigilância", "lista de utentes"],
        ["windows", "macos", "linux"],
        "AGPL-3.0-only",
    ),
    (
        "Portefólio do Internato",
        "Residency portfolio",
        "Modelo para registar atividades, formação e objetivos ao longo do Internato.",
        "Template to record activities, training and goals during residency.",
        "spreadsheet",
        ["internato", "ensino-formacao"],
        ["portefólio", "internato"],
        ["excel", "gsheets"],
        "CC-BY-4.0",
    ),
    (
        "Conversor de doses pediátricas",
        "Paediatric dose converter",
        "Cálculo de doses por peso com alertas de dose máxima.",
        "Weight-based dosing with maximum-dose warnings.",
        "calculator",
        ["prescricao-terapeutica", "pediatria"],
        ["doses", "pediatria"],
        ["web", "android"],
        "MIT",
    ),
    (
        "Indicadores da USF",
        "Practice indicators",
        "Folha de cálculo para acompanhar os indicadores contratualizados da unidade ao longo do ano.",
        "Spreadsheet to follow the practice's contracted indicators through the year.",
        "spreadsheet",
        ["indicadores-dados", "gestao-clinica"],
        ["indicadores", "idg"],
        ["excel"],
        "CC-BY-SA-4.0",
    ),
    (
        "Exportador de listagens clínicas",
        "Clinical list exporter",
        "Script que converte exportações de listagens em tabelas prontas para análise.",
        "Script that turns list exports into analysis-ready tables.",
        "script",
        ["indicadores-dados", "produtividade"],
        ["python", "exportação", "excel"],
        ["windows", "macos", "linux"],
        "MIT",
    ),
    (
        "Atalhos de consulta",
        "Visit shortcuts",
        "Extensão de navegador com atalhos de texto para registos clínicos frequentes.",
        "Browser extension with text shortcuts for frequent clinical notes.",
        "extension",
        ["produtividade"],
        ["atalhos", "registos"],
        ["web"],
        "MPL-2.0",
    ),
    (
        "Assistente de cartas de referenciação",
        "Referral letter assistant",
        "Conjunto de prompts para rever e estruturar cartas de referenciação, sem dados de utentes.",
        "Prompt set to review and structure referral letters, without patient data.",
        "ai_prompt",
        ["inteligencia-artificial", "burocracia"],
        ["ia", "referenciação"],
        ["web"],
        "CC-BY-4.0",
    ),
    (
        "Calculadora CKD-EPI",
        "CKD-EPI calculator",
        "Taxa de filtração glomerular estimada (CKD-EPI 2021) e estadiamento da doença renal crónica.",
        "Estimated GFR (CKD-EPI 2021) and chronic kidney disease staging.",
        "calculator",
        ["calculadoras-scores", "nefrologia"],
        ["tfg", "doença renal"],
        ["web"],
        "Apache-2.0",
    ),
    (
        "Escala de Barthel",
        "Barthel index",
        "Avaliação da independência nas atividades de vida diária, com interpretação.",
        "Assessment of independence in activities of daily living, with interpretation.",
        "calculator",
        ["calculadoras-scores", "geriatria"],
        ["barthel", "funcionalidade"],
        ["web", "ios", "android"],
        "MIT",
    ),
    (
        "Simulador de exame do Internato",
        "Residency exam simulator",
        "Perguntas de escolha múltipla para treino, com explicações e referências.",
        "Multiple-choice practice questions with explanations and references.",
        "webapp",
        ["internato", "ensino-formacao"],
        ["exame", "estudo"],
        ["web"],
        "proprietary",
    ),
    (
        "Tabela de equivalências de opioides",
        "Opioid conversion table",
        "Conversão entre opioides e vias de administração, com notas de segurança.",
        "Conversion between opioids and routes, with safety notes.",
        "calculator",
        ["prescricao-terapeutica", "cuidados-paliativos"],
        ["opioides", "dor"],
        ["web"],
        "MIT",
    ),
    (
        "Calendário de rastreios oncológicos",
        "Cancer screening calendar",
        "Mostra os rastreios recomendados por idade e sexo e as datas seguintes.",
        "Shows recommended screenings by age and sex, and next dates.",
        "webapp",
        ["rastreios-prevencao", "oncologia"],
        ["rastreio", "cancro"],
        ["web"],
        "GPL-3.0-only",
    ),
    (
        "Escala GDS-15",
        "GDS-15 scale",
        "Escala de depressão geriátrica de 15 itens, com pontuação automática.",
        "15-item geriatric depression scale with automatic scoring.",
        "calculator",
        ["calculadoras-scores", "psiquiatria-saude-mental", "geriatria"],
        ["depressão", "idosos"],
        ["web"],
        "MIT",
    ),
    (
        "Dados abertos de prescrição",
        "Open prescribing data",
        "Conjunto de dados agregados de prescrição por região, para investigação.",
        "Aggregated prescribing dataset by region, for research.",
        "dataset",
        ["investigacao", "indicadores-dados"],
        ["dados abertos", "prescrição"],
        ["other"],
        "CC-BY-4.0",
    ),
    (
        "Relatório de atividade do Internato",
        "Residency activity report",
        "Gera o relatório anual de atividades a partir do registo do portefólio.",
        "Builds the yearly activity report from the portfolio log.",
        "script",
        ["internato", "burocracia"],
        ["relatório", "internato"],
        ["windows", "macos"],
        "MIT",
    ),
    (
        "Teleconsulta: guião",
        "Teleconsultation guide",
        "Guião de preparação de teleconsultas com lista de verificação.",
        "Teleconsultation preparation guide with a checklist.",
        "other",
        ["telemedicina"],
        ["teleconsulta"],
        ["web"],
        "CC-BY-4.0",
    ),
    (
        "Calculadora de idade gestacional",
        "Gestational age calculator",
        "Idade gestacional e data provável do parto a partir da DUM ou da ecografia.",
        "Gestational age and due date from last period or ultrasound.",
        "calculator",
        ["calculadoras-scores", "saude-materna-planeamento-familiar"],
        ["gravidez", "dpp"],
        ["web", "android", "ios"],
        "MIT",
    ),
]

LOREM = (
    "## O que faz\n\n{summary}\n\n## Como usar\n\n1. Abra a ferramenta.\n2. Preencha os campos pedidos.\n"
    "3. Leia a interpretação e confirme com os protocolos locais.\n\n## Limitações\n\nNão substitui o juízo clínico. "
    "Os resultados devem ser interpretados no contexto de cada utente.\n"
)


def seed_demo_data(db: Session, count: int = 30) -> int:
    rng = random.Random(42)  # deterministic demo data
    cats = {c.slug: c.id for c in db.scalars(select(Category)).all()}
    if not cats:
        raise RuntimeError("seed categories first: python -m app.cli seed categories")
    users: list[User] = []
    for i, (name, profession) in enumerate(PEOPLE):
        address = f"demo{i + 1}@example.org"
        user = db.scalar(select(User).where(User.email == address))
        if user is None:
            user = User(
                email=address,
                display_name=name,
                handle=name.lower().replace(" ", "-").replace("ç", "c"),
                profession=profession,
                locale=Locale.pt,
                role=Role.moderator if i == 1 else Role.user,
                email_verified_at=utcnow(),
                onboarded_at=utcnow(),
                terms_version=settings_store.get(db, "terms.current_version"),
                terms_accepted_at=utcnow(),
                github_username=f"demo-{i + 1}" if i % 2 == 0 else None,
            )
            db.add(user)
        users.append(user)
    db.flush()
    moderator = users[1]
    created = 0
    for n in range(count):
        spec = TOOLS[n % len(TOOLS)]
        title_pt, title_en, summary_pt, summary_en, ttype, cat_slugs, tags, platforms, licence = spec
        suffix = f" {n // len(TOOLS) + 1}" if n >= len(TOOLS) else ""
        owner = users[(n + 2) % len(users)]
        if owner.id == moderator.id:
            owner = users[0]
        slug_title = f"{title_pt}{suffix}"
        if db.scalar(select(Tool.id).where(Tool.title_pt == slug_title)):
            continue
        data = {
            "title_pt": slug_title,
            "title_en": f"{title_en}{suffix}" if title_en else None,
            "summary_pt": summary_pt,
            "summary_en": summary_en,
            "description_pt": LOREM.format(summary=summary_pt),
            "description_en": None,
            "tool_type": ttype,
            "care_setting": rng.choice(["primary", "primary", "both", "hospital"]),
            "platforms": platforms,
            "tool_languages": ["pt"] + (["en"] if title_en else []),
            "website_url": f"https://example.org/{n}",
            "repo_url": f"https://github.com/demo-org/tool-{n}" if licence != "proprietary" else None,
            "download_url": None,
            "docs_url": None,
            "license_spdx": licence,
            "pricing": "free" if licence != "proprietary" else "freemium",
            "patient_data": rng.choice(["none", "none", "local_only", "server"]),
            "intended_use": "Profissionais dos cuidados de saúde primários, como apoio à consulta. Não substitui o juízo clínico.",
            "version_label": f"v1.{n % 5}",
            "category_ids": [cats[s] for s in cat_slugs if s in cats],
            "tags": tags,
        }
        claims: dict[str, dict[str, Any]] = {}
        if n % 7 == 0:
            claims["rgpd"] = {
                "evidence_url": f"https://example.org/{n}/privacidade",
                "data_location": "eu_eea",
            }
        if n % 9 == 3:
            claims["mdr"] = {
                "class": "IIa",
                "nb_number": "0123",
                "certificate_no": f"MDR-{n:04d}",
                "valid_until": "2028-05-01",
                "evidence_url": f"https://example.org/{n}/certificado",
            }
            claims["ce"] = {
                "legal_basis": "MDR",
                "manufacturer": "Exemplo, Lda.",
                "evidence_url": f"https://example.org/{n}/doc",
            }
        if n % 11 == 5:
            claims["mdr"] = {"class": "I", "evidence_url": f"https://example.org/{n}/declaracao"}
            claims["ce"] = {
                "legal_basis": "MDR",
                "manufacturer": owner.display_name,
                "evidence_url": f"https://example.org/{n}/doc",
            }
        tool = tool_service.create_tool(db, owner, data, claims)
        tool.declarations_accepted_at = utcnow()
        db.flush()
        final = "pending" if n % 10 == 9 else "published"
        tool_service.transition(db, tool, "submit", owner)
        if final == "published":
            tool_service.transition(db, tool, "approve", moderator)
            tool.published_at = utcnow() - timedelta(days=rng.randint(1, 200))
            if tool.github is not None:
                tool.github.stars = rng.choice([0, 2, 5, 12, 40, 150])
                tool.github.forks = rng.randint(0, 20)
                tool.github.open_issues = rng.randint(0, 9)
                tool.github.pushed_at = utcnow() - timedelta(days=rng.randint(3, 500))
                tool.github.fetched_at = utcnow()
            for day in range(60):
                if rng.random() < 0.5:
                    db.add(
                        ToolDailyStat(
                            tool_id=tool.id,
                            day=today() - timedelta(days=day),
                            search_clicks=rng.randint(0, 6),
                            outbound_clicks=rng.randint(0, 8),
                            views=rng.randint(1, 20),
                        )
                    )
            for fan in rng.sample(users, rng.randint(0, 4)):
                if fan.id != owner.id:
                    db.add(Star(user_id=fan.id, tool_id=tool.id))
                    tool.stars_count += 1
        created += 1
    db.flush()
    scoring.recompute(db)
    search.rebuild(db)
    return created
