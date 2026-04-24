# Autoblogger_AI-News

German AI news pipeline that tracks official AI company feeds, generates factual German summaries, and publishes WordPress drafts automatically.

## Proposed Directory Tree

```text
Autoblogger_AI-News/
  app/
    __init__.py
    main.py
    config.py
    logging_config.py
    models.py
    db.py
    sources.py
    feed_fetcher.py
    filters.py
    extractor.py
    summarizer.py
    wordpress.py
    pipeline.py
    utils.py
  data/
    autoblogger.sqlite3      # created at runtime
  .env.example
  requirements.txt
  README.md
```

## What This MVP Does

- Monitors a small hand-picked source registry.
- Parses RSS/Atom feeds with `feedparser`.
- Stores discovered and processed entries in SQLite.
- Applies only transparent hard filters for duplicates and obvious non-editorial pages.
- Extracts original article text with `trafilatura`.
- Generates a structured German summary through a summarizer abstraction.
- Creates WordPress draft posts through the WordPress REST API.
- Runs as a simple synchronous local CLI.

This is intentionally not a crawler, ranking system, queue system, vector system, or dashboard.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- Keep `SUMMARIZER_PROVIDER=stub` for local testing.
- Keep `WP_DRY_RUN=true` until WordPress credentials are ready.
- Set `WP_BASE_URL`, `WP_USERNAME`, and `WP_APPLICATION_PASSWORD` to create real drafts.

Initialize the database:

```bash
python -m app.main init-db
```

Show configured sources:

```bash
python -m app.main sources
```

Run the pipeline:

```bash
python -m app.main run
```

Check persisted status counts:

```bash
python -m app.main status
```

Run preflight checks before the content pipeline:

```bash
python -m app.main doctor
python -m app.main doctor --verbose
```

## Source Registry

Sources live in `app/sources.py`. The registry is deliberately small because every valid new entry from an active source is processed.

Only `OpenAI News` is active by default. Other sample primary-source entries are included as inactive placeholders and should be validated before activation. Do not activate broad feeds unless their full output belongs in the product.

## WordPress Notes

The publisher always sends `status=draft`. Optional category and tag support uses existing numeric WordPress IDs:

```env
WP_DEFAULT_CATEGORY_ID=12
WP_TAG_IDS=4,7,9
```

When `WP_DRY_RUN=true`, no remote post is created and the pipeline records a `dry_run` publish job.

## Summarization Notes

`app/summarizer.py` contains:

- `SUMMARY_PROMPT_TEMPLATE`, a strict German factual-summary prompt.
- `Summarizer`, the service interface.
- `StubSummarizer`, a deterministic local fallback.

The stub keeps the system runnable without an LLM key. Replace or extend `create_summarizer()` later with a real provider implementation that returns the same `GermanSummary` structure.

## Extension Notes

Paper summaries:
Add a separate source type and extractor path for PDFs or paper metadata. Keep it separate from company news feeds so the MVP feed pipeline stays predictable.

Image generation:
Add a media service after summarization and before WordPress publishing. Store generated media IDs in a new table or in `publish_jobs` metadata.

Auto-publish rules:
Keep drafts as the default. Add explicit rule checks and an allowlist before changing WordPress status from `draft` to `publish`.

More sources:
Add new `SourceConfig` entries with `active=False`, validate feed quality manually, then activate. Prefer official company blogs, official research feeds, or official newsroom feeds only.
