"""
定时任务调度器
用于定期抓取RSS订阅源
Week 5 Phase 2: 使用统一的 FeedRefresher
Week 5 Phase 3: 使用结构化日志 + 支持多用户抓取
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio
from backend.utils.feed_refresher import FeedRefresher
from backend.services.cache_cleaner import run_cache_cleanup
from backend.services.feed_validation import validate_candidate_feeds
from core.config.settings import settings
import logging

# Week 5 Phase 3: 使用统一的日志（不单独创建，使用 root logger）
logger = logging.getLogger(__name__)


class FeedScheduler:
    """RSS订阅源定时抓取调度器"""

    def __init__(self, rss_fetcher, feed_url_manager, nlp_processor, db_manager, subscription_service=None):
        """
        初始化调度器

        Args:
            rss_fetcher: RSS抓取器实例
            feed_url_manager: Feed URL管理器实例
            nlp_processor: NLP处理器实例
            db_manager: 数据库管理器实例
            subscription_service: 订阅服务实例（可选）
        """
        self.rss_fetcher = rss_fetcher
        self.feed_url_manager = feed_url_manager
        self.nlp_processor = nlp_processor
        self.db_manager = db_manager
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.subscription_service = subscription_service

        # Week 5 Phase 2: 初始化统一的刷新器
        self.feed_refresher = FeedRefresher(
            rss_fetcher=rss_fetcher,
            feed_url_manager=feed_url_manager,
            nlp_processor=nlp_processor,
            db_manager=db_manager,
            subscription_service=subscription_service
        )

    async def fetch_all_active_feeds(self):
        """
        抓取所有活跃的订阅源
        Week 5 Phase 2: 使用统一的 FeedRefresher
        Week 5 Phase 3: 使用结构化日志 + 支持多用户抓取
        Week 5 Phase 4: 使用 connection_scope 确保连接正确释放
        """
        # 使用 connection_scope 确保后台任务正确释放数据库连接
        with self.db_manager.connection_scope():
            await self._fetch_all_active_feeds_impl()

    async def _fetch_all_active_feeds_impl(self):
        """实际的抓取实现（在 connection_scope 内执行）"""
        try:
            logger.info("定时抓取任务开始", extra={"task_type": "scheduled_fetch"})

            # Week 5 Phase 3: 从数据库获取所有有订阅源的用户
            users = self.db_manager.get_active_user_ids()

            if not users:
                logger.warning("没有找到活跃用户，跳过本次抓取")
                return

            total_feeds = 0
            total_articles = 0
            failed_feeds = 0

            for user_id in users:
                try:
                    # 获取用户订阅源
                    feeds = self.db_manager.get_user_feeds(user_id)
                    total_feeds += len(feeds)

                    logger.info(
                        "获取用户订阅源",
                        extra={
                            "user_id": user_id,
                            "feed_count": len(feeds)
                        }
                    )

                    if not feeds:
                        continue

                    # Week 5 Phase 2: 使用统一的刷新函数
                    results = await self.feed_refresher.refresh_feeds(
                        feeds=feeds,
                        enable_logging=False,  # 调度器不需要额外的更新日志
                        check_existence=True   # 启用去重优化
                    )

                    # 统计结果
                    for result in results:
                        if result['status'] == 'success':
                            total_articles += result['stored_count']
                            logger.info(
                                "订阅源刷新成功",
                                extra={
                                    "feed_id": result['feed_id'],
                                    "feed_name": result['feed_name'],
                                    "articles_fetched": result['articles_count'],
                                    "articles_stored": result['stored_count'],
                                    "articles_skipped": result['skipped_count'],
                                    "articles_failed": result['failed_count']
                                }
                            )
                        else:
                            failed_feeds += 1
                            logger.error(
                                "订阅源刷新失败",
                                extra={
                                    "feed_id": result['feed_id'],
                                    "feed_name": result['feed_name'],
                                    "error": result.get('error', 'Unknown')
                                }
                            )

                except Exception as e:
                    logger.error(
                        "处理用户订阅源失败",
                        extra={
                            "user_id": user_id,
                            "error": str(e)
                        }
                    )
                    continue

            logger.info(
                "定时抓取任务完成",
                extra={
                    "task_type": "scheduled_fetch",
                    "total_users": len(users),
                    "total_feeds": total_feeds,
                    "successful_feeds": total_feeds - failed_feeds,
                    "failed_feeds": failed_feeds,
                    "new_articles": total_articles
                }
            )

        except Exception as e:
            logger.error("定时抓取任务执行失败", extra={"error": str(e)})

    async def generate_daily_podcasts(self):
        """
        为所有活跃用户生成每日播客
        Week 5 Phase 4: 使用 connection_scope 确保连接正确释放
        """
        with self.db_manager.connection_scope():
            await self._generate_daily_podcasts_impl()

    async def _generate_daily_podcasts_impl(self):
        """实际的播客生成实现（在 connection_scope 内执行）"""
        try:
            logger.info("开始生成每日播客", extra={"task_type": "podcast_generation"})

            # 检查是否启用播客功能
            if not settings.podcast_enabled:
                logger.info("播客功能未启用，跳过生成")
                return

            # 导入播客生成器
            from backend.services.podcast_generator import PodcastGenerator
            podcast_generator = PodcastGenerator()

            # 获取所有启用自动播客的活跃用户（含语言偏好）
            users = self.db_manager.get_podcast_enabled_users()

            if not users:
                logger.warning("没有找到启用自动播客的活跃用户，跳过播客生成")
                return

            # Auto-generation is open to all users with auto_podcast_enabled=True
            # (manual generation via API is already unrestricted)

            total_generated = 0
            total_failed = 0

            for user_id, preferred_language in users:
                try:
                    # 自托管版配额检查始终允许；保留统一调用协议
                    if self.subscription_service:
                        quota = self.subscription_service.check_podcast_quota(user_id)
                        if not quota['allowed']:
                            logger.info(
                                "用户播客配额不足，跳过自动生成",
                                extra={"user_id": user_id, "limit": quota['limit'], "used": quota['used']}
                            )
                            continue
                    else:
                        logger.warning(
                            "未配置 subscription_service，跳过配额检查",
                            extra={"user_id": user_id}
                        )

                    # 语言归一化：仅当 preferred_language == 'en' 时使用英文，其他都回落到中文
                    language = 'en' if (preferred_language or '').lower() == 'en' else 'zh'
                    logger.info(
                        f"为用户 {user_id} 生成播客",
                        extra={"user_id": user_id, "language": language}
                    )

                    # 生成播客
                    podcast_id = await podcast_generator.generate_daily_podcast(
                        user_id=user_id,
                        style=settings.podcast_style_default,
                        time_range_hours=24,
                        max_articles=settings.podcast_max_articles,
                        language=language
                    )

                    # 自托管版配额始终为无限；保留统计用于观测用量
                    if self.subscription_service:
                        self.subscription_service.record_podcast_usage(user_id)

                    total_generated += 1
                    logger.info(
                        "播客生成成功",
                        extra={
                            "user_id": user_id,
                            "podcast_id": podcast_id
                        }
                    )

                except Exception as e:
                    total_failed += 1
                    logger.error(
                        "播客生成失败",
                        extra={
                            "user_id": user_id,
                            "error": str(e)
                        }
                    )

            logger.info(
                "每日播客生成完成",
                extra={
                    "task_type": "podcast_generation",
                    "total_generated": total_generated,
                    "total_failed": total_failed
                }
            )

        except Exception as e:
            logger.error("每日播客生成任务失败", extra={"error": str(e)})

    def _run_async_task(self):
        """在同步上下文中运行异步任务（带45分钟超时保护）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 45分钟超时：确保在下一个小时调度前完成
            loop.run_until_complete(
                asyncio.wait_for(self.fetch_all_active_feeds(), timeout=2700)
            )
        except asyncio.TimeoutError:
            logger.error("定时抓取任务超时（45分钟），强制取消", extra={"task_type": "scheduled_fetch"})
        except Exception as e:
            logger.error("运行异步任务失败", extra={"error": str(e)})
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    def _run_feed_validation(self):
        """运行候选 feed 验证任务"""
        try:
            logger.info("开始执行候选 feed 验证任务", extra={"task_type": "feed_validation"})
            with self.db_manager.connection_scope():
                validate_candidate_feeds(self.db_manager)
            logger.info("候选 feed 验证任务完成", extra={"task_type": "feed_validation"})
        except Exception as e:
            logger.error("候选 feed 验证任务失败", extra={"task_type": "feed_validation", "error": str(e)})

    def _run_cache_cleanup(self):
        """运行缓存清理任务"""
        try:
            logger.info("开始执行音频缓存清理任务", extra={"task_type": "cache_cleanup"})
            result = run_cache_cleanup(dry_run=False)

            if "error" in result:
                logger.error(
                    "缓存清理任务失败",
                    extra={
                        "task_type": "cache_cleanup",
                        "error": result["error"]
                    }
                )
            else:
                logger.info(
                    "缓存清理任务完成",
                    extra={
                        "task_type": "cache_cleanup",
                        "total_files_deleted": result.get("total_files_deleted", 0),
                        "total_space_freed_mb": result.get("total_space_freed_mb", 0),
                        "expired_files_deleted": result.get("expired_files_deleted", 0),
                        "size_files_deleted": result.get("size_files_deleted", 0)
                    }
                )
        except Exception as e:
            logger.error("缓存清理任务执行失败", extra={"error": str(e)})

    def _run_podcast_generation(self):
        """运行播客生成任务（同步包装，带30分钟超时保护）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                asyncio.wait_for(self.generate_daily_podcasts(), timeout=1800)
            )
        except asyncio.TimeoutError:
            logger.error("播客生成任务超时（30分钟），强制取消", extra={"task_type": "podcast_generation"})
        except Exception as e:
            logger.error("运行播客生成任务失败", extra={"error": str(e)})
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            asyncio.set_event_loop(None)
            loop.close()

    def start(self):
        """启动定时任务调度器"""
        if self.is_running:
            logger.warning("调度器已在运行中")
            return

        try:
            # 添加定时任务
            # 每小时执行一次RSS抓取
            self.scheduler.add_job(
                self._run_async_task,
                trigger=CronTrigger(minute=0),  # 每小时的0分执行
                id='fetch_all_feeds_hourly',
                name='每小时抓取所有订阅源',
                replace_existing=True,
                coalesce=True  # 如果多个执行被跳过，只执行一次catch-up
            )

            # 添加候选 feed 验证任务：每 4 小时运行一次
            self.scheduler.add_job(
                self._run_feed_validation,
                trigger=CronTrigger(hour='*/4'),  # 每 4 小时执行
                id='feed_validation_periodic',
                name='候选 Feed 质量验证',
                replace_existing=True
            )

            # 添加缓存清理任务：每天凌晨3点执行
            self.scheduler.add_job(
                self._run_cache_cleanup,
                trigger=CronTrigger(hour=3, minute=0),  # 每天凌晨3点执行
                id='cache_cleanup_daily',
                name='每日音频缓存清理',
                replace_existing=True
            )

            # 添加播客生成任务：每天凌晨2点执行
            if settings.podcast_enabled:
                self.scheduler.add_job(
                    self._run_podcast_generation,
                    trigger=CronTrigger(
                        hour=settings.podcast_generation_hour,
                        minute=settings.podcast_generation_minute,
                    ),
                    id='podcast_generation_daily',
                    name='每日 AI 播客生成',
                    replace_existing=True,
                    coalesce=True
                )

            # 也可以添加更频繁的任务，比如每30分钟
            # self.scheduler.add_job(
            #     self._run_async_task,
            #     trigger=CronTrigger(minute='*/30'),
            #     id='fetch_all_feeds_30min',
            #     name='每30分钟抓取所有订阅源',
            #     replace_existing=True
            # )

            # 启动调度器
            self.scheduler.start()
            self.is_running = True

            logger.info("定时任务调度器已启动", extra={"scheduler_status": "started"})
            logger.info("调度任务列表", extra={"job_count": len(self.scheduler.get_jobs())})
            for job in self.scheduler.get_jobs():
                logger.info(
                    "调度任务详情",
                    extra={
                        "job_id": job.id,
                        "job_name": job.name,
                        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
                    }
                )

        except Exception as e:
            logger.error("启动调度器失败", extra={"error": str(e)})
            raise

    def stop(self):
        """停止定时任务调度器"""
        if not self.is_running:
            logger.warning("调度器未在运行")
            return

        try:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("定时任务调度器已停止", extra={"scheduler_status": "stopped"})
        except Exception as e:
            logger.error("停止调度器失败", extra={"error": str(e)})

    def get_status(self):
        """获取调度器状态"""
        if not self.is_running:
            return {
                "running": False,
                "jobs": []
            }

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

        return {
            "running": True,
            "jobs": jobs
        }

    def trigger_now(self):
        """立即触发一次抓取任务"""
        logger.info("手动触发抓取任务", extra={"trigger_type": "manual"})
        self._run_async_task()
