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
- To use real German summaries, set `SUMMARIZER_PROVIDER=openai` and add `OPENAI_API_KEY`.
- Keep `WP_DRY_RUN=true` until WordPress credentials are ready.
- Set `WP_BASE_URL`, `WP_USERNAME`, and `WP_APPLICATION_PASSWORD` to create real drafts.
- Keep `WP_POST_STATUS=draft` until you intentionally want immediate live publishing.
- Never commit `.env`; it contains secrets.

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

The publisher sends the configured `WP_POST_STATUS`. Use `draft` for review-first operation and `publish` only when the source list, summaries, and WordPress setup are ready for live publishing.

```env
WP_POST_STATUS=draft
# or:
WP_POST_STATUS=publish
```

Optional category and tag support uses existing numeric WordPress IDs:

```env
WP_DEFAULT_CATEGORY_ID=12
WP_TAG_IDS=4,7,9
```

Find category and tag IDs in WordPress admin URLs or through the WordPress REST API. Categories and tags must be created in WordPress first; this pipeline never creates taxonomy terms automatically.

When `WP_DRY_RUN=true`, no remote post is created and the pipeline records a `dry_run` publish job. When `WP_DRY_RUN=false`, `WP_POST_STATUS=draft` creates drafts and `WP_POST_STATUS=publish` publishes immediately.

Optional AI category classification can select 1-3 WordPress category IDs from a fixed allowlist:

```env
AI_CATEGORY_CLASSIFICATION_ENABLED=true
AI_ALLOWED_CATEGORIES=5:KI-News,6:Modelle,7:Forschung,8:Tools,9:Sicherheit
```

German category names are supported. The OpenAI summarizer uses the category names for semantic meaning, but must return only numeric IDs from the allowlist. Invalid or empty AI category output is ignored, and the publisher falls back to `WP_DEFAULT_CATEGORY_ID` when configured.

To prevent one active source from consuming the full run, use:

```env
MAX_ARTICLES_PER_RUN=20
MAX_ARTICLES_PER_SOURCE_PER_RUN=5
```

With these values, each active source can process at most 5 new articles during a run, while the global run still stops at 20.

## Summarization Notes

`app/summarizer.py` contains:

- `SUMMARY_PROMPT_TEMPLATE`, a strict German factual-summary prompt.
- `Summarizer`, the service interface.
- `StubSummarizer`, a deterministic local fallback.
- `OpenAISummarizer`, a real provider using the OpenAI Responses API.

The stub keeps the system runnable without an LLM key. To enable OpenAI summaries:

```env
SUMMARIZER_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.4-mini
OPENAI_MAX_INPUT_CHARS=30000
OPENAI_REQUEST_TIMEOUT_SECONDS=60
```

The OpenAI provider asks for structured JSON with `german_title`, `german_excerpt`, `german_body_html`, and `tags`, then validates the result before WordPress draft creation. WordPress posts are still created as drafts and should be reviewed before publication.

## Image Generation

Generated featured images are optional and disabled by default:

```env
IMAGE_GENERATION_ENABLED=false
IMAGE_PROVIDER=openai
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=medium
OPENAI_IMAGE_STYLE=editorial
OPENAI_IMAGE_SAVE_LOCAL_COPY=false
OPENAI_IMAGE_OUTPUT_DIR=data/generated_images
```

When enabled with `IMAGE_PROVIDER=openai`, the pipeline reuses `OPENAI_API_KEY` to generate one clean editorial illustration per article. The prompt avoids logos, brand names, screenshots, UI clones, watermarks, and text-heavy poster layouts. If `WP_DRY_RUN=true`, WordPress media upload and post creation are skipped; local image generation may still run when image generation is enabled.

When `WP_DRY_RUN=false`, the generated image is uploaded to the WordPress media library before the post is created, and the returned media ID is sent as `featured_media`. If image generation or upload fails, the pipeline logs a warning and still creates the article without a featured image. Generated images should be reviewed editorially before publication.

## Extension Notes

Paper summaries:
Add a separate source type and extractor path for PDFs or paper metadata. Keep it separate from company news feeds so the MVP feed pipeline stays predictable.

Image generation:
Add a media service after summarization and before WordPress publishing. Store generated media IDs in a new table or in `publish_jobs` metadata.

Auto-publish rules:
Keep drafts as the default. Add explicit rule checks and an allowlist before changing WordPress status from `draft` to `publish`.

More sources:
Add new `SourceConfig` entries with `active=False`, validate feed quality manually, then activate. Prefer official company blogs, official research feeds, or official newsroom feeds only.
