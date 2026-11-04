"""
RSS 抓取速率限制器

功能：
1. 按 host 限流（每个域名独立的并发数和请求间隔）
2. 指数退避重试（429/5xx 错误）
3. 超时分离配置（连接超时、读取超时、总超时）
"""
import asyncio
import time
import logging
from typing import Dict, Optional
from urllib.parse import urlparse
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class PerHostRateLimiter:
    """按 host 的速率限制器"""

    def __init__(
        self,
        max_concurrent_per_host: int = 3,
        request_interval: float = 0.5,
        enable_adaptive: bool = True
    ):
        """
        初始化速率限制器

        Args:
            max_concurrent_per_host: 每个 host 的最大并发数
            request_interval: 同一 host 的请求间隔（秒）
            enable_adaptive: 是否启用自适应速率调整
        """
        self.max_concurrent_per_host = max_concurrent_per_host
        self.request_interval = request_interval
        self.enable_adaptive = enable_adaptive

        # 每个 host 的信号量（限制并发）
        self._semaphores: Dict[str, asyncio.Semaphore] = {}

        # 每个 host 的最后请求时间
        self._last_request_time: Dict[str, float] = {}

        # 每个 host 的动态速率配置（自适应）
        self._host_configs: Dict[str, Dict] = defaultdict(lambda: {
            'interval': self.request_interval,
            'error_count': 0,
            'last_error_time': 0,
            'backoff_until': 0  # 退避截止时间
        })

        # 全局锁（用于安全更新内部状态）
        self._lock = asyncio.Lock()

    def _extract_host(self, url: str) -> str:
        """提取 URL 的 host"""
        try:
            parsed = urlparse(url)
            return parsed.netloc or 'unknown'
        except Exception:
            return 'unknown'

    async def acquire(self, url: str) -> None:
        """
        获取访问许可（阻塞直到允许访问）

        Args:
            url: 目标 URL
        """
        host = self._extract_host(url)

        # 1. 获取/创建 host 的信号量
        async with self._lock:
            if host not in self._semaphores:
                self._semaphores[host] = asyncio.Semaphore(self.max_concurrent_per_host)

        semaphore = self._semaphores[host]

        # 2. 等待信号量（限制并发）
        await semaphore.acquire()

        # 3. 检查是否需要退避等待
        config = self._host_configs[host]
        now = time.time()

        if config['backoff_until'] > now:
            wait_time = config['backoff_until'] - now
            logger.info(f"Host {host} 处于退避期，等待 {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        # 4. 等待请求间隔
        last_time = self._last_request_time.get(host, 0)
        interval = config['interval']
        elapsed = now - last_time

        if elapsed < interval:
            wait_time = interval - elapsed
            await asyncio.sleep(wait_time)

        # 5. 更新最后请求时间
        self._last_request_time[host] = time.time()

    def release(self, url: str) -> None:
        """
        释放访问许可

        Args:
            url: 目标 URL
        """
        host = self._extract_host(url)
        if host in self._semaphores:
            self._semaphores[host].release()

    async def report_success(self, url: str) -> None:
        """
        报告请求成功（自适应速率调整）

        Args:
            url: 目标 URL
        """
        if not self.enable_adaptive:
            return

        host = self._extract_host(url)
        config = self._host_configs[host]

        # 成功后逐渐降低请求间隔（加速）
        if config['error_count'] > 0:
            config['error_count'] = max(0, config['error_count'] - 1)

        if config['interval'] > self.request_interval:
            config['interval'] = max(
                self.request_interval,
                config['interval'] * 0.9  # 每次成功减少 10%
            )

    async def report_error(
        self,
        url: str,
        status_code: Optional[int] = None,
        error_type: str = 'unknown'
    ) -> float:
        """
        报告请求错误（自适应速率调整 + 指数退避）

        Args:
            url: 目标 URL
            status_code: HTTP 状态码（如果有）
            error_type: 错误类型（'rate_limit', 'server_error', 'timeout', etc.）

        Returns:
            建议的退避等待时间（秒）
        """
        host = self._extract_host(url)
        config = self._host_configs[host]
        now = time.time()

        config['error_count'] += 1
        config['last_error_time'] = now

        # 根据错误类型计算退避时间
        if status_code == 429 or error_type == 'rate_limit':
            # 速率限制：指数退避（1s, 2s, 4s, 8s, 16s, ...）
            backoff_time = min(2 ** config['error_count'], 60)  # 最多 60s
            logger.warning(f"Host {host} 遇到速率限制（429），退避 {backoff_time}s")

        elif status_code and 500 <= status_code < 600:
            # 服务器错误：较短退避
            backoff_time = min(config['error_count'] * 3, 30)  # 最多 30s
            logger.warning(f"Host {host} 服务器错误（{status_code}），退避 {backoff_time}s")

        elif error_type == 'timeout':
            # 超时：中等退避
            backoff_time = min(config['error_count'] * 2, 20)  # 最多 20s
            logger.warning(f"Host {host} 请求超时，退避 {backoff_time}s")

        else:
            # 其他错误：较短退避
            backoff_time = min(config['error_count'], 10)  # 最多 10s
            logger.warning(f"Host {host} 请求失败（{error_type}），退避 {backoff_time}s")

        # 设置退避截止时间
        config['backoff_until'] = now + backoff_time

        # 自适应：增加请求间隔（减速）
        if self.enable_adaptive:
            config['interval'] = min(
                config['interval'] * 1.5,  # 每次失败增加 50%
                5.0  # 最多 5s 间隔
            )

        return backoff_time

    def get_host_stats(self, url: str) -> Dict:
        """
        获取 host 的统计信息

        Args:
            url: 目标 URL

        Returns:
            统计信息字典
        """
        host = self._extract_host(url)
        config = self._host_configs[host]
        semaphore = self._semaphores.get(host)

        return {
            'host': host,
            'interval': config['interval'],
            'error_count': config['error_count'],
            'last_error_time': config['last_error_time'],
            'backoff_until': config['backoff_until'],
            'is_backing_off': config['backoff_until'] > time.time(),
            'available_slots': semaphore._value if semaphore else self.max_concurrent_per_host,
            'max_concurrent': self.max_concurrent_per_host
        }

    async def reset_host(self, url: str) -> None:
        """
        重置 host 的限流状态

        Args:
            url: 目标 URL
        """
        host = self._extract_host(url)

        async with self._lock:
            # 重置配置
            self._host_configs[host] = {
                'interval': self.request_interval,
                'error_count': 0,
                'last_error_time': 0,
                'backoff_until': 0
            }

            # 清除最后请求时间
            if host in self._last_request_time:
                del self._last_request_time[host]

        logger.info(f"已重置 host {host} 的限流状态")


class TimeoutConfig:
    """超时配置（分离连接、读取、总超时）"""

    def __init__(
        self,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        total_timeout: float = 30.0
    ):
        """
        初始化超时配置

        Args:
            connect_timeout: 连接超时（秒）
            read_timeout: 读取超时（秒）
            total_timeout: 总超时（秒）
        """
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.total_timeout = total_timeout

    def to_aiohttp_timeout(self):
        """转换为 aiohttp.ClientTimeout"""
        import aiohttp
        return aiohttp.ClientTimeout(
            sock_connect=self.connect_timeout,
            sock_read=self.read_timeout,
            total=self.total_timeout
        )

    def __repr__(self):
        return (
            f"TimeoutConfig(connect={self.connect_timeout}s, "
            f"read={self.read_timeout}s, total={self.total_timeout}s)"
        )


# 使用示例
if __name__ == '__main__':
    import asyncio

    async def test_rate_limiter():
        """测试速率限制器"""
        limiter = PerHostRateLimiter(
            max_concurrent_per_host=2,
            request_interval=1.0,
            enable_adaptive=True
        )

        async def fetch_with_limiter(url: str, fail: bool = False):
            """模拟带限流的请求"""
            try:
                await limiter.acquire(url)
                print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] 开始请求: {url}")

                # 模拟请求
                await asyncio.sleep(0.5)

                if fail:
                    # 模拟错误
                    backoff = await limiter.report_error(url, status_code=429)
                    print(f"  ❌ 请求失败，建议退避 {backoff}s")
                else:
                    # 模拟成功
                    await limiter.report_success(url)
                    print(f"  ✅ 请求成功")

            finally:
                limiter.release(url)

        # 测试1: 同一 host 的并发限制
        print("=== 测试1: 并发限制（max=2）===")
        urls = [
            "https://example.com/feed1",
            "https://example.com/feed2",
            "https://example.com/feed3",
            "https://example.com/feed4"
        ]
        await asyncio.gather(*[fetch_with_limiter(url) for url in urls])

        # 测试2: 错误重试和退避
        print("\n=== 测试2: 错误重试和指数退避 ===")
        await fetch_with_limiter("https://example.com/fail1", fail=True)
        await fetch_with_limiter("https://example.com/fail2", fail=True)

        # 查看 host 统计
        print("\n=== Host 统计 ===")
        stats = limiter.get_host_stats("https://example.com/")
        print(f"Host: {stats['host']}")
        print(f"请求间隔: {stats['interval']:.2f}s")
        print(f"错误计数: {stats['error_count']}")
        print(f"是否退避中: {stats['is_backing_off']}")
        print(f"可用槽位: {stats['available_slots']}/{stats['max_concurrent']}")

    asyncio.run(test_rate_limiter())
