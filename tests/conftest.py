"""
RSS管理UI测试配置和fixtures
"""
import sys
import os

# 将项目根目录加入 sys.path，确保 backend 包可被 pytest 正确导入
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# 开源版：测试不依赖开发者本地的 .env（该文件不入库）。
# Settings 中必填但测试无实际用途的字段在此提供哑默认值，
# 必须在任何 backend 模块导入之前设置。
os.environ.setdefault("POSTGRES_PASSWORD", "test_postgres_password")
# 需 ≥32 字符（settings.py 有长度校验）
os.environ.setdefault("SECRET_KEY", "test_secret_key_0123456789_0123456789")
os.environ.setdefault("JWT_SECRET_KEY", "test_jwt_secret_key_0123456789_012345")

import pytest
import requests
import time
from typing import Dict, Any
from unittest.mock import MagicMock, patch

# 测试配置
TEST_BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
TEST_USER_ID = os.getenv("TEST_USER_ID", "test-user")
TEST_ENV = os.getenv("TEST_ENV", "local")  # local, ci, mock

# 测试数据库配置（用于本地测试）
TEST_DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),  # 测试环境使用 5433
    "database": os.getenv("POSTGRES_DB", "jasmine_test"),
    "user": os.getenv("POSTGRES_USER", "test"),
    "password": os.getenv("POSTGRES_PASSWORD", "test123"),
}

@pytest.fixture(scope="session")
def api_base_url():
    """API基础URL"""
    return TEST_BASE_URL

@pytest.fixture(scope="session")
def test_user_id():
    """测试用户ID"""
    return TEST_USER_ID

@pytest.fixture(scope="session")
def api_client():
    """API客户端"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session

@pytest.fixture(scope="session")
def api_client_auth():
    """带有认证头的 API 客户端（默认 test-user/test123）"""
    username = os.getenv('TEST_USERNAME', 'test-user')
    password = os.getenv('TEST_PASSWORD', 'test123')
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    r = session.post(f"{TEST_BASE_URL}/api/auth/login", json={"username": username, "password": password})
    if r.status_code == 200 and 'access_token' in r.json():
        session.headers['Authorization'] = f"Bearer {r.json()['access_token']}"
    return session

@pytest.fixture(scope="session")
def wait_for_server():
    """等待服务器启动"""
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f"{TEST_BASE_URL}/docs", timeout=5)
            if response.status_code == 200:
                print(f"✅ 服务器就绪 (尝试 {i+1}/{max_retries})")
                return True
        except requests.exceptions.RequestException:
            if i < max_retries - 1:
                print(f"⏳ 等待服务器启动... ({i+1}/{max_retries})")
                time.sleep(2)

    pytest.fail(f"❌ 服务器在 {max_retries * 2} 秒内未启动")

@pytest.fixture
def test_feed_data():
    """测试订阅源数据"""
    return {
        "valid_feed": {
            "feed_name": "V2EX热门话题",
            "feed_url": "https://rsshub.app/v2ex/topics/hot"
        },
        "bilibili_feed": {
            "feed_name": "B站动态测试",
            "feed_url": "https://rsshub.app/bilibili/user/dynamic/313609123"
        },
        "problematic_feed": {
            "feed_name": "小红书测试",
            "feed_url": "https://rsshub.app/xiaohongshu/user/5f3a9b9e00000000010035fe"
        },
        "invalid_feed": {
            "feed_name": "无效源",
            "feed_url": "https://invalid-url-that-does-not-exist.com/rss"
        }
    }

@pytest.fixture
def clean_user_feeds(api_client_auth, api_base_url, test_user_id):
    """清理测试用户的所有订阅源"""
    def cleanup():
        try:
            # 获取用户所有订阅源
            response = api_client_auth.get(f"{api_base_url}/user/{test_user_id}/feeds")
            if response.status_code == 200:
                feeds = response.json().get("feeds", [])

                # 删除所有订阅源
                for feed in feeds:
                    feed_id = feed.get("id")
                    if feed_id:
                        api_client_auth.delete(f"{api_base_url}/user/{test_user_id}/feeds/{feed_id}")
        except Exception as e:
            print(f"清理订阅源时出错: {e}")

    # 测试前清理
    cleanup()
    yield
    # 测试后清理
    cleanup()


# ============================================================================
# Mock Fixtures - 用于单元测试，避免依赖外部服务
# ============================================================================

@pytest.fixture
def mock_rsshub_response():
    """Mock RSSHub 响应数据"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>测试订阅源</title>
    <link>https://example.com</link>
    <description>测试描述</description>
    <item>
      <title>测试文章标题</title>
      <link>https://example.com/article/1</link>
      <description>测试文章描述</description>
      <pubDate>Mon, 03 Feb 2026 10:00:00 GMT</pubDate>
      <guid>https://example.com/article/1</guid>
    </item>
    <item>
      <title>测试文章标题2</title>
      <link>https://example.com/article/2</link>
      <description>测试文章描述2</description>
      <pubDate>Mon, 03 Feb 2026 11:00:00 GMT</pubDate>
      <guid>https://example.com/article/2</guid>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def mock_bilibili_feed():
    """Mock Bilibili RSS Feed"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>B站动态测试</title>
    <link>https://www.bilibili.com</link>
    <item>
      <title>测试视频标题</title>
      <link>https://www.bilibili.com/video/BV1xx411c7mD</link>
      <description>测试视频描述</description>
      <pubDate>Mon, 03 Feb 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def mock_rsshub(monkeypatch, mock_rsshub_response, mock_bilibili_feed):
    """Mock RSSHub 服务，避免依赖真实的 RSSHub"""
    def mock_fetch_feed(url: str):
        """根据 URL 返回不同的 Mock 数据"""
        if "bilibili" in url:
            return mock_bilibili_feed
        elif "xiaohongshu" in url:
            # 小红书经常失败，返回空数据
            return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>小红书</title></channel></rss>"""
        else:
            return mock_rsshub_response

    # Mock feedparser 或 RSS 抓取函数
    # 注意：需要根据实际代码路径调整
    try:
        monkeypatch.setattr("backend.services.rss_service.fetch_feed", mock_fetch_feed)
    except AttributeError:
        # 如果路径不存在，跳过（单元测试可能不需要）
        pass

    return mock_fetch_feed


