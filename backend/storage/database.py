import psycopg2
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from typing import List, Dict, Any, Optional
import functools
import json
import logging
import uuid
import time
import asyncio
import threading
import os
from pathlib import Path
from contextlib import contextmanager
from core.config.settings import settings
from backend.config.onboarding_starter_pack import get_starter_pack_feed_defs
from backend.utils.whitelist import filter_tts_pregenerate_users
from backend.utils.url import normalize_url, generate_content_hash

# Phase 3: TTS 预合成支持已废弃（v2 MP3 架构迁移）
# from backend.nlp.tts_segment_service import extract_first_segment, pregenerate_tts_segment
from backend.nlp.speech_service import get_speech_service
from backend.services.tts_stable_playback import StableTtsPlaybackManager, get_stable_tts_manager

# user_feeds 表结构：
# CREATE TABLE user_feeds (
#     id SERIAL PRIMARY KEY,
#     user_id VARCHAR(64) NOT NULL,
#     feed_name VARCHAR(255) NOT NULL,
#     feed_url VARCHAR(1024) NOT NULL,
#     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );


def _with_db_scope(func):
    """
    装饰器：将方法体包裹在 ``self.connection_scope()`` 中，保证连接的 checkout
    与 release 都发生在同一线程（即真正执行 DB 操作的线程）。

    背景:
        ``DBConnectionMiddleware.dispatch`` 是 ``async def``，运行在事件循环线程；
        但 FastAPI 的同步 ``def`` 路由处理器运行在 worker 线程池。``threading.local()``
        的连接归属于检出连接的线程，中间件在事件循环线程上调用 ``release_conn()``
        无法归还 worker 线程中已检出的连接，从而出现 ``idle in transaction`` 泄漏。

    使用 ``connection_scope`` 的 re-entrant 实现可以避免方法嵌套调用时被过早释放。
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with self.connection_scope():
            return func(self, *args, **kwargs)

    return wrapper


class DatabaseManager:
    # ✅ 类级别并发控制（从配置读取）
    _tts_semaphore = None  # 延迟初始化
    _tts_last_request_time = 0  # 上次请求时间戳（类级别共享）
    _tts_lock = threading.Lock()  # 保护 last_request_time 的锁

    def __init__(self, pg_config: Dict[str, str]):
        """
        数据访问管理器，仅使用 PostgreSQL。

        Phase 1 商业化：使用 ThreadedConnectionPool 替代单连接，支持多用户并发访问。
        """
        # Connection pooling: minconn=5 (idle connections), maxconn=80 (max concurrent)
        # 推广期负载估算: 1000注册用户/400月活, 峰值同时在线~50人
        # HTTP并发(30) + 定时任务(10连接) + TTS预生成(10) + 缓冲(30) = ~80
        # PostgreSQL max_connections 已调至 200 (docker-compose.prod.yml)
        self._pool = ThreadedConnectionPool(minconn=5, maxconn=80, **pg_config)
        self._thread_local = threading.local()
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Database connection pool initialized (min=5, max=80)")

        # ✅ 初始化 TTS 预生成信号量（仅初始化一次）
        if DatabaseManager._tts_semaphore is None:
            DatabaseManager._tts_semaphore = threading.Semaphore(
                settings.tts_pregenerate_concurrency
            )
            self.logger.info(
                f"🚦 [TTS 预生成] 并发控制初始化: "
                f"concurrency={settings.tts_pregenerate_concurrency}, "
                f"min_interval={settings.tts_pregenerate_min_interval}s"
            )

        # 进程内缓存: user_id -> (timestamp, feeds)
        self._user_feeds_cache: Dict[str, Any] = {}
        # 使用配置中的 TTL，默认由 settings.user_feeds_cache_ttl_seconds 控制
        self._user_feeds_cache_ttl: int = settings.user_feeds_cache_ttl_seconds

    @property
    def pg_conn(self):
        """
        Thread-local database connection from pool.

        Each thread gets its own connection, reused across method calls within the same request.
        Call release_conn() after each request to return the connection to the pool.
        """
        if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None or self._thread_local.conn.closed:
            self._thread_local.conn = self._pool.getconn()
        return self._thread_local.conn

    def release_conn(self):
        """Return the current thread's connection back to the pool."""
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn is not None:
            conn = self._thread_local.conn
            # 防御性 rollback：归还前回滚未结束的事务，避免连接以 idle in transaction 状态滞留。
            # psycopg2 默认 autocommit=False，SELECT 也会隐式开启事务。
            # 注：ThreadedConnectionPool.putconn() 本身在归还非空闲连接时已有 rollback，
            # 此处显式 rollback 仅为防御性 guard，确保事务边界清晰。
            try:
                if not conn.closed:
                    conn.rollback()
            except Exception as e:
                self.logger.warning(f"rollback before putconn failed: {e}")
            try:
                self._pool.putconn(conn)
            except Exception:
                pass
            self._thread_local.conn = None

    def close_pool(self):
        """Close all connections in the pool (call on app shutdown)."""
        try:
            self._pool.closeall()
            self.logger.info("Database connection pool closed")
        except Exception as e:
            self.logger.warning(f"Error closing connection pool: {e}")

    @contextmanager
    def connection_scope(self):
        """
        Re-entrant context manager: 保证连接在使用后被正确释放，且释放发生在
        实际进行 DB 操作的同一线程（避免 thread-local 跨线程错配导致
        ``idle in transaction`` 泄漏）。

        通过 ``threading.local()`` 维护每线程的嵌套深度，只有最外层 ``with``
        退出时才真正归还连接。这样：

        - 外层（如 ``@_with_db_scope`` 装饰的公共方法）拥有 lifecycle，
        - 内层调用其他被装饰的方法时不会过早释放连接，
        - 背景任务（如定时抓取）依然可以显式使用 ``with db_manager.connection_scope():``。

        Usage:
            with db_manager.connection_scope():
                db_manager.some_method()
        """
        depth = getattr(self._thread_local, 'scope_depth', 0)
        self._thread_local.scope_depth = depth + 1
        try:
            yield self
        finally:
            self._thread_local.scope_depth -= 1
            if self._thread_local.scope_depth <= 0:
                # 最外层退出时才归还连接，并清理深度计数避免残留
                self._thread_local.scope_depth = 0
                self.release_conn()

    def _ensure_source_type(self, source_type: str = "rss") -> str:
        """确保源类型存在，返回UUID"""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 首先检查是否已有这个name的源类型
                cur.execute("SELECT id FROM source_types WHERE name = %s", (source_type,))
                existing_type = cur.fetchone()
                if existing_type:
                    # 如果源类型存在，返回其ID
                    return existing_type['id']

                # 生成UUID
                source_type_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, source_type))

                # 创建新的源类型
                cur.execute("""
                    INSERT INTO source_types (id, name, display_name, description, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET id = EXCLUDED.id
                """, (source_type_uuid, source_type, source_type.upper(), f"{source_type} RSS feeds", True))

                self.pg_conn.commit()
                self.logger.info(f"创建源类型: {source_type} -> {source_type_uuid}")

                return source_type_uuid
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.warning(f"创建源类型失败: {e}")
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, source_type))
        
    def store_article(self, article: Dict[str, Any]) -> tuple:
        """
        存储文章到 PostgreSQL（Phase 1 双写兼容模式）
        同时写入 global_articles（共享内容池）和 articles（兼容层）

        Returns:
            tuple: (global_article_id, legacy_article_id, is_new)
        """
        try:
            legacy_article_id = None
            is_new = False
            global_article_id = None
            content = article.get('content', '')

            # 确保 feed_id 是整数
            feed_id = article.get('feed_id', 1)
            if isinstance(feed_id, str):
                try:
                    feed_id = int(feed_id.split('-')[-1]) if '-' in feed_id else 1
                except Exception:
                    feed_id = 1

            # 查询 feed 所属用户（用于 user_article_refs）
            user_id = self._get_user_id_by_feed_id(feed_id)

            # 规范化 URL 和生成内容哈希
            article_url = article.get('link', article.get('url', ''))
            norm_url = normalize_url(article_url)
            content_hash = generate_content_hash(content, norm_url)

            with self.pg_conn.cursor() as cur:
                # 先查询旧的 content_hash，用于判断文章内容是否真正变化
                cur.execute("SELECT content_hash FROM global_articles WHERE url = %s", (norm_url,))
                row = cur.fetchone()
                old_content_hash = row[0] if row else None

                # 确保 source_type 存在
                source_type_id = self._ensure_source_type("rss")

                # 1) 双写：global_articles（全局内容池，按 URL 去重）
                cur.execute("""
                    INSERT INTO global_articles (
                        url, content_hash, title, author, published_at,
                        content, summary, source_feed_url, source_type_id,
                        word_count, reading_time, cover_image, language
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                        content_hash = EXCLUDED.content_hash,
                        title = EXCLUDED.title,
                        author = EXCLUDED.author,
                        published_at = EXCLUDED.published_at,
                        content = EXCLUDED.content,
                        summary = CASE WHEN EXCLUDED.summary IS NOT NULL AND EXCLUDED.summary != '' THEN EXCLUDED.summary ELSE global_articles.summary END,
                        source_feed_url = EXCLUDED.source_feed_url,
                        word_count = EXCLUDED.word_count,
                        reading_time = EXCLUDED.reading_time,
                        cover_image = EXCLUDED.cover_image,
                        language = EXCLUDED.language,
                        last_updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (
                    norm_url,
                    content_hash,
                    article['title'],
                    article.get('author'),
                    article.get('published', article.get('published_at')),
                    content,
                    article.get('summary'),
                    article.get('source', ''),
                    source_type_id,
                    article.get('word_count'),
                    article.get('reading_time'),
                    article.get('cover_image'),
                    article.get('language', 'zh')
                ))
                global_article_id = cur.fetchone()[0]

                # 2) 双写：articles（兼容层，保留现有行为）
                cur.execute("""
                    INSERT INTO articles (
                        feed_id, source_type_id, title, url, published_at, summary, content,
                        author, source, content_hash, language, word_count,
                        reading_time, cover_image
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (feed_id, url) DO UPDATE SET
                        title = EXCLUDED.title,
                        published_at = EXCLUDED.published_at,
                        summary = EXCLUDED.summary,
                        content = EXCLUDED.content,
                        author = EXCLUDED.author,
                        source = EXCLUDED.source,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, (xmax = 0) AS is_new
                """, (
                    feed_id,
                    source_type_id,
                    article['title'],
                    norm_url,
                    article.get('published', article.get('published_at')),
                    article.get('summary', ''),
                    content,
                    article.get('author', ''),
                    article.get('source', ''),
                    content_hash,
                    article.get('language', 'zh'),
                    article.get('word_count'),
                    article.get('reading_time'),
                    article.get('cover_image')
                ))
                legacy_article_id, is_new = cur.fetchone()

                # 3) 创建/更新用户关联（兼容层）
                # 只在文章内容真正变化（content_hash 改变）或首次插入时更新 fetched_at，
                # 避免 RSS 源重复推送相同文章时错误刷新排序时间
                # TODO: 当前使用 global_articles.content_hash 做全局判断，若用户 A 先更新了
                # 文章，用户 B 后续抓取同一更新时可能不会刷新 fetched_at（因为全局 hash
                # 已与新内容一致）。RSS 文章极少更新，此边界情况暂不影响生产；若未来
                # 需要精确处理，可在 user_article_refs 中添加 last_seen_content_hash 字段。
                content_changed = old_content_hash != content_hash
                if user_id:
                    if content_changed or old_content_hash is None:
                        cur.execute("""
                            INSERT INTO user_article_refs (
                                user_id, global_article_id, legacy_article_id, feed_id, fetched_at
                            ) VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP))
                            ON CONFLICT (user_id, global_article_id, feed_id) DO UPDATE SET
                                legacy_article_id = EXCLUDED.legacy_article_id,
                                fetched_at = CURRENT_TIMESTAMP
                        """, (user_id, global_article_id, legacy_article_id, feed_id,
                              article.get('published', article.get('published_at'))))
                    else:
                        cur.execute("""
                            INSERT INTO user_article_refs (
                                user_id, global_article_id, legacy_article_id, feed_id, fetched_at
                            ) VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP))
                            ON CONFLICT (user_id, global_article_id, feed_id) DO UPDATE SET
                                legacy_article_id = EXCLUDED.legacy_article_id
                        """, (user_id, global_article_id, legacy_article_id, feed_id,
                              article.get('published', article.get('published_at'))))

                self.pg_conn.commit()
                self.logger.info(
                    f"成功存储/更新文章: {article['title']} "
                    f"(global_id={global_article_id}, legacy_id={legacy_article_id}, is_new={is_new})"
                )

            # TTS 预生成触发（自托管版所有订阅用户，后台线程非阻塞）
            # Phase 2：使用 global_article_id
            if is_new and global_article_id:
                feed_url = article.get('source')
                pregenerate_users = self._get_feed_tts_pregenerate_users(feed_url)
                pregenerate_users = filter_tts_pregenerate_users(pregenerate_users)
                if pregenerate_users:
                    import threading
                    for pregenerate_user_id in pregenerate_users:
                        thread = threading.Thread(
                            target=self._pregenerate_tts_sync,
                            args=(global_article_id, pregenerate_user_id),
                            daemon=True
                        )
                        thread.start()
                        self.logger.info(
                            f"🎵 触发 TTS 预生成（后台线程）: article_id={global_article_id}, user={pregenerate_user_id}"
                        )

            return global_article_id, legacy_article_id, is_new

        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"存储文章失败: {str(e)}")
            raise
            
    def search_articles(self, query: str, size: int = 10) -> List[Dict[str, Any]]:
        """
        搜索文章（全局范围）。

        Phase 1：统一使用 PostgreSQL 进行模糊搜索，不再依赖 ES。
        """
        return self.search_articles_pg(query, limit=size, offset=0)

    def search_articles_pg(self, query: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """
        使用 PostgreSQL 进行全文搜索（Phase 2：基于 global_articles）。

        实现：
        - 使用 to_tsvector + plainto_tsquery（simple 配置）
        - 基于 title / summary / content 组合构建向量
        - 与迁移脚本中的 GIN 索引保持一致
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id,
                           title,
                           summary,
                           url,
                           published_at,
                           author,
                           source_feed_url AS source,
                           last_updated_at AS updated_at,
                           content
                    FROM global_articles
                    WHERE to_tsvector(
                            'simple',
                            COALESCE(title, '') || ' ' ||
                            COALESCE(summary, '') || ' ' ||
                            COALESCE(content, '')
                          )
                          @@ plainto_tsquery('simple', %s)
                    ORDER BY last_updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (query, limit, offset)
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"PG 搜索失败: {e}")
            return []

    def search_user_articles_pg(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
        offset: int = 0,
        language: str = 'en'
    ) -> List[Dict[str, Any]]:
        """
        在指定用户订阅范围内使用 PostgreSQL 全文搜索（Phase 2：基于 global_articles + user_article_refs）。

        实现：
        - 限定 JOIN user_article_refs + user_feeds，确保只搜索当前用户的文章；
        - 使用与 search_articles_pg 相同的 tsvector 表达式。
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ga.id,
                           ga.title,
                           COALESCE(as_lang.summary, ga.summary) AS summary,
                           ga.url,
                           ga.published_at,
                           ga.author,
                           ga.source_feed_url AS source,
                           uar.fetched_at AS updated_at,
                           ga.content
                    FROM global_articles ga
                    JOIN user_article_refs uar ON uar.global_article_id = ga.id
                    JOIN user_feeds f ON f.id = uar.feed_id
                    LEFT JOIN article_summaries as_lang
                      ON as_lang.global_article_id = ga.id AND as_lang.language = %s
                    WHERE f.user_id = %s
                      AND to_tsvector(
                            'simple',
                            COALESCE(ga.title, '') || ' ' ||
                            COALESCE(ga.summary, '') || ' ' ||
                            COALESCE(ga.content, '')
                          )
                          @@ plainto_tsquery('simple', %s)
                    ORDER BY uar.fetched_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (language, user_id, query, limit, offset)
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"用户范围 PG 搜索失败: {e}")
            return []

    def search_articles_scoped(self, query: str, size: int, feed_urls: List[str]) -> List[Dict[str, Any]]:
        """
        在用户订阅源范围内搜索文章。

        Phase 1：为向后兼容保留签名，内部实现统一降级为 PostgreSQL 搜索，
        并在内存中根据 feed_urls 对结果进行过滤。
        """
        if not feed_urls:
            return []
        try:
            # 先使用全局 PG 搜索获取一批候选结果
            fallback = self.search_articles_pg(query, limit=size * 5, offset=0)
            feed_url_set = set(feed_urls)
            return [a for a in fallback if a.get('source') in feed_url_set][:size]
        except Exception as e:
            self.logger.error(f"Scoped PG search failed: {e}")
            return []

    def get_article_id_by_url(self, url: str) -> Any:
        """根据URL获取文章ID（返回 global_articles.id）"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT id FROM global_articles WHERE url = %s LIMIT 1", (url,))
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as e:
            self.logger.error(f"根据URL查询文章ID失败: {str(e)}")
            return None
            
    def get_top_news(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取热门新闻（Phase 2：基于 global_articles）。

        按照最近 N 天内的 published_at 排序，取前若干条。
        （global_articles 暂无 view_count，按发布时间排序）
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, summary, url, published_at, author,
                           source_feed_url AS source, last_updated_at AS updated_at, content
                    FROM global_articles
                    WHERE published_at >= NOW() - (%s || ' days')::interval
                    ORDER BY published_at DESC
                    LIMIT 10
                    """,
                    (days,)
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting top news from PostgreSQL: {str(e)}")
            return []

    def get_articles_by_source(self, source: str = None, feed_id: int = None, only_summary: bool = False, order_by: str = 'updated_at', desc: bool = True, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """按来源/频道或订阅源ID获取文章，支持只返回摘要/全文、排序与分页（Phase 2：基于 global_articles）"""
        try:
            with self.pg_conn.cursor() as cur:
                fields = "ga.id, ga.title, ga.summary, ga.url, ga.published_at, ga.author, ga.source_feed_url AS source, ga.last_updated_at AS updated_at"
                if not only_summary:
                    fields += ", ga.content"
                query = f"SELECT {fields} FROM global_articles ga"
                params = []
                where_clauses = []
                if source:
                    where_clauses.append("ga.source_feed_url = %s")
                    params.append(source)
                if feed_id is not None:
                    query += " JOIN user_article_refs uar ON uar.global_article_id = ga.id"
                    where_clauses.append("uar.feed_id = %s")
                    params.append(feed_id)
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
                ORDER_FIELD_MAP = {
                    "updated_at": "ga.last_updated_at",
                    "published_at": "ga.published_at",
                    "title": "ga.title",
                    "created_at": "ga.first_seen_at",
                }
                if order_by not in ORDER_FIELD_MAP:
                    order_by = "updated_at"
                order_field = ORDER_FIELD_MAP[order_by]
                query += f" ORDER BY {order_field} {'DESC' if desc else 'ASC'} LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                return results
        except Exception as e:
            self.logger.error(f"按来源获取文章失败: {str(e)}")
            return []

    def article_exists(self, feed_id: str, url: str) -> bool:
        """判断指定 feed_id 和 url 的文章是否已存在（Phase 2：基于 user_article_refs + global_articles）"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM user_article_refs uar
                    JOIN global_articles ga ON ga.id = uar.global_article_id
                    WHERE uar.feed_id = %s AND ga.url = %s
                    LIMIT 1
                    """,
                    (feed_id, url)
                )
                return cur.fetchone() is not None
        except Exception as e:
            self.logger.error(f"检查文章是否存在失败: {str(e)}")
            return False

    def get_article_by_url(self, url: str) -> Dict[str, Any]:
        """根据URL获取文章详情（Phase 2：从 global_articles 查询）"""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        source_feed_url AS source,
                        title,
                        url,
                        content,
                        summary,
                        author,
                        published_at,
                        entities,
                        source_type_id AS feed_id,
                        last_updated_at AS updated_at
                    FROM global_articles
                    WHERE url = %s
                    LIMIT 1
                    """,
                    (url,)
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            self.logger.error(f"根据URL获取文章失败: {str(e)}")
            return None

    def get_user_article_by_url(self, user_id: str, url: str, language: str = 'en') -> Dict[str, Any]:
        """根据URL获取用户所属的文章详情（Phase 2：从 user_article_refs + global_articles 查询）"""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        ga.id,
                        uar.feed_id,
                        ga.title,
                        ga.url,
                        ga.content,
                        COALESCE(as_lang.summary, ga.summary) AS summary,
                        ga.author,
                        ga.published_at,
                        ga.entities,
                        ga.source_feed_url AS source,
                        ga.last_updated_at AS updated_at
                    FROM global_articles ga
                    JOIN user_article_refs uar ON uar.global_article_id = ga.id
                    LEFT JOIN article_summaries as_lang
                      ON as_lang.global_article_id = ga.id AND as_lang.language = %s
                    WHERE ga.url = %s AND uar.user_id = %s
                    LIMIT 1
                    """,
                    (language, url, user_id)
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"根据URL获取用户文章失败: {str(e)}")
            return None

    def get_article_metadata(self, article_id: int) -> Dict[str, Any]:
        """
        获取文章元数据（用于 TTS 生成和 Media Session）

        Args:
            article_id: global_articles.id

        Returns:
            包含文章元数据的字典，失败时返回 None
        """
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        title,
                        source_feed_url AS source,
                        summary,
                        content,
                        cover_image
                    FROM global_articles
                    WHERE id = %s
                    """,
                    (article_id,)
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                else:
                    self.logger.warning(f"文章不存在: {article_id}")
                    return None
        except Exception as e:
            self.logger.error(f"获取文章元数据失败: {e}", exc_info=True)
            return None

    def get_user_article_metadata(self, user_id: str, article_id: int, language: str = 'en') -> Dict[str, Any]:
        """获取用户所属的文章元数据（通过 user_article_refs 验证所有权，article_id 为 global_articles.id）"""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        ga.id, ga.title, ga.source_feed_url AS source,
                        COALESCE(as_lang.summary, ga.summary) AS summary,
                        ga.content, ga.cover_image, ga.language,
                        uar.global_article_id
                    FROM user_article_refs uar
                    JOIN global_articles ga ON ga.id = uar.global_article_id
                    LEFT JOIN article_summaries as_lang
                      ON as_lang.global_article_id = ga.id AND as_lang.language = %s
                    WHERE uar.global_article_id = %s AND uar.user_id = %s
                    LIMIT 1
                    """,
                    (language, article_id, user_id)
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            self.logger.error(f"获取用户文章元数据失败: {e}", exc_info=True)
            return None

    @staticmethod
    def _normalize_feed_url(url: str) -> str:
        """Normalize feed URL for matching: ignore protocol, lowercase host, strip trailing slash."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url.strip())
            host = parsed.hostname.lower() if parsed.hostname else ''
            path = parsed.path
            if path != '/' and path.endswith('/'):
                path = path[:-1]
            return f"{host}{path}{parsed.query}"
        except Exception:
            return url

    def get_user_article_metadata_with_fallback(
        self,
        user_id: str,
        article_id: int,
        language: str = 'en'
    ) -> Dict[str, Any]:
        """
        获取用户文章元数据，带 user_article_refs 自动修复兜底。

        背景：新用户通过 starter pack 快速添加订阅源后，global_articles 中可能已存在该源的历史文章，
        但 create_user_feed() 的 user_article_refs 链接只覆盖当时存在的文章。后续新抓取的 global_articles
        可能没有对应的 user_article_refs，导致 TTS/play 等依赖该表的接口返回 404。

        逻辑：
        1. 先走标准 user_article_refs JOIN 查询；
        2. 若未命中，检查该 article_id 是否存在于 global_articles，且用户订阅了对应的 source_feed_url；
        3. 若满足条件，自动补创建 user_article_refs 并返回文章元数据。

        注意：feed_url 匹配使用 URL 归一化（忽略协议、尾部斜杠、host 大小写），避免同一订阅源因 URL
        变体差异导致 fallback 失效。
        """
        # 1) 标准查询
        result = self.get_user_article_metadata(user_id, article_id, language=language)
        if result:
            return result

        # 2) 兜底：检查 global_articles + user_feeds 匹配
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 获取文章信息
                cur.execute(
                    "SELECT id, title, source_feed_url, summary, content, cover_image FROM global_articles WHERE id = %s",
                    (article_id,)
                )
                article = cur.fetchone()
                if not article:
                    return None

                source_feed_url = article["source_feed_url"]
                if not source_feed_url:
                    return None

                # 检查用户是否订阅了该 source_feed_url（使用 URL 归一化匹配）
                cur.execute(
                    "SELECT id, feed_url FROM user_feeds WHERE user_id = %s",
                    (user_id,)
                )
                user_feeds = cur.fetchall()
                normalized_source = self._normalize_feed_url(source_feed_url)
                feed_row = None
                for uf in user_feeds:
                    if self._normalize_feed_url(uf["feed_url"]) == normalized_source:
                        feed_row = uf
                        break
                if not feed_row:
                    return None

                localized_summary = self.get_article_summary(article_id, language)
                if localized_summary:
                    article["summary"] = localized_summary

                feed_id = feed_row["id"]

                # 3) 自动补创建 user_article_refs（同时补 legacy articles 行，保持下游兼容）
                cur.execute(
                    """
                    INSERT INTO articles (
                        feed_id, source_type_id, title, url, published_at, summary, content,
                        author, source, content_hash, language
                    )
                    SELECT
                        %s, st.id, ga.title, ga.url, ga.published_at, ga.summary, ga.content,
                        ga.author, ga.source_feed_url, ga.content_hash, ga.language
                    FROM global_articles ga
                    CROSS JOIN (SELECT id FROM source_types WHERE name = 'rss' LIMIT 1) st
                    WHERE ga.id = %s
                    ON CONFLICT (feed_id, url) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        content = EXCLUDED.content,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    (feed_id, article_id)
                )
                legacy_row = cur.fetchone()
                legacy_article_id = legacy_row["id"] if legacy_row else None

                cur.execute(
                    """
                    INSERT INTO user_article_refs (
                        user_id, global_article_id, legacy_article_id, feed_id, fetched_at
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, global_article_id, feed_id) DO UPDATE SET
                        legacy_article_id = EXCLUDED.legacy_article_id,
                        fetched_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, article_id, legacy_article_id, feed_id)
                )
                self.pg_conn.commit()
                self.logger.info(
                    f"user_article_refs fallback: 自动补创建 user={user_id} article={article_id} feed={feed_id}"
                )

                return {
                    "id": article["id"],
                    "title": article["title"],
                    "source": article["source_feed_url"],
                    "summary": article["summary"],
                    "content": article["content"],
                    "cover_image": article["cover_image"],
                    "global_article_id": article["id"],
                }
        except Exception as e:
            self.logger.error(f"user_article_refs fallback 失败: {e}", exc_info=True)
            self.pg_conn.rollback()
            return None

    def _get_feed_tts_pregenerate_users(self, feed_url: str) -> list:
        """查询订阅该源的全部用户，用于自托管版 TTS 预生成。"""
        try:
            if not feed_url:
                return []

            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT uf.user_id FROM user_feeds uf WHERE uf.feed_url = %s AND uf.is_active = true",
                    (feed_url,)
                )
                results = cur.fetchall()
                return [row[0] for row in results]
        except Exception as e:
            self.logger.error(f"查询 feed TTS 预生成用户失败: feed_url={feed_url}, error={e}")
            return []

    def _get_feed_user_id(self, feed_url: str) -> str:
        """
        根据 feed_url 查询所属用户 ID（兼容旧代码）

        Args:
            feed_url: 订阅源 URL

        Returns:
            用户 ID，失败时返回 None
        """
        try:
            if not feed_url:
                return None

            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT user_id FROM user_feeds WHERE feed_url = %s LIMIT 1", (feed_url,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            self.logger.error(f"查询 feed 用户失败: feed_url={feed_url}, error={e}")
            return None

    def _get_user_id_by_feed_id(self, feed_id: int) -> str:
        """
        根据 feed_id 查询所属用户 ID

        Args:
            feed_id: 订阅源 ID

        Returns:
            用户 ID，失败时返回 None
        """
        try:
            if not feed_id:
                return None
            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT user_id FROM user_feeds WHERE id = %s LIMIT 1", (feed_id,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            self.logger.error(f"查询 feed 用户失败: feed_id={feed_id}, error={e}")
            return None

    def get_user_language(self, user_id: str) -> str:
        """获取用户偏好语言，默认 'en'"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("SELECT preferred_language FROM users WHERE id = %s LIMIT 1", (user_id,))
                result = cur.fetchone()
                return result[0] if result and result[0] else 'en'
        except Exception as e:
            self.logger.error(f"查询用户语言偏好失败: user_id={user_id}, error={e}")
            return 'en'

    def get_article_summary(self, global_article_id: int, language: str = 'en') -> Optional[str]:
        """按语言获取已缓存的 AI 摘要"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT summary FROM article_summaries WHERE global_article_id = %s AND language = %s LIMIT 1",
                    (global_article_id, language)
                )
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            self.logger.error(f"查询文章摘要缓存失败: global_id={global_article_id}, lang={language}, error={e}")
            return None

    def upsert_article_summary(self, global_article_id: int, language: str, summary: str) -> None:
        """缓存语言特定的 AI 摘要"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO article_summaries (global_article_id, language, summary)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (global_article_id, language) DO UPDATE SET
                        summary = EXCLUDED.summary,
                        updated_at = CURRENT_TIMESTAMP
                """, (global_article_id, language, summary))
                self.pg_conn.commit()
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"缓存文章摘要失败: global_id={global_article_id}, lang={language}, error={e}")

    def update_article_summary(self, global_article_id: int, legacy_article_id: int, summary: str) -> None:
        """更新兼容层 articles 的 summary 字段，避免语言特定摘要污染全局共享内容"""
        try:
            with self.pg_conn.cursor() as cur:
                if legacy_article_id:
                    cur.execute("UPDATE articles SET summary = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (summary, legacy_article_id))
                self.pg_conn.commit()
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"更新文章摘要失败: global_id={global_article_id}, legacy_id={legacy_article_id}, error={e}")

    def _pregenerate_tts_sync(self, article_id: int, user_id: str = None):
        """
        同步包装器：在后台线程中运行异步预生成任务

        Args:
            article_id: 文章 ID
            user_id: 用户 ID（用于记录用量和日志）
        """
        # ✅ 使用信号量限制并发数（Azure OpenAI 配额：3 RPM）
        with self._tts_semaphore:
            try:
                # ✅ 智能限流：确保请求间隔符合配置（避免 Rate Limit）
                with self._tts_lock:
                    current_time = time.time()
                    elapsed = current_time - self._tts_last_request_time
                    min_interval = settings.tts_pregenerate_min_interval

                    if elapsed < min_interval:
                        wait_time = min_interval - elapsed
                        self.logger.info(
                            f"⏳ [TTS 预生成] 限流等待: {wait_time:.1f}s "
                            f"(Azure OpenAI {60/min_interval:.0f} RPM 限制)"
                        )
                        time.sleep(wait_time)

                    # 更新上次请求时间
                    DatabaseManager._tts_last_request_time = time.time()

                # 创建新的事件循环（线程独立）
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # 同步运行异步任务
                    loop.run_until_complete(self._pregenerate_tts_for_article(article_id, user_id))
                finally:
                    # ✅ 修复：确保所有异步任务完全清理后再关闭循环
                    # 关键：在关闭循环之前，必须确保所有资源已释放

                    # 1. 获取所有待处理任务
                    try:
                        pending = asyncio.all_tasks(loop)
                    except RuntimeError:
                        # 如果获取任务失败，可能循环已关闭，直接返回
                        return

                    # 2. 取消所有未完成的任务
                    for task in pending:
                        if not task.done():
                            task.cancel()

                    # 3. 等待所有任务完成（包括清理）- 这给了 httpx/httpcore 时间释放资源
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

                    # 4. 给予事件循环时间处理未决的 I/O 和回调
                    # 这对 httpx 的连接清理至关重要
                    loop.run_until_complete(asyncio.sleep(0))

                    # 5. 等待所有异步生成器关闭
                    loop.run_until_complete(loop.shutdown_asyncgens())

                    # 6. 最后再关闭循环
                    loop.close()
            except Exception as e:
                self.logger.error(
                    f"❌ [TTS 预生成线程] 失败: article_id={article_id}, error={e}",
                    exc_info=True
                )
            finally:
                # ✅ 关键：释放数据库连接回连接池
                # 后台线程没有 HTTP 中间件来释放连接，必须手动释放
                try:
                    self.release_conn()
                except Exception:
                    pass

    async def _pregenerate_tts_for_article(self, article_id: int, user_id: str = None):
        """
        为指定文章预生成 TTS 音频缓存（异步非阻塞）

        Args:
            article_id: 文章 ID
            user_id: 用户 ID（用于记录用量和日志）
        """
        speech_service = None
        stable_manager = get_stable_tts_manager(settings)
        try:
            start_time = time.time()
            self.logger.info(f"🚀 [TTS 预生成] 开始: article_id={article_id}, user={user_id}")

            # 1. 获取文章 metadata
            article = self.get_article_metadata(article_id)
            if not article:
                self.logger.warning(f"❌ [TTS 预生成] 文章不存在: {article_id}")
                return

            # 2. 初始化 TTS 服务（每个任务独立实例，避免跨线程共享 httpx 客户端）
            speech_service = get_speech_service(settings)
            voice = stable_manager.normalize_voice(speech_service, None)

            # 3. 清洗文本（与播放接口保持一致）
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(article['content'], 'html.parser')
            clean_text = soup.get_text(separator=' ', strip=True)

            if not clean_text or not clean_text.strip():
                self.logger.warning(f"⚠️  [TTS 预生成] 文章内容为空: {article_id}")
                return

            # 使用与播放接口一致的文本处理（标题 + 内容）
            tts_text_parts = [article['title']]
            tts_text_parts.append(clean_text)
            tts_text = stable_manager.prepare_text('。'.join(tts_text_parts))

            # 4. 计算 V2 缓存状态（必须与播放接口完全一致）
            cache_key = stable_manager.build_cache_key(
                speech_service,
                tts_text,
                voice,
                article_id=str(article_id)
            )
            status = await stable_manager.get_status(
                speech_service=speech_service,
                article_id=str(article_id),
                clean_text=tts_text,
                voice=voice
            )

            # 5. 检查缓存是否已存在
            if status.get("final_ready"):
                resolved_path = stable_manager.resolve_final_path(speech_service, cache_key)
                cache_name = resolved_path.name if resolved_path else stable_manager.get_final_path(cache_key).name
                self.logger.info(f"⏭️  [TTS 预生成] 跳过: 缓存已存在 {cache_name}")
                return

            if status.get("status") == "generating":
                self.logger.info(f"⚠️  [TTS 预生成] 已有进行中的 V2 任务，跳过重复生成: {article_id}")
                return

            # 6. 初始化 manifest 并执行 V2 分段生成
            manifest = stable_manager._read_manifest(cache_key)
            if manifest is None:
                manifest = stable_manager._build_initial_manifest(
                    str(article_id),
                    cache_key,
                    voice,
                    tts_text
                )
            manifest["status"] = "generating"
            manifest["error_info"] = None
            stable_manager._write_manifest(cache_key, manifest)

            await stable_manager._generate_article_audio(
                speech_service=speech_service,
                article_id=str(article_id),
                clean_text=tts_text,
                voice=voice,
                cache_key=cache_key
            )

            # 7. 验证文件是否真正生成
            resolved_path = stable_manager.resolve_final_path(speech_service, cache_key)
            if not resolved_path or not resolved_path.exists():
                raise RuntimeError(f"预生成失败: 缓存文件不存在 {stable_manager.get_final_path(cache_key)}")

            file_size = resolved_path.stat().st_size
            if file_size == 0:
                raise RuntimeError(f"预生成失败: 缓存文件大小为 0 {resolved_path}")

            final_status = stable_manager.get_status(
                speech_service=speech_service,
                article_id=str(article_id),
                clean_text=tts_text,
                voice=voice
            )
            if not final_status.get("final_ready"):
                raise RuntimeError(final_status.get("error_info") or "V2 预生成未完成")

            # 8. 记录成功结果
            elapsed = time.time() - start_time
            self.logger.info(
                f"✅ [TTS 预生成] 成功: article_id={article_id}, "
                f"cache_key={cache_key}, segments={final_status.get('segments_total')}, "
                f"size={file_size/1024:.1f}KB, time={elapsed:.2f}s"
            )

        except Exception as e:
            self.logger.error(
                f"❌ [TTS 预生成] 失败: article_id={article_id}, error={e}",
                exc_info=True
            )
            # 失败不阻断，用户播放时会降级到流式透传
        finally:
            # ✅ 不再此处关闭客户端，让事件循环自然清理
            # 原因：_producer_task 可能还在使用客户端进行 HTTP 连接清理
            # 在 _pregenerate_tts_sync 的 finally 块中已经处理了事件循环的优雅关闭
            pass

    # ================== 收藏与阅读历史 (Week 3) ==================
    def add_saved_article(self, user_id: str, article_id: int) -> bool:
        """article_id 为 global_articles.id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_saved_articles (user_id, global_article_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, global_article_id) DO NOTHING
                    """,
                    (user_id, article_id)
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"添加收藏失败: {e}")
            return False

    def remove_saved_article(self, user_id: str, article_id: int) -> bool:
        """article_id 为 global_articles.id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_saved_articles WHERE user_id = %s AND global_article_id = %s",
                    (user_id, article_id)
                )
                self.pg_conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"取消收藏失败: {e}")
            return False

    def is_article_saved(self, user_id: str, article_id: int) -> bool:
        """article_id 为 global_articles.id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM user_saved_articles WHERE user_id = %s AND global_article_id = %s LIMIT 1",
                    (user_id, article_id)
                )
                return cur.fetchone() is not None
        except Exception as e:
            self.logger.error(f"查询收藏状态失败: {e}")
            return False

    @_with_db_scope
    def list_saved_articles(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ga.id, ga.title, ga.summary, ga.url, ga.published_at, ga.author,
                           ga.source_feed_url AS source, ga.last_updated_at AS updated_at, ga.content
                    FROM user_saved_articles s
                    JOIN global_articles ga ON ga.id = s.global_article_id
                    WHERE s.user_id = %s
                    ORDER BY s.saved_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset)
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"获取收藏列表失败: {e}")
            return []

    def mark_article_read(self, user_id: str, article_id: int, read_at: Any = None) -> bool:
        """article_id 为 global_articles.id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_reading_history (user_id, global_article_id, is_read, read_at)
                    VALUES (%s, %s, true, COALESCE(%s, CURRENT_TIMESTAMP))
                    ON CONFLICT (user_id, global_article_id) DO UPDATE SET
                      is_read = EXCLUDED.is_read,
                      read_at = EXCLUDED.read_at,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, article_id, read_at)
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"标记已读失败: {e}")
            return False

    def mark_article_unread(self, user_id: str, article_id: int) -> bool:
        """article_id 为 global_articles.id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_reading_history (user_id, global_article_id, is_read)
                    VALUES (%s, %s, false)
                    ON CONFLICT (user_id, global_article_id) DO UPDATE SET
                      is_read = false,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, article_id)
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"标记未读失败: {e}")
            return False

    # ================================
    # Audio Play History Methods
    # ================================

    def record_audio_play(self, user_id: str, item_type: str, item_id: int,
                          title: str = None, source_name: str = None,
                          duration_seconds: int = 0, played_seconds: int = 0,
                          progress_percentage: float = 0, is_completed: bool = False) -> bool:
        """Record or update audio play history for TTS articles or podcasts.
        Phase 2: article 的 item_id 直接使用 global_articles.id。"""
        try:
            with self.pg_conn.cursor() as cur:
                if item_type == 'article':
                    cur.execute(
                        """
                        INSERT INTO audio_play_history
                          (user_id, item_type, item_id, global_article_id, title, source_name,
                           duration_seconds, played_seconds, progress_percentage,
                           is_completed, played_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, item_type, item_id) DO UPDATE SET
                          global_article_id = EXCLUDED.global_article_id,
                          title = EXCLUDED.title,
                          source_name = EXCLUDED.source_name,
                          duration_seconds = EXCLUDED.duration_seconds,
                          played_seconds = EXCLUDED.played_seconds,
                          progress_percentage = EXCLUDED.progress_percentage,
                          is_completed = EXCLUDED.is_completed,
                          played_at = EXCLUDED.played_at
                        """,
                        (user_id, item_type, item_id, item_id, title, source_name,
                         duration_seconds, played_seconds, progress_percentage, is_completed)
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO audio_play_history
                          (user_id, item_type, item_id, title, source_name,
                           duration_seconds, played_seconds, progress_percentage,
                           is_completed, played_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, item_type, item_id) DO UPDATE SET
                          title = EXCLUDED.title,
                          source_name = EXCLUDED.source_name,
                          duration_seconds = EXCLUDED.duration_seconds,
                          played_seconds = EXCLUDED.played_seconds,
                          progress_percentage = EXCLUDED.progress_percentage,
                          is_completed = EXCLUDED.is_completed,
                          played_at = EXCLUDED.played_at
                        """,
                        (user_id, item_type, item_id, title, source_name,
                         duration_seconds, played_seconds, progress_percentage, is_completed)
                    )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"记录播放历史失败: {e}")
            return False

    def get_audio_play_history(self, user_id: str, item_type: str = None,
                               limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get audio play history for a user, optionally filtered by type."""
        try:
            with self.pg_conn.cursor() as cur:
                if item_type:
                    cur.execute(
                        """
                        SELECT h.*, ga.url as article_url, ga.summary
                        FROM audio_play_history h
                        LEFT JOIN global_articles ga ON h.item_type = 'article' AND h.global_article_id = ga.id
                        WHERE h.user_id = %s AND h.item_type = %s
                        ORDER BY h.played_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, item_type, limit, offset)
                    )
                else:
                    cur.execute(
                        """
                        SELECT h.*, ga.url as article_url, ga.summary
                        FROM audio_play_history h
                        LEFT JOIN global_articles ga ON h.item_type = 'article' AND h.global_article_id = ga.id
                        WHERE h.user_id = %s
                        ORDER BY h.played_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset)
                    )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"获取播放历史失败: {e}")
            return []

    def clear_audio_play_history(self, user_id: str, item_type: str = None) -> bool:
        """Clear audio play history for a user, optionally filtered by type."""
        try:
            with self.pg_conn.cursor() as cur:
                if item_type:
                    cur.execute(
                        "DELETE FROM audio_play_history WHERE user_id = %s AND item_type = %s",
                        (user_id, item_type)
                    )
                else:
                    cur.execute(
                        "DELETE FROM audio_play_history WHERE user_id = %s",
                        (user_id,)
                    )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"清空播放历史失败: {e}")
            return False

    def delete_audio_play_history_item(self, user_id: str, item_type: str, item_id: int) -> bool:
        """Delete a specific item from audio play history."""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM audio_play_history WHERE user_id = %s AND item_type = %s AND item_id = %s",
                    (user_id, item_type, item_id)
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"删除播放历史项失败: {e}")
            return False

    # ================================
    # User Queue & Playback State Sync
    # ================================

    @_with_db_scope
    def get_user_queue(self, user_id: str) -> Dict[str, Any]:
        """Get the synced listen queue for a user."""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT items, updated_at
                    FROM user_queues
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                if not row:
                    return {"items": [], "updated_at": None}
                return {
                    "items": row["items"] or [],
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
        except Exception as e:
            self.logger.error(f"获取用户听读队列失败: {e}")
            return {"items": [], "updated_at": None}

    @_with_db_scope
    def save_user_queue(self, user_id: str, items: List[Dict[str, Any]]) -> bool:
        """Upsert the synced listen queue for a user."""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_queues (user_id, items, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE SET
                      items = EXCLUDED.items,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (user_id, Json(items))
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"保存用户听读队列失败: {e}")
            return False

    @_with_db_scope
    def clear_user_queue(self, user_id: str) -> bool:
        """Clear the synced listen queue for a user."""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_queues WHERE user_id = %s",
                    (user_id,)
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"清空用户听读队列失败: {e}")
            return False

    @_with_db_scope
    def get_playback_state(self, user_id: str) -> Dict[str, Any]:
        """Get the synced playback state for a user."""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT playlist, current_index, "current_time", total_time,
                           current_article, is_playing, playback_rate, updated_at
                    FROM user_playback_state
                    WHERE user_id = %s
                    """,
                    (user_id,)
                )
                row = cur.fetchone()
                if not row:
                    return self._empty_playback_state()
                return {
                    "playlist": row["playlist"] or [],
                    "current_index": row["current_index"] or 0,
                    "current_time": float(row["current_time"] or 0),
                    "total_time": float(row["total_time"] or 0),
                    "current_article": row["current_article"],
                    "is_playing": bool(row["is_playing"]) if row["is_playing"] is not None else False,
                    "playback_rate": float(row["playback_rate"] or 1.0),
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
                }
        except Exception as e:
            self.logger.error(f"获取用户播放状态失败: {e}")
            return self._empty_playback_state()

    def _empty_playback_state(self) -> Dict[str, Any]:
        return {
            "playlist": [],
            "current_index": 0,
            "current_time": 0.0,
            "total_time": 0.0,
            "current_article": None,
            "is_playing": False,
            "playback_rate": 1.0,
            "updated_at": None
        }

    @_with_db_scope
    def save_playback_state(self, user_id: str, state: Dict[str, Any]) -> bool:
        """Upsert the synced playback state for a user."""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_playback_state
                      (user_id, playlist, current_index, "current_time", total_time,
                       current_article, is_playing, playback_rate, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE SET
                      playlist = EXCLUDED.playlist,
                      current_index = EXCLUDED.current_index,
                      "current_time" = EXCLUDED."current_time",
                      total_time = EXCLUDED.total_time,
                      current_article = EXCLUDED.current_article,
                      is_playing = EXCLUDED.is_playing,
                      playback_rate = EXCLUDED.playback_rate,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (
                        user_id,
                        Json(state.get("playlist", [])),
                        state.get("current_index", 0),
                        state.get("current_time", 0),
                        state.get("total_time", 0),
                        Json(state.get("current_article")) if state.get("current_article") is not None else None,
                        state.get("is_playing", False),
                        state.get("playback_rate", 1.0)
                    )
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"保存用户播放状态失败: {e}")
            return False

    def get_existing_articles(self, feed_url_pairs: List[tuple]) -> set:
        """批量查询已存在的 (feed_id, url) 文章，返回集合（Phase 2：基于 user_article_refs + global_articles）"""
        if not feed_url_pairs:
            return set()
        try:
            with self.pg_conn.cursor() as cur:
                # 构造参数化查询，避免 SQL 注入
                values_placeholders = ','.join(['(%s, %s)'] * len(feed_url_pairs))
                query = f"""
                    SELECT uar.feed_id, ga.url
                    FROM user_article_refs uar
                    JOIN global_articles ga ON ga.id = uar.global_article_id
                    WHERE (uar.feed_id, ga.url) IN ({values_placeholders})
                """
                # 将参数展平成一维元组
                flat_params = [item for pair in feed_url_pairs for item in pair]
                cur.execute(query, flat_params)
                return set(cur.fetchall())
        except Exception as e:
            self.logger.error(f"批量查询文章是否存在失败: {str(e)}")
            return set()

    @_with_db_scope
    def create_user_feed(self, user_id: str, feed_name: str, feed_url: str) -> tuple[int, bool]:
        """添加用户订阅源（含同步链接 global_articles），返回 (feed_id, is_existing)。

        说明：该方法仍保留同步语义，主要被 OPML 导入等低频路径使用。Onboarding 等
        高并发场景请改用 create_user_feed_minimal + link_global_articles_to_feed
        组合，将耗时的 global_articles → articles/user_article_refs 链接移到后台任务。
        """
        feed_id, is_existing = self.create_user_feed_minimal(user_id, feed_name, feed_url)
        if not is_existing:
            self.link_global_articles_to_feed(user_id, feed_id, feed_url)
        return feed_id, is_existing

    @_with_db_scope
    def create_user_feed_minimal(self, user_id: str, feed_name: str, feed_url: str) -> tuple[int, bool]:
        """仅插入 user_feeds 一行，立刻 commit & 返回 (feed_id, is_existing)。

        不做 global_articles → articles/user_article_refs 的链接（这部分耗时占
        addFeed 总耗时的 >80%，应交给后台任务）。调用方拿到 feed_id 后可立即
        响应前端，并通过 BackgroundTasks 调度 link_global_articles_to_feed。
        """
        try:
            with self.pg_conn.cursor() as cur:
                source_type_id = self._ensure_source_type("rss")

                cur.execute(
                    """
                    INSERT INTO user_feeds (user_id, source_type_id, feed_name, feed_url)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (user_id, source_type_id, feed_name, feed_url)
                )
                new_id = cur.fetchone()[0]
                self.pg_conn.commit()
                self.logger.info(
                    f"成功添加用户订阅源（最小化）: {feed_name} ({feed_url}) for user {user_id}, feed_id={new_id}"
                )
                # 订阅源发生变化时，清空用户订阅缓存（简单起见清空全局缓存）
                self._user_feeds_cache.clear()
                return new_id, False
        except psycopg2.IntegrityError as e:
            self.pg_conn.rollback()
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM user_feeds WHERE user_id = %s AND feed_url = %s",
                    (user_id, feed_url)
                )
                row = cur.fetchone()
                if row:
                    existing_id = row[0]
                    self.logger.info(
                        f"订阅源已存在，返回现有 id: {existing_id} ({feed_url}) for user {user_id}"
                    )
                    return existing_id, True
            self.logger.error(f"添加用户订阅源失败: {str(e)}")
            raise
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"添加用户订阅源失败: {str(e)}")
            raise

    def link_global_articles_to_feed(
        self,
        user_id: str,
        feed_id: int,
        feed_url: str,
        limit: Optional[int] = None,
    ) -> int:
        """把 global_articles 中匹配 feed_url 的行物化到 articles，并建立 user_article_refs。

        从 create_user_feed 中拆出来，方便由 BackgroundTasks 调度。返回链接的 ref 行数。
        在后台线程调用时务必用 with db_manager.connection_scope(): 包住，确保连接被
        归还到连接池（HTTP 中间件只负责请求线程，不负责后台任务）。
        """
        try:
            with self.pg_conn.cursor() as cur:
                source_type_id = self._ensure_source_type("rss")

                limit_clause = ""
                params_suffix = (feed_url,)
                if limit is not None:
                    limit_clause = """
                    ORDER BY COALESCE(ga.published_at, ga.first_seen_at) DESC
                    LIMIT %s
                    """
                    params_suffix = (feed_url, limit)

                # Cross-user sharing: 为已存在的 global_articles 生成兼容层 legacy 行
                cur.execute(
                    f"""
                    INSERT INTO articles (
                        feed_id, source_type_id, title, url, published_at, summary, content,
                        author, source, content_hash, language, word_count,
                        reading_time, cover_image
                    )
                    SELECT
                        %s, %s, ga.title, ga.url, ga.published_at, ga.summary, ga.content,
                        ga.author, ga.source_feed_url, ga.content_hash, ga.language,
                        ga.word_count, ga.reading_time, ga.cover_image
                    FROM global_articles ga
                    WHERE ga.source_feed_url = %s
                    {limit_clause}
                    ON CONFLICT (feed_id, url) DO UPDATE SET
                        title = EXCLUDED.title,
                        published_at = EXCLUDED.published_at,
                        summary = EXCLUDED.summary,
                        content = EXCLUDED.content,
                        author = EXCLUDED.author,
                        source = EXCLUDED.source,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (feed_id, source_type_id, *params_suffix)
                )

                # 建立 user_article_refs（包含 legacy_article_id，确保下游 API 兼容）
                cur.execute(
                    f"""
                    INSERT INTO user_article_refs (user_id, global_article_id, legacy_article_id, feed_id, fetched_at)
                    SELECT %s, ga.id, a.id, %s, COALESCE(ga.published_at, CURRENT_TIMESTAMP)
                    FROM global_articles ga
                    JOIN articles a ON a.url = ga.url AND a.feed_id = %s
                    WHERE ga.source_feed_url = %s
                    {limit_clause}
                    ON CONFLICT (user_id, global_article_id, feed_id) DO UPDATE SET
                        legacy_article_id = EXCLUDED.legacy_article_id,
                        fetched_at = EXCLUDED.fetched_at
                    """,
                    (user_id, feed_id, feed_id, *params_suffix)
                )
                linked_count = cur.rowcount
                self.pg_conn.commit()
                if linked_count > 0:
                    self.logger.info(
                        f"为订阅源链接全局文章: feed_id={feed_id}, feed_url={feed_url}, "
                        f"user={user_id}, linked={linked_count}"
                    )
                return linked_count
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(
                f"link_global_articles_to_feed 失败: feed_id={feed_id}, feed_url={feed_url}, "
                f"user={user_id}, err={str(e)}"
            )
            return 0

    @_with_db_scope
    def activate_starter_pack_feeds(
        self,
        user_id: str,
        feeds: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """创建 starter pack 订阅，并在返回前同步链接少量已有全局文章。

        Onboarding 首屏需要确定性地看到文章列表，但全量链接历史文章会阻塞几十秒。
        这里仅同步每个源最近一小批文章，完整历史由 HTTP 层的 BackgroundTasks 补齐。
        """
        initial_link_limit = 20
        activated_feeds = []
        created_count = 0
        existing_count = 0
        total_linked_count = 0

        for feed in feeds:
            feed_name = feed["feed_name"]
            feed_url = feed["feed_url"]
            feed_id, is_existing = self.create_user_feed_minimal(user_id, feed_name, feed_url)
            linked_count = self.link_global_articles_to_feed(
                user_id,
                feed_id,
                feed_url,
                limit=initial_link_limit,
            )

            if is_existing:
                existing_count += 1
            else:
                created_count += 1
            total_linked_count += linked_count
            activated_feeds.append({
                "feed_id": feed_id,
                "feed_name": feed_name,
                "feed_url": feed_url,
                "is_existing": is_existing,
                "linked_count": linked_count,
            })

        return {
            "feeds": activated_feeds,
            "created_count": created_count,
            "existing_count": existing_count,
            "linked_count": total_linked_count,
            "initial_link_limit": initial_link_limit,
            "needs_background_backfill": True,
        }

    def copy_podcast_to_user(
        self,
        source_user_id: str,
        target_user_id: str,
        language: str = "zh"
    ) -> Optional[int]:
        """
        将体验用户的最新已生成播客复制给新用户，作为 onboarding cache。
        同时复制 podcast_articles 和 podcast_scripts，保证 detail 页和 RAG 完整。
        返回新播客的 id；若无可用播客则返回 None。
        """
        try:
            with self.pg_conn.cursor() as cur:
                # 1. 查找 source 用户最新已完成播客
                cur.execute(
                    """
                    SELECT id
                    FROM podcasts
                    WHERE user_id = %s AND generation_status = 'completed'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (source_user_id,)
                )
                row = cur.fetchone()
                if not row:
                    self.logger.warning(
                        f"无可用 experience podcast: source={source_user_id}, lang={language}"
                    )
                    return None
                source_podcast_id = row[0]

                # 2. 复制 podcasts 行
                cur.execute(
                    """
                    INSERT INTO podcasts (
                        user_id, title, description, style, duration,
                        cover_image, generation_status, generation_started_at,
                        generation_completed_at, generation_error, audio_url,
                        audio_cache_key, play_count, source, created_at, updated_at
                    )
                    SELECT
                        %s, title, description, style, duration,
                        cover_image, 'completed', generation_started_at,
                        generation_completed_at, generation_error, audio_url,
                        NULL, 0, 'onboarding_cache', NOW(), NOW()
                    FROM podcasts
                    WHERE id = %s
                    RETURNING id
                    """,
                    (target_user_id, source_podcast_id)
                )
                new_podcast_id = cur.fetchone()[0]

                # 3. 复制 podcast_articles
                cur.execute(
                    """
                    INSERT INTO podcast_articles (
                        podcast_id, article_id, global_article_id,
                        sequence_order, importance_score, start_time, end_time
                    )
                    SELECT
                        %s, article_id, global_article_id,
                        sequence_order, importance_score, start_time, end_time
                    FROM podcast_articles
                    WHERE podcast_id = %s
                    """,
                    (new_podcast_id, source_podcast_id)
                )

                # 4. 复制 podcast_scripts
                cur.execute(
                    """
                    INSERT INTO podcast_scripts (
                        podcast_id, full_script, script_version,
                        total_segments, estimated_duration, generated_by,
                        generation_prompt, suggested_questions
                    )
                    SELECT
                        %s, full_script, script_version,
                        total_segments, estimated_duration, generated_by,
                        generation_prompt, suggested_questions
                    FROM podcast_scripts
                    WHERE podcast_id = %s
                    """,
                    (new_podcast_id, source_podcast_id)
                )

                self.pg_conn.commit()
                self.logger.info(
                    f"Copied podcast {source_podcast_id} -> {new_podcast_id} "
                    f"from {source_user_id} to {target_user_id}"
                )
                return new_podcast_id

        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"copy_podcast_to_user 失败: {str(e)}", exc_info=True)
            return None

    def get_starter_pack_feeds(self, language: str = "zh", min_valid_count: int = 4) -> List[Dict[str, Any]]:
        """
        获取 onboarding starter pack feeds。
        返回人工筛选的固定列表，不依赖 feed_validation 动态查询。
        """
        return get_starter_pack_feed_defs(language)

    def upsert_feed_validation(
        self,
        feed_url: str,
        feed_name: str,
        language: str,
        is_valid: bool,
        article_count: int,
        avg_content_length: int,
        last_article_at: Optional[Any] = None,
        validation_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        插入或更新 feed_validation 记录。
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feed_validation (
                        feed_url, feed_name, language, is_valid,
                        article_count, avg_content_length, last_article_at,
                        last_validated_at, validation_metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                    ON CONFLICT (feed_url) DO UPDATE SET
                        feed_name = EXCLUDED.feed_name,
                        language = EXCLUDED.language,
                        is_valid = EXCLUDED.is_valid,
                        article_count = EXCLUDED.article_count,
                        avg_content_length = EXCLUDED.avg_content_length,
                        last_article_at = EXCLUDED.last_article_at,
                        last_validated_at = NOW(),
                        validation_metadata = EXCLUDED.validation_metadata
                    """,
                    (
                        feed_url, feed_name, language, is_valid,
                        article_count, avg_content_length,
                        last_article_at,
                        Json(validation_metadata or {})
                    )
                )
                self.pg_conn.commit()
                return True
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"upsert_feed_validation 失败: {e}", exc_info=True)
            return False

    def get_tts_cache_entry(self, global_article_id: int, voice: str, engine: str) -> Optional[Dict[str, Any]]:
        """通过 global_article_id 查询 TTS 缓存元数据，实现跨用户复用"""
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT cache_key, file_path, file_size, duration_seconds, format
                    FROM tts_cache
                    WHERE global_article_id = %s AND voice = %s AND engine = %s
                    """,
                    (global_article_id, voice, engine)
                )
                row = cur.fetchone()
                if row:
                    # 更新访问统计
                    cur.execute(
                        """
                        UPDATE tts_cache
                        SET last_accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1
                        WHERE global_article_id = %s AND voice = %s AND engine = %s
                        """,
                        (global_article_id, voice, engine)
                    )
                    self.pg_conn.commit()
                    return dict(row)
                return None
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"查询 TTS 缓存失败: {e}", exc_info=True)
            return None

    def upsert_tts_cache_entry(
        self,
        global_article_id: int,
        voice: str,
        engine: str,
        cache_key: str,
        file_path: str,
        file_size: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        format: str = "mp3"
    ) -> None:
        """写入或更新 TTS 缓存元数据"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tts_cache
                        (global_article_id, voice, engine, cache_key, file_path, file_size, duration_seconds, format)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (global_article_id, voice, engine)
                    DO UPDATE SET
                        cache_key = EXCLUDED.cache_key,
                        file_path = EXCLUDED.file_path,
                        file_size = EXCLUDED.file_size,
                        duration_seconds = EXCLUDED.duration_seconds,
                        format = EXCLUDED.format,
                        last_accessed_at = CURRENT_TIMESTAMP,
                        access_count = tts_cache.access_count + 1
                    """,
                    (global_article_id, voice, engine, cache_key, file_path, file_size, duration_seconds, format)
                )
                self.pg_conn.commit()
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"写入 TTS 缓存失败: {e}", exc_info=True)

    @_with_db_scope
    def get_user_feeds(self, user_id: str) -> list:
        """获取用户所有订阅源"""
        try:
            # 优先从缓存中读取，减少数据库查询
            now = time.time()
            cached = self._user_feeds_cache.get(user_id)
            if cached:
                ts, feeds = cached
                if now - ts < self._user_feeds_cache_ttl:
                    return feeds

            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, feed_name, feed_url, is_active, created_at, updated_at
                    FROM user_feeds
                    WHERE user_id = %s AND is_active = true
                    ORDER BY created_at DESC
                    """,
                    (user_id,)
                )
                feeds = [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
                self.logger.info(f"查询用户 {user_id} 的订阅源，共 {len(feeds)} 条")
                # 更新缓存
                self._user_feeds_cache[user_id] = (now, feeds)
            # 显式结束事务，避免连接以 idle in transaction 状态滞留（psycopg2 默认非 autocommit）
            self.pg_conn.commit()
            return feeds
        except Exception as e:
            try:
                self.pg_conn.rollback()
            except Exception:
                pass
            self.logger.error(f"查询用户订阅源失败: {str(e)}")
            return []

    def get_active_user_ids(self) -> list:
        """
        获取所有有订阅源且启用自动刷新的活跃用户ID列表
        Week 5 Phase 3: 支持多用户定时抓取 + auto_refresh_enabled 过滤
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT uf.user_id
                    FROM user_feeds uf
                    INNER JOIN users u ON uf.user_id = u.id
                    WHERE u.auto_refresh_enabled = TRUE
                    ORDER BY uf.user_id
                    """
                )
                user_ids = [row[0] for row in cur.fetchall()]
                self.logger.info(f"查询启用自动刷新的活跃用户，共 {len(user_ids)} 个")
                return user_ids
        except Exception as e:
            self.logger.error(f"查询活跃用户失败: {str(e)}")
            return []

    def get_podcast_enabled_user_ids(self) -> list:
        """
        获取所有启用自动播客生成的用户ID列表
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT id
                    FROM users
                    WHERE auto_podcast_enabled = TRUE
                    ORDER BY id
                    """
                )
                user_ids = [row[0] for row in cur.fetchall()]
                self.logger.info(f"查询启用自动播客的用户，共 {len(user_ids)} 个")
                return user_ids
        except Exception as e:
            self.logger.error(f"查询自动播客用户失败: {str(e)}")
            return []

    def get_podcast_enabled_users(self) -> list:
        """
        获取所有启用自动播客生成的用户 (id, preferred_language) 元组列表

        Returns:
            List[Tuple[str, Optional[str]]]: 形如 [('test-user', 'en'), ...]
            preferred_language 可能为 None / 空串，调用方需自行做归一化。
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, preferred_language
                    FROM users
                    WHERE auto_podcast_enabled = TRUE
                    ORDER BY id
                    """
                )
                users = [(row[0], row[1]) for row in cur.fetchall()]
                self.logger.info(
                    f"查询启用自动播客的用户（含语言偏好），共 {len(users)} 个"
                )
                return users
        except Exception as e:
            self.logger.error(f"查询自动播客用户（含语言偏好）失败: {str(e)}")
            return []

    @_with_db_scope
    def update_user_feed(self, feed_id: int, feed_name: str, feed_url: str, user_id: str = None) -> bool:
        """更新订阅源信息"""
        try:
            with self.pg_conn.cursor() as cur:
                if user_id:
                    cur.execute(
                        """
                        UPDATE user_feeds SET feed_name = %s, feed_url = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s
                        """,
                        (feed_name, feed_url, feed_id, user_id)
                    )
                else:
                    cur.execute(
                        """
                        UPDATE user_feeds SET feed_name = %s, feed_url = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s
                        """,
                        (feed_name, feed_url, feed_id)
                    )
                self.pg_conn.commit()
                updated = cur.rowcount > 0
                self.logger.info(f"更新订阅源 {feed_id}: {feed_name} -> {feed_url}, 成功: {updated}")
                if updated:
                    # 订阅源更新后清空缓存，确保后续读取到最新数据
                    self._user_feeds_cache.clear()
                return updated
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"更新用户订阅源失败: {str(e)}")
            return False

    @_with_db_scope
    def delete_user_feed(self, feed_id: int, user_id: str = None) -> bool:
        """删除订阅源"""
        try:
            with self.pg_conn.cursor() as cur:
                # 删除相关的文章（通过 feed ownership 限定）
                if user_id:
                    cur.execute(
                        "DELETE FROM articles WHERE feed_id = %s AND feed_id IN (SELECT id FROM user_feeds WHERE id = %s AND user_id = %s)",
                        (feed_id, feed_id, user_id)
                    )
                else:
                    cur.execute("DELETE FROM articles WHERE feed_id = %s", (feed_id,))
                articles_deleted = cur.rowcount

                # 删除用户文章关联（cross-user sharing 新架构）
                if user_id:
                    cur.execute(
                        "DELETE FROM user_article_refs WHERE feed_id = %s AND user_id = %s",
                        (feed_id, user_id)
                    )
                else:
                    cur.execute("DELETE FROM user_article_refs WHERE feed_id = %s", (feed_id,))
                refs_deleted = cur.rowcount

                # 删除订阅源
                if user_id:
                    cur.execute("DELETE FROM user_feeds WHERE id = %s AND user_id = %s", (feed_id, user_id))
                else:
                    cur.execute("DELETE FROM user_feeds WHERE id = %s", (feed_id,))
                feeds_deleted = cur.rowcount

                self.pg_conn.commit()
                self.logger.info(f"删除订阅源 {feed_id}: 删除了 {feeds_deleted} 个订阅源、{articles_deleted} 篇兼容文章和 {refs_deleted} 条关联")
                if feeds_deleted > 0:
                    # 订阅源删除后清空缓存
                    self._user_feeds_cache.clear()
                return feeds_deleted > 0
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"删除用户订阅源失败: {str(e)}")
            return False

    def deactivate_user_feed(self, feed_id: int, user_id: str = None) -> bool:
        """停用订阅源，保留历史文章与播客引用。"""
        try:
            with self.pg_conn.cursor() as cur:
                if user_id:
                    cur.execute(
                        """
                        UPDATE user_feeds
                        SET is_active = false, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND user_id = %s
                        """,
                        (feed_id, user_id)
                    )
                else:
                    cur.execute(
                        """
                        UPDATE user_feeds
                        SET is_active = false, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (feed_id,)
                    )
                updated = cur.rowcount > 0
                self.pg_conn.commit()
                if updated:
                    self._user_feeds_cache.clear()
                return updated
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"停用订阅源失败: {str(e)}")
            return False

    # ================== 用户认证相关方法 (Week 3) ==================

    def create_user(self, username: str, email: str, password_hash: str,
                   full_name: str = None, is_superuser: bool = False,
                   preferred_language: str = 'en', auth_provider: str = 'password') -> str:
        """
        创建新用户

        Args:
            username: 用户名（唯一）
            email: 邮箱（唯一）
            password_hash: 密码哈希
            full_name: 全名（可选）
            is_superuser: 是否为超级用户
            preferred_language: 偏好语言（默认 'zh'）
            auth_provider: 认证来源（默认 'password'）

        Returns:
            str: 用户ID

        Raises:
            Exception: 用户名或邮箱已存在
        """
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 生成用户ID (使用username作为ID保持向后兼容)
                user_id = username

                cur.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, full_name, is_superuser, is_active, preferred_language, auth_provider)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, username, email, password_hash, full_name, is_superuser, True, preferred_language, auth_provider)
                )
                new_user_id = cur.fetchone()['id']
                self.pg_conn.commit()
                self.logger.info(f"成功创建用户: {username} ({email}), language={preferred_language}")
                return new_user_id
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"创建用户失败: {str(e)}")
            raise

    def get_user_by_username(self, username: str) -> Dict[str, Any]:
        """
        根据用户名获取用户信息

        Args:
            username: 用户名

        Returns:
            dict: 用户信息，如果不存在返回None
        """
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, email, password_hash, full_name, avatar_url,
                           is_active, is_superuser, preferred_language, tts_voice_zh, tts_voice_en, auth_provider, created_at, updated_at
                    FROM users
                    WHERE username = %s
                    """,
                    (username,)
                )
                user = cur.fetchone()
                return dict(user) if user else None
        except Exception as e:
            self.logger.error(f"查询用户失败: {str(e)}")
            return None

    def get_user_by_email(self, email: str) -> Dict[str, Any]:
        """
        根据邮箱获取用户信息

        Args:
            email: 邮箱

        Returns:
            dict: 用户信息，如果不存在返回None
        """
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, email, password_hash, full_name, avatar_url,
                           is_active, is_superuser, preferred_language, tts_voice_zh, tts_voice_en, auth_provider, created_at, updated_at
                    FROM users
                    WHERE email = %s
                    """,
                    (email,)
                )
                user = cur.fetchone()
                return dict(user) if user else None
        except Exception as e:
            self.logger.error(f"查询用户失败: {str(e)}")
            return None

    @_with_db_scope
    def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        """
        根据ID获取用户信息

        Args:
            user_id: 用户ID

        Returns:
            dict: 用户信息（不含password_hash），如果不存在返回None
        """
        try:
            with self.pg_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, email, full_name, avatar_url,
                           is_active, is_superuser, preferred_language, auto_podcast_enabled, tts_voice_zh, tts_voice_en, auth_provider, created_at, updated_at
                    FROM users
                    WHERE id = %s
                    """,
                    (user_id,)
                )
                user = cur.fetchone()
                user_dict = dict(user) if user else None
            # 显式结束事务，避免连接以 idle in transaction 状态滞留（每个鉴权请求都会调用，热路径）
            self.pg_conn.commit()
            return user_dict
        except Exception as e:
            try:
                self.pg_conn.rollback()
            except Exception:
                pass
            self.logger.error(f"查询用户失败: {str(e)}")
            return None

    def update_user(self, user_id: str, **updates) -> bool:
        """
        更新用户信息

        Args:
            user_id: 用户ID
            **updates: 要更新的字段（email, full_name, avatar_url等）

        Returns:
            bool: 是否更新成功
        """
        try:
            # 过滤允许更新的字段
            allowed_fields = ['email', 'full_name', 'avatar_url', 'is_active', 'preferred_language', 'auto_podcast_enabled', 'tts_voice_zh', 'tts_voice_en']
            filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

            if not filtered_updates:
                self.logger.warning("没有有效的字段需要更新")
                return False

            # 构建SET子句
            set_clause = ", ".join([f"{k} = %s" for k in filtered_updates.keys()])
            values = list(filtered_updates.values())
            values.append(user_id)

            with self.pg_conn.cursor() as cur:
                cur.execute(
                    f"UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    values
                )
                self.pg_conn.commit()
                updated = cur.rowcount > 0
                if updated:
                    self.logger.info(f"更新用户 {user_id} 信息成功")
                return updated
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"更新用户失败: {str(e)}")
            return False

    def update_user_password(self, user_id: str, new_password_hash: str) -> bool:
        """
        更新用户密码

        Args:
            user_id: 用户ID
            new_password_hash: 新密码哈希

        Returns:
            bool: 是否更新成功
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (new_password_hash, user_id)
                )
                self.pg_conn.commit()
                updated = cur.rowcount > 0
                if updated:
                    self.logger.info(f"更新用户 {user_id} 密码成功")
                return updated
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"更新用户密码失败: {str(e)}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """
        删除用户（会级联删除用户的所有订阅源和文章）

        Args:
            user_id: 用户ID

        Returns:
            bool: 是否删除成功
        """
        try:
            with self.pg_conn.cursor() as cur:
                # 显式删除无外键约束的关联表数据
                cur.execute("DELETE FROM user_saved_articles WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_reading_history WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                self.pg_conn.commit()
                deleted = cur.rowcount > 0
                if deleted:
                    self.logger.info(f"删除用户 {user_id} 成功")
                return deleted
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"删除用户失败: {str(e)}")
            return False

    # ================== 刷新日志 tracking ==================

    def start_feed_update_log(self, feed_id: int) -> int:
        """创建一条运行中的刷新日志，返回log id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feed_update_logs (feed_id, status, started_at)
                    VALUES (%s, 'running', CURRENT_TIMESTAMP)
                    RETURNING id
                    """,
                    (feed_id,)
                )
                log_id = cur.fetchone()[0]
                self.pg_conn.commit()
                return log_id
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.warning(f"创建刷新日志失败: {e}")
            return -1

    def complete_feed_update_log(self, log_id: int, status: str,
                                  articles_fetched: int = 0,
                                  stored_count: int = 0,
                                  failed_count: int = 0,
                                  error_message: str = None) -> None:
        """完成一条刷新日志。log_id 若无效则忽略。"""
        if log_id is None or log_id < 0:
            return
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE feed_update_logs
                    SET status = %s,
                        completed_at = CURRENT_TIMESTAMP,
                        articles_fetched = %s,
                        stored_count = %s,
                        failed_count = %s,
                        error_message = %s
                    WHERE id = %s
                    """,
                    (status, articles_fetched, stored_count, failed_count, error_message, log_id)
                )
                self.pg_conn.commit()
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.warning(f"更新刷新日志失败: {e}")

    @_with_db_scope
    def get_latest_feed_update_status_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户所有订阅源的刷新状态（包含最近一次尝试与最近一次成功时间）"""
        try:
            with self.pg_conn.cursor() as cur:
                # 如果日志表不存在，直接返回空，避免污染连接事务状态
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables WHERE table_name = 'feed_update_logs'
                    )
                    """
                )
                exists = cur.fetchone()[0]
                if not exists:
                    return []

                cur.execute(
                    """
                    WITH last_try AS (
                        SELECT DISTINCT ON (feed_id)
                            feed_id,
                            status,
                            started_at,
                            completed_at,
                            articles_fetched,
                            stored_count,
                            failed_count,
                            error_message
                        FROM feed_update_logs
                        ORDER BY feed_id, started_at DESC NULLS LAST
                    ), last_success AS (
                        SELECT feed_id, MAX(completed_at) AS last_success_at
                        FROM feed_update_logs
                        WHERE status = 'success' AND articles_fetched > 0
                        GROUP BY feed_id
                    )
                    SELECT
                        f.id AS feed_id,
                        f.feed_name,
                        f.feed_url,
                        lt.status,
                        lt.started_at,
                        lt.completed_at,
                        lt.articles_fetched,
                        lt.stored_count,
                        lt.failed_count,
                        COALESCE(lt.error_message, '') AS error_message,
                        ls.last_success_at,
                        CASE WHEN ls.last_success_at IS NULL THEN TRUE ELSE FALSE END AS never_success
                    FROM user_feeds f
                    LEFT JOIN last_try lt ON lt.feed_id = f.id
                    LEFT JOIN last_success ls ON ls.feed_id = f.id
                    WHERE f.user_id = %s
                    ORDER BY f.created_at DESC
                    """,
                    (user_id,)
                )
                columns = [d[0] for d in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            # 关键：ROLLBACK 清除连接的 aborted 状态，避免影响后续查询
            try:
                self.pg_conn.rollback()
            except Exception:
                pass
            self.logger.error(f"查询刷新状态失败: {e}")
            return []

    def user_exists(self, username: str = None, email: str = None) -> bool:
        """
        检查用户是否存在

        Args:
            username: 用户名（可选）
            email: 邮箱（可选）

        Returns:
            bool: 用户是否存在
        """
        try:
            with self.pg_conn.cursor() as cur:
                if username:
                    cur.execute("SELECT 1 FROM users WHERE username = %s LIMIT 1", (username,))
                elif email:
                    cur.execute("SELECT 1 FROM users WHERE email = %s LIMIT 1", (email,))
                else:
                    return False
                return cur.fetchone() is not None
        except Exception as e:
            self.logger.error(f"检查用户是否存在失败: {str(e)}")
            return False

    @_with_db_scope
    def get_user_articles(self, user_id: str, feed_id: int = None, source: str = None,
                         only_summary: bool = False, order_by: str = 'updated_at',
                         desc: bool = True, limit: int = 10, offset: int = 0,
                         read_filter: str = None, language: str = 'en') -> List[Dict[str, Any]]:
        """
        获取用户订阅源的文章列表（Phase 2：仅从 user_article_refs + global_articles 查询）

        Args:
            user_id: 用户ID
            feed_id: 指定订阅源ID（可选）
            source: 来源过滤（可选）
            only_summary: 是否只返回摘要
            order_by: 排序字段
            desc: 是否倒序
            limit: 返回数量
            offset: 偏移量

        Returns:
            list: 文章列表
        """
        try:
            with self.pg_conn.cursor() as cur:
                # 优先使用语言化摘要缓存；未命中时回退到 global_articles.summary（通常是 RSS 原始摘要）
                # 先获取用户的所有订阅源ID
                cur.execute(
                    "SELECT id FROM user_feeds WHERE user_id = %s",
                    (user_id,)
                )
                user_feed_ids = [row[0] for row in cur.fetchall()]

                if not user_feed_ids:
                    return []

                restrict_to_user_feeds = not (read_filter == "read" and feed_id is None)

                content_field = "" if only_summary else ", ga.content"
                fields = (
                    "uar.global_article_id AS id, ga.title, COALESCE(as_lang.summary, ga.summary) AS summary, ga.url, "
                    "ga.published_at, ga.author, ga.source_feed_url AS source, ga.language, "
                    "uar.fetched_at AS updated_at"
                    f"{content_field}, "
                    "COALESCE(urh.read_at, (SELECT MAX(urh2.read_at) FROM user_reading_history urh2 "
                    "WHERE urh2.user_id = %s AND urh2.is_read = true AND urh2.global_article_id = ga.id)) AS read_at, "
                    "COALESCE(urh.is_read, EXISTS(SELECT 1 FROM user_reading_history urh3 "
                    "WHERE urh3.user_id = %s AND urh3.is_read = true AND urh3.global_article_id = ga.id)) AS is_read"
                )

                cte = "WITH user_feed_ids AS (SELECT id FROM user_feeds WHERE user_id = %s) "

                query = (
                    f"SELECT {fields} FROM user_article_refs uar "
                    "JOIN global_articles ga ON ga.id = uar.global_article_id "
                    "LEFT JOIN article_summaries as_lang ON as_lang.global_article_id = ga.id AND as_lang.language = %s "
                    "LEFT JOIN user_reading_history urh ON urh.global_article_id = ga.id AND urh.user_id = %s "
                    "WHERE uar.user_id = %s"
                )
                if restrict_to_user_feeds:
                    query += " AND uar.feed_id IN (SELECT id FROM user_feed_ids)"
                if feed_id is not None:
                    query += " AND uar.feed_id = %s"
                if source:
                    query += " AND ga.source_feed_url = %s"
                if read_filter == "read":
                    query += " AND urh.is_read = true"
                elif read_filter == "unread":
                    query += " AND (urh.is_read = false OR urh.is_read IS NULL)"
                    query += (
                        " AND NOT EXISTS (SELECT 1 FROM user_reading_history urh2 "
                        "WHERE urh2.user_id = %s AND urh2.is_read = true AND urh2.global_article_id = ga.id)"
                    )

                ORDER_FIELD_MAP = {
                    "updated_at": "uar.fetched_at",
                    "published_at": "ga.published_at",
                    "title": "ga.title",
                    "created_at": "ga.first_seen_at",
                }
                if order_by not in ORDER_FIELD_MAP:
                    order_by = "updated_at"
                sort_column = ORDER_FIELD_MAP[order_by]
                if read_filter in ("read", "unread"):
                    sort_dir = 'DESC' if desc else 'ASC'
                    query += (
                        f" ORDER BY COALESCE(read_at, {sort_column}) {sort_dir} "
                        f"LIMIT %s OFFSET %s"
                    )
                else:
                    query += (
                        f" ORDER BY {sort_column} {'DESC' if desc else 'ASC'} "
                        f"LIMIT %s OFFSET %s"
                    )

                params = [
                    user_id,   # CTE user_feed_ids
                    user_id,   # read_at subquery
                    user_id,   # is_read subquery
                    language,  # article_summaries language
                    user_id,   # urh LEFT JOIN
                    user_id,   # WHERE uar.user_id
                ]
                if feed_id is not None:
                    params.append(feed_id)
                if source:
                    params.append(source)
                if read_filter == "unread":
                    params.append(user_id)

                params.extend([limit, offset])

                cur.execute(cte + query, params)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
            # 显式结束事务，避免连接以 idle in transaction 状态滞留（feed 列表是高频热路径）
            self.pg_conn.commit()
            return results
        except Exception as e:
            try:
                self.pg_conn.rollback()
            except Exception:
                pass
            self.logger.error(f"获取用户文章失败: {str(e)}")
            return []

    @_with_db_scope
    def get_user_articles_stats(
        self,
        user_id: str,
        feed_id: int = None,
        source: str = None,
        read_filter: str = None,
        language: str = 'en',
    ) -> Dict[str, int]:
        """
        获取用户文章列表的稳定统计值（按去重后的全局文章维度）

        返回：
            {
                "total": 文章总数,
                "playable_total": 可播放文章总数
            }
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM user_feeds WHERE user_id = %s",
                    (user_id,)
                )
                user_feed_ids = [row[0] for row in cur.fetchall()]

                if not user_feed_ids:
                    return {"total": 0, "playable_total": 0}

                restrict_to_user_feeds = not (read_filter == "read" and feed_id is None)

                cte = "WITH user_feed_ids AS (SELECT id FROM user_feeds WHERE user_id = %s) "
                query = (
                    "SELECT "
                    "COUNT(DISTINCT ga.id) AS total, "
                    "COUNT(DISTINCT CASE "
                    "WHEN LENGTH(TRIM(COALESCE(as_lang.summary, ga.summary, ga.content, ''))) > 0 "
                    "THEN ga.id END) AS playable_total "
                    "FROM user_article_refs uar "
                    "JOIN global_articles ga ON ga.id = uar.global_article_id "
                    "LEFT JOIN article_summaries as_lang ON as_lang.global_article_id = ga.id AND as_lang.language = %s "
                    "LEFT JOIN user_reading_history urh ON urh.global_article_id = ga.id AND urh.user_id = %s "
                    "WHERE uar.user_id = %s"
                )

                if restrict_to_user_feeds:
                    query += " AND uar.feed_id IN (SELECT id FROM user_feed_ids)"
                if feed_id is not None:
                    query += " AND uar.feed_id = %s"
                if source:
                    query += " AND ga.source_feed_url = %s"
                if read_filter == "read":
                    query += " AND urh.is_read = true"
                elif read_filter == "unread":
                    query += " AND (urh.is_read = false OR urh.is_read IS NULL)"
                    query += (
                        " AND NOT EXISTS (SELECT 1 FROM user_reading_history urh2 "
                        "WHERE urh2.user_id = %s AND urh2.is_read = true AND urh2.global_article_id = ga.id)"
                    )

                params = [
                    user_id,   # CTE user_feed_ids
                    language,  # article_summaries language
                    user_id,   # urh LEFT JOIN
                    user_id,   # WHERE uar.user_id
                ]
                if feed_id is not None:
                    params.append(feed_id)
                if source:
                    params.append(source)
                if read_filter == "unread":
                    params.append(user_id)

                cur.execute(cte + query, params)
                row = cur.fetchone()
                if not row:
                    return {"total": 0, "playable_total": 0}

                total = int(row[0] or 0)
                playable_total = int(row[1] or 0)
                return {"total": total, "playable_total": playable_total}
        except Exception as e:
            self.logger.error(f"获取用户文章统计失败: {str(e)}")
            return {"total": 0, "playable_total": 0}

    @_with_db_scope
    def get_user_feed_overview_stats(
        self,
        user_id: str,
        feed_id: int = None,
        source: str = None,
        language: str = 'en',
    ) -> Dict[str, int]:
        """
        获取首页概览统计。

        当前产品语义：按 Asia/Shanghai 当日、用户 feed 中新更新的文章数。
        所有已入库文章都视为可收听，前端用单个数字展示 "new articles ready to listen"。
        """
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM user_feeds WHERE user_id = %s",
                    (user_id,)
                )
                user_feed_ids = [row[0] for row in cur.fetchall()]

                if not user_feed_ids:
                    return {"today_ready_count": 0}

                cte = "WITH user_feed_ids AS (SELECT id FROM user_feeds WHERE user_id = %s) "
                query = (
                    "SELECT COUNT(DISTINCT ga.id) AS today_ready_count "
                    "FROM user_article_refs uar "
                    "JOIN global_articles ga ON ga.id = uar.global_article_id "
                    "WHERE uar.user_id = %s "
                    "AND uar.feed_id IN (SELECT id FROM user_feed_ids) "
                    "AND DATE(uar.fetched_at AT TIME ZONE 'Asia/Shanghai') = DATE(NOW() AT TIME ZONE 'Asia/Shanghai')"
                )

                params = [
                    user_id,   # CTE user_feed_ids
                    user_id,   # WHERE uar.user_id
                ]
                if feed_id is not None:
                    query += " AND uar.feed_id = %s"
                    params.append(feed_id)
                if source:
                    query += " AND ga.source_feed_url = %s"
                    params.append(source)

                cur.execute(cte + query, params)
                row = cur.fetchone()
                return {"today_ready_count": int((row[0] if row else 0) or 0)}
        except Exception as e:
            self.logger.error(f"获取首页概览统计失败: {str(e)}")
            return {"today_ready_count": 0}

    def save_user_feedback(
        self, user_id: str, message: str, attach_logs: bool = False,
        frontend_logs: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[int]:
        """保存用户反馈到数据库，返回 feedback id"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_feedback (user_id, message, attach_logs, frontend_logs, status)
                    VALUES (%s, %s, %s, COALESCE(%s, '[]'::jsonb), 'open')
                    RETURNING id
                    """,
                    (user_id, message, attach_logs, Json(frontend_logs) if frontend_logs else None)
                )
                result = cur.fetchone()
                self.pg_conn.commit()
                return result[0] if result else None
        except Exception as e:
            self.pg_conn.rollback()
            self.logger.error(f"保存用户反馈失败: {e}")
            return None

    def get_user_feedback(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """获取指定用户的反馈列表（管理员可用于查看所有反馈）"""
        try:
            with self.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, message, attach_logs, frontend_logs, status,
                           created_at, updated_at
                    FROM user_feedback
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset)
                )
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"获取用户反馈失败: {e}")
            return []
