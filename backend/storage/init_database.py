"""
数据库初始化脚本 - 支持完整的数据库设置和迁移
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

class DatabaseInitializer:
    """数据库初始化器"""

    def __init__(self):
        self.schema_file = Path(__file__).parent / 'schemas.sql'
        self.init_data_file = Path(__file__).parent / 'init_data.sql'
        self.migrations_dir = Path(__file__).parent / 'migrations'

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
                logger.info(f"数据库 '{settings.postgres_db}' 创建成功")
            else:
                logger.info(f"数据库 '{settings.postgres_db}' 已存在")

            cur.close()
            conn.close()

        except Exception as e:
            logger.error(f"创建数据库失败: {e}")
            raise

    def execute_sql_file(self, sql_file: Path, description: str):
        """执行SQL文件"""
        if not sql_file.exists():
            logger.warning(f"SQL文件不存在: {sql_file}")
            return

        try:
            with db_manager.pg_conn.cursor() as cur:
                # 读取并执行SQL文件
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()

                cur.execute(sql_content)
                db_manager.pg_conn.commit()

                logger.info(f"{description} 执行成功")

        except Exception as e:
            db_manager.pg_conn.rollback()
            logger.error(f"{description} 执行失败: {e}")
            raise
        finally:
            db_manager.release_conn()

    def init_postgres(self):
        """初始化 PostgreSQL"""
        logger.info("开始初始化 PostgreSQL...")

        # 1. 创建数据库
        self.create_database_if_not_exists()

        # 2. 执行数据库架构
        self.execute_sql_file(self.schema_file, "数据库架构创建")

        # 4. 执行增量迁移（按文件名顺序）
        self.execute_migrations()

        # 5. 插入初始数据
        self.execute_sql_file(self.init_data_file, "初始数据插入")

        logger.info("PostgreSQL 初始化完成")

    def execute_migrations(self):
        """按顺序执行 migrations 目录下的 *.sql 文件"""
        try:
            if not self.migrations_dir.exists():
                logger.info("未找到 migrations 目录，跳过数据库迁移")
                return

            files = sorted([p for p in self.migrations_dir.glob('*.sql')])
            if not files:
                logger.info("migrations 目录为空，跳过数据库迁移")
                return

            for sql_path in files:
                self.execute_sql_file(sql_path, f"数据库迁移: {sql_path.name}")

        except Exception as e:
            logger.error(f"执行数据库迁移失败: {e}")
            raise

    def verify_installation(self):
        """验证安装"""
        logger.info("开始验证数据库安装...")

        try:
            # 验证 PostgreSQL
            cur = db_manager.pg_conn.cursor()
            try:
                # 检查主要表是否存在
                tables_to_check = [
                    'users', 'source_types', 'user_feeds', 'articles',
                    'entities', 'categories', 'tags', 'system_settings'
                ]

                for table in tables_to_check:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = %s
                        )
                    """, (table,))
                    if not cur.fetchone()[0]:
                        raise Exception(f"表 '{table}' 不存在")

                # 检查初始数据
                cur.execute("SELECT COUNT(*) FROM source_types")
                source_types_count = cur.fetchone()[0]
                if source_types_count == 0:
                    raise Exception("未找到初始的源类型数据")

                logger.info(f"PostgreSQL 验证成功 - 找到 {source_types_count} 个源类型")
            finally:
                cur.close()
                db_manager.release_conn()

            logger.info("数据库安装验证完成")

        except Exception as e:
            logger.error(f"数据库验证失败: {e}")
            raise

    def drop_all_tables(self):
        """删除所有表（危险操作，仅用于开发环境）"""
        if not settings.app_debug:
            raise Exception("只能在调试模式下删除所有表")

        logger.warning("正在删除所有数据库表...")

        try:
            with db_manager.get_postgres_cursor() as cur:
                # 获取所有表名
                cur.execute("""
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                """)
                tables = [row[0] for row in cur.fetchall()]

                # 删除所有表
                for table in tables:
                    cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

                logger.warning(f"已删除 {len(tables)} 个表")

        except Exception as e:
            logger.error(f"删除表失败: {e}")
            raise

    def reset_database(self):
        """重置数据库（完全重新初始化）"""
        if not settings.app_debug:
            raise Exception("只能在调试模式下重置数据库")

        logger.warning("正在重置数据库...")
        self.drop_all_tables()
        self.init_postgres()
        self.verify_installation()
        logger.info("数据库重置完成")

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Readaria 数据库初始化工具')
    parser.add_argument('--reset', action='store_true', help='重置数据库（删除所有数据）')
    parser.add_argument('--verify-only', action='store_true', help='仅验证数据库')

    args = parser.parse_args()

    initializer = DatabaseInitializer()

    try:
        if args.reset:
            if not settings.app_debug:
                print("错误: 重置数据库只能在调试模式下进行")
                sys.exit(1)
            initializer.reset_database()
        elif args.verify_only:
            initializer.verify_installation()
        else:
            # 正常初始化
            initializer.init_postgres()
            initializer.verify_installation()

        print("✅ 数据库初始化成功完成！")

    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
