# Autoblogger_AI-News

Autoblogger_AI-News is a local-first Python MVP for turning hand-picked official AI company RSS/Atom feeds into German WordPress articles. It discovers new entries from approved primary sources, extracts the article text, generates a factual German summary, optionally generates a featured image, and creates a WordPress post through the REST API.

The project is intended for developers and editors who want a review-first automation pipeline for a German AI news site. It is deliberately not a broad web crawler, ranking system, dashboard, queue system, or social publishing tool.

## Features

- Hand-picked source registry in `app/sources.py` with active flags, source types, and URL/category filters.
- RSS/Atom parsing with `feedparser`.
- SQLite persistence for sources, feed entries, extracted articles, summaries, and publish jobs.
- Duplicate detection by source-local GUID, URL, and canonical URL.
- Transparent hard filters for obvious careers, jobs, events, legal, privacy, and unrelated URLs.
- Article fetching with browser-like headers and `trafilatura`-based text extraction.
- German summarizer abstraction with:
  - deterministic local stub provider for smoke tests,
  - OpenAI Responses API provider for structured German summaries.
- Validation for generated summary fields, safe simple HTML tags, category IDs, and common German umlaut transliteration mistakes.
- Optional OpenAI-assisted category selection from a predefined allowlist of existing WordPress category IDs.
- Optional OpenAI image generation for WordPress featured images.
- WordPress REST API publishing with configurable `draft` or `publish` post status.
- WordPress dry-run mode that skips remote post and media creation.
- `doctor` command for configuration, database, feed, extraction, summarizer, image, and WordPress readiness checks.

## Live Website / Demo

