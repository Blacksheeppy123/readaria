#!/usr/bin/env python3
"""
Readaria 健康检查与监控脚本
在 VPS 上通过 crontab 定时执行，检查系统各项指标并报警

使用方式:
    python3 scripts/health_check.py

Crontab 配置（每分钟执行一次；路径按实际安装目录调整）:
    * * * * * /path/to/readaria/venv/bin/python /path/to/readaria/scripts/health_check.py >> /path/to/readaria/logs/health_check.log 2>&1
"""

import os
import sys
import json
import time
import logging
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============ 配置 ============
PROJECT_ROOT = Path(os.environ.get("READARIA_ROOT", Path(__file__).resolve().parents[1]))
LOGS_DIR = PROJECT_ROOT / "logs"
ALERT_LOG = LOGS_DIR / "alerts.log"

# 报警阈值
THRESHOLDS = {
    "cpu_percent": 80,
    "memory_percent": 85,
    "disk_percent": 85,
    "nginx_5xx_rate": 0.05,  # 5%
    "api_response_ms": 5000,
    "db_connections_ratio": 0.8,  # 80% max_connections
}

# 监控的 Docker 容器
DOCKER_CONTAINERS = [
    "docker-api-1",
    "docker-postgres-1",
    "docker-redis-1",
]

# 监控的 API 端点
API_ENDPOINTS = [
    {"name": "API Root", "url": "http://localhost:8000/", "timeout_ms": 2000},
    {"name": "API Docs", "url": "http://localhost:8000/docs", "timeout_ms": 3000},
]

# Nginx 日志路径
NGINX_ACCESS_LOG = os.environ.get("NGINX_ACCESS_LOG", "/var/log/nginx/readaria_api_access.log")
NGINX_ERROR_LOG = os.environ.get("NGINX_ERROR_LOG", "/var/log/nginx/readaria_api_error.log")

# 报警冷却时间（同一类报警在 N 分钟内只发一次）
ALERT_COOLDOWN_MINUTES = 10


# ============ 报警状态管理 ============

def get_alert_state_file(alert_type: str) -> Path:
    """获取报警状态文件路径"""
    state_dir = PROJECT_ROOT / ".alert_state"
    state_dir.mkdir(exist_ok=True)
    return state_dir / f"{alert_type}.last_alert"


def should_alert(alert_type: str) -> bool:
    """检查是否应该发送报警（考虑冷却时间）"""
    state_file = get_alert_state_file(alert_type)
    if not state_file.exists():
        return True
    last_alert_time = datetime.fromtimestamp(state_file.stat().st_mtime)
    if datetime.now() - last_alert_time > timedelta(minutes=ALERT_COOLDOWN_MINUTES):
        return True
    return False


def record_alert(alert_type: str):
    """记录报警时间"""
    state_file = get_alert_state_file(alert_type)
    state_file.touch()


def send_alert(level: str, alert_type: str, message: str):
    """
    发送报警
    level: WARNING | CRITICAL
    alert_type: 用于冷却去重的标识
    message: 报警内容
    """
    if not should_alert(alert_type):
        return

    record_alert(alert_type)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alert_line = f"[{timestamp}] [{level}] [{alert_type}] {message}"

    # 写入报警日志
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(alert_line + "\n")

    # 输出到标准日志
    if level == "CRITICAL":
        logger.error(f"🚨 {alert_line}")
    else:
        logger.warning(f"⚠️  {alert_line}")

    # Webhook / Server 酱推送
    _send_webhook_alert(level, alert_type, message)
    _send_serverchan_alert(level, alert_type, message)


