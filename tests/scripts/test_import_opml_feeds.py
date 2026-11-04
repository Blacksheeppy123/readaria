import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_opml_feeds import (
    parse_opml,
    assign_category,
    extract_plain_text,
    escape_js_string,
    FeedValidationResult,
)
from backend.utils.html_sanitizer import HTMLSanitizer


SAMPLE_OPML = """
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline text="Tech Blogs">
      <outline text="Test Blog" title="Test Blog" xmlUrl="https://example.com/feed.xml" htmlUrl="https://example.com" />
    </outline>
  </body>
</opml>
"""


@pytest.mark.unit
def test_parse_opml_extracts_feed():
    feeds = parse_opml(SAMPLE_OPML, "en")
    assert len(feeds) == 1
    assert feeds[0]["name"] == "Test Blog"
    assert feeds[0]["url"] == "https://example.com/feed.xml"
    assert feeds[0]["source_language"] == "en"
    assert feeds[0]["opml_category"] == "Tech Blogs"


@pytest.mark.unit
def test_assign_category_en_tech():
    feed = {"name": "Cloudflare Blog", "opml_category": "Companies"}
    assert assign_category(feed, "en") == "tech"


@pytest.mark.unit
def test_assign_category_en_ai():
    feed = {"name": "OpenAI Research", "opml_category": "Research"}
    assert assign_category(feed, "en") == "ai"


@pytest.mark.unit
def test_assign_category_zh():
    feed = {"name": "阮一峰的网络日志", "opml_category": "编程"}
    assert assign_category(feed, "zh") == "chinese"


@pytest.mark.unit
def test_assign_category_zh_ai():
    feed = {"name": "机器学习笔记", "opml_category": "机器学习"}
    assert assign_category(feed, "zh") == "ai"


@pytest.mark.unit
def test_assign_category_avoids_false_positive():
    feed = {"name": "Mail Blog", "opml_category": "Tech"}
    assert assign_category(feed, "en") == "tech"


@pytest.mark.unit
def test_extract_plain_text():
    sanitizer = HTMLSanitizer()
    raw = "<p>Hello <strong>world</strong></p><script>alert(1)</script>"
    text = extract_plain_text(raw, sanitizer)
    assert "Hello world" in text
    assert "script" not in text.lower()
    assert "alert" not in text.lower()


@pytest.mark.unit
def test_escape_js_string():
    assert escape_js_string("It's great") == "It\\'s great"
    assert escape_js_string("Line\nBreak") == "Line Break"
    assert escape_js_string("back`tick") == "back\\`tick"
    assert escape_js_string("dollar$") == "dollar\\$"


@pytest.mark.unit
def test_feed_validation_result_to_dict():
    feed = {"name": "Test", "url": "https://test.com"}
    result = FeedValidationResult(feed, True, "ok", avg_length=300, plain_text_ratio=0.8, language="en")
    d = result.to_dict()
    assert d["passed"] is True
    assert d["avg_length"] == 300
    assert d["plain_text_ratio"] == 0.8
