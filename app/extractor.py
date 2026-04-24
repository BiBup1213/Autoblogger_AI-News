"""Article download and text extraction."""

from __future__ import annotations

import logging

import requests
import trafilatura
from trafilatura.metadata import extract_metadata

from app.models import ArticleContent, FeedItem

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Raised when an article cannot be fetched or reduced to usable text."""

    pass


class ArticleExtractor:
    """Fetch article pages and extract their main text with trafilatura."""

    def __init__(self, timeout_seconds: int, user_agent: str, min_chars: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.min_chars = min_chars
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def extract(self, item: FeedItem) -> ArticleContent:
        """Extract article content or raise ExtractionError with a durable reason."""
        try:
            response = self.session.get(item.url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ExtractionError(f"Article fetch failed: {exc}") from exc

        html = response.text
        metadata = extract_metadata(html, default_url=response.url)
        extracted_text = trafilatura.extract(
            html,
            url=response.url,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )

        if not extracted_text:
            raise ExtractionError("No article text could be extracted")

        extracted_text = extracted_text.strip()
        if len(extracted_text) < self.min_chars:
            raise ExtractionError(
                f"Extracted text is too short ({len(extracted_text)} chars)"
            )

        original_title = (metadata.title if metadata and metadata.title else item.title).strip()
        published_at = metadata.date if metadata and metadata.date else item.published_at
        canonical_url = metadata.url if metadata and metadata.url else response.url

        return ArticleContent(
            source_name=item.source_name,
            source_url=response.url,
            original_title=original_title,
            published_at=published_at,
            text=extracted_text,
            canonical_url=canonical_url,
        )
