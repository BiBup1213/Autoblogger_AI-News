"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _csv_int_env(name: str) -> list[int]:
    raw_value = os.getenv(name, "")
    values: list[int] = []
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            continue
    return values


@dataclass(frozen=True)
class Settings:
    database_path: Path
    http_timeout_seconds: int
    user_agent: str
    max_articles_per_run: int
    min_extracted_chars: int
    wordpress_base_url: str | None
    wordpress_username: str | None
    wordpress_application_password: str | None
    wordpress_dry_run: bool
    wordpress_default_category_id: int | None
    wordpress_tag_ids: list[int]
    summarizer_provider: str

    @property
    def wordpress_configured(self) -> bool:
        return bool(
            self.wordpress_base_url
            and self.wordpress_username
            and self.wordpress_application_password
        )


def load_settings() -> Settings:
    database_path = Path(os.getenv("DATABASE_PATH", "data/autoblogger.sqlite3"))
    category_id_raw = os.getenv("WP_DEFAULT_CATEGORY_ID")
    category_id = int(category_id_raw) if category_id_raw and category_id_raw.isdigit() else None

    return Settings(
        database_path=database_path,
        http_timeout_seconds=_int_env("HTTP_TIMEOUT_SECONDS", 20),
        user_agent=os.getenv(
            "HTTP_USER_AGENT",
            "AutobloggerAI-News/0.1 (+https://example.com; contact@example.com)",
        ),
        max_articles_per_run=_int_env("MAX_ARTICLES_PER_RUN", 20),
        min_extracted_chars=_int_env("MIN_EXTRACTED_CHARS", 500),
        wordpress_base_url=os.getenv("WP_BASE_URL"),
        wordpress_username=os.getenv("WP_USERNAME"),
        wordpress_application_password=os.getenv("WP_APPLICATION_PASSWORD"),
        wordpress_dry_run=_bool_env("WP_DRY_RUN", True),
        wordpress_default_category_id=category_id,
        wordpress_tag_ids=_csv_int_env("WP_TAG_IDS"),
        summarizer_provider=os.getenv("SUMMARIZER_PROVIDER", "stub").strip().lower(),
    )