@pytest.fixture
def mock_openai_tts(monkeypatch):
    """Mock OpenAI TTS 服务，避免消耗 API 配额"""
    def mock_generate_speech(text: str, voice: str = "alloy", **kwargs):
        """返回假的音频数据"""
        # 返回一个简单的 MP3 header（足够测试使用）
        return b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 100

    try:
        monkeypatch.setattr(
            "backend.services.tts_service.generate_speech",
            mock_generate_speech
        )
    except AttributeError:
        pass

    return mock_generate_speech


@pytest.fixture
def mock_wechat2rss(monkeypatch):
    """Mock wechat2rss 服务，避免消耗付费配额"""
    mock_data = {
        "feeds": [
            {
                "id": "test-feed-1",
                "title": "测试公众号",
                "url": "https://wechat2rss.marlinworks.xyz/feed/test-feed-1"
            }
        ]
    }

    def mock_get_feeds():
        return mock_data

    try:
        monkeypatch.setattr(
            "backend.services.wechat_service.get_feeds",
            mock_get_feeds
        )
    except AttributeError:
        pass

    return mock_data


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis，使用 fakeredis"""
    try:
        from fakeredis import FakeRedis
        fake_redis = FakeRedis()

        # Mock Redis 连接
        monkeypatch.setattr("backend.core.cache.redis_client", fake_redis)
        return fake_redis
    except ImportError:
        # 如果 fakeredis 未安装，返回 MagicMock
        mock = MagicMock()
        mock.get.return_value = None
        mock.set.return_value = True
        return mock


@pytest.fixture
def mock_database(monkeypatch):
    """Mock 数据库连接（用于纯单元测试）"""
    mock_db = MagicMock()
    mock_db.execute.return_value = []
    mock_db.commit.return_value = None
    mock_db.rollback.return_value = None

    try:
        monkeypatch.setattr("backend.core.database.db_session", mock_db)
    except AttributeError:
        pass

    return mock_db


# ============================================================================
# 测试环境自动配置
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """自动配置测试环境"""
    print(f"\n🧪 测试环境: {TEST_ENV}")

    if TEST_ENV == "local":
        print(f"📝 使用本地测试数据库: {TEST_DB_CONFIG['host']}:{TEST_DB_CONFIG['port']}")
    elif TEST_ENV == "ci":
        print("📝 使用 CI 环境配置")
    elif TEST_ENV == "mock":
        print("📝 使用 Mock 模式（无外部依赖）")

    yield

    print("\n✅ 测试环境清理完成")
