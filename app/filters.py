"""Transparent hard filters for source feed entries."""

from __future__ import annotations

import re

from app.models import FeedItem, FilterResult, SourceConfig


GENERIC_EXCLUDED_TERMS = (
    "career",
    "careers",
    "hiring",
    "job",
    "jobs",
    "event",
    "events",
    "webinar",
    "conference",
    "terms",
    "privacy",
    "legal",
)


def should_process_entry(source: SourceConfig, item: FeedItem) -> FilterResult:
    url = item.canonical_url or item.url
    title_lower = item.title.lower()

    if source.allowed_url_patterns and not any(
        re.search(pattern, url) for pattern in source.allowed_url_patterns
    ):
        return FilterResult(False, "URL does not match source allowed patterns")

    for pattern in source.excluded_url_patterns:
        if re.search(pattern, url):
            return FilterResult(False, f"URL matches excluded pattern: {pattern}")

    if any(category in source.excluded_categories for category in item.categories):
        return FilterResult(False, "Entry category is excluded for this source")

    for term in GENERIC_EXCLUDED_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", title_lower):
            return FilterResult(False, f"Title contains excluded term: {term}")

    return FilterResult(True)

