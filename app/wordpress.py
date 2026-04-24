"""WordPress REST API draft publisher."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests

from app.config import Settings
from app.models import GermanSummary, PublishResult

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """Create WordPress draft posts through the REST API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    def create_draft(self, summary: GermanSummary) -> PublishResult:
        """Create a draft post, or return a non-remote status for dry runs."""
        if self.settings.wordpress_dry_run:
            logger.info("WordPress dry-run enabled; draft creation skipped for %s", summary.german_title)
            return PublishResult(None, None, "dry_run")

        if not self.settings.wordpress_configured:
            logger.warning("WordPress is not configured; draft creation skipped")
            return PublishResult(None, None, "skipped")

        endpoint = urljoin(
            self.settings.wordpress_base_url.rstrip("/") + "/",
            "wp-json/wp/v2/posts",
        )
        payload: dict[str, object] = {
            "title": summary.german_title,
            "excerpt": summary.german_excerpt,
            "content": summary.german_body_html,
            "status": "draft",
        }

        if self.settings.wordpress_default_category_id is not None:
            payload["categories"] = [self.settings.wordpress_default_category_id]
        if self.settings.wordpress_tag_ids:
            payload["tags"] = self.settings.wordpress_tag_ids

        try:
            response = self.session.post(
                endpoint,
                json=payload,
                auth=(
                    self.settings.wordpress_username,
                    self.settings.wordpress_application_password,
                ),
                timeout=self.settings.http_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"WordPress draft creation failed: {exc}") from exc

        data = response.json()
        post_id = data.get("id")
        post_url = data.get("link")
        logger.info("Created WordPress draft id=%s title=%s", post_id, summary.german_title)
        return PublishResult(
            wordpress_post_id=int(post_id) if post_id is not None else None,
            wordpress_url=str(post_url) if post_url else None,
            status="draft_created",
        )
