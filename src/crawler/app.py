"""Lambda handler: crawl AI news sites and send email digest."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from crawlers import AnthropicCrawler, Article, BaseCrawler, ClaudeCodeCrawler, GeminiCrawler, OpenAICrawler
from notifier import Notifier
from translator import Translator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
ssm = boto3.client("ssm")


def handler(event: dict, context) -> dict:
    """Lambda entrypoint triggered by EventBridge schedule.

    Crawls each source, filters already-seen articles, translates new ones,
    and sends an email digest via SES.
    """
    table_name = os.environ["SEEN_ARTICLES_TABLE"]
    from_email = os.environ["FROM_EMAIL"]
    to_email = os.environ["TO_EMAIL"]
    gemini_api_key = ssm.get_parameter(
        Name=os.environ["GEMINI_API_KEY_PARAM"],
        WithDecryption=True,
    )["Parameter"]["Value"]

    table = dynamodb.Table(table_name)
    translator = Translator(api_key=gemini_api_key)
    notifier = Notifier(from_email=from_email, to_email=to_email)

    crawlers: list[BaseCrawler] = [
        AnthropicCrawler(),
        OpenAICrawler(),
        GeminiCrawler(),
        ClaudeCodeCrawler(),
    ]

    new_articles_by_source: dict[str, list[Article]] = {}

    for crawler in crawlers:
        try:
            articles = crawler.fetch()
            logger.info(f"Fetched {len(articles)} articles from {crawler.source_name}")

            new_articles: list[Article] = []
            for article in articles:
                if _is_seen(table, article.url):
                    continue
                translated = translator.translate(article)
                new_articles.append(translated)
                _mark_seen(table, article.url)

            if new_articles:
                new_articles_by_source[crawler.source_name] = new_articles
            logger.info(f"New articles from {crawler.source_name}: {len(new_articles)}")

        except Exception:
            logger.exception(f"Error processing {crawler.source_name}")

    total_new = sum(len(v) for v in new_articles_by_source.values())

    try:
        notifier.send(new_articles_by_source)
    except Exception:
        logger.exception("Failed to send email")

    return {
        "statusCode": 200,
        "body": json.dumps({"new_articles_count": total_new}),
    }


def _is_seen(table, url: str) -> bool:
    """Return True if the URL has already been processed."""
    response = table.get_item(Key={"url": url})
    return "Item" in response


def _mark_seen(table, url: str) -> None:
    """Store the URL in DynamoDB with a 30-day TTL."""
    ttl = int(datetime.now(timezone.utc).timestamp()) + 30 * 24 * 60 * 60
    table.put_item(Item={"url": url, "ttl": ttl})
