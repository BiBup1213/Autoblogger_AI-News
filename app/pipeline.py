"""Synchronous MVP pipeline."""

from __future__ import annotations

import logging

from app.config import Settings
from app.db import Database
from app.extractor import ArticleExtractor, ExtractionError
from app.feed_fetcher import FeedFetcher
from app.filters import should_process_entry
from app.image_generator import ImageGenerator
from app.models import FeedItem, SourceConfig
from app.sources import SOURCES
from app.summarizer import Summarizer
from app.wordpress import WordPressPublisher

logger = logging.getLogger(__name__)


class NewsPipeline:
    """Coordinate one synchronous pass through the approved source registry."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        feed_fetcher: FeedFetcher,
        extractor: ArticleExtractor,
        summarizer: Summarizer,
        image_generator: ImageGenerator,
        publisher: WordPressPublisher,
        sources: tuple[SourceConfig, ...] = SOURCES,
    ) -> None:
        self.settings = settings
        self.database = database
        self.feed_fetcher = feed_fetcher
        self.extractor = extractor
        self.summarizer = summarizer
        self.image_generator = image_generator
        self.publisher = publisher
        self.sources = sources

    def run(self) -> None:
        """Fetch active sources and process new accepted entries once."""
        self.database.initialize()
        self.database.upsert_sources(self.sources)

        active_source_rows = self.database.get_active_sources()
        logger.info("Processing %s active source(s)", len(active_source_rows))

        processed_count = 0
        for source_row in active_source_rows:
            if processed_count >= self.settings.max_articles_per_run:
                logger.info("Reached MAX_ARTICLES_PER_RUN=%s", self.settings.max_articles_per_run)
                break

            source_id = int(source_row["id"])
            source = self.database.row_to_source_config(source_row)
            logger.info("Fetching feed: %s", source.name)
            items = self.feed_fetcher.fetch(source)
            logger.info("Fetched %s item(s) from %s", len(items), source.name)
            source_processed_count = 0

            for item in items:
                if processed_count >= self.settings.max_articles_per_run:
                    break
                if source_processed_count >= self.settings.max_articles_per_source_per_run:
                    logger.info(
                        "Reached MAX_ARTICLES_PER_SOURCE_PER_RUN=%s for %s",
                        self.settings.max_articles_per_source_per_run,
                        source.name,
                    )
                    break

                filter_result = should_process_entry(source, item)
                if not filter_result.accepted:
                    logger.info("Skipped %s: %s", item.url, filter_result.reason)
                    continue

                feed_entry_id = self.database.insert_feed_entry(source_id, item)
                if feed_entry_id is None:
                    logger.debug("Duplicate feed entry skipped: %s", item.url)
                    continue

                processed_count += 1
                source_processed_count += 1
                self._process_entry(source_id, feed_entry_id, item)

            logger.info("Processed %s new article(s) from %s", source_processed_count, source.name)

        logger.info("Run finished. New entries processed: %s", processed_count)

    def _process_entry(self, source_id: int, feed_entry_id: int, item: FeedItem) -> None:
        """Process one newly inserted entry through all downstream stages."""
        try:
            article = self.extractor.extract(item)
            article_id = self.database.create_extracted_article(feed_entry_id, source_id, article)
            self.database.update_feed_entry_status(feed_entry_id, "extracted")
            logger.info("Extracted article: %s", article.original_title)
        except ExtractionError as exc:
            logger.warning("Extraction failed for %s: %s", item.url, exc)
            self.database.mark_article_failed(feed_entry_id, source_id, item.url, item.title, str(exc))
            self.database.update_feed_entry_status(feed_entry_id, "failed", str(exc))
            return

        try:
            summary = self.summarizer.summarize(article)
            self.database.save_summary(article_id, summary)
            self.database.update_feed_entry_status(feed_entry_id, "summarized")
            logger.info("Summary created: %s", summary.german_title)
        except Exception as exc:
            logger.exception("Summarization failed for %s", item.url)
            self.database.update_feed_entry_status(feed_entry_id, "failed", str(exc))
            return

        generated_image = None
        try:
            generated_image = self.image_generator.generate(summary)
            if generated_image is not None:
                logger.info(
                    "Generated featured image for %s at %s",
                    summary.german_title,
                    generated_image.local_file_path,
                )
        except Exception as exc:
            logger.warning("Image generation failed for %s: %s", summary.german_title, exc)

        try:
            publish_result = self.publisher.create_draft(summary, generated_image)
            self.database.create_or_update_publish_job(
                article_id=article_id,
                status=publish_result.status,
                wordpress_post_id=publish_result.wordpress_post_id,
                wordpress_url=publish_result.wordpress_url,
            )
            if publish_result.status in {"draft_created", "published"}:
                self.database.update_feed_entry_status(feed_entry_id, "published")
            logger.info("Publishing status for %s: %s", summary.german_title, publish_result.status)
        except Exception as exc:
            logger.exception("Publishing failed for %s", item.url)
            self.database.create_or_update_publish_job(
                article_id=article_id,
                status="failed",
                failure_reason=str(exc),
            )
            self.database.update_feed_entry_status(feed_entry_id, "failed", str(exc))
