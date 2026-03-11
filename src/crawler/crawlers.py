"""Web crawlers for Anthropic, OpenAI, and Google Gemini news pages."""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
TIMEOUT = 30


@dataclass
class Article:
    """Represents a news article."""

    title: str
    url: str
    summary: str = ""
    source_name: str = ""
    translated_title: str = ""
    translated_summary: str = ""


class BaseCrawler:
    """Base class for site crawlers."""

    source_name: str = ""
    news_url: str = ""
    base_url: str = ""

    def fetch(self) -> list[Article]:
        """Fetch articles from the news page. Must be implemented by subclasses."""
        raise NotImplementedError

    def _get(self, url: str) -> BeautifulSoup:
        """GET request with common headers."""
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    def _extract_next_data(self, soup: BeautifulSoup) -> dict | None:
        """Extract __NEXT_DATA__ JSON embedded by Next.js."""
        tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if tag and tag.string:
            try:
                return json.loads(tag.string)
            except json.JSONDecodeError:
                pass
        return None

    def _absolute_url(self, href: str) -> str:
        """Convert relative URL to absolute."""
        if href.startswith("http"):
            return href
        return self.base_url.rstrip("/") + "/" + href.lstrip("/")

    def _fetch_rss(self, rss_url: str) -> list[Article]:
        """Parse RSS 2.0 or Atom feed and return articles."""
        resp = requests.get(rss_url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        articles: list[Article] = []

        # RSS 2.0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            summary = (item.findtext("description") or "").strip()
            # Strip HTML tags from description
            summary = re.sub(r"<[^>]+>", "", summary)[:300]
            if title and link:
                articles.append(Article(title=title, url=link, summary=summary, source_name=self.source_name))

        # Atom
        if not articles:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns):
                title = (entry.findtext("atom:title", "", ns) or "").strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                summary = (entry.findtext("atom:summary", "", ns) or "").strip()
                summary = re.sub(r"<[^>]+>", "", summary)[:300]
                if title and link:
                    articles.append(Article(title=title, url=link, summary=summary, source_name=self.source_name))

        return articles[:20]


class AnthropicCrawler(BaseCrawler):
    """Crawler for Anthropic news, trying RSS then HTML fallback."""

    source_name = "Anthropic"
    base_url = "https://www.anthropic.com"
    news_url = "https://www.anthropic.com/news"
    rss_url = "https://www.anthropic.com/rss.xml"

    def fetch(self) -> list[Article]:
        """Fetch latest articles from Anthropic, trying RSS first."""
        # Try RSS first (more reliable than scraping)
        try:
            articles = self._fetch_rss(self.rss_url)
            if articles:
                logger.info(f"[Anthropic] Found {len(articles)} articles via RSS")
                return articles
        except Exception as e:
            logger.debug(f"[Anthropic] RSS failed: {e}, falling back to HTML")

        # Fallback: parse HTML
        soup = self._get(self.news_url)
        articles = []
        next_data = self._extract_next_data(soup)
        if next_data:
            articles = self._parse_next_data(next_data)
        if not articles:
            articles = self._parse_html(soup)

        logger.info(f"[Anthropic] Found {len(articles)} articles via HTML")
        return articles

    def _parse_next_data(self, data: dict) -> list[Article]:
        """Parse articles from Next.js page data."""
        articles: list[Article] = []
        try:
            # Walk through Next.js data looking for news items
            page_props = data.get("props", {}).get("pageProps", {})
            posts = page_props.get("posts") or page_props.get("articles") or []
            for post in posts[:20]:
                title = post.get("title") or post.get("heading", "")
                slug = post.get("slug") or post.get("url", "")
                summary = post.get("description") or post.get("excerpt") or post.get("summary", "")
                if title and slug:
                    url = self._absolute_url(f"/news/{slug.lstrip('/')}")
                    articles.append(Article(title=title, url=url, summary=summary, source_name=self.source_name))
        except (KeyError, TypeError, AttributeError) as e:
            logger.debug(f"[Anthropic] Next.js parse error: {e}")
        return articles

    def _parse_html(self, soup: BeautifulSoup) -> list[Article]:
        """Fallback HTML parser for Anthropic news."""
        articles: list[Article] = []
        # Article cards typically have an anchor linking to /news/*
        seen_urls: set[str] = set()
        for a in soup.find_all("a", href=re.compile(r"^/news/[^/]+")):
            href = a["href"]
            url = self._absolute_url(href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Try to find the title within the link or nearby heading
            heading = a.find(["h2", "h3", "h4"]) or a
            title = heading.get_text(strip=True)
            if not title:
                continue

            # Look for summary text in sibling/parent elements
            parent = a.find_parent(["article", "div", "li"])
            summary = ""
            if parent:
                p = parent.find("p")
                if p:
                    summary = p.get_text(strip=True)

            articles.append(Article(title=title, url=url, summary=summary, source_name=self.source_name))

        return articles[:20]


class OpenAICrawler(BaseCrawler):
    """Crawler for OpenAI news via RSS feed."""

    source_name = "OpenAI"
    base_url = "https://openai.com"
    rss_url = "https://openai.com/blog/rss.xml"

    def fetch(self) -> list[Article]:
        """Fetch latest articles from OpenAI RSS feed."""
        articles = self._fetch_rss(self.rss_url)
        logger.info(f"[OpenAI] Found {len(articles)} articles")
        return articles


class GeminiCrawler(BaseCrawler):
    """Crawler for Google Gemini news via RSS, falling back to HTML."""

    source_name = "Google Gemini"
    base_url = "https://blog.google"
    rss_url = "https://blog.google/products/gemini/rss/"
    news_url = "https://blog.google/products/gemini/"

    def fetch(self) -> list[Article]:
        """Fetch latest articles from Google Gemini blog, trying RSS first."""
        try:
            articles = self._fetch_rss(self.rss_url)
            if articles:
                logger.info(f"[Google Gemini] Found {len(articles)} articles via RSS")
                return articles
        except Exception as e:
            logger.debug(f"[Google Gemini] RSS failed: {e}, falling back to HTML")

        soup = self._get(self.news_url)
        articles = self._parse_html(soup)
        logger.info(f"[Google Gemini] Found {len(articles)} articles via HTML")
        return articles

    def _parse_html(self, soup: BeautifulSoup) -> list[Article]:
        """Parse article entries from blog.google/products/gemini/."""
        articles: list[Article] = []
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=re.compile(r"/products/gemini/")):
            href = a.get("href", "")
            # Skip the section index itself
            if href.rstrip("/") == "/products/gemini":
                continue
            url = self._absolute_url(href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            heading = a.find(["h2", "h3", "h4"]) or a
            title = heading.get_text(strip=True)
            if not title:
                continue

            parent = a.find_parent(["article", "div", "li"])
            summary = ""
            if parent:
                p = parent.find("p")
                if p:
                    summary = p.get_text(strip=True)

            articles.append(Article(title=title, url=url, summary=summary, source_name=self.source_name))

        return articles[:20]
