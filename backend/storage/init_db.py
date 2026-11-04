import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import logging

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from core.config.database import POSTGRES_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_postgres():
    """初始化PostgreSQL数据库"""
    try:
        # 连接到默认数据库
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password'],
            database='postgres'
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # 创建数据库（如果不存在）
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{POSTGRES_CONFIG['dbname']}'")
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {POSTGRES_CONFIG['dbname']}")
            logger.info(f"创建数据库: {POSTGRES_CONFIG['dbname']}")
        
        cur.close()
        conn.close()
        
        # 连接到目标数据库
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()
        
        # 检查表是否存在
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'articles'
            );
        """)
        
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            # 创建完整的表结构
            cur.execute("""
                CREATE TABLE articles (
                    id SERIAL PRIMARY KEY,
                    feed_id VARCHAR(255) NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published TIMESTAMP,
                    summary TEXT,
                    content TEXT,
                    author TEXT,
                    source TEXT,
                    entities JSONB,
                    translation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(feed_id, url)
                )
            """)
            
            # 创建索引
            cur.execute("CREATE INDEX idx_articles_feed_id ON articles(feed_id)")
            cur.execute("CREATE INDEX idx_articles_published ON articles(published)")
            cur.execute("CREATE INDEX idx_articles_url ON articles(url)")
            
            logger.info("成功创建 articles 表")
        else:
            # 检查是否需要添加 feed_id 列
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'articles' AND column_name = 'feed_id'
            """)
            
            if not cur.fetchone():
                # 添加 feed_id 列
                cur.execute("ALTER TABLE articles ADD COLUMN feed_id VARCHAR(255)")
                cur.execute("UPDATE articles SET feed_id = 'unknown' WHERE feed_id IS NULL")
                cur.execute("ALTER TABLE articles ALTER COLUMN feed_id SET NOT NULL")
                
                # 删除旧的唯一约束
                cur.execute("ALTER TABLE articles DROP CONSTRAINT IF EXISTS articles_url_key")
                
                # 添加新的复合唯一约束
                cur.execute("ALTER TABLE articles ADD CONSTRAINT articles_feed_id_url_key UNIQUE(feed_id, url)")
                
                # 添加索引
                cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published)")
                
                logger.info("成功添加 feed_id 列和相关约束")
            else:
                logger.info("feed_id 列已存在，跳过表结构修改")
            
            # 检查是否需要添加 updated_at 列
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'articles' AND column_name = 'updated_at'
            """)
            
            if not cur.fetchone():
                cur.execute("ALTER TABLE articles ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                logger.info("成功添加 updated_at 列")
        
        # 检查 user_feeds 表是否存在
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'user_feeds'
            );
        """)
        user_feeds_exists = cur.fetchone()[0]
        if not user_feeds_exists:
            cur.execute("""
                CREATE TABLE user_feeds (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    feed_name VARCHAR(255) NOT NULL,
                    feed_url VARCHAR(1024) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX idx_user_feeds_user_id ON user_feeds(user_id)")
            cur.execute("CREATE INDEX idx_user_feeds_feed_url ON user_feeds(feed_url)")
            logger.info("成功创建 user_feeds 表")
        else:
            logger.info("user_feeds 表已存在，跳过创建")
        
        cur.close()
        conn.close()
        logger.info("PostgreSQL数据库初始化完成")
        
    except Exception as e:
        logger.error(f"PostgreSQL数据库初始化失败: {str(e)}")
        raise

def init_all():
    """初始化数据库"""
    init_postgres()

if __name__ == "__main__":
    init_all() 