"""WordPress REST API draft publisher."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urljoin

import requests

from app.config import Settings
from app.models import GeneratedImage, GermanSummary, PublishResult

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """Create WordPress posts through the REST API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    def create_draft(
        self,
        summary: GermanSummary,
        generated_image: GeneratedImage | None = None,
    ) -> PublishResult:
        """Create a configured WordPress post, or return dry-run status."""
        if self.settings.wordpress_dry_run:
            logger.info("WordPress dry-run enabled; post creation skipped for %s", summary.german_title)
            if generated_image is not None:
                logger.info("WordPress dry-run enabled; media upload skipped for %s", generated_image.local_file_path)
            return PublishResult(None, None, "dry_run", image_status="skipped_dry_run")

        if not self.settings.wordpress_configured:
            logger.warning("WordPress is not configured; post creation skipped")
            return PublishResult(None, None, "skipped")
        if self.settings.wordpress_post_status not in {"draft", "publish"}:
            raise RuntimeError(
                "Invalid WP_POST_STATUS="
                f"{self.settings.wordpress_post_status!r}; expected 'draft' or 'publish'"
            )

        endpoint = urljoin(
            self.settings.wordpress_base_url.rstrip("/") + "/",
            "wp-json/wp/v2/posts",
        )
        payload: dict[str, object] = {
            "title": summary.german_title,
            "excerpt": summary.german_excerpt,
            "content": summary.german_body_html,
            "status": self.settings.wordpress_post_status,
        }

        category_ids = self._category_ids_for_summary(summary)
        if category_ids:
            payload["categories"] = category_ids
        if self.settings.wordpress_tag_ids:
            payload["tags"] = self.settings.wordpress_tag_ids

        featured_media_id = None
        image_status = "not_generated"
        if generated_image is not None:
            try:
                featured_media_id = self.upload_media(generated_image)
                payload["featured_media"] = featured_media_id
                image_status = "uploaded"
                logger.info("Featured image attached as media ID %s", featured_media_id)
            except Exception as exc:
                image_status = "upload_failed"
                logger.warning("Image upload failed; creating post without featured image: %s", exc)

        logger.info(
            "Creating WordPress post as status=%s categories=%s tags=%s featured_media=%s",
            self.settings.wordpress_post_status,
            category_ids,
            self.settings.wordpress_tag_ids,
            featured_media_id,
        )
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
            raise RuntimeError(f"WordPress post creation failed: {exc}") from exc

        data = response.json()
        post_id = data.get("id")
        post_url = data.get("link")
        logger.info(
            "Created WordPress post id=%s status=%s title=%s",
            post_id,
            self.settings.wordpress_post_status,
            summary.german_title,
        )
        return PublishResult(
            wordpress_post_id=int(post_id) if post_id is not None else None,
            wordpress_url=str(post_url) if post_url else None,
            status="published" if self.settings.wordpress_post_status == "publish" else "draft_created",
            featured_media_id=featured_media_id,
            image_status=image_status,
        )

    def upload_media(self, generated_image: GeneratedImage) -> int:
        endpoint = urljoin(
            self.settings.wordpress_base_url.rstrip("/") + "/",
            "wp-json/wp/v2/media",
        )
        file_path = Path(generated_image.local_file_path)
        headers = {
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Content-Type": generated_image.mime_type,
        }
        response = self.session.post(
            endpoint,
            data=file_path.read_bytes(),
            headers=headers,
            auth=(
                self.settings.wordpress_username,
                self.settings.wordpress_application_password,
            ),
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        media_data = response.json()
        media_id = int(media_data["id"])
        logger.info("Uploaded WordPress media ID %s from %s", media_id, file_path)
        self._update_media_metadata(media_id, generated_image)
        return media_id

    def _update_media_metadata(self, media_id: int, generated_image: GeneratedImage) -> None:
        endpoint = urljoin(
            self.settings.wordpress_base_url.rstrip("/") + "/",
            f"wp-json/wp/v2/media/{media_id}",
        )
        payload: dict[str, str] = {"alt_text": generated_image.alt_text}
        if generated_image.caption:
            payload["caption"] = generated_image.caption
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
            logger.warning("Media metadata update failed for ID %s: %s", media_id, exc)

    def _category_ids_for_summary(self, summary: GermanSummary) -> list[int]:
        if self.settings.ai_category_classification_enabled:
            allowed_ids = set(self.settings.ai_allowed_categories)
            category_ids = [
                category_id
                for category_id in summary.category_ids
                if category_id in allowed_ids
            ][:3]
            if category_ids:
                return category_ids

        if self.settings.wordpress_default_category_id is not None:
            return [self.settings.wordpress_default_category_id]
        return []
