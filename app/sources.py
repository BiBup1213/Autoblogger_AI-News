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
        active=False,
        allowed_url_patterns=(r"^https://openai\.com/",),
        excluded_url_patterns=(),
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
        source_type="official_research_lab_news",
        active=True,
        allowed_url_patterns=(r"^https://deepmind\.google/",),
        excluded_url_patterns=(r"/careers?", r"/jobs?", r"/events?", r"/terms", r"/privacy"),
    ),
    SourceConfig(
        name="Meta Engineering",
        feed_url="https://engineering.fb.com/feed/",
        source_type="official_engineering_blog",
        active=True,
        allowed_url_patterns=(r"^https://engineering\.fb\.com/",),
        excluded_url_patterns=(r"/careers?", r"/jobs?", r"/events?", r"/legal", r"/privacy"),
        excluded_categories=("careers", "events"),
    ),
    SourceConfig(
        name="Hugging Face Blog",
        feed_url="https://huggingface.co/blog/feed.xml",
        source_type="official_engineering_blog",
        active=True,
        allowed_url_patterns=(r"^https://huggingface\.co/blog/",),
        excluded_url_patterns=(),
    ),
    SourceConfig(
        name="Microsoft AI Blog",
        feed_url="https://blogs.microsoft.com/ai/feed/",
        source_type="official_company_news",
        active=True,
        allowed_url_patterns=(r"^https://blogs\.microsoft\.com/ai/",),
        excluded_url_patterns=(r"/events?", r"/careers?", r"/jobs?", r"/privacy", r"/legal"),
    ),
    SourceConfig(
        name="Microsoft Research",
        feed_url="https://www.microsoft.com/en-us/research/feed/",
        source_type="official_research_blog",
        active=True,
        allowed_url_patterns=(r"^https://www\.microsoft\.com/en-us/research/",),
        excluded_url_patterns=(r"/careers?", r"/jobs?", r"/events?", r"/privacy", r"/legal"),
    ),
    SourceConfig(
        name="NVIDIA Blog",
        feed_url="https://blogs.nvidia.com/feed/",
        source_type="official_company_news",
        active=True,
        allowed_url_patterns=(r"^https://blogs\.nvidia\.com/",),
        excluded_url_patterns=(r"/about-nvidia/", r"/careers?", r"/jobs?", r"/events?"),
    ),
    SourceConfig(
        name="NVIDIA Technical Blog",
        feed_url="https://developer.nvidia.com/blog/feed/",
        source_type="official_engineering_blog",
        active=True,
        allowed_url_patterns=(r"^https://developer\.nvidia\.com/blog/",),
        excluded_url_patterns=(r"/events?", r"/training/", r"/careers?", r"/jobs?"),
    ),
    SourceConfig(
        name="xAI via Nitter",
        feed_url="https://nitter.net/xai/rss",
        source_type="social_feed_unofficial",
        active=False,
        allowed_url_patterns=(r"^https://nitter\.net/xai",),
        excluded_url_patterns=(),
    ),
)