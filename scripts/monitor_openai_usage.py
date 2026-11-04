#!/usr/bin/env python3
"""
Readaria OpenAI 用量监控脚本
监控 OpenAI API 调用成本和额度使用情况，超限预警

使用方式:
    python3 scripts/monitor_openai_usage.py

Crontab 配置（每天 08:00 执行，检查昨日用量；路径按实际安装目录调整）:
    0 8 * * * /path/to/readaria/venv/bin/python /path/to/readaria/scripts/monitor_openai_usage.py >> /path/to/readaria/logs/openai_usage.log 2>&1

同时支持实时检查（手动执行）:
    python3 scripts/monitor_openai_usage.py --check-now
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 项目路径：默认取仓库根目录，也可通过环境变量覆盖
PROJECT_ROOT = Path(os.environ.get("READARIA_ROOT", Path(__file__).resolve().parents[1]))
LOGS_DIR = PROJECT_ROOT / "logs"

# OpenAI 相关配置
OPENAI_API_BASE = "https://api.openai.com/v1"

# 预警阈值（从 settings 读取，这里是默认值）
DEFAULT_ALERT_THRESHOLDS = {
    "daily_usd": 5.0,      # 日用量超过 $5 预警
    "monthly_usd": 100.0,  # 月用量超过 $100 预警
    "remaining_percent": 20,  # 剩余额度低于 20% 预警
}


def get_openai_api_key() -> str:
    """从环境变量或 .env 文件获取 OpenAI API Key"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        return api_key

    # 尝试从 .env 读取
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")

    return ""


