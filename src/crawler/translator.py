"""Gemini-based translator for article titles and summaries."""

import logging

from google import genai

from crawlers import Article

logger = logging.getLogger(__name__)

TRANSLATE_PROMPT = """\
以下のAI関連記事のタイトルと概要を自然な日本語に翻訳してください。
既に日本語の場合はそのまま返してください。

タイトル: {title}
概要: {summary}

以下の形式で返してください（他の説明は不要）:
タイトル: <翻訳後タイトル>
概要: <翻訳後概要>
"""


class Translator:
    """Translates article content to Japanese using Gemini."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def translate(self, article: Article) -> Article:
        """Translate article title and summary to Japanese.

        Returns the same article with translated_title and translated_summary filled in.
        On error, falls back to the original text.
        """
        try:
            prompt = TRANSLATE_PROMPT.format(
                title=article.title,
                summary=article.summary or "(概要なし)",
            )
            response = self._client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = response.text or ""
            article.translated_title, article.translated_summary = self._parse_response(text, article)
        except Exception as e:
            logger.warning(f"Translation failed for '{article.title}': {e}")
            article.translated_title = article.title
            article.translated_summary = article.summary

        return article

    def _parse_response(self, text: str, article: Article) -> tuple[str, str]:
        """Parse the structured response from Gemini."""
        translated_title = article.title
        translated_summary = article.summary

        for line in text.splitlines():
            if line.startswith("タイトル:"):
                translated_title = line.removeprefix("タイトル:").strip()
            elif line.startswith("概要:"):
                translated_summary = line.removeprefix("概要:").strip()

        return translated_title, translated_summary
