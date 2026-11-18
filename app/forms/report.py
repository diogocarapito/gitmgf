"""Report form (PRD F11): anyone can report; anonymous reporters give an email (D31)."""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.forms.common import FieldError, blank_to_none
from app.i18n import N_
from app.models.enums import ReportReason


class ReportForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: ReportReason
    details: str = Field(min_length=20, max_length=2000)
    email: Annotated[EmailStr | None, BeforeValidator(blank_to_none)] = None
    good_faith: bool = Field(default=False, validate_default=True)
    anonymous: bool = False  # set by the route, not the form

    @field_validator("good_faith")
    @classmethod
    def _good_faith(cls, v: bool) -> bool:
        if not v:
            raise FieldError(N_("Confirme que faz a denúncia de boa-fé."))
        return v

    @model_validator(mode="after")
    def _email_needed(self) -> Any:
        if self.anonymous and not self.email:
            raise ValueError("email")
        return self
