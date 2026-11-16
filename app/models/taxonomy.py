from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow

tool_categories = Table(
    "tool_categories",
    Base.metadata,
    Column("tool_id", ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True, index=True),
)

tool_tags = Table(
    "tool_tags",
    Base.metadata,
    Column("tool_id", ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name_pt: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))
    description_pt: Mapped[str | None]
    description_en: Mapped[str | None]
    icon: Mapped[str | None] = mapped_column(String(40))
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    is_specialty: Mapped[bool] = mapped_column(default=False)

    def name(self, lang: str) -> str:
        return self.name_en if lang == "en" and self.name_en else self.name_pt

    def description(self, lang: str) -> str:
        return (self.description_en if lang == "en" and self.description_en else self.description_pt) or ""


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(40))
    usage_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
