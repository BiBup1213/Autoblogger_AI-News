"""German summarization abstraction and default stub implementation."""

from __future__ import annotations

import html
import json
import logging
import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from app.config import Settings
from app.models import ArticleContent, GermanSummary
from app.utils import truncate

logger = logging.getLogger(__name__)


SUMMARY_PROMPT_TEMPLATE = """\
Du bist ein redaktioneller Assistent für eine deutsche KI-Nachrichtenplattform.

Aufgabe:
Fasse den folgenden Artikel auf Deutsch zusammen. Bleibe strikt bei den Fakten
aus der Quelle. Erfinde keine Details, Zahlen, Zitate oder Bewertungen. Keine
Spekulation. Unsicherheit muss klar als Unsicherheit formuliert werden. Der Ton
ist neutral, informativ und lesbar, ohne Marketing-Sprache und ohne Hype.
Verwende korrektes UTF-8-Deutsch mit echten Umlauten und ß. Schreibe zum Beispiel
"Künstliche Intelligenz", nicht "Kuenstliche Intelligenz". Verwende niemals ae,
oe, ue oder ss als Ersatz für ä, ö, ü oder ß.

Ausgabeformat als JSON:
{{
  "german_title": "Kurzer deutscher Titel",
  "german_excerpt": "Ein sachlicher Kurztext mit maximal 2 Sätzen",
  "german_body_html": "<p>Mehrere kurze Absätze auf Deutsch.</p><p>...</p><h2>Quelle</h2><p><a href=\\"SOURCE_URL\\">Originalquelle</a></p>",
  "tags": ["optional", "kurz"],
  "category_ids": []
}}

Quelle:
- Source name: {source_name}
- Source URL: {source_url}
- Original title: {original_title}
- Publication date: {published_at}

Artikeltext:
{article_text}
"""

OPENAI_SUMMARY_SYSTEM_PROMPT = """\
Du bist ein sachlicher deutschsprachiger Fachredakteur für KI- und Technologiethemen.

Deine Aufgabe ist keine journalistische Neufassung, sondern eine quellennahe
deutsche Verdichtung eines Originaltexts.

Strikte Regeln:
- Schreibe auf Deutsch.
- Verwende korrektes UTF-8-Deutsch mit echten Umlauten und ß.
- Schreibe "ä", "ö", "ü", "Ä", "Ö", "Ü" und "ß" korrekt. Verwende niemals
  "ae", "oe", "ue" oder "ss" als Ersatz.
- Bleibe eng an der Quelle.
- Erfinde keine Fakten, Zahlen, Zitate, Ursachen, Folgen oder Bewertungen.
- Füge keine eigene Einordnung, Meinung, Dramaturgie oder Relevanzbehauptung hinzu.
- Vermeide Hype, Clickbait, Marketing-Sprache und wertende Formulierungen.
- Erhalte Einschränkungen, Unsicherheiten, Trade-offs und Vergleichsmaßstäbe aus der Quelle.
- Bewahre Produkt-, Modell-, Firmen-, Personen-, Projekt- und Methodennamen.
- Übersetze technische Fachbegriffe nur, wenn es eine etablierte deutsche Entsprechung gibt.
- Behalte englische Fachbegriffe bei, wenn eine deutsche Übersetzung ungewöhnlich,
  missverständlich oder künstlich wirken würde.
- Kopiere keine langen Passagen aus der Quelle.
- Schreibe flüssige Absätze, keine Stichpunktliste.
- Verwende keine festen Standardüberschriften wie "Was wurde angekündigt?",
  "Warum ist das relevant?", "Einordnung" oder "Offene Punkte".
- Erzeuge WordPress-sicheres HTML nur mit diesen Tags: p, h2, ul, li, strong, em, a.
- Füge am Ende eine kurze Quellen-Notiz mit Link zur Originalquelle ein.
"""

