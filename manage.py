#!/usr/bin/env python3
"""
Jasmine 知识管理系统 - 管理脚本
"""
import os
import sys
import asyncio
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

def setup_environment():
    """设置环境"""
    # 检查 .env 文件
    env_file = project_root / '.env'
    if not env_file.exists():
        env_example = project_root / '.env.example'
        if env_example.exists():
            print("❌ .env 文件不存在")
            print(f"请复制 {env_example} 到 {env_file} 并修改相应配置")
            sys.exit(1)
        else:
            print("❌ 缺少环境配置文件")
            sys.exit(1)

def init_database(reset=False, production=False):
    """初始化数据库

    Args:
        reset: 是否重置数据库（仅开发环境）
        production: 是否使用生产环境初始化（跳过 migrations，使用 production_init.sql）
    """
    if production:
        # 生产环境：使用 production_init.sql（基于本地开发数据库最终状态）
        print("🚀 使用生产环境初始化脚本...")
        from backend.storage.init_database_production import ProductionDatabaseInitializer
        initializer = ProductionDatabaseInitializer()

        if reset:
            print("❌ 生产环境不支持 --reset 参数")
            sys.exit(1)

        print("🔧 正在初始化生产环境数据库...")
        initializer.init_postgres()
        initializer.verify_installation()
    else:
        # 开发环境：使用 schemas.sql + migrations
        print("🔧 使用开发环境初始化脚本...")
        from backend.storage.init_database import DatabaseInitializer
        initializer = DatabaseInitializer()

        if reset:
            print("⚠️  正在重置数据库...")
            initializer.reset_database()
        else:
            print("🔧 正在初始化数据库...")
            initializer.init_postgres()
            initializer.verify_installation()

    print("✅ 数据库初始化完成")

async def test_database():
    """测试数据库"""
    from scripts.test_database import DatabaseTester

    print("🧪 开始数据库测试...")
    tester = DatabaseTester()
    await tester.run_all_tests()
    print("✅ 数据库测试完成")

def start_server():
    """启动服务器"""
    import uvicorn
    from backend.api.main import app

    print("🚀 启动 Jasmine 服务器...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )

def check_health():
    """检查系统健康状态"""
    from backend.storage.database_manager_v2 import database_v2

    print("🔍 检查系统健康状态...")
    health = database_v2.health_check()

    print(f"状态: {health['status']}")
    print(f"时间: {health['timestamp']}")

    for service, status in health['services'].items():
        emoji = "✅" if status else "❌"
        print(f"{emoji} {service}: {'正常' if status else '异常'}")

    if 'statistics' in health:
        print("\n📊 统计信息:")
        for key, value in health['statistics'].items():
            print(f"  {key}: {value}")

def show_stats():
    """显示系统统计"""
    from backend.storage.database_manager_v2 import database_v2

    print("📊 系统统计信息:")
    stats = database_v2.get_system_stats()

    for key, value in stats.items():
        if value is None:
            value = "N/A"
        elif isinstance(value, float):
            value = f"{value:.2f}"
        print(f"  {key}: {value}")

def create_user():
    """创建用户"""
    import getpass

    # 数据层: 优先使用 v2，如果不可用则回退到 DatabaseManager
    try:
        from backend.storage.database_manager_v2 import database_v2 as _db
        db = _db
    except Exception:
        try:
            from core.config.settings import settings
            from backend.storage.database import DatabaseManager
            db = DatabaseManager(settings.postgres_config)
        except Exception as e:
            print(f"❌ 初始化数据库连接失败: {e}")
            return

    # 加载 bcrypt
    try:
        from passlib.hash import bcrypt
    except Exception:
        bcrypt = None

    print("👤 创建新用户")

    username = input("用户名: ").strip()
    if not username:
        print("❌ 用户名不能为空")
        return

    email = input("邮箱: ").strip()
    if not email:
        print("❌ 邮箱不能为空")
        return

    password = getpass.getpass("密码: ")
    if len(password) < 6:
        print("❌ 密码至少6位")
        return

    full_name = input("全名 (可选): ").strip() or None

    # 更安全的密码哈希（bcrypt）
    if not bcrypt:
        print("❌ 缺少依赖: passlib[bcrypt]。请先安装依赖后重试。")
        print("   pip install 'passlib[bcrypt]'")
        return
    password_hash = bcrypt.hash(password)

    try:
        # v2 对象与 DatabaseManager 接口命名不同，这里统一调用常见签名
        if hasattr(db, 'create_user'):
            user_id = db.create_user(username, email, password_hash, full_name)
        else:
            raise Exception('未找到可用的 create_user 方法')
        print(f"✅ 用户创建成功: {username} ({user_id})")
    except Exception as e:
        print(f"❌ 用户创建失败: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Jasmine 知识管理系统管理工具')

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 数据库相关命令
    db_parser = subparsers.add_parser('db', help='数据库操作')
    db_subparsers = db_parser.add_subparsers(dest='db_command')

    init_parser = db_subparsers.add_parser('init', help='初始化数据库')
    init_parser.add_argument('--reset', action='store_true', help='重置数据库（仅开发环境）')
    init_parser.add_argument('--production', action='store_true', help='使用生产环境初始化（跳过 migrations）')

    db_subparsers.add_parser('test', help='测试数据库')
    db_subparsers.add_parser('health', help='检查数据库健康')
    db_subparsers.add_parser('stats', help='显示系统统计')

    # 用户管理
    user_parser = subparsers.add_parser('user', help='用户管理')
    user_subparsers = user_parser.add_subparsers(dest='user_command')
    user_subparsers.add_parser('create', help='创建用户')

    # 服务器命令
    subparsers.add_parser('runserver', help='启动开发服务器')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 设置环境
    setup_environment()

    try:
        if args.command == 'db':
            if args.db_command == 'init':
                init_database(reset=args.reset, production=args.production)
            elif args.db_command == 'test':
                asyncio.run(test_database())
            elif args.db_command == 'health':
                check_health()
            elif args.db_command == 'stats':
                show_stats()
            else:
                db_parser.print_help()

        elif args.command == 'user':
            if args.user_command == 'create':
                create_user()
            else:
                user_parser.print_help()

        elif args.command == 'runserver':
            start_server()

    except KeyboardInterrupt:
        print("\n👋 操作被用户取消")
    except Exception as e:
        print(f"\n❌ 操作失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
