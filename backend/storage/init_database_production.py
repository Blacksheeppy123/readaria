"""
生产环境数据库初始化脚本
使用单一的 production_init.sql 文件，跳过增量迁移
适用于全新的生产环境部署
"""
import os
import sys
import logging
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from core.config.settings import settings
from backend.storage.database import DatabaseManager

# 初始化 DatabaseManager
db_manager = DatabaseManager(pg_config=settings.postgres_config)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProductionDatabaseInitializer:
    """生产环境数据库初始化器"""

    def __init__(self):
        self.production_schema_file = Path(__file__).parent / 'production_init.sql'
        self.init_data_file = Path(__file__).parent / 'init_data.sql'

    def create_database_if_not_exists(self):
        """创建数据库（如果不存在）"""
        try:
            # 连接到默认数据库
            conn = psycopg2.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                user=settings.postgres_user,
                password=settings.postgres_password,
                database='postgres'
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()

            # 检查数据库是否存在
            cur.execute("""
                SELECT 1 FROM pg_database WHERE datname = %s
            """, (settings.postgres_db,))

            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{settings.postgres_db}"')
                logger.info(f"✅ 数据库 '{settings.postgres_db}' 创建成功")
            else:
                logger.info(f"ℹ️  数据库 '{settings.postgres_db}' 已存在")

            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"❌ 创建数据库失败: {e}")
            raise

    def schema_exists(self) -> bool:
        """Return whether the application schema has already been initialized."""
        with db_manager.pg_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'users'
                )
            """)
            exists = cur.fetchone()[0]
        db_manager.release_conn()
        return exists

    def execute_sql_file(self, sql_file: Path, description: str):
        """执行SQL文件"""
        if not sql_file.exists():
            logger.error(f"❌ SQL文件不存在: {sql_file}")
            raise FileNotFoundError(f"SQL文件不存在: {sql_file}")

        try:
            with db_manager.pg_conn.cursor() as cur:
                # 读取并执行SQL文件
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()

                cur.execute(sql_content)
                db_manager.pg_conn.commit()

                logger.info(f"✅ {description} 执行成功")

        except Exception as e:
            db_manager.pg_conn.rollback()
            logger.error(f"❌ {description} 执行失败: {e}")
            raise
        finally:
            db_manager.release_conn()

    def init_postgres(self):
        """初始化 PostgreSQL（生产环境）"""
        logger.info("=" * 60)
        logger.info("🚀 开始初始化生产环境 PostgreSQL...")
        logger.info("=" * 60)

        # 1. 创建数据库
        logger.info("\n📦 步骤 1: 创建数据库")
        self.create_database_if_not_exists()

        # 2. 全新部署时执行完整架构；已有部署保留数据并跳过初始化
        if self.schema_exists():
            logger.info("ℹ️  检测到现有数据库架构，跳过 production_init.sql")
        else:
            logger.info("\n📦 步骤 3: 创建数据库表结构")
            logger.info("ℹ️  使用 production_init.sql（基于本地开发数据库最终状态）")
            logger.info("ℹ️  跳过增量迁移脚本（migrations/*.sql）")
            self.execute_sql_file(self.production_schema_file, "生产环境数据库架构创建")

        # 4. 插入初始数据
        logger.info("\n📦 步骤 4: 插入初始数据")
        self.execute_sql_file(self.init_data_file, "初始数据插入")

        logger.info("\n" + "=" * 60)
        logger.info("✅ PostgreSQL 初始化完成")
        logger.info("=" * 60)

    def verify_installation(self):
        """验证安装"""
        logger.info("\n" + "=" * 60)
        logger.info("🔍 开始验证数据库安装...")
        logger.info("=" * 60)

        try:
            # 验证 PostgreSQL
            cur = db_manager.pg_conn.cursor()
            try:
                # 检查主要表是否存在
                tables_to_check = [
                    'users', 'source_types', 'user_feeds', 'articles',
                    'user_sessions', 'user_saved_articles', 'user_reading_history'
                ]

                logger.info("\n📦 检查数据库表...")
                for table in tables_to_check:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = %s
                        )
                    """, (table,))
                    if not cur.fetchone()[0]:
                        raise Exception(f"表 '{table}' 不存在")
                    logger.info(f"  ✅ {table}")

                # 检查初始数据
                logger.info("\n📦 检查初始数据...")
                cur.execute("SELECT COUNT(*) FROM source_types")
                source_types_count = cur.fetchone()[0]
                if source_types_count == 0:
                    raise Exception("未找到初始的源类型数据")

                logger.info(f"  ✅ 找到 {source_types_count} 个源类型")
            finally:
                cur.close()
                db_manager.release_conn()

            logger.info("\n" + "=" * 60)
            logger.info("✅ 数据库安装验证完成")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"❌ 数据库验证失败: {e}")
            raise

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Readaria 数据库初始化工具')
    parser.add_argument('--verify-only', action='store_true', help='仅验证数据库')

    args = parser.parse_args()

    initializer = ProductionDatabaseInitializer()

    try:
        print("\n" + "🎯" * 30)
        print("Readaria 数据库初始化")
        print("🎯" * 30)

        if args.verify_only:
            # 仅验证
            initializer.verify_installation()
        elif initializer.schema_exists():
            # 容器重启或已有部署：不重复初始化，也不隐式执行升级迁移
            logger.info("ℹ️  检测到现有数据库，跳过初始化；升级迁移请按文档单独执行")
            initializer.verify_installation()
        else:
            # 仅全新数据库执行完整初始化
            initializer.init_postgres()
            initializer.verify_installation()

        print("\n" + "=" * 60)
        print("✅ 数据库初始化成功完成！")
        print("=" * 60)
        print("\n下一步:")
        print("  1. 创建测试用户: python backend/scripts/create_test_user.py")
        print("  2. 启动 API 服务: sudo systemctl start readaria-api")
        print("  3. 验证 API 文档: curl http://localhost:8000/docs")
        print()

    except Exception as e:
        print(f"\n❌ 数据库初始化失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
