"""Suggestion form (D32): signed-in users send a feature request or suggestion to a tool's author."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SuggestionKind


class SuggestionForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: SuggestionKind
    message: str = Field(min_length=20, max_length=2000)
    allow_reply: bool = False
