import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, pass_context, select_autoescape
from markupsafe import Markup, escape

from app import i18n
from app.config import get_settings
from app.i18n import labels
from app.services.badges import derived_badges

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"], default_for_string=True),
    extensions=["jinja2.ext.i18n", "jinja2.ext.do"],
    trim_blocks=True,
    lstrip_blocks=True,
)
env.install_gettext_callables(gettext=i18n.gettext, ngettext=i18n.ngettext, newstyle=True)  # type: ignore[attr-defined]


@pass_context
def _url(ctx: Any, path: str = "/", **query: Any) -> str:
    """Language-prefixed URL: url('/search', q='x') -> /pt/search?q=x"""
    lang = ctx.get("lang", i18n.DEFAULT_LANG)
    if not path.startswith("/"):
        path = "/" + path
    base = f"/{lang}{path}"
    pairs = [(k, v) for k, v in query.items() if v not in (None, "", [], False)]
    return f"{base}?{urlencode(pairs, doseq=True)}" if pairs else base


def _static(path: str) -> str:
    return f"/static/{path}?v={get_settings().git_sha}"


def _icon(name: str, cls: str = "icon", label: str | None = None) -> Markup:
    aria = f' role="img" aria-label="{escape(label)}"' if label else ' aria-hidden="true"'
    return Markup(  # noqa: S704 - inputs escaped above
        f'<svg class="{escape(cls)}"{aria} focusable="false"><use href="{_static("icons/sprite.svg")}#{escape(name)}"></use></svg>'
    )


@pass_context
def _localized(ctx: Any, obj: Any, field: str) -> str:
    return i18n.localized(obj, field, ctx.get("lang", i18n.DEFAULT_LANG))[0]


@pass_context
def _is_fallback(ctx: Any, obj: Any, field: str) -> bool:
    return i18n.localized(obj, field, ctx.get("lang", i18n.DEFAULT_LANG))[1]


@pass_context
def _f_date(ctx: Any, value: Any, fmt: str = "long") -> str:
    return i18n.format_date(value, ctx.get("lang", i18n.DEFAULT_LANG), fmt)


@pass_context
def _f_short_date(ctx: Any, value: Any) -> str:
    return i18n.format_short_date(value, ctx.get("lang", i18n.DEFAULT_LANG))


@pass_context
def _f_datetime(ctx: Any, value: Any, fmt: str = "medium") -> str:
    return i18n.format_datetime(value, ctx.get("lang", i18n.DEFAULT_LANG), fmt)


@pass_context
def _f_number(ctx: Any, value: Any) -> str:
    return i18n.format_number(value or 0, ctx.get("lang", i18n.DEFAULT_LANG))


@pass_context
def _f_relative(ctx: Any, value: Any) -> str:
    return i18n.format_relative(value, ctx.get("lang", i18n.DEFAULT_LANG))


def _domain(url: str | None) -> str:
    if not url:
        return ""
    return urlsplit(url).netloc.removeprefix("www.")


@pass_context
def _label(ctx: Any, mapping: dict[str, str], key: Any) -> str:
    if key is None:
        return ""
    value = mapping.get(str(key), str(key))
    return i18n.translations(ctx.get("lang", i18n.DEFAULT_LANG)).gettext(value)


env.globals.update(
    url=_url,
    static=_static,
    icon=_icon,
    localized=_localized,
    is_fallback=_is_fallback,
    label=_label,
    labels=labels,
    card_badges=derived_badges,
    HTML_LANG=i18n.HTML_LANG,
)
env.filters.update(
    date=_f_date,
    short_date=_f_short_date,
    datetime=_f_datetime,
    number=_f_number,
    relative=_f_relative,
    domain=_domain,
)


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def base_context(request: Request) -> dict[str, Any]:
    lang = getattr(request.state, "lang", i18n.DEFAULT_LANG)
    path = request.url.path
    return {
        "request": request,
        "lang": lang,
        "other_lang": "en" if lang == "pt" else "pt",
        "user": getattr(request.state, "user", None),
        "csrf_token": getattr(request.state, "csrf_token", ""),
        "path": path,
        "full_path": path + (f"?{request.url.query}" if request.url.query else ""),
        "alt_url": i18n.swap_lang(path, "en" if lang == "pt" else "pt")
        + (f"?{request.url.query}" if request.url.query else ""),
        "url_pt": i18n.swap_lang(path, "pt"),
        "url_en": i18n.swap_lang(path, "en"),
        "base_url": get_settings().base_url.rstrip("/"),
        "banner": getattr(request.state, "banner", ""),
        "is_htmx": is_htmx(request),
        "settings": get_settings(),
        "flash": request.query_params.get("flash"),
    }


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    ctx = base_context(request)
    ctx.update(context or {})
    with i18n.use_lang(ctx["lang"]):
        html = env.get_template(template).render(ctx)
    return HTMLResponse(html, status_code=status_code, headers=headers)


def render_to_string(template: str, context: dict[str, Any], lang: str) -> str:
    with i18n.use_lang(lang):
        return env.get_template(template).render({"lang": lang, **context})


_URL_RE = re.compile(r"(https?://[^\s<>\"]+)")


def text_to_html(text: str) -> Markup:
    """Plain-text email body -> minimal HTML: escaped, paragraphs, clickable links."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    out = []
    for para in paragraphs:
        escaped = str(escape(para))
        linked = _URL_RE.sub(r'<a href="\1">\1</a>', escaped)
        out.append("<p>" + linked.replace("\n", "<br>") + "</p>")
    return Markup("\n".join(out))  # noqa: S704 - inputs escaped above


def render_email(template: str, context: dict[str, Any], lang: str) -> tuple[str, str, str]:
    """Returns (subject, text, html). Each email template defines `subject` and `body` blocks."""
    base = get_settings().base_url.rstrip("/")
    ctx = {"lang": lang, "base_url": base, **context}
    with i18n.use_lang(lang):
        tmpl = env.get_template(f"emails/{template}.txt")
        tctx = tmpl.new_context(ctx)
        subject = " ".join("".join(tmpl.blocks["subject"](tctx)).split())
        body = "".join(tmpl.blocks["body"](tmpl.new_context(ctx))).strip() + "\n"
        html = env.get_template("emails/_layout.html").render(
            {**ctx, "subject": subject, "body_html": text_to_html(body)}
        )
    return subject, body, html
