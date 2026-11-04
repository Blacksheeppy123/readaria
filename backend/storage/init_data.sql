-- ================================
-- Jasmine 知识管理系统初始数据
-- ================================

-- 插入默认的内容源类型
INSERT INTO source_types (id, name, display_name, description) VALUES
('rss', 'rss', 'RSS 订阅', '传统的 RSS/Atom 订阅源'),
('wechat', 'wechat', '微信公众号', '微信公众号文章抓取'),
('xiaohongshu', 'xiaohongshu', '小红书', '小红书内容抓取'),
('bilibili', 'bilibili', '哔哩哔哩', 'B站视频和动态抓取'),
('twitter', 'twitter', 'X (Twitter)', 'X平台推文抓取'),
('podcast', 'podcast', '播客', '音频播客内容抓取'),
('weibo', 'weibo', '微博', '微博内容抓取'),
('zhihu', 'zhihu', '知乎', '知乎问答和文章抓取')
ON CONFLICT (name) DO UPDATE SET
display_name = EXCLUDED.display_name,
description = EXCLUDED.description;

/*
-- Note: The following tables (categories, tags, system_settings, user_bookmarks)
-- are not in the production schema and have been commented out.
-- They may be added in future schema versions.

-- 插入默认分类
INSERT INTO categories (name, description, parent_id) VALUES
('科技', '科技相关文章', NULL),
('财经', '财经和商业文章', NULL),
('生活', '生活方式相关内容', NULL),
('娱乐', '娱乐和休闲内容', NULL),
('教育', '教育和学习相关', NULL),
('健康', '健康和医疗相关', NULL),
('旅行', '旅行和地理相关', NULL),
('美食', '美食和烹饪相关', NULL),
('时尚', '时尚和美容相关', NULL),
('体育', '体育和运动相关', NULL)
ON CONFLICT (name) DO NOTHING;

-- 为科技分类添加子分类
WITH tech_category AS (
    SELECT id FROM categories WHERE name = '科技' LIMIT 1
)
INSERT INTO categories (name, description, parent_id)
SELECT name, description, tech_category.id FROM tech_category, (VALUES
    ('人工智能', 'AI和机器学习相关'),
    ('编程开发', '编程语言和开发技术'),
    ('硬件设备', '电子设备和硬件'),
    ('互联网', '网络技术和互联网服务'),
    ('移动应用', '手机应用和移动技术'),
    ('区块链', '区块链和加密货币'),
    ('数据科学', '数据分析和大数据')
) AS subcats(name, description)
ON CONFLICT (name) DO NOTHING;

-- 插入默认标签
INSERT INTO tags (name, color) VALUES
('重要', '#EF4444'),
('技术', '#3B82F6'),
('新闻', '#10B981'),
('深度', '#8B5CF6'),
('热点', '#F59E0B'),
('原创', '#06B6D4'),
('转载', '#6B7280'),
('视频', '#EC4899'),
('音频', '#84CC16'),
('图片', '#F97316')
ON CONFLICT (name) DO NOTHING;

-- 插入系统默认配置
INSERT INTO system_settings (key, value, description) VALUES
('system.version', '"1.0.0"', '系统版本号'),
('nlp.enabled', 'true', '是否启用NLP处理'),
('nlp.auto_translate', 'true', '是否自动翻译'),
('nlp.extract_entities', 'true', '是否提取实体'),
('fetch.default_interval', '60', '默认抓取间隔（分钟）'),
('fetch.max_articles_per_source', '50', '每个源最大文章数'),
('search.results_per_page', '20', '搜索结果每页数量'),
('system.maintenance_mode', 'false', '维护模式开关')
ON CONFLICT (key) DO UPDATE SET
value = EXCLUDED.value,
updated_at = CURRENT_TIMESTAMP;

-- 创建默认管理员用户（需要在应用启动时设置密码）
INSERT INTO users (id, username, email, full_name, is_superuser, password_hash) VALUES
('00000000-0000-0000-0000-000000000001', 'admin', 'admin@jasmine.local', '系统管理员', true, '$2b$12$placeholder.hash.will.be.replaced')
ON CONFLICT (username) DO NOTHING;

-- 为管理员创建示例收藏夹
WITH admin_user AS (
    SELECT id FROM users WHERE username = 'admin' LIMIT 1
)
INSERT INTO user_bookmarks (id, user_id, name, description, is_public)
SELECT '00000000-0000-0000-0000-000000000001', admin_user.id, '重要文章', '标记为重要的文章收藏', false
FROM admin_user
ON CONFLICT (id) DO NOTHING;
*/