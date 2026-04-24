"""Hand-picked primary source registry.

Keep this list intentionally small. This MVP processes every valid new item from
active sources, so do not activate broad feeds unless their whole output belongs
in the product.
"""

from __future__ import annotations

from app.models import SourceConfig


SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(
        name="OpenAI News",
        feed_url="https://openai.com/news/rss.xml",
        source_type="official_company_news",
        active=True,
        allowed_url_patterns=(r"^https://openai\.com/news/",),
        excluded_url_patterns=(
            r"/careers?",
            r"/jobs?",
            r"/events?",
            r"/policies?",
            r"/terms",
            r"/privacy",
        ),
    ),
    SourceConfig(
        name="Anthropic Newsroom",
        feed_url="https://www.anthropic.com/news/rss.xml",
        source_type="official_company_news_placeholder",
        active=False,
        allowed_url_patterns=(r"^https://www\.anthropic\.com/",),
        excluded_url_patterns=(r"/careers?", r"/jobs?", r"/events?", r"/legal", r"/privacy"),
    ),
    SourceConfig(
        name="Google DeepMind News",
        feed_url="https://deepmind.google/blog/rss.xml",
        source_type="official_research_lab_news_placeholder",
        active=False,
        allowed_url_patterns=(r"^https://deepmind\.google/",),
        excluded_url_patterns=(r"/careers?", r"/jobs?", r"/events?", r"/terms", r"/privacy"),
    ),
    SourceConfig(
        name="Meta Engineering",
        feed_url="https://engineering.fb.com/feed/",
        source_type="official_engineering_blog",
        active=False,
        allowed_url_patterns=(r"^https://engineering\.fb\.com/",),
        excluded_url_patterns=(r"/careers?", r"/jobs?", r"/events?", r"/legal", r"/privacy"),
        excluded_categories=("careers", "events"),
    ),
)