def call_openai_api(endpoint: str, api_key: str) -> dict:
    """调用 OpenAI API"""
    req = urllib.request.Request(
        f"{OPENAI_API_BASE}/{endpoint}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.error("OpenAI API 限流 (429)，请稍后再试")
        elif e.code == 401:
            logger.error("OpenAI API Key 无效 (401)")
        else:
            logger.error(f"OpenAI API 错误: HTTP {e.code}")
        try:
            error_body = e.read().decode("utf-8")
            logger.error(f"错误详情: {error_body}")
        except:
            pass
        return {}
    except Exception as e:
        logger.error(f"调用 OpenAI API 失败: {e}")
        return {}


def check_usage(api_key: str) -> dict:
    """检查 OpenAI 用量（基于 usage API，如果可用）"""
    # OpenAI 的 usage API 需要访问 https://api.openai.com/v1/usage
    # 注意：此端点可能需要特殊的权限
    result = call_openai_api("usage?date=" + datetime.now().strftime("%Y-%m-%d"), api_key)
    return result


def check_billing(api_key: str) -> dict:
    """检查 OpenAI 账单和额度信息"""
    # 获取订阅信息
    subscription = call_openai_api("dashboard/billing/subscription", api_key)

    # 获取已用量
    now = datetime.now()
    start_date = now.replace(day=1).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    usage = call_openai_api(
        f"dashboard/billing/usage?start_date={start_date}&end_date={end_date}",
        api_key
    )

    return {
        "subscription": subscription,
        "usage": usage,
    }


def check_daily_usage(api_key: str, date_str: str) -> dict:
    """
    通过 OpenAI Billing API 查询指定日期的实际用量
    返回 {"daily_usage_usd": float, "source": "api"} 或 {"daily_usage_usd": None, "source": None}
    """
    try:
        result = call_openai_api(
            f"dashboard/billing/usage?start_date={date_str}&end_date={date_str}",
            api_key
        )
        if result and "total_usage" in result:
            daily_usage = result["total_usage"] / 100  # 转换为美元
            return {
                "daily_usage_usd": round(daily_usage, 4),
                "source": "api"
            }
    except Exception as e:
        logger.warning(f"Billing API 日用量查询失败: {e}")

    return {"daily_usage_usd": None, "source": None}


def check_rate_limits(api_key: str) -> dict:
    """检查 OpenAI Rate Limits"""
    # 通过模型列表端点间接检查 key 是否有效
    models = call_openai_api("models", api_key)
    if models and "data" in models:
        return {
            "key_valid": True,
            "models_available": len(models.get("data", [])),
        }
    return {
        "key_valid": False,
        "models_available": 0,
    }


def estimate_cost_from_logs(date_str: str = None) -> dict:
    """
    从应用日志中估算昨日 OpenAI 调用成本
    解析日志中的 TTS / 摘要 / 播客生成记录
    """
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    log_file = LOGS_DIR / f"api_{date_str}.log"
    if not log_file.exists():
        # 尝试当前日志文件
        log_file = LOGS_DIR / "api.log"

    if not log_file.exists():
        logger.warning(f"日志文件不存在: {log_file}")
        return {"estimated_cost_usd": 0, "tts_count": 0, "summary_count": 0, "podcast_count": 0}

    tts_count = 0
    summary_count = 0
    podcast_count = 0

    # 成本估算（2026-10-26 更新：gpt-4.1-nano 下线，切换到新模型）
    # gpt-5.6-luna: $0.20/1M input, $1.20/1M output（替代 gpt-4.1-nano）
    # gpt-6-luna:   $0.10/1M input, $0.50/1M output（替代 gpt-4.1-mini）
    # tts-1: $0.015/1K chars
    COST_PER_TTS = 0.03       # $0.03/篇（文章朗读 TTS）
    COST_PER_SUMMARY = 0.001  # $0.001/篇（gpt-5.6-luna，输出单价约为 nano 的 3 倍）
    COST_PER_PODCAST = 0.08   # $0.08/集（gpt-6-luna 脚本 + 5.6-luna 问题 + tts-1）

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                # TTS: 精确匹配实际合成调用日志
                if "Segment parallel generation" in line:
                    tts_count += 1
                # 摘要: 精确匹配 NLP processor 入口日志，避免 "生成成功"/"生成完成" 重复计数
                if "开始生成摘要" in line and "backend.nlp.processor" in line:
                    summary_count += 1
                # 播客: 精确匹配单用户播客生成入口，避免 "生成脚本"/"生成成功" 重复计数
                if "开始为用户" in line and "生成播客" in line and "backend.services.podcast_generator" in line:
                    podcast_count += 1
    except Exception as e:
        logger.warning(f"日志解析失败: {e}")

    # 去重：粗略估算，实际数量可能偏少或偏多
    estimated_cost = (
        tts_count * COST_PER_TTS +
        summary_count * COST_PER_SUMMARY +
        podcast_count * COST_PER_PODCAST
    )

    return {
        "date": date_str,
        "estimated_cost_usd": round(estimated_cost, 4),
        "tts_count": tts_count,
        "summary_count": summary_count,
        "podcast_count": podcast_count,
        "cost_breakdown": {
            "tts": round(tts_count * COST_PER_TTS, 4),
            "summary": round(summary_count * COST_PER_SUMMARY, 4),
            "podcast": round(podcast_count * COST_PER_PODCAST, 4),
        }
    }


def send_alert(message: str, level: str = "WARNING"):
    """发送报警"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alert_line = f"[{timestamp}] [{level}] [OpenAI] {message}"

    # 写入报警日志
    alert_log = LOGS_DIR / "alerts.log"
    alert_log.parent.mkdir(parents=True, exist_ok=True)
    with open(alert_log, "a", encoding="utf-8") as f:
        f.write(alert_line + "\n")

    logger.warning(f"🚨 {alert_line}")

    # Webhook 推送
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
    if webhook_url:
        try:
            payload = json.dumps({
                "msgtype": "markdown",
                "markdown": {
                    "content": f"**Readaria OpenAI 监控**\n"
                               f"> **级别**: {'🚨 CRITICAL' if level == 'CRITICAL' else '⚠️ WARNING'}\n"
                               f"> **时间**: {timestamp}\n"
                               f"> **详情**: {message}"
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                webhook_url, data=payload,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info("Webhook 报警发送成功")
        except Exception as e:
            logger.warning(f"Webhook 发送失败: {e}")

    # Server 酱推送
    sendkey = os.environ.get("SCT_SENDKEY", "")
    if sendkey:
        try:
            title = f"[Readaria OpenAI {'严重' if level == 'CRITICAL' else '警告'}]"
            desp = (
                f"**级别**: {'🚨 CRITICAL' if level == 'CRITICAL' else '⚠️ WARNING'}  \n"
                f"**时间**: {timestamp}  \n"
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
                    logger.info("Server 酱报警发送成功")
                else:
                    logger.warning(f"Server 酱报警发送失败: {resp_body}")
        except Exception as e:
            logger.warning(f"Server 酱发送失败: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Readaria OpenAI 用量监控")
    parser.add_argument("--check-now", action="store_true", help="立即检查当前状态")
    parser.add_argument("--date", help="指定日期 (YYYY-MM-DD)，分析该日用量")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("OpenAI 用量监控开始...")

    api_key = get_openai_api_key()
    if not api_key:
        logger.error("未找到 OpenAI API Key，请在 .env 中配置 OPENAI_API_KEY")
        sys.exit(1)

    # 1. 检查 API Key 有效性
    logger.info("[1/4] 检查 API Key 有效性...")
    rate_limit_info = check_rate_limits(api_key)
    if rate_limit_info.get("key_valid"):
        logger.info(f"  ✅ API Key 有效，可用模型: {rate_limit_info['models_available']} 个")
    else:
        logger.error("  ❌ API Key 无效或已过期")
        send_alert("OpenAI API Key 无效或已过期，请立即检查！", "CRITICAL")

    # 2. 检查账单信息
    logger.info("[2/4] 检查账单信息...")
    billing = check_billing(api_key)
    subscription = billing.get("subscription", {})
    usage = billing.get("usage", {})

    if subscription:
        hard_limit = subscription.get("hard_limit_usd", "N/A")
        logger.info(f"  额度上限: ${hard_limit}")

    if usage:
        total_usage = usage.get("total_usage", 0) / 100  # 转换为美元
        logger.info(f"  本月已用: ${total_usage:.2f}")

        # 预警检查
        if isinstance(subscription.get("hard_limit_usd"), (int, float)):
            hard_limit = subscription["hard_limit_usd"]
            remaining = hard_limit - total_usage
            remaining_percent = (remaining / hard_limit) * 100 if hard_limit > 0 else 100

            logger.info(f"  剩余额度: ${remaining:.2f} ({remaining_percent:.1f}%)")

            if remaining_percent < DEFAULT_ALERT_THRESHOLDS["remaining_percent"]:
                send_alert(
                    f"OpenAI 剩余额度不足 {DEFAULT_ALERT_THRESHOLDS['remaining_percent']}%: "
                    f"${remaining:.2f} / ${hard_limit:.2f} ({remaining_percent:.1f}%)",
                    "CRITICAL"
                )

            if total_usage > DEFAULT_ALERT_THRESHOLDS["monthly_usd"]:
                send_alert(
                    f"OpenAI 月用量超过阈值 ${DEFAULT_ALERT_THRESHOLDS['monthly_usd']}: "
                    f"${total_usage:.2f}",
                    "WARNING"
                )
    else:
        logger.warning("  ⚠️ 无法获取账单信息（可能是权限不足或 API 变更）")

    # 3. 查询实际用量（优先 Billing API，回退日志估算）
    logger.info("[3/4] 查询昨日用量...")
    target_date = args.date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 优先尝试 Billing API 获取真实日用量
    daily_usage_result = check_daily_usage(api_key, target_date)
    daily_cost = daily_usage_result.get("daily_usage_usd")
    usage_source = daily_usage_result.get("source")

    if daily_cost is not None:
        logger.info(f"  ✅ Billing API 实际用量: ${daily_cost:.2f} (来源: OpenAI API)")
    else:
        logger.info("  ⚠️ Billing API 不可用，回退到日志估算")

    # 日志估算作为参考（无论 API 是否成功都输出）
    log_estimate = estimate_cost_from_logs(target_date)
    logger.info(f"  日期: {log_estimate['date']}")
    logger.info(f"  TTS 调用: {log_estimate['tts_count']} 次, 成本: ${log_estimate['cost_breakdown']['tts']:.2f}")
    logger.info(f"  摘要调用: {log_estimate['summary_count']} 次, 成本: ${log_estimate['cost_breakdown']['summary']:.2f}")
    logger.info(f"  播客生成: {log_estimate['podcast_count']} 次, 成本: ${log_estimate['cost_breakdown']['podcast']:.2f}")
    logger.info(f"  日志估算总成本: ${log_estimate['estimated_cost_usd']:.2f}")

    # 报警判断：优先使用 API 真实数据，其次日志估算
    alert_cost = daily_cost if daily_cost is not None else log_estimate["estimated_cost_usd"]
    alert_source = "实际用量" if daily_cost is not None else "日志估算"

    if alert_cost > DEFAULT_ALERT_THRESHOLDS["daily_usd"]:
        if daily_cost is not None:
            send_alert(
                f"昨日 OpenAI {alert_source}超过 ${DEFAULT_ALERT_THRESHOLDS['daily_usd']}: "
                f"${alert_cost:.2f} (来源: OpenAI Billing API)",
                "WARNING"
            )
        else:
            send_alert(
                f"昨日 OpenAI {alert_source}超过 ${DEFAULT_ALERT_THRESHOLDS['daily_usd']}: "
                f"${alert_cost:.2f} "
                f"(TTS: {log_estimate['tts_count']}, 摘要: {log_estimate['summary_count']}, 播客: {log_estimate['podcast_count']})",
                "WARNING"
            )

    # 4. 输出结构化报告
    logger.info("[4/4] 生成监控报告...")
    report = {
        "timestamp": datetime.now().isoformat(),
        "api_key_valid": rate_limit_info.get("key_valid", False),
        "billing": {
            "hard_limit_usd": subscription.get("hard_limit_usd") if subscription else None,
            "monthly_usage_usd": usage.get("total_usage", 0) / 100 if usage else None,
        },
        "daily_usage": {
            "date": target_date,
            "daily_usage_usd": daily_cost,
            "source": usage_source,
        },
        "log_estimate": log_estimate,
        "thresholds": DEFAULT_ALERT_THRESHOLDS,
    }

    # 保存报告
    report_file = LOGS_DIR / f"openai_usage_{datetime.now().strftime('%Y%m%d')}.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    logger.info(f"报告已保存: {report_file}")
    logger.info("OpenAI 监控完成")


if __name__ == "__main__":
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    main()
