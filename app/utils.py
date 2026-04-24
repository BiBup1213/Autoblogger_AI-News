"""Small shared helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urldefrag, urlsplit, urlunsplit


DEFAULT_ACCEPT_LANGUAGE = "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
HTML_ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8"
)
FEED_ACCEPT_HEADER = (
    "application/rss+xml,application/atom+xml,application/xml;q=0.9,"
    "text/xml;q=0.8,*/*;q=0.7"
)


def build_http_headers(user_agent: str, accept: str = HTML_ACCEPT_HEADER) -> dict[str, str]:
    """Return conservative browser-like headers for approved source requests."""
    return {
        "User-Agent": user_agent,
        "Accept": accept,
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_url(url: str) -> str:
    """Normalize enough for deduplication without changing article identity."""
    url = urldefrag(url.strip())[0]
    parts = urlsplit(url)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "..."
