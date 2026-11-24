"""Colab post and comment forms (D41)."""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.forms.common import blank_to_none, clean_url
from app.models.enums import ColabKind
from app.services.colabs import ColabData
from app.services.comments import MAX_LENGTH, MIN_LENGTH


class ColabForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: ColabKind
    title: str = Field(min_length=8, max_length=120)
    body: str = Field(min_length=30, max_length=4000)
    link_url: Annotated[str | None, BeforeValidator(blank_to_none)] = None
    tool_id: Annotated[int | None, BeforeValidator(blank_to_none)] = None

    @field_validator("link_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return clean_url(v)

    def data(self) -> ColabData:
        return ColabData(self.kind, self.title, self.body, self.link_url, self.tool_id)


class CommentForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH)
    parent_id: Annotated[int | None, BeforeValidator(blank_to_none)] = None


class ReasonForm(BaseModel):
    """Moderator hide/block reason, sent to the person affected."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=10, max_length=2000)