def _send_webhook_alert(level: str, alert_type: str, message: str):
    """通过 Webhook 发送报警（企业微信/钉钉）"""
    # 从环境变量读取 webhook URL
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
    if not webhook_url:
        return

    try:
        # 企业微信机器人格式
        payload = json.dumps({
            "msgtype": "markdown",
            "markdown": {
                "content": f"**Readaria 监控报警**\n"
                           f"> **级别**: {'🚨 CRITICAL' if level == 'CRITICAL' else '⚠️ WARNING'}\n"
                           f"> **类型**: {alert_type}\n"
                           f"> **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                           f"> **详情**: {message}"
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info(f"Webhook 报警发送成功: {alert_type}")
            else:
                logger.warning(f"Webhook 报警发送失败: HTTP {resp.status}")
    except Exception as e:
        logger.warning(f"Webhook 报警发送异常: {e}")


def _send_serverchan_alert(level: str, alert_type: str, message: str):
    """通过 Server 酱推送报警到微信"""
    sendkey = os.environ.get("SCT_SENDKEY", "")
    if not sendkey:
        return

    try:
        title = f"[Readaria {'严重' if level == 'CRITICAL' else '警告'}] {alert_type}"
        desp = (
            f"**级别**: {'🚨 CRITICAL' if level == 'CRITICAL' else '⚠️ WARNING'}  \n"
            f"**类型**: {alert_type}  \n"
            f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
            f"**详情**: {message}"
        )
        data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
        req = urllib.request.Request(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = json.loads(resp.read().decode("utf-8"))
            if resp_body.get("code") == 0:
                logger.info(f"Server 酱报警发送成功: {alert_type}")
            else:
                logger.warning(f"Server 酱报警发送失败: {resp_body}")
    except Exception as e:
        logger.warning(f"Server 酱报警发送异常: {e}")


# ============ 检查项 ============

def check_docker_containers() -> list:
    """检查 Docker 容器状态"""
    issues = []
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}"],
            capture_output=True, text=True, timeout=10
        )
        running_containers = {}
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                name, status = line.split("|", 1)
                running_containers[name.strip()] = status.strip()

        for container in DOCKER_CONTAINERS:
            if container not in running_containers:
                issues.append({
                    "type": "docker_container_down",
                    "container": container,
                    "message": f"容器 {container} 未运行"
                })
            elif "unhealthy" in running_containers[container].lower():
                issues.append({
                    "type": "docker_container_unhealthy",
                    "container": container,
                    "message": f"容器 {container} 状态异常: {running_containers[container]}"
                })
    except subprocess.TimeoutExpired:
        issues.append({"type": "docker_timeout", "message": "Docker 命令超时"})
    except Exception as e:
        issues.append({"type": "docker_error", "message": f"Docker 检查失败: {e}"})

    return issues


def check_api_endpoints() -> list:
    """检查 API 端点响应"""
    issues = []
    for endpoint in API_ENDPOINTS:
        try:
            start = time.time()
            req = urllib.request.Request(endpoint["url"], method="GET")
            with urllib.request.urlopen(req, timeout=endpoint["timeout_ms"] / 1000) as resp:
                elapsed_ms = (time.time() - start) * 1000
                if resp.status != 200:
                    issues.append({
                        "type": "api_error",
                        "endpoint": endpoint["name"],
                        "message": f"{endpoint['name']} 返回 HTTP {resp.status}"
                    })
                elif elapsed_ms > THRESHOLDS["api_response_ms"]:
                    issues.append({
                        "type": "api_slow",
                        "endpoint": endpoint["name"],
                        "message": f"{endpoint['name']} 响应过慢: {elapsed_ms:.0f}ms"
                    })
        except urllib.error.HTTPError as e:
            issues.append({
                "type": "api_error",
                "endpoint": endpoint["name"],
                "message": f"{endpoint['name']} HTTP 错误: {e.code}"
            })
        except urllib.error.URLError as e:
            issues.append({
                "type": "api_unreachable",
                "endpoint": endpoint["name"],
                "message": f"{endpoint['name']} 无法访问: {e.reason}"
            })
        except Exception as e:
            issues.append({
                "type": "api_exception",
                "endpoint": endpoint["name"],
                "message": f"{endpoint['name']} 检查异常: {e}"
            })

    return issues


def check_system_resources() -> list:
    """检查系统资源（CPU、内存、磁盘）"""
    issues = []

    # CPU 使用率（最近 1 分钟平均）
    try:
        with open("/proc/loadavg", "r") as f:
            loadavg = f.read().strip().split()
            load_1min = float(loadavg[0])

        # 获取 CPU 核心数
        cpu_cores = os.cpu_count() or 1
        cpu_percent = (load_1min / cpu_cores) * 100

        if cpu_percent > THRESHOLDS["cpu_percent"]:
            issues.append({
                "type": "cpu_high",
                "message": f"CPU 使用率过高: {cpu_percent:.1f}% (load: {load_1min:.2f}/{cpu_cores} cores)"
            })
    except Exception as e:
        logger.debug(f"CPU 检查失败: {e}")

    # 内存使用率
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = {}
            for line in f:
                if ":" in line:
                    key, value = line.split(":", 1)
                    meminfo[key.strip()] = int(value.strip().split()[0])  # kB

        total = meminfo.get("MemTotal", 0)
        available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        if total > 0:
            used_percent = ((total - available) / total) * 100
            if used_percent > THRESHOLDS["memory_percent"]:
                issues.append({
                    "type": "memory_high",
                    "message": f"内存使用率过高: {used_percent:.1f}%"
                })
    except Exception as e:
        logger.debug(f"内存检查失败: {e}")

    # 磁盘使用率（系统盘 + 数据盘）
    disks_to_check = [
        (str(PROJECT_ROOT), "系统盘"),
        (str(PROJECT_ROOT / "data_disk"), "数据盘"),
    ]
    for disk_path, disk_name in disks_to_check:
        try:
            result = subprocess.run(
                ["df", "-h", disk_path],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        use_percent = int(parts[4].rstrip("%"))
                        if use_percent > THRESHOLDS["disk_percent"]:
                            issues.append({
                                "type": f"disk_high_{disk_name}",
                                "message": f"{disk_name}使用率过高: {use_percent}% ({parts[5]})"
                            })
                    except ValueError:
                        pass
        except Exception as e:
            logger.debug(f"{disk_name}检查失败: {e}")

    return issues


def check_nginx_errors() -> list:
    """检查 Nginx 最近 5 分钟的错误率"""
    issues = []

    if not os.path.exists(NGINX_ACCESS_LOG):
        return issues

    try:
        # 构造最近 5 分钟（含当前分钟）每个分钟的 nginx 时间戳前缀
        # 例: {"08/May/2026:16:42", ..., "08/May/2026:16:47"}
        now = datetime.now()
        minute_prefixes = {
            (now - timedelta(minutes=offset)).strftime("%d/%b/%Y:%H:%M")
            for offset in range(6)
        }

        total_requests = 0
        error_5xx = 0

        # 读取日志文件末尾（最多 10000 行，避免大文件问题）
        result = subprocess.run(
            ["tail", "-n", "10000", NGINX_ACCESS_LOG],
            capture_output=True, text=True, timeout=10
        )

        for line in result.stdout.split("\n"):
            # nginx 时间戳形如 [08/May/2026:16:42:30 +0800]，取到分钟一级匹配
            if not any(prefix in line for prefix in minute_prefixes):
                continue
            total_requests += 1
            # Nginx 日志格式中状态码在第 9 个字段（常见格式）
            parts = line.split()
            if len(parts) >= 9:
                try:
                    status = int(parts[8])
                    if status >= 500:
                        error_5xx += 1
                except ValueError:
                    pass

        if total_requests > 0:
            error_rate = error_5xx / total_requests
            if error_rate > THRESHOLDS["nginx_5xx_rate"]:
                issues.append({
                    "type": "nginx_5xx_high",
                    "message": f"Nginx 5xx 错误率过高: {error_rate*100:.1f}% ({error_5xx}/{total_requests} 请求)"
                })
    except Exception as e:
        logger.debug(f"Nginx 错误检查失败: {e}")

    return issues


def check_backup_status() -> list:
    """检查备份状态"""
    issues = []
    backup_dir = PROJECT_ROOT / "backups"

    # 1. 检查最近 24 小时内是否有备份文件
    try:
        cutoff = datetime.now() - timedelta(hours=24)
        recent_backups = []
        for f in backup_dir.glob("backup_*.tar.gz"):
            if datetime.fromtimestamp(f.stat().st_mtime) > cutoff:
                recent_backups.append(f)

        if not recent_backups:
            issues.append({
                "type": "backup_missing",
                "message": "过去 24 小时内未找到备份文件，请检查 auto_backup.sh 是否正常运行"
            })
        else:
            # 2. 检查备份文件大小是否合理（至少 1MB）
            latest = max(recent_backups, key=lambda f: f.stat().st_mtime)
            size = latest.stat().st_size
            if size < 1024 * 1024:  # 1MB
                issues.append({
                    "type": "backup_too_small",
                    "message": f"最新备份文件过小: {size} bytes ({latest.name})，可能备份不完整"
                })
            else:
                logger.info(f"  ✅ 备份正常: {latest.name} ({size / (1024*1024):.1f}MB)")

        # 3. 检查备份日志是否有错误
        today_log = LOGS_DIR / f"backup_{datetime.now().strftime('%Y%m%d')}.log"
        if today_log.exists():
            content = today_log.read_text(encoding="utf-8", errors="ignore")
            if "⚠️" in content or "失败" in content:
                issues.append({
                    "type": "backup_log_error",
                    "message": f"备份日志中发现错误，请检查 {today_log.name}"
                })
    except Exception as e:
        logger.debug(f"备份检查失败: {e}")

    return issues


def check_disk_usage_detail() -> list:
    """检查关键目录的磁盘使用情况"""
    issues = []

    dirs_to_check = [
        (str(PROJECT_ROOT / "logs"), 5 * 1024 * 1024 * 1024, "日志目录"),  # 5GB
        (str(PROJECT_ROOT / "audio_cache"), 20 * 1024 * 1024 * 1024, "音频缓存"),  # 20GB
        (str(PROJECT_ROOT / "podcast_cache"), 10 * 1024 * 1024 * 1024, "播客缓存"),  # 10GB
    ]

    for path, max_size, name in dirs_to_check:
        try:
            if os.path.exists(path):
                result = subprocess.run(
                    ["du", "-sb", path],
                    capture_output=True, text=True, timeout=10
                )
                size = int(result.stdout.split()[0])
                if size > max_size:
                    issues.append({
                        "type": "dir_size_high",
                        "message": f"{name} ({path}) 大小超过阈值: {size / (1024**3):.1f}GB > {max_size / (1024**3):.0f}GB"
                    })
        except Exception as e:
            logger.debug(f"目录大小检查失败 ({path}): {e}")

    return issues


# ============ 主流程 ============

def run_health_check():
    """执行完整健康检查"""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("开始健康检查...")

    all_issues = []

    # 1. Docker 容器状态
    logger.info("[1/5] 检查 Docker 容器状态...")
    issues = check_docker_containers()
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            send_alert("CRITICAL", issue["type"], issue["message"])
    else:
        logger.info("  ✅ 所有容器运行正常")

    # 2. API 端点
    logger.info("[2/5] 检查 API 端点...")
    issues = check_api_endpoints()
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            level = "CRITICAL" if "unreachable" in issue["type"] else "WARNING"
            send_alert(level, issue["type"], issue["message"])
    else:
        logger.info("  ✅ 所有 API 端点正常")

    # 3. 系统资源
    logger.info("[3/5] 检查系统资源...")
    issues = check_system_resources()
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            send_alert("WARNING", issue["type"], issue["message"])
    else:
        logger.info("  ✅ 系统资源正常")

    # 4. Nginx 错误率
    logger.info("[4/5] 检查 Nginx 错误率...")
    issues = check_nginx_errors()
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            send_alert("WARNING", issue["type"], issue["message"])
    else:
        logger.info("  ✅ Nginx 错误率正常")

    # 5. 目录大小
    logger.info("[5/6] 检查目录大小...")
    issues = check_disk_usage_detail()
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            send_alert("WARNING", issue["type"], issue["message"])
    else:
        logger.info("  ✅ 目录大小正常")

    # 6. 备份状态
    logger.info("[6/6] 检查备份状态...")
    issues = check_backup_status()
    all_issues.extend(issues)
    if issues:
        for issue in issues:
            send_alert("CRITICAL", issue["type"], issue["message"])
    else:
        logger.info("  ✅ 备份状态正常")

    # 汇总
    elapsed = time.time() - start_time
    if all_issues:
        logger.warning(f"健康检查完成，发现 {len(all_issues)} 个问题，耗时 {elapsed:.1f}s")
    else:
        logger.info(f"✅ 健康检查全部通过，耗时 {elapsed:.1f}s")

    # 输出结构化日志（便于后续分析）
    health_report = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "issues_count": len(all_issues),
        "issues": all_issues,
        "status": "unhealthy" if all_issues else "healthy",
    }
    print(json.dumps(health_report, ensure_ascii=False))

    return len(all_issues) == 0


if __name__ == "__main__":
    # 确保日志目录存在
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 支持命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="Readaria 健康检查脚本")
    parser.add_argument("--check", choices=["docker", "api", "resources", "nginx", "disk", "backup", "all"],
                        default="all", help="指定检查项")
    args = parser.parse_args()

    if args.check == "all":
        success = run_health_check()
        sys.exit(0 if success else 1)
    else:
        # 单项检查（用于调试）
        check_map = {
            "docker": check_docker_containers,
            "api": check_api_endpoints,
            "resources": check_system_resources,
            "nginx": check_nginx_errors,
            "disk": check_disk_usage_detail,
            "backup": check_backup_status,
        }
        issues = check_map[args.check]()
        for issue in issues:
            print(f"[{issue['type']}] {issue['message']}")
        sys.exit(0 if not issues else 1)
