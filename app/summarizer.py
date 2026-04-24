"""German summarization abstraction and default stub implementation."""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod

from app.models import ArticleContent, GermanSummary
from app.utils import truncate


SUMMARY_PROMPT_TEMPLATE = """\
Du bist ein redaktioneller Assistent fuer eine deutsche KI-Nachrichtenplattform.

Aufgabe:
Fasse den folgenden Artikel auf Deutsch zusammen. Bleibe strikt bei den Fakten
aus der Quelle. Erfinde keine Details, Zahlen, Zitate oder Bewertungen. Keine
Spekulation. Unsicherheit muss klar als Unsicherheit formuliert werden. Der Ton
ist neutral, informativ und lesbar, ohne Marketing-Sprache und ohne Hype.

Ausgabeformat als JSON:
{{
  "german_title": "Kurzer deutscher Titel",
  "german_excerpt": "Ein sachlicher Kurztext mit maximal 2 Saetzen",
  "german_body_html": "<p>Mehrere kurze Absaetze auf Deutsch.</p><p>...</p><h2>Quelle</h2><p><a href=\\"SOURCE_URL\\">Originalquelle</a></p>",
  "tags": ["optional", "kurz"]
}}

Quelle:
- Source name: {source_name}
- Source URL: {source_url}
- Original title: {original_title}
- Publication date: {published_at}

Artikeltext:
{article_text}
"""


class Summarizer(ABC):
    @abstractmethod
    def summarize(self, article: ArticleContent) -> GermanSummary:
        raise NotImplementedError


def build_summary_prompt(article: ArticleContent, max_chars: int = 12000) -> str:
    return SUMMARY_PROMPT_TEMPLATE.format(
        source_name=article.source_name,
        source_url=article.source_url,
        original_title=article.original_title,
        published_at=article.published_at or "unbekannt",
        article_text=truncate(article.text, max_chars),
    )


class StubSummarizer(Summarizer):
    """Deterministic fallback for local runs without an LLM API key.

    It does not claim to be a high-quality abstractive summary. It creates a
    conservative German draft scaffold from source text snippets, making missing
    LLM configuration visible while keeping the full pipeline testable.
    """

    def summarize(self, article: ArticleContent) -> GermanSummary:
        sentences = self._first_sentences(article.text, limit=4)
        escaped_title = html.escape(article.original_title)
        escaped_source = html.escape(article.source_name)
        escaped_url = html.escape(article.source_url, quote=True)

        if sentences:
            excerpt = (
                "Automatisch erstellter Entwurf auf Basis der Originalquelle. "
                f"Der Artikel behandelt: {truncate(sentences[0], 180)}"
            )
        else:
            excerpt = "Automatisch erstellter Entwurf auf Basis der Originalquelle."

        paragraph_one = " ".join(sentences[:2]) if sentences else article.original_title
        paragraph_two = " ".join(sentences[2:4]) if len(sentences) > 2 else ""

        body_parts = [
            "<p><strong>Hinweis:</strong> Dies ist ein lokaler Stub-Entwurf. "
            "Konfigurieren Sie spaeter einen LLM-Summarizer fuer redaktionell bessere Zusammenfassungen.</p>",
            f"<p>Die Originalquelle {escaped_source} berichtet ueber <em>{escaped_title}</em>.</p>",
            f"<p>{html.escape(paragraph_one)}</p>",
        ]
        if paragraph_two:
            body_parts.append(f"<p>{html.escape(paragraph_two)}</p>")
        body_parts.append(
            f'<h2>Quelle</h2><p><a href="{escaped_url}">Originalartikel bei {escaped_source}</a></p>'
        )

        return GermanSummary(
            german_title=f"Kurzueberblick: {article.original_title}",
            german_excerpt=excerpt,
            german_body_html="\n".join(body_parts),
            source_name=article.source_name,
            source_url=article.source_url,
            original_title=article.original_title,
            tags=self._tags(article),
        )

    def _first_sentences(self, text: str, limit: int) -> list[str]:
        normalized = re.sub(r"\s+", " ", text.strip())
        candidates = re.split(r"(?<=[.!?])\s+", normalized)
        return [sentence.strip() for sentence in candidates if sentence.strip()][:limit]

    def _tags(self, article: ArticleContent) -> list[str]:
        tags = ["KI", article.source_name]
        lower_text = f"{article.original_title} {article.text[:2000]}".lower()
        for keyword, tag in (
            ("model", "Modelle"),
            ("research", "Forschung"),
            ("safety", "KI-Sicherheit"),
            ("api", "API"),
            ("open source", "Open Source"),
        ):
            if keyword in lower_text and tag not in tags:
                tags.append(tag)
        return tags[:5]


def create_summarizer(provider: str) -> Summarizer:
    if provider != "stub":
        raise ValueError(
            f"Unsupported SUMMARIZER_PROVIDER={provider!r}. This MVP ships with 'stub'."
        )
    return StubSummarizer()

