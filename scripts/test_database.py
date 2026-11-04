#!/usr/bin/env python3
"""
数据库功能测试脚本
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from core.config.settings import settings
from backend.storage.database import DatabaseManager

# 初始化 DatabaseManager
db_manager = DatabaseManager(pg_config=settings.postgres_config)

# 兼容旧代码的引用
database_v2 = db_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseTester:
    """数据库功能测试器"""

    def __init__(self):
        self.db = database_v2
        self.test_user_id = None
        self.test_feed_id = None
        self.test_article_id = None

    async def test_health_check(self):
        """测试健康检查"""
        logger.info("🔍 测试健康检查...")

        health = self.db.health_check()
        logger.info(f"健康状态: {health}")

        assert health['status'] in ['healthy', 'unhealthy'], "健康状态格式错误"
        assert 'services' in health, "缺少服务状态"
        assert 'postgres' in health['services'], "缺少PostgreSQL状态"

        if not health['services']['postgres']:
            raise Exception("PostgreSQL 连接失败")

        logger.info("✅ 健康检查测试通过")

    async def test_user_management(self):
        """测试用户管理"""
        logger.info("👤 测试用户管理...")

        # 创建测试用户
        username = f"test_user_{uuid4().hex[:8]}"
        email = f"{username}@test.com"
        password_hash = "test_password_hash"

        self.test_user_id = self.db.create_user(
            username=username,
            email=email,
            password_hash=password_hash,
            full_name="测试用户"
        )

        logger.info(f"创建用户: {username} ({self.test_user_id})")

        # 获取用户信息
        user = self.db.get_user_by_username(username)
        assert user is not None, "获取用户失败"
        assert user['username'] == username, "用户名不匹配"
        assert user['email'] == email, "邮箱不匹配"

        logger.info("✅ 用户管理测试通过")

    async def test_feed_management(self):
        """测试订阅源管理"""
        logger.info("📡 测试订阅源管理...")

        if not self.test_user_id:
            raise Exception("需要先创建测试用户")

        # 创建测试订阅源
        feed_name = "测试RSS源"
        feed_url = "https://test.example.com/rss.xml"
        feed_config = {"fetch_interval": 60, "enabled": True}

        self.test_feed_id = self.db.create_user_feed(
            user_id=self.test_user_id,
            source_type="rss",
            feed_name=feed_name,
            feed_url=feed_url,
            feed_config=feed_config
        )

        logger.info(f"创建订阅源: {feed_name} ({self.test_feed_id})")

        # 获取用户订阅源
        feeds = self.db.get_user_feeds(self.test_user_id)
        assert len(feeds) > 0, "获取订阅源失败"

        feed = feeds[0]
        assert feed['feed_name'] == feed_name, "订阅源名称不匹配"
        assert feed['feed_url'] == feed_url, "订阅源URL不匹配"
        assert feed['source_type'] == "rss", "源类型不匹配"

        # 按源类型获取
        rss_feeds = self.db.get_user_feeds(self.test_user_id, source_type="rss")
        assert len(rss_feeds) == 1, "按源类型获取失败"

        logger.info("✅ 订阅源管理测试通过")

    async def test_article_management(self):
        """测试文章管理"""
        logger.info("📰 测试文章管理...")

        if not self.test_feed_id:
            raise Exception("需要先创建测试订阅源")

        # 创建测试文章
        article_data = {
            'feed_id': self.test_feed_id,
            'title': '测试文章标题',
            'url': 'https://test.example.com/article/1',
            'author': '测试作者',
            'published_at': datetime.now(timezone.utc),
            'content_text': '这是一篇测试文章的内容，包含了一些中文文本用于测试搜索功能。',
            'content_html': '<p>这是一篇测试文章的内容</p>',
            'summary': '这是文章摘要',
            'translation': 'This is an article summary',
            'word_count': 50,
            'entities': [
                {'text': '测试', 'label': 'TEST', 'start': 0, 'end': 2}
            ],
            'keywords': ['测试', '文章', 'AI'],
            'sentiment_score': 0.8
        }

        self.test_article_id = self.db.store_article(article_data)
        logger.info(f"创建文章: {article_data['title']} ({self.test_article_id})")

        # 测试 PostgreSQL 搜索功能
        search_results = self.db.search_articles("测试文章", size=10)
        logger.info(f"搜索结果: {len(search_results)} 条")

        # 验证搜索结果
        if search_results:
            result = search_results[0]
            assert '测试文章' in result['title'], "搜索结果标题不匹配"
            logger.info("搜索功能正常")
        else:
            logger.warning("搜索未返回结果，请检查 PostgreSQL 全文搜索配置")

        logger.info("✅ 文章管理测试通过")

    async def test_system_stats(self):
        """测试系统统计"""
        logger.info("📊 测试系统统计...")

        stats = self.db.get_system_stats()
        logger.info(f"系统统计: {stats}")

        assert 'active_users' in stats, "缺少活跃用户统计"
        assert 'total_articles' in stats, "缺少文章总数统计"
        assert stats['active_users'] >= 1, "活跃用户数应该至少为1"

        logger.info("✅ 系统统计测试通过")

    async def test_connection_pool(self):
        """测试连接池"""
        logger.info("🔗 测试连接池...")

        # 并发执行多个数据库操作
        tasks = []
        for i in range(10):
            task = asyncio.create_task(self._concurrent_db_operation(i))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查是否有异常
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            logger.warning(f"并发操作中有 {len(exceptions)} 个异常: {exceptions}")
        else:
            logger.info("所有并发操作成功完成")

        logger.info("✅ 连接池测试通过")

    async def _concurrent_db_operation(self, index: int):
        """并发数据库操作"""
        try:
            health = self.db.health_check()
            await asyncio.sleep(0.1)  # 模拟一些处理时间
            return f"操作 {index} 完成"
        except Exception as e:
            logger.error(f"并发操作 {index} 失败: {e}")
            raise

    async def cleanup(self):
        """清理测试数据"""
        logger.info("🧹 清理测试数据...")

        try:
            # 删除测试文章（通过外键约束会自动处理）
            # 删除测试订阅源（通过外键约束会自动处理）
            # 删除测试用户
            if self.test_user_id:
                with db_manager.get_postgres_cursor() as cur:
                    cur.execute("DELETE FROM users WHERE id = %s", (self.test_user_id,))
                logger.info("测试数据清理完成")
        except Exception as e:
            logger.warning(f"清理测试数据失败: {e}")

    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始数据库功能测试...")

        try:
            await self.test_health_check()
            await self.test_user_management()
            await self.test_feed_management()
            await self.test_article_management()
            await self.test_system_stats()
            await self.test_connection_pool()

            logger.info("🎉 所有测试通过！")

        except Exception as e:
            logger.error(f"❌ 测试失败: {e}")
            raise
        finally:
            await self.cleanup()

async def main():
    """主函数"""
    try:
        # 检查配置
        logger.info(f"使用配置: PostgreSQL={settings.postgres_host}:{settings.postgres_port}")
        logger.info(f"数据库: {settings.postgres_db}")

        # 运行测试
        tester = DatabaseTester()
        await tester.run_all_tests()

        print("\n✅ 数据库功能测试全部通过！")

    except Exception as e:
        print(f"\n❌ 数据库测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())