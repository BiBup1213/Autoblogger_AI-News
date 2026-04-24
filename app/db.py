"""SQLite persistence layer."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from app.models import ArticleContent, FeedItem, GermanSummary, SourceConfig
from app.utils import utc_now_iso

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    feed_url TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    allowed_url_patterns TEXT NOT NULL DEFAULT '[]',
                    excluded_url_patterns TEXT NOT NULL DEFAULT '[]',
                    excluded_categories TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feed_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    guid TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    canonical_url TEXT,
                    title TEXT NOT NULL,
                    published_at TEXT,
                    categories TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'discovered',
                    failure_reason TEXT,
                    raw_data TEXT NOT NULL DEFAULT '{}',
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_id, guid)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_feed_entries_canonical_url
                ON feed_entries(canonical_url)
                WHERE canonical_url IS NOT NULL;

                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_entry_id INTEGER NOT NULL UNIQUE REFERENCES feed_entries(id) ON DELETE CASCADE,
                    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    original_url TEXT NOT NULL,
                    canonical_url TEXT,
                    original_title TEXT NOT NULL,
                    published_at TEXT,
                    extracted_text TEXT,
                    extraction_status TEXT NOT NULL DEFAULT 'pending',
                    german_title TEXT,
                    german_excerpt TEXT,
                    german_body_html TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    summary_status TEXT NOT NULL DEFAULT 'pending',
                    failure_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS publish_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL UNIQUE REFERENCES articles(id) ON DELETE CASCADE,
                    wordpress_post_id INTEGER,
                    wordpress_url TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    failure_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
        logger.info("SQLite database initialized at %s", self.path)

    def upsert_sources(self, sources: Iterable[SourceConfig]) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            for source in sources:
                connection.execute(
                    """
                    INSERT INTO sources (
                        name, feed_url, source_type, active, allowed_url_patterns,
                        excluded_url_patterns, excluded_categories, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        feed_url = excluded.feed_url,
                        source_type = excluded.source_type,
                        active = excluded.active,
                        allowed_url_patterns = excluded.allowed_url_patterns,
                        excluded_url_patterns = excluded.excluded_url_patterns,
                        excluded_categories = excluded.excluded_categories,
                        updated_at = excluded.updated_at
                    """,
                    (
                        source.name,
                        source.feed_url,
                        source.source_type,
                        int(source.active),
                        json.dumps(list(source.allowed_url_patterns)),
                        json.dumps(list(source.excluded_url_patterns)),
                        json.dumps(list(source.excluded_categories)),
                        now,
                        now,
                    ),
                )

    def get_active_sources(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM sources WHERE active = 1 ORDER BY name"
                ).fetchall()
            )

    def insert_feed_entry(self, source_id: int, item: FeedItem) -> int | None:
        now = utc_now_iso()
        with self.connect() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO feed_entries (
                        source_id, guid, url, canonical_url, title, published_at,
                        categories, raw_data, discovered_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        item.guid,
                        item.url,
                        item.canonical_url,
                        item.title,
                        item.published_at,
                        json.dumps(list(item.categories)),
                        json.dumps(item.raw),
                        now,
                        now,
                    ),
                )
                return int(cursor.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def update_feed_entry_status(self, feed_entry_id: int, status: str, failure_reason: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE feed_entries
                SET status = ?, failure_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, failure_reason, utc_now_iso(), feed_entry_id),
            )

    def create_extracted_article(self, feed_entry_id: int, source_id: int, article: ArticleContent) -> int:
        now = utc_now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO articles (
                    feed_entry_id, source_id, original_url, canonical_url, original_title,
                    published_at, extracted_text, extraction_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'extracted', ?, ?)
                ON CONFLICT(feed_entry_id) DO UPDATE SET
                    canonical_url = excluded.canonical_url,
                    original_title = excluded.original_title,
                    published_at = excluded.published_at,
                    extracted_text = excluded.extracted_text,
                    extraction_status = 'extracted',
                    failure_reason = NULL,
                    updated_at = excluded.updated_at
                RETURNING id
                """,
                (
                    feed_entry_id,
                    source_id,
                    article.source_url,
                    article.canonical_url,
                    article.original_title,
                    article.published_at,
                    article.text,
                    now,
                    now,
                ),
            )
            row = cursor.fetchone()
            return int(row["id"])

    def mark_article_failed(self, feed_entry_id: int, source_id: int, original_url: str, title: str, reason: str) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO articles (
                    feed_entry_id, source_id, original_url, original_title,
                    extraction_status, summary_status, failure_reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'failed', 'pending', ?, ?, ?)
                ON CONFLICT(feed_entry_id) DO UPDATE SET
                    extraction_status = 'failed',
                    failure_reason = excluded.failure_reason,
                    updated_at = excluded.updated_at
                """,
                (feed_entry_id, source_id, original_url, title, reason, now, now),
            )

    def save_summary(self, article_id: int, summary: GermanSummary) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE articles
                SET german_title = ?, german_excerpt = ?, german_body_html = ?,
                    tags = ?, summary_status = 'summarized', failure_reason = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    summary.german_title,
                    summary.german_excerpt,
                    summary.german_body_html,
                    json.dumps(summary.tags),
                    utc_now_iso(),
                    article_id,
                ),
            )

    def create_or_update_publish_job(
        self,
        article_id: int,
        status: str,
        wordpress_post_id: int | None = None,
        wordpress_url: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        now = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO publish_jobs (
                    article_id, wordpress_post_id, wordpress_url, status,
                    failure_reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id) DO UPDATE SET
                    wordpress_post_id = excluded.wordpress_post_id,
                    wordpress_url = excluded.wordpress_url,
                    status = excluded.status,
                    failure_reason = excluded.failure_reason,
                    updated_at = excluded.updated_at
                """,
                (article_id, wordpress_post_id, wordpress_url, status, failure_reason, now, now),
            )

    def row_to_source_config(self, row: sqlite3.Row) -> SourceConfig:
        return SourceConfig(
            name=row["name"],
            feed_url=row["feed_url"],
            source_type=row["source_type"],
            active=bool(row["active"]),
            allowed_url_patterns=tuple(json.loads(row["allowed_url_patterns"])),
            excluded_url_patterns=tuple(json.loads(row["excluded_url_patterns"])),
            excluded_categories=tuple(json.loads(row["excluded_categories"])),
        )

    def get_counts_by_status(self) -> dict[str, Any]:
        with self.connect() as connection:
            entry_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM feed_entries GROUP BY status"
            ).fetchall()
            publish_rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM publish_jobs GROUP BY status"
            ).fetchall()
        return {
            "feed_entries": {row["status"]: row["count"] for row in entry_rows},
            "publish_jobs": {row["status"]: row["count"] for row in publish_rows},
        }

