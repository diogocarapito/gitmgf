"""Form helpers: FormData -> dict for Pydantic, and Pydantic errors -> translatable messages."""

import re
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BeforeValidator, StringConstraints, ValidationError
from starlette.datastructures import FormData, UploadFile

from app.i18n import N_

# Pydantic error type -> msgid (formatted with the error ctx)
ERROR_MESSAGES = {
    "missing": N_("Campo obrigatório."),
    "string_too_short": N_("Texto demasiado curto (mín. %(min_length)s caracteres)."),
    "string_too_long": N_("Texto demasiado longo (máx. %(max_length)s caracteres)."),
    "enum": N_("Escolhe uma opção válida."),
    "literal_error": N_("Escolhe uma opção válida."),
    "int_parsing": N_("Valor inválido."),
    "value_error": N_("Valor inválido."),
    "too_long": N_("Demasiados itens (máx. %(max_length)s)."),
    "too_short": N_("Escolhe pelo menos %(min_length)s."),
    "string_pattern_mismatch": N_("Formato inválido."),
    "bool_parsing": N_("Valor inválido."),
    "date_from_datetime_parsing": N_("Data inválida."),
    "date_parsing": N_("Data inválida."),
}
REQUIRED = N_("Campo obrigatório.")
INVALID_URL = N_("Indica um endereço http:// ou https:// válido (máx. 500 caracteres).")
INVALID_EMAIL = N_("Indica um email válido.")


class FieldError(ValueError):
    """Raise inside validators with a msgid; shown under the field."""


def form_to_dict(form: FormData, multi: set[str] | None = None) -> dict[str, Any]:
    multi = multi or set()
    data: dict[str, Any] = {}
    for key in form:
        if key in multi:
            data[key] = [v for v in form.getlist(key) if isinstance(v, str) and v != ""]
        else:
            value = form.get(key)
            if isinstance(value, UploadFile):
                continue
            data[key] = value
    for key in multi:
        data.setdefault(key, [])
    return data


def errors_from(exc: ValidationError) -> dict[str, tuple[str, dict[str, Any]]]:
    """{field: (msgid, params)} — the first error per field."""
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for err in exc.errors():
        loc = err.get("loc") or ("__all__",)
        field = str(loc[0])
        if field in out:
            continue
        ctx = err.get("ctx") or {}
        original = ctx.get("error")
        if isinstance(original, FieldError):
            out[field] = (str(original), {})
            continue
        if err["type"] == "value_error" and "email" in str(err.get("msg", "")).lower():
            out[field] = (INVALID_EMAIL, {})
            continue
        msgid = ERROR_MESSAGES.get(err["type"], N_("Valor inválido."))
        params = {k: v for k, v in ctx.items() if isinstance(v, (int, str))}
        out[field] = (msgid, params)
    return out


def clean_url(value: str | None) -> str | None:
    """http(s) only, ≤ 500 chars; no javascript:, data: or credentials (TECH_SPEC §16)."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 500 or re.search(r"\s", value):
        raise FieldError(INVALID_URL)
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.netloc
        or "@" in parts.netloc
        or "." not in parts.netloc
    ):
        raise FieldError(INVALID_URL)
    return value


def blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def opt_str(max_length: int) -> object:
    """Optional text: blank -> None, otherwise at most `max_length` characters."""
    return Annotated[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None,
        BeforeValidator(blank_to_none),
    ]
