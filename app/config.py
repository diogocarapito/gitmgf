from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-insecure-secret-change-me"  # noqa: S105 - placeholder, rejected in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    secret_key: str = DEV_SECRET
    base_url: str = "http://localhost:8000"
    data_dir: Path = Path("data")
    database_path: Path | None = None

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "gitmgf <noreply@gitmgf.com>"
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    # Where replies to notifications go (appeals are made "by replying"). Falls back to LEGAL_CONTACT_EMAIL.
    smtp_reply_to: str = ""

    github_api_token: str = ""

    admin_emails: str = ""
    healthcheck_ping_url: str = ""
    git_sha: str = "dev"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def db_path(self) -> Path:
        return self.database_path or self.data_dir / "gitmgf.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def session_cookie(self) -> str:
        # The __Host- prefix requires Secure, so it is only used over HTTPS in prod.
        return "__Host-gitmgf_session" if self.is_prod else "gitmgf_session"

    @property
    def secure_cookies(self) -> bool:
        return self.is_prod

    @property
    def reply_to(self) -> str:
        import os

        return self.smtp_reply_to or os.environ.get("LEGAL_CONTACT_EMAIL", "")

    @property
    def email_backend(self) -> str:
        if self.app_env == "test":
            return "memory"
        if self.smtp_host:
            return "smtp"
        # No SMTP in prod: notifications stay queued in the outbox (readable at /admin/emails).
        return "none" if self.is_prod else "console"

    def config_errors(self) -> list[str]:
        """Problems that must block a production start."""
        errors = []
        if self.is_prod:
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
                errors.append("SECRET_KEY must be set to a random value of at least 32 characters")
            if not self.base_url.startswith("https://"):
                errors.append("BASE_URL must use https:// in prod")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
