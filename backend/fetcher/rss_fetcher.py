import feedparser
import requests
from datetime import datetime
from typing import List, Dict, Any
import logging
import email.utils
import time
import hashlib
import aiohttp
import asyncio
import uuid
from urllib.parse import urlparse, urlunparse

# Week 4.5: 导入速率限制器
from backend.fetcher.rate_limiter import PerHostRateLimiter, TimeoutConfig
# Week 4.5: 导入结构化日志
from backend.utils.logger import FeedFetchLogger, ContextLogger
# Docker 环境配置
from core.config.settings import Settings

class RSSFetcher:
    def __init__(
        self,
        max_concurrent_per_host: int = 3,
        request_interval: float = 0.5,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        total_timeout: float = 30.0,
        enable_adaptive_rate: bool = True
    ):
        """
        初始化 RSS 抓取器（Week 4.5: 添加速率限制和超时配置）

        Args:
            max_concurrent_per_host: 每个 host 的最大并发数
            request_interval: 同一 host 的请求间隔（秒）
            connect_timeout: 连接超时（秒）
            read_timeout: 读取超时（秒）
            total_timeout: 总超时（秒）
            enable_adaptive_rate: 是否启用自适应速率调整
        """
        self.logger = logging.getLogger(__name__)

        # Week 5 Cleanup (2025-11-20): wechat_cookie_manager removed - migrated to RSSHub-CookieCloud

        # Week 4.5: 创建结构化日志记录器
        self.context_logger = ContextLogger(self.logger)
        self.fetch_logger = FeedFetchLogger(self.context_logger)

        # Week 4.5: 速率限制器
        self.rate_limiter = PerHostRateLimiter(
            max_concurrent_per_host=max_concurrent_per_host,
            request_interval=request_interval,
            enable_adaptive=enable_adaptive_rate
        )

        # Week 4.5: 超时配置
        self.timeout_config = TimeoutConfig(
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            total_timeout=total_timeout
        )

        # 浏览器请求头，用于绕过 Cloudflare 防护
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

        # 简单的内存级抓取缓存，避免一段时间内重复抓取同一feed
        # 结构: { feed_url: { 'ts': epoch_seconds, 'articles': List[Dict] } }
        self._cache = {}
        # 每个feed_url一个异步锁，避免并发重复抓取
        self._locks = {}
        # 缓存有效期（秒）
        self._cache_ttl = 300

        # Docker 环境配置（用于 URL 转换）
        self.settings = Settings()

    def generate_feed_id(self, feed_url: str) -> str:
        """根据feed URL生成唯一ID"""
        # 使用MD5哈希生成确定性UUID
        hash_obj = hashlib.md5(feed_url.encode())
        # 将32位hex转换为标准UUID格式
        hex_str = hash_obj.hexdigest()
        return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"

    # ================== Week 5 Cleanup (2025-11-20): 微信 Cookie 注入功能已移除 ==================
    # Reason: Migrated to RSSHub-CookieCloud solution
    # - get_wechat_cookie_headers() removed
    # - handle_wechat_cookie_error() removed
    # - RSSHub-CookieCloud now handles cookie management directly
    # - See docs/wechat_cookie_sync_solution_v2.md for new architecture

    def _normalize_docker_url(self, feed_url: str) -> str:
        """
        Docker 环境 URL 转换：将 localhost 地址转换为 Docker 服务名

        在 Docker 容器中，localhost 指向容器本身，需要使用服务名访问其他容器：
        - http://localhost:4001 → http://wechat2rss:8080 (wechat2rss 服务)
        - http://localhost:1200 → http://rsshub:1200 (rsshub 服务)
        - http://127.0.0.1:4001 → http://wechat2rss:8080
        - http://127.0.0.1:1200 → http://rsshub:1200

        Args:
            feed_url: 原始 RSS URL

        Returns:
            转换后的 URL（如果需要转换）或原始 URL
        """
        try:
            parsed = urlparse(feed_url)

            # 检查是否为 localhost 或 127.0.0.1
            is_localhost = parsed.hostname in ('localhost', '127.0.0.1')

            if not is_localhost:
                return feed_url

            # wechat2rss: 端口 4001 → wechat2rss:8080
            if parsed.port == 4001 or ':4001' in parsed.netloc:
                wechat2rss_url = self.settings.wechat2rss_base_url.rstrip('/')
                new_url = f"{wechat2rss_url}{parsed.path}"
                if parsed.query:
                    new_url += f"?{parsed.query}"
                self.logger.info(f"Docker URL 转换: {feed_url} → {new_url}")
                return new_url

            # 2026-05-18: 本地 RSSHub 已移除，不再转换 localhost:1200
            # 其他 localhost URL 不转换
            return feed_url

        except Exception as e:
            self.logger.warning(f"URL 转换失败: {feed_url}, 错误: {e}")
            return feed_url

    # ================== RSS 抓取核心方法 ==================

    def parse_date(self, date_str: str) -> str:
        """解析RSS feed中的日期字符串为ISO格式"""
        # 如果日期为空或None，直接返回当前时间，不记录警告
        if not date_str or not date_str.strip():
            return datetime.now().isoformat()

        try:
            # 尝试解析RFC 2822格式的日期 (如: "Mon, 27 Oct 2025 10:30:00 GMT")
            parsed_date = email.utils.parsedate_tz(date_str)
            if parsed_date:
                timestamp = email.utils.mktime_tz(parsed_date)
                return datetime.fromtimestamp(timestamp).isoformat()

            # 尝试解析ISO格式 (如: "2025-10-27T10:30:00Z")
            try:
                # 移除时区标识符如Z或+00:00
                cleaned_date = date_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(cleaned_date)
                return dt.isoformat()
            except:
                pass

            # 尝试常见的日期格式
            date_formats = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%Y年%m月%d日",
            ]
            for fmt in date_formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.isoformat()
                except:
                    continue

            # 所有格式都无法解析，只对非空字符串记录警告
            if date_str.strip():
                self.logger.debug(f"无法解析日期格式: {date_str[:50]}，使用当前时间")
            return datetime.now().isoformat()

        except Exception as e:
            self.logger.error(f"日期解析错误: {str(e)}, date_str={date_str[:50] if date_str else 'None'}")
            return datetime.now().isoformat()
        
    async def fetch_feed_with_retry(self, feed_url: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        获取RSS源内容（Week 4.5: 集成速率限制和结构化日志）

        Args:
            feed_url: RSS URL
            max_retries: 最大重试次数

        Returns:
            文章列表
        """
        # Docker 环境 URL 转换：将 localhost 地址转换为 Docker 服务名
        feed_url = self._normalize_docker_url(feed_url)

        # Week 4.5: 开始抓取日志
        feed_id = self.generate_feed_id(feed_url)
        self.fetch_logger.start_fetch(feed_url, feed_id=feed_id)

        is_official_rsshub = feed_url.startswith("https://rsshub.app/")
        if is_official_rsshub:
            max_retries = 5

        for attempt in range(max_retries):
            try:
                # Week 4.5: 获取速率限制许可
                await self.rate_limiter.acquire(feed_url)

                try:
                    # Week 4.5: 使用配置化的超时
                    timeout = self.timeout_config.to_aiohttp_timeout()

                    # Week 5 Cleanup (2025-11-20): Cookie injection removed - handled by RSSHub-CookieCloud
                    async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                        async with session.get(feed_url) as response:
                            if response.status == 200:
                                content = await response.text()
                                feed = feedparser.parse(content)
                                articles = []

                                for entry in feed.entries:
                                    published = self.parse_date(entry.get('published', ''))
                                    # 生成唯一的guid
                                    link = entry.get('link', '')
                                    title = entry.get('title', '')
                                    if link:
                                        hash_obj = hashlib.md5(link.encode())
                                    else:
                                        hash_obj = hashlib.md5(title.encode())

                                    # 将MD5转换为UUID格式
                                    hex_str = hash_obj.hexdigest()
                                    guid = f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"

                                    # 处理content字段
                                    content = ''
                                    if entry.get('content'):
                                        if isinstance(entry['content'], list) and entry['content']:
                                            content = entry['content'][0].get('value', '')
                                        else:
                                            content = str(entry['content'])

                                    # 如果没有content，使用summary
                                    if not content:
                                        content = entry.get('summary', '')

                                    article = {
                                        'guid': guid,
                                        'feed_id': feed_id,
                                        'title': title,
                                        'url': link,  # 统一使用'url'字段
                                        'link': link,  # 保留向后兼容
                                        'published_at': published,  # 使用数据库表的字段名
                                        'published': published,  # 保留向后兼容
                                        'summary': entry.get('summary', ''),
                                        'content': content,
                                        'author': entry.get('author', ''),
                                        'source': feed_url
                                    }
                                    articles.append(article)

                                # 限制每个 feed 返回的文章数量，避免异常 RSS 返回大量历史文章
                                max_articles = self.settings.max_articles_per_feed
                                if len(articles) > max_articles:
                                    # 按发布时间排序（最新的在前），取前 max_articles 篇
                                    articles.sort(
                                        key=lambda x: x.get('published_at') or datetime.min,
                                        reverse=True
                                    )
                                    articles = articles[:max_articles]
                                    self.logger.warning(
                                        f"Feed {feed_url} 返回文章过多，已截断至 {max_articles} 篇"
                                    )

                                # Week 4.5: 报告成功
                                await self.rate_limiter.report_success(feed_url)

                                # Week 4.5: 记录成功日志
                                self.fetch_logger.end_fetch(
                                    success=True,
                                    article_count=len(articles),
                                    status_code=200
                                )

                                return articles

                            else:
                                self.logger.warning(f"HTTP {response.status} for {feed_url}, attempt {attempt + 1}")

                                # Week 5 Cleanup (2025-11-20): Cookie error handling removed
                                # Week 4.5: 报告错误并获取退避时间
                                error_type = 'rate_limit' if response.status == 429 else 'server_error'
                                backoff_time = await self.rate_limiter.report_error(
                                    feed_url,
                                    status_code=response.status,
                                    error_type=error_type
                                )

                                if attempt < max_retries - 1:
                                    self.logger.info(f"等待 {backoff_time:.1f}s 后重试...")
                                    await asyncio.sleep(backoff_time)
                                else:
                                    # 最后一次重试失败
                                    self.fetch_logger.end_fetch(
                                        success=False,
                                        error_msg=f"HTTP {response.status}",
                                        status_code=response.status
                                    )

                finally:
                    # Week 4.5: 释放速率限制许可
                    self.rate_limiter.release(feed_url)

            except asyncio.TimeoutError:
                self.logger.warning(f"Attempt {attempt + 1} timeout for {feed_url}")

                # Week 4.5: 报告超时错误
                backoff_time = await self.rate_limiter.report_error(
                    feed_url,
                    error_type='timeout'
                )

                if attempt < max_retries - 1:
                    self.logger.info(f"超时后等待 {backoff_time:.1f}s 重试...")
                    await asyncio.sleep(backoff_time)
                else:
                    self.fetch_logger.end_fetch(
                        success=False,
                        error_msg="Timeout"
                    )

            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for {feed_url}: {str(e)}")

                # Week 4.5: 报告通用错误
                backoff_time = await self.rate_limiter.report_error(
                    feed_url,
                    error_type='exception'
                )

                if attempt < max_retries - 1:
                    self.logger.info(f"异常后等待 {backoff_time:.1f}s 重试...")
                    await asyncio.sleep(backoff_time)
                else:
                    self.fetch_logger.end_fetch(
                        success=False,
                        error_msg=str(e)
                    )

        self.logger.error(f"All attempts failed for {feed_url}")
        return []
        
    async def fetch_feed(self, feed_url: str) -> List[Dict[str, Any]]:
        """获取RSS源内容（带内存缓存，避免短时间重复抓取）"""
        now = time.time()
        cached = self._cache.get(feed_url)
        if cached and (now - cached.get('ts', 0) <= self._cache_ttl):
            return cached.get('articles', [])

        # 获取/创建对应URL的锁
        lock = self._locks.setdefault(feed_url, asyncio.Lock())
        async with lock:
            # 双重检查，避免锁等待期间重复抓取
            cached2 = self._cache.get(feed_url)
            if cached2 and (time.time() - cached2.get('ts', 0) <= self._cache_ttl):
                return cached2.get('articles', [])

            articles = await self.fetch_feed_with_retry(feed_url)
            self._cache[feed_url] = {
                'ts': time.time(),
                'articles': articles
            }
            return articles
            
    async def fetch_multiple_feeds(self, feed_urls: List[str]) -> List[Dict[str, Any]]:
        """批量获取多个RSS源（对URL去重，并发抓取+缓存复用）"""
        unique_urls = list(dict.fromkeys(feed_urls))
        # 并发抓取
        tasks = [self.fetch_feed(url) for url in unique_urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        all_articles = []
        for articles in results:
            all_articles.extend(articles)
        return all_articles
