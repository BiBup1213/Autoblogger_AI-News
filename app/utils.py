"""Small shared helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urldefrag, urlsplit, urlunsplit


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

