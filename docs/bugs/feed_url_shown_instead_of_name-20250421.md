# 文章详情和筛选弹窗显示原始 feed URL 而非订阅源名称

## 问题描述

在以下页面/组件中，文章来源显示的是原始的 feed URL（如 `https://wechat2rss.marlinworks.xyz/feed/2392306830.xml`），而非人类可读的订阅源名称：

1. **文章详情页** (`ArticleDetail.vue`)：文章元信息中的来源字段直接显示原始 URL
2. **文章列表筛选弹窗** (`ArticlesView.vue`)：筛选来源时，每个 `van-cell` 的 `label` 显示的是 `feed.feed_url`
3. **TTS Player 页面** (`TtsPlayerView.vue`)：播放器中文章信息和播放列表显示原始 feed URL
4. **文章详情页作者** (`ArticleDetail.vue`)：当 RSS 源未提供 author 字段时，显示 "Unknown"

**预期表现**：显示用户设置的订阅源名称（`feed_name`）
**实际表现**：显示原始 RSS 地址或 Unknown，阅读体验差

## 原因定位

### 根本原因
`ArticleDetail.vue` 中没有使用 `feedStore` 进行 URL 到名称的映射，直接渲染了 `article.source` 字段。

`ArticlesView.vue` 的筛选弹窗虽然标题已显示 `feed_name`，但额外添加了 `:label="feed.feed_url"`，导致每个选项下方都显示冗长的 URL。

`TtsPlayerView.vue` 同样没有引入 `feedStore`，直接显示 `currentArticle.source` 和 `item.source`。

对于作者显示 "Unknown"，是因为部分 RSS 源（如路透财经早报）本身不提供 `author` 字段，数据库中该字段为空。

### 相关代码位置
- `frontend/src/views/ArticleDetail.vue` 第 62-65 行：直接显示 `display.source || article?.source`
- `frontend/src/views/ArticleDetail.vue` 第 56 行：作者显示 `display.author || article?.author || $t('common.unknown')`
- `frontend/src/views/ArticlesView.vue` 第 523 行：`:label="feed.feed_url"`
- `frontend/src/views/TtsPlayerView.vue` 第 34 行：`currentArticle?.source`
- `frontend/src/views/TtsPlayerView.vue` 第 170 行：`item.source`

## 修复方案

1. **ArticleDetail.vue（来源）**：
   - 引入 `useFeedStore`
   - 添加 `getSourceName()` 辅助函数（与 `FeedView.vue` / `ArticlesView.vue` 相同的实现）
   - 模板中使用 `getSourceName(display.source || article?.source)` 替代直接显示

2. **ArticleDetail.vue（作者）**：
   - 当 author 为空时，fallback 到 `getSourceName(source)`，用订阅源名称替代 "Unknown"

3. **ArticlesView.vue**：
   - 移除 `van-cell` 的 `:label="feed.feed_url"`，标题已足够标识订阅源

4. **TtsPlayerView.vue**：
   - 引入 `useFeedStore`
   - 添加 `getSourceName()` 辅助函数
   - 模板中主信息区和播放列表都使用 `getSourceName()` 映射

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/views/ArticleDetail.vue`
- `frontend/src/views/ArticlesView.vue`
- `frontend/src/views/TtsPlayerView.vue`

**修复时间**: 2025-04-21 / 2025-04-22

**修改内容**:
- `ArticleDetail.vue`: 引入 `useFeedStore`，添加 `getSourceName()` 函数，来源元信息使用映射后的名称；作者为空时 fallback 显示订阅源名称
- `ArticlesView.vue`: 移除筛选弹窗中 `van-cell` 的 `label` 属性（原显示 feed_url）
- `TtsPlayerView.vue`: 引入 `useFeedStore`，添加 `getSourceName()` 函数，主信息区和播放列表中的 source 均使用映射后的名称

## 相关提交

