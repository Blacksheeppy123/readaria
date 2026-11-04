# MIT Sloan Management Review 重复订阅报错

## 问题描述

在 Discover Feeds 页面点击 "MIT Sloan Management Review" 的 "+ Subscribe" 按钮时，弹出 "Failed to add feed" 错误提示。该 feed 实际上已经成功订阅过，但前端仍显示为未订阅状态，导致用户可以再次点击订阅，最终触发后端数据库唯一约束冲突。

- **实际表现**: 已订阅的 feed 显示 "+ Subscribe"，点击后报错 "Failed to add feed"
- **预期表现**: 已订阅的 feed 应显示 "Subscribed" 且按钮禁用

## 原因定位

### 根本原因

前后端 URL 归一化逻辑不一致：
1. **前端配置** (`frontend/src/config/recommendedFeeds.js`) 中 MIT Sloan 的 URL 为 `https://sloanreview.mit.edu/feed/`（带尾部斜杠）
2. **后端验证器** (`backend/utils/url_validator.py:56`) 在 `normalize_url` 中会移除尾部斜杠，存储到数据库的 URL 为 `https://sloanreview.mit.edu/feed`
3. **前端 `isSubscribed` 判断** (`FeedDiscoverView.vue:18-19`) 使用精确字符串匹配：`existingUrls.value.has(url)`，导致 `https://sloanreview.mit.edu/feed/` !== `https://sloanreview.mit.edu/feed`，前端误判为未订阅

### 具体流程问题

1. 用户首次订阅 MIT Sloan → 后端存储归一化 URL（无尾部斜杠）→ 订阅成功
2. 用户再次进入 Discover Feeds → 前端比较 `https://sloanreview.mit.edu/feed/`（配置）与 `https://sloanreview.mit.edu/feed`（后端返回）→ 不匹配 → 显示 "+ Subscribe"
3. 用户点击订阅 → 后端尝试插入 → `user_feeds` 表的 `UNIQUE(user_id, feed_url)` 约束冲突 → 抛出 500 错误

### 相关代码位置

- `frontend/src/views/FeedDiscoverView.vue:18-19` - `isSubscribed` 精确字符串匹配
- `frontend/src/views/FeedsView.vue:17,24` - 同样的 `isSubscribed` 逻辑
- `frontend/src/config/recommendedFeeds.js:317` - MIT Sloan URL 配置
- `backend/utils/url_validator.py:56` - `normalize_url` 移除尾部斜杠
- `backend/storage/database.py:1282-1354` - `create_user_feed` 未处理重复订阅的 IntegrityError

## 修复方案

### 前端修复
在 `FeedDiscoverView.vue` 和 `FeedsView.vue` 中添加 URL 归一化辅助函数，修改 `isSubscribed` 使用归一化后的 URL 进行比较：

```javascript
const normalizeUrl = (url) => url?.replace(/\/$/, '') || url
const existingUrls = computed(() => new Set(feedStore.feeds.map(f => normalizeUrl(f.feed_url))))
const isSubscribed = (url) => existingUrls.value.has(normalizeUrl(url))
```

### 后端修复
在 `backend/storage/database.py` 的 `create_user_feed` 中捕获 `IntegrityError`，当为唯一约束冲突时返回已存在的 feed_id，而非抛出 500 错误。`backend/api/main.py` 相应调整为返回 200 OK 或更友好的提示。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/views/FeedDiscoverView.vue`
- `frontend/src/views/FeedsView.vue`
- `backend/storage/database.py`
- `backend/api/main.py`
- `tests/backend/storage/test_cross_user_sharing.py`
- `scripts/add_random_feeds_from_opml.py`

**修复时间**: 2025-04-17

**修改内容**:
- 前端 `isSubscribed` 增加 URL 尾部斜杠归一化，确保前后端 URL 一致性
- 后端 `create_user_feed` 捕获重复订阅的 `IntegrityError`，返回 `(feed_id, is_existing)` 元组，避免 500 错误
- 调整所有调用 `create_user_feed` 的代码以兼容新的返回签名
- 单元测试与快速测试全部通过，前端构建成功

## 相关提交

- 待补充
