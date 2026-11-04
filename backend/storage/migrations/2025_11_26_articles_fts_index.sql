-- Week 6: 添加 articles 全文搜索 GIN 索引（Phase 1，无 ES 场景）
-- 说明：
-- - 使用 PostgreSQL 内置全文搜索（tsvector + GIN）
-- - 基于 title / summary / content 三个字段构造组合向量
-- - 在字段不存在或索引已存在时安全跳过

DO $$
BEGIN
  -- 仅在 articles 表存在 content 字段时创建索引（兼容旧结构）
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'articles' AND column_name = 'content'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_indexes
      WHERE schemaname = 'public' AND indexname = 'idx_articles_fts_combined'
    ) THEN
      CREATE INDEX idx_articles_fts_combined
      ON articles
      USING GIN (
        to_tsvector(
          'simple',
          COALESCE(title, '') || ' ' ||
          COALESCE(summary, '') || ' ' ||
          COALESCE(content, '')
        )
      );
    END IF;
  END IF;
END $$;

