from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator

from app.forms.common import FieldError, blank_to_none, opt_str
from app.i18n import N_
from app.models.enums import Locale, Profession


class MagicLinkForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr = Field(max_length=254)
    next: str | None = None


class ProfileForm(BaseModel):
    """Onboarding and settings (PRD F2)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=2, max_length=80)
    handle: str = Field(min_length=3, max_length=30)
    profession: Profession
    specialty_category_id: Annotated[int | None, BeforeValidator(blank_to_none)] = None
    workplace: opt_str(120) = None  # type: ignore[valid-type]
    github_username: opt_str(39) = None  # type: ignore[valid-type]
    locale: Locale = Locale.pt

    @field_validator("handle")
    @classmethod
    def _handle(cls, v: str) -> str:
        import re

        v = v.lower()
        if not re.fullmatch(r"[a-z0-9-]{3,30}", v):
            raise FieldError(N_("Use 3 a 30 letras minúsculas, números ou hífenes."))
        return v

    @field_validator("github_username")
    @classmethod
    def _github(cls, v: str | None) -> str | None:
        import re

        if v is None:
            return None
        v = v.removeprefix("@").removeprefix("https://github.com/").strip("/")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", v):
            raise FieldError(N_("Nome de utilizador do GitHub inválido."))
        return v


class OnboardingForm(ProfileForm):
    accept_terms: bool = Field(default=False, validate_default=True)

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise FieldError(N_("Tem de aceitar os Termos e as Normas de Submissão para continuar."))
        return v