OPENAI_SUMMARY_USER_TEMPLATE = """\
Erstelle eine quellennahe deutsche Zusammenfassung als JSON mit exakt diesen Feldern:

- german_title:
  Kurzer, sachlicher deutscher Titel. Kein Clickbait, keine Dramatisierung.

- german_excerpt:
  1 bis 2 sachliche Sätze, die den Inhalt knapp zusammenfassen.

- german_body_html:
  Ein zusammenhängender deutscher HTML-Text mit mehreren kurzen Absätzen.
  Die sichtbare Struktur soll sich aus dem Original ergeben, nicht aus einer festen Vorlage.

  Regeln für german_body_html:
  - Beginne direkt mit der wichtigsten Information aus dem Original.
  - Verwende hauptsächlich <p>-Absätze.
  - Verwende <h2> nur, wenn es dem konkreten Text natürlich hilft.
  - Verwende keine Standardüberschriften wie:
    "Was wurde angekündigt?", "Warum ist das relevant?", "Einordnung",
    "Offene Punkte", "Fazit".
  - Keine journalistische Dramaturgie.
  - Keine eigene Bewertung.
  - Keine künstliche Zuspitzung.
  - Keine Meta-Formulierungen wie "Der Artikel beschreibt..." oder
    "Die Quelle berichtet...", wenn der Inhalt direkt formuliert werden kann.
  - Bei Research-, Modell- oder Produkttexten müssen zentrale Methoden,
    Ergebnisse, Grenzen, Parameter, Benchmarks oder Trade-offs erhalten bleiben,
    sofern sie im Original wichtig sind.
  - Technische Begriffe dürfen im Englischen bleiben, wenn die deutsche
    Übersetzung unüblich oder unpräzise wäre.
  - Verwende korrektes UTF-8-Deutsch mit echten Umlauten und ß. Schreibe niemals
    "ae", "oe", "ue" oder "ss" als Ersatz für "ä", "ö", "ü" oder "ß".
  - Am Ende muss stehen:
    <h2>Quelle</h2>
    <p><a href="{source_url}">Originalquelle: {source_name}</a></p>

- tags:
  Maximal 8 kurze Tags. Produkt-, Firmen- oder Fachbegriffe dürfen englisch bleiben.

- category_ids:
  {category_instruction}

Quellmetadaten:
- Quelle: {source_name}
- Originaltitel: {original_title}
- URL: {source_url}
- Veröffentlichungsdatum: {published_at}
- Content source type: {content_source_type}

{fallback_instruction}

Erlaubte WordPress-Kategorien:
{allowed_categories}

Artikeltext:
{article_text}
"""

SUMMARY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "german_title": {"type": "string"},
        "german_excerpt": {"type": "string"},
        "german_body_html": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "category_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": [
        "german_title",
        "german_excerpt",
        "german_body_html",
        "tags",
        "category_ids",
    ],
}

ALLOWED_HTML_TAGS = {"p", "h2", "ul", "li", "strong", "em", "a"}

COMMON_GERMAN_TRANSLITERATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b[Ff]uer\b",
        r"\b[Uu]eber\w*\b",
        r"\b[Ss]paeter\b",
        r"\b[Kk]uenstlich\w*\b",
        r"\b[Mm]uessen\b",
        r"\b[Dd]uerfen\b",
        r"\b[Kk]oennen\b",
        r"\b[Ww]aere\b",
        r"\b[Ww]uerde\w*\b",
        r"\b[Aa]ngekuendig\w*\b",
        r"\b[Vv]eroeffentlich\w*\b",
        r"\b[Oo]effentlich\w*\b",
        r"\b[Mm]oeglich\w*\b",
        r"\b[Nn]atuerlich\b",
        r"\b[Hh]auptsaechlich\b",
        r"\b[Uu]nueblich\b",
        r"\b[Uu]npraezise\b",
        r"\b[Zz]urueck\b",
        r"\b[Zz]usammenhaeng\w*\b",
        r"\b[Aa]bsaetz\w*\b",
        r"\b[Ss]aetz\w*\b",
        r"\b[Ff]uege\b",
        r"\b[Ee]inschraenk\w*\b",
        r"\b[Gg]roess\w*\b",
        r"\b[Mm]assstae\w*\b",
        r"\b[Aa]usser\w*\b",
    )
)


class SummarizerConfigurationError(RuntimeError):
    """Raised when a selected summarizer provider is not configured."""


class SummarizerResponseError(RuntimeError):
    """Raised when a provider returns malformed or unsafe summary content."""


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


