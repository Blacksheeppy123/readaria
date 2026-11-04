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
from backend.nlp.processor import NLPProcessor
from backend.storage.database_manager_v2 import DatabaseManagerV2

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OPMLProcessor:
    def __init__(self):
        self.rss_fetcher = RSSFetcher()
        self.nlp_processor = NLPProcessor()
        self.db_manager = DatabaseManagerV2()

    def parse_opml(self, opml_file_path: str) -> List[Dict[str, str]]:
        """解析OPML文件，提取feed信息"""
        feeds = []
        try:
            tree = ET.parse(opml_file_path)
            root = tree.getroot()

            # 查找所有outline元素
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
        # 在ElementTree中，我们需要手动查找父元素
        for parent in root.iter('outline'):
            if outline_element in list(parent):
                return parent.get('text', 'General')
        return 'General'

    async def process_feed_batch(self, feeds: List[Dict[str, str]], user_id: str, max_articles_per_feed: int = 5) -> None:
        """批量处理feed列表"""
        logger.info(f"开始处理 {len(feeds)} 个feed源，每个源最多抓取 {max_articles_per_feed} 篇文章")

        for i, feed_info in enumerate(feeds, 1):
            try:
                logger.info(f"\n===== 处理第 {i}/{len(feeds)} 个feed: {feed_info['title']} =====")
                logger.info(f"URL: {feed_info['xml_url']}")
                logger.info(f"分类: {feed_info['category']}")

                # 获取文章
                articles = await self.rss_fetcher.fetch_feed(feed_info['xml_url'])
                if not articles:
                    logger.warning(f"未能获取到文章: {feed_info['title']}")
                    continue

                logger.info(f"获取到 {len(articles)} 篇文章")

                # 限制文章数量
                articles = articles[:max_articles_per_feed]
                logger.info(f"将处理最新的 {len(articles)} 篇文章")

                # 处理每篇文章
                for j, article in enumerate(articles, 1):
                    try:
                        logger.info(f"  处理文章 {j}/{len(articles)}: {article['title']}")

                        # 添加用户ID和分类信息
                        article['user_id'] = user_id
                        article['category'] = feed_info['category']
                        article['feed_title'] = feed_info['title']

                        # NLP处理
                        processed_article = self.nlp_processor.process_article(article)

                        # 存储文章
                        success = self.db_manager.store_article(processed_article)
                        if success:
                            logger.info(f"  ✅ 成功处理并存储文章: {processed_article['title']}")
                        else:
                            logger.error(f"  ❌ 文章存储失败: {article['title']}")

                    except Exception as e:
                        logger.error(f"  ❌ 处理文章失败: {str(e)}")
                        continue

                logger.info(f"===== {feed_info['title']} 处理完成 =====\n")

                # 添加延迟避免请求过于频繁
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"❌ 处理feed失败 {feed_info['title']}: {str(e)}")
                continue

    async def create_user_feeds(self, feeds: List[Dict[str, str]], user_id: str) -> None:
        """为用户创建feed订阅"""
        logger.info(f"为用户 {user_id} 创建 {len(feeds)} 个feed订阅")

        for feed_info in feeds:
            try:
                # 检查是否已存在订阅
                existing_feed = self.db_manager.get_user_feed_by_url(user_id, feed_info['xml_url'])
                if existing_feed:
                    logger.info(f"订阅已存在，跳过: {feed_info['title']}")
                    continue

                # 创建新订阅
                feed_config = {
                    'category': feed_info['category'],
                    'description': f"从 {feed_info['html_url']} 导入",
                    'is_active': True
                }

                feed_id = self.db_manager.create_user_feed(
                    user_id=user_id,
                    source_type='RSS',
                    feed_name=feed_info['title'],
                    feed_url=feed_info['xml_url'],
                    feed_config=feed_config
                )
                success = bool(feed_id)
                if success:
                    logger.info(f"✅ 创建订阅成功: {feed_info['title']}")
                else:
                    logger.error(f"❌ 创建订阅失败: {feed_info['title']}")

            except Exception as e:
                logger.error(f"❌ 创建订阅异常 {feed_info['title']}: {str(e)}")

async def main():
    # OPML文件路径
    opml_file = os.path.join(project_root, "feeds.opml")  # path to your OPML export

    # 用户ID (可以从环境变量或参数获取)
    user_id = "test_user_001"  # 这里使用测试用户ID

    processor = OPMLProcessor()

    # 解析OPML文件
    logger.info("开始解析OPML文件...")
    feeds = processor.parse_opml(opml_file)

    if not feeds:
        logger.error("没有找到有效的feed源")
        return

    # 显示找到的feed源
    logger.info("\n找到的feed源:")
    for i, feed in enumerate(feeds, 1):
        logger.info(f"{i}. {feed['title']} ({feed['category']}) - {feed['xml_url']}")

    # 创建用户订阅
    logger.info("\n开始创建用户订阅...")
    await processor.create_user_feeds(feeds, user_id)

    # 批量处理feed
    logger.info("\n开始批量抓取和处理feed...")
    await processor.process_feed_batch(feeds, user_id, max_articles_per_feed=3)

    logger.info("\n🎉 所有feed处理完成！")

if __name__ == "__main__":
    asyncio.run(main())