"""Shared domain models for the news pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    name: str
    feed_url: str
    source_type: str
    active: bool = True
    allowed_url_patterns: tuple[str, ...] = ()
    excluded_url_patterns: tuple[str, ...] = ()
    excluded_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedItem:
    source_name: str
    guid: str
    url: str
    title: str
    published_at: str | None = None
    canonical_url: str | None = None
    categories: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    reason: str = ""


@dataclass(frozen=True)
class ArticleContent:
    source_name: str
    source_url: str
    original_title: str
    published_at: str | None
    text: str
    canonical_url: str | None = None


@dataclass(frozen=True)
class GermanSummary:
    german_title: str
    german_excerpt: str
    german_body_html: str
    source_name: str
    source_url: str
    original_title: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PublishResult:
    wordpress_post_id: int | None
    wordpress_url: str | None
    status: str

