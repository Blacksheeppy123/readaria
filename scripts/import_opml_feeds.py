#!/usr/bin/env python3
"""
OPML Feed Import & Validation Script for Jasmine
Fetches curated RSS feeds from public OPML files, validates quality,
and updates frontend recommendedFeeds.js and backend feed_validation table.
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

from backend.fetcher.rss_fetcher import RSSFetcher
from backend.storage.database import DatabaseManager
from backend.utils.html_sanitizer import HTMLSanitizer
from core.config.settings import settings

logger = logging.getLogger("import_opml_feeds")

# ==================== Configuration ====================

OPML_SOURCES = {
    "en": {
        "url": "https://raw.githubusercontent.com/kilimchoi/engineering-blogs/master/engineering_blogs.opml",
        "target_language": "en",
    },
    "zh": {
        "url": "https://raw.githubusercontent.com/timqian/chinese-independent-blogs/master/feed.opml",
        "target_language": "zh",
    },
    "curated_mixed": {
        "url": "https://raw.githubusercontent.com/merrygreek/rss-feeds-opml/main/rss_merged_dedup.opml",
        "target_language": "auto",  # infer from parent category
    },
    "curated_en": {
        "url": "https://raw.githubusercontent.com/ThinkPeace/rss-cache/main/feeds.opml",
        "target_language": "en",
    },
    "plenary_business": {
        "url": "https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/recommended/with_category/Business%20%26%20Economy.opml",
        "target_language": "en",
    },
    "plenary_books": {
        "url": "https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/recommended/with_category/Books.opml",
        "target_language": "en",
    },
    "plenary_gaming": {
        "url": "https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/recommended/with_category/Gaming.opml",
        "target_language": "en",
    },
    "plenary_food": {
        "url": "https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/recommended/with_category/Food.opml",
        "target_language": "en",
    },
    "plenary_football": {
        "url": "https://raw.githubusercontent.com/plenaryapp/awesome-rss-feeds/master/recommended/with_category/Football.opml",
        "target_language": "en",
    },
}

VALIDATION_CONFIG = {
    "sample_size": 5,
    "min_content_length": 200,
    "min_plain_text_ratio": 0.4,
    "recency_days": 60,
    "min_articles_with_content": 3,
}

STARTER_PACK_SIZE = 8

# Manually curated high-quality feeds (confirmed to have in-feed full text)
MANUAL_FEEDS = [
    # News
    {"name": "NPR News", "url": "https://feeds.npr.org/1001/rss.xml", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "The Register", "url": "https://www.theregister.com/headlines.atom", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "Engadget", "url": "https://www.engadget.com/rss.xml", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "Guardian World", "url": "https://www.theguardian.com/world/rss", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "Axios", "url": "https://www.axios.com/feeds/feed.rss", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "The Atlantic", "url": "https://www.theatlantic.com/feed/all/", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    {"name": "Vox", "url": "https://www.vox.com/rss/index.xml", "source_language": "en", "opml_category": "News", "source_key": "manual_news"},
    # Reddit
    {"name": "r/technology", "url": "https://www.reddit.com/r/technology/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/worldnews", "url": "https://www.reddit.com/r/worldnews/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/programming", "url": "https://www.reddit.com/r/programming/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/science", "url": "https://www.reddit.com/r/science/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/AskReddit", "url": "https://www.reddit.com/r/AskReddit/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/explainlikeimfive", "url": "https://www.reddit.com/r/explainlikeimfive/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/todayilearned", "url": "https://www.reddit.com/r/todayilearned/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/gadgets", "url": "https://www.reddit.com/r/gadgets/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
    {"name": "r/business", "url": "https://www.reddit.com/r/business/.rss", "source_language": "en", "opml_category": "Reddit", "source_key": "manual_reddit"},
]

# Domain/name-based popularity score (1-10). Used to surface well-known media.
MEDIA_POPULARITY = {
    # Tier 10: Global household names
    "theguardian.com": 10, "guardian.co.uk": 10,
    "nytimes.com": 10, "npr.org": 10,
    "bbc.com": 10, "bbc.co.uk": 10,
    "reuters.com": 10, "apnews.com": 10,
    "nature.com": 10, "nasa.gov": 10,
    "forbes.com": 10, "fortune.com": 10,
    "businessinsider.com": 10, "bloomberg.com": 10,
    "theverge.com": 10, "wired.com": 10,
    "techcrunch.com": 10, "axios.com": 10,
    "vox.com": 10, "theatlantic.com": 10,
    "nbcnews.com": 10, "cbsnews.com": 10,
    "foxnews.com": 10, "reddit.com": 10,
    "vanityfair.com": 10, "vogue.com": 10,
    "gq.com": 10, "elle.com": 10,
    "glamour.com": 10, "harvard.edu": 10,
    "mit.edu": 10, "stanford.edu": 10,
    "economist.com": 10, "wsj.com": 10,
    "ft.com": 10, "cnbc.com": 10,

    # Tier 9: Very well known
    "arstechnica.com": 9, "engadget.com": 9,
    "scientificamerican.com": 9, "popsci.com": 9,
    "technologyreview.com": 9, "geekwire.com": 9,
    "futurism.com": 9, "theregister.com": 9,
    "slashdot.org": 9, "thehackernews.com": 9,
    "mashable.com": 9, "deadline.com": 9,
    "variety.com": 9, "hollywoodreporter.com": 9,
    "tmz.com": 9, "usatoday.com": 9,
    "latimes.com": 9, "washingtonpost.com": 9,
    "politico.com": 9, "time.com": 9,
    "espn.com": 9, "si.com": 9,
    "bleacherreport.com": 9, "pitchfork.com": 9,
    "rollingstone.com": 9, "billboard.com": 9,

    # Tier 8: Recognizable in niche / strong brands
    "bitcoinmagazine.com": 8, "coindesk.com": 8, "cointelegraph.com": 8,
    "phys.org": 8, "sciencedaily.com": 8,
    "futurity.org": 8, "universetoday.com": 8,
    "quantamagazine.org": 8, "science.org": 8,
    "modernfarmer.com": 8, "nylon.com": 8,
    "hypebeast.com": 8, "highsnobiety.com": 8,
    "ted.com": 8, "lrb.co.uk": 8,
    "parisreview.com": 8, "electricliterature.com": 8,
    "openculture.com": 8, "jstor.org": 8,
    "themarginalian.org": 8, "longreads.com": 8,
    "gizmodo.com": 8, "lifehacker.com": 8,
    "kotaku.com": 8, "ign.com": 8,
    "pcgamer.com": 8, "gamespot.com": 8,
    "travelandleisure.com": 8, "lonelyplanet.com": 8,
    "foodandwine.com": 8, "bonappetit.com": 8,
    "architecturaldigest.com": 8, "dezeen.com": 8,
    "petapixel.com": 8, "500px.com": 8,
    "motleyfool.com": 8, "fool.com": 8,
    "investopedia.com": 8, "seekingalpha.com": 8,
    "marketwatch.com": 8, "barrons.com": 8,
    "fastcompany.com": 8, "inc.com": 8,
    "entrepreneur.com": 8, "hbr.org": 8,

    # Tier 7: Solid mid-tier brands
    "bitcoinnews.com": 7, "cryptobriefing.com": 7,
    "coinjournal.net": 7, "financemagnates.com": 7,
    "endpts.com": 7, "healthcareittoday.com": 7,
    "hitconsultant.net": 7, "geekwire.com": 7,
    "rcrwireless.com": 7, "telecompaper.com": 7,
    "wiley.com": 7, "sciencedirect.com": 7,
    "jstor.org": 7, "thoughtcatalog.com": 7,
    "fivebooks.com": 7, "literaryhub.com": 7,
    "oldnavy.com": 7, "nordstrom.com": 7,
    "macys.com": 7, "sephora.com": 7,

    # Chinese sources tier mapping (keyword-based in function below)
}

# Chinese popularity keywords (higher score for well-known names)
ZH_POPULARITY_KEYWORDS = {
    10: ["美国之音", "bbc", "纽约时报", "卫报", " Reuters", "路透"],
    9:  ["云风", "阮一峰", "小众软件", "湾区日报", "极客公园", "36氪", "虎嗅", "爱范儿", "sspai", "少数派"],
    8:  ["美团", "阿里", "腾讯", "字节", "百度", "华为", "知乎", "豆瓣", "bilibili", "哔哩哔哩"],
    7:  ["python", "程序员", "工程师", "技术", "独立博客", "周刊"],
}


def get_popularity_score(feed: Dict[str, Any]) -> int:
    """Return popularity score 1-10 for a feed based on domain and name."""
    url = feed.get("url", "").lower()
    name = feed.get("name", "").lower()
    source_lang = feed.get("source_language", "en")

    # Domain matching
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    # Remove www. prefix for matching
    if domain.startswith("www."):
        domain = domain[4:]

    score = MEDIA_POPULARITY.get(domain, 0)
    if score == 0:
        # Try stripping subdomains for root domain match
        parts = domain.split(".")
        if len(parts) >= 2:
            root = ".".join(parts[-2:])
            score = MEDIA_POPULARITY.get(root, 0)

    # Name-based matching for Chinese feeds
    if source_lang == "zh" or "中文" in name or "普通话" in name:
        for tier_score, keywords in ZH_POPULARITY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in name:
                    score = max(score, tier_score)
                    break
            if score >= 10:
                break

    # Extra English name boosts for iconic media not caught by domain
    en_boosts = {
        "guardian": 10, "npr": 10, "bbc": 10, "reuters": 10,
        "nature": 10, "nasa": 10, "mit technology review": 9,
        "the verge": 10, "ars technica": 9, "engadget": 9,
        "wired": 10, "techcrunch": 10, "mashable": 9,
        "slashdot": 9, "hacker news": 9, "the register": 9,
        "reddit": 9, "substack": 7,
    }
    for keyword, boost in en_boosts.items():
        if keyword in name:
            score = max(score, boost)

    # Penalize author/section feeds so main publication feed ranks higher
    author_patterns = [
        "/feed/author/", "/feed/channel/", "/feeds/posts/default",
        "/rss/author/", "/feed/contributor/",
    ]
    if any(p in url for p in author_patterns):
        score = max(1, score - 2)

    # Explicit name overrides for starter-pack quality
    exact_name_boosts = {
        "the atlantic": 11,
        "vox": 11,
        "npr news": 11,
        "ars technica": 11,
        "the verge -  all posts": 11,
        "fortune » - fortune": 11,
        "business insider": 11,
        "nbc news top stories": 11,
        "foxnews.com": 11,
        "popular science": 11,
        "nature - issue - nature.com science feeds": 11,
        "guardian world": 11,
        "axios": 11,
        "mit technology review": 11,
        "wired": 11,
        "the economist": 11,
        "云风的 blog": 11,
        "python 工匠": 11,
        "onev's den": 10,
        "tony bai": 10,
        "geekplux": 10,
        "后端技术杂谈": 10,
        "罗磊的独立博客": 10,
        "debug客栈": 9,
        "硕鼠的博客站": 9,
        "囧克斯 勾三股四": 9,
    }
    exact = name.strip()
    if exact in exact_name_boosts:
        score = max(score, exact_name_boosts[exact])

    return max(score, 1)  # Minimum 1 so every feed has a score


# ==================== OPML Parsing ====================

def fetch_opml(url: str) -> Optional[str]:
    """Fetch OPML content from URL."""
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read().decode('utf-8')
        # Fix common XML malformations: unescaped ampersands in attribute values
        # This regex replaces bare & with &amp; when it's not already a valid entity
        content = re.sub(r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', content)
        return content
    except Exception as e:
        logger.warning(f"Failed to fetch OPML from {url}: {e}")
        return None


def parse_opml(xml_content: str, source_lang: str) -> List[Dict[str, Any]]:
    """Parse OPML XML and extract feed candidates."""
    feeds = []
    try:
        root = ET.fromstring(xml_content.strip())
    except ET.ParseError as e:
        logger.error(f"OPML parse error: {e}")
        return feeds

    for outline in root.findall('.//outline[@xmlUrl]'):
        title = outline.get('title') or outline.get('text') or 'Unknown'
        xml_url = outline.get('xmlUrl')
        html_url = outline.get('htmlUrl', '')
        if not xml_url:
            continue

        # Try to infer category from parent outline
        # Note: stdlib xml.etree.ElementTree does not have getparent(),
        # so we search for the outline that directly contains this node.
        category = 'General'
        for parent in root.iter('outline'):
            if outline in list(parent):
                category = parent.get('text', parent.get('title', 'General'))
                break

        # Auto-detect language from parent category for mixed OPMLs
        assigned_lang = source_lang
        if source_lang == "auto":
            if "中文" in category or "chinese" in category.lower():
                assigned_lang = "zh"
            else:
                assigned_lang = "en"

        feeds.append({
            'name': title.strip(),
            'url': xml_url.strip(),
            'html_url': html_url.strip(),
            'source_language': assigned_lang,
            'opml_category': category,
        })

    logger.info(f"Parsed {len(feeds)} feeds from {source_lang} OPML")
    return feeds


def parse_inoreader_opml(file_path: str) -> List[Dict[str, Any]]:
    """Parse Inoreader OPML export with smart category and language inference."""
    feeds = []
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"Inoreader OPML not found: {file_path}")
        return feeds
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"Inoreader OPML parse error for {path.name}: {e}")
        return feeds

    parent_map = {child: parent for parent in root.iter() for child in parent}

    for outline in root.findall('.//outline[@xmlUrl]'):
        title = outline.get('title') or outline.get('text') or 'Unknown'
        xml_url = outline.get('xmlUrl')
        html_url = outline.get('htmlUrl', '')
        if not xml_url:
            continue

        parent = parent_map.get(outline)
        category = 'General'
        if parent is not None and parent.tag == 'outline':
            category = parent.get('text', parent.get('title', 'General'))

        cat_lower = category.lower()
        name_lower = title.lower()

        if 'china' in cat_lower or 'bilibili' in name_lower or any(zh in name_lower for zh in ['中文网', '普通话', '美国之音']):
            assigned_lang = 'zh'
        elif 'japan' in cat_lower or any(jp in name_lower for jp in ['nhk', 'ニュース', '週刊', 'カラパイア', 'ロケット', 'ハムスター', '痛いニュース', 'ライフハッカー', '東洋経済']):
            assigned_lang = 'ja'
        elif any(fr in name_lower for fr in ['le parisien', 'le monde']):
            assigned_lang = 'fr'
        else:
            assigned_lang = 'en'

        feeds.append({
            'name': title.strip(),
            'url': xml_url.strip(),
            'html_url': html_url.strip(),
            'source_language': assigned_lang,
            'opml_category': category,
        })

    logger.info(f"Parsed {len(feeds)} feeds from Inoreader OPML {path.name}")
    return feeds

# ==================== Feed Validation ====================

class FeedValidationResult:
    def __init__(self, feed: Dict[str, Any], passed: bool, reason: str = "",
                 avg_length: int = 0, plain_text_ratio: float = 0.0,
                 language: str = "", articles_with_content: int = 0,
                 last_article_at: Optional[datetime] = None):
        self.feed = feed
        self.passed = passed
        self.reason = reason
        self.avg_length = avg_length
        self.plain_text_ratio = plain_text_ratio
        self.language = language
        self.articles_with_content = articles_with_content
        self.last_article_at = last_article_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.feed.get("name", "Unknown"),
            "url": self.feed.get("url", ""),
            "passed": self.passed,
            "reason": self.reason,
            "avg_length": self.avg_length,
            "plain_text_ratio": round(self.plain_text_ratio, 2),
            "language": self.language,
            "articles_with_content": self.articles_with_content,
            "last_article_at": self.last_article_at.isoformat() if self.last_article_at else None,
        }


def extract_plain_text(raw_content: str, sanitizer: HTMLSanitizer) -> str:
    """Extract plain text from raw HTML or content string."""
    if not raw_content:
        return ""
    cleaned = sanitizer.sanitize(raw_content)
    return sanitizer.sanitize_text(cleaned)


def _parse_published_date(published: Any) -> Optional[datetime]:
    """Parse a published date from RSSFetcher output to timezone-aware datetime."""
    if not published:
        return None
    try:
        if isinstance(published, str):
            published = datetime.fromisoformat(published.replace("Z", "+00:00"))
        if isinstance(published, datetime):
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            return published
    except Exception:
        pass
    return None


def detect_language(text: str) -> str:
    """Detect language code; returns 'unknown' on failure."""
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


async def validate_feed(
    feed: Dict[str, Any],
    rss_fetcher: RSSFetcher,
    sanitizer: HTMLSanitizer,
) -> FeedValidationResult:
    """
    Validate a single feed against all 5 rules.
    """
    url = feed["url"]
    target_lang = feed.get("source_language", "en")

    logger.info(f"Validating feed: {feed['name']} ({url})")

    articles = await rss_fetcher.fetch_feed(url)
    if not articles:
        return FeedValidationResult(feed, False, "无法获取文章或feed为空")

    sample = articles[:VALIDATION_CONFIG["sample_size"]]
    cfg = VALIDATION_CONFIG

    # Rule 1: Recency
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=cfg["recency_days"])
    recent_articles = []
    for art in sample:
        published = _parse_published_date(art.get("published_at") or art.get("published", ""))
        if published and published >= cutoff:
            recent_articles.append(art)

    if not recent_articles:
        return FeedValidationResult(feed, False, f"最近 {cfg['recency_days']} 天内无更新")

    # Rule 2 & 3 & 4: Content availability, length, cleanliness
    contents = []
    for art in sample:
        raw = art.get("content") or art.get("summary", "")
        if raw:
            plain = extract_plain_text(raw, sanitizer)
            if len(plain.strip()) > 20:
                contents.append((raw, plain))

    if len(contents) < cfg["min_articles_with_content"]:
        return FeedValidationResult(
            feed, False,
            f"有正文的文章不足 ({len(contents)}/{cfg['min_articles_with_content']})"
        )

    total_plain_len = sum(len(p) for _, p in contents)
    total_raw_len = sum(len(r) for r, _ in contents)
    avg_length = total_plain_len // len(contents) if contents else 0
    plain_text_ratio = (total_plain_len / total_raw_len) if total_raw_len > 0 else 0.0

    if avg_length < cfg["min_content_length"]:
        return FeedValidationResult(
            feed, False,
            f"平均正文长度不足 ({avg_length} < {cfg['min_content_length']})",
            avg_length=avg_length,
            plain_text_ratio=plain_text_ratio,
            articles_with_content=len(contents),
        )

    if plain_text_ratio < cfg["min_plain_text_ratio"]:
        return FeedValidationResult(
            feed, False,
            f"HTML/格式清洗评分过低 ({plain_text_ratio:.2f} < {cfg['min_plain_text_ratio']})",
            avg_length=avg_length,
            plain_text_ratio=plain_text_ratio,
            articles_with_content=len(contents),
        )

    # Rule 5: Language consistency
    combined_text = " ".join([p for _, p in contents])[:5000]
    lang = detect_language(combined_text)

    # langdetect returns 'zh-cn' or 'zh-tw' sometimes; normalize to 'zh'
    normalized_lang = "zh" if lang.startswith("zh") else lang
    normalized_target = "zh" if target_lang.startswith("zh") else target_lang

    if normalized_lang != normalized_target:
        return FeedValidationResult(
            feed, False,
            f"语言不匹配 (检测到 {lang}, 期望 {target_lang})",
            avg_length=avg_length,
            plain_text_ratio=plain_text_ratio,
            articles_with_content=len(contents),
            language=lang,
        )

    # Determine most recent article date from all fetched articles
    last_article_at = None
    for art in articles:
        published = _parse_published_date(art.get("published_at") or art.get("published", ""))
        if published and (last_article_at is None or published > last_article_at):
            last_article_at = published

    return FeedValidationResult(
        feed, True, "通过",
        avg_length=avg_length,
        plain_text_ratio=plain_text_ratio,
        articles_with_content=len(contents),
        language=lang,
        last_article_at=last_article_at,
    )


# ==================== Categorization ====================

INOREADER_CATEGORY_MAP = {
    "tech": ["tech news", "telecom", "healthtech"],
    "ai": ["ai", "artificial intelligence"],
    "news": ["world news", "usa"],
    "science": ["science & space"],
    "business": [
        "investing", "finance & economics", "crypto",
        "blockchain & cryptocurrency", "product management",
        "leadership", "entrepreneurship", "advertising",
        "public relations", "publishing"
    ],
    "longform": ["books", "arts & culture", "writing", "podcasts"],
    "lifestyle": [
        "gaming", "sports news", "basketball", "betting", "fitness",
        "wellness", "travel", "food", "drinks", "fashion & beauty",
        "cars", "diy & crafts", "architecture & design", "photography",
        "entertainment", "productivity", "agriculture"
    ],
}


def _map_inoreader_category(opml_category: str) -> Optional[str]:
    """Map Inoreader category text to Jasmine category."""
    cat_lower = opml_category.lower()
    for jasmine_cat, keywords in INOREADER_CATEGORY_MAP.items():
        for kw in keywords:
            if kw in cat_lower:
                return jasmine_cat
    return None


def _has_keyword(text: str, keywords: List[str]) -> bool:
    for k in keywords:
        # Use word boundaries for short English keywords; simple containment for phrases/CJK
        if len(k) <= 3 and k.isascii():
            if re.search(rf'\b{re.escape(k)}\b', text, re.IGNORECASE):
                return True
        else:
            if k in text:
                return True
    return False


def assign_category(feed: Dict[str, Any], source_lang: str) -> str:
    """Map validated feed to existing recommendedFeeds category."""
    name_lower = feed["name"].lower()
    opml_cat = feed.get("opml_category", "").lower()
    source_key = feed.get("source_key", "").lower()

    # Manual source overrides
    if "manual_news" in source_key:
        return "news"

    # Reddit-specific overrides based on subreddit name
    if "manual_reddit" in source_key:
        if "r/worldnews" in feed["name"]:
            return "news"
        if "r/technology" in feed["name"] or "r/gadgets" in feed["name"]:
            return "tech"
        if "r/programming" in feed["name"]:
            return "tech"
        if "r/science" in feed["name"]:
            return "science"
        if "r/business" in feed["name"]:
            return "business"
        # AskReddit, explainlikeimfive, todayilearned -> lifestyle
        return "lifestyle"

    # Source-level overrides for curated OPML bundles
    if "plenary_business" in source_key or "business" in opml_cat or "economy" in opml_cat:
        return "business"
    if "plenary_books" in source_key or "book" in opml_cat:
        return "longform"
    if "plenary_food" in source_key:
        return "lifestyle"
    if "plenary_gaming" in source_key or "game" in opml_cat:
        return "lifestyle"
    if "plenary_football" in source_key or "sport" in opml_cat or "football" in opml_cat or "cricket" in opml_cat:
        return "lifestyle"

    # Inoreader category mapping
    inoreader_mapped = _map_inoreader_category(opml_cat)
    if inoreader_mapped:
        return inoreader_mapped

    ai_keywords = ["ai", "openai", "machine learning", "ml", "artificial intelligence", "deep learning", "神经网络", "机器学习"]
    is_ai = _has_keyword(name_lower, ai_keywords) or _has_keyword(opml_cat, ai_keywords)

    if source_lang == "zh":
        if is_ai:
            return "ai"
        return "chinese"

    # English feeds
    if is_ai:
        return "ai"

    return "tech"


# ==================== Frontend Writer ====================

FRONTEND_HEADER = '''/**
 * Recommended RSS feeds for new users
 * Categorized for easy browsing during onboarding
 *
 * Feed icon: Google S2 Favicon API
 * https://www.google.com/s2/favicons?domain={domain}&sz=64
 */

/**
 * Helper: get favicon URL from feed URL
 */
export function getFaviconUrl(feedUrl, size = 32) {
  try {
    const url = new URL(feedUrl)
    return `https://www.google.com/s2/favicons?domain=${url.hostname}&sz=${size}`
  } catch {
    return null
  }
}

'''


def generate_recommended_feeds_js(validated_feeds: List[FeedValidationResult]) -> str:
    """Generate the content of recommendedFeeds.js from validated feeds."""
    # Group feeds by assigned category
    categorized: Dict[str, List[FeedValidationResult]] = {
        "popular": [],
        "tech": [],
        "ai": [],
        "chinese": [],
        "business": [],
        "lifestyle": [],
        "longform": [],
        "news": [],
        "science": [],
    }

    for result in validated_feeds:
        cat = assign_category(result.feed, result.feed.get("source_language", "en"))
        categorized.setdefault(cat, []).append(result)

    # Sort each category by popularity descending, then avg_length descending
    for cat in categorized:
        categorized[cat].sort(
            key=lambda r: (get_popularity_score(r.feed), r.avg_length),
            reverse=True,
        )

    # Pick top 8 for starter packs by popularity + quality
    en_popular = [r for r in validated_feeds if r.feed.get("source_language") == "en"]
    zh_popular = [r for r in validated_feeds if r.feed.get("source_language") == "zh"]
    en_popular.sort(key=lambda r: (get_popularity_score(r.feed), r.avg_length), reverse=True)
    zh_popular.sort(key=lambda r: (get_popularity_score(r.feed), r.avg_length), reverse=True)

    starter_en = en_popular[:STARTER_PACK_SIZE]
    starter_zh = zh_popular[:STARTER_PACK_SIZE]

    # Top feeds per language go to popular
    categorized["popular"] = starter_en + starter_zh
    # Remove them from their original categories to avoid duplicates
    popular_urls = {r.feed["url"] for r in categorized["popular"]}
    for cat in ["tech", "ai", "chinese", "business", "lifestyle", "longform", "news", "science"]:
        categorized[cat] = [r for r in categorized[cat] if r.feed["url"] not in popular_urls]

    lines = [FRONTEND_HEADER]

    # Starter pack EN
    lines.append("// English starter pack - Tech & Business focused")
    lines.append("export const starterPackFeedsEn = [")
    for r in starter_en:
        lines.append(f"  {{ name: '{escape_js_string(r.feed['name'])}', url: '{escape_js_string(r.feed['url'])}' }},")
    lines.append("]")
    lines.append("")

    # Starter pack ZH
    lines.append("// Chinese starter pack - Mixed sources including RSSHub and independent blogs")
    lines.append("export const starterPackFeedsZh = [")
    for r in starter_zh:
        lines.append(f"  {{ name: '{escape_js_string(r.feed['name'])}', url: '{escape_js_string(r.feed['url'])}' }},")
    lines.append("]")
    lines.append("")

    lines.append("// Default export for backward compatibility")
    lines.append("export const starterPackFeeds = starterPackFeedsEn")
    lines.append("")
    lines.append("// Helper to get localized starter pack")
    lines.append("export function getStarterPackFeeds(locale) {")
    lines.append("  return locale === 'zh' ? starterPackFeedsZh : starterPackFeedsEn")
    lines.append("}")
    lines.append("")

    # Category labels
    category_labels = {
        "popular": ("Popular", "精选推荐", "🔥"),
        "tech": ("Technology", "科技", "💻"),
        "ai": ("AI & ML", "AI & 机器学习", "🤖"),
        "chinese": ("Chinese", "中文源", "🇨🇳"),
        "business": ("Business & Finance", "商业财经", "💰"),
        "lifestyle": ("Health & Lifestyle", "健康生活", "🏋️"),
        "longform": ("Long-form & Thinking", "深度阅读", "📚"),
        "news": ("News", "新闻时事", "📰"),
        "science": ("Science & Space", "科学探索", "🔬"),
    }

    lines.append("""/**
 * Full recommended feed catalog
 * AUTO-GENERATED for curated categories; manual categories preserved below
 */""")
    lines.append("export const recommendedFeeds = [")

    for cat_key in ["popular", "tech", "ai", "chinese", "business", "lifestyle", "longform", "news", "science"]:
        results = categorized.get(cat_key, [])
        if not results:
            continue
        en_label, zh_label, icon = category_labels[cat_key]
        lines.append("  {")
        lines.append(f"    category: '{cat_key}',")
        lines.append(f"    label: {{ en: '{en_label}', zh: '{zh_label}' }},")
        lines.append(f"    icon: '{icon}',")
        lines.append("    feeds: [")
        for r in results:
            name = escape_js_string(r.feed["name"])
            url = escape_js_string(r.feed["url"])
            desc = f"{r.feed['name']} - validated"
            lines.append(f"      {{ name: '{name}', url: '{url}', desc: '{escape_js_string(desc)}' }},")
        lines.append("    ]")
        lines.append("  },")

    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def escape_js_string(s: str) -> str:
    """Escape a string for safe inclusion in JS single-quoted string."""
    s = s.replace('\\', '\\\\')
    s = s.replace("'", "\\'")
    s = s.replace('"', '\\"')
    s = s.replace('`', '\\`')
    s = s.replace('$', '\\$')
    s = s.replace('\n', ' ')
    s = s.replace('\r', ' ')
    s = s.replace('\t', ' ')
    s = s.replace('</script>', '<\\/script>')
    # Remove other control characters
    s = re.sub(r'[\x00-\x1f]', ' ', s)
    return s


# ==================== Report Generator ====================

def generate_report(results: List[FeedValidationResult]) -> str:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    lines = ["# OPML Feed Import Report", ""]
    lines.append(f"- **Total feeds parsed**: {len(results)}")
    lines.append(f"- **Passed**: {len(passed)}")
    lines.append(f"- **Failed**: {len(failed)}")
    lines.append("")

    lines.append("## Passed Feeds by Category")
    categorized: Dict[str, List[FeedValidationResult]] = {}
    for r in passed:
        cat = assign_category(r.feed, r.feed.get("source_language", "en"))
        categorized.setdefault(cat, []).append(r)

    for cat, items in sorted(categorized.items()):
        lines.append(f"\n### {cat} ({len(items)})")
        for r in items[:10]:
            lines.append(f"- {r.feed['name']} ({r.avg_length} chars, {r.plain_text_ratio:.2f} ratio)")
        if len(items) > 10:
            lines.append(f"- ... and {len(items) - 10} more")

    lines.append("\n## Failed Feeds Breakdown")
    # Bucket reasons
    fetch_failures = []
    recency_failures = []
    content_failures = []
    length_failures = []
    cleanliness_failures = []
    language_failures = []
    other_failures = []

    for r in failed:
        reason = r.reason
        if "无法获取文章" in reason or "feed为空" in reason or "Timeout" in reason or "HTTP " in reason or "Cannot connect" in reason or "SSL" in reason or "certificate" in reason or "DNS" in reason:
            fetch_failures.append(r)
        elif "最近" in reason and "天内无更新" in reason:
            recency_failures.append(r)
        elif "有正文的文章不足" in reason:
            content_failures.append(r)
        elif "平均正文长度不足" in reason:
            length_failures.append(r)
        elif "HTML/格式清洗评分过低" in reason:
            cleanliness_failures.append(r)
        elif "语言不匹配" in reason:
            language_failures.append(r)
        else:
            other_failures.append(r)

    breakdown = [
        ("Fetch failure (超时/404/SSL/DNS/无法连接)", fetch_failures),
        ("Recency (30天内无更新)", recency_failures),
        ("Content availability (有正文文章不足)", content_failures),
        ("Length (平均正文长度不足)", length_failures),
        ("Cleanliness (HTML/格式评分过低)", cleanliness_failures),
        ("Language mismatch", language_failures),
        ("Other", other_failures),
    ]

    for label, items in breakdown:
        pct = (len(items) / len(failed) * 100) if failed else 0
        lines.append(f"- **{label}**: {len(items)} ({pct:.1f}%)")

    lines.append("\n## Failed Feeds (sample)")
    for r in failed[:20]:
        lines.append(f"- {r.feed['name']}: {r.reason}")
    if len(failed) > 20:
        lines.append(f"- ... and {len(failed) - 20} more")

    return "\n".join(lines)


# ==================== Database Writer ====================

def write_to_db(db_manager: DatabaseManager, results: List[FeedValidationResult]) -> None:
    passed = [r for r in results if r.passed]
    logger.info(f"Writing {len(passed)} validated feeds to database...")
    for r in passed:
        success = db_manager.upsert_feed_validation(
            feed_url=r.feed["url"],
            feed_name=r.feed["name"],
            language=r.feed.get("source_language", "en"),
            is_valid=True,
            article_count=r.articles_with_content,
            avg_content_length=r.avg_length,
            last_article_at=r.last_article_at,
            validation_metadata={
                "plain_text_ratio": round(r.plain_text_ratio, 4),
                "detected_language": r.language,
                "opml_category": r.feed.get("opml_category", ""),
            }
        )
        if not success:
            logger.warning(f"DB write failed for {r.feed['url']}")


# ==================== Main CLI ====================

async def main_async():
    parser = argparse.ArgumentParser(description="Import and validate OPML feeds")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Preview without writing")
    parser.add_argument("--write", action="store_true", default=False, help="Write to frontend and DB")
    parser.add_argument("--en-opml", type=str, default=None, help="Local English OPML file")
    parser.add_argument("--zh-opml", type=str, default=None, help="Local Chinese OPML file")
    parser.add_argument("--report-out", type=str, default=None, help="Save report to file")
    parser.add_argument("--limit", type=int, default=None, help="Limit total number of feeds to validate")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent feed validations")
    parser.add_argument(
        "--sources",
        type=str,
        default="curated_mixed,curated_en",
        help="Comma-separated list of source keys to use (default: curated_mixed,curated_en). Options: en,zh,curated_mixed,curated_en",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.write:
        args.dry_run = True  # Default to safe mode

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    rss_fetcher = RSSFetcher()
    sanitizer = HTMLSanitizer()

    all_candidates: List[Dict[str, Any]] = []

    source_keys = [s.strip() for s in args.sources.split(",") if s.strip()]

    # Legacy local file overrides
    if args.en_opml:
        with open(args.en_opml, "r", encoding="utf-8") as f:
            xml = f.read()
        all_candidates.extend(parse_opml(xml, "en"))
    if args.zh_opml:
        with open(args.zh_opml, "r", encoding="utf-8") as f:
            xml = f.read()
        all_candidates.extend(parse_opml(xml, "zh"))

    # Additional OPML exports (pass via --inoreader / place your own exports here)
    INOREADER_FILES = []
    for inoreader_path in INOREADER_FILES:
        inoreader_feeds = parse_inoreader_opml(str(inoreader_path))
        for f in inoreader_feeds:
            if f["source_language"] not in ("en", "zh"):
                continue
            f["source_key"] = "inoreader"
            all_candidates.append(f)

    # Fetch from configured remote sources
    for key in source_keys:
        if key not in OPML_SOURCES:
            logger.warning(f"Unknown source key: {key}, skipping")
            continue
        cfg = OPML_SOURCES[key]
        xml = fetch_opml(cfg["url"])
        if xml:
            candidates = parse_opml(xml, cfg["target_language"])
            for c in candidates:
                c["source_key"] = key
            all_candidates.extend(candidates)

    # Inject manually curated feeds
    for mf in MANUAL_FEEDS:
        all_candidates.append(dict(mf))

    if not all_candidates:
        logger.error("No feeds found from any OPML source.")
        return

    # Deduplicate by URL (keep first occurrence, which prioritizes earlier sources)
    seen_urls = set()
    deduped_candidates = []
    for c in all_candidates:
        url = c["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        deduped_candidates.append(c)
    all_candidates = deduped_candidates

    if args.limit and len(all_candidates) > args.limit:
        all_candidates = all_candidates[:args.limit]

    logger.info(f"Starting validation for {len(all_candidates)} feeds (concurrency={args.concurrency})...")

    semaphore = asyncio.Semaphore(args.concurrency)

    async def _validate_one(candidate: Dict[str, Any]) -> FeedValidationResult:
        async with semaphore:
            return await validate_feed(candidate, rss_fetcher, sanitizer)

    results = await asyncio.gather(*[_validate_one(c) for c in all_candidates])

    report = generate_report(results)
    print("\n" + report)

    if args.report_out:
        report_path = Path(args.report_out)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        logger.info(f"Report saved to {args.report_out}")

    if args.write:
        # Write frontend
        js_content = generate_recommended_feeds_js([r for r in results if r.passed])
        frontend_path = PROJECT_ROOT / "frontend" / "src" / "config" / "recommendedFeeds.js"
        frontend_path.parent.mkdir(parents=True, exist_ok=True)
        frontend_path.write_text(js_content, encoding="utf-8")
        logger.info(f"Updated frontend file: {frontend_path}")

        # Write backend
        db_manager = DatabaseManager(pg_config=settings.postgres_config)
        try:
            write_to_db(db_manager, results)
        finally:
            db_manager.close_pool()
        logger.info("Database update complete.")
    else:
        logger.info("Dry-run complete. No files or database were modified.")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
