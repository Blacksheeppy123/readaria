# TIME 源文章作者显示错误

## 问题描述

- 使用 `mytest1` 账户登录后，在 Feed 页面筛选 **TIME** 源
- 文章列表中每篇文章的**来源**字段都显示成了 `DIYgod`
- 预期显示：文章的真正来源应该是 "TIME"
- 实际显示：所有 TIME 文章的来源均显示为 "DIYgod"

## 原因定位

### 根本原因

后端 `_map_article_sources_to_feed_urls` 函数（`backend/api/main.py:321`）和前端的 `getSourceName` 函数在进行 URL 匹配时，**仅使用 `pathname` 进行映射**，没有考虑 `hostname`。

mytest1 同时订阅了以下两个 feed：
- `TIME` -> `https://time.com/feed` （pathname: `/feed`）
- `DIYgod` -> `https://diygod.cc/feed` （pathname: `/feed`）

由于两者的 pathname 相同（都是 `/feed`），`_map_article_sources_to_feed_urls` 在建立 `path -> feed_url` 字典时，后者覆盖了前者。因此，所有 `source_feed_url` 为 `https://time.com/feed` 的文章，其 `source` 字段被错误映射为 `https://diygod.cc/feed`，前端自然显示 feed 名称为 "DIYgod"。

### 相关代码位置

- 后端映射逻辑：`backend/api/main.py:321-373`（`_map_article_sources_to_feed_urls`）
- 前端来源显示逻辑：
  - `frontend/src/views/FeedView.vue:352-365`（`getSourceName`）
  - `frontend/src/views/ArticlesView.vue:249-278`（`getSourceName`）
  - `frontend/src/views/ListenView.vue:223-235`（`getSourceName`）

## 修复方案

1. **后端修复**：在 `_map_article_sources_to_feed_urls` 中：
   - 如果 `source` 已经直接匹配某个用户订阅的 `feed_url`，直接跳过映射。
   - 只有 `source` 的 hostname 属于内部/Docker 抓取地址（`localhost`、`127.0.0.1`、`rsshub`、`wechat2rss`）时，才进行 pathname 映射。

2. **前端修复**：在所有使用 `getSourceName` 的页面中：
   - 保持精确匹配 `feed_url === sourceUrl` 优先。
   - pathname fallback 仅对内部抓取地址生效，避免不同域名相同 pathname 的 feed 被错误映射。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/api/main.py`
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/ArticlesView.vue`
- `frontend/src/views/ListenView.vue`

**修复时间**: 2025-04-17

**修改内容**:
- `backend/api/main.py`: `_map_article_sources_to_feed_urls` 增加 `feed_url_set` 精确匹配，并限制 pathname 映射仅在内部 host 时生效。
- `frontend/src/views/FeedView.vue`: `getSourceName` 增加内部 host 判断。
- `frontend/src/views/ArticlesView.vue`: `getSourceName` 增加内部 host 判断。
- `frontend/src/views/ListenView.vue`: `getSourceName` 增加内部 host 判断。

## 相关提交

- 待补充
