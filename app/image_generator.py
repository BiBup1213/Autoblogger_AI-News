"""Optional editorial image generation for WordPress featured images."""

from __future__ import annotations

import base64
import logging
import re
import struct
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from app.config import Settings
from app.models import GeneratedImage, GermanSummary
from app.utils import truncate

logger = logging.getLogger(__name__)


HOUSE_STYLE_BLOCK = """\
Create a clean, modern editorial illustration for a German AI news website.
Use a professional technology-news aesthetic, landscape format, polished digital illustration style, and a restrained modern palette of cool blues, teals, soft violets, light grays, and white.
Use subtle accent colors only. Avoid chaotic, neon, or overly saturated color mixes.
Focus on one clear central concept, minimal clutter, clean background, balanced composition, and a neutral trustworthy mood.
The image should be suitable as a WordPress featured image and should feel consistent with a serious technology news publication.
"""

CATEGORY_TOPIC_BLOCK = """\
Category and topic cues:
- Category IDs if available: {category_ids}
- Concise topic cues: {topic_cues}
"""

ARTICLE_TOPIC_BLOCK = """\
Article-specific context:
- German title: {german_title}
- Short excerpt: {german_excerpt}
- Source/company: {source_name}
- Requested visual style note: {style}

Reflect the article topic in a generic editorial way without recreating exact branded products, exact interfaces, or specific real-world scenes that did not occur.
"""

HARD_NEGATIVE_BLOCK = """\
Important hard constraints:
NO text inside the image.
NO readable text, NO letters, NO words, NO typography, NO captions, NO headlines, NO labels, NO numbers, NO charts with numeric marks.
NO logos, NO brand marks, NO trademarks, NO watermarks, NO signatures.
NO screenshots, NO website UI, NO app UI, NO fake interface elements, NO browser windows, NO dashboard panels, NO chat bubbles, NO buttons, NO menus.
NO poster-like layout, NO infographic-style composition, NO diagram panels, NO text-heavy composition.
Avoid anything that looks like a product mockup, branded UI clone, slide deck, or marketing poster.
"""


class ImageGenerationError(RuntimeError):
    """Raised when optional image generation cannot produce a usable file."""


class ImageGenerator(ABC):
    @abstractmethod
    def generate(self, summary: GermanSummary) -> GeneratedImage | None:
        raise NotImplementedError


class NoOpImageGenerator(ImageGenerator):
    def generate(self, summary: GermanSummary) -> GeneratedImage | None:
        return None


class UnavailableImageGenerator(ImageGenerator):
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def generate(self, summary: GermanSummary) -> GeneratedImage | None:
        logger.warning("Image generation unavailable for %s: %s", summary.german_title, self.reason)
        return None


class OpenAIImageGenerator(ImageGenerator):
    """Generate one editorial image through the OpenAI Images API."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ImageGenerationError("OpenAI image generation requires OPENAI_API_KEY")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImageGenerationError("OpenAI image generation requires the openai package") from exc

        self.settings = settings
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_image_timeout_seconds,
        )

    def generate(self, summary: GermanSummary) -> GeneratedImage:
        prompt = build_image_prompt(summary, self.settings)
        logger.info(
            "Generating image for article title=%s model=%s size=%s quality=%s",
            summary.german_title,
            self.settings.openai_image_model,
            self.settings.openai_image_size,
            self.settings.openai_image_quality,
        )
        response = self.client.images.generate(
            model=self.settings.openai_image_model,
            prompt=prompt,
            size=self.settings.openai_image_size,
            quality=self.settings.openai_image_quality,
            n=1,
        )
        image_base64 = response.data[0].b64_json
        if not image_base64:
            raise ImageGenerationError("OpenAI image response did not include base64 image data")

        image_bytes = base64.b64decode(image_base64)
        output_path = self._output_path(summary)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_bytes)
        width, height = _png_dimensions(image_bytes)
        logger.info("Generated image saved to %s", output_path)

        return GeneratedImage(
            local_file_path=output_path,
            mime_type="image/png",
            generation_prompt_used=prompt,
            alt_text=_alt_text(summary),
            caption=f"KI-generierte redaktionelle Illustration zum Artikel: {summary.german_title}",
            width=width,
            height=height,
        )

    def _output_path(self, summary: GermanSummary) -> Path:
        filename = _safe_slug(summary.german_title)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        if self.settings.openai_image_save_local_copy:
            directory = self.settings.openai_image_output_dir
        else:
            directory = Path(tempfile.gettempdir()) / "autoblogger_ai_news_images"
        return directory / f"{filename}-{timestamp}.png"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self.parts)


def create_image_generator(settings: Settings) -> ImageGenerator:
    if not settings.image_generation_enabled or settings.image_provider == "none":
        logger.info("Image generation disabled")
        return NoOpImageGenerator()
    if settings.image_provider == "openai":
        try:
            return OpenAIImageGenerator(settings)
        except ImageGenerationError as exc:
            return UnavailableImageGenerator(str(exc))
    return UnavailableImageGenerator(f"Unsupported IMAGE_PROVIDER={settings.image_provider!r}")


def build_image_prompt(summary: GermanSummary, settings: Settings) -> str:
    topic_cues = _body_topic_cues(summary.german_body_html)
    prompt = "\n\n".join(
        (
            HOUSE_STYLE_BLOCK.strip(),
            CATEGORY_TOPIC_BLOCK.format(
                category_ids=", ".join(str(category_id) for category_id in summary.category_ids) or "none",
                topic_cues=topic_cues,
            ).strip(),
            ARTICLE_TOPIC_BLOCK.format(
                german_title=summary.german_title,
                german_excerpt=summary.german_excerpt,
                source_name=summary.source_name,
                style=settings.openai_image_style,
            ).strip(),
            HARD_NEGATIVE_BLOCK.strip(),
        )
    )
    return truncate(prompt, settings.openai_image_prompt_max_chars)


def _body_topic_cues(body_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(body_html)
    return truncate(parser.text(), 450)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "generated-image"


def _alt_text(summary: GermanSummary) -> str:
    return truncate(
        f"Redaktionelle KI-Illustration zum Artikel {summary.german_title}",
        160,
    )


def _png_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    if len(image_bytes) < 24 or image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    width, height = struct.unpack(">II", image_bytes[16:24])
    return width, height
