"""Shared onboarding starter pack definitions."""

STARTER_PACK_FEEDS = {
    "zh": [
        {
            "feed_name": "牧之野",
            "feed_url": "https://wechat2rss.marlinworks.xyz/feed/3551111165.xml",
            "language": "zh",
            "is_valid": True,
        },
        {
            "feed_name": "金渐成",
            "feed_url": "https://wechat2rss.marlinworks.xyz/feed/3639555537.xml",
            "language": "zh",
            "is_valid": True,
        },
        {
            "feed_name": "路透财经早报",
            "feed_url": "https://wechat2rss.marlinworks.xyz/feed/3589865648.xml",
            "language": "zh",
            "is_valid": True,
        },
        {
            "feed_name": "程苓峰",
            "feed_url": "https://wechat2rss.marlinworks.xyz/feed/2399005440.xml",
            "language": "zh",
            "is_valid": True,
        },
        {
            "feed_name": "不懂经",
            "feed_url": "https://wechat2rss.marlinworks.xyz/feed/3584401771.xml",
            "language": "zh",
            "is_valid": True,
        },
    ],
    "en": [
        {
            "feed_name": "The Atlantic",
            "feed_url": "https://www.theatlantic.com/feed/all/",
            "language": "en",
            "is_valid": True,
        },
        {
            "feed_name": "Popular Science",
            "feed_url": "https://www.popsci.com/feed/",
            "language": "en",
            "is_valid": True,
        },
        {
            "feed_name": "Vox",
            "feed_url": "https://www.vox.com/rss/index.xml",
            "language": "en",
            "is_valid": True,
        },
        {
            "feed_name": "Axios",
            "feed_url": "https://www.axios.com/feeds/feed.rss",
            "language": "en",
            "is_valid": True,
        },
        {
            "feed_name": "Ars Technica",
            "feed_url": "https://feeds.arstechnica.com/arstechnica/index",
            "language": "en",
            "is_valid": True,
        },
    ],
}


def get_starter_pack_feed_defs(language: str) -> list[dict]:
    normalized = "zh" if str(language).startswith("zh") else "en"
    return [dict(feed) for feed in STARTER_PACK_FEEDS[normalized]]
