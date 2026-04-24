"""CLI entrypoint.

Run with:
    python -m app.main run
"""

from __future__ import annotations

import argparse
import json
import logging

from app.config import load_settings
from app.db import Database
from app.doctor import Doctor, render_report
from app.logging_config import configure_logging
from app.sources import SOURCES

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="German AI news autoblogger MVP")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Fetch feeds, summarize new entries, and create WordPress drafts")
    subparsers.add_parser("init-db", help="Initialize SQLite schema and source registry")
    subparsers.add_parser("sources", help="Print configured source registry")
    subparsers.add_parser("status", help="Print stored status counts")
    doctor_parser = subparsers.add_parser("doctor", help="Run system readiness checks")
    doctor_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print all detail lines for each readiness check",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    settings = load_settings()
    database = Database(settings.database_path)

    if args.command == "init-db":
        database.initialize()
        database.upsert_sources(SOURCES)
        logger.info("Initialized database and synced sources")
        return

    if args.command == "sources":
        print(json.dumps([source.__dict__ for source in SOURCES], indent=2, default=list))
        return

    if args.command == "status":
        database.initialize()
        print(json.dumps(database.get_counts_by_status(), indent=2))
        return

    if args.command == "doctor":
        report = Doctor(settings=settings, sources=SOURCES).run()
        print(render_report(report, verbose=args.verbose))
        return

    if args.command == "run":
        from app.extractor import ArticleExtractor
        from app.feed_fetcher import FeedFetcher
        from app.image_generator import create_image_generator
        from app.pipeline import NewsPipeline
        from app.summarizer import create_summarizer
        from app.wordpress import WordPressPublisher

        summarizer = create_summarizer(settings)
        pipeline = NewsPipeline(
            settings=settings,
            database=database,
            feed_fetcher=FeedFetcher(settings.http_timeout_seconds, settings.user_agent),
            extractor=ArticleExtractor(
                settings.http_timeout_seconds,
                settings.user_agent,
                settings.min_extracted_chars,
            ),
            summarizer=summarizer,
            image_generator=create_image_generator(settings),
            publisher=WordPressPublisher(settings),
        )
        pipeline.run()
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
