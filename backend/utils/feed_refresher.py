"""
统一的订阅源刷新工具模块
Week 5 Phase 2: 提取统一的 refresh_feeds() 函数
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.utils.whitelist import is_feature_whitelist_user
from backend.utils.url import normalize_url
from core.config.settings import settings

logger = logging.getLogger(__name__)


class FeedRefresher:
    """统一的订阅源刷新器"""

    def __init__(self, rss_fetcher, feed_url_manager, nlp_processor, db_manager, subscription_service=None):
        """
        初始化刷新器

        Args:
            rss_fetcher: RSS 抓取器实例
            feed_url_manager: Feed URL 管理器实例
            nlp_processor: NLP 处理器实例
            db_manager: 数据库管理器实例
            subscription_service: 订阅服务实例（可选）
        """
        self.rss_fetcher = rss_fetcher
        self.feed_url_manager = feed_url_manager
        self.nlp_processor = nlp_processor
        self.db_manager = db_manager
        self.subscription_service = subscription_service

    async def refresh_feeds(
        self,
        feeds: List[Dict[str, Any]],
        enable_logging: bool = True,
        check_existence: bool = True
    ) -> List[Dict[str, Any]]:
        """
        统一的订阅源刷新函数

        Args:
            feeds: 订阅源列表,每个元素包含 id, feed_name, feed_url
            enable_logging: 是否启用更新日志记录
            check_existence: 是否检查文章存在性(去重优化)

        Returns:
            刷新结果列表,每个元素包含:
            - feed_id: 订阅源ID
            - feed_name: 订阅源名称
            - status: 状态 (success/error)
            - articles_count: 抓取的文章数
            - stored_count: 成功存储的文章数
            - failed_count: 存储失败的文章数
            - skipped_count: 跳过的文章数(已存在)
            - optimal_url: 优化后的URL
            - error: 错误信息(如有)
        """
        results = []

        for feed in feeds:
            feed_id = feed['id']
            feed_name = feed['feed_name']
            feed_url = feed['feed_url']

            try:
                # 1. 开始更新日志
                log_id = None
                if enable_logging:
                    log_id = self.db_manager.start_feed_update_log(feed_id)

                # 查询该 feed 所属用户，用于功能白名单判断
                # 使用 feed_id 获取用户，避免共享 feed_url 时返回错误的用户
                feed_user_id = self.db_manager._get_user_id_by_feed_id(feed_id)
                is_whitelist_user = is_feature_whitelist_user(feed_user_id)

                # 2. 获取优化后的URL
                optimal_url = self.feed_url_manager.get_optimal_url(feed_url)

                # 3. 抓取文章
                articles = await self.rss_fetcher.fetch_multiple_feeds([optimal_url])

                if not articles:
                    logger.warning(f"订阅源 {feed_name} 未抓取到文章")

                    # 记录为成功但无新文章
                    result = {
                        "feed_id": feed_id,
                        "feed_name": feed_name,
                        "status": "success",
                        "articles_count": 0,
                        "stored_count": 0,
                        "failed_count": 0,
                        "skipped_count": 0,
                        "optimal_url": optimal_url
                    }
                    results.append(result)

                    if enable_logging and log_id:
                        self.db_manager.complete_feed_update_log(
                            log_id, 'success', 0, 0, 0, None
                        )

                    # 更新 last_fetched_at
                    self._update_last_fetched(feed_id)

                    continue

                # 4. 处理和存储文章
                stored_count = 0
                failed_count = 0
                skipped_count = 0

                for article in articles:
                    # 限制每个 feed 每次抓取最多处理的文章数
                    if stored_count >= settings.max_articles_per_feed:
                        logger.info(
                            f"订阅源 {feed_name}: 已达到单次最大处理上限 "
                            f"{settings.max_articles_per_feed} 篇，跳过剩余文章"
                        )
                        break

                    try:
                        # 添加 feed_id
                        article['feed_id'] = feed_id

                        # 修复：使用原始 feed_url（用于 TTS 预生成白名单匹配）
                        article['source'] = feed_url

                        # Week 5 Phase 2: 文章存在性检查(去重优化)
                        if check_existence:
                            article_url = article.get('url') or article.get('link')
                            if article_url and self._article_exists(article_url, feed_id):
                                logger.debug(f"文章已存在,跳过: {article.get('title', 'Unknown')}")
                                skipped_count += 1
                                continue

                        # 1. 先存储文章（获取 global_article_id 用于摘要缓存）
                        global_article_id, legacy_article_id, is_new = self.db_manager.store_article(article)

                        # 2. 获取用户语言偏好
                        user_language = self.db_manager.get_user_language(feed_user_id)

                        # 3. 检查语言特定摘要缓存
                        cached_summary = self.db_manager.get_article_summary(global_article_id, user_language)

                        if cached_summary:
                            article['summary'] = cached_summary
                            article['entities'] = article.get('entities', [])
                        else:
                            # 4. AI 摘要：自托管版无限额度；保留用量统计
                            use_ai_summary = False
                            if self.subscription_service:
                                plan = self.subscription_service.get_effective_plan(feed_user_id)
                                ai_limit = plan.get('ai_summary_daily_limit', 20)
                                if ai_limit == -1:
                                    use_ai_summary = True
                                else:
                                    usage = self.subscription_service.get_usage_today(feed_user_id)
                                    use_ai_summary = usage['ai_summary_count'] < ai_limit

                            if use_ai_summary:
                                content = article.get('content', '')
                                summary = self.nlp_processor.generate_summary(content, language=user_language)
                                article['summary'] = summary
                                article['entities'] = self.nlp_processor.extract_entities(content)
                                self.subscription_service.record_ai_summary_usage(feed_user_id)
                            else:
                                content = article.get('content', '')
                                article['summary'] = self.nlp_processor._fallback_summary(content, 150)
                                article['entities'] = []

                            # 5. 缓存摘要并更新文章表
                            self.db_manager.upsert_article_summary(global_article_id, user_language, article['summary'])
                            self.db_manager.update_article_summary(global_article_id, legacy_article_id, article['summary'])

                        stored_count += 1

                    except Exception as e:
                        failed_count += 1
                        logger.error(f"处理文章失败: {article.get('title', 'Unknown')} - {str(e)}")
                        continue

                # 5. 记录结果
                result = {
                    "feed_id": feed_id,
                    "feed_name": feed_name,
                    "status": "success",
                    "articles_count": len(articles),
                    "stored_count": stored_count,
                    "failed_count": failed_count,
                    "skipped_count": skipped_count,
                    "optimal_url": optimal_url
                }
                results.append(result)

                logger.info(
                    f"订阅源 {feed_name}: 抓取 {len(articles)} 篇, "
                    f"存储 {stored_count} 篇, 跳过 {skipped_count} 篇, 失败 {failed_count} 篇"
                )

                # 6. 完成更新日志
                if enable_logging and log_id:
                    self.db_manager.complete_feed_update_log(
                        log_id, 'success', len(articles), stored_count, failed_count, None
                    )

                # 7. 更新 last_fetched_at
                self._update_last_fetched(feed_id)

            except Exception as e:
                # 错误处理
                error_msg = str(e)
                logger.error(f"刷新订阅源 {feed_name} 失败: {error_msg}")

                result = {
                    "feed_id": feed_id,
                    "feed_name": feed_name,
                    "status": "error",
                    "articles_count": 0,
                    "stored_count": 0,
                    "failed_count": 0,
                    "skipped_count": 0,
                    "error": error_msg
                }
                results.append(result)

                # 记录失败日志
                if enable_logging and log_id:
                    try:
                        self.db_manager.complete_feed_update_log(
                            log_id, 'error', 0, 0, 0, error_msg
                        )
                    except Exception:
                        pass

        return results

    def _article_exists(self, url: str, feed_id: int = None) -> bool:
        """
        检查文章是否已存在（按 feed_id + url 去重）

        Args:
            url: 文章URL（原始格式，内部会归一化后比对）
            feed_id: 订阅源ID（指定时按 feed 级别去重）

        Returns:
            是否存在
        """
        try:
            norm_url = normalize_url(url)
            if feed_id is not None:
                return self.db_manager.article_exists(feed_id, norm_url)
            article_id = self.db_manager.get_article_id_by_url(norm_url)
            return article_id is not None
        except Exception as e:
            logger.warning(f"检查文章存在性失败: {url} - {str(e)}")
            return False

    async def refresh_single_feed(self, user_id: str, feed_id: int, feed_url: str, feed_name: str = None) -> Dict[str, Any]:
        """
        为单个 feed 执行一次 RSS 抓取（onboarding / 手动添加场景用）

        Args:
            user_id: 用户ID
            feed_id: 订阅源ID
            feed_url: 订阅源URL
            feed_name: 订阅源名称（可选）

        Returns:
            刷新结果字典
        """
        feed = {
            'id': feed_id,
            'feed_name': feed_name or feed_url,
            'feed_url': feed_url
        }
        results = await self.refresh_feeds([feed], enable_logging=True, check_existence=True)
        return results[0] if results else {
            'feed_id': feed_id,
            'feed_name': feed_name or feed_url,
            'status': 'error',
            'articles_count': 0,
            'stored_count': 0,
            'error': 'No result returned'
        }

    def _update_last_fetched(self, feed_id: int) -> None:
        """
        更新订阅源的 last_fetched_at 时间戳

        Args:
            feed_id: 订阅源ID
        """
        try:
            cur = self.db_manager.pg_conn.cursor()
            cur.execute("""
                UPDATE user_feeds
                SET last_fetched_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (feed_id,))
            self.db_manager.pg_conn.commit()
            cur.close()
            logger.debug(f"订阅源 {feed_id} last_fetched_at 已更新")
        except Exception as e:
            logger.error(f"更新 last_fetched_at 失败: feed_id={feed_id}, error={str(e)}")
