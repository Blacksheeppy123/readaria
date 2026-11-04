"""
音频缓存自动清理服务
功能：定期清理超过指定天数的音频缓存文件
"""
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, List

from core.config.settings import settings

logger = logging.getLogger(__name__)


class AudioCacheCleaner:
    """音频缓存清理器"""

    def __init__(
        self,
        cache_dir: str = None,
        expiry_days: int = None,
        max_size_gb: int = None
    ):
        """
        初始化缓存清理器

        Args:
            cache_dir: 缓存目录路径（默认从配置读取）
            expiry_days: 缓存过期天数（默认从配置读取）
            max_size_gb: 最大缓存容量 GB（默认从配置读取）
        """
        self.cache_dir = Path(cache_dir or settings.tts_cache_dir)
        self.expiry_days = expiry_days or settings.tts_cache_expiry_days
        self.max_size_gb = max_size_gb or settings.tts_cache_max_size_gb

        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"音频缓存清理器初始化: "
            f"目录={self.cache_dir}, "
            f"过期天数={self.expiry_days}, "
            f"最大容量={self.max_size_gb}GB"
        )

    def get_cache_stats(self) -> dict:
        """
        获取缓存统计信息

        Returns:
            dict: 包含文件数量、总大小、最旧文件等信息
        """
        if not self.cache_dir.exists():
            return {
                "total_files": 0,
                "total_size_mb": 0,
                "total_size_gb": 0,
                "oldest_file": None,
                "newest_file": None
            }

        files = list(self.cache_dir.glob("*.mp3"))

        if not files:
            return {
                "total_files": 0,
                "total_size_mb": 0,
                "total_size_gb": 0,
                "oldest_file": None,
                "newest_file": None
            }

        total_size = sum(f.stat().st_size for f in files)
        file_times = [(f, f.stat().st_mtime) for f in files]
        oldest = min(file_times, key=lambda x: x[1])
        newest = max(file_times, key=lambda x: x[1])

        return {
            "total_files": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
            "oldest_file": {
                "name": oldest[0].name,
                "age_days": round((time.time() - oldest[1]) / 86400, 1)
            },
            "newest_file": {
                "name": newest[0].name,
                "age_days": round((time.time() - newest[1]) / 86400, 1)
            }
        }

    def clean_expired_files(self, dry_run: bool = False) -> Tuple[int, float]:
        """
        清理过期的缓存文件

        Args:
            dry_run: 是否为模拟运行（不实际删除文件）

        Returns:
            Tuple[int, float]: (删除文件数量, 释放空间 MB)
        """
        if not self.cache_dir.exists():
            logger.warning(f"缓存目录不存在: {self.cache_dir}")
            return 0, 0.0

        # 计算过期时间戳
        expiry_timestamp = time.time() - (self.expiry_days * 86400)
        expiry_date = datetime.fromtimestamp(expiry_timestamp)

        logger.info(f"开始清理过期缓存文件（过期时间: {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}）")

        deleted_count = 0
        freed_space = 0.0
        expired_files: List[Path] = []

        # 查找过期文件
        for file_path in self.cache_dir.glob("*.mp3"):
            try:
                file_mtime = file_path.stat().st_mtime
                if file_mtime < expiry_timestamp:
                    file_size = file_path.stat().st_size
                    file_age_days = (time.time() - file_mtime) / 86400

                    expired_files.append(file_path)
                    freed_space += file_size

                    logger.debug(
                        f"发现过期文件: {file_path.name} "
                        f"(年龄: {file_age_days:.1f}天, 大小: {file_size / (1024 * 1024):.2f}MB)"
                    )
            except Exception as e:
                logger.error(f"检查文件失败 {file_path}: {e}")

        # 删除过期文件
        if expired_files:
            if dry_run:
                logger.info(f"[模拟运行] 将删除 {len(expired_files)} 个过期文件，释放 {freed_space / (1024 * 1024):.2f}MB")
            else:
                for file_path in expired_files:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"删除文件失败 {file_path}: {e}")

                logger.info(
                    f"清理完成: 删除 {deleted_count} 个过期文件，"
                    f"释放 {freed_space / (1024 * 1024):.2f}MB 空间"
                )
        else:
            logger.info("未发现过期文件")

        return deleted_count, freed_space / (1024 * 1024)

    def clean_by_size(self, dry_run: bool = False) -> Tuple[int, float]:
        """
        按大小清理缓存（当缓存超过最大容量时，删除最旧的文件）

        Args:
            dry_run: 是否为模拟运行（不实际删除文件）

        Returns:
            Tuple[int, float]: (删除文件数量, 释放空间 MB)
        """
        if not self.cache_dir.exists():
            logger.warning(f"缓存目录不存在: {self.cache_dir}")
            return 0, 0.0

        # 获取所有文件及其大小和修改时间
        files = []
        total_size = 0

        for file_path in self.cache_dir.glob("*.mp3"):
            try:
                stat = file_path.stat()
                files.append({
                    "path": file_path,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime
                })
                total_size += stat.st_size
            except Exception as e:
                logger.error(f"读取文件信息失败 {file_path}: {e}")

        total_size_gb = total_size / (1024 * 1024 * 1024)

        # 如果未超过最大容量，无需清理
        if total_size_gb <= self.max_size_gb:
            logger.info(
                f"缓存大小 {total_size_gb:.2f}GB 未超过限制 {self.max_size_gb}GB，无需清理"
            )
            return 0, 0.0

        logger.info(
            f"缓存大小 {total_size_gb:.2f}GB 超过限制 {self.max_size_gb}GB，"
            f"开始清理最旧的文件"
        )

        # 按修改时间排序（最旧的在前）
        files.sort(key=lambda x: x["mtime"])

        # 计算需要释放的空间
        target_size = self.max_size_gb * 0.8 * 1024 * 1024 * 1024  # 清理到 80% 容量
        need_to_free = total_size - target_size

        deleted_count = 0
        freed_space = 0.0

        # 删除最旧的文件直到达到目标大小
        for file_info in files:
            if freed_space >= need_to_free:
                break

            file_path = file_info["path"]
            file_size = file_info["size"]

            if dry_run:
                logger.info(
                    f"[模拟运行] 将删除: {file_path.name} "
                    f"(大小: {file_size / (1024 * 1024):.2f}MB)"
                )
            else:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"已删除: {file_path.name}")
                except Exception as e:
                    logger.error(f"删除文件失败 {file_path}: {e}")

            freed_space += file_size

        freed_space_mb = freed_space / (1024 * 1024)

        if not dry_run:
            logger.info(
                f"按大小清理完成: 删除 {deleted_count} 个文件，"
                f"释放 {freed_space_mb:.2f}MB 空间"
            )

        return deleted_count, freed_space_mb

    def clean_all(self, dry_run: bool = False) -> dict:
        """
        执行完整的缓存清理（先按过期时间，再按大小）

        Args:
            dry_run: 是否为模拟运行（不实际删除文件）

        Returns:
            dict: 清理结果统计
        """
        logger.info("=" * 60)
        logger.info("开始音频缓存清理任务")
        logger.info("=" * 60)

        # 清理前统计
        stats_before = self.get_cache_stats()
        logger.info(
            f"清理前: {stats_before['total_files']} 个文件, "
            f"{stats_before['total_size_gb']:.2f}GB"
        )

        # 1. 清理过期文件
        expired_count, expired_space = self.clean_expired_files(dry_run=dry_run)

        # 2. 按大小清理
        size_count, size_space = self.clean_by_size(dry_run=dry_run)

        # 清理后统计
        stats_after = self.get_cache_stats()
        logger.info(
            f"清理后: {stats_after['total_files']} 个文件, "
            f"{stats_after['total_size_gb']:.2f}GB"
        )

        result = {
            "dry_run": dry_run,
            "before": stats_before,
            "after": stats_after,
            "expired_files_deleted": expired_count,
            "expired_space_freed_mb": round(expired_space, 2),
            "size_files_deleted": size_count,
            "size_space_freed_mb": round(size_space, 2),
            "total_files_deleted": expired_count + size_count,
            "total_space_freed_mb": round(expired_space + size_space, 2),
            "timestamp": datetime.now().isoformat()
        }

        logger.info("=" * 60)
        logger.info(
            f"清理任务完成: 删除 {result['total_files_deleted']} 个文件, "
            f"释放 {result['total_space_freed_mb']:.2f}MB"
        )
        logger.info("=" * 60)

        return result


def run_cache_cleanup(dry_run: bool = False) -> dict:
    """
    运行缓存清理任务（供定时任务调用）

    Args:
        dry_run: 是否为模拟运行

    Returns:
        dict: 清理结果
    """
    try:
        cleaner = AudioCacheCleaner()
        result = cleaner.clean_all(dry_run=dry_run)
        return result
    except Exception as e:
        logger.error(f"缓存清理任务失败: {e}", exc_info=True)
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    # 命令行测试
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("=" * 60)
        print("模拟运行模式（不会实际删除文件）")
        print("=" * 60)

    result = run_cache_cleanup(dry_run=dry_run)

    print("\n清理结果:")
    print(f"- 删除过期文件: {result.get('expired_files_deleted', 0)} 个")
    print(f"- 释放过期空间: {result.get('expired_space_freed_mb', 0):.2f}MB")
    print(f"- 删除超量文件: {result.get('size_files_deleted', 0)} 个")
    print(f"- 释放超量空间: {result.get('size_space_freed_mb', 0):.2f}MB")
    print(f"- 总计删除: {result.get('total_files_deleted', 0)} 个文件")
    print(f"- 总计释放: {result.get('total_space_freed_mb', 0):.2f}MB")
