from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, ForeignKey, Index, String, Text, UniqueConstraint, and_, or_, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import (
    Assurance,
    CareSetting,
    ClaimState,
    MediaState,
    PatientData,
    Pricing,
    RevisionStatus,
    ToolStatus,
    ToolType,
    str_enum,
)
from app.models.taxonomy import Category, Tag, tool_categories, tool_tags
from app.models.user import User

PUBLIC_STATUSES = (ToolStatus.published, ToolStatus.archived)
# Visible before a moderator validates them (D43): submitted tools, and tools sent back for changes, as long as
# they were never rejected. Keep in sync with Tool.is_unvalidated and Tool.unvalidated_clause().
UNVALIDATED_SQL = "(t.rejected_at IS NULL AND (t.status = 'pending' OR (t.status = 'draft' AND t.changes_requested_at IS NOT NULL)))"


class Tool(Base):
    __tablename__ = "tools"
    __table_args__ = (
        Index("ix_tools_status_score", "status", text("score DESC")),
        Index("ix_tools_status_published", "status", text("published_at DESC")),
        Index("ix_tools_status_stars", "status", text("stars_count DESC")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[ToolStatus] = mapped_column(str_enum(ToolStatus, "tool_status"), default=ToolStatus.draft)
    tool_type: Mapped[ToolType | None] = mapped_column(str_enum(ToolType, "tool_type"))
    title_pt: Mapped[str] = mapped_column(String(80))
    title_en: Mapped[str | None] = mapped_column(String(80))
    summary_pt: Mapped[str] = mapped_column(String(200), default="")
    summary_en: Mapped[str | None] = mapped_column(String(200))
    description_pt: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str | None] = mapped_column(Text)
    description_html_pt: Mapped[str] = mapped_column(Text, default="")
    description_html_en: Mapped[str | None] = mapped_column(Text)
    intended_use: Mapped[str] = mapped_column(String(600), default="")
    care_setting: Mapped[CareSetting | None] = mapped_column(str_enum(CareSetting, "care_setting"))
    platforms: Mapped[list[str]] = mapped_column(default=list)
    tool_languages: Mapped[list[str]] = mapped_column(default=list)
    website_url: Mapped[str | None] = mapped_column(String(500))
    repo_url: Mapped[str | None] = mapped_column(String(500))
    download_url: Mapped[str | None] = mapped_column(String(500))
    docs_url: Mapped[str | None] = mapped_column(String(500))
    support_email: Mapped[str | None] = mapped_column(String(254))  # public, shown on the tool page
    license_spdx: Mapped[str | None] = mapped_column(String(40))
    is_open_source: Mapped[bool] = mapped_column(default=False)
    pricing: Mapped[Pricing | None] = mapped_column(str_enum(Pricing, "pricing"))
    patient_data: Mapped[PatientData | None] = mapped_column(str_enum(PatientData, "patient_data"))
    version_label: Mapped[str | None] = mapped_column(String(40))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(default=0.0)
    score_log: Mapped[float] = mapped_column(default=0.0)
    score_reset_at: Mapped[datetime | None]
    stars_count: Mapped[int] = mapped_column(default=0)
    declarations_accepted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    submitted_at: Mapped[datetime | None]
    changes_requested_at: Mapped[datetime | None]  # sent back by a moderator; still visible (D43)
    rejected_at: Mapped[datetime | None]  # once rejected, never visible again before approval (D43)
    published_at: Mapped[datetime | None]
    last_content_update_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]

    owner: Mapped[User] = relationship(lazy="joined")
    categories: Mapped[list[Category]] = relationship(secondary=tool_categories, order_by=Category.sort_order)
    tags: Mapped[list[Tag]] = relationship(secondary=tool_tags, order_by=Tag.label)
    media: Mapped[list["ToolMedia"]] = relationship(
        back_populates="tool",
        order_by="ToolMedia.sort_order",
        lazy="selectin",  # listings show the first screenshot on every card: one query per page
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    claims: Mapped[list["ToolCertification"]] = relationship(
        back_populates="tool", cascade="all, delete-orphan", passive_deletes=True
    )
    github: Mapped["ToolGithub | None"] = relationship(
        back_populates="tool", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_public(self) -> bool:
        """Validated and public: published or archived."""
        return self.status in PUBLIC_STATUSES

    @property
    def is_unvalidated(self) -> bool:
        """Public but not yet validated by a moderator (D43)."""
        if self.rejected_at is not None:
            return False
        return self.status == ToolStatus.pending or (
            self.status == ToolStatus.draft and self.changes_requested_at is not None
        )

    @property
    def is_visible(self) -> bool:
        return self.is_public or self.is_unvalidated

    @classmethod
    def unvalidated_clause(cls) -> ColumnElement[bool]:
        return and_(
            cls.rejected_at.is_(None),
            or_(
                cls.status == ToolStatus.pending,
                and_(cls.status == ToolStatus.draft, cls.changes_requested_at.is_not(None)),
            ),
        )

    @classmethod
    def listed_clause(cls) -> ColumnElement[bool]:
        """Shown in listings: published, or visible before validation (D43)."""
        return or_(cls.status == ToolStatus.published, cls.unvalidated_clause())

    @property
    def live_media(self) -> list["ToolMedia"]:
        return [m for m in self.media if m.state == MediaState.live]

    @property
    def cover(self) -> "ToolMedia | None":
        """The first live screenshot, shown on the tool's card."""
        live = self.live_media
        return live[0] if live else None

    def __repr__(self) -> str:
        return f"<Tool {self.id} {self.slug} {self.status}>"


class ToolMedia(Base):
    __tablename__ = "tool_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[int | None] = mapped_column(ForeignKey("tool_revisions.id", ondelete="SET NULL"))
    state: Mapped[MediaState] = mapped_column(str_enum(MediaState, "media_state"), default=MediaState.live)
    file_name: Mapped[str] = mapped_column(String(64))
    thumb_name: Mapped[str] = mapped_column(String(64))
    width: Mapped[int]
    height: Mapped[int]
    alt_text_pt: Mapped[str] = mapped_column(String(200))
    alt_text_en: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    tool: Mapped[Tool] = relationship(back_populates="media")

    def alt(self, lang: str) -> str:
        return self.alt_text_en if lang == "en" and self.alt_text_en else self.alt_text_pt


class ToolRevision(Base):
    __tablename__ = "tool_revisions"
    __table_args__ = (
        Index(
            "uq_tool_revisions_one_pending",
            "tool_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    data: Mapped[dict[str, Any]]
    status: Mapped[RevisionStatus] = mapped_column(
        str_enum(RevisionStatus, "revision_status"), default=RevisionStatus.pending
    )
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None]

    tool: Mapped[Tool] = relationship(lazy="joined")


class Star(Base):
    __tablename__ = "stars"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tool_id: Mapped[int] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ToolGithub(Base):
    __tablename__ = "tool_github"

    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100))
    repo: Mapped[str] = mapped_column(String(100))
    stars: Mapped[int | None]
    forks: Mapped[int | None]
    open_issues: Mapped[int | None]
    pushed_at: Mapped[datetime | None]
    license_spdx: Mapped[str | None] = mapped_column(String(40))
    archived: Mapped[bool] = mapped_column(default=False)
    default_branch: Mapped[str | None] = mapped_column(String(100))
    etag: Mapped[str | None] = mapped_column(String(200))
    fetched_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(String(200))

    tool: Mapped[Tool] = relationship(back_populates="github")


class Certification(Base):
    """Admin-managed catalogue of certifications (PRD F20, TECH_SPEC §5.3)."""

    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    badge_label: Mapped[str] = mapped_column(String(30))
    label_template: Mapped[str | None] = mapped_column(String(60))
    name_pt: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    help_pt: Mapped[str | None] = mapped_column(Text)
    help_en: Mapped[str | None] = mapped_column(Text)
    assurance_default: Mapped[Assurance] = mapped_column(str_enum(Assurance, "assurance_default"))
    field_schema: Mapped[list[Any]] = mapped_column(default=list)
    is_core: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    def name(self, lang: str) -> str:
        return self.name_en if lang == "en" else self.name_pt

    def help(self, lang: str) -> str:
        return (self.help_en if lang == "en" else self.help_pt) or ""


class ToolCertification(Base):
    __tablename__ = "tool_certifications"
    __table_args__ = (
        UniqueConstraint("tool_id", "certification_id"),
        Index("ix_tool_certifications_lookup", "certification_id", "state", "valid_until"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id", ondelete="CASCADE"))
    state: Mapped[ClaimState] = mapped_column(str_enum(ClaimState, "claim_state"), default=ClaimState.pending)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    assurance: Mapped[Assurance] = mapped_column(str_enum(Assurance, "claim_assurance"))
    evidence_url: Mapped[str | None] = mapped_column(String(500))
    valid_until: Mapped[date | None]
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None]
    expiry_notified_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    tool: Mapped[Tool] = relationship(back_populates="claims")
    certification: Mapped[Certification] = relationship(lazy="joined")
