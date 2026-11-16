"""Search query parameters (TECH_SPEC §8.4). Unknown or invalid values are dropped, never errors."""

import re
from typing import Any

from pydantic import BaseModel, field_validator
from starlette.datastructures import QueryParams

from app.models.enums import Platform, ToolLanguage, ToolType, values
from app.services.search import MAX_PAGE, SORTS, SearchParams

SLUG_RE = re.compile(r"^[a-z0-9-]{1,80}$")
CODE_RE = re.compile(r"^[a-z0-9_]{1,30}$")


class SearchQueryParams(BaseModel):
    q: str = ""
    cat: list[str] = []
    type: str | None = None
    platform: list[str] = []
    setting: str | None = None
    oss: bool = False
    free: bool = False
    cert: list[str] = []
    lang: str | None = None
    sort: str | None = None
    page: int = 1

    @field_validator("q", mode="before")
    @classmethod
    def _q(cls, v: Any) -> str:
        return str(v or "")[:200]

    @field_validator("cat", mode="before")
    @classmethod
    def _cat(cls, v: Any) -> list[str]:
        return list(dict.fromkeys(s for s in v or [] if SLUG_RE.match(s)))[:10]

    @field_validator("cert", mode="before")
    @classmethod
    def _cert(cls, v: Any) -> list[str]:
        return list(dict.fromkeys(s for s in v or [] if CODE_RE.match(s)))[:10]

    @field_validator("platform", mode="before")
    @classmethod
    def _platform(cls, v: Any) -> list[str]:
        allowed = set(values(Platform))
        return list(dict.fromkeys(s for s in v or [] if s in allowed))

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v: Any) -> str | None:
        return v if v in values(ToolType) else None

    @field_validator("setting", mode="before")
    @classmethod
    def _setting(cls, v: Any) -> str | None:
        return v if v in ("primary", "hospital") else None

    @field_validator("lang", mode="before")
    @classmethod
    def _lang(cls, v: Any) -> str | None:
        return v if v in values(ToolLanguage) else None

    @field_validator("sort", mode="before")
    @classmethod
    def _sort(cls, v: Any) -> str | None:
        return v if v in SORTS else None

    @field_validator("oss", "free", mode="before")
    @classmethod
    def _flag(cls, v: Any) -> bool:
        return v in ("1", "on", "true", True)

    @field_validator("page", mode="before")
    @classmethod
    def _page(cls, v: Any) -> int:
        try:
            return max(1, min(int(v), MAX_PAGE))
        except (TypeError, ValueError):
            return 1

    @classmethod
    def from_query(cls, qp: QueryParams) -> "SearchQueryParams":
        data: dict[str, Any] = {
            k: qp.get(k) for k in ("q", "type", "setting", "oss", "free", "lang", "sort", "page") if k in qp
        }
        for key in ("cat", "platform", "cert"):
            data[key] = qp.getlist(key)
        return cls.model_validate(data)

    def to_params(self) -> SearchParams:
        return SearchParams(**self.model_dump())
