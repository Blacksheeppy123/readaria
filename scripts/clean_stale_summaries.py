#!/usr/bin/env python3
"""
Readaria 存量脏摘要缓存清理脚本

背景：修复摘要语言 bug 之前，article_summaries 的缓存键 language 是用户 UI
偏好语言而非摘要实际语言，个别条目可能出现"缓存键与摘要语言不一致"的脏数据。

本脚本扫描 article_summaries，用与运行时相同的检测逻辑（backend/utils/
language_detect.py）校验每条摘要的语言与缓存键是否一致，删除不一致的条目。
被删除的条目会在下次订阅源刷新时按内容语言自动重新生成（运行时自愈逻辑）。

使用方式:
    python3 scripts/clean_stale_summaries.py            # 只扫描并报告（dry-run）
    python3 scripts/clean_stale_summaries.py --delete   # 删除不一致的条目

Crontab 配置（可选，每周执行一次；路径按实际安装目录调整）:
    0 5 * * 1 /path/to/readaria/venv/bin/python /path/to/readaria/scripts/clean_stale_summaries.py --delete >> /path/to/readaria/logs/cleanup.log 2>&1
"""

import argparse
import logging
import os
import sys

# 允许从仓库任意位置运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 扫描批次大小，避免一次性加载全表
BATCH_SIZE = 500


def iter_summary_batches(cur, last_id: int):
    cur.execute(
        """
        SELECT id, global_article_id, language, summary
        FROM article_summaries
        WHERE id > %s
        ORDER BY id
        LIMIT %s
        """,
        (last_id, BATCH_SIZE),
    )
    return cur.fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description="清理语言与缓存键不一致的存量摘要缓存")
    parser.add_argument("--delete", action="store_true", help="实际删除不一致条目（默认仅扫描报告）")
    args = parser.parse_args()

    from core.config.settings import settings
    from backend.storage.database import DatabaseManager
    from backend.utils.language_detect import summary_matches_language

    db_manager = DatabaseManager(pg_config=settings.postgres_config)

    stale_ids = []
    scanned = 0
    last_id = 0

    with db_manager.pg_conn.cursor() as cur:
        while True:
            rows = iter_summary_batches(cur, last_id)
            if not rows:
                break
            for row_id, global_article_id, language, summary in rows:
                scanned += 1
                if not summary_matches_language(summary, language):
                    stale_ids.append(row_id)
                    logger.warning(
                        f"脏缓存: id={row_id}, global_article_id={global_article_id}, "
                        f"language='{language}', summary={str(summary)[:40]!r}..."
                    )
            last_id = rows[-1][0]
        db_manager.pg_conn.rollback()  # 扫描只读，不持有事务

    logger.info(f"扫描完成: 共 {scanned} 条，发现 {len(stale_ids)} 条语言不一致")

    if not stale_ids:
        return 0

    if not args.delete:
        logger.info("dry-run 模式：未删除任何条目。确认后请加 --delete 重新执行")
        return 0

    with db_manager.pg_conn.cursor() as cur:
        cur.execute("DELETE FROM article_summaries WHERE id = ANY(%s)", (stale_ids,))
        db_manager.pg_conn.commit()
    logger.info(f"已删除 {len(stale_ids)} 条脏缓存，下次刷新时将按内容语言自动重新生成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