def build_openai_summary_prompt(
    article: ArticleContent,
    max_chars: int,
    category_classification_enabled: bool = False,
    allowed_categories: dict[int, str] | None = None,
) -> str:
    article_text = truncate(article.text, max_chars)
    fallback_instruction = ""
    if article.content_source_type == "feed_fallback":
        fallback_instruction = (
            "Es waren nur RSS-/Feed-Metadaten verfügbar. Erstelle einen kürzeren "
            "deutschen Kurzbericht und behaupte nicht, dass der vollständige "
            "Artikel analysiert wurde."
        )
    allowed_categories = allowed_categories or {}
    category_instruction = "Gib eine leere Liste zurück."
    allowed_category_text = "Keine Kategorien konfiguriert."
    if category_classification_enabled and allowed_categories:
        category_instruction = (
            "Wähle 1 bis 3 numerische WordPress-Kategorie-IDs. Die erlaubten "
            "Kategorienamen können Deutsch sein. Nutze ihre semantische Bedeutung "
            "zur Klassifikation des Artikels, gib aber ausschließlich numerische "
            "Kategorie-IDs zurück. Wähle nur aus den erlaubten IDs. Erfinde keine "
            "Kategorien. Gib keine Kategorienamen zurück."
        )
        allowed_category_text = "\n".join(
            f"- {category_id}: {name}"
            for category_id, name in sorted(allowed_categories.items())
        )

    return OPENAI_SUMMARY_USER_TEMPLATE.format(
        source_name=article.source_name,
        source_url=article.source_url,
        original_title=article.original_title,
        published_at=article.published_at or "unbekannt",
        content_source_type=article.content_source_type,
        fallback_instruction=fallback_instruction,
        category_instruction=category_instruction,
        allowed_categories=allowed_category_text,
        article_text=article_text,
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
            "Konfigurieren Sie später einen LLM-Summarizer für redaktionell bessere Zusammenfassungen.</p>",
            f"<p>Die Originalquelle {escaped_source} berichtet über <em>{escaped_title}</em>.</p>",
            f"<p>{html.escape(paragraph_one)}</p>",
        ]
        if paragraph_two:
            body_parts.append(f"<p>{html.escape(paragraph_two)}</p>")
        body_parts.append(
            f'<h2>Quelle</h2><p><a href="{escaped_url}">Originalartikel bei {escaped_source}</a></p>'
        )

        return GermanSummary(
            german_title=f"Kurzüberblick: {article.original_title}",
            german_excerpt=excerpt,
            german_body_html="\n".join(body_parts),
            source_name=article.source_name,
            source_url=article.source_url,
            original_title=article.original_title,
            tags=self._tags(article),
            category_ids=[],
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


class OpenAISummarizer(Summarizer):
    """Summarize extracted articles through the OpenAI Responses API."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise SummarizerConfigurationError(
                "SUMMARIZER_PROVIDER=openai requires OPENAI_API_KEY"
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SummarizerConfigurationError(
                "SUMMARIZER_PROVIDER=openai requires the openai package. "
                "Install requirements.txt."
            ) from exc

        self.model = settings.openai_model
        self.max_input_chars = settings.openai_max_input_chars
        self.category_classification_enabled = settings.ai_category_classification_enabled
        self.allowed_categories = settings.ai_allowed_categories
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_request_timeout_seconds,
        )
        logger.info("OpenAI summarizer configured with model=%s", self.model)

    def summarize(self, article: ArticleContent) -> GermanSummary:
        """Return a validated German summary for one extracted article."""
        source_text = self._source_text(article)
        if len(article.text) > self.max_input_chars:
            logger.info(
                "Truncated article text for OpenAI summarization from %s to %s chars",
                len(article.text),
                self.max_input_chars,
            )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": OPENAI_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": source_text},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "german_ai_news_summary",
                    "strict": True,
                    "schema": SUMMARY_JSON_SCHEMA,
                }
            },
        )
        payload = _parse_response_json(response)
        return _summary_from_payload(
            payload,
            article,
            allowed_category_ids=set(self.allowed_categories),
        )

    def _source_text(self, article: ArticleContent) -> str:
        return build_openai_summary_prompt(
            article=article,
            max_chars=self.max_input_chars,
            category_classification_enabled=self.category_classification_enabled,
            allowed_categories=self.allowed_categories,
        )


class _SafeHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_HTML_TAGS:
            return

        if tag == "a":
            href = self._safe_href(attrs)
            if href:
                self.parts.append(f'<a href="{html.escape(href, quote=True)}">')
                self.open_tags.append(tag)
            return

        self.parts.append(f"<{tag}>")
        self.open_tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in ALLOWED_HTML_TAGS and tag in self.open_tags:
            self.parts.append(f"</{tag}>")
            if self.open_tags[-1] == tag:
                self.open_tags.pop()
            else:
                self.open_tags.remove(tag)

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data))

    def get_html(self) -> str:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts).strip()

    def _safe_href(self, attrs: list[tuple[str, str | None]]) -> str | None:
        for key, value in attrs:
            if key.lower() != "href" or not value:
                continue
            parsed_url = urlparse(value)
            if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
                return value
        return None


class _VisibleTextParser(HTMLParser):
    """Extract visible text so umlaut checks do not inspect URLs or HTML syntax."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self.parts)


def create_summarizer(settings_or_provider: Settings | str) -> Summarizer:
    if isinstance(settings_or_provider, Settings):
        settings = settings_or_provider
        provider = settings.summarizer_provider
    else:
        settings = None
        provider = settings_or_provider

    if provider == "stub":
        logger.info("Using stub summarizer provider")
        return StubSummarizer()
    if provider == "openai":
        if settings is None:
            raise SummarizerConfigurationError(
                "OpenAI summarizer requires full Settings, not only a provider string"
            )
        return OpenAISummarizer(settings)
    raise SummarizerConfigurationError(f"Unsupported SUMMARIZER_PROVIDER={provider!r}")


def _parse_response_json(response: Any) -> dict[str, Any]:
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise SummarizerResponseError("OpenAI response did not contain output_text")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise SummarizerResponseError("OpenAI response was not valid JSON") from exc

    if not isinstance(payload, dict):
        raise SummarizerResponseError("OpenAI response JSON was not an object")
    return payload


def _summary_from_payload(
    payload: dict[str, Any],
    article: ArticleContent,
    allowed_category_ids: set[int] | None = None,
) -> GermanSummary:
    german_title = _required_string(payload, "german_title")
    german_excerpt = _required_string(payload, "german_excerpt")
    german_body_html = _sanitize_summary_html(_required_string(payload, "german_body_html"))
    if not german_body_html:
        raise SummarizerResponseError("german_body_html is empty after sanitization")
    german_body_html = _ensure_source_note(german_body_html, article)

    tags = _validated_tags(payload.get("tags", []))
    category_ids = _validated_category_ids(
        payload.get("category_ids", []),
        allowed_category_ids or set(),
    )
    _validate_umlaut_spelling(
        german_title=german_title,
        german_excerpt=german_excerpt,
        german_body_html=german_body_html,
        tags=tags,
    )
    return GermanSummary(
        german_title=german_title,
        german_excerpt=german_excerpt,
        german_body_html=german_body_html,
        source_name=article.source_name,
        source_url=article.source_url,
        original_title=article.original_title,
        tags=tags,
        category_ids=category_ids,
    )


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SummarizerResponseError(f"{key} is missing or empty")
    return value.strip()


def _validated_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SummarizerResponseError("tags must be a list")

    tags: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:8]


