"""Preflight checks for the local news pipeline."""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from importlib.util import find_spec
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    import requests
except ImportError:
    requests = None

from app.config import Settings
from app.models import FeedItem, SourceConfig


EXPECTED_TABLES = {"sources", "feed_entries", "articles", "publish_jobs"}
REAL_SUMMARIZER_CREDENTIALS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


class CheckStatus(Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    summary: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DoctorReport:
    checks: list[CheckResult]

    @property
    def counts(self) -> Counter[CheckStatus]:
        return Counter(
            check.status for check in self.checks if check.name != "Readiness"
        )

    @property
    def readiness(self) -> str:
        if self.counts[CheckStatus.FAIL]:
            return "NOT READY"
        if self.counts[CheckStatus.WARN]:
            return "READY WITH WARNINGS"
        return "READY"


@dataclass
class DoctorContext:
    """Shared state between checks that naturally build on each other."""

    feed_samples: dict[str, FeedItem] = field(default_factory=dict)


class Doctor:
    """Run read-only readiness checks without changing pipeline state."""

    def __init__(self, settings: Settings, sources: tuple[SourceConfig, ...]) -> None:
        self.settings = settings
        self.sources = sources
        self.context = DoctorContext()
        self.session = requests.Session() if requests is not None else None
        if self.session is not None:
            self.session.headers.update({"User-Agent": settings.user_agent})

    def run(self) -> DoctorReport:
        checks = [
            self.check_configuration(),
            self.check_database(),
            self.check_source_registry(),
            self.check_rss_feeds(),
            self.check_extraction(),
            self.check_summarizer(),
            self.check_wordpress(),
        ]
        checks.append(self.build_readiness_check(checks))
        return DoctorReport(checks)

    def check_configuration(self) -> CheckResult:
        failures: list[str] = []
        warnings: list[str] = []
        details = ["Core settings loaded successfully"]

        if not Path(".env").exists():
            warnings.append("No .env file found; defaults and process environment will be used")
        missing_dependencies = self._missing_required_dependencies()
        if missing_dependencies:
            failures.append("Missing Python dependencies: " + ", ".join(missing_dependencies))
        if find_spec("dotenv") is None:
            warnings.append("python-dotenv is not installed; .env files will not be loaded")
        if self.settings.http_timeout_seconds <= 0:
            failures.append("HTTP_TIMEOUT_SECONDS must be greater than 0")
        if self.settings.max_articles_per_run <= 0:
            failures.append("MAX_ARTICLES_PER_RUN must be greater than 0")
        if self.settings.min_extracted_chars <= 0:
            failures.append("MIN_EXTRACTED_CHARS must be greater than 0")
        if not str(self.settings.database_path):
            failures.append("DATABASE_PATH is empty")
        if not self.settings.user_agent.strip():
            failures.append("HTTP_USER_AGENT is empty")

        if self.settings.wordpress_dry_run:
            details.append("WordPress dry-run mode enabled; credentials are optional")
        else:
            missing_wp = self._missing_wordpress_settings()
            if missing_wp:
                failures.append(
                    "WordPress publishing is enabled but missing: " + ", ".join(missing_wp)
                )

        provider = self.settings.summarizer_provider
        if provider == "stub":
            details.append("SUMMARIZER_PROVIDER=stub")
        else:
            missing_credentials = self._missing_summarizer_credentials(provider)
            if missing_credentials:
                failures.append(
                    f"SUMMARIZER_PROVIDER={provider} is missing credentials: "
                    + ", ".join(missing_credentials)
                )
            failures.append(
                f"SUMMARIZER_PROVIDER={provider} is not implemented by this MVP"
            )

        details.extend(warnings)
        details.extend(failures)
        return CheckResult(
            name="Configuration",
            status=self._status(failures, warnings),
            summary=self._summary("Configuration is usable", warnings, failures),
            details=details,
        )

    def check_database(self) -> CheckResult:
        db_path = self.settings.database_path
        if db_path.exists() and db_path.is_dir():
            return CheckResult(
                "Database",
                CheckStatus.FAIL,
                "SQLite path points to a directory",
                [str(db_path)],
            )

        if not db_path.exists():
            return self._check_missing_database_path(db_path)

        try:
            with sqlite3.connect(db_path) as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()
                table_rows = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
        except sqlite3.Error as exc:
            return CheckResult(
                "Database",
                CheckStatus.FAIL,
                "SQLite database cannot be opened",
                [str(exc)],
            )

        existing_tables = {row[0] for row in table_rows}
        missing_tables = sorted(EXPECTED_TABLES - existing_tables)
        details = [f"SQLite file opens successfully: {db_path}"]
        if quick_check:
            details.append(f"SQLite quick_check: {quick_check[0]}")

        if missing_tables:
            details.append("Missing tables: " + ", ".join(missing_tables))
            return CheckResult(
                "Database",
                CheckStatus.WARN,
                "Database exists but schema is not initialized",
                details + ["Run: python -m app.main init-db"],
            )

        return CheckResult(
            "Database",
            CheckStatus.OK,
            "SQLite database is initialized",
            details,
        )

    def check_source_registry(self) -> CheckResult:
        failures: list[str] = []
        warnings: list[str] = []

        names = [source.name for source in self.sources]
        feed_urls = [source.feed_url for source in self.sources]
        duplicate_names = sorted(_duplicates(names))
        duplicate_feed_urls = sorted(_duplicates(feed_urls))

        if duplicate_names:
            failures.append("Duplicate source names: " + ", ".join(duplicate_names))
        if duplicate_feed_urls:
            failures.append("Duplicate feed URLs: " + ", ".join(duplicate_feed_urls))

        invalid_sources = 0
        for source in self.sources:
            source_errors = self._source_validation_errors(source)
            if source_errors:
                invalid_sources += 1
                failures.extend(f"{source.name}: {error}" for error in source_errors)

        active_count = sum(1 for source in self.sources if source.active)
        if active_count == 0:
            failures.append("No active sources configured")

        details = [
            f"{len(self.sources)} sources configured",
            f"{active_count} active sources",
            f"{invalid_sources} invalid sources",
        ]
        details.extend(warnings)
        details.extend(failures)
        return CheckResult(
            "Source registry",
            self._status(failures, warnings),
            self._summary("Source registry is valid", warnings, failures),
            details,
        )

    def check_rss_feeds(self) -> CheckResult:
        active_sources = [source for source in self.sources if source.active]
        if not active_sources:
            return CheckResult(
                "RSS feeds",
                CheckStatus.FAIL,
                "No active sources to check",
                ["Enable at least one source in app/sources.py"],
            )

        failures: list[str] = []
        warnings: list[str] = []
        details: list[str] = []
        working_count = 0

        for source in active_sources:
            source_status, message, sample_item = self._check_one_feed(source)
            details.append(f"{source.name}: {source_status.value} ({message})")
            if sample_item:
                self.context.feed_samples[source.name] = sample_item
            if source_status == CheckStatus.OK:
                working_count += 1
            elif source_status == CheckStatus.WARN:
                warnings.append(f"{source.name}: {message}")
            else:
                failures.append(f"{source.name}: {message}")

        details.append(f"{working_count}/{len(active_sources)} active feeds working")
        return CheckResult(
            "RSS feeds",
            self._status(failures, warnings),
            f"{working_count}/{len(active_sources)} active feeds working",
            details,
        )

    def check_extraction(self) -> CheckResult:
        if not self.context.feed_samples:
            return CheckResult(
                "Extraction",
                CheckStatus.FAIL,
                "No reachable feed samples available for extraction",
                ["Fix RSS feed failures before checking article extraction"],
            )

        try:
            from app.extractor import ArticleExtractor, ExtractionError
        except ImportError as exc:
            return CheckResult(
                "Extraction",
                CheckStatus.FAIL,
                "Extraction dependencies are not installed",
                [str(exc), "Install requirements.txt before running the pipeline"],
            )

        extractor = ArticleExtractor(
            timeout_seconds=self.settings.http_timeout_seconds,
            user_agent=self.settings.user_agent,
            min_chars=self.settings.min_extracted_chars,
        )
        failures: list[str] = []
        warnings: list[str] = []
        details: list[str] = []
        success_count = 0

        for source_name, item in self.context.feed_samples.items():
            try:
                article = extractor.extract(item)
            except ExtractionError as exc:
                failures.append(f"{source_name}: {exc}")
                details.append(f"{source_name}: FAIL ({exc})")
                continue

            text_length = len(article.text)
            if text_length < self.settings.min_extracted_chars * 2:
                warnings.append(f"{source_name}: extracted text is short ({text_length} chars)")
                details.append(f"{source_name}: WARN ({text_length} chars extracted)")
            else:
                success_count += 1
                details.append(f"{source_name}: OK ({text_length} chars extracted)")

        total = len(self.context.feed_samples)
        return CheckResult(
            "Extraction",
            self._status(failures, warnings),
            f"{success_count}/{total} sample articles extracted cleanly",
            details,
        )

    def check_summarizer(self) -> CheckResult:
        provider = self.settings.summarizer_provider
        if provider == "stub":
            return CheckResult(
                "Summarizer",
                CheckStatus.WARN,
                "Stub summarizer active; no external LLM configured",
                ["Mode: stub", "Pipeline is runnable, but summaries are placeholder drafts"],
            )

        missing_credentials = self._missing_summarizer_credentials(provider)
        details = [f"Mode: {provider}"]
        if missing_credentials:
            details.append("Missing credentials: " + ", ".join(missing_credentials))
        details.append("This MVP currently implements only the stub summarizer")

        return CheckResult(
            "Summarizer",
            CheckStatus.FAIL,
            f"Summarizer provider {provider!r} is not ready",
            details,
        )

    def check_wordpress(self) -> CheckResult:
        if self.settings.wordpress_dry_run:
            details = ["WP_DRY_RUN=true; no WordPress write check will be performed"]
            if self.settings.wordpress_base_url:
                details.extend(self._check_wordpress_reachability(auth_required=False))
            else:
                details.append("WP_BASE_URL is not configured, which is acceptable in dry-run mode")
            return CheckResult(
                "WordPress",
                CheckStatus.WARN,
                "Dry-run mode enabled; drafts will not be created remotely",
                details,
            )

        missing_settings = self._missing_wordpress_settings()
        if missing_settings:
            return CheckResult(
                "WordPress",
                CheckStatus.FAIL,
                "WordPress publishing enabled but configuration is incomplete",
                ["Missing: " + ", ".join(missing_settings)],
            )

        details = self._check_wordpress_reachability(auth_required=True)
        failures = [detail for detail in details if detail.startswith("FAIL:")]
        warnings = [detail for detail in details if detail.startswith("WARN:")]
        return CheckResult(
            "WordPress",
            self._status(failures, warnings),
            self._summary("WordPress REST API is reachable", warnings, failures),
            details,
        )

    def build_readiness_check(self, checks: Iterable[CheckResult]) -> CheckResult:
        counts = Counter(check.status for check in checks)
        if counts[CheckStatus.FAIL]:
            status = CheckStatus.FAIL
            summary = "System is not ready; fix FAIL checks before running the pipeline"
        elif counts[CheckStatus.WARN]:
            status = CheckStatus.WARN
            summary = "System runnable with warnings"
        else:
            status = CheckStatus.OK
            summary = "System ready"

        details = [
            f"OK: {counts[CheckStatus.OK]}",
            f"WARN: {counts[CheckStatus.WARN]}",
            f"FAIL: {counts[CheckStatus.FAIL]}",
        ]
        return CheckResult("Readiness", status, summary, details)

    def _check_missing_database_path(self, db_path: Path) -> CheckResult:
        parent = db_path.parent if str(db_path.parent) else Path(".")
        nearest_existing_parent = _nearest_existing_parent(parent)
        if nearest_existing_parent is None:
            return CheckResult(
                "Database",
                CheckStatus.FAIL,
                "No existing parent directory found for SQLite path",
                [str(db_path)],
            )

        if not os.access(nearest_existing_parent, os.W_OK):
            return CheckResult(
                "Database",
                CheckStatus.FAIL,
                "SQLite path is not currently writable",
                [f"Nearest existing parent is not writable: {nearest_existing_parent}"],
            )

        return CheckResult(
            "Database",
            CheckStatus.WARN,
            "SQLite file does not exist yet, but path appears creatable",
            [str(db_path), "Run: python -m app.main init-db"],
        )

    def _check_one_feed(
        self, source: SourceConfig
    ) -> tuple[CheckStatus, str, FeedItem | None]:
        if requests is None or self.session is None:
            return CheckStatus.FAIL, "requests is not installed", None
        if feedparser is None:
            return CheckStatus.FAIL, "feedparser is not installed", None

        try:
            response = self.session.get(
                source.feed_url,
                timeout=self.settings.http_timeout_seconds,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return CheckStatus.FAIL, _short_error(exc), None

        parsed_feed = feedparser.parse(response.content)
        entries = list(parsed_feed.entries)
        if parsed_feed.bozo and not entries:
            bozo_reason = getattr(parsed_feed, "bozo_exception", "parse warning")
            return CheckStatus.FAIL, f"feed is not parseable: {bozo_reason}", None

        if not entries:
            return CheckStatus.WARN, "feed parsed but contains no entries", None

        from app.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher(self.settings.http_timeout_seconds, self.settings.user_agent)
        sample_item = fetcher.parse_entry(source, entries[0])
        if sample_item is None:
            return CheckStatus.WARN, "feed has entries but no usable article link", None

        if parsed_feed.bozo:
            bozo_reason = getattr(parsed_feed, "bozo_exception", "parse warning")
            return (
                CheckStatus.WARN,
                f"{len(entries)} entries found, but parser reported: {bozo_reason}",
                sample_item,
            )

        return CheckStatus.OK, f"{len(entries)} entries found", sample_item

    def _check_wordpress_reachability(self, auth_required: bool) -> list[str]:
        if requests is None or self.session is None:
            return ["FAIL: requests is not installed"]

        base_url = self.settings.wordpress_base_url
        if not base_url:
            return ["FAIL: WP_BASE_URL is not configured"]

        details: list[str] = []
        api_root = urljoin(base_url.rstrip("/") + "/", "wp-json/")
        posts_endpoint = urljoin(base_url.rstrip("/") + "/", "wp-json/wp/v2/posts")
        current_user_endpoint = urljoin(base_url.rstrip("/") + "/", "wp-json/wp/v2/users/me")
        request_auth = None
        if auth_required:
            request_auth = (
                self.settings.wordpress_username,
                self.settings.wordpress_application_password,
            )

        try:
            root_response = self.session.get(api_root, timeout=self.settings.http_timeout_seconds)
            root_response.raise_for_status()
            details.append("OK: REST API root reachable")
        except requests.RequestException as exc:
            return [f"FAIL: REST API unavailable: {_short_error(exc)}"]

        if auth_required:
            try:
                user_response = self.session.get(
                    current_user_endpoint,
                    auth=request_auth,
                    timeout=self.settings.http_timeout_seconds,
                )
            except requests.RequestException as exc:
                return details + [f"FAIL: auth check failed: {_short_error(exc)}"]

            if user_response.status_code in {401, 403}:
                return details + [f"FAIL: authentication failed ({user_response.status_code})"]
            if user_response.status_code >= 400:
                return details + [f"FAIL: user auth endpoint returned {user_response.status_code}"]
            details.append("OK: authentication accepted by users/me endpoint")

        try:
            options_response = self.session.options(
                posts_endpoint,
                auth=request_auth,
                timeout=self.settings.http_timeout_seconds,
            )
        except requests.RequestException as exc:
            return details + [f"FAIL: posts endpoint unreachable: {_short_error(exc)}"]

        if auth_required and options_response.status_code in {401, 403}:
            return details + [f"FAIL: authentication failed ({options_response.status_code})"]
        if options_response.status_code >= 400:
            return details + [f"FAIL: posts endpoint returned {options_response.status_code}"]

        details.append("OK: posts endpoint responds to OPTIONS")
        details.extend(self._check_wordpress_taxonomies(request_auth))
        details.append("WARN: doctor does not create a test post; draft creation is inferred from REST permissions")
        return details

    def _check_wordpress_taxonomies(self, auth: tuple[str | None, str | None] | None) -> list[str]:
        base_url = self.settings.wordpress_base_url
        if not base_url:
            return []

        details: list[str] = []
        if self.settings.wordpress_default_category_id is not None:
            endpoint = urljoin(
                base_url.rstrip("/") + "/",
                f"wp-json/wp/v2/categories/{self.settings.wordpress_default_category_id}",
            )
            details.append(self._check_wordpress_lookup(endpoint, auth, "default category"))

        for tag_id in self.settings.wordpress_tag_ids:
            endpoint = urljoin(base_url.rstrip("/") + "/", f"wp-json/wp/v2/tags/{tag_id}")
            details.append(self._check_wordpress_lookup(endpoint, auth, f"tag {tag_id}"))

        return details

    def _check_wordpress_lookup(
        self,
        endpoint: str,
        auth: tuple[str | None, str | None] | None,
        label: str,
    ) -> str:
        if requests is None or self.session is None:
            return f"FAIL: could not validate {label}: requests is not installed"

        try:
            response = self.session.get(
                endpoint,
                auth=auth,
                timeout=self.settings.http_timeout_seconds,
            )
        except requests.RequestException as exc:
            return f"WARN: could not validate {label}: {_short_error(exc)}"

        if response.status_code == 404:
            return f"FAIL: configured {label} does not exist"
        if response.status_code >= 400:
            return f"WARN: could not validate {label}: HTTP {response.status_code}"
        return f"OK: configured {label} exists"

    def _source_validation_errors(self, source: SourceConfig) -> list[str]:
        errors: list[str] = []
        parsed_url = urlparse(source.feed_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            errors.append(f"feed URL is not plausible: {source.feed_url}")

        for label, patterns in (
            ("allowed_url_patterns", source.allowed_url_patterns),
            ("excluded_url_patterns", source.excluded_url_patterns),
        ):
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"{label} contains invalid regex {pattern!r}: {exc}")
        return errors

    def _missing_wordpress_settings(self) -> list[str]:
        missing: list[str] = []
        if not self.settings.wordpress_base_url:
            missing.append("WP_BASE_URL")
        if not self.settings.wordpress_username:
            missing.append("WP_USERNAME")
        if not self.settings.wordpress_application_password:
            missing.append("WP_APPLICATION_PASSWORD")
        return missing

    def _missing_summarizer_credentials(self, provider: str) -> list[str]:
        required_names = REAL_SUMMARIZER_CREDENTIALS.get(provider, (f"{provider.upper()}_API_KEY",))
        return [name for name in required_names if not os.getenv(name)]

    def _missing_required_dependencies(self) -> list[str]:
        return [
            package_name
            for package_name in ("requests", "feedparser", "trafilatura")
            if find_spec(package_name) is None
        ]

    def _status(self, failures: list[str], warnings: list[str]) -> CheckStatus:
        if failures:
            return CheckStatus.FAIL
        if warnings:
            return CheckStatus.WARN
        return CheckStatus.OK

    def _summary(self, ok_summary: str, warnings: list[str], failures: list[str]) -> str:
        if failures:
            return failures[0]
        if warnings:
            return warnings[0]
        return ok_summary


def render_report(report: DoctorReport, verbose: bool = False) -> str:
    """Render doctor results for a plain terminal."""
    lines: list[str] = []
    total = len(report.checks)
    for index, check in enumerate(report.checks, start=1):
        heading = f"[{index}/{total}] {check.name}"
        lines.append(f"{heading:.<42} {check.status.value}")
        lines.append(f"       {check.summary}")
        for detail in _visible_details(check.details, verbose):
            lines.append(f"       {detail}")
        lines.append("")

    counts = report.counts
    lines.append(
        "Summary: "
        f"{report.readiness} "
        f"({counts[CheckStatus.OK]} OK, "
        f"{counts[CheckStatus.WARN]} WARN, "
        f"{counts[CheckStatus.FAIL]} FAIL)"
    )
    return "\n".join(lines).rstrip()


def _visible_details(details: list[str], verbose: bool) -> list[str]:
    if verbose or len(details) <= 4:
        return details
    hidden_count = len(details) - 4
    return details[:4] + [f"... {hidden_count} more detail(s); rerun with --verbose"]


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _nearest_existing_parent(path: Path) -> Path | None:
    current = path
    while not current.exists():
        if current.parent == current:
            return None
        current = current.parent
    return current if current.is_dir() else current.parent


def _short_error(exc: BaseException) -> str:
    message = str(exc)
    return message if len(message) <= 180 else message[:177] + "..."
