from fastapi import FastAPI, HTTPException, Query, Body, Depends, Header, Request, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response, StreamingResponse, FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import threading
from pydantic import BaseModel, EmailStr, Field
import uvicorn
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sys
import os
import asyncio
from datetime import datetime, timezone
import requests
import httpx
import logging
import time
import hmac
import hashlib
import base64

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from backend.fetcher.rss_fetcher import RSSFetcher
from backend.fetcher.feed_url_manager import FeedURLManager
from backend.nlp.processor import NLPProcessor
from backend.nlp.speech_service import get_speech_service
# Phase 3: 预合成缓存已废弃（v2 MP3 架构迁移）
# from backend.nlp.tts_segment_service import get_cached_segment_path
from backend.storage.database import DatabaseManager
from backend.scheduler.feed_scheduler import FeedScheduler
from backend.utils.url_validator import create_url_validator_from_settings
from backend.utils.html_sanitizer import create_html_sanitizer_from_settings
# Week 5 Cleanup (2025-11-20): WeChatCookieManager import removed - migrated to RSSHub-CookieCloud
from backend.utils.feed_refresher import FeedRefresher  # Week 5 Phase 2
from backend.utils.logger import setup_logging
from backend.utils.whitelist import is_frontend_log_whitelist_user
from core.config.settings import settings, TTS_VOICE_CATALOG
from core.auth import jwt_utils
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ================== 音频播放签名 URL 工具 ==================
# 用于替代 JWT query token，防止令牌泄露到日志和浏览器历史中

_AUDIO_SIG_TTL_SECONDS = 300  # 签名有效期 5 分钟


def _build_audio_signature(podcast_id: int, user_id: str, exp: int, voice: Optional[str] = None) -> str:
    """为给定的 (podcast_id, user_id, exp, voice) 构建 HMAC 签名。"""
    data = f"{podcast_id}:{user_id}:{exp}"
    if voice:
        data += f":{voice}"
    return hmac.new(
        settings.secret_key.encode(),
        data.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def _generate_audio_signature(podcast_id: int, user_id: str, voice: Optional[str] = None) -> tuple[str, int]:
    """生成短期有效的音频播放签名 URL 参数。

    Returns:
        (signature, expiry_timestamp)
    """
    expiry = int(datetime.now(timezone.utc).timestamp()) + _AUDIO_SIG_TTL_SECONDS
    return _build_audio_signature(podcast_id, user_id, expiry, voice), expiry


def _verify_audio_signature(podcast_id: int, user_id: str, sig: str, exp: int, voice: Optional[str] = None) -> bool:
    """验证音频播放签名 URL 参数。

    Returns:
        bool: 签名有效且未过期
    """
    try:
        if not sig or not exp:
            return False
        if datetime.now(timezone.utc).timestamp() > exp:
            return False
        expected_sig = _build_audio_signature(podcast_id, user_id, exp, voice)
        return hmac.compare_digest(expected_sig, sig)
    except Exception:
        return False

# 初始化结构化日志（API）
setup_logging(
    service_name="readaria-api",
    log_level="INFO",
    log_file="logs/api.log",
    enable_json=True,
    enable_console=True
)
logger = logging.getLogger(__name__)

# 初始化JWT配置
jwt_utils.init_jwt_config(
    secret_key=settings.jwt_secret_key,
    algorithm=settings.jwt_algorithm,
    expire_minutes=settings.jwt_access_token_expire_minutes
)
logger.info("JWT配置初始化完成")

# 初始化 API 限流器
def _get_rate_limit_key(request: Request) -> str:
    """限流 key：已认证用 user_id，未认证用 IP"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        user_id = jwt_utils.verify_token(token)
        if user_id:
            return f"user:{user_id}"
    return get_remote_address(request)

limiter = Limiter(key_func=_get_rate_limit_key, default_limits=[settings.rate_limit_default])

# 初始化组件(Week 5: 调整初始化顺序以支持微信 Cookie)
# 1. 先初始化数据库管理器
db_manager = DatabaseManager(pg_config=settings.postgres_config)

# 自托管版：无限功能配额与用量统计
from backend.services.subscription_service import SubscriptionService
subscription_service = SubscriptionService(db_manager)
from backend.services.tts_stable_playback import StableTtsPlaybackManager, get_stable_tts_manager

stable_tts_manager = get_stable_tts_manager(settings)


# 2. 初始化 RSS Fetcher
rss_fetcher = RSSFetcher(
    # Week 4.5: 传递抓取稳定性配置
    max_concurrent_per_host=settings.fetch_max_concurrent_per_host,
    request_interval=settings.fetch_request_interval,
    connect_timeout=5.0,  # 连接超时
    read_timeout=15.0,    # 读取超时
    total_timeout=settings.fetch_timeout,  # 总超时
    enable_adaptive_rate=True  # 启用自适应速率
)

# 4. 初始化其他组件
# 2026-05-18: 本地 RSSHub 已移除，platform_routing / force_local 等配置已废弃
feed_url_manager = FeedURLManager()
logger.info("FeedURLManager 初始化完成: 使用公共 RSSHub 实例")

nlp_processor = NLPProcessor()

# 初始化安全工具 (Week 4.5)
url_validator = create_url_validator_from_settings(settings)
html_sanitizer = create_html_sanitizer_from_settings(settings)

# Week 5 Phase 2: 初始化统一的刷新器
feed_refresher = FeedRefresher(
    rss_fetcher=rss_fetcher,
    feed_url_manager=feed_url_manager,
    nlp_processor=nlp_processor,
    db_manager=db_manager,
    subscription_service=subscription_service
)

# 初始化定时任务调度器
feed_scheduler = FeedScheduler(
    rss_fetcher=rss_fetcher,
    feed_url_manager=feed_url_manager,
    nlp_processor=nlp_processor,
    db_manager=db_manager,
    subscription_service=subscription_service
)

# 定义应用生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器"""
    # 启动时执行
    try:
        feed_scheduler.start()
        logger.info("应用启动完成，定时任务调度器已启动")
    except Exception as e:
        logger.error(f"启动定时任务调度器失败: {str(e)}")

    yield

    # 关闭时执行
    try:
        feed_scheduler.stop()
        logger.info("应用关闭，定时任务调度器已停止")
    except Exception as e:
        logger.error(f"停止定时任务调度器失败: {str(e)}")

    # 关闭数据库连接池
    try:
        db_manager.close_pool()
    except Exception as e:
        logger.error(f"关闭数据库连接池失败: {str(e)}")

# ---- Sentry 错误追踪初始化 ----
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    def _before_send(event, hint):
        # 过滤前端日志上报产生的噪音事件
        transaction = event.get("transaction") or ""
        if "/api/v1/frontend-logs" in transaction:
            return None
        # 过滤 frontend logger 产生的事件
        logger_name = (event.get("extra") or {}).get("logger") or ""
        if logger_name == "frontend":
            return None
        return event

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment="production",
        release=settings.app_version,
        integrations=[
            StarletteIntegration(transaction_style="url"),
            FastApiIntegration(transaction_style="url"),
            LoggingIntegration(event_level=logging.CRITICAL),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        before_send=_before_send,
    )
    logger.info("Sentry 错误追踪已启用")
else:
    logger.info("Sentry DSN 未配置，错误追踪已跳过")

# 创建 FastAPI 应用
app = FastAPI(
    title="Readaria - 个人知识管理系统",
    lifespan=lifespan
)

# CORS 白名单由部署环境显式配置，支持逗号分隔的精确 Origin。
_allowed_cors_origins = [
    origin.strip()
    for origin in settings.cors_allowed_origins.split(",")
    if origin.strip()
]

# 注册限流器
app.state.limiter = limiter

# 自定义限流异常处理器，添加CORS头避免前端CORS错误
def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """处理限流异常，返回带CORS头的429响应"""
    origin = request.headers.get("Origin", "")

    # 检查origin是否在允许列表中（使用与CORS中间件一致的配置）
    if origin in _allowed_cors_origins:
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Silent, Range, If-None-Match",
        }
    else:
        headers = {}

    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests, please slow down"},
        headers=headers
    )

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Silent", "Range", "If-None-Match"],
)

# 数据库连接归还中间件：每个请求结束后将连接归还到连接池
class DBConnectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        finally:
            try:
                db_manager.release_conn()
            except Exception:
                pass

app.add_middleware(DBConnectionMiddleware)

# HTTP Bearer认证方案
security = HTTPBearer()

# ================== Pydantic模型定义 ==================

class RegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    preferred_language: Optional[str] = "en"

class LoginRequest(BaseModel):
    """用户登录请求"""
    username: str
    password: str

class GoogleOAuthRequest(BaseModel):
    """Google OAuth 登录请求"""
    id_token: str

class UserResponse(BaseModel):
    """用户信息响应"""
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_superuser: bool
    preferred_language: Optional[str] = "en"
    auto_podcast_enabled: bool = False
    tts_voice_zh: Optional[str] = None
    tts_voice_en: Optional[str] = None
    auth_provider: Optional[str] = "password"
    is_frontend_log_whitelist_user: bool = False

class TokenResponse(BaseModel):
    """Token响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    is_new_user: Optional[bool] = None


def build_user_response_payload(user: Dict[str, Any]) -> Dict[str, Any]:
    """Attach derived frontend capabilities to the user payload returned to the app."""
    payload = dict(user)
    payload["is_frontend_log_whitelist_user"] = _is_frontend_log_whitelisted_user(user)
    return payload


def _is_frontend_log_whitelisted_user(user: Dict[str, Any]) -> bool:
    """Allow diagnostic-log whitelisting by username, user id, or email."""
    return any(
        is_frontend_log_whitelist_user(user.get(field))
        for field in ("username", "id", "email")
    )

class SavedRequest(BaseModel):
    article_id: Optional[int] = None
    url: Optional[str] = None

class ReadRequest(BaseModel):
    article_id: Optional[int] = None
    url: Optional[str] = None

class FeedbackRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    attach_logs: bool = False
    frontend_logs: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=100)

class AudioPlayHistoryRecord(BaseModel):
    """Record audio play history item"""
    item_type: str  # 'article' or 'podcast'
    item_id: int
    title: Optional[str] = None
    source_name: Optional[str] = None
    duration_seconds: Optional[int] = 0
    played_seconds: Optional[int] = 0
    progress_percentage: Optional[float] = 0
    is_completed: Optional[bool] = False


class QueueItem(BaseModel):
    """Article metadata stored in a synced queue or playback playlist."""
    id: Optional[int] = None
    url: str
    title: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    updated_at: Optional[str] = None
    cover: Optional[str] = None


class QueueUpdateRequest(BaseModel):
    """Full replacement payload for the user's synced listen queue."""
    items: List[QueueItem]


class PlaybackStateUpdateRequest(BaseModel):
    """Full replacement payload for the user's synced playback state."""
    playlist: List[QueueItem] = []
    current_index: int = 0
    current_time: float = 0.0
    total_time: float = 0.0
    current_article: Optional[QueueItem] = None
    is_playing: bool = False
    playback_rate: float = 1.0


class TtsSynthesizeRequest(BaseModel):
    """TTS 语音合成请求"""
    text: str  # 待朗读文本
    article_id: Optional[str] = None  # 文章 ID（可选，支持分段格式如 "123_segment_0"）
    lang: Optional[str] = "auto"  # 语言标识："auto" | "zh" | "en"
    voice: Optional[str] = "default"  # 声线标识："default" | "default_female" | "default_male"

# Week 5 Cleanup (2025-11-20): WeChatCookieRequest model removed
# Reason: Migrated to RSSHub-CookieCloud solution

# ================== 辅助函数 ==================

