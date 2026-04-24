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


def parse_allowed_categories(raw_value: str) -> dict[int, str]:
    """Parse ID:Name pairs without creating or validating WordPress terms."""
    categories: dict[int, str] = {}
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        category_id_raw, separator, name = part.partition(":")
        if not separator:
            continue
        category_id_raw = category_id_raw.strip()
        name = name.strip()
        if category_id_raw.isdigit() and name:
            categories[int(category_id_raw)] = name
    return categories


@dataclass(frozen=True)
class Settings:
    database_path: Path
    http_timeout_seconds: int
    user_agent: str
    max_articles_per_run: int
    max_articles_per_source_per_run: int
    min_extracted_chars: int
    wordpress_base_url: str | None
    wordpress_username: str | None
    wordpress_application_password: str | None
    wordpress_dry_run: bool
    wordpress_post_status: str
    wordpress_default_category_id: int | None
    wordpress_tag_ids: list[int]
    summarizer_provider: str
    openai_api_key: str | None
    openai_model: str
    openai_max_input_chars: int
    openai_request_timeout_seconds: int
    ai_category_classification_enabled: bool
    ai_allowed_categories: dict[int, str]
    image_generation_enabled: bool
    image_provider: str
    openai_image_model: str
    openai_image_size: str
    openai_image_quality: str
    openai_image_style: str
    openai_image_timeout_seconds: int
    openai_image_prompt_max_chars: int
    openai_image_save_local_copy: bool
    openai_image_output_dir: Path

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
        max_articles_per_source_per_run=_int_env("MAX_ARTICLES_PER_SOURCE_PER_RUN", 5),
        min_extracted_chars=_int_env("MIN_EXTRACTED_CHARS", 500),
        wordpress_base_url=os.getenv("WP_BASE_URL"),
        wordpress_username=os.getenv("WP_USERNAME"),
        wordpress_application_password=os.getenv("WP_APPLICATION_PASSWORD"),
        wordpress_dry_run=_bool_env("WP_DRY_RUN", True),
        wordpress_post_status=os.getenv("WP_POST_STATUS", "draft").strip().lower(),
        wordpress_default_category_id=category_id,
        wordpress_tag_ids=_csv_int_env("WP_TAG_IDS"),
        summarizer_provider=os.getenv("SUMMARIZER_PROVIDER", "stub").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        openai_max_input_chars=_int_env("OPENAI_MAX_INPUT_CHARS", 30000),
        openai_request_timeout_seconds=_int_env("OPENAI_REQUEST_TIMEOUT_SECONDS", 60),
        ai_category_classification_enabled=_bool_env("AI_CATEGORY_CLASSIFICATION_ENABLED", False),
        ai_allowed_categories=parse_allowed_categories(os.getenv("AI_ALLOWED_CATEGORIES", "")),
        image_generation_enabled=_bool_env("IMAGE_GENERATION_ENABLED", False),
        image_provider=os.getenv("IMAGE_PROVIDER", "openai").strip().lower(),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1",
        openai_image_size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024").strip() or "1536x1024",
        openai_image_quality=os.getenv("OPENAI_IMAGE_QUALITY", "medium").strip().lower(),
        openai_image_style=os.getenv("OPENAI_IMAGE_STYLE", "editorial").strip() or "editorial",
        openai_image_timeout_seconds=_int_env("OPENAI_IMAGE_TIMEOUT_SECONDS", 90),
        openai_image_prompt_max_chars=_int_env("OPENAI_IMAGE_PROMPT_MAX_CHARS", 4000),
        openai_image_save_local_copy=_bool_env("OPENAI_IMAGE_SAVE_LOCAL_COPY", False),
        openai_image_output_dir=Path(os.getenv("OPENAI_IMAGE_OUTPUT_DIR", "data/generated_images")),
    )
