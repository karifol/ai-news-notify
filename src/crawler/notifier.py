"""SES email notifier for AI news articles."""

import logging
from datetime import date

import boto3

from crawlers import Article

logger = logging.getLogger(__name__)


class Notifier:
    """Sends HTML digest email via Amazon SES."""

    def __init__(self, from_email: str, to_email: str, region: str = "ap-northeast-1") -> None:
        self._from = from_email
        self._to = to_email
        self._ses = boto3.client("ses", region_name=region)

    def send(self, articles_by_source: dict[str, list[Article]]) -> None:
        """Send an HTML email digest with new articles grouped by source.

        Args:
            articles_by_source: Dict mapping source name to list of translated articles.
        """
        today = date.today().strftime("%Y年%m月%d日")
        subject = f"【AI新着情報】{today}"
        html_body = self._build_html(articles_by_source, today)
        text_body = self._build_text(articles_by_source, today)

        self._ses.send_email(
            Source=self._from,
            Destination={"ToAddresses": [self._to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                },
            },
        )
        total = sum(len(v) for v in articles_by_source.values())
        logger.info(f"Email sent: {total} articles to {self._to}")

    def _build_html(self, articles_by_source: dict[str, list[Article]], today: str) -> str:
        """Build HTML email body."""
        sections = ""
        for source, articles in articles_by_source.items():
            items = ""
            for a in articles:
                title = a.translated_title or a.title
                summary = a.translated_summary or a.summary
                summary_html = f'<p style="color:#555;margin:4px 0 0;">{summary}</p>' if summary else ""
                items += f"""
                <li style="margin-bottom:16px;list-style:none;padding:12px;background:#f9f9f9;border-radius:6px;">
                  <a href="{a.url}" style="font-size:15px;font-weight:bold;color:#1a56db;text-decoration:none;">
                    {title}
                  </a>
                  {summary_html}
                  <p style="color:#888;font-size:12px;margin:4px 0 0;">
                    <a href="{a.url}" style="color:#888;">{a.url}</a>
                  </p>
                </li>"""
            sections += f"""
            <div style="margin-bottom:32px;">
              <h2 style="font-size:18px;border-bottom:2px solid #1a56db;padding-bottom:6px;color:#1a56db;">
                {source}
              </h2>
              <ul style="padding:0;margin:0;">{items}</ul>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><title>AI新着情報</title></head>
<body style="font-family:sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#222;">
  <h1 style="font-size:20px;color:#111;">AI新着情報 - {today}</h1>
  {sections}
  <hr style="border:none;border-top:1px solid #ddd;margin-top:32px;">
  <p style="color:#aaa;font-size:11px;">このメールはAI News Notifyにより自動送信されています。</p>
</body>
</html>"""

    def _build_text(self, articles_by_source: dict[str, list[Article]], today: str) -> str:
        """Build plain text fallback email body."""
        lines = [f"AI新着情報 - {today}", "=" * 40]
        for source, articles in articles_by_source.items():
            lines.append(f"\n【{source}】")
            for a in articles:
                title = a.translated_title or a.title
                summary = a.translated_summary or a.summary
                lines.append(f"\n■ {title}")
                if summary:
                    lines.append(f"  {summary}")
                lines.append(f"  {a.url}")
        lines.append("\n" + "=" * 40)
        lines.append("このメールはAI News Notifyにより自動送信されています。")
        return "\n".join(lines)
