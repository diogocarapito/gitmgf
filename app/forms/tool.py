"""Tool submission form (PRD F3). Drafts need only a title; submission validates everything."""

import re
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator
from slugify import slugify

from app.forms.common import (
    REQUIRED,
    FieldError,
    blank_to_none,
    clean_url,
    errors_from,
    form_to_dict,
    opt_str,
)
from app.i18n import N_
from app.i18n.labels import LICENSE_LABEL
from app.models.enums import CareSetting, PatientData, Platform, Pricing, ToolLanguage, ToolType

MULTI_FIELDS = {"category_ids", "platforms", "tool_languages"}
LINK_FIELDS = ("website_url", "repo_url", "download_url", "docs_url")
DECLARATIONS = ("decl_author", "decl_no_patient_data", "decl_no_validation")
MAX_TAGS = 10

OptStr = Annotated[str | None, BeforeValidator(blank_to_none)]


def parse_tags(raw: str | list[str] | None) -> list[str]:
    """Free tags: lowercase, trimmed, de-duplicated accent-insensitively (PRD F6)."""
    if not raw:
        return []
    parts = raw if isinstance(raw, list) else re.split(r"[,;\n]", raw)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        label = re.sub(r"\s+", " ", part.strip().lstrip("#")).lower()
        slug = slugify(label)
        if not label or not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(label)
    return out


class ToolForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title_pt: str = Field("", max_length=80)
    title_en: opt_str(80) = None  # type: ignore[valid-type]
    summary_pt: str = Field("", max_length=200)
    summary_en: opt_str(200) = None  # type: ignore[valid-type]
    description_pt: str = Field("", max_length=20000)
    description_en: opt_str(20000) = None  # type: ignore[valid-type]
    tool_type: Annotated[ToolType | None, BeforeValidator(blank_to_none)] = None
    category_ids: list[int] = Field(default_factory=list, max_length=5)
    tags: list[str] = Field(default_factory=list)
    care_setting: Annotated[CareSetting | None, BeforeValidator(blank_to_none)] = None
    platforms: list[Platform] = Field(default_factory=list)
    tool_languages: list[ToolLanguage] = Field(default_factory=list)
    website_url: OptStr = None
    repo_url: OptStr = None
    download_url: OptStr = None
    docs_url: OptStr = None
    license_spdx: OptStr = None
    pricing: Annotated[Pricing | None, BeforeValidator(blank_to_none)] = None
    patient_data: Annotated[PatientData | None, BeforeValidator(blank_to_none)] = None
    intended_use: str = Field("", max_length=600)
    version_label: opt_str(40) = None  # type: ignore[valid-type]
    decl_author: bool = False
    decl_no_patient_data: bool = False
    decl_no_validation: bool = False

    @field_validator("website_url", "repo_url", "download_url", "docs_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return clean_url(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: Any) -> list[str]:
        tags = parse_tags(v)
        if len(tags) > MAX_TAGS:
            raise FieldError(N_("Máximo de 10 etiquetas."))
        for tag in tags:
            if len(tag) > 40 or len(tag) < 2:
                raise FieldError(N_("Cada etiqueta deve ter entre 2 e 40 caracteres."))
        return tags

    @field_validator("license_spdx")
    @classmethod
    def _license(cls, v: str | None) -> str | None:
        if v is not None and v not in LICENSE_LABEL:
            raise FieldError(N_("Escolha uma opção válida."))
        return v

    @field_validator("platforms", "tool_languages", mode="after")
    @classmethod
    def _dedupe(cls, v: list[Any]) -> list[Any]:
        return list(dict.fromkeys(v))

    def submission_errors(self) -> dict[str, tuple[str, dict[str, Any]]]:
        """Required on submit (draft → pending)."""
        errors: dict[str, tuple[str, dict[str, Any]]] = {}

        def need(name: str, ok: bool, msg: str = REQUIRED) -> None:
            if not ok and name not in errors:
                errors[name] = (msg, {})

        need("summary_pt", bool(self.summary_pt))
        need("description_pt", bool(self.description_pt))
        need("tool_type", self.tool_type is not None)
        need("category_ids", 1 <= len(self.category_ids) <= 5, N_("Escolha entre 1 e 5 categorias."))
        need("care_setting", self.care_setting is not None)
        need("platforms", bool(self.platforms), N_("Escolha pelo menos uma plataforma."))
        need("tool_languages", bool(self.tool_languages), N_("Escolha pelo menos um idioma."))
        need("website_url", any(getattr(self, f) for f in LINK_FIELDS), N_("Indique pelo menos uma ligação."))
        need("license_spdx", self.license_spdx is not None)
        need("pricing", self.pricing is not None)
        need("patient_data", self.patient_data is not None)
        need("intended_use", bool(self.intended_use))
        for name in DECLARATIONS:
            need(name, getattr(self, name), N_("Confirmação obrigatória para submeter."))
        return errors

    def tool_data(self) -> dict[str, Any]:
        """Editable listing data (the revision snapshot shape, minus media and certifications)."""
        data = self.model_dump(exclude=set(DECLARATIONS))
        for key in ("tool_type", "care_setting", "pricing", "patient_data"):
            data[key] = data[key].value if data[key] is not None else None
        data["platforms"] = [p.value for p in self.platforms]
        data["tool_languages"] = [x.value for x in self.tool_languages]
        return data


def parse_tool_form(form: Any) -> tuple[ToolForm, dict[str, tuple[str, dict[str, Any]]], dict[str, Any]]:
    """Returns (validated form, field errors, raw values for re-rendering). Invalid fields fall back to empty."""
    raw = form_to_dict(form, MULTI_FIELDS)
    for name in DECLARATIONS:
        raw[name] = form.get(name) in ("1", "on", "true")
    errors: dict[str, tuple[str, dict[str, Any]]] = {}
    try:
        parsed = ToolForm.model_validate(raw)
    except ValidationError as exc:
        errors = errors_from(exc)
        cleaned = {k: v for k, v in raw.items() if k not in errors}
        try:
            parsed = ToolForm.model_validate(cleaned)
        except ValidationError:
            parsed = ToolForm(title_pt=str(raw.get("title_pt") or "")[:80])
    if len(parsed.title_pt) < 3 and "title_pt" not in errors:
        errors["title_pt"] = (N_("Indique um título com pelo menos 3 caracteres."), {})
    return parsed, errors, raw
