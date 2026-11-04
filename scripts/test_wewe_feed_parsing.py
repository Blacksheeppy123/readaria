#!/usr/bin/env python3
"""
测试 WeWe RSS Feed 解析
"""
import sys
import os
import asyncio
import html

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.fetcher.rss_fetcher import RSSFetcher


async def test_wewe_feed():
    """测试 WeWe RSS feed 解析"""

    feed_url = "http://127.0.0.1:4000/feeds/MP_WXS_2392306830.atom"

    print("=" * 70)
    print("WeWe RSS Feed 解析测试")
    print("=" * 70)
    print(f"\nFeed URL: {feed_url}\n")

    fetcher = RSSFetcher()

    try:
        articles = await fetcher.fetch_feed(feed_url)

        print(f"✅ 成功抓取 {len(articles)} 篇文章\n")

        if articles:
            # 查看第一篇文章的详细信息
            article = articles[0]

            print("-" * 70)
            print(f"标题: {article.get('title', '')}")
            print(f"链接: {article.get('url', '')}")
            print(f"发布时间: {article.get('published_at', '')}")
            print(f"作者: {article.get('author', '')}")
            print("-" * 70)

            # 检查摘要
            summary = article.get('summary', '')
            print(f"\n摘要 (前 200 字符):")
            print(summary[:200] if summary else "(无摘要)")

            # 检查内容
            content = article.get('content', '')
            print(f"\n内容 (前 500 字符):")
            print(content[:500] if content else "(无内容)")

            # 检查是否有 HTML 实体编码问题
            print("\n" + "=" * 70)
            print("HTML 实体检查:")
            print("=" * 70)

            if '&amp;' in content or '&lt;' in content or '&gt;' in content:
                print("⚠️  检测到 HTML 实体编码 (&amp;, &lt;, &gt;)")
                print("\n解码后的内容 (前 500 字符):")
                decoded_content = html.unescape(content)
                print(decoded_content[:500])
            else:
                print("✅ 没有检测到 HTML 实体编码问题")

    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)


if __name__ == '__main__':
    asyncio.run(test_wewe_feed())
