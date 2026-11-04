#!/usr/bin/env python3
"""
RSS订阅源测试脚本
用于测试OPML中的订阅源是否可以成功抓取
"""

import asyncio
import time
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.fetcher.rss_fetcher import RSSFetcher
from backend.fetcher.feed_url_manager import FeedURLManager

# 测试样本 - 选择代表性的订阅源
TEST_FEEDS = [
    # 无需认证 - 国内源
    {
        "name": "V2EX-最热主题",
        "url": "http://localhost:1200/v2ex/topics/hot",
        "type": "no_auth_cn",
        "platform": "v2ex"
    },
    {
        "name": "豆瓣-实时热门电影",
        "url": "http://localhost:1200/douban/list/movie_real_time_hotest",
        "type": "no_auth_cn",
        "platform": "douban"
    },
    {
        "name": "雪球-热帖",
        "url": "http://localhost:1200/xueqiu/hots",
        "type": "no_auth_cn",
        "platform": "xueqiu"
    },
    {
        "name": "华尔街见闻-最热文章",
        "url": "http://localhost:1200/wallstreetcn/hot",
        "type": "no_auth_cn",
        "platform": "wallstreetcn"
    },
    # 无需认证 - 国际源
    {
        "name": "宝玉的博客",
        "url": "http://localhost:1200/baoyu/blog",
        "type": "no_auth_intl",
        "platform": "baoyu"
    },
    # 直接RSS源
    {
        "name": "Last Week in AI",
        "url": "https://lastweekin.ai/feed",
        "type": "direct_rss",
        "platform": "direct"
    },
    # 需要认证 - Twitter
    {
        "name": "Twitter @Pavel Durov",
        "url": "http://localhost:1200/twitter/user/durov",
        "type": "auth_required",
        "platform": "twitter"
    },
    # 需要认证 - 小红书
    {
        "name": "Blacksheepy - 小红书笔记",
        "url": "http://localhost:1200/xiaohongshu/user/5f3a9b9e00000000010035fe/notes",
        "type": "auth_required",
        "platform": "xiaohongshu"
    },
    # 需要认证 - Bilibili
    {
        "name": "点金小侯 - bilibili 动态",
        "url": "http://localhost:1200/bilibili/user/dynamic/731771",
        "type": "auth_required",
        "platform": "bilibili"
    },
    {
        "name": "bilibili 排行榜-全站",
        "url": "http://localhost:1200/bilibili/ranking/0",
        "type": "no_auth_cn",
        "platform": "bilibili"
    },
    # YouTube
    {
        "name": "小Lin说 - YouTube",
        "url": "http://localhost:1200/youtube/user/@xiao_lin_shuo",
        "type": "auth_required",
        "platform": "youtube"
    },
    # 第三方RSS服务
    {
        "name": "红色安生-微信公众号",
        "url": "https://wechat2rss.xlab.app/feed/e2379df83a2450a7dd45022f0408c65cdf11563f.xml",
        "type": "third_party",
        "platform": "wechat"
    },
]


