# Podcast Generation UI and Status Issues

## 问题描述

三个相关问题：

1. **Feed 页跳转未定位**：Feed 页提示 "generate today's podcast"，点击后跳转到 Listen 页，但没有定位到播客生成卡片位置。

2. **生成按钮状态异常**：使用 test-user 账户点击生成播客后，按钮进入旋转状态（图二），一会又恢复成初始状态（图一），需要再次点击才进入真正的生成中状态。

3. **自动生成未生效**：test-user 账户设置了自动生成播客，但今天的播客（April 24）没有自动生成，仍为 "Generate Daily Podcast" 状态。

## 原因定位

### 根本原因

#### 问题 1：Feed → Listen 跳转未定位
Feed 页的跳转按钮使用 `router.push({ name: 'listen' })`，未传递任何锚点或查询参数。Listen 页没有接收和处理定位逻辑，因此跳转到页面顶部而非播客卡片位置。

#### 问题 2：按钮状态异常（HTTP 超时导致）
播客生成是同步长任务（约 3 分 49 秒），但前端 Axios 超时 180 秒，Cloudflare/Nginx 超时约 60-100 秒。当请求超时：
1. 前端 `generatePodcast()` 抛出超时错误
2. `onGenerate()` 捕获错误，`generating.value = false`
3. 但 `fetchPodcasts()` 未被调用（它在 `generatePodcast()` 中位于 API 调用之后）
4. `podcastStore` 不知道有 pending 的播客，`isTodayPodcastInProgress` 仍为 false
5. 按钮恢复初始状态

用户第二次点击时，后端检测到已有生成中的记录，返回 `already_generated: true` 和 `status: 'generating'`，此时 `fetchPodcasts()` 成功执行，`isTodayPodcastInProgress` 变为 true，按钮才显示正确的生成中状态。

**相关代码**：
- `frontend/src/api/request.js`: Axios timeout 180000ms
- `frontend/src/views/ListenView.vue:103-119`: `onGenerate()` 同步调用 API
- `backend/services/podcast_generator.py`: `generate_daily_podcast()` 同步阻塞执行约 3m49s
- `backend/api/main.py`: `generate_podcast` endpoint 同步调用 `await generator.generate_daily_podcast()`

#### 问题 3：自动生成未生效（白名单过滤）
调度器 `generate_daily_podcasts()` 获取 `auto_podcast_enabled = true` 的用户后，通过 `filter_feature_whitelist_users()` 过滤。`feature_whitelist` 默认值为空列表 `[]`，test-user 不在其中，因此被过滤掉。日志显示 "没有白名单用户需要生成播客，跳过"。

手动生成 API (`POST /api/v1/podcasts/generate`) 并未检查白名单，因此 test-user 可以手动生成，但不能自动生成，行为不一致。

**相关代码**：
- `backend/scheduler/feed_scheduler.py:184-189`: 白名单过滤逻辑
- `backend/utils/whitelist.py:50-52`: `filter_feature_whitelist_users()` 实现
- `core/config/settings.py:231`: `feature_whitelist: List[str] = []`

## 修复方案

### 问题 1：添加跳转定位
- Feed 页跳转时传递 `query: { scrollTo: 'podcast' }`
- Listen 页 `onMounted` 中检测该参数，使用 `scrollIntoView` 滚动到播客卡片位置

### 问题 2：改为异步后台生成
- 后端 API 使用 FastAPI `BackgroundTasks`，创建播客记录后立即返回 `pending` 状态
- 后台任务调用新的 `generate_podcast_content()` 方法执行实际的生成工作
- 前端无需改动，已有的轮询机制 (`fetchPodcasts` + `startPodcastStatusPolling`) 会自动更新状态

### 问题 3：移除自动生成的白名单限制
- 删除调度器中的 `filter_feature_whitelist_users()` 过滤逻辑
- 所有启用 `auto_podcast_enabled` 的用户均可自动获得播客生成

## 修复状态

- [x] 文档记录
- [x] 问题定位
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/ListenView.vue`
- `backend/api/main.py`
- `backend/services/podcast_generator.py`
- `backend/scheduler/feed_scheduler.py`

**修复时间**: 2026-04-24

**修改内容**:
- FeedView.vue: 跳转按钮添加 `query: { scrollTo: 'podcast' }`
- ListenView.vue: 添加 `useRoute` + `podcastSectionRef`，`onMounted` 中检测 `scrollTo` 参数并平滑滚动到播客卡片
- main.py: 引入 `BackgroundTasks`；`generate_podcast` endpoint 改为创建记录 + 后台任务执行；添加 `_run_podcast_generation_background` helper
- podcast_generator.py: 新增 `generate_podcast_content()` 方法，复用原 `generate_daily_podcast` 中的生成逻辑
- feed_scheduler.py: 移除 `filter_feature_whitelist_users` 过滤

## 相关提交

- [待补充]