def _validated_category_ids(value: Any, allowed_category_ids: set[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    if not allowed_category_ids:
        return []

    category_ids: list[int] = []
    for item in value:
        if not isinstance(item, int):
            continue
        if item in allowed_category_ids and item not in category_ids:
            category_ids.append(item)
    return category_ids[:3]


def _validate_umlaut_spelling(
    german_title: str,
    german_excerpt: str,
    german_body_html: str,
    tags: list[str],
) -> None:
    """Reject common ASCII transliterations in generated German output.

    The check is intentionally conservative: it catches frequent German
    transliteration errors without banning valid German words that contain "ss"
    after the spelling reform, such as "dass" or "muss".
    """

    fields = {
        "german_title": german_title,
        "german_excerpt": german_excerpt,
        "german_body_html": _visible_text_from_html(german_body_html),
        "tags": " ".join(tags),
    }
    violations: list[str] = []
    for field_name, text in fields.items():
        matches = _common_transliteration_matches(text)
        if matches:
            violations.append(f"{field_name}: {', '.join(matches[:5])}")

    if violations:
        raise SummarizerResponseError(
            "Generated German text contains ASCII umlaut transliterations. "
            "Use real UTF-8 umlauts and ß instead: " + "; ".join(violations)
        )


def _common_transliteration_matches(text: str) -> list[str]:
    matches: list[str] = []
    for pattern in COMMON_GERMAN_TRANSLITERATION_PATTERNS:
        for match in pattern.findall(text):
            if match not in matches:
                matches.append(match)
    return matches


def _visible_text_from_html(raw_html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw_html)
    parser.close()
    return parser.get_text()


def _sanitize_summary_html(raw_html: str) -> str:
    parser = _SafeHtmlParser()
    parser.feed(raw_html)
    parser.close()
    return parser.get_html()


def _ensure_source_note(body_html: str, article: ArticleContent) -> str:
    if article.source_url in body_html:
        return body_html

    escaped_url = html.escape(article.source_url, quote=True)
    escaped_source = html.escape(article.source_name)
    source_note = (
        f'<h2>Quelle</h2><p><a href="{escaped_url}">'
        f"Originalquelle: {escaped_source}</a></p>"
    )
    return body_html.rstrip() + "\n" + source_note
