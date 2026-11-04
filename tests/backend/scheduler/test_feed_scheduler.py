"""
FeedScheduler 单元测试
覆盖超时处理、资源释放等关键行为
"""
import asyncio
import pytest
from unittest.mock import MagicMock

from backend.scheduler.feed_scheduler import FeedScheduler


class TestFeedSchedulerTimeout:
    """测试 FeedScheduler 超时与资源释放行为"""

    @pytest.fixture
    def scheduler(self):
        """创建带有 mock 依赖的 FeedScheduler"""
        mock_db = MagicMock()
        mock_db.connection_scope.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_db.connection_scope.return_value.__exit__ = MagicMock(return_value=False)

        return FeedScheduler(
            rss_fetcher=MagicMock(),
            feed_url_manager=MagicMock(),
            nlp_processor=MagicMock(),
            db_manager=mock_db,
            subscription_service=MagicMock()
        )

    def test_run_async_task_timeout_does_not_crash(self, scheduler, monkeypatch):
        """
        测试：异步任务超时后，方法正常返回且不抛未处理异常。
        这是生产故障的回归保护：旧代码会无限挂起，新代码应超时后安全退出。
        """
        async def never_complete():
            await asyncio.sleep(1000)

        scheduler.fetch_all_active_feeds = never_complete

        # 将超时时间临时改为 0.01 秒以便测试
        original_wait_for = asyncio.wait_for
        async def fast_timeout(coro, timeout):
            return await original_wait_for(coro, timeout=0.01)
        monkeypatch.setattr(asyncio, "wait_for", fast_timeout)

        # 不应抛异常（TimeoutError 被内部捕获）
        scheduler._run_async_task()

    def test_run_async_task_subsequent_call_after_timeout(self, scheduler, monkeypatch):
        """
        测试：一次超时后，下一次调用仍能正常执行。
        验证事件循环资源被彻底释放，不会干扰后续调度。
        """
        call_count = 0

        async def slow_then_fast():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(1000)  # 第一次卡死
            # 第二次快速完成

        scheduler.fetch_all_active_feeds = slow_then_fast

        original_wait_for = asyncio.wait_for
        async def fast_timeout(coro, timeout):
            return await original_wait_for(coro, timeout=0.01)
        monkeypatch.setattr(asyncio, "wait_for", fast_timeout)

        # 第一次调用：超时
        scheduler._run_async_task()
        assert call_count == 1

        # 第二次调用：仍然能执行（不因为残留循环而崩溃）
        scheduler._run_async_task()
        assert call_count == 2

