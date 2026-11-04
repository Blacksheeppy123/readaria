"""
结构化 JSON 日志配置

功能：
1. 统一的 JSON 格式日志输出
2. 为 RSS 抓取、API 请求添加上下文追踪
3. 支持不同级别的日志输出（控制台、文件）
4. 包含关键指标（耗时、成功率、错误分布）
"""
import logging
import logging.handlers
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
import traceback

# 东八区时区对象
TZ_CHINA = timezone(timedelta(hours=8))


class JSONFormatter(logging.Formatter):
    """精简字段的 JSON 格式化器"""

    def __init__(self, service_name: str = "readaria"):
        """
        初始化 JSON 格式化器

        Args:
            service_name: 服务名称
        """
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录为 JSON

        Args:
            record: 日志记录

        Returns:
            JSON 格式的日志字符串
        """
        # 使用东八区时间: 年-月-日 时:分:秒
        timestamp = datetime.now(TZ_CHINA).strftime("%Y-%m-%d %H:%M:%S")

        # 提前提取关键信息，确保出现在日志最前面
        extra_from_context = getattr(record, "extra", {}) or {}
        record_dict = record.__dict__

        task_type = None
        trigger_type = None
        if isinstance(extra_from_context, dict):
            task_type = extra_from_context.get("task_type")
            trigger_type = extra_from_context.get("trigger_type")
        # 兼容 logging(..., extra={...}) 直接挂到 record 上的字段
        if task_type is None and isinstance(record_dict, dict):
            task_type = record_dict.get("task_type")
        if trigger_type is None and isinstance(record_dict, dict):
            trigger_type = record_dict.get("trigger_type")

        # 计算更粗粒度的来源字段，便于快速区分 scheduler / api 等
        logger_name = record.name or ""
        component = "api"
        if logger_name.startswith("backend.scheduler"):
            component = "scheduler"
        elif logger_name.startswith("backend.fetcher") or logger_name.startswith("backend.utils.feed_refresher"):
            component = "fetcher"

        # 基础字段（时间 + 级别 + 粗粒度来源）
        log_data = {
            "timestamp": timestamp,
            "level": record.levelname,
            "component": component,
        }

        # 在 message 之前插入关键区分字段，便于快速筛选 scheduler 日志
        if task_type is not None:
            log_data["task_type"] = task_type
        if trigger_type is not None:
            log_data["trigger_type"] = trigger_type

        # 标准消息字段
        log_data["message"] = record.getMessage()

        # 添加由 ContextLogger 注入的上下文字段（如果有）
        if isinstance(extra_from_context, dict):
            log_data.update(extra_from_context)

        # 兼容直接通过 logging.Logger(..., extra={...}) 传入的自定义字段
        # 提取所有非标准属性作为额外上下文，避免遗漏 scheduler 的 task_type 等字段
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "asctime",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
        }
        for key, value in record.__dict__.items():
            if key in log_data:
                continue
            if key in standard_attrs:
                continue
            if key in ("extra",):
                continue
            if key.startswith("_"):
                continue
            log_data[key] = value

        # logger 名称放在最后，方便阅读时先看到业务字段
        log_data["logger"] = logger_name

        # 添加异常信息（如果有）
        if record.exc_info:
            exc_type = record.exc_info[0].__name__
            exc_msg = str(record.exc_info[1])
            log_data.update(
                {
                    "error_type": exc_type,
                    "error_message": exc_msg,
                    "traceback": traceback.format_exception(*record.exc_info),
                }
            )

        return json.dumps(log_data, ensure_ascii=False)


class ContextLogger:
    """带上下文的日志记录器"""

    def __init__(self, logger: logging.Logger):
        """
        初始化上下文日志记录器

        Args:
            logger: Python 标准 logger
        """
        self.logger = logger
        self._context: Dict[str, Any] = {}

    def set_context(self, **kwargs):
        """设置上下文字段"""
        self._context.update(kwargs)

    def clear_context(self):
        """清除上下文"""
        self._context.clear()

    def _log_with_context(self, level: str, msg: str, **kwargs):
        """带上下文的日志记录"""
        extra = {**self._context, **kwargs}
        getattr(self.logger, level)(msg, extra={"extra": extra})

    def debug(self, msg: str, **kwargs):
        """Debug 级别日志"""
        self._log_with_context("debug", msg, **kwargs)

    def info(self, msg: str, **kwargs):
        """Info 级别日志"""
        self._log_with_context("info", msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        """Warning 级别日志"""
        self._log_with_context("warning", msg, **kwargs)

    def error(self, msg: str, **kwargs):
        """Error 级别日志"""
        self._log_with_context("error", msg, **kwargs)

    def critical(self, msg: str, **kwargs):
        """Critical 级别日志"""
        self._log_with_context("critical", msg, **kwargs)


class FeedFetchLogger:
    """RSS 抓取日志记录器（带指标统计）"""

    def __init__(self, logger: ContextLogger):
        """
        初始化抓取日志记录器

        Args:
            logger: 上下文日志记录器
        """
        self.logger = logger
        self.start_time: Optional[float] = None
        self.feed_url: Optional[str] = None
        self.feed_id: Optional[str] = None

    def start_fetch(self, feed_url: str, feed_id: Optional[str] = None):
        """开始抓取"""
        self.start_time = time.time()
        self.feed_url = feed_url
        self.feed_id = feed_id

        self.logger.set_context(
            feed_url=feed_url,
            feed_id=feed_id,
            operation="fetch_feed"
        )

        self.logger.info(
            "开始抓取 RSS 源",
            feed_url=feed_url,
            feed_id=feed_id
        )

    def end_fetch(
        self,
        success: bool,
        article_count: int = 0,
        error_msg: Optional[str] = None,
        status_code: Optional[int] = None
    ):
        """结束抓取"""
        if self.start_time is None:
            return

        duration = time.time() - self.start_time

        log_data = {
            "feed_url": self.feed_url,
            "feed_id": self.feed_id,
            "duration_ms": int(duration * 1000),
            "success": success,
            "article_count": article_count
        }

        if status_code:
            log_data["status_code"] = status_code

        if error_msg:
            log_data["error"] = error_msg

        if success:
            self.logger.info(
                f"抓取成功: {article_count} 篇文章, 耗时 {duration:.2f}s",
                **log_data
            )
        else:
            self.logger.error(
                f"抓取失败: {error_msg or 'Unknown error'}, 耗时 {duration:.2f}s",
                **log_data
            )

        # 清除上下文
        self.logger.clear_context()
        self.start_time = None


class APIRequestLogger:
    """API 请求日志记录器"""

    def __init__(self, logger: ContextLogger):
        """
        初始化 API 请求日志记录器

        Args:
            logger: 上下文日志记录器
        """
        self.logger = logger
        self.start_time: Optional[float] = None

    def start_request(
        self,
        method: str,
        path: str,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        """开始 API 请求"""
        self.start_time = time.time()

        self.logger.set_context(
            operation="api_request",
            method=method,
            path=path,
            user_id=user_id,
            request_id=request_id
        )

        self.logger.info(
            f"API 请求: {method} {path}",
            method=method,
            path=path,
            user_id=user_id,
            request_id=request_id
        )

    def end_request(
        self,
        status_code: int,
        success: bool = True,
        error_msg: Optional[str] = None
    ):
        """结束 API 请求"""
        if self.start_time is None:
            return

        duration = time.time() - self.start_time

        log_data = {
            "duration_ms": int(duration * 1000),
            "status_code": status_code,
            "success": success
        }

        if error_msg:
            log_data["error"] = error_msg

        level = "info" if success else "error"
        getattr(self.logger, level)(
            f"API 响应: {status_code}, 耗时 {duration:.2f}s",
            **log_data
        )

        # 清除上下文
        self.logger.clear_context()
        self.start_time = None


def setup_logging(
    service_name: str = "readaria",
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_json: bool = True,
    enable_console: bool = True
) -> ContextLogger:
    """
    配置结构化日志

    Args:
        service_name: 服务名称
        log_level: 日志级别
        log_file: 日志文件路径（可选）
        enable_json: 是否启用 JSON 格式
        enable_console: 是否启用控制台输出

    Returns:
        ContextLogger 实例
    """
    # 创建根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # 清除现有的 handlers
    root_logger.handlers.clear()

    # 控制台使用更易读的文本格式: [LEVEL] YYYY-MM-DD HH:MM:SS message
    console_formatter = logging.Formatter(
        fmt="[%(levelname)s] %(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件根据需要选择 JSON 或文本格式
    if enable_json:
        file_formatter: logging.Formatter = JSONFormatter(service_name=service_name)
    else:
        file_formatter = logging.Formatter(
            fmt="[%(levelname)s] %(asctime)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # 控制台 handler（总是使用易读格式）
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # 文件 handler（使用 TimedRotatingFileHandler 实现按日期自动切分）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 使用 TimedRotatingFileHandler，在午夜（东八区）自动创建新文件
        # when='midnight': 每天午夜切分
        # interval=1: 每 1 天切分一次
        # backupCount=90: 保留最近 90 天的日志
        # atTime: 在东八区午夜（UTC+8 00:00）切分，相当于 UTC 16:00
        # suffix: 日志文件后缀格式为 YYYY-MM-DD
        from datetime import time as dt_time

        timed_file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_path),
            when='midnight',
            interval=1,
            backupCount=90,
            encoding='utf-8',
            atTime=dt_time(0, 0, 0),  # 本地时间午夜
            utc=False  # 使用本地时间（容器内已配置为东八区）
        )
        # 设置日志文件名后缀格式：原文件名_YYYY-MM-DD.log
        timed_file_handler.suffix = "%Y-%m-%d"
        # 修改 namer 函数，使日期后缀插入到文件名和扩展名之间
        def custom_namer(default_name: str) -> str:
            """自定义日志文件命名：logs/api.log.2025-12-28 → logs/api_2025-12-28.log"""
            parts = default_name.rsplit('.', 2)  # 分割为 ['logs/api', 'log', '2025-12-28']
            if len(parts) == 3:
                base, ext, date = parts
                return f"{base}_{date}.{ext}"
            return default_name

        timed_file_handler.namer = custom_namer
        timed_file_handler.setFormatter(file_formatter)
        root_logger.addHandler(timed_file_handler)

    # 返回上下文 logger
    return ContextLogger(root_logger)


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logger = setup_logging(
        service_name="readaria",
        log_level="INFO",
        enable_json=True,
        enable_console=True
    )

    # 示例1: 基础日志
    logger.info("应用启动", version="1.0.0", env="development")

    # 示例2: RSS 抓取日志
    feed_logger = FeedFetchLogger(logger)
    feed_logger.start_fetch("https://rsshub.app/v2ex/topics/hot", feed_id="feed-123")
    time.sleep(0.5)  # 模拟抓取
    feed_logger.end_fetch(success=True, article_count=10)

    # 示例3: RSS 抓取失败
    feed_logger.start_fetch("https://example.com/feed", feed_id="feed-456")
    time.sleep(0.3)
    feed_logger.end_fetch(success=False, error_msg="HTTP 429", status_code=429)

    # 示例4: API 请求日志
    api_logger = APIRequestLogger(logger)
    api_logger.start_request("GET", "/api/articles", user_id="user-123", request_id="req-abc")
    time.sleep(0.2)
    api_logger.end_request(status_code=200, success=True)

    # 示例5: 异常日志
    try:
        1 / 0
    except Exception as e:
        logger.error("发生异常", error_type="ZeroDivisionError")
        logging.exception("详细异常信息")


def setup_frontend_logging(
    log_file: str = "logs/frontend.log",
    log_level: str = "INFO",
    enable_json: bool = True
) -> logging.Logger:
    """
    配置前端日志记录器（独立于 API 日志）

    功能：
    - 接收来自前端白名单用户的日志
    - 使用 TimedRotatingFileHandler 按日期切分
    - JSON 格式存储，便于分析

    Args:
        log_file: 日志文件路径
        log_level: 日志级别
        enable_json: 是否使用 JSON 格式

    Returns:
        配置好的 Logger 实例
    """
    # 创建独立的 logger（不继承 root logger 配置）
    frontend_logger = logging.getLogger("frontend")
    frontend_logger.setLevel(getattr(logging, log_level.upper()))
    frontend_logger.propagate = False  # 不传播到 root logger

    # 清除现有 handlers
    frontend_logger.handlers.clear()

    # 创建日志目录
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 文件 formatter（JSON 格式）
    if enable_json:
        file_formatter = JSONFormatter(service_name="frontend")
    else:
        file_formatter = logging.Formatter(
            fmt="[%(levelname)s] %(asctime)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # 文件 handler（使用 TimedRotatingFileHandler 实现按日期自动切分）
    from datetime import time as dt_time

    timed_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_path),
        when='midnight',
        interval=1,
        backupCount=90,  # 保留 90 天
        encoding='utf-8',
        atTime=dt_time(0, 0, 0),
        utc=False
    )
    timed_file_handler.suffix = "%Y-%m-%d"

    # 自定义文件命名：frontend.log.2025-12-30 → frontend_2025-12-30.log
    def custom_namer(default_name: str) -> str:
        parts = default_name.rsplit('.', 2)
        if len(parts) == 3:
            base, ext, date = parts
            return f"{base}_{date}.{ext}"
        return default_name

    timed_file_handler.namer = custom_namer
    timed_file_handler.setFormatter(file_formatter)
    frontend_logger.addHandler(timed_file_handler)

    return frontend_logger


# 全局前端日志记录器实例
_frontend_logger = None


def get_frontend_logger() -> logging.Logger:
    """
    获取前端日志记录器单例

    Returns:
        配置好的前端日志记录器
    """
    global _frontend_logger
    if _frontend_logger is None:
        _frontend_logger = setup_frontend_logging()
    return _frontend_logger