class FeedTester:
    def __init__(self):
        self.fetcher = RSSFetcher()
        self.url_manager = FeedURLManager()
        self.results = []

    async def test_single_feed(self, feed_info):
        """测试单个订阅源"""
        print(f"\n{'='*60}")
        print(f"测试: {feed_info['name']}")
        print(f"URL: {feed_info['url']}")
        print(f"类型: {feed_info['type']} | 平台: {feed_info['platform']}")
        print(f"{'='*60}")

        start_time = time.time()
        result = {
            "name": feed_info['name'],
            "url": feed_info['url'],
            "type": feed_info['type'],
            "platform": feed_info['platform'],
            "success": False,
            "error": None,
            "duration": 0,
            "article_count": 0,
            "sample_titles": []
        }

        try:
            # 使用现有的fetcher测试
            articles = await self.fetcher.fetch_feed(feed_info['url'])

            duration = time.time() - start_time
            result['duration'] = round(duration, 2)

            if articles and len(articles) > 0:
                result['success'] = True
                result['article_count'] = len(articles)
                # 获取前3篇文章标题
                result['sample_titles'] = [
                    article.get('title', 'No title')[:50]
                    for article in articles[:3]
                ]

                print(f"✅ 成功 - 抓取到 {len(articles)} 篇文章")
                print(f"⏱️  耗时: {duration:.2f}秒")
                print(f"📰 示例标题:")
                for i, title in enumerate(result['sample_titles'], 1):
                    print(f"   {i}. {title}")
            else:
                result['success'] = False
                result['error'] = "No articles returned"
                print(f"⚠️  失败 - 未返回文章")

        except Exception as e:
            duration = time.time() - start_time
            result['duration'] = round(duration, 2)
            result['error'] = str(e)
            print(f"❌ 失败 - {str(e)}")
            print(f"⏱️  耗时: {duration:.2f}秒")

        self.results.append(result)
        return result

    async def test_all_feeds(self):
        """测试所有订阅源"""
        print(f"\n🚀 开始测试 {len(TEST_FEEDS)} 个订阅源...")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        for i, feed_info in enumerate(TEST_FEEDS, 1):
            print(f"\n[{i}/{len(TEST_FEEDS)}]")
            await self.test_single_feed(feed_info)

            # 短暂延迟，避免请求过快
            if i < len(TEST_FEEDS):
                await asyncio.sleep(1)

        print(f"\n{'='*60}")
        print("📊 测试完成，生成报告...")
        print(f"{'='*60}")

    def generate_report(self):
        """生成测试报告"""
        total = len(self.results)
        success_count = sum(1 for r in self.results if r['success'])
        fail_count = total - success_count
        success_rate = (success_count / total * 100) if total > 0 else 0

        # 按类型分组统计
        type_stats = {}
        for result in self.results:
            feed_type = result['type']
            if feed_type not in type_stats:
                type_stats[feed_type] = {'total': 0, 'success': 0}
            type_stats[feed_type]['total'] += 1
            if result['success']:
                type_stats[feed_type]['success'] += 1

        # 生成报告
        report = []
        report.append("\n" + "="*80)
        report.append("📋 RSS订阅源测试报告")
        report.append("="*80)
        report.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"测试数量: {total} 个订阅源")
        report.append(f"")
        report.append(f"📈 总体结果:")
        report.append(f"  ✅ 成功: {success_count} 个 ({success_rate:.1f}%)")
        report.append(f"  ❌ 失败: {fail_count} 个")
        report.append(f"")

        # 按类型统计
        report.append(f"📊 按类型统计:")
        type_names = {
            'no_auth_cn': '无需认证-国内',
            'no_auth_intl': '无需认证-国际',
            'auth_required': '需要认证',
            'direct_rss': '直接RSS',
            'third_party': '第三方服务'
        }
        for feed_type, stats in type_stats.items():
            type_name = type_names.get(feed_type, feed_type)
            rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0
            report.append(f"  • {type_name}: {stats['success']}/{stats['total']} ({rate:.1f}%)")

        report.append(f"")
        report.append(f"📝 详细结果:")
        report.append(f"")

        # 成功的源
        success_results = [r for r in self.results if r['success']]
        if success_results:
            report.append(f"✅ 成功的订阅源 ({len(success_results)}):")
            for r in success_results:
                report.append(f"  • {r['name']}")
                report.append(f"    平台: {r['platform']} | 文章数: {r['article_count']} | 耗时: {r['duration']}秒")
            report.append(f"")

        # 失败的源
        fail_results = [r for r in self.results if not r['success']]
        if fail_results:
            report.append(f"❌ 失败的订阅源 ({len(fail_results)}):")
            for r in fail_results:
                report.append(f"  • {r['name']}")
                report.append(f"    平台: {r['platform']} | 类型: {r['type']}")
                report.append(f"    错误: {r['error']}")
            report.append(f"")

        # 建议
        report.append(f"💡 建议:")
        if success_rate >= 70:
            report.append(f"  ✅ 成功率达到 {success_rate:.1f}%，满足70%的目标要求")
        else:
            report.append(f"  ⚠️  成功率 {success_rate:.1f}%，未达到70%目标，需要优化")

        # 检查需要认证的源
        auth_required = [r for r in self.results if r['type'] == 'auth_required']
        auth_failed = [r for r in auth_required if not r['success']]
        if auth_failed:
            report.append(f"  • 有 {len(auth_failed)} 个需要认证的源失败，建议配置Cookie")
            report.append(f"    失败平台: {', '.join(set(r['platform'] for r in auth_failed))}")

        report.append(f"")
        report.append("="*80)

        report_text = "\n".join(report)
        print(report_text)

        # 保存报告
        report_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "feed_test_report.md"))
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# RSS订阅源测试报告\n\n")
            f.write(report_text)

        print(f"\n💾 报告已保存到: {report_file}")

        return {
            'success_rate': success_rate,
            'success_count': success_count,
            'fail_count': fail_count,
            'type_stats': type_stats
        }


async def main():
    tester = FeedTester()
    await tester.test_all_feeds()
    stats = tester.generate_report()

    # 返回退出码
    if stats['success_rate'] >= 70:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
