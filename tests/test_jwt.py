"""
测试JWT工具函数
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.auth import jwt_utils
from core.config.settings import settings

# 初始化JWT配置
jwt_utils.init_jwt_config(
    secret_key=settings.jwt_secret_key,
    algorithm=settings.jwt_algorithm,
    expire_minutes=settings.jwt_access_token_expire_minutes
)

print("=== 测试密码哈希功能 ===")
password = "test123"
hashed = jwt_utils.get_password_hash(password)
print(f"原始密码: {password}")
print(f"哈希密码: {hashed}")
print(f"密码验证: {jwt_utils.verify_password(password, hashed)}")
print(f"错误密码验证: {jwt_utils.verify_password('wrong', hashed)}")
print()

print("=== 测试JWT Token生成和验证 ===")
user_id = "test-user"
username = "test-user"

# 创建token
token = jwt_utils.create_user_token(user_id, username, email="test@example.com")
print(f"生成的Token: {token[:50]}...")
print()

# 验证token
verified_user_id = jwt_utils.verify_token(token)
print(f"验证结果 - 用户ID: {verified_user_id}")

# 解码token查看完整payload
payload = jwt_utils.decode_access_token(token)
print(f"Token Payload: {payload}")
print()

print("=== 测试完成 ===")
