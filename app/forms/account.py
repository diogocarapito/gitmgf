from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator

from app.forms.common import FieldError, blank_to_none, opt_str
from app.i18n import N_
from app.models.enums import Locale, Profession


class LoginForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    next: str | None = None


def _check_new_password(password: str, confirm: str, email: str | None) -> None:
    from app.services.passwords import password_problem

    problem = password_problem(password, email)
    if problem:
        raise PasswordError("password", problem)
    if password != confirm:
        raise PasswordError("password_confirm", N_("As palavras-passe não coincidem."))


class PasswordError(ValueError):
    def __init__(self, field: str, msgid: str) -> None:
        super().__init__(msgid)
        self.field = field
        self.msgid = msgid


class RegisterForm(BaseModel):
    """Basic info up front (PRD F2, D30): after the emailed code there is no onboarding step."""

    model_config = ConfigDict(str_strip_whitespace=True)
    display_name: str = Field(min_length=2, max_length=80)
    email: EmailStr = Field(max_length=254)
    profession: Profession
    specialty_category_id: Annotated[int | None, BeforeValidator(blank_to_none)] = None
    password: str = Field(default="", max_length=128)
    password_confirm: str = Field(default="", max_length=128)
    invite: str | None = Field(default=None, max_length=100)
    accept_terms: bool = Field(default=False, validate_default=True)

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v: bool) -> bool:
        if not v:
            raise FieldError(N_("Tens de aceitar os Termos e as Normas de Submissão para continuar."))
        return v

    def profile(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "profession": self.profession.value,
            "specialty_category_id": self.specialty_category_id,
        }

    def password_errors(self) -> dict[str, tuple[str, dict[str, Any]]]:
        try:
            _check_new_password(self.password, self.password_confirm, str(self.email))
        except PasswordError as exc:
            return {exc.field: (exc.msgid, {})}
        return {}


def new_password_errors(
    password: str, confirm: str, email: str | None
) -> dict[str, tuple[str, dict[str, Any]]]:
    try:
        _check_new_password(password, confirm, email)
    except PasswordError as exc:
        return {exc.field: (exc.msgid, {})}
    return {}


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
            raise FieldError(N_("Usa 3 a 30 letras minúsculas, números ou hífenes."))
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
            raise FieldError(N_("Tens de aceitar os Termos e as Normas de Submissão para continuar."))
        return v
