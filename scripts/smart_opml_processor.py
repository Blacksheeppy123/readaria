import os
import sys
import xml.etree.ElementTree as ET
import asyncio
import logging
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(project_root)

from backend.fetcher.rss_fetcher import RSSFetcher
from backend.fetcher.feed_url_manager import create_feed_url_manager
from backend.storage.database_manager_v2 import DatabaseManagerV2

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SmartOPMLProcessor:
    """智能OPML处理器，支持本地/公共RSSHub自动切换"""

    def __init__(self, mode: str = 'smart'):
        """
        初始化处理器

        Args:
            mode: URL管理模式
                - 'smart': 智能模式（默认）
                - 'local': 强制本地RSSHub
                - 'public': 优先公共RSSHub
                - 'prefer_local': 偏好本地RSSHub
        """
        self.rss_fetcher = RSSFetcher()
        self.db_manager = DatabaseManagerV2()
        self.url_manager = create_feed_url_manager(mode)
        self.mode = mode

    def parse_opml(self, opml_file_path: str) -> List[Dict[str, str]]:
        """解析OPML文件，提取feed信息"""
        feeds = []
        try:
            tree = ET.parse(opml_file_path)
            root = tree.getroot()

            for outline in root.findall('.//outline[@xmlUrl]'):
                feed_info = {
                    'title': outline.get('title', outline.get('text', 'Unknown')),
                    'xml_url': outline.get('xmlUrl'),
                    'html_url': outline.get('htmlUrl', ''),
                    'type': outline.get('type', 'rss'),
                    'category': self._get_category(outline, root)
                }
                feeds.append(feed_info)

            logger.info(f"从OPML文件解析到 {len(feeds)} 个feed源")
            return feeds

        except Exception as e:
            logger.error(f"解析OPML文件失败: {str(e)}")
            return []

    def _get_category(self, outline_element, root) -> str:
        """获取feed所属分类"""
        for parent in root.iter('outline'):
            if outline_element in list(parent):
                return parent.get('text', 'General')
        return 'General'

    def analyze_feeds(self, feeds: List[Dict[str, str]]) -> Dict[str, any]:
        """分析feed列表"""
        feed_urls = [f['xml_url'] for f in feeds]
        stats = self.url_manager.analyze_feed_list(feed_urls)

        logger.info(f"\n{'='*60}")
        logger.info("Feed源分析结果")
        logger.info(f"{'='*60}")
        logger.info(f"总计: {stats['total']} 个feed")
        logger.info(f"  - RSSHub源: {stats['rsshub_feeds']} 个")
        logger.info(f"  - 直接RSS源: {stats['direct_rss_feeds']} 个")
        logger.info(f"  - 需要认证: {stats['requires_auth']} 个")
        logger.info(f"  - 无需认证: {stats['no_auth_required']} 个")

        if stats['platforms']:
            logger.info(f"\n平台分布:")
            for platform, count in stats['platforms'].items():
                auth_status = "🔐 需要认证" if self.url_manager.requires_authentication(platform) else "🔓 无需认证"
                logger.info(f"  - {platform}: {count} 个 {auth_status}")

        if stats['recommendations']:
            logger.info(f"\n💡 建议:")
            for rec in stats['recommendations']:
                logger.info(f"  • {rec}")

        logger.info(f"{'='*60}\n")

        return stats

    async def create_user_feeds(self, feeds: List[Dict[str, str]], user_id: str) -> Dict[str, str]:
        """
        为用户创建feed订阅

        Returns:
            feed_url -> subscription_id的映射
        """
        logger.info(f"为用户 {user_id} 创建 {len(feeds)} 个feed订阅")
        feed_mapping = {}

        for feed_info in feeds:
            try:
                # 优化URL
                original_url = feed_info['xml_url']
                optimal_url = self.url_manager.get_optimal_url(original_url)

                # 检查是否已存在订阅（使用优化后的URL）
                existing_feed = self.db_manager.get_user_feed_by_url(user_id, optimal_url)
                if existing_feed:
                    logger.info(f"订阅已存在: {feed_info['title']}")
                    feed_mapping[optimal_url] = existing_feed['id']
                    continue

                # 创建新订阅
                feed_config = {
                    'category': feed_info['category'],
                    'description': f"从 {feed_info['html_url']} 导入",
                    'is_active': True,
                    'original_url': original_url,  # 保存原始URL
                    'optimal_url': optimal_url     # 保存优化后的URL
                }

                feed_id = self.db_manager.create_user_feed(
                    user_id=user_id,
                    source_type='rss',
                    feed_name=feed_info['title'],
                    feed_url=optimal_url,  # 使用优化后的URL
                    feed_config=feed_config
                )

                if feed_id:
                    logger.info(f"✅ 创建订阅成功: {feed_info['title']}")
                    if optimal_url != original_url:
                        logger.info(f"   URL已优化: {original_url} -> {optimal_url}")
                    feed_mapping[optimal_url] = feed_id
                else:
                    logger.error(f"❌ 创建订阅失败: {feed_info['title']}")

            except Exception as e:
                logger.error(f"❌ 创建订阅异常 {feed_info['title']}: {str(e)}")

        return feed_mapping

    async def fetch_and_store_articles(self, feed_info: Dict[str, str],
                                     subscription_id: str,
                                     user_id: str,
                                     max_articles: int = 3) -> int:
        """
        抓取并存储单个feed的文章

        Returns:
            成功存储的文章数量
        """
        try:
            # 优化URL
            optimal_url = self.url_manager.get_optimal_url(feed_info['xml_url'])

            logger.info(f"抓取feed: {feed_info['title']}")
            logger.info(f"  URL: {optimal_url}")

            # 抓取文章
            articles = await self.rss_fetcher.fetch_feed(optimal_url)
            if not articles:
                logger.warning(f"  未能获取到文章")
                return 0

            logger.info(f"  获取到 {len(articles)} 篇文章")

            # 限制数量
            articles = articles[:max_articles]
            success_count = 0

            for i, article in enumerate(articles, 1):
                try:
                    # 准备文章数据
                    article_data = {
                        'feed_id': subscription_id,
                        'title': article['title'],
                        'url': article['link'],
                        'author': article.get('author', ''),
                        'published_at': article['published'],
                        'content_text': article.get('content', '')[:1000] if article.get('content') else '',
                        'content_html': '',
                        'summary': article.get('summary', '')[:300] if article.get('summary') else '',
                        'translation': '',
                        'word_count': len(article.get('content', '')),
                        'cover_image_url': '',
                        'media_urls': [],
                        'entities': [],
                        'keywords': [],
                        'sentiment_score': 0.0
                    }

                    # 存储文章
                    article_id = self.db_manager.store_article(article_data)
                    if article_id:
                        success_count += 1
                        logger.info(f"  ✅ [{i}/{len(articles)}] {article['title'][:50]}...")

                except Exception as e:
                    logger.error(f"  ❌ 处理文章失败: {str(e)}")
                    continue

            logger.info(f"  完成：成功存储 {success_count}/{len(articles)} 篇文章\n")
            return success_count

        except Exception as e:
            logger.error(f"❌ 抓取feed失败 {feed_info['title']}: {str(e)}")
            return 0

    async def process_all_feeds(self, feeds: List[Dict[str, str]],
                               user_id: str,
                               max_articles_per_feed: int = 3):
        """处理所有feed"""
        logger.info(f"\n开始批量处理 {len(feeds)} 个feed源...")

        # 1. 分析feed
        stats = self.analyze_feeds(feeds)

        # 2. 创建订阅
        logger.info("步骤1: 创建feed订阅...")
        feed_mapping = await self.create_user_feeds(feeds, user_id)
        logger.info(f"成功创建 {len(feed_mapping)} 个订阅\n")

        # 3. 抓取文章
        logger.info(f"步骤2: 批量抓取文章（每个feed最多{max_articles_per_feed}篇）...")
        total_articles = 0

        for feed_info in feeds:
            optimal_url = self.url_manager.get_optimal_url(feed_info['xml_url'])

            if optimal_url in feed_mapping:
                subscription_id = feed_mapping[optimal_url]
                count = await self.fetch_and_store_articles(
                    feed_info, subscription_id, user_id, max_articles_per_feed
                )
                total_articles += count

                # 延迟，避免请求过快
                await asyncio.sleep(2)
            else:
                logger.warning(f"跳过未订阅的feed: {feed_info['title']}")

        # 4. 总结
        logger.info(f"\n{'='*60}")
        logger.info("处理完成总结")
        logger.info(f"{'='*60}")
        logger.info(f"✅ 成功创建订阅: {len(feed_mapping)} 个")
        logger.info(f"✅ 成功存储文章: {total_articles} 篇")
        logger.info(f"📊 平均每个feed: {total_articles/len(feed_mapping):.1f} 篇" if feed_mapping else "")
        logger.info(f"{'='*60}\n")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='智能OPML Feed处理器')
    parser.add_argument('--mode', type=str, default='smart',
                       choices=['smart', 'local', 'public', 'prefer_local'],
                       help='URL管理模式 (默认: smart)')
    parser.add_argument('--opml', type=str,
                       default='feeds.opml',
                       help='OPML文件路径')
    parser.add_argument('--user', type=str, default='test_user_003',
                       help='用户名')
    parser.add_argument('--max-articles', type=int, default=3,
                       help='每个feed最多抓取文章数')
    parser.add_argument('--analyze-only', action='store_true',
                       help='仅分析不处理')

    args = parser.parse_args()

    # 创建处理器
    processor = SmartOPMLProcessor(mode=args.mode)

    logger.info(f"{'='*60}")
    logger.info(f"智能OPML Feed处理器")
    logger.info(f"{'='*60}")
    logger.info(f"模式: {args.mode}")
    logger.info(f"OPML文件: {args.opml}")
    logger.info(f"用户: {args.user}")
    logger.info(f"{'='*60}\n")

    # 解析OPML
    opml_path = os.path.join(project_root, args.opml)
    feeds = processor.parse_opml(opml_path)

    if not feeds:
        logger.error("未找到有效的feed源")
        return

    # 如果只是分析
    if args.analyze_only:
        processor.analyze_feeds(feeds)
        return

    # 创建或获取用户
    try:
        user_id = processor.db_manager.create_user(
            username=args.user,
            email=f"{args.user}@example.com",
            password_hash="test_hash",
            full_name=f"测试用户 {args.user}"
        )
        logger.info(f"创建测试用户成功: {user_id}\n")
    except Exception as e:
        if "duplicate key" in str(e).lower():
            user = processor.db_manager.get_user_by_username(args.user)
            user_id = user['id']
            logger.info(f"使用现有用户: {user_id}\n")
        else:
            logger.error(f"创建用户失败: {e}")
            return

    # 处理所有feed
    await processor.process_all_feeds(feeds, user_id, args.max_articles)

    logger.info("\n🎉 所有处理完成！")


if __name__ == "__main__":
    asyncio.run(main())