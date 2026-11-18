from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as SAEnum


def str_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Enum stored as its string value, guarded by a CHECK constraint (TECH_SPEC §5.1)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


class Profession(StrEnum):
    specialist = "specialist"
    resident = "resident"
    nurse = "nurse"
    pharmacist = "pharmacist"
    med_student = "med_student"
    other_health = "other_health"
    engineer = "engineer"
    other = "other"


class Locale(StrEnum):
    pt = "pt"
    en = "en"


class Role(StrEnum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


class UserStatus(StrEnum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"


class ToolStatus(StrEnum):
    draft = "draft"
    pending = "pending"
    published = "published"
    rejected = "rejected"
    hidden = "hidden"
    archived = "archived"
    deleted = "deleted"


class ToolType(StrEnum):
    webapp = "webapp"
    calculator = "calculator"
    desktop = "desktop"
    mobile = "mobile"
    spreadsheet = "spreadsheet"
    script = "script"
    extension = "extension"
    ai_prompt = "ai_prompt"
    dataset = "dataset"
    other = "other"


class CareSetting(StrEnum):
    primary = "primary"
    hospital = "hospital"
    both = "both"
    na = "na"


class Platform(StrEnum):
    web = "web"
    windows = "windows"
    macos = "macos"
    linux = "linux"
    android = "android"
    ios = "ios"
    excel = "excel"
    gsheets = "gsheets"
    libreoffice = "libreoffice"
    other = "other"


class ToolLanguage(StrEnum):
    pt = "pt"
    en = "en"
    es = "es"
    fr = "fr"
    other = "other"


class Pricing(StrEnum):
    free = "free"
    freemium = "freemium"
    paid = "paid"


class PatientData(StrEnum):
    none = "none"
    local_only = "local_only"
    server = "server"
    unknown = "unknown"


class MediaState(StrEnum):
    live = "live"
    pending = "pending"
    removed = "removed"


class RevisionStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"


class Assurance(StrEnum):
    self_declared = "self_declared"
    third_party = "third_party"
    mixed = "mixed"


class ClaimState(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class EventKind(StrEnum):
    search_click = "search_click"
    outbound_click = "outbound_click"
    view = "view"


class LinkKind(StrEnum):
    website = "website"
    repo = "repo"
    download = "download"
    docs = "docs"


class ReportReason(StrEnum):
    broken_link = "broken_link"
    dangerous_content = "dangerous_content"
    inappropriate = "inappropriate"
    security_privacy = "security_privacy"
    incorrect_certification = "incorrect_certification"
    spam = "spam"
    copyright = "copyright"
    illegal = "illegal"
    other = "other"


class ReportStatus(StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class EmailStatus(StrEnum):
    queued = "queued"
    sent = "sent"
    failed = "failed"


def values(enum_cls: Any) -> list[str]:
    return [m.value for m in enum_cls]
