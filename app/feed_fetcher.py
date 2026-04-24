"""RSS/Atom feed fetching and parsing."""

from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests

from app.models import FeedItem, SourceConfig
from app.utils import normalize_url

logger = logging.getLogger(__name__)


class FeedFetcher:
    """Fetch and normalize approved RSS/Atom feeds."""

    def __init__(self, timeout_seconds: int, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def fetch(self, source: SourceConfig) -> list[FeedItem]:
        """Return parseable feed entries, logging network failures as warnings."""
        try:
            response = self.session.get(source.feed_url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Feed fetch failed for %s: %s", source.name, exc)
            return []

        parsed_feed = feedparser.parse(response.content)
        if parsed_feed.bozo:
            logger.warning("Feed parser reported a recoverable issue for %s", source.name)

        items: list[FeedItem] = []
        for entry in parsed_feed.entries:
            item = self._parse_entry(source, entry)
            if item is not None:
                items.append(item)
        return items

    def _parse_entry(self, source: SourceConfig, entry: Any) -> FeedItem | None:
        """Map feedparser's loose entry shape into the internal FeedItem model."""
        link = entry.get("link")
        if not link:
            return None

        url = normalize_url(link)
        guid = str(entry.get("id") or entry.get("guid") or url)
        title = str(entry.get("title") or "Ohne Titel").strip()
        published_at = self._published_at(entry)
        categories = tuple(
            str(tag.get("term") or tag.get("label") or "").strip().lower()
            for tag in entry.get("tags", [])
            if tag.get("term") or tag.get("label")
        )

        raw = {
            "id": entry.get("id"),
            "link": entry.get("link"),
            "title": entry.get("title"),
            "published": entry.get("published"),
            "updated": entry.get("updated"),
            "summary": entry.get("summary"),
            "tags": list(categories),
        }

        return FeedItem(
            source_name=source.name,
            guid=guid,
            url=url,
            canonical_url=url,
            title=title,
            published_at=published_at,
            categories=categories,
            raw=raw,
        )

    def _published_at(self, entry: Any) -> str | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            return f"{parsed.tm_year:04d}-{parsed.tm_mon:02d}-{parsed.tm_mday:02d}"

        raw_value = entry.get("published") or entry.get("updated")
        if not raw_value:
            return None

        try:
            return parsedate_to_datetime(raw_value).date().isoformat()
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
