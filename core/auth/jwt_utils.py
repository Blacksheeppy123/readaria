"""
JWT认证工具模块
提供JWT token生成、验证和密码哈希功能
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置（从环境变量获取）
SECRET_KEY = None  # 将在初始化时从settings加载
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天


def init_jwt_config(secret_key: str, algorithm: str = "HS256", expire_minutes: int = 60 * 24 * 7):
    """
    初始化JWT配置

    Args:
        secret_key: JWT密钥
        algorithm: 加密算法，默认HS256
        expire_minutes: token过期时间（分钟），默认7天
    """
    global SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
    SECRET_KEY = secret_key
    ALGORITHM = algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES = expire_minutes
    logger.info(f"JWT配置已初始化: algorithm={algorithm}, expire_minutes={expire_minutes}")


# ================== 密码哈希功能 ==================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希密码是否匹配

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        bool: 密码是否匹配
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"密码验证失败: {str(e)}")
        return False


def get_password_hash(password: str) -> str:
    """
    对密码进行哈希

    Args:
        password: 明文密码

    Returns:
        str: 哈希后的密码
    """
    return pwd_context.hash(password)


# ================== JWT Token功能 ==================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建JWT访问令牌

    Args:
        data: 要编码到token中的数据（通常包含user_id, username等）
        expires_delta: token过期时间，如果不提供则使用默认值

    Returns:
        str: JWT token字符串

    Raises:
        ValueError: 如果JWT未初始化
    """
    if SECRET_KEY is None:
        raise ValueError("JWT未初始化，请先调用init_jwt_config()")

    to_encode = data.copy()

    # 设置过期时间
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,  # 过期时间
        "iat": datetime.utcnow(),  # 签发时间
    })

    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        logger.error(f"创建JWT token失败: {str(e)}")
        raise


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码并验证JWT访问令牌

    Args:
        token: JWT token字符串

    Returns:
        dict: 解码后的payload数据，如果验证失败返回None
    """
    if SECRET_KEY is None:
        logger.error("JWT未初始化")
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT解码失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"JWT验证出错: {str(e)}")
        return None


def verify_token(token: str) -> Optional[str]:
    """
    验证JWT token并返回用户ID

    Args:
        token: JWT token字符串

    Returns:
        str: 用户ID，如果验证失败返回None
    """
    payload = decode_access_token(token)
    if payload is None:
        return None

    # 从payload中提取user_id
    user_id = payload.get("sub")  # 'sub' (subject) 是JWT标准字段，用于存储用户标识
    return user_id


def create_user_token(user_id: str, username: str, **extra_data) -> str:
    """
    为用户创建JWT token（便捷方法）

    Args:
        user_id: 用户ID
        username: 用户名
        **extra_data: 其他要编码到token中的数据

    Returns:
        str: JWT token字符串
    """
    token_data = {
        "sub": user_id,  # 'sub' 标准字段存储用户ID
        "username": username,
        **extra_data
    }
    return create_access_token(token_data)


# ================== Token刷新功能（可选） ==================

def create_refresh_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建刷新令牌（过期时间更长）

    Args:
        user_id: 用户ID
        expires_delta: token过期时间，默认30天

    Returns:
        str: 刷新token字符串
    """
    if expires_delta is None:
        expires_delta = timedelta(days=30)

    token_data = {
        "sub": user_id,
        "type": "refresh"  # 标记为刷新token
    }
    return create_access_token(token_data, expires_delta=expires_delta)
