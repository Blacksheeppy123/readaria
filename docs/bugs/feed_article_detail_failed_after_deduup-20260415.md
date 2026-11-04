# 上线全局文章去重后，文章详情页加载失败

## 问题描述

上线 Cross-User Content Sharing（全局文章去重）Phase 2 后，用户在文章列表页点击任意文章进入详情页时，页面显示 "Failed to load article"，文章无法正常阅读。

- **影响范围**: 所有文章详情页（通过列表页点击进入）
- **触发条件**: 文章 URL 中包含已编码的特殊字符（如 `%20`）
- **表现**: 详情页 fallback 到 API 获取时返回 404，最终显示加载失败

## 原因定位

### 根本原因

`ArticleDetail.vue` 中存在一个 pre-existing 的 URL 解码逻辑 bug。该代码使用 `do...while` 循环对路由参数 `id`（即文章 URL）进行反复 `decodeURIComponent`，直到字符串中不再出现 `%XX` 模式为止。

当全局去重上线后，`global_articles` 表直接存储了 RSS 源返回的原始 URL（可能包含 `%20` 等编码字符）。而旧版 `articles` 表中的 URL 经过了一些清洗或存储时恰好没有这类编码。因此该 bug 在旧数据下未暴露，全局去重后大量原始 URL 触发了问题。

### 具体流程问题

1. 列表页通过 `router.push` 将文章 URL 作为 `params.id` 传入，并 `encodeURIComponent` 一次
2. `beforeRouteEnter` 和 `loadArticle` 中对该参数进行循环解码
3. 若 URL 内部本身包含 `%20`（如 `https://example.com/path%20with%20spaces`），循环解码会将 `%20` 变成空格
4. 解码后的 URL 与数据库中的原始 URL 不匹配，`getArticleByUrl` 返回 404
5. 搜索兜底也因 URL 不匹配而失败，最终显示 "Failed to load article"

### 相关代码位置

- `frontend/src/views/ArticleDetail.vue:143-144` — `beforeRouteEnter` 中的循环解码
- `frontend/src/views/ArticleDetail.vue:263-266` — `loadArticle` 中的循环解码

## 修复方案

将两处循环解码替换为单次 `decodeURIComponent`。

理由：
- Vue Router 在解析 `params.id` 时已经自动对 URL 进行了一次 decode
- 列表页传入时只做了一次 `encodeURIComponent`
- 因此只需要单次 `decodeURIComponent` 即可还原原始 URL
- 循环解码是过度操作，会破坏本身就包含 `%XX` 的合法 URL

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/views/ArticleDetail.vue`

**修复时间**: 2026-04-15

**修改内容**:
- 将 `beforeRouteEnter` 中的 `do...while` 循环解码改为单次 `decodeURIComponent`
- 将 `loadArticle` 中的 `do...while` 循环解码改为单次 `decodeURIComponent`

## 相关提交

- `0b2a784` fix(article): replace loop URL decode with single decodeURIComponent