def _map_article_sources_to_feed_urls(articles: List[Dict[str, Any]], user_feeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将文章的source字段映射回用户订阅的原始feed_url

    背景：系统会将RSSHub URL从公共实例（rsshub.app）转换为本地实例（localhost:1200）进行抓取，
    导致文章的source字段是localhost URL，而用户订阅的feed_url是rsshub.app URL。
    前端通过feed_url匹配source显示来源名称时会失败。

    Args:
        articles: 文章列表
        user_feeds: 用户订阅列表

    Returns:
        更新后的文章列表（source字段已映射）
    """
    from urllib.parse import urlparse

    if not articles or not user_feeds:
        return articles

    # 创建路径到feed_url的映射，以及直接匹配的feed_url集合
    feed_url_set = set()
    path_to_feed_url = {}
    for feed in user_feeds:
        feed_url = feed.get('feed_url')
        if not feed_url:
            continue
        feed_url_set.add(feed_url)
        try:
            parsed = urlparse(feed_url)
            path = parsed.path
            if path:
                path_to_feed_url[path] = feed_url
        except Exception:
            continue

    # 内部/Docker 地址，只有这些地址才需要进行 pathname 映射
    internal_hosts = {'localhost', '127.0.0.1', 'rsshub', 'wechat2rss'}

    # 更新文章的source字段
    for article in articles:
        source = article.get('source')
        if not source:
            continue

        # 如果 source 已经直接匹配某个用户订阅的 feed_url，无需映射
        if source in feed_url_set:
            continue

        try:
            # 提取source的路径
            parsed_source = urlparse(source)
            source_path = parsed_source.path

            # 只有内部抓取地址才进行 pathname 映射，避免不同域名但相同 pathname 的 feed 被错误映射
            if parsed_source.hostname in internal_hosts and source_path in path_to_feed_url:
                article['source'] = path_to_feed_url[source_path]
        except Exception:
            # 解析失败，保持原样
            continue

    return articles

# ================== 认证依赖函数 ==================

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    获取当前登录用户（认证依赖）

    从Authorization header中提取JWT token并验证
    """
    token = credentials.credentials
    user_id = jwt_utils.verify_token(token)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 从数据库获取用户信息
    user = db_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.get('is_active', False):
        raise HTTPException(
            status_code=403,
            detail="Account is disabled"
        )

    return user


async def verify_user_ownership(
    user_id: str,
    current_user: Dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    验证当前用户拥有请求的 user_id 资源（IDOR 防护）
    Superuser 可以访问任何用户的资源
    """
    if current_user['id'] != user_id and not current_user.get('is_superuser', False):
        raise HTTPException(status_code=403, detail="Access denied")
    return current_user


async def require_superuser(
    current_user: Dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """管理员端点保护"""
    if not current_user.get('is_superuser', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ================== 自托管版无限配额依赖（保持既有调用协议） ==================

async def require_tts_quota(current_user: Dict = Depends(get_current_user)) -> Dict[str, Any]:
    """检查用户 TTS 配额"""
    quota = subscription_service.check_tts_quota(current_user['id'])
    if not quota['allowed']:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Daily TTS limit reached",
                "used": quota['used'],
                "limit": quota['limit'],
                "plan": quota['plan'],
                "upgrade_url": "/pricing"
            }
        )
    return current_user


async def require_podcast_quota(current_user: Dict = Depends(get_current_user)) -> Dict[str, Any]:
    """检查用户播客配额"""
    quota = subscription_service.check_podcast_quota(current_user['id'])
    if not quota['allowed']:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Daily podcast limit reached",
                "used": quota['used'],
                "limit": quota['limit'],
                "plan": quota['plan'],
                "upgrade_url": "/pricing"
            }
        )
    return current_user


# 挂载静态文件目录（UI前端） - 暂时禁用，使用Vite dev server
# frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
# if os.path.exists(frontend_path):
#     app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

# ================== 根路径 ==================

@app.get("/", response_class=HTMLResponse)
@app.head("/", response_class=HTMLResponse)
async def root():
    """
    API根路径，返回服务信息
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Readaria RSS Manager</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .info { background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }
            a { color: #0066cc; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>Readaria RSS Manager</h1>
        <div class="info">
            <p><strong>Status:</strong> Running</p>
            <p><strong>Version:</strong> 1.0.0</p>
            <p><strong>API Documentation:</strong> <a href="/docs">/docs</a></p>
        </div>
        <p>Welcome to Readaria RSS Manager API. Visit <a href="/docs">/docs</a> for interactive API documentation.</p>
    </body>
    </html>
    """

# ================== 用户认证API (Week 3) ==================

@app.post("/api/auth/register", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
async def register(request: Request, reg_req: RegisterRequest):
    """
    用户注册

    创建新用户账号并返回access token
    """
    try:
        # 检查用户名是否已存在
        if db_manager.user_exists(username=reg_req.username):
            raise HTTPException(status_code=400, detail="Username already taken")

        # 检查邮箱是否已存在
        if db_manager.user_exists(email=reg_req.email):
            raise HTTPException(status_code=400, detail="Email already registered")

        # 验证密码强度
        if len(reg_req.password) < settings.password_min_length:
            raise HTTPException(status_code=400, detail=f"Password must be at least {settings.password_min_length} characters")
        if settings.password_require_mixed:
            import re
            if not re.search(r'[A-Za-z]', reg_req.password) or not re.search(r'[0-9]', reg_req.password):
                raise HTTPException(status_code=400, detail="Password must contain both letters and numbers")

        # 哈希密码
        password_hash = jwt_utils.get_password_hash(reg_req.password)

        # 创建用户（自托管版注册默认开放）
        user_id = db_manager.create_user(
            username=reg_req.username,
            email=reg_req.email,
            password_hash=password_hash,
            full_name=reg_req.full_name,
            preferred_language=reg_req.preferred_language,
            auth_provider='password'
        )

        # 生成JWT token
        token = jwt_utils.create_user_token(
            user_id=user_id,
            username=reg_req.username,
            email=reg_req.email
        )

        # 获取用户信息
        user = db_manager.get_user_by_id(user_id)

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse(**build_user_response_payload(user)),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"用户注册失败: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed, please try again")

@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
async def login(request: Request, login_req: LoginRequest):
    """
    用户登录

    验证用户名和密码，返回access token
    """
    try:
        # 获取用户信息（含password_hash）
        user = db_manager.get_user_by_username(login_req.username)

        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

        # 验证密码
        if not jwt_utils.verify_password(login_req.password, user['password_hash']):
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )

        # 检查用户是否被禁用
        if not user.get('is_active', False):
            raise HTTPException(
                status_code=403,
                detail="Account is disabled"
            )

        # 生成JWT token
        token = jwt_utils.create_user_token(
            user_id=user['id'],
            username=user['username'],
            email=user['email']
        )

        # 移除敏感信息
        user_info = {k: v for k, v in user.items() if k != 'password_hash'}

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse(**build_user_response_payload(user_info))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"用户登录失败: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed, please try again")

@app.post("/api/auth/google", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
async def google_oauth_login(request: Request, oauth_req: GoogleOAuthRequest):
    """
    Google OAuth login/register

    Verifies Google ID token, creates account if needed, returns JWT.
    """
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth is not configured")

    try:
        # Verify Google ID token via Google's tokeninfo endpoint
        async with httpx.AsyncClient() as client:
            verify_resp = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": oauth_req.id_token},
                timeout=10
            )

        if verify_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google token")

        google_info = verify_resp.json()

        # Verify audience matches our client ID
        if google_info.get("aud") != settings.google_oauth_client_id:
            raise HTTPException(status_code=401, detail="Token audience mismatch")

        email = google_info.get("email")
        if not email or google_info.get("email_verified") != "true":
            raise HTTPException(status_code=401, detail="Email not verified")

        # Check if user exists by email
        user = db_manager.get_user_by_email(email)
        is_new_user = False

        if user:
            # Existing user — login
            if not user.get('is_active', False):
                raise HTTPException(status_code=403, detail="Account is disabled")
        else:
            # New user — register
            is_new_user = True
            name = google_info.get("name", "")
            # Generate username from email prefix, ensure uniqueness
            base_username = email.split("@")[0][:20].replace(".", "_").replace("+", "_")
            username = base_username
            counter = 1
            while db_manager.user_exists(username=username):
                username = f"{base_username}_{counter}"
                counter += 1

            # Create user with a random unusable password
            import secrets
            random_hash = jwt_utils.get_password_hash(secrets.token_urlsafe(32))

            user_id = db_manager.create_user(
                username=username,
                email=email,
                password_hash=random_hash,
                full_name=name,
                preferred_language='en',
                auth_provider='google'
            )
            user = db_manager.get_user_by_id(user_id)

        # Generate JWT token
        token = jwt_utils.create_user_token(
            user_id=user['id'],
            username=user['username'],
            email=user['email']
        )

        user_info = {k: v for k, v in user.items() if k != 'password_hash'}

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse(**build_user_response_payload(user_info)),
            "is_new_user": is_new_user,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google OAuth failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Google login failed")

@app.get("/api/auth/google/client-id")
@limiter.limit("10/minute")
async def get_google_client_id(request: Request):
    """Return Google OAuth client ID for frontend (public endpoint)"""
    if not settings.google_oauth_client_id:
        return {"client_id": None}
    return {"client_id": settings.google_oauth_client_id}

@app.get("/api/auth/me")
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """
    获取当前登录用户信息

    需要在Header中提供有效的JWT token:
    Authorization: Bearer <token>

    同时返回自托管版无限配额与用量信息。
    """
    user_response = UserResponse(**build_user_response_payload(current_user)).model_dump()
    # 附加订阅信息
    try:
        user_response['subscription'] = subscription_service.get_subscription_summary(current_user['id'])
    except Exception as e:
        logger.warning(f"获取订阅信息失败: {e}")
        user_response['subscription'] = None
    return user_response


class UpdateLanguageRequest(BaseModel):
    """更新用户语言偏好请求"""
    preferred_language: str


@app.patch("/api/auth/me/language")
async def update_user_language(
    req: UpdateLanguageRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    更新当前登录用户的语言偏好

    支持的 language 值: zh, en, ja, ko, fr, de, es, ru 等
    """
    valid_languages = {'zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'}
    language = req.preferred_language
    if language not in valid_languages:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language}")

    success = db_manager.update_user(current_user['id'], preferred_language=language)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update language preference")

    return {"status": "success", "preferred_language": language}


class UpdateAutoPodcastRequest(BaseModel):
    """更新用户自动播客设置请求"""
    auto_podcast_enabled: bool


@app.patch("/api/auth/me/auto-podcast")
async def update_user_auto_podcast(
    req: UpdateAutoPodcastRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    更新当前登录用户的自动播客生成设置
    """
    success = db_manager.update_user(
        current_user['id'],
        auto_podcast_enabled=req.auto_podcast_enabled
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update auto podcast setting")

    return {"status": "success", "auto_podcast_enabled": req.auto_podcast_enabled}


class UpdateTtsVoicesRequest(BaseModel):
    """更新用户 TTS 音色偏好请求（字段缺省=不修改，显式 null=恢复默认）"""
    tts_voice_zh: Optional[str] = None
    tts_voice_en: Optional[str] = None


def _validate_catalog_voice(voice: Optional[str], lang: str) -> Optional[str]:
    """校验 voice 必须存在于音色目录对应语言分组，非法则抛 400。"""
    if voice is None:
        return None
    if any(v["id"] == voice for v in TTS_VOICE_CATALOG.get(lang, [])):
        return voice
    raise HTTPException(status_code=400, detail=f"Unsupported voice for {lang}: {voice}")


@app.patch("/api/auth/me/tts-voices")
async def update_user_tts_voices(
    req: UpdateTtsVoicesRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    更新当前登录用户的 TTS 朗读音色偏好

    - 只更新请求体中出现的字段（model_fields_set 区分"未传"与"显式 null"）
    - 字段值为 null 表示恢复系统默认音色
    - voice id 必须在 GET /api/v1/tts/voices 目录内且语言匹配
    """
    updates: Dict[str, Any] = {}
    if "tts_voice_zh" in req.model_fields_set:
        updates["tts_voice_zh"] = _validate_catalog_voice(req.tts_voice_zh, "zh")
    if "tts_voice_en" in req.model_fields_set:
        updates["tts_voice_en"] = _validate_catalog_voice(req.tts_voice_en, "en")
    if not updates:
        raise HTTPException(status_code=400, detail="No tts voice field provided")

    success = db_manager.update_user(current_user["id"], **updates)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update tts voice preference")

    return {"status": "success", **updates}


@app.post("/api/auth/logout")
async def logout(current_user: Dict = Depends(get_current_user)):
    """
    用户登出

    前端需要删除本地存储的token
    后端暂时不做token黑名单处理（Week 3 MVP）
    """
    return {"status": "success", "message": "Logged out successfully"}


class DeleteAccountRequest(BaseModel):
    """账号删除请求"""
    password: str = ""


@app.delete("/api/auth/account")
async def delete_account(
    req: DeleteAccountRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    删除当前用户账号及所有关联数据（GDPR Article 17）

    需要密码确认，级联删除所有用户数据
    """
    try:
        # 通过用户名获取含 password_hash 的完整用户信息
        user = db_manager.get_user_by_username(current_user['username'])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # 密码确认：有密码则验证，无密码则允许（兼容 OAuth 用户无可用密码的情况）
        if req.password:
            if not jwt_utils.verify_password(req.password, user['password_hash']):
                raise HTTPException(status_code=401, detail="Password verification failed")

        # 级联删除用户及所有关联数据
        success = db_manager.delete_user(current_user['id'])
        if not success:
            raise HTTPException(status_code=500, detail="Account deletion failed")

        logger.info(f"用户 {current_user['username']} 已删除账号 (GDPR)")
        return {"status": "success", "message": "Account and all associated data have been deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"账号删除失败: {str(e)}")
        raise HTTPException(status_code=500, detail="Account deletion failed")


@app.get("/api/auth/data-export")
def export_user_data(current_user: Dict = Depends(get_current_user)):
    """Export all user data as JSON (GDPR Article 20 - Data Portability)"""
    try:
        user_id = current_user["id"]

        # Collect all user data
        user_data = {
            "exported_at": datetime.now().isoformat(),
            "user": {
                "id": current_user.get("id"),
                "username": current_user.get("username"),
                "email": current_user.get("email"),
            },
            "feeds": db_manager.get_user_feeds(user_id),
            "saved_articles": [],
            "read_articles": [],
        }

        # Get saved articles
        try:
            saved = db_manager.list_saved_articles(user_id, limit=10000, offset=0)
            user_data["saved_articles"] = saved if saved else []
        except Exception as e:
            logger.warning(f"Failed to export saved articles for user {user_id}: {e}")

        import json
        content = json.dumps(user_data, ensure_ascii=False, indent=2, default=str)

        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="readaria_data_export_{user_id}.json"'
            }
        )
    except Exception as e:
        logger.error(f"Data export failed: {e}")
        raise HTTPException(status_code=500, detail="Data export failed")


@app.post("/feeds/fetch")
async def fetch_feeds(feed_urls: List[str], current_user: Dict = Depends(get_current_user)):
    """获取RSS源内容"""
    try:
        articles = await rss_fetcher.fetch_multiple_feeds(feed_urls)
        return {"status": "success", "articles": articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/articles/process")
async def process_article(article: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    """处理文章"""
    try:
        user_language = current_user.get('preferred_language', 'en')
        # NLP处理
        processed_article = nlp_processor.process_article(article, language=user_language)

        # 存储文章（PostgreSQL 同时提供搜索索引）
        db_manager.store_article(processed_article)

        return {"status": "success", "article": processed_article}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/articles/search")
async def search_articles(query: str, size: int = 10, current_user: Dict = Depends(get_current_user)):
    """
    搜索文章（仅限当前登录用户订阅范围），使用 PostgreSQL 全文搜索。
    """
    try:
        # 获取用户的订阅源列表（用于后续 source → feed_url 映射）
        user_feeds = db_manager.get_user_feeds(current_user['id'])
        if not user_feeds:
            return {"status": "success", "results": []}

        # 在用户订阅范围内使用 PostgreSQL 搜索
        results = db_manager.search_user_articles_pg(
            current_user['id'],
            query,
            limit=size,
            offset=0,
            language=current_user.get('preferred_language', 'en')
        )

        # 将文章的 source 字段映射回用户订阅的原始 feed_url
        results = _map_article_sources_to_feed_urls(results, user_feeds)

        return {"status": "success", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles/by-url")
async def get_article_by_url(url: str, current_user: Dict = Depends(get_current_user)):
    """根据URL获取文章详情（限当前用户订阅范围）"""
    try:
        article = db_manager.get_user_article_by_url(
            current_user['id'],
            url,
            language=current_user.get('preferred_language', 'en')
        )
        if not article:
            # 兜底：全局查询（兼容共享文章场景）
            article = db_manager.get_article_by_url(url)
        if article:
            return {"status": "success", "article": article}
        else:
            raise HTTPException(status_code=404, detail="文章未找到")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/articles/top")
async def get_top_news(days: int = Query(7, ge=1, le=365), current_user: Dict = Depends(get_current_user)):
    """获取热门新闻"""
    try:
        results = db_manager.get_top_news(days)
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 删除 /knowledge/network 接口

@app.get("/articles/by_source")
async def get_articles_by_source(
    source: str = Query(None, description="频道/来源，可选"),
    only_summary: bool = Query(False, description="是否只返回摘要"),
    order_by: str = Query("published_at", description="排序字段"),
    desc: bool = Query(True, description="是否倒序"),
    limit: int = Query(10, description="返回数量"),
    current_user: Dict = Depends(get_current_user)
):
    """分频道/来源获取最新文章，支持摘要/全文、排序（限当前用户订阅范围）"""
    try:
        # 获取用户的所有 feed_id，限定查询范围
        user_feeds = db_manager.get_user_feeds(current_user['id'])
        if not user_feeds:
            return {"status": "success", "results": []}

        # 使用用户的 feed_url 列表来过滤 source
        user_feed_urls = [f['feed_url'] for f in user_feeds]
        all_results = db_manager.get_articles_by_source(
            source=source,
            only_summary=only_summary,
            order_by=order_by,
            desc=desc,
            limit=limit
        )
        # 过滤：只返回 source 在用户订阅范围内的文章
        feed_url_set = set(user_feed_urls)
        results = [a for a in all_results if a.get('source') in feed_url_set] if all_results else []
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/feeds")
def get_user_feeds(user_id: str, current_user: Dict = Depends(verify_user_ownership)):
    """获取用户所有订阅源"""
    try:
        feeds = db_manager.get_user_feeds(user_id)
        return {"status": "success", "feeds": feeds}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/user/{user_id}/feeds")
def create_user_feed(
    user_id: str,
    feed: dict = Body(...),
    background_tasks: BackgroundTasks = None,
    current_user: Dict = Depends(verify_user_ownership)
):
    """添加用户订阅源 (Week 4.5: 添加 URL 安全验证)"""
    try:
        feed_name = feed.get("feed_name")
        feed_url = feed.get("feed_url")
        if not feed_name or not feed_url:
            raise HTTPException(status_code=400, detail="feed_name 和 feed_url 必填")

        # 2026-05-18: 先 normalize 已退役的本地 RSSHub hosts，再验证
        feed_url = feed_url_manager.get_optimal_url(feed_url)
        # Week 4.5: URL 安全验证
        # 检查 RSSHub URL 是否在白名单内
        is_rsshub_url = 'rsshub' in feed_url.lower()
        is_valid, normalized_url, error_msg = url_validator.validate_and_normalize(
            feed_url,
            check_rsshub_host=is_rsshub_url
        )

        if not is_valid:
            raise HTTPException(status_code=403, detail=f"URL 验证失败: {error_msg}")

        # 使用归一化后的 URL
        # Fix 1 (2026-05-11): 拆分快慢路径 —— 仅同步执行 INSERT user_feeds 并立即返回，
        # 把 INSERT articles + user_article_refs(~1,426 行)挪到 BackgroundTasks，
        # 避免 onboarding 4 个 feed 串行链接 5,000+ 行导致 30s+ 阻塞响应。
        feed_id, is_existing = db_manager.create_user_feed_minimal(user_id, feed_name, normalized_url)

        # Phase 2 P1: 新 feed 添加成功后异步触发一次 RSS 抓取
        # Fix 1: 同时在后台把全局文章池里已有的同源文章链接到当前用户
        if not is_existing and background_tasks:
            def _link_global_articles_in_background(uid=user_id, fid=feed_id, furl=normalized_url):
                # 在后台线程池里运行，需手动管理连接池里的 thread-local 连接
                try:
                    with db_manager.connection_scope():
                        db_manager.link_global_articles_to_feed(uid, fid, furl)
                except Exception as link_exc:
                    logger.warning(
                        f"[background_link] 链接全局文章失败 user_id={uid} feed_id={fid}: {link_exc}"
                    )

            background_tasks.add_task(_link_global_articles_in_background)

            background_tasks.add_task(
                feed_refresher.refresh_single_feed,
                user_id=user_id,
                feed_id=feed_id,
                feed_url=normalized_url,
                feed_name=feed_name
            )

        return {
            "status": "success",
            "feed_id": feed_id,
            "normalized_url": normalized_url,
            "is_existing": is_existing
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建订阅失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/user/{user_id}/feeds/{feed_id}")
def update_user_feed(user_id: str, feed_id: int, feed: dict = Body(...), current_user: Dict = Depends(verify_user_ownership)):
    """修改用户订阅源 (Week 4.5: 添加 URL 安全验证)"""
    try:
        feed_name = feed.get("feed_name")
        feed_url = feed.get("feed_url")
        if not feed_name or not feed_url:
            raise HTTPException(status_code=400, detail="feed_name 和 feed_url 必填")

        # 2026-05-18: 先 normalize 已退役的本地 RSSHub hosts，再验证
        feed_url = feed_url_manager.get_optimal_url(feed_url)
        # Week 4.5: URL 安全验证
        is_rsshub_url = 'rsshub' in feed_url.lower()
        is_valid, normalized_url, error_msg = url_validator.validate_and_normalize(
            feed_url,
            check_rsshub_host=is_rsshub_url
        )

        if not is_valid:
            raise HTTPException(status_code=403, detail=f"URL 验证失败: {error_msg}")

        ok = db_manager.update_user_feed(feed_id, feed_name, normalized_url, user_id=user_id)
        return {"status": "success" if ok else "not_found", "normalized_url": normalized_url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新订阅失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/user/{user_id}/feeds/{feed_id}")
def delete_user_feed(user_id: str, feed_id: int, current_user: Dict = Depends(verify_user_ownership)):
    """删除用户订阅源"""
    try:
        ok = db_manager.delete_user_feed(feed_id, user_id=user_id)
        return {"status": "success" if ok else "not_found"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== OPML Import/Export ==================

@app.get("/api/user/{user_id}/feeds/opml/export")
def export_opml(user_id: str, current_user: Dict = Depends(verify_user_ownership)):
    """Export user feeds as OPML file"""
    try:
        feeds = db_manager.get_user_feeds(user_id)
        username = current_user.get("username", user_id)

        opml = ET.Element('opml', version='2.0')
        head = ET.SubElement(opml, 'head')
        title_el = ET.SubElement(head, 'title')
        title_el.text = f'Readaria Feeds - {username}'
        date_el = ET.SubElement(head, 'dateCreated')
        date_el.text = datetime.now().isoformat()

        body = ET.SubElement(opml, 'body')

        # Group feeds by category (inferred from URL patterns)
        categories = {}
        for feed in feeds:
            feed_url = feed.get('feed_url', '').lower()
            if any(kw in feed_url for kw in ['youtube', 'bilibili']):
                cat = 'Videos'
            elif any(kw in feed_url for kw in ['podcast', 'xiaoyuzhou']):
                cat = 'Podcasts'
            elif 'wechat' in feed_url:
                cat = 'WeChat'
            else:
                cat = 'Articles'
            categories.setdefault(cat, []).append(feed)

        for cat_name, cat_feeds in sorted(categories.items()):
            cat_outline = ET.SubElement(body, 'outline', text=cat_name)
            for feed in sorted(cat_feeds, key=lambda x: x.get('feed_name', '')):
                ET.SubElement(cat_outline, 'outline',
                              text=feed.get('feed_name', 'Unknown'),
                              title=feed.get('feed_name', 'Unknown'),
                              type='rss',
                              xmlUrl=feed.get('feed_url', ''),
                              htmlUrl=feed.get('feed_url', ''))

        rough_xml = ET.tostring(opml, encoding='unicode')
        pretty_xml = minidom.parseString(rough_xml).toprettyxml(indent="  ", encoding="UTF-8")

        return Response(
            content=pretty_xml,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="readaria_feeds_{username}.opml"'
            }
        )
    except Exception as e:
        logger.error(f"OPML export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/user/{user_id}/feeds/opml/import")
@limiter.limit(settings.rate_limit_feed_refresh)
async def import_opml(request: Request, user_id: str, file: UploadFile = File(...), current_user: Dict = Depends(verify_user_ownership)):
    """Import feeds from OPML file"""
    try:
        content = await file.read()

        # Validate file size (1MB limit)
        if len(content) > 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 1MB)")
        try:
            content_str = content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = content.decode('latin-1')

        # Parse OPML
        try:
            root = ET.fromstring(content_str)
        except ET.ParseError as e:
            raise HTTPException(status_code=400, detail=f"Invalid OPML format: {e}")

        # Extract feeds from all outline elements with xmlUrl
        parsed_feeds = []
        for outline in root.iter('outline'):
            xml_url = outline.get('xmlUrl')
            if xml_url:
                name = outline.get('text') or outline.get('title') or 'Unknown Feed'
                parsed_feeds.append({'name': name, 'url': xml_url})

        if not parsed_feeds:
            raise HTTPException(status_code=400, detail="No feeds found in OPML file")

        # Get existing feeds to detect duplicates
        existing_feeds = db_manager.get_user_feeds(user_id)
        existing_urls = {f['feed_url'].lower().rstrip('/') for f in existing_feeds}

        imported = []
        skipped = []
        failed = []

        for feed in parsed_feeds:
            feed_url = feed['url'].strip()
            feed_name = feed['name'].strip()

            # Skip duplicates
            if feed_url.lower().rstrip('/') in existing_urls:
                skipped.append({'name': feed_name, 'url': feed_url, 'reason': 'duplicate'})
                continue

            try:
                # 2026-05-18: 先 normalize 已退役的本地 RSSHub hosts，再验证
                feed_url = feed_url_manager.get_optimal_url(feed_url)
                # URL validation
                is_rsshub_url = 'rsshub' in feed_url.lower()
                is_valid, normalized_url, error_msg = url_validator.validate_and_normalize(
                    feed_url, check_rsshub_host=is_rsshub_url
                )

                if not is_valid:
                    skipped.append({'name': feed_name, 'url': feed_url, 'reason': error_msg})
                    continue

                feed_id, _ = db_manager.create_user_feed(user_id, feed_name, normalized_url)
                imported.append({'name': feed_name, 'url': normalized_url, 'feed_id': feed_id})
                existing_urls.add(normalized_url.lower().rstrip('/'))
            except Exception as e:
                failed.append({'name': feed_name, 'url': feed_url, 'reason': str(e)})

        return {
            "status": "success",
            "total": len(parsed_feeds),
            "imported": len(imported),
            "skipped": len(skipped),
            "failed": len(failed),
            "details": {
                "imported": imported,
                "skipped": skipped,
                "failed": failed
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OPML import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/user/{user_id}/fetch_feeds")
async def fetch_user_feeds(user_id: str, current_user: Dict = Depends(verify_user_ownership)):
    """抓取该用户所有订阅源"""
    try:
        feeds = db_manager.get_user_feeds(user_id)
        feed_urls = [f['feed_url'] for f in feeds]
        if not feed_urls:
            return {"status": "empty", "msg": "该用户没有订阅任何源"}
        articles = await rss_fetcher.fetch_multiple_feeds(feed_urls)
        return {"status": "success", "count": len(articles), "articles": articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== 新增RSS管理UI专用接口 ==================


@app.post("/api/feeds/test")
async def test_feed_url(data: dict = Body(...), current_user: Dict = Depends(get_current_user)):
    """测试RSS源URL是否有效"""
    feed_url = data.get("feed_url")
    if not feed_url:
        raise HTTPException(status_code=400, detail="feed_url 必填")

    try:
        # 2026-05-18: 先 normalize 已退役的本地 RSSHub hosts，再验证
        feed_url = feed_url_manager.get_optimal_url(feed_url)
        # SSRF 防护：验证用户提供的 URL
        # 检查 RSSHub URL 是否在白名单内（与保存/导入保持一致）
        is_rsshub_url = 'rsshub' in feed_url.lower()
        is_valid, normalized_url, error_msg = url_validator.validate_and_normalize(
            feed_url,
            check_rsshub_host=is_rsshub_url
        )
        if not is_valid:
            return {"status": "error", "message": f"URL 不安全: {error_msg}", "optimal_url": feed_url}

        # 获取优化后的URL
        optimal_url = feed_url_manager.get_optimal_url(normalized_url)

        # 检查是否是问题路由
        route_info = feed_url_manager.parse_rsshub_route(normalized_url)
        is_problematic = False
        issues = []

        if route_info:
            platform = route_info['platform']
            problematic_info = feed_url_manager.is_problematic_route(platform)
            if problematic_info:
                is_problematic = True
                issues = problematic_info.get('issues', [])

        # 测试连接（在线程池中运行避免阻塞事件循环）
        # 禁用重定向防止 SSRF 绕过：攻击者提交合法 URL 后返回 302 跳转到内网
        try:
            response = await run_in_threadpool(
                requests.get, optimal_url, timeout=15, allow_redirects=False
            )
            if response.status_code == 200:
                content = response.text.lower()
                if 'rss' in content or '<?xml' in content:
                    item_count = response.text.count('<item>')
                    # Extract feed title from XML
                    feed_title = None
                    try:
                        import re
                        # Try <title> inside <channel> (RSS 2.0)
                        title_match = re.search(r'<channel[^>]*>.*?<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', response.text, re.DOTALL | re.IGNORECASE)
                        if not title_match:
                            # Try Atom <title>
                            title_match = re.search(r'<feed[^>]*>.*?<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', response.text, re.DOTALL | re.IGNORECASE)
                        if title_match:
                            feed_title = title_match.group(1).strip()
                    except Exception:
                        pass
                    return {
                        "status": "success",
                        "message": f"RSS源有效，包含 {item_count} 个条目",
                        "optimal_url": optimal_url,
                        "feed_title": feed_title,
                        "item_count": item_count,
                        "is_problematic": is_problematic,
                        "issues": issues
                    }
                else:
                    return {
                        "status": "warning",
                        "message": "URL可访问但内容不像RSS格式",
                        "optimal_url": optimal_url,
                        "is_problematic": is_problematic,
                        "issues": issues
                    }
            elif response.status_code in (403, 429):
                return {
                    "status": "warning",
                    "message": f"访问受限/频率限制: {response.status_code}",
                    "optimal_url": optimal_url,
                    "is_problematic": is_problematic,
                    "issues": issues + ["rate_limited_or_forbidden"]
                }
            else:
                return {
                    "status": "error",
                    "message": f"HTTP错误: {response.status_code}",
                    "optimal_url": optimal_url,
                    "is_problematic": is_problematic,
                    "issues": issues
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"连接失败: {str(e)}",
                "optimal_url": optimal_url,
                "is_problematic": is_problematic,
                "issues": issues
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/{user_id}/feeds/refresh")
async def refresh_user_feeds(
    user_id: str,
    async_mode: bool = Query(True, description="是否后台异步刷新(默认true)"),
    feed_ids: Optional[List[int]] = Body(None, embed=False),
    current_user: Dict = Depends(verify_user_ownership)
):
    """
    刷新用户的RSS源(可指定特定源ID)
    Week 5 Phase 2: 使用统一的 FeedRefresher

    请求体支持两种格式:
    1. 数组形式: [1, 2, 3]
    2. 对象形式: {"feed_ids": [1, 2, 3]}
    """
    try:
        feeds = db_manager.get_user_feeds(user_id)

        # 如果指定了feed_ids,则只刷新指定的源
        if feed_ids:
            feeds = [f for f in feeds if f['id'] in feed_ids]

        if not feeds:
            return {"status": "empty", "message": "没有找到要刷新的订阅源"}

        async def _do_refresh():
            # Week 5 Phase 2: 使用统一的刷新函数
            results = await feed_refresher.refresh_feeds(
                feeds=feeds,
                enable_logging=True,   # 手动刷新启用更新日志
                check_existence=True   # 启用去重优化
            )

            success_count = len([r for r in results if r['status'] == 'success'])
            return {
                "status": "completed",
                "total_feeds": len(results),
                "success_count": success_count,
                "results": results
            }

        if async_mode:
            def _runner():
                try:
                    asyncio.run(_do_refresh())
                except Exception as e:
                    logger.error(f"异步刷新任务异常: {e}")
            threading.Thread(target=_runner, daemon=True).start()
            return {"status": "accepted", "message": "刷新任务已在后台启动", "feeds": [f['id'] for f in feeds]}

        # 同步执行
        return await _do_refresh()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/user/{user_id}/feeds/refresh/status")
def get_refresh_status(user_id: str, current_user: Dict = Depends(verify_user_ownership)):
    """返回该用户所有订阅源最近一次刷新状态"""
    try:
        data = db_manager.get_latest_feed_update_status_for_user(user_id)
        return {"status": "success", "results": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/feeds/articles")
async def get_user_feed_articles(
    user_id: str,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    feed_id: Optional[int] = Query(None, description="指定订阅源ID"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    source: Optional[str] = Query(None, description="来源过滤（可选，通常为频道/源标识）"),
    read: Optional[str] = Query(None, description="阅读状态过滤: read/unread"),
    order_by: str = Query(
        "published_at",
        description="排序字段: published_at(发布时间)/updated_at(更新时间)",
    ),
    sort: str = Query("desc", description="排序方向: asc/desc"),
    current_user: Dict = Depends(verify_user_ownership)
):
    """获取用户订阅源的文章列表（分页，支持排序）"""
    try:
        # 首先获取该用户的所有订阅源ID
        user_feeds = db_manager.get_user_feeds(user_id)
        if not user_feeds:
            # 用户没有订阅源，返回空列表
            return {
                "status": "success",
                "articles": [],
                "overview": {
                    "today_ready_count": 0,
                },
                "pagination": {
                    "page": page,
                    "size": size,
                    "total": 0,
                    "playable_total": 0,
                    "pages": 0,
                },
            }

        user_feed_ids = [feed["id"] for feed in user_feeds]
        user_language = current_user.get('preferred_language', 'en')

        # 统一读取阅读过滤参数
        read_filter = read if read in ("read", "unread") else None
        offset = (page - 1) * size

        # 统一处理排序参数（只允许后端已支持的字段）
        allowed_order_fields = {"updated_at", "published_at"}
        if order_by not in allowed_order_fields:
            order_by = "updated_at"
        desc = sort.lower() != "asc"

        if search:
            # ES 搜索并过滤，只保留用户订阅范围
            user_feed_urls = [f["feed_url"] for f in user_feeds]
            es_results = db_manager.search_articles_scoped(search, size, user_feed_urls)
            if not es_results:
                # PG 模糊兜底，限定用户范围
                articles = db_manager.search_user_articles_pg(
                    user_id, search, limit=size, offset=offset
                )
                total = len(articles)
            else:
                articles = es_results
                total = len(articles)

            # 搜索结果同样需要将 source 映射回用户订阅的原始 feed_url
            articles = _map_article_sources_to_feed_urls(articles, user_feeds)
        else:
            # 无搜索时的获取逻辑
            # 使用按来源/订阅源获取接口，但限制在用户的订阅源范围内
            if feed_id and feed_id not in user_feed_ids:
                # 请求的 feed_id 不属于该用户，返回空
                return {
                    "status": "success",
                    "articles": [],
                    "overview": {
                        "today_ready_count": 0,
                    },
                    "pagination": {
                        "page": page,
                        "size": size,
                        "total": 0,
                        "playable_total": 0,
                        "pages": 0,
                    },
                }

            # 直接按 feed_id / source 交给数据层处理，保持用户作用域
            results = db_manager.get_user_articles(
                user_id=user_id,
                feed_id=feed_id,
                source=source,
                only_summary=True,
                order_by=order_by,
                desc=desc,
                limit=size,
                offset=offset,
                read_filter=read_filter,
                language=user_language,
            )
            articles = _map_article_sources_to_feed_urls(results, user_feeds)
            stats = db_manager.get_user_articles_stats(
                user_id=user_id,
                feed_id=feed_id,
                source=source,
                read_filter=read_filter,
                language=user_language,
            )
            total = stats["total"]
            playable_total = stats["playable_total"]

        if search:
            playable_total = sum(
                1
                for article in articles
                if str(article.get("content") or "").strip() or str(article.get("summary") or "").strip()
            )

        overview = db_manager.get_user_feed_overview_stats(
            user_id=user_id,
            feed_id=feed_id,
            source=source,
            language=user_language,
        )

        return {
            "status": "success",
            "articles": articles,
            "overview": overview,
            "pagination": {
                "page": page,
                "size": size,
                "total": total,
                "playable_total": playable_total,
                "pages": (total + size - 1) // size,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/feeds/stats")
def get_user_feeds_stats(user_id: str, current_user: Dict = Depends(verify_user_ownership)):
    """获取用户订阅源统计信息"""
    try:
        feeds = db_manager.get_user_feeds(user_id)

        # 分析订阅源
        feed_urls = [f['feed_url'] for f in feeds]
        stats = feed_url_manager.analyze_feed_list(feed_urls)

        # 计算每个源的状态
        feed_stats = []
        for feed in feeds:
            route_info = feed_url_manager.parse_rsshub_route(feed['feed_url'])
            is_rsshub = route_info is not None

            problematic_info = {}
            if is_rsshub:
                platform = route_info['platform']
                problematic_info = feed_url_manager.is_problematic_route(platform)

            feed_stats.append({
                "id": feed['id'],
                "feed_name": feed['feed_name'],
                "feed_url": feed['feed_url'],
                "is_rsshub": is_rsshub,
                "platform": route_info['platform'] if route_info else 'rss',
                "requires_auth": feed_url_manager.requires_authentication(route_info['platform']) if route_info else False,
                "is_problematic": bool(problematic_info),
                "issues": problematic_info.get('issues', []) if problematic_info else []
            })

        return {
            "status": "success",
            "overview": stats,
            "feeds": feed_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== 收藏与阅读接口 (Week 3) ==================

@app.get("/api/saved")
async def list_saved_articles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: Dict = Depends(get_current_user)
):
    try:
        offset = (page - 1) * size
        items = db_manager.list_saved_articles(current_user['id'], limit=size, offset=offset)
        return {"status": "success", "articles": items, "pagination": {"page": page, "size": size, "total": len(items)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/saved/status")
async def saved_status(url: str, current_user: Dict = Depends(get_current_user)):
    try:
        article_id = db_manager.get_article_id_by_url(url)
        if not article_id:
            return {"status": "success", "saved": False}
        saved = db_manager.is_article_saved(current_user['id'], article_id)
        return {"status": "success", "saved": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/saved")
async def add_saved(req: SavedRequest, current_user: Dict = Depends(get_current_user)):
    try:
        article_id = req.article_id
        if not article_id and req.url:
            article_id = db_manager.get_article_id_by_url(req.url)
        if not article_id:
            raise HTTPException(status_code=404, detail="文章不存在，无法收藏")
        ok = db_manager.add_saved_article(current_user['id'], article_id)
        if not ok:
            raise HTTPException(status_code=500, detail="收藏失败")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/saved")
async def remove_saved(url: Optional[str] = None, article_id: Optional[int] = None, current_user: Dict = Depends(get_current_user)):
    try:
        aid = article_id
        if not aid and url:
            aid = db_manager.get_article_id_by_url(url)
        if not aid:
            raise HTTPException(status_code=404, detail="文章不存在")
        ok = db_manager.remove_saved_article(current_user['id'], aid)
        return {"status": "success" if ok else "not_found"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/read")
async def mark_read(req: ReadRequest, current_user: Dict = Depends(get_current_user)):
    try:
        article_id = req.article_id
        if not article_id and req.url:
            article_id = db_manager.get_article_id_by_url(req.url)
        if not article_id:
            raise HTTPException(status_code=404, detail="文章不存在")
        ok = db_manager.mark_article_read(current_user['id'], article_id)
        if not ok:
            raise HTTPException(status_code=500, detail="标记已读失败")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/articles/read")
async def mark_unread(url: Optional[str] = None, article_id: Optional[int] = None, current_user: Dict = Depends(get_current_user)):
    try:
        aid = article_id
        if not aid and url:
            aid = db_manager.get_article_id_by_url(url)
        if not aid:
            raise HTTPException(status_code=404, detail="文章不存在")
        ok = db_manager.mark_article_unread(current_user['id'], aid)
        if not ok:
            raise HTTPException(status_code=500, detail="标记未读失败")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== Audio Play History 播放历史接口 ==================

@app.get("/api/v1/audio-history")
async def get_audio_play_history(
    item_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: Dict = Depends(get_current_user)
):
    """Get user's audio play history (TTS articles and podcasts)."""
    try:
        # Validate item_type if provided
        if item_type and item_type not in ('article', 'podcast'):
            raise HTTPException(status_code=400, detail="Invalid item_type. Must be 'article' or 'podcast'")

        history = db_manager.get_audio_play_history(
            current_user['id'],
            item_type=item_type,
            limit=min(limit, 100),  # Max 100 per request
            offset=offset
        )
        return {"status": "success", "data": history}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/audio-history")
async def record_audio_play(
    req: AudioPlayHistoryRecord,
    current_user: Dict = Depends(get_current_user)
):
    """Record or update audio play history."""
    try:
        # Validate item_type
        if req.item_type not in ('article', 'podcast'):
            raise HTTPException(status_code=400, detail="Invalid item_type. Must be 'article' or 'podcast'")

        ok = db_manager.record_audio_play(
            user_id=current_user['id'],
            item_type=req.item_type,
            item_id=req.item_id,
            title=req.title,
            source_name=req.source_name,
            duration_seconds=req.duration_seconds or 0,
            played_seconds=req.played_seconds or 0,
            progress_percentage=req.progress_percentage or 0,
            is_completed=req.is_completed or False
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to record play history")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/audio-history")
async def clear_audio_play_history(
    item_type: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)
):
    """Clear user's audio play history. Optionally filter by type."""
    try:
        if item_type and item_type not in ('article', 'podcast'):
            raise HTTPException(status_code=400, detail="Invalid item_type. Must be 'article' or 'podcast'")

        ok = db_manager.clear_audio_play_history(current_user['id'], item_type=item_type)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to clear play history")
        return {"status": "success", "message": "Play history cleared"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/audio-history/{item_type}/{item_id}")
async def delete_audio_play_history_item(
    item_type: str,
    item_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """Delete a specific item from audio play history."""
    try:
        if item_type not in ('article', 'podcast'):
            raise HTTPException(status_code=400, detail="Invalid item_type. Must be 'article' or 'podcast'")

        ok = db_manager.delete_audio_play_history_item(current_user['id'], item_type, item_id)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to delete play history item")
        return {"status": "success", "message": "Item removed from history"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== User Queue & Playback State Sync ==================

@app.get("/api/v1/queue")
async def get_user_queue(current_user: Dict = Depends(get_current_user)):
    """Get the user's synced listen queue."""
    try:
        data = db_manager.get_user_queue(current_user['id'])
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/queue")
async def update_user_queue(
    req: QueueUpdateRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Replace the user's synced listen queue."""
    try:
        items = [item.model_dump() for item in req.items]
        ok = db_manager.save_user_queue(current_user['id'], items)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to save queue")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/queue")
async def clear_user_queue(current_user: Dict = Depends(get_current_user)):
    """Clear the user's synced listen queue."""
    try:
        ok = db_manager.clear_user_queue(current_user['id'])
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to clear queue")
        return {"status": "success", "message": "Queue cleared"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/playback-state")
async def get_playback_state(current_user: Dict = Depends(get_current_user)):
    """Get the user's synced playback state snapshot."""
    try:
        data = db_manager.get_playback_state(current_user['id'])
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/v1/playback-state")
async def update_playback_state(
    req: PlaybackStateUpdateRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Replace the user's synced playback state snapshot."""
    try:
        state = req.model_dump()
        ok = db_manager.save_playback_state(current_user['id'], state)
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to save playback state")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================== TTS 语音合成接口 ==================

@app.get("/api/v1/tts/voices")
async def list_tts_voices(current_user: Dict = Depends(get_current_user)):
    """返回可选 TTS 音色目录（按语言分组），供设置页音色选择器使用。"""
    return TTS_VOICE_CATALOG


class TtsVoicePreviewRequest(BaseModel):
    """音色试听请求（voice=目录音色 id 或 'default'）"""
    voice: str
    lang: str


@app.post("/api/v1/tts/voice-preview")
@limiter.limit(settings.rate_limit_tts)
async def preview_tts_voice(
    request: Request,
    payload: TtsVoicePreviewRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    音色试听（语音选择功能，2026-09-07）

    - 仅允许目录内音色（含 'default'），文本固定为目录 sample_text —— 零滥用面
    - 固定文本 + use_cache → 首次生成后永久命中缓存，边际成本≈0
    - 不消耗用户 TTS 每日配额（不调用 record_tts_usage）
    """
    lang = (payload.lang or "").lower()
    if lang not in TTS_VOICE_CATALOG:
        raise HTTPException(status_code=400, detail=f"Unsupported lang: {payload.lang}")

    voices = TTS_VOICE_CATALOG[lang]
    if payload.voice == "default":
        voice_entry = next(v for v in voices if v["is_default"])
        voice_id = None  # None → service 层解析为系统默认音色
    else:
        voice_entry = next((v for v in voices if v["id"] == payload.voice), None)
        if voice_entry is None:
            raise HTTPException(status_code=400, detail=f"Unsupported voice for {lang}: {payload.voice}")
        voice_id = voice_entry["id"]

    try:
        speech_service = get_speech_service(settings)
        audio_bytes = await speech_service.synthesize(
            text=voice_entry["sample_text"],
            article_id=None,
            lang=lang,
            voice=voice_id
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=voice_preview.mp3",
                "Cache-Control": "public, max-age=86400",  # 固定文本，可长缓存
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TTS] 音色试听失败 - voice={payload.voice}, lang={lang}, error={e}")
        raise HTTPException(status_code=500, detail="Voice preview failed")


@app.post("/api/v1/tts/synthesize-stream", response_class=StreamingResponse)
@limiter.limit(settings.rate_limit_tts)
async def synthesize_audio_stream(
    request: Request,
    payload: TtsSynthesizeRequest,
    current_user: dict = Depends(require_tts_quota)
):
    """
    流式生成语音（TTS），边生成边播放
    """
    start_time = time.time()

    # 记录请求信息
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    logger.info(
        f"[TTS Stream] 收到请求 - "
        f"user={current_user['username']}, ip={client_ip}, "
        f"article_id={payload.article_id or 'N/A'}, "
        f"text_length={len(payload.text)}, lang={payload.lang}, voice={payload.voice}, "
        f"user_agent={user_agent}"
    )

    try:
        if not payload.text or len(payload.text.strip()) == 0:
            logger.warning(f"[TTS Stream] 请求文本为空 - user={current_user['username']}")
            raise HTTPException(status_code=400, detail="待朗读文本不能为空")

        if len(payload.text) > settings.tts_max_article_length:
            if settings.tts_long_article_strategy == "reject":
                logger.warning(
                    f"[TTS Stream] 文本过长被拒绝 - "
                    f"user={current_user['username']}, length={len(payload.text)}, "
                    f"limit={settings.tts_max_article_length}"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"文本过长（{len(payload.text)} 字符），超过上限 {settings.tts_max_article_length} 字符"
                )
            else:
                logger.info(
                    f"[TTS Stream] 长文本检测 - "
                    f"user={current_user['username']}, length={len(payload.text)}, "
                    f"strategy={settings.tts_long_article_strategy}"
                )

        speech_service = get_speech_service(settings)

        # ✅ 统一使用 AAC 格式（兼容所有设备：iOS/Android/桌面）
        audio_format = "aac"  # 所有设备统一使用 AAC


        media_types = {
            "opus": "audio/webm",  # WebM 容器支持 MediaSource API
            "aac": "audio/mp4",  # ✅ M4A 容器使用 audio/mp4 MIME (iOS Safari 兼容)
            "mp3": "audio/mpeg",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "pcm": "audio/pcm"
        }
        media_type = media_types.get(audio_format, "audio/mpeg")

        # 流式TTS不支持预合成缓存，直接调用云端合成
        logger.info(
            f"[TTS Stream] 开始云端流式合成 - "
            f"user={current_user['username']}, format={audio_format}, media_type={media_type}, "
            f"service={speech_service.__class__.__name__}, "
            f"article_id={payload.article_id or 'N/A'}"
        )

        async def audio_generator():
            chunk_count = 0
            total_bytes = 0
            synthesis_start = time.time()

            try:
                async for chunk in speech_service.synthesize_stream(
                    text=payload.text,
                    article_id=str(payload.article_id) if payload.article_id else None,
                    lang=payload.lang if payload.lang != "auto" else None,
                    voice=payload.voice if payload.voice != "default" else None,
                    audio_format=audio_format
                ):
                    chunk_count += 1
                    total_bytes += len(chunk)
                    yield chunk

                synthesis_time = time.time() - synthesis_start
                logger.info(
                    f"[TTS Stream] 合成完成 - "
                    f"user={current_user['username']}, "
                    f"article_id={payload.article_id or 'N/A'}, "
                    f"chunks={chunk_count}, total_bytes={total_bytes}, "
                    f"synthesis_time={synthesis_time:.2f}s"
                )

            except ValueError as e:
                logger.warning(
                    f"[TTS Stream] 参数错误 - "
                    f"user={current_user['username']}, error={e}"
                )
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logger.error(
                    f"[TTS Stream] 合成失败 - "
                    f"user={current_user['username']}, "
                    f"article_id={payload.article_id or 'N/A'}, "
                    f"error={e}",
                    exc_info=True
                )
                raise HTTPException(status_code=500, detail="音频生成失败")

        total_time = time.time() - start_time
        logger.info(
            f"[TTS Stream] 请求处理完成 - "
            f"user={current_user['username']}, total_time={total_time:.2f}s"
        )

        # Phase 1: 记录 TTS 用量
        subscription_service.record_tts_usage(current_user['id'], len(payload.text))

        return StreamingResponse(
            audio_generator(),
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Audio-Format": audio_format
            }
        )

    except HTTPException:
        raise


@app.post("/api/v1/tts/synthesize")
@limiter.limit(settings.rate_limit_tts)
async def synthesize_audio(
    request: Request,
    payload: TtsSynthesizeRequest,
    current_user: dict = Depends(require_tts_quota)
):
    """
    生成语音（TTS）

    Phase 3 优化：检查预合成缓存（RSS 抓取时自动生成第一段）
    - 如果是第一段且存在预合成缓存，直接返回缓存文件
    - 否则走正常合成流程

    Args:
        payload: TTS 合成请求（text, article_id, lang, voice）
        current_user: 当前登录用户（JWT 认证）

    Returns:
        音频二进制数据（Content-Type: audio/mpeg）

    Raises:
        HTTPException 400: 文本过长或为空
        HTTPException 500: 音频生成失败
    """
    start_time = time.time()

    # 记录请求信息
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    logger.info(
        f"[TTS] 收到请求 - "
        f"user={current_user['username']}, ip={client_ip}, "
        f"article_id={payload.article_id or 'N/A'}, "
        f"text_length={len(payload.text)}, lang={payload.lang}, voice={payload.voice}, "
        f"user_agent={user_agent}"
    )

    try:
        # 文本长度校验
        if not payload.text or len(payload.text.strip()) == 0:
            logger.warning(f"[TTS] 请求文本为空 - user={current_user['username']}")
            raise HTTPException(status_code=400, detail="待朗读文本不能为空")

        # ⚠️ Phase 3 预合成缓存已废弃（v2 MP3 流式架构迁移）
        # 新架构统一使用 /api/v1/tts/play/{article_id} 接口，自动处理缓存逻辑

        # 长文本处理：根据策略配置决定是否拒绝
        # - "reject": API 层直接拒绝
        # - "segment" 或 "truncate": 传递到 service 层处理
        if len(payload.text) > settings.tts_max_article_length:
            if settings.tts_long_article_strategy == "reject":
                logger.warning(
                    f"[TTS] 文本过长被拒绝 - "
                    f"user={current_user['username']}, length={len(payload.text)}, "
                    f"limit={settings.tts_max_article_length}"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"文本过长（{len(payload.text)} 字符），超过上限 {settings.tts_max_article_length} 字符"
                )
            else:
                # segment 或 truncate 策略：记录日志，交给 service 层处理
                logger.info(
                    f"[TTS] 长文本检测 - "
                    f"user={current_user['username']}, length={len(payload.text)}, "
                    f"strategy={settings.tts_long_article_strategy}"
                )

        # 获取语音服务实例
        speech_service = get_speech_service(settings)

        # 调用 TTS 合成（未命中缓存）
        synthesis_start = time.time()
        logger.info(
            f"[TTS] 开始云端合成 - "
            f"user={current_user['username']}, "
            f"service={speech_service.__class__.__name__}, "
            f"text_length={len(payload.text)}, lang={payload.lang}, voice={payload.voice}, "
            f"article_id={payload.article_id or 'N/A'}"
        )

        audio_bytes = await speech_service.synthesize(
            text=payload.text,
            article_id=str(payload.article_id) if payload.article_id else None,
            lang=payload.lang if payload.lang != "auto" else None,
            voice=payload.voice if payload.voice != "default" else None
        )

        synthesis_time = time.time() - synthesis_start
        total_time = time.time() - start_time

        logger.info(
            f"[TTS] 云端合成完成 - "
            f"user={current_user['username']}, "
            f"article_id={payload.article_id or 'N/A'}, "
            f"audio_size={len(audio_bytes)} bytes, "
            f"synthesis_time={synthesis_time:.2f}s, "
            f"total_time={total_time:.2f}s"
        )

        # Phase 1: 记录 TTS 用量
        subscription_service.record_tts_usage(current_user['id'], len(payload.text))

        # 返回音频（直接流式传输）
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=audio.mp3",
                "Cache-Control": "public, max-age=86400",  # 缓存 24 小时
                "X-Cache-Hit": "none"  # 标识未命中缓存
            }
        )

    except ValueError as e:
        # 参数校验错误
        logger.warning(
            f"[TTS] 参数错误 - "
            f"user={current_user['username']}, error={e}"
        )
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        # TTS 生成失败
        logger.error(
            f"[TTS] 合成失败 - "
            f"user={current_user['username']}, "
            f"article_id={getattr(payload, 'article_id', 'N/A')}, "
            f"error={e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"音频生成失败: {str(e)}")

# ================== TTS 统一播放接口（v2 - MP3 流式透传架构）==================

def _extract_tts_auth_token(request: Optional[Request]) -> str:
    """从 Authorization header 提取 TTS 认证令牌。不再支持 URL query token，防止令牌泄露。"""
    auth_token = None

    if request and request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            auth_token = auth_header[7:]

    if not auth_token:
        raise HTTPException(status_code=401, detail="需要身份验证")

    return auth_token


def _get_tts_request_context(
    article_id: str,
    request: Optional[Request],
    token: Optional[str]
):
    auth_token = _extract_tts_auth_token(request)
    user_id = jwt_utils.verify_token(auth_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="无效的认证令牌")

    current_user = db_manager.get_user_by_id(user_id)
    if not current_user:
        raise HTTPException(status_code=401, detail="用户不存在")

    article = db_manager.get_user_article_metadata_with_fallback(
        user_id,
        int(article_id),
        language=current_user.get('preferred_language', 'en')
    )
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    speech_service = get_speech_service(settings)
    global_article_id = article.get("global_article_id")
    return current_user, article, speech_service, global_article_id


def _build_article_tts_text(article: Dict[str, Any]) -> str:
    tts_text_parts = [article["title"]]
    tts_text_parts.append(article["content"])
    return "。".join([part for part in tts_text_parts if part and str(part).strip()])


async def _resolve_tts_prepare_status(
    article_id: str,
    article: Dict[str, Any],
    speech_service: Any,
    voice: Optional[str],
    global_article_id: Optional[int] = None
):
    voice_to_use = stable_tts_manager.normalize_voice(speech_service, voice)
    raw_tts_text = _build_article_tts_text(article)
    clean_text = stable_tts_manager.prepare_text(raw_tts_text)
    tts_article_id = str(global_article_id) if global_article_id else article_id
    status = await stable_tts_manager.get_status(
        speech_service=speech_service,
        article_id=tts_article_id,
        clean_text=clean_text,
        voice=voice_to_use,
        global_article_id=global_article_id,
        db_manager=db_manager
    )
    return voice_to_use, clean_text, status


@app.post("/api/v1/tts/prepare/{article_id}")
async def prepare_tts_generation(
    article_id: str,
    voice: str = Query(default=settings.openai_tts_voice, description="声线标识"),
    token: str = Query(default=None, description="备用认证方式（URL query token）"),
    request: Request = None
):
    """
    触发或加入 V2 稳定播放生成任务。
    """
    try:
        current_user, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, token)
        requested_voice = None if voice == "default" else voice
        voice_to_use, clean_text, status = await _resolve_tts_prepare_status(
            article_id=article_id,
            article=article,
            speech_service=speech_service,
            voice=requested_voice,
            global_article_id=global_article_id
        )

        if status["final_ready"]:
            return JSONResponse(status, headers={"Cache-Control": "no-cache"})

        if status["status"] == "generating":
            return JSONResponse(status, headers={"Cache-Control": "no-cache"})

        # 始终检查用户配额（配额是用户级别的，不是文章级别的）
        quota = subscription_service.check_tts_quota(current_user["id"])
        if not quota["allowed"]:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Daily TTS limit reached",
                    "used": quota["used"],
                    "limit": quota["limit"],
                    "plan": quota["plan"],
                    "upgrade_url": "/pricing"
                }
            )

        tts_article_id = str(global_article_id) if global_article_id else article_id
        prepare_state, response = await stable_tts_manager.ensure_generation_started(
            speech_service=speech_service,
            article_id=tts_article_id,
            clean_text=clean_text,
            voice=voice_to_use,
            global_article_id=global_article_id,
            db_manager=db_manager
        )

        if prepare_state == "started" and not await stable_tts_manager.usage_already_recorded(response["cache_key"]):
            subscription_service.record_tts_usage(current_user["id"], len(clean_text))
            await stable_tts_manager.mark_usage_recorded(response["cache_key"])

        return JSONResponse(response, headers={"Cache-Control": "no-cache"})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("❌ TTS prepare 失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="TTS 准备失败，请稍后重试")


@app.get("/api/v1/tts/prepare/{article_id}")
async def get_tts_prepare_status(
    article_id: str,
    voice: str = Query(default=settings.openai_tts_voice, description="声线标识"),
    token: str = Query(default=None, description="备用认证方式（URL query token）"),
    request: Request = None
):
    """
    轮询 V2 稳定播放状态。
    """
    try:
        _, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, token)
        requested_voice = None if voice == "default" else voice
        _, _, status = await _resolve_tts_prepare_status(
            article_id=article_id,
            article=article,
            speech_service=speech_service,
            voice=requested_voice,
            global_article_id=global_article_id
        )
        return JSONResponse(status, headers={"Cache-Control": "no-cache"})
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("❌ 获取 TTS prepare 状态失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="获取 TTS 状态失败")

@app.get("/api/v1/tts/play/{article_id}")
async def play_tts(
    article_id: str,
    voice: str = Query(default=settings.openai_tts_voice, description="声线标识"),
    lang: str = Query(default="auto", description="语言（保留参数，兼容旧接口）"),
    sig: Optional[str] = Query(default=None, description="签名（用于 HTML5 audio 标签）"),
    exp: Optional[int] = Query(default=None, description="签名过期时间戳"),
    uid: Optional[str] = Query(default=None, description="签名用户ID"),
    cache_only: bool = Query(default=False, description="仅检查缓存状态，不返回音频"),
    token: str = Query(default=None, description="备用认证方式（URL query token）"),
    request: Request = None
):
    """
    V2 最终完整音频播放接口。

    只返回已完整生成的稳定文件。
    """
    try:
        # 签名 URL 验证（用于 HTML5 audio 标签，无需暴露 JWT）
        if sig and exp:
            # 验证文章存在（通过签名 URL 不需要完整 JWT 认证）
            # 先尝试从 header 获取用户，否则签名 URL 必须有效
            auth_header = request.headers.get("Authorization") if request else None
            if auth_header and auth_header.startswith("Bearer "):
                # 有 Bearer token，走正常流程
                _, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, token)
            else:
                # 无 Bearer token，需要验证签名
                if not uid:
                    raise HTTPException(status_code=401, detail="Missing signature user ID")
                if not _verify_audio_signature(int(article_id), uid, sig, exp, voice=voice if voice != "default" else None):
                    raise HTTPException(status_code=401, detail="Invalid or expired signature")
                # 签名验证通过，使用签名用户继续
                current_user = db_manager.get_user_by_id(uid)
                if not current_user:
                    raise HTTPException(status_code=401, detail="用户不存在")
                article = db_manager.get_user_article_metadata_with_fallback(
                    uid, int(article_id), language=current_user.get('preferred_language', 'en')
                )
                if not article:
                    raise HTTPException(status_code=404, detail="文章不存在")
                speech_service = get_speech_service(settings)
                global_article_id = article.get("global_article_id")
        else:
            _, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, token)
        requested_voice = None if voice == "default" else voice
        voice_to_use, clean_text, status = await _resolve_tts_prepare_status(
            article_id=article_id,
            article=article,
            speech_service=speech_service,
            voice=requested_voice,
            global_article_id=global_article_id
        )

        if cache_only:
            cache_status = "hit" if status["final_ready"] else (
                "generating" if status["status"] in {"generating", "started"} or status["first_playable_ready"] else "miss"
            )
            return JSONResponse(
                {
                    "cache": cache_status,
                    **status
                },
                headers={"Cache-Control": "no-cache"}
            )

        tts_article_id = str(global_article_id) if global_article_id else article_id
        cache_key = stable_tts_manager.build_cache_key(speech_service, clean_text, voice_to_use, tts_article_id)
        final_path = stable_tts_manager.resolve_final_path(speech_service, cache_key)
        if final_path and final_path.exists():
            etag = f'"{cache_key}"'
            if_none_match = request.headers.get("if-none-match") if request else None
            if if_none_match == etag:
                return Response(status_code=304)

            return FileResponse(
                final_path,
                media_type="audio/mpeg",
                headers={
                    "Cache-Control": "private, max-age=31536000, immutable",
                    "ETag": etag,
                    "Accept-Ranges": "bytes",
                    "X-Audio-Cache": "hit"
                }
            )

        detail = "failed" if status["status"] == "failed" else "not_ready"
        message = "audio generation failed" if detail == "failed" else "final audio not ready"
        raise HTTPException(
            status_code=409,
            detail={
                "detail": detail,
                "message": message,
                "status": status["status"],
                "first_playable_ready": status["first_playable_ready"],
                "ready_duration_sec": status["ready_duration_sec"],
                "segments_ready": status["segments_ready"],
                "segments_total": status["segments_total"]
            }
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("❌ TTS 播放失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="TTS 生成失败，请稍后重试")


@app.get("/api/v1/tts/play-url/{article_id}")
@limiter.limit(settings.rate_limit_tts)
async def get_tts_play_url(
    request: Request,
    article_id: str,
    voice: str = Query(default=settings.openai_tts_voice, description="声线标识"),
    lang: str = Query(default="auto", description="语言"),
    current_user: Dict = Depends(get_current_user)
):
    """
    获取 TTS 播放的签名 URL（用于 HTML5 audio 标签）

    权限：需要登录
    返回：带签名的临时 URL，有效期 5 分钟
    """
    try:
        user_id = current_user["id"]

        # 验证文章存在且属于当前用户
        article = db_manager.get_user_article_metadata_with_fallback(
            user_id, int(article_id), language=current_user.get('preferred_language', 'en')
        )
        if not article:
            raise HTTPException(status_code=404, detail="文章不存在")

        # 生成签名 URL（5 分钟有效），签名包含 voice 防止参数篡改
        sig, expiry = _generate_audio_signature(int(article_id), user_id, voice=voice if voice != "default" else None)

        # 构建播放 URL（包含 uid 用于签名验证）
        params = f"sig={sig}&exp={expiry}&uid={user_id}"
        if voice and voice != "default":
            params += f"&voice={voice}"
        if lang and lang != "auto":
            params += f"&lang={lang}"

        audio_url = f"/api/v1/tts/play/{article_id}?{params}"

        return {
            "success": True,
            "audio_url": audio_url,
            "expires_in": _AUDIO_SIG_TTL_SECONDS
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成 TTS 播放 URL 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tts/segment-play-url/{article_id}/{index}")
@limiter.limit(settings.rate_limit_tts)
async def get_tts_segment_play_url(
    request: Request,
    article_id: str,
    index: int,
    voice: str = Query(default=settings.openai_tts_voice, description="声线标识"),
    current_user: Dict = Depends(get_current_user)
):
    """
    获取 TTS segment 播放的签名 URL（用于 HTML5 audio 标签）

    权限：需要登录
    返回：带签名的临时 URL，有效期 5 分钟
    """
    try:
        user_id = current_user["id"]

        # 验证文章存在且属于当前用户
        article = db_manager.get_user_article_metadata_with_fallback(
            user_id, int(article_id), language=current_user.get('preferred_language', 'en')
        )
        if not article:
            raise HTTPException(status_code=404, detail="文章不存在")

        # 生成签名 URL（5 分钟有效），签名包含 voice 防止参数篡改
        sig, expiry = _generate_audio_signature(int(article_id), user_id, voice=voice if voice != "default" else None)

        # 构建 segment 播放 URL（包含 uid 用于签名验证）
        params = f"sig={sig}&exp={expiry}&uid={user_id}"
        if voice and voice != "default":
            params += f"&voice={voice}"

        audio_url = f"/api/v1/tts/segments/{article_id}/{index}?{params}"

        return {
            "success": True,
            "audio_url": audio_url,
            "expires_in": _AUDIO_SIG_TTL_SECONDS
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成 TTS segment 播放 URL 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tts/segments/{article_id}/{index}")
async def get_tts_segment(
    article_id: str,
    index: int,
    voice: str = Query(default=settings.openai_tts_voice, description="声线标识"),
    sig: Optional[str] = Query(default=None, description="签名（用于 HTML5 audio 标签）"),
    exp: Optional[int] = Query(default=None, description="签名过期时间戳"),
    uid: Optional[str] = Query(default=None, description="签名用户ID"),
    request: Request = None
):
    """
    返回单个已完整生成的稳定 segment。
    """
    try:
        # 签名 URL 验证（用于 HTML5 audio 标签，无需暴露 JWT）
        if sig and exp:
            auth_header = request.headers.get("Authorization") if request else None
            if auth_header and auth_header.startswith("Bearer "):
                _, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, None)
            else:
                if not uid:
                    raise HTTPException(status_code=401, detail="Missing signature user ID")
                if not _verify_audio_signature(int(article_id), uid, sig, exp, voice=voice if voice != "default" else None):
                    raise HTTPException(status_code=401, detail="Invalid or expired signature")
                current_user = db_manager.get_user_by_id(uid)
                if not current_user:
                    raise HTTPException(status_code=401, detail="用户不存在")
                article = db_manager.get_user_article_metadata_with_fallback(
                    uid, int(article_id), language=current_user.get('preferred_language', 'en')
                )
                if not article:
                    raise HTTPException(status_code=404, detail="文章不存在")
                speech_service = get_speech_service(settings)
                global_article_id = article.get("global_article_id")
        else:
            _, article, speech_service, global_article_id = _get_tts_request_context(article_id, request, None)
        requested_voice = None if voice == "default" else voice
        voice_to_use, clean_text, status = await _resolve_tts_prepare_status(
            article_id=article_id,
            article=article,
            speech_service=speech_service,
            voice=requested_voice,
            global_article_id=global_article_id
        )

        tts_article_id = str(global_article_id) if global_article_id else article_id
        cache_key = stable_tts_manager.build_cache_key(speech_service, clean_text, voice_to_use, tts_article_id)
        if index < 0 or index >= status["segments_total"]:
            raise HTTPException(status_code=404, detail="segment_not_found")

        segment_state = status["segments"][index] if index < len(status["segments"]) else None
        segment_path = stable_tts_manager.get_segment_path(cache_key, index)

        if segment_state and segment_state["status"] == "ready" and segment_path.exists():
            return FileResponse(
                segment_path,
                media_type="audio/mpeg",
                headers={
                    "Cache-Control": "private, max-age=86400",
                    "Accept-Ranges": "bytes",
                    "X-Audio-Cache": "segment"
                }
            )

        detail = "segment_failed" if segment_state and segment_state["status"] == "failed" else "segment_not_ready"
        raise HTTPException(
            status_code=409,
            detail={
                "detail": detail,
                "segment_index": index,
                "segment_status": segment_state["status"] if segment_state else "missing",
                "message": "segment audio not ready"
            }
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("❌ 获取 TTS segment 失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="获取音频分段失败")

# ================== 定时任务管理接口 ==================

@app.get("/api/scheduler/status")
def get_scheduler_status(current_user: Dict = Depends(require_superuser)):
    """获取定时任务调度器状态"""
    try:
        status = feed_scheduler.get_status()
        return {"status": "success", "scheduler": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduler/trigger")
async def trigger_scheduler(current_user: Dict = Depends(require_superuser)):
    """手动触发一次抓取任务"""
    try:
        # 在后台线程中执行，避免阻塞API响应
        import threading
        thread = threading.Thread(target=feed_scheduler.trigger_now)
        thread.start()

        return {
            "status": "success",
            "message": "抓取任务已触发，正在后台执行"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cache/cleanup")
async def trigger_cache_cleanup(dry_run: bool = Query(False, description="是否为模拟运行（不实际删除文件）"), current_user: Dict = Depends(require_superuser)):
    """
    手动触发音频缓存清理任务

    Args:
        dry_run: 是否为模拟运行（不实际删除文件）

    Returns:
        清理结果统计
    """
    try:
        from backend.services.cache_cleaner import run_cache_cleanup

        logger.info(f"手动触发缓存清理任务 (dry_run={dry_run})")

        # 在后台线程中执行，避免阻塞API响应
        import threading
        result = {"status": "running", "message": "缓存清理任务已触发"}

        def cleanup_task():
            try:
                cleanup_result = run_cache_cleanup(dry_run=dry_run)
                logger.info(f"缓存清理任务完成: {cleanup_result}")
            except Exception as e:
                logger.error(f"缓存清理任务失败: {e}", exc_info=True)

        thread = threading.Thread(target=cleanup_task)
        thread.start()

        return result
    except Exception as e:
        logger.error(f"触发缓存清理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cache/stats")
async def get_cache_stats(current_user: Dict = Depends(require_superuser)):
    """
    获取音频缓存统计信息

    Returns:
        缓存统计信息（文件数量、总大小、最旧/最新文件等）
    """
    try:
        from backend.services.cache_cleaner import AudioCacheCleaner

        cleaner = AudioCacheCleaner()
        stats = cleaner.get_cache_stats()

        return {
            "status": "success",
            "data": stats
        }
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ================== AI 播客 API (2026-02-02) ==================

from backend.services.podcast_generator import PodcastGenerator, PodcastRateLimitError
from backend.services.podcast_rag import PodcastRAG
from backend.config.onboarding_starter_pack import get_starter_pack_feed_defs

# 延迟初始化播客生成器（避免模块加载时创建数据库连接）
_podcast_generator = None
_podcast_rag = None

def get_podcast_generator() -> PodcastGenerator:
    """获取播客生成器实例（延迟初始化）"""
    global _podcast_generator
    if _podcast_generator is None:
        _podcast_generator = PodcastGenerator()
    return _podcast_generator


def get_podcast_rag() -> PodcastRAG:
    """获取播客 RAG 实例（延迟初始化）"""
    global _podcast_rag
    if _podcast_rag is None:
        _podcast_rag = PodcastRAG(settings, db_manager)
    return _podcast_rag


async def _run_podcast_generation_background(
    podcast_id: int,
    user_id: str,
    style: str,
    time_range_hours: int,
    max_articles: int,
    language: str
):
    """后台执行播客生成（由 BackgroundTasks 调度）"""
    try:
        generator = get_podcast_generator()
        await generator.generate_podcast_content(
            podcast_id=podcast_id,
            user_id=user_id,
            style=style,
            time_range_hours=time_range_hours,
            max_articles=max_articles,
            language=language
        )
    except Exception:
        # 异常已在 generate_podcast_content 中记录并更新状态为 failed
        pass


class PodcastGenerateRequest(BaseModel):
    """播客生成请求"""
    style: str = "deep_dive"  # 播客样式
    time_range_hours: int = 24  # 时间范围（小时）
    max_articles: int = 10  # 最大文章数
    language: str = "en"  # 语言（zh/en）


class PodcastProgressRequest(BaseModel):
    """播放进度保存请求"""
    current_time: int  # 当前播放位置（秒）
    total_time: int  # 总时长（秒）
    is_completed: bool = False  # 是否播放完成


class PodcastChatRequest(BaseModel):
    """播客对话请求"""
    message: str  # 用户消息


@app.post("/api/v1/podcasts/generate")
@limiter.limit(settings.rate_limit_podcast)
async def generate_podcast(
    request: Request,
    payload: PodcastGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user)
):
    """
    触发播客生成（异步后台执行）

    权限：需要登录
    频控：同一用户 1 分钟内只能触发 1 次，每天最多 3 次
    """
    try:
        user_id = current_user["id"]

        # 检查是否启用播客功能
        if not settings.podcast_enabled:
            raise HTTPException(
                status_code=403,
                detail="Podcast feature is disabled"
            )

        # 检查今日是否已存在播客（包含 onboarding cache，避免与 createExperiencePodcast 竞态后生成重复 user_generated podcast）
        # 优先返回 user_generated；若仅有 onboarding_cache 则也视为已就绪，直接返回 cache id
        with db_manager.pg_conn.cursor() as cur:
            cur.execute("""
                SELECT id, generation_status, source
                FROM podcasts
                WHERE user_id = %s
                  AND created_at >= CURRENT_DATE
                ORDER BY CASE WHEN source = 'onboarding_cache' THEN 1 ELSE 0 END, created_at DESC
                LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            if row:
                existing_id, status, source = row
                if status == 'completed':
                    return {
                        "success": True,
                        "podcast_id": existing_id,
                        "already_generated": True,
                        "status": status,
                        "source": source,
                        "message": "Today's podcast has already been generated"
                    }
                elif status in ('pending', 'generating'):
                    return {
                        "success": True,
                        "podcast_id": existing_id,
                        "already_generated": True,
                        "status": status,
                        "source": source,
                        "message": "Today's podcast is currently being generated"
                    }
                # status == 'failed' -> allow retry, fall through

        # 检查播客配额（在重复生成检查之后，避免当日已生成时仍报配额超限）
        quota = subscription_service.check_podcast_quota(user_id)
        if not quota['allowed']:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Daily podcast limit reached",
                    "used": quota['used'],
                    "limit": quota['limit'],
                    "plan": quota['plan']
                }
            )

        # 创建播客记录（立即返回，后台异步生成内容）
        user_language = current_user.get('preferred_language', 'en')
        language = 'en' if user_language == 'en' else 'zh'
        generator = get_podcast_generator()
        podcast_id = generator._create_podcast_record(user_id, payload.style, language)

        # 启动后台任务生成播客内容
        background_tasks.add_task(
            _run_podcast_generation_background,
            podcast_id,
            user_id,
            payload.style,
            payload.time_range_hours,
            payload.max_articles,
            language
        )

        # 记录播客用量（仅统计，不参与功能门控）
        subscription_service.record_podcast_usage(user_id)

        return {
            "success": True,
            "podcast_id": podcast_id,
            "already_generated": False,
            "status": "pending",
            "message": "Daily podcast generation started"
        }

    except HTTPException:
        raise
    except PodcastRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"播客生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/podcasts")
async def get_podcasts(
    current_user: Dict = Depends(get_current_user),
    status: Optional[str] = Query(None, description="筛选状态"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    获取播客列表

    权限：需要登录
    """
    try:
        user_id = current_user["id"]

        # 构建查询
        query = """
        SELECT
            id,
            title,
            description,
            style,
            duration,
            cover_image,
            generation_status,
            generation_error,
            play_count,
            source,
            created_at
        FROM podcasts
        WHERE user_id = %s
        """

        params = [user_id]

        if status:
            query += " AND generation_status = %s"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, tuple(params))
            result = cur.fetchall()

        podcasts = []
        for row in result:
            podcasts.append({
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "style": row[3],
                "duration": row[4],
                "cover_image": row[5],
                "generation_status": row[6],
                "generation_error": row[7],
                "play_count": row[8],
                "source": row[9],
                "created_at": row[10].isoformat() if row[10] else None
            })

        return {
            "success": True,
            "podcasts": podcasts,
            "total": len(podcasts)
        }

    except Exception as e:
        logger.error(f"获取播客列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/podcasts/{podcast_id}")
async def delete_podcast(
    podcast_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """删除播客及其关联数据（脚本、文章关联、对话、进度）"""
    try:
        user_id = current_user["id"]

        with db_manager.pg_conn.cursor() as cur:
            # 验证播客归属
            cur.execute(
                "SELECT id, audio_url, source FROM podcasts WHERE id = %s AND user_id = %s",
                (podcast_id, user_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="播客不存在")

            audio_path = row[1]
            podcast_source = row[2]

            # 级联删除关联数据
            cur.execute("DELETE FROM podcast_play_progress WHERE podcast_id = %s", (podcast_id,))
            cur.execute("DELETE FROM podcast_conversations WHERE podcast_id = %s", (podcast_id,))
            cur.execute("DELETE FROM podcast_articles WHERE podcast_id = %s", (podcast_id,))
            cur.execute("DELETE FROM podcast_scripts WHERE podcast_id = %s", (podcast_id,))
            cur.execute("DELETE FROM podcasts WHERE id = %s AND user_id = %s", (podcast_id, user_id))
            db_manager.pg_conn.commit()

        # 删除音频缓存文件（onboarding_cache 共享音频，不删除底层文件）
        if audio_path and podcast_source != 'onboarding_cache':
            try:
                from pathlib import Path
                audio_file = Path(audio_path)
                if audio_file.exists():
                    audio_file.unlink()
                    logger.info(f"已删除音频文件: {audio_path}")
            except Exception as e:
                logger.warning(f"删除音频文件失败: {e}")

        logger.info(f"用户 {user_id} 删除了播客 {podcast_id}")
        return {"success": True, "message": "播客已删除"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除播客失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/podcasts/{podcast_id}")
async def get_podcast_detail(
    podcast_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """
    获取播客详情

    权限：需要登录
    """
    try:
        user_id = current_user["id"]

        # 查询播客信息
        query = """
        SELECT
            p.id,
            p.title,
            p.description,
            p.style,
            p.duration,
            p.cover_image,
            p.generation_status,
            p.generation_error,
            p.audio_url,
            p.play_count,
            p.source,
            p.created_at
        FROM podcasts p
        WHERE p.id = %s AND p.user_id = %s
        """

        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (podcast_id, user_id))
            result = cur.fetchall()

        if not result:
            raise HTTPException(status_code=404, detail="Podcast not found")

        row = result[0]
        podcast = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "style": row[3],
            "duration": row[4],
            "cover_image": row[5],
            "generation_status": row[6],
            "generation_error": row[7],
            "audio_url": row[8],
            "play_count": row[9],
            "source": row[10],
            "created_at": row[11].isoformat() if row[11] else None
        }

        # 查询关联文章（Phase 2：使用 global_articles）
        articles_query = """
        SELECT
            ga.id,
            ga.title,
            ga.url,
            ga.source_feed_url,
            uf.feed_name,
            pa.start_time,
            pa.end_time,
            pa.sequence_order
        FROM podcast_articles pa
        JOIN global_articles ga ON ga.id = pa.global_article_id
        LEFT JOIN user_feeds uf ON uf.feed_url = ga.source_feed_url AND uf.user_id = %s
        WHERE pa.podcast_id = %s
        ORDER BY pa.sequence_order
        """

        with db_manager.pg_conn.cursor() as cur:
            cur.execute(articles_query, (user_id, podcast_id))
            articles_result = cur.fetchall()

        articles = []
        for article_row in articles_result:
            articles.append({
                "id": article_row[0],
                "title": article_row[1],
                "url": article_row[2],
                "source": article_row[3],
                "feed_title": article_row[4],
                "start_time": article_row[5],
                "end_time": article_row[6],
                "sequence_order": article_row[7]
            })

        podcast["articles"] = articles

        # 查询播放进度
        progress_query = """
        SELECT current_position, progress_percentage, is_completed
        FROM podcast_play_progress
        WHERE user_id = %s AND podcast_id = %s
        """

        with db_manager.pg_conn.cursor() as cur:
            cur.execute(progress_query, (user_id, podcast_id))
            progress_result = cur.fetchall()

        if progress_result:
            podcast["progress"] = {
                "current_time": progress_result[0][0],
                "progress_percentage": progress_result[0][1],
                "is_completed": progress_result[0][2]
            }
        else:
            podcast["progress"] = None

        return {
            "success": True,
            "podcast": podcast
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取播客详情失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/podcasts/{podcast_id}/audio-url")
async def get_podcast_audio_url(
    podcast_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """
    获取播客音频的签名 URL（用于 HTML5 audio 标签）

    权限：需要登录
    返回：带签名的临时 URL，有效期 1 小时
    """
    try:
        user_id = current_user["id"]

        # 验证播客存在且属于当前用户
        query = """
        SELECT id FROM podcasts
        WHERE id = %s AND user_id = %s AND generation_status = 'completed'
        """
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (podcast_id, user_id))
            result = cur.fetchall()

        if not result:
            raise HTTPException(status_code=404, detail="Podcast not found")

        # 生成短期签名 URL（5 分钟有效），替代 JWT query token
        sig, expiry = _generate_audio_signature(podcast_id, user_id)
        audio_url = f"/api/v1/podcasts/{podcast_id}/audio?sig={sig}&exp={expiry}"
        return {
            "success": True,
            "audio_url": audio_url,
            "expires_in": _AUDIO_SIG_TTL_SECONDS
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成音频 URL 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/podcasts/{podcast_id}/audio")
async def get_podcast_audio(
    podcast_id: int,
    sig: Optional[str] = Query(None, description="签名（用于 HTML5 audio 标签）"),
    exp: Optional[int] = Query(None, description="签名过期时间戳"),
    current_user: Optional[Dict] = None,
    request: Request = None
):
    """
    播放播客音频（支持 Range 请求）

    权限：需要登录（支持签名 URL 或 Bearer token）
    """
    try:
        user_id = None

        # 优先使用签名 URL（用于 HTML5 audio 标签）
        if sig and exp:
            # 先从数据库查询该播客所属用户
            verify_query = """
            SELECT user_id FROM podcasts
            WHERE id = %s AND generation_status = 'completed'
            """
            with db_manager.pg_conn.cursor() as cur:
                cur.execute(verify_query, (podcast_id,))
                row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Podcast not found")

            podcast_owner_id = row[0]

            if not _verify_audio_signature(podcast_id, podcast_owner_id, sig, exp):
                raise HTTPException(status_code=401, detail="Invalid or expired signature")

            user_id = podcast_owner_id
        else:
            # 回退到 Bearer token（用于 API 调用）
            if not current_user:
                # 尝试从 Authorization header 获取
                from fastapi.security import HTTPBearer
                security = HTTPBearer()
                try:
                    credentials = await security(request)
                    current_user = await get_current_user(credentials)
                except:
                    raise HTTPException(status_code=401, detail="Authentication required")

            user_id = current_user["id"]

        # 查询播客音频路径
        query = """
        SELECT audio_url, duration
        FROM podcasts
        WHERE id = %s AND user_id = %s AND generation_status = 'completed'
        """

        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (podcast_id, user_id))
            result = cur.fetchall()

        if not result:
            raise HTTPException(status_code=404, detail="Podcast audio not found")

        audio_path = result[0][0]

        if not os.path.exists(audio_path):
            raise HTTPException(status_code=404, detail="Audio file not found")

        # 只在首次播放时更新播放次数（Range: bytes=0- 或无 Range header）
        range_header = request.headers.get("Range") if request else None
        is_first_request = (
            not range_header or  # 无 Range header
            range_header.startswith("bytes=0-")  # 从头开始的 Range 请求
        )
        if is_first_request:
            update_query = """
            UPDATE podcasts
            SET play_count = play_count + 1
            WHERE id = %s
            """
            with db_manager.pg_conn.cursor() as cur:
                cur.execute(update_query, (podcast_id,))
                db_manager.pg_conn.commit()

        # 返回音频文件（支持 Range）
        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "private, max-age=3600"  # 1 小时，匹配 token TTL
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"播放播客音频失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/podcasts/{podcast_id}/progress")
async def save_podcast_progress(
    podcast_id: int,
    request: PodcastProgressRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    保存播放进度

    权限：需要登录
    """
    try:
        user_id = current_user["id"]

        # 计算进度百分比
        progress_percentage = (request.current_time / request.total_time * 100) if request.total_time > 0 else 0

        # 插入或更新进度
        # 数据库列名是 current_position，不是 current_time
        query = """
        INSERT INTO podcast_play_progress (
            user_id,
            podcast_id,
            current_position,
            total_time,
            progress_percentage,
            is_completed,
            last_played_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_id, podcast_id)
        DO UPDATE SET
            current_position = EXCLUDED.current_position,
            total_time = EXCLUDED.total_time,
            progress_percentage = EXCLUDED.progress_percentage,
            is_completed = EXCLUDED.is_completed,
            last_played_at = NOW()
        """

        with db_manager.pg_conn.cursor() as cur:
            cur.execute(
                query,
                (
                    user_id,
                    podcast_id,
                    request.current_time,
                    request.total_time,
                    progress_percentage,
                    request.is_completed
                )
            )
            db_manager.pg_conn.commit()

        return {
            "success": True,
            "message": "Progress saved"
        }

    except Exception as e:
        logger.error(f"保存播放进度失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/podcasts/{podcast_id}/chat")
async def chat_with_podcast(
    podcast_id: int,
    request: PodcastChatRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    与播客对话

    权限：需要登录
    """
    try:
        user_id = current_user["id"]

        # 检查播客是否存在
        query = "SELECT id FROM podcasts WHERE id = %s AND user_id = %s"
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (podcast_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Podcast not found")

        # 获取用户语言偏好
        user_language = current_user.get('preferred_language', 'en')

        # 获取对话历史
        rag = get_podcast_rag()
        conversation_history = rag.get_conversation_history(
            podcast_id=podcast_id,
            user_id=user_id,
            limit=5
        )

        # 生成回复
        response = await rag.generate_response(
            podcast_id=podcast_id,
            user_message=request.message,
            conversation_history=conversation_history,
            language=user_language
        )

        # 保存对话
        article_ids = [art["id"] for art in response.get("related_articles", [])]
        rag.save_conversation(
            podcast_id=podcast_id,
            user_id=user_id,
            user_message=request.message,
            assistant_message=response["assistant_message"],
            context_article_ids=article_ids,
            context_segments=response.get("related_segments", [])
        )

        return {
            "success": True,
            "assistant_message": response["assistant_message"],
            "related_articles": response.get("related_articles", []),
            "related_segments": response.get("related_segments", [])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"播客对话失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/podcasts/{podcast_id}/conversations")
async def get_podcast_conversations(
    podcast_id: int,
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100)
):
    """
    获取播客对话历史

    权限：需要登录
    """
    try:
        user_id = current_user["id"]

        # 检查播客是否存在
        query = "SELECT id FROM podcasts WHERE id = %s AND user_id = %s"
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (podcast_id, user_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Podcast not found")

        # 获取对话历史
        rag = get_podcast_rag()
        conversations = rag.get_conversation_history(
            podcast_id=podcast_id,
            user_id=user_id,
            limit=limit
        )

        return {
            "success": True,
            "conversations": conversations
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/podcasts/{podcast_id}/suggested-questions")
async def get_podcast_suggested_questions(
    podcast_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """
    获取播客推荐问题（生成播客时已预生成，此接口直接读取）

    权限：需要登录
    """
    defaults = [
        "这期播客的核心观点是什么？",
        "有哪些值得关注的要点？",
        "能帮我总结一下主要内容吗？"
    ]
    try:
        user_id = current_user["id"]

        # 检查播客是否存在并读取预生成的问题
        query = """
        SELECT ps.suggested_questions
        FROM podcasts p
        JOIN podcast_scripts ps ON ps.podcast_id = p.id
        WHERE p.id = %s AND p.user_id = %s
        ORDER BY ps.created_at DESC
        LIMIT 1
        """
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (podcast_id, user_id))
            result = cur.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Podcast not found")

        questions = result[0] if result[0] else defaults

        return {
            "success": True,
            "questions": questions
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取推荐问题失败: {e}", exc_info=True)
        return {
            "success": True,
            "questions": defaults
        }


# ================== 公开分享 API (Phase 1: Podcast Sharing) ==================

_PREVIEW_AUDIO_SIG_TTL_SECONDS = 1800  # 预览音频签名有效期 30 分钟


def _generate_preview_audio_signature(podcast_id: int, user_id: str) -> tuple[str, int]:
    """生成播客预览音频的短期签名 URL 参数（30 分钟有效期）。"""
    expiry = int(datetime.now(timezone.utc).timestamp()) + _PREVIEW_AUDIO_SIG_TTL_SECONDS
    return _build_audio_signature(podcast_id, user_id, expiry), expiry


def _generate_share_token() -> str:
    """生成随机的分享令牌（16 字符 Base32）。"""
    import secrets
    return secrets.token_urlsafe(16)[:22]


@app.post("/api/v1/podcasts/{podcast_id}/share")
async def create_podcast_share(
    podcast_id: int,
    current_user: Dict = Depends(get_current_user)
):
    """
    为播客创建分享令牌（需认证，仅播客所有者）

    返回分享令牌。如果播客已有分享令牌，直接返回现有令牌（幂等）。
    使用 COALESCE 避免并发覆盖。
    """
    try:
        user_id = current_user["id"]

        # 先检查播客是否存在且属于当前用户
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM podcasts WHERE id = %s AND user_id = %s AND generation_status = 'completed'",
                (podcast_id, user_id)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Podcast not found")

        # 使用 COALESCE 单语句原子更新：已有 token 不覆盖
        for attempt in range(3):
            token = _generate_share_token()
            with db_manager.pg_conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE podcasts
                    SET share_token = COALESCE(share_token, %s)
                    WHERE id = %s
                    RETURNING share_token
                    """,
                    (token, podcast_id)
                )
                result = cur.fetchone()
                db_manager.pg_conn.commit()

            if result and result[0]:
                return {
                    "success": True,
                    "share_token": result[0]
                }

        raise HTTPException(status_code=500, detail="Failed to generate share token")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建播客分享失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/share/podcast-meta/{share_token}")
async def get_shared_podcast_meta(share_token: str):
    """
    通过分享令牌获取播客公开元数据（无需认证）

    用于分享页面的 OG 标签注入和预览页渲染。
    """
    try:
        query = """
        SELECT
            p.id,
            p.title,
            p.description,
            p.duration,
            p.cover_image,
            p.user_id,
            p.created_at
        FROM podcasts p
        WHERE p.share_token = %s AND p.generation_status = 'completed'
        """
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (share_token,))
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Share not found")

        podcast_id = row[0]

        articles_query = """
        SELECT
            ga.title,
            ga.url
        FROM podcast_articles pa
        JOIN global_articles ga ON ga.id = pa.global_article_id
        WHERE pa.podcast_id = %s
        ORDER BY pa.sequence_order
        """
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(articles_query, (podcast_id,))
            articles_rows = cur.fetchall()

        stories = []
        for article_row in articles_rows:
            stories.append({"title": article_row[0], "article_url": article_row[1]})

        return {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "duration": row[3],
            "cover_art_url": row[4],
            "created_at": row[6].isoformat() if row[6] else None,
            "stories": stories
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取播客分享元数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/share/podcast-audio/{share_token}")
async def get_shared_podcast_audio(share_token: str):
    """
    通过分享令牌获取播客音频预览 URL（无需认证）

    返回带签名的音频 URL，有效期 30 分钟。
    """
    try:
        query = """
        SELECT id, user_id FROM podcasts
        WHERE share_token = %s AND generation_status = 'completed'
        """
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(query, (share_token,))
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Share not found")

        podcast_id, user_id = row

        sig, expiry = _generate_preview_audio_signature(podcast_id, user_id)
        audio_url = f"/api/v1/podcasts/{podcast_id}/audio?sig={sig}&exp={expiry}"

        return {
            "success": True,
            "audio_url": audio_url,
            "expires_in": _PREVIEW_AUDIO_SIG_TTL_SECONDS
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成播客预览音频 URL 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ================== 前端日志收集 API (2025-12-30) ==================

class FrontendLogEntry(BaseModel):
    """前端日志条目"""
    timestamp: str  # 前端时间戳（东八区）
    level: str  # info, warn, error
    message: str
    context: Optional[Dict[str, Any]] = None  # 上下文信息（URL, userAgent 等）
    stack: Optional[str] = None  # 错误堆栈（仅 error 级别）


class FrontendLogsRequest(BaseModel):
    """前端日志批量上传请求"""
    logs: List[FrontendLogEntry]


@app.post("/api/v1/frontend-logs")
async def submit_frontend_logs(
    request: FrontendLogsRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    接收前端日志并写入 frontend.log

    权限：仅白名单用户可上传
    """
    from backend.utils.logger import get_frontend_logger

    # 验证白名单
    if not _is_frontend_log_whitelisted_user(current_user):
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized - only whitelist users can submit frontend logs"
        )

    username = current_user.get("username") or current_user.get("id")

    # 获取前端日志记录器
    frontend_logger = get_frontend_logger()

    # 批量写入日志
    for log_entry in request.logs:
        log_level = log_entry.level.upper()
        context = log_entry.context or {}

        # 添加用户名到上下文
        context["username"] = username

        # 根据日志级别写入
        if log_level == "ERROR":
            frontend_logger.error(
                log_entry.message,
                extra={
                    "extra": context,
                    "stack": log_entry.stack
                }
            )
        elif log_level == "WARN":
            frontend_logger.warning(
                log_entry.message,
                extra={"extra": context}
            )
        else:  # INFO
            frontend_logger.info(
                log_entry.message,
                extra={"extra": context}
            )

    return {
        "success": True,
        "received_count": len(request.logs)
    }


@app.post("/api/v1/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    接收用户反馈并持久化到数据库和日志
    """
    username = current_user.get("username") or current_user.get("id")
    user_id = current_user.get("id")

    # 持久化到数据库
    feedback_id = db_manager.save_user_feedback(
        user_id=user_id,
        message=req.message,
        attach_logs=req.attach_logs,
        frontend_logs=req.frontend_logs,
    )

    logger.info(
        "User feedback submitted",
        extra={
            "extra": {
                "username": username,
                "user_id": user_id,
                "feedback_id": feedback_id,
                "message": req.message,
                "attach_logs": req.attach_logs,
                "frontend_logs_count": len(req.frontend_logs) if req.frontend_logs else 0,
            }
        }
    )
    return {"success": True, "message": "Feedback received, thank you!"}

# ================== Week 5 Cleanup (2025-11-20): 微信 Cookie 管理 API 已移除 ==================
# Reason: Migrated to RSSHub-CookieCloud solution
# - RSSHub-CookieCloud provides direct browser→RSSHub cookie sync
# - No need for Readaria to act as intermediary
# - See docs/wechat_cookie_sync_solution_v2.md for new architecture

if __name__ == "__main__":
    # 配置 uvicorn 日志格式
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s - %(levelprefix)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(asctime)s - %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=log_config)


# ================== 自托管版配额与用量 API ==================

@app.get("/api/v1/subscription/me")
async def get_my_subscription(current_user: Dict = Depends(get_current_user)):
    """获取自托管版无限配额信息"""
    summary = subscription_service.get_subscription_summary(current_user['id'])
    return summary


@app.get("/api/v1/subscription/usage")
async def get_my_usage(current_user: Dict = Depends(get_current_user)):
    """获取当前用户今日用量"""
    usage_today = subscription_service.get_usage_today(current_user['id'])
    usage_week = subscription_service.get_usage_week(current_user['id'])
    plan = subscription_service.get_effective_plan(current_user['id'])
    return {
        "today": usage_today,
        "week": usage_week,
        "limits": {
            "tts_daily": plan['tts_daily_limit'],
            "podcast_daily": plan['podcast_daily_limit'],
            "ai_summary_daily": plan['ai_summary_daily_limit'],
        },
        "plan": plan['plan_id'],
    }


@app.get("/api/v1/onboarding/starter-pack")
@limiter.limit("30/minute")
async def get_starter_pack(request: Request, language: str = Query("en", description="用户语言")):
    """
    获取 onboarding starter pack feeds。
    只返回已通过内容质量验证的 feed 列表。
    """
    try:
        feeds = db_manager.get_starter_pack_feeds(language=language)
        # 将 datetime 对象序列化为 ISO 格式字符串
        serialized = []
        for f in feeds:
            row = dict(f)
            for key in ("last_article_at", "last_validated_at"):
                if row.get(key) and hasattr(row[key], "isoformat"):
                    row[key] = row[key].isoformat()
            serialized.append(row)
        return {"status": "success", "feeds": serialized}
    except Exception as e:
        logger.error(f"获取 starter pack 失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/onboarding/starter-pack/reset")
async def reset_starter_pack_feeds(
    request: Request,
    language: str = Query("en", description="用户语言"),
    current_user: Dict = Depends(get_current_user),
):
    """
    将当前用户的 starter pack 订阅重置为当前语言的标准集合。
    仅删除历史 starter pack 源，不影响用户手动添加的其它订阅。
    """
    try:
        user_id = current_user["id"]
        canonical_feeds = get_starter_pack_feed_defs(language)
        target_urls = {feed["feed_url"] for feed in canonical_feeds}
        legacy_urls = {
            feed["feed_url"]
            for lang in ("zh", "en")
            for feed in get_starter_pack_feed_defs(lang)
        }

        feeds = db_manager.get_user_feeds(user_id)
        removed_feed_ids = []
        for feed in feeds:
            feed_url = feed.get("feed_url")
            if feed_url in legacy_urls and feed_url not in target_urls:
                if db_manager.deactivate_user_feed(feed["id"], user_id=user_id):
                    removed_feed_ids.append(feed["id"])

        return {
            "status": "success",
            "removed_feed_ids": removed_feed_ids,
            "target_feed_urls": list(target_urls),
        }
    except Exception as e:
        logger.error(f"重置 starter pack 失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/onboarding/starter-pack/activate")
@limiter.limit("10/minute")
async def activate_starter_pack(
    request: Request,
    background_tasks: BackgroundTasks,
    language: str = Query("en", description="用户语言"),
    current_user: Dict = Depends(get_current_user),
):
    """
    为当前用户激活 starter pack。

    与逐条 addFeed 不同，此接口会在返回前同步链接已有 global_articles，
    确保 onboarding 跳转到 FeedView 时首屏文章列表已经有数据可读。
    """
    try:
        user_id = current_user["id"]
        canonical_feeds = get_starter_pack_feed_defs(language)
        normalized_feeds = []

        for feed in canonical_feeds:
            feed_name = feed.get("feed_name")
            feed_url = feed.get("feed_url")
            if not feed_name or not feed_url:
                logger.warning(f"跳过无效 starter pack feed: {feed}")
                continue

            is_rsshub_url = "rsshub" in feed_url.lower()
            is_valid, normalized_url, error_msg = url_validator.validate_and_normalize(
                feed_url,
                check_rsshub_host=is_rsshub_url,
            )
            if not is_valid:
                logger.warning(
                    f"跳过 starter pack URL 验证失败: feed={feed_name}, url={feed_url}, error={error_msg}"
                )
                continue

            normalized_feeds.append({
                "feed_name": feed_name,
                "feed_url": normalized_url,
            })

        if not normalized_feeds:
            raise HTTPException(status_code=503, detail="Starter pack 暂不可用")

        result = await run_in_threadpool(
            db_manager.activate_starter_pack_feeds,
            user_id,
            normalized_feeds,
        )

        feed_ids = [feed["feed_id"] for feed in result["feeds"]]
        feeds = db_manager.get_user_feeds(user_id)
        activated = [feed for feed in feeds if feed.get("id") in feed_ids]
        backfill_scheduled = False
        if result.get("needs_background_backfill") and background_tasks:
            def _backfill_starter_pack_global_articles():
                try:
                    with db_manager.connection_scope():
                        for feed in result["feeds"]:
                            db_manager.link_global_articles_to_feed(
                                user_id,
                                feed["feed_id"],
                                feed["feed_url"],
                            )
                    logger.info(
                        f"[onboarding_starter_pack] 后台补齐历史文章完成 user_id={user_id}, "
                        f"feeds={len(result['feeds'])}"
                    )
                except Exception as backfill_exc:
                    logger.warning(
                        f"[onboarding_starter_pack] 后台补齐历史文章失败 user_id={user_id}: {backfill_exc}"
                    )

            background_tasks.add_task(_backfill_starter_pack_global_articles)
            backfill_scheduled = True

        if activated and background_tasks:
            background_tasks.add_task(
                feed_refresher.refresh_feeds,
                feeds=activated,
                enable_logging=True,
                check_existence=True,
            )
        elif activated:
            logger.warning(
                f"[onboarding_starter_pack] BackgroundTasks 不可用，跳过后台刷新 user_id={user_id}"
            )

        return {
            "status": "success",
            "feeds": result["feeds"],
            "created_count": result["created_count"],
            "existing_count": result["existing_count"],
            "linked_count": result["linked_count"],
            "initial_link_limit": result.get("initial_link_limit"),
            "backfill_scheduled": backfill_scheduled,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"激活 starter pack 失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/onboarding/experience-podcast")
async def create_experience_podcast(
    request: Request,
    language: str = Query("zh", description="用户语言 (zh/en)"),
    current_user: Dict = Depends(get_current_user),
):
    """
    为新用户复制 onboarding experience 播客（Magic Moment）。

    逻辑：
    1. 根据 language 找到对应的 experience 用户
    2. 将该用户的最新已生成播客复制给当前用户（source='onboarding_cache'）
    3. 返回新播客的摘要信息，前端可直接跳转播放

    幂等：同一用户一天内多次调用只复制一次。
    """
    try:
        user_id = current_user["id"]
        normalized_language = "zh" if language.startswith("zh") else "en"
        experience_user_id = (
            "onboarding-experience-zh" if normalized_language == "zh" else "onboarding-experience-en"
        )

        # 幂等检查：今天是否已复制过相同语言的 onboarding cache
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.title, p.description, p.duration, p.cover_image, p.audio_url, p.created_at
                FROM podcasts p
                LEFT JOIN podcast_scripts ps ON ps.podcast_id = p.id
                WHERE user_id = %s AND source = 'onboarding_cache'
                  AND p.created_at >= CURRENT_DATE
                  AND (
                    (%s = 'zh' AND (ps.full_script IS NULL OR ps.full_script !~ '[A-Za-z]{4,}'))
                    OR
                    (%s = 'en' AND ps.full_script ~ '[A-Za-z]{4,}')
                  )
                ORDER BY p.created_at DESC
                LIMIT 1
                """,
                (user_id, normalized_language, normalized_language),
            )
            existing = cur.fetchone()

        if existing:
            return {
                "success": True,
                "podcast": {
                    "id": existing[0],
                    "title": existing[1],
                    "description": existing[2],
                    "duration": existing[3],
                    "cover_image": existing[4],
                    "audio_url": existing[5],
                    "created_at": existing[6].isoformat() if existing[6] else None,
                    "source": "onboarding_cache",
                },
                "message": "今日体验播客已存在",
            }

        # 执行复制
        new_podcast_id = db_manager.copy_podcast_to_user(
            source_user_id=experience_user_id,
            target_user_id=user_id,
            language=normalized_language,
        )

        if not new_podcast_id:
            # 无可用播客时返回 503，前端可降级为正常生成流程
            raise HTTPException(
                status_code=503,
                detail="体验播客暂不可用，请稍后重试或手动生成",
            )

        # 查询新播客详情返回
        with db_manager.pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, description, duration, cover_image, audio_url, created_at
                FROM podcasts
                WHERE id = %s
                """,
                (new_podcast_id,),
            )
            row = cur.fetchone()

        return {
            "success": True,
            "podcast": {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "duration": row[3],
                "cover_image": row[4],
                "audio_url": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "source": "onboarding_cache",
            },
            "message": "体验播客已就绪",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建 experience podcast 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
