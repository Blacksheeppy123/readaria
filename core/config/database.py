"""
数据库配置 - 向后兼容模块
建议使用 config.settings 中的新配置系统
"""
import warnings
from core.config.settings import settings

# 发出弃用警告
warnings.warn(
    "config.database 模块已弃用，请使用 config.settings 替代",
    DeprecationWarning,
    stacklevel=2
)

# 向后兼容的配置导出
POSTGRES_CONFIG = settings.postgres_config