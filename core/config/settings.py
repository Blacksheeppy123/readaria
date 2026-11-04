"""
Readaria 知识管理系统 - 统一配置管理
"""
import os
from typing import Optional, List, Dict, Any
from pydantic import validator
from pydantic_settings import BaseSettings
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

class Settings(BaseSettings):
    """应用配置类"""

    # ---- Sentry 错误追踪 ----
    sentry_dsn: Optional[str] = None

    # ---- 应用基础配置 ----
    app_name: str = "Readaria Knowledge Management"
    app_version: str = "1.0.0"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ---- OpenAI 配置 ----
    openai_api_key: str
    openai_model: str = "gpt-5.6-luna"  # 2026-10-26: gpt-4.1-nano 已下线，官方推荐替代
    openai_base_url: str = "https://api.openai.com/v1"

    # ---- OpenRouter Fallback 配置 ----
    # 当 OpenAI 接口达到调用量限制时，自动切换到 OpenRouter
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "moonshotai/kimi-k2.5"

    # ---- TTS Provider 配置 ----
    # 可选: "openai" | "azure" | "google" (默认优先使用 google，其次是 azure，最后是 openai)
    tts_provider: str = "google"  # 默认 TTS 提供商

    # ---- Google Cloud TTS 配置 ----
    # 使用 Google Cloud Text-to-Speech API
    # 1. 创建服务账号并下载 JSON 密钥文件: https://console.cloud.google.com/iam-admin/serviceaccounts
    # 2. 启用 Text-to-Speech API: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
    google_cloud_credentials_path: str = ""  # 服务账号 JSON 密钥文件路径
    google_application_credentials: str = ""  # 兼容标准环境变量 GOOGLE_APPLICATION_CREDENTIALS
    google_cloud_tts_voice: str = "cmn-CN-Standard-A"  # 默认中文女声
    google_cloud_tts_language_code: str = "cmn-CN"  # 语言代码

    # ---- Azure OpenAI TTS 配置 ----
    # 使用 Azure OpenAI TTS 服务（Sweden Central 区域）
    # 注意：NLP 处理（摘要、实体提取）仍使用上面的 OpenAI 配置
    azure_openai_tts_endpoint: str = ""  # Azure OpenAI endpoint，例如：https://your-resource.openai.azure.com/
    azure_openai_tts_api_key: str = ""  # Azure OpenAI API key
    azure_openai_tts_deployment: str = "tts"  # Azure OpenAI TTS 部署名称（在 Azure Portal 中配置）
    azure_openai_api_version: str = "2024-02-15-preview"  # Azure OpenAI API 版本

    # ---- Azure Cognitive Services Speech 配置（免费额度 TTS 方案）----
    # 每月 50 万 Neural TTS 字符免费；需要在 Azure Portal 创建 Speech 资源
    azure_speech_key: Optional[str] = None
    azure_speech_region: Optional[str] = None
    azure_speech_tts_voice: str = "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural"  # 默认中文女声（新一代 DragonHD Flash，自然度更高）
    azure_speech_output_format: str = "Audio48Khz96KBitRateMonoMp3"  # 输出音质（按字符计费，提升码率不增加费用）

    # ---- OpenAI TTS 配置（已弃用，改用 Azure OpenAI）----
    # TTS 模型配置
    openai_tts_model: str = "tts-1"  # 标准版 ($0.015/1K chars)，高质量版 "tts-1-hd" ($0.030/1K chars) 速度较慢
    openai_tts_voice: str = "nova"  # 默认声音：alloy (中性)、nova/shimmer (女声)、echo/fable/onyx (男声)
    openai_tts_format: str = "mp3"  # 音频格式：mp3 (完美兼容所有平台)、opus、aac、flac、wav、pcm

    # 缓存配置（本地文件系统）
    tts_cache_dir: str = "audio_cache/"  # 音频缓存目录（相对路径，兼容本地/生产环境）
    tts_cache_max_size_gb: int = 10  # 最大缓存容量（GB）
    tts_cache_expiry_days: int = 14  # 缓存过期天数

    # ---- TTS 预合成配置 (Phase 3) ----
    # 预合成功能：RSS 抓取文章后自动生成第一段 TTS，实现秒播
    tts_pregenerate_enabled: bool = True  # 是否启用预合成功能
    tts_pregenerate_max_length: int = 1000  # 预合成第一段的最大长度（字符）
    tts_segment_cache_dir: str = "/app/audio_cache/tts_segments"  # 预合成缓存目录（复用现有挂载点）
    tts_pregenerate_async: bool = True  # 是否异步执行预合成（不阻塞 RSS 抓取）

    # 预生成并发控制（OpenAI Rate Limit: 100 RPM）
    tts_pregenerate_concurrency: int = 20  # 预生成最大并发数
    tts_pregenerate_min_interval: int = 3   # 预生成请求最小间隔（秒），20 并发时约 3s/request

    # 预合成范围控制（成本控制）
    # True: 所有用户的文章都预合成（成本高，适用于正式用户多的场景）
    # False: 仅为测试用户（test-user）的文章预合成（成本低，适用于测试阶段）
    tts_pregenerate_all_users: bool = False  # 是否为所有用户预合成 TTS

    # 文本处理配置
    tts_max_chars_per_request: int = 3000  # OpenAI 单次请求上限（基于 4096 tokens）
    tts_max_article_length: int = 30000  # 文章总长度上限（约 10 分钟朗读）
    tts_long_article_strategy: str = "segment"  # 超长文章处理策略："segment" (分段合并) | "truncate" (截断) | "reject" (拒绝)
    tts_segment_generation_timeout_seconds: int = 45  # 单个分段生成超时（秒）

    # TTS 首播延迟优化（单段起播）
    tts_first_segments_parallel_count: int = 1  # 并行生成的首段数量（改为1，单段满足阈值即起播）
    tts_segment_generation_concurrency: int = 3  # per-process segment 并发上限
    tts_first_playable_min_seconds: int = 25  # first_playable 阈值（秒），140字中文约30秒音频
    tts_segment_target_first: int = 140  # segment 0 目标字符数（缩短以减少API耗时）

    # 降级策略
    tts_enable_fallback: bool = True  # 失败时是否降级到本地 TTS（Web Speech API）

    # 成本控制
    tts_daily_budget_usd: float = 5.0  # 每日预算（美元）
    tts_monthly_budget_usd: float = 100.0  # 每月预算（美元）

    # ---- 播客生成配置 ----
    podcast_enabled: bool = True  # 是否启用播客功能
    podcast_generation_hour: int = 0  # 每日生成时间（UTC 小时，0=北京时间 08:00）
    podcast_generation_minute: int = 15  # 每日生成时间（UTC 分钟）。与 minute=0 hourly fetch 错开，给抓取留时间窗口
    podcast_max_articles: int = 10  # 每个播客最大文章数
    podcast_style_default: str = "deep_dive"  # 默认播客样式
    podcast_audio_cache_dir: str = "/app/podcast_cache/"  # 播客音频缓存目录

    # 播客成本控制
    podcast_daily_budget_usd: float = 10.0  # 每日预算（美元）
    podcast_monthly_budget_usd: float = 200.0  # 每月预算（美元）

    # 播客 RAG 配置
    podcast_rag_context_max_length: int = 8000  # RAG 上下文最大长度
    podcast_rag_conversation_history_limit: int = 5  # 对话历史保留条数

    # ---- PostgreSQL 配置 ----
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "readaria"
    postgres_user: str = "postgres"
    postgres_password: str
    postgres_sslmode: str = "disable"

    # ---- Redis 配置 ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0

    # ---- RSSHub 配置 ----
    # 2026-05-18: 本地 RSSHub 服务已移除，所有 RSSHub 源直接使用公共实例。
    # 以下配置保留向后兼容，但不再生效：
    # - rsshub_local_url / rsshub_force_local / rsshub_platform_routing 已废弃
    # - rsshub_allowed_hosts 仍用于 SSRF 防护白名单
    rsshub_local_url: str = "http://localhost:1200"
    rsshub_proxy_url: Optional[str] = None
    rsshub_allowed_hosts: str = "rsshub.app,localhost,127.0.0.1,rsshub.moeyy.cn,rsshub.uneasy.win,yangzhi.app"

    # ---- wechat2rss 配置 ----
    # Docker 环境应设置为 http://wechat2rss:8080，本地开发为 http://localhost:4001
    wechat2rss_base_url: str = "http://localhost:4001"

    # ---- 微信公众号 / WeChat 配置 ----
    # 全局微信 Cookie，用于微信公众号抓取（可选）
    # 建议通过环境变量 WECHAT_COOKIE 配置
    wechat_cookie: Optional[str] = None

    # Week 5 Phase 3: RSSHub 路由配置 (2026-05-18 已废弃)
    # 本地 RSSHub 服务已移除，以下配置不再生效，保留仅用于向后兼容：
    rsshub_force_local: bool = False
    rsshub_platform_routing: Optional[str] = None

    # ---- 日志配置 ----
    log_level: str = "INFO"
    log_max_size: str = "10MB"
    log_backup_count: int = 5

    # ---- NLP 处理配置 ----
    spacy_model: str = "zh_core_web_sm"
    max_summary_length: int = 150
    entity_extraction_enabled: bool = True

    # ---- 公共 Demo（默认关闭）----
    demo_mode: bool = False
    demo_turnstile_secret_key: str = ""
    demo_daily_interaction_limit: int = 3

    # ---- 抓取配置 ----
    fetch_max_retries: int = 3
    fetch_timeout: int = 30
    fetch_delay_seconds: int = 2
    max_articles_per_feed: int = 20
    # 抓取限流配置（按 host）
    fetch_max_concurrent_per_host: int = 3  # 每个域名最大并发数
    fetch_request_interval: float = 0.5  # 请求间隔（秒）
    # 允许的 URL 协议白名单
    allowed_url_schemes: str = "http,https"
    # HTML 内容最大长度（字节，防止恶意内容）
    max_html_content_length: int = 500_000  # 500KB

    # ---- 缓存配置 ----
    # 用户订阅源列表缓存时间（秒），用于降低 get_user_feeds 查询频率
    user_feeds_cache_ttl_seconds: int = 120

    # ---- 安全配置 ----
    secret_key: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 10080  # 7天 = 7 * 24 * 60 分钟

    # ---- API 限流配置 ----
    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "10/minute"          # 登录/注册
    rate_limit_tts: str = "20/minute"           # TTS 端点（成本敏感）
    rate_limit_podcast: str = "5/minute"        # 播客生成
    rate_limit_admin: str = "30/minute"         # 管理员端点
    rate_limit_feed_refresh: str = "10/minute"  # Feed 刷新

    # ---- CORS 配置 ----
    cors_allowed_origins: str = "http://localhost:5174,http://localhost:5173,http://localhost:3000"

    # ---- 密码策略 ----
    password_min_length: int = 8
    password_require_mixed: bool = True  # 要求字母 + 数字

    # ---- Google OAuth ----
    google_oauth_client_id: str = ""  # Google Cloud Console OAuth Client ID

    # ---- 白名单配置 ----
    # 功能白名单：允许使用测试期特权能力（AI 摘要、播客、TTS 预生成等）
    feature_whitelist: List[str] = []

    # 前端日志白名单：仅允许上传浏览器端日志，不授予其它特权
    frontend_log_whitelist: List[str] = []

    @validator('feature_whitelist', pre=True)
    def parse_feature_whitelist(cls, v):
        """解析功能白名单（支持字符串或列表）"""
        if isinstance(v, str):
            return [user.strip() for user in v.split(',') if user.strip()]
        return v or []

    @validator('frontend_log_whitelist', pre=True)
    def parse_frontend_log_whitelist(cls, v):
        """解析前端日志白名单（支持字符串或列表）"""
        if isinstance(v, str):
            # 支持逗号分隔的字符串：FRONTEND_LOG_WHITELIST=test-user,admin,developer
            return [user.strip() for user in v.split(',') if user.strip()]
        return v or []

    class Config:
        env_file = PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator('openai_api_key')
    def validate_openai_api_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError('OpenAI API key must be provided and valid')
        return v

    @validator('postgres_password')
    def validate_postgres_password(cls, v):
        if not v:
            raise ValueError('PostgreSQL password must be provided')
        return v

    @validator('secret_key')
    def validate_secret_key(cls, v):
        if not v or len(v) < 32:
            raise ValueError('Secret key must be at least 32 characters long')
        return v

    @property
    def postgres_url(self) -> str:
        """PostgreSQL 连接URL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def postgres_config(self) -> dict:
        """PostgreSQL 配置字典"""
        return {
            'host': self.postgres_host,
            'port': self.postgres_port,
            'dbname': self.postgres_db,
            'user': self.postgres_user,
            'password': self.postgres_password,
            'sslmode': self.postgres_sslmode
        }

    @property
    def redis_url(self) -> str:
        """Redis 连接URL"""
        auth_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def resolved_google_credentials_path(self) -> str:
        """
        统一解析 Google Cloud 凭据路径。

        优先级：
        1. GOOGLE_CLOUD_CREDENTIALS_PATH（项目显式配置）
        2. GOOGLE_APPLICATION_CREDENTIALS（Google 官方标准环境变量）
        """
        return self.google_cloud_credentials_path or self.google_application_credentials

    @property
    def log_config(self) -> dict:
        """日志配置字典"""
        return {
            'level': self.log_level,
            'max_size': self.log_max_size,
            'backup_count': self.log_backup_count,
            'log_dir': PROJECT_ROOT / 'data' / 'logs'
        }

    @property
    def rsshub_public_endpoints(self) -> List[str]:
        """公共 RSSHub 端点列表"""
        return [
            "https://rsshub.app/",
            "https://rsshub.moeyy.cn/",
            "https://rsshub.uneasy.win/",
            "https://yangzhi.app/"
        ]

    @property
    def rsshub_allowed_hosts_list(self) -> List[str]:
        """RSSHub 允许的主机列表"""
        return [host.strip() for host in self.rsshub_allowed_hosts.split(',') if host.strip()]

    @property
    def allowed_url_schemes_list(self) -> List[str]:
        """允许的 URL 协议列表"""
        return [scheme.strip() for scheme in self.allowed_url_schemes.split(',') if scheme.strip()]

# 创建全局配置实例
try:
    settings = Settings()
except Exception as e:
    print(f"配置加载失败: {e}")
    print("请确保 .env 文件存在并包含所有必需的配置项")
    print("可以参考 .env.example 文件创建 .env 文件")
    raise

# ---- TTS 音色目录（用户音色选择功能，2026-09-07）----
# 面向用户的可选音色清单，id 为 Azure Speech 完整音色名。
# 已对 eastasia 区域可用性验证（Azure voices/list API，2026-09-07）。
# 注意：目录为 azure_speech provider 专属；切换 provider 需重新审视。
# is_default 必须与生产默认一致：zh=Xiaoxiao / en=Tiana（不改缓存行为）。
TTS_VOICE_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "zh": [
        {
            "id": "zh-CN-Xiaoxiao:DragonHDFlashLatestNeural",
            "lang": "zh",
            "name": "晓晓",
            "description": "温暖女声",
            "gender": "female",
            "is_default": True,
            "sample_text": "你好，欢迎收听 Readaria 为你朗读的文章。",
        },
        {
            "id": "zh-CN-Yunyi:DragonHDFlashLatestNeural",
            "lang": "zh",
            "name": "云希",
            "description": "清亮男声",
            "gender": "male",
            "is_default": False,
            "sample_text": "你好，欢迎收听 Readaria 为你朗读的文章。",
        },
        {
            "id": "zh-CN-YunyangNeural",
            "lang": "zh",
            "name": "云野",
            "description": "新闻男声",
            "gender": "male",
            "is_default": False,
            "sample_text": "你好，欢迎收听 Readaria 为你朗读的文章。",
        },
        {
            "id": "zh-CN-Xiaoyi:DragonHDFlashLatestNeural",
            "lang": "zh",
            "name": "晓伊",
            "description": "活泼女声",
            "gender": "female",
            "is_default": False,
            "sample_text": "你好，欢迎收听 Readaria 为你朗读的文章。",
        },
        {
            "id": "zh-CN-Xiaohan:DragonHDFlashLatestNeural",
            "lang": "zh",
            "name": "晓涵",
            "description": "成熟女声",
            "gender": "female",
            "is_default": False,
            "sample_text": "你好，欢迎收听 Readaria 为你朗读的文章。",
        },
        {
            "id": "zh-CN-Xiaoshuang:DragonHDFlashLatestNeural",
            "lang": "zh",
            "name": "晓双",
            "description": "儿童童声",
            "gender": "female",
            "is_default": False,
            "sample_text": "你好，欢迎收听 Readaria 为你朗读的文章。",
        },
    ],
    "en": [
        {
            "id": "en-US-Tiana:DragonHDFlashLatestNeural",
            "lang": "en",
            "name": "Tiana",
            "description": "温暖女声",
            "gender": "female",
            "is_default": True,
            "sample_text": "Hi, this is a preview of Readaria's narration voice.",
        },
        {
            "id": "en-US-Jimmie:DragonHDFlashLatestNeural",
            "lang": "en",
            "name": "Jimmie",
            "description": "明亮男声",
            "gender": "male",
            "is_default": False,
            "sample_text": "Hi, this is a preview of Readaria's narration voice.",
        },
        {
            "id": "en-US-Ava:DragonLatestNeural",
            "lang": "en",
            "name": "Ava",
            "description": "清晰女声",
            "gender": "female",
            "is_default": False,
            "sample_text": "Hi, this is a preview of Readaria's narration voice.",
        },
        {
            "id": "en-US-Andrew:DragonLatestNeural",
            "lang": "en",
            "name": "Andrew",
            "description": "低沉男声",
            "gender": "male",
            "is_default": False,
            "sample_text": "Hi, this is a preview of Readaria's narration voice.",
        },
    ],
}

# 向后兼容的配置导出
POSTGRES_CONFIG = settings.postgres_config

__all__ = ['settings', 'POSTGRES_CONFIG', 'PROJECT_ROOT', 'TTS_VOICE_CATALOG']
