#!/usr/bin/env python3
"""
Readaria 缓存清理脚本
按 LRU 策略清理音频缓存和播客缓存，防止磁盘空间无限增长

使用方式:
    python3 scripts/cleanup_cache.py

Crontab 配置（每天凌晨 04:00 执行；路径按实际安装目录调整）:
    0 4 * * * /path/to/readaria/venv/bin/python /path/to/readaria/scripts/cleanup_cache.py >> /path/to/readaria/logs/cleanup.log 2>&1
"""

import os
import sys
import json
import time
import shutil
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 配置：默认使用仓库内目录，可通过 READARIA_ROOT 覆盖
PROJECT_ROOT = Path(os.environ.get("READARIA_ROOT", Path(__file__).resolve().parents[1]))
CACHE_CONFIG = {
    str(PROJECT_ROOT / "audio_cache"): {
        "max_size_gb": 20,
        "max_age_days": 30,
        "description": "TTS 音频缓存"
    },
    str(PROJECT_ROOT / "podcast_cache"): {
        "max_size_gb": 10,
        "max_age_days": 90,
        "description": "播客音频缓存"
    },
}

LOGS_CONFIG = {
    str(PROJECT_ROOT / "logs"): {
        "max_size_gb": 5,
        "max_age_days": 90,
        "pattern": "*.log",
        "description": "应用日志"
    }
}