Generated or processed articles can be published to the public website [KI News Radar](https://ki-news-radar.de/). The site is used as the public output/demo target for articles prepared by this application through the WordPress REST API.

The repository supports both draft-first and direct publishing modes. Review-first draft publishing is the default and recommended local setup.

## Architecture and Project Structure

```text
Autoblogger_AI-News/
  app/
    main.py              # CLI entry point
    config.py            # .env and environment-based runtime settings
    logging_config.py    # logging setup
    models.py            # dataclasses shared across modules
    db.py                # SQLite schema and persistence gateway
    sources.py           # hand-picked source registry
    feed_fetcher.py      # RSS/Atom fetching and feed item normalization
    filters.py           # simple hard filters for feed entries
    extractor.py         # article download and trafilatura extraction
    summarizer.py        # stub and OpenAI German summarizer providers
    image_generator.py   # optional OpenAI featured image generation
    wordpress.py         # WordPress post and media REST API publisher
    doctor.py            # preflight/readiness checks
    pipeline.py          # synchronous processing pipeline
    utils.py             # shared utility helpers
  data/
    autoblogger.sqlite3  # local SQLite database path used by default
  .env.example           # documented environment template
  requirements.txt       # Python dependencies
  README.md
```

There is no Docker setup, JavaScript package file, deployment manifest, or configured test framework in the repository at the moment.

## Installation

### Prerequisites

- Python 3.11 or newer.
- `pip`.
- Network access for feed fetching, article extraction, OpenAI calls, and WordPress publishing.
- A WordPress site with REST API access and an Application Password if real publishing is enabled.
- An OpenAI API key only if `SUMMARIZER_PROVIDER=openai` or OpenAI image generation is enabled.

### Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

If your system exposes Python 3.11 as `python` instead of `python3.11`, use:

```bash
python -m venv .venv
```

## Configuration

Runtime configuration is loaded from environment variables. The project uses `python-dotenv`, so local development should normally use a `.env` file copied from `.env.example`.

Never commit `.env`; it may contain API keys, WordPress credentials, and other secrets.

### Core Settings

```env
DATABASE_PATH=data/autoblogger.sqlite3
HTTP_TIMEOUT_SECONDS=20
HTTP_USER_AGENT=AutobloggerAI-News/0.1 (+https://example.com; contact@example.com)
MAX_ARTICLES_PER_RUN=20
MAX_ARTICLES_PER_SOURCE_PER_RUN=5
MIN_EXTRACTED_CHARS=500
```

`MAX_ARTICLES_PER_RUN` is the global per-run limit. `MAX_ARTICLES_PER_SOURCE_PER_RUN` prevents one active source from consuming the whole run.

### Summarization

For local smoke tests, keep the stub provider:

```env
SUMMARIZER_PROVIDER=stub
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
OPENAI_MAX_INPUT_CHARS=30000
OPENAI_REQUEST_TIMEOUT_SECONDS=60
```

To enable real German summaries:

```env
SUMMARIZER_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.4-mini
```

Generated German text is expected to use real UTF-8 umlauts and `ß`, for example `Künstliche Intelligenz`, not ASCII transliterations.

### WordPress

Dry-run mode is enabled by default. In dry-run mode, the pipeline processes articles but does not create remote WordPress posts or upload media.

```env
WP_DRY_RUN=true
WP_POST_STATUS=draft
WP_BASE_URL=https://your-wordpress-site.example
WP_USERNAME=your-wordpress-username
WP_APPLICATION_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
```

Allowed post statuses are:

- `draft` for review-first operation.
- `publish` for immediate live publishing.

Use `publish` only after sources, summaries, categories, and WordPress credentials have been verified.

### WordPress Categories and Tags

The app can attach existing WordPress category and tag IDs. It does not create taxonomy terms.

```env
WP_DEFAULT_CATEGORY_ID=
WP_TAG_IDS=
```

Examples:

```env
WP_DEFAULT_CATEGORY_ID=12
WP_TAG_IDS=4,7,9
```

WordPress category and tag IDs can be found in WordPress admin URLs or through the WordPress REST API.

### Optional AI Category Classification

When enabled, the OpenAI summarizer may choose 1 to 3 category IDs from a fixed allowlist. The category names may be German, but the model must return only numeric IDs.

```env
AI_CATEGORY_CLASSIFICATION_ENABLED=false
AI_ALLOWED_CATEGORIES=
```

Example:

```env
AI_CATEGORY_CLASSIFICATION_ENABLED=true
AI_ALLOWED_CATEGORIES=5:KI-News,6:Modelle,7:Forschung,8:Tools,9:Sicherheit,10:Audio & Video,11:Robotik,12:Unternehmen,13:Open Source,14:Regulierung
```

Invalid or empty AI category output is ignored. If `WP_DEFAULT_CATEGORY_ID` is configured, it is used as the fallback.

### Optional Featured Image Generation

Image generation is disabled by default.

```env
IMAGE_GENERATION_ENABLED=false
IMAGE_PROVIDER=openai
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=medium
OPENAI_IMAGE_STYLE=editorial
OPENAI_IMAGE_TIMEOUT_SECONDS=90
OPENAI_IMAGE_PROMPT_MAX_CHARS=4000
OPENAI_IMAGE_SAVE_LOCAL_COPY=false
OPENAI_IMAGE_OUTPUT_DIR=data/generated_images
```

When enabled with `IMAGE_PROVIDER=openai`, the pipeline reuses `OPENAI_API_KEY`. It generates one editorial illustration per article, uploads it to the WordPress media library when `WP_DRY_RUN=false`, and sends the returned media ID as `featured_media`.

Image generation and upload are non-blocking. If either step fails, the article can still be created without a featured image.

## Local Usage

Initialize the SQLite schema and sync the source registry:

```bash
python -m app.main init-db
```

Print configured sources:

```bash
python -m app.main sources
```

Run readiness checks:

```bash
python -m app.main doctor
python -m app.main doctor --verbose
```

Run one synchronous pipeline pass:

```bash
python -m app.main run
```

Print stored status counts:

```bash
python -m app.main status
```

Change log verbosity:

```bash
python -m app.main --log-level DEBUG run
```

## Tests and Quality Checks

No automated test suite is currently present in the repository.

The basic available quality check is Python compilation:

```bash
python -m compileall app
```

The preflight command is also useful before a real run:

```bash
python -m app.main doctor --verbose
```

No formatter, linter, or type-checking command is configured in repository metadata.

## Internal Workflow

The application runs as a simple synchronous CLI pipeline:

1. Load settings from `.env` and process environment variables.
2. Initialize the SQLite schema if needed and sync `app/sources.py` into the `sources` table.
3. Load active sources from SQLite.
4. Fetch each active RSS/Atom feed with `FeedFetcher`.
5. Normalize feed entries into `FeedItem` dataclasses.
6. Apply hard filters from `filters.py`.
7. Insert new entries into SQLite; duplicates are skipped.
8. Fetch the original article page and extract main text with `ArticleExtractor`.
9. Save extracted article data and mark the feed entry as `extracted`.
10. Generate a German summary with the configured summarizer provider.
11. Validate summary structure, safe HTML, tags, category IDs, and common umlaut transliteration mistakes.
12. Optionally generate one editorial image with `image_generator.py`.
13. If not in WordPress dry-run mode, optionally upload the image to WordPress media.
14. Create a WordPress post with configured status, category IDs, tag IDs, and featured media ID when available.
15. Store the publish result in SQLite and update feed entry status.

Failures are handled per article where possible. Extraction, summarization, and publishing failures are logged and persisted without stopping the whole run.

## Doctor Command

`python -m app.main doctor` performs read-only readiness checks for:

- core configuration and dependencies,
- SQLite path and schema,
- source registry validity,
- RSS feed reachability,
- sample extraction viability,
- summarizer provider configuration,
- image generation configuration,
- WordPress dry-run, REST API, and authentication state.

Use `--verbose` to show all detail lines for each check.

## Source Registry

Sources are defined in `app/sources.py`. The registry is intentionally small because every valid new entry from an active source is processed.

The current registry includes active official or primary-source feeds such as Google DeepMind, Meta Engineering, Hugging Face Blog, Microsoft AI Blog, Microsoft Research, NVIDIA Blog, and NVIDIA Technical Blog. Some entries, such as OpenAI News and Anthropic Newsroom, are present but inactive by default in the current code.

Before activating a new source, verify that the feed is official, that its entries are appropriate for the site, and that the URL filters are narrow enough for the product.

## Current Status

This project is a production-leaning MVP. It has a real synchronous pipeline, SQLite persistence, a doctor command, OpenAI summarization support, optional image generation, and WordPress REST publishing.

It is not production-complete. Visible limitations include:

- no automated test suite,
- no scheduler or background worker,
- no dashboard or web UI,
- no migration framework beyond schema creation in `db.py`,
- no automatic WordPress taxonomy creation,
- no broad crawler or relevance scoring,
- no Docker or deployment configuration.

The default configuration is intentionally safe: WordPress dry-run is enabled, post status defaults to `draft`, the summarizer defaults to `stub`, and image generation is disabled.

## Roadmap and Possible Improvements

Grounded next steps for this codebase could include:

- Add focused unit tests for configuration parsing, filters, source validation, summarizer validation, and WordPress payload construction.
- Add integration tests with mocked RSS feeds, article HTML, OpenAI responses, and WordPress REST responses.
- Add a simple migration mechanism if the SQLite schema evolves further.
- Store generated image metadata or upload status in SQLite if editorial image workflows become important.
- Add more official sources only after manual feed validation.
- Add separate paper-summary support through a dedicated source type and extractor path.
- Add explicit auto-publish rules while keeping `draft` as the default.

## License

No license specified yet.