def fix_directory_permissions(path: Path) -> bool:
    """
    修复目录权限，确保当前用户可以删除其中的文件。
    Docker 容器以非 root 用户创建缓存文件，宿主机用户可能没有写权限。
    注意：path 可能是 symlink，需要解析为真实路径后再处理。
    """
    if not path.exists():
        return True
    # 解析 symlink 到真实路径（find 默认不跟随 symlink 遍历）
    real_path = path.resolve()
    try:
        # 先尝试直接修改权限
        for dirpath, dirnames, filenames in os.walk(real_path):
            dp = Path(dirpath)
            if dp.exists():
                current_mode = dp.stat().st_mode
                # 确保目录对 owner/group/others 都有写权限
                os.chmod(dp, current_mode | 0o777)
    except PermissionError:
        # 如果没有权限，尝试使用 sudo（-L 跟随 symlink）
        try:
            result = subprocess.run(
                ["sudo", "find", "-L", str(real_path), "-type", "d", "-exec", "chmod", "777", "{}", "+"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                logger.warning(f"sudo chmod 失败: {result.stderr.strip()}")
                return False
        except Exception as e:
            logger.warning(f"修复权限时出错: {e}")
            return False
    return True


def get_dir_size(path: Path) -> int:
    """获取目录总大小（字节）"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = Path(dirpath) / f
            if fp.is_file():
                total += fp.stat().st_size
    return total


def get_files_sorted_by_atime(path: Path, pattern: str = "*") -> list:
    """按访问时间（atime）排序的文件列表，最久未访问的在前面"""
    files = []
    for f in path.rglob(pattern):
        if f.is_file():
            stat = f.stat()
            files.append({
                "path": f,
                "size": stat.st_size,
                "atime": stat.st_atime,
                "mtime": stat.st_mtime,
            })
    files.sort(key=lambda x: x["atime"])
    return files


def cleanup_directory(path: str, max_size_gb: float, max_age_days: int, pattern: str = "*", dry_run: bool = False) -> dict:
    """
    清理单个目录
    策略:
    1. 先删除超过 max_age_days 的文件
    2. 如果仍然超过 max_size_gb，按 LRU 删除最久未访问的文件
    """
    result = {
        "path": path,
        "deleted_by_age": 0,
        "deleted_by_size": 0,
        "bytes_freed": 0,
        "errors": []
    }

    dir_path = Path(path)
    if not dir_path.exists():
        logger.info(f"目录不存在，跳过: {path}")
        return result

    # 解析 symlink 到真实路径，确保后续操作（find、os.walk）都能正确遍历
    real_dir_path = dir_path.resolve()

    # 修复目录权限（非 dry-run 模式下），确保可以删除 Docker 容器创建的文件
    if not dry_run:
        permission_fixed = fix_directory_permissions(dir_path)
        if not permission_fixed:
            logger.warning(f"[{path}] 无法修复目录权限，清理可能失败")

    max_size_bytes = max_size_gb * 1024 * 1024 * 1024
    cutoff_time = time.time() - (max_age_days * 24 * 3600)

    files = get_files_sorted_by_atime(real_dir_path, pattern)
    current_size = sum(f["size"] for f in files)

    logger.info(f"[{path}] 当前文件数: {len(files)}, 大小: {current_size / (1024**3):.2f}GB, 上限: {max_size_gb}GB")

    # 第一步：按年龄删除
    remaining_files = []
    for f in files:
        if f["mtime"] < cutoff_time:
            if dry_run:
                logger.info(f"  [DRY-RUN] 删除过期文件: {f['path'].name} (mtime: {datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d')})")
            else:
                try:
                    f["path"].unlink()
                    result["deleted_by_age"] += 1
                    result["bytes_freed"] += f["size"]
                    logger.info(f"  删除过期文件: {f['path'].name}")
                except Exception as e:
                    result["errors"].append(str(e))
                    logger.warning(f"  删除失败: {f['path'].name}, 错误: {e}")
        else:
            remaining_files.append(f)

    # 第二步：按 LRU 删除（如果仍然超过大小限制）
    remaining_size = sum(f["size"] for f in remaining_files)
    if remaining_size > max_size_bytes:
        # 按 atime 排序（最久未访问的在前面）
        remaining_files.sort(key=lambda x: x["atime"])

        for f in remaining_files:
            if remaining_size <= max_size_bytes:
                break

            if dry_run:
                logger.info(f"  [DRY-RUN] LRU 删除: {f['path'].name} (atime: {datetime.fromtimestamp(f['atime']).strftime('%Y-%m-%d')})")
            else:
                try:
                    f["path"].unlink()
                    result["deleted_by_size"] += 1
                    result["bytes_freed"] += f["size"]
                    remaining_size -= f["size"]
                    logger.info(f"  LRU 删除: {f['path'].name}")
                except Exception as e:
                    result["errors"].append(str(e))
                    logger.warning(f"  删除失败: {f['path'].name}, 错误: {e}")

    # 第三步：删除空目录（非 dry-run 模式下）
    if not dry_run:
        empty_dirs_removed = 0
        for dirpath, dirnames, filenames in os.walk(real_dir_path, topdown=False):
            dp = Path(dirpath)
            if dp != real_dir_path and dp.exists() and not any(dp.iterdir()):
                try:
                    dp.rmdir()
                    empty_dirs_removed += 1
                except Exception as e:
                    logger.debug(f"  删除空目录失败: {dp}, 错误: {e}")
        if empty_dirs_removed > 0:
            logger.info(f"[{path}] 删除空目录: {empty_dirs_removed} 个")

    final_size = get_dir_size(real_dir_path)
    logger.info(f"[{path}] 清理完成: 删除 {result['deleted_by_age'] + result['deleted_by_size']} 个文件, 释放 {result['bytes_freed'] / (1024**2):.1f}MB, 剩余 {final_size / (1024**3):.2f}GB")

    return result


def cleanup_logs(dry_run: bool = False) -> list:
    """清理日志目录"""
    results = []
    for path, config in LOGS_CONFIG.items():
        result = cleanup_directory(
            path,
            config["max_size_gb"],
            config["max_age_days"],
            config.get("pattern", "*.log"),
            dry_run
        )
        result["description"] = config["description"]
        results.append(result)
    return results


def cleanup_cache(dry_run: bool = False) -> list:
    """清理缓存目录"""
    results = []
    for path, config in CACHE_CONFIG.items():
        result = cleanup_directory(
            path,
            config["max_size_gb"],
            config["max_age_days"],
            dry_run=dry_run
        )
        result["description"] = config["description"]
        results.append(result)
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Readaria 缓存清理脚本")
    parser.add_argument("--dry-run", action="store_true", help="模拟运行，不实际删除")
    parser.add_argument("--cache-only", action="store_true", help="只清理缓存")
    parser.add_argument("--logs-only", action="store_true", help="只清理日志")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(f"开始缓存清理 (dry_run={args.dry_run})")

    all_results = []

    if not args.logs_only:
        logger.info("\n[缓存清理]")
        cache_results = cleanup_cache(dry_run=args.dry_run)
        all_results.extend(cache_results)

    if not args.cache_only:
        logger.info("\n[日志清理]")
        log_results = cleanup_logs(dry_run=args.dry_run)
        all_results.extend(log_results)

    # 输出汇总报告
    total_freed = sum(r["bytes_freed"] for r in all_results)
    total_deleted = sum(r["deleted_by_age"] + r["deleted_by_size"] for r in all_results)

    logger.info("\n" + "=" * 60)
    logger.info(f"清理完成: 共删除 {total_deleted} 个文件, 释放 {total_freed / (1024**2):.1f}MB")

    # 输出结构化日志
    report = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "total_files_deleted": total_deleted,
        "total_bytes_freed": total_freed,
        "details": all_results,
    }
    print(json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
