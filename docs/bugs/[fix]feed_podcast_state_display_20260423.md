# Feed 与 Listen 播客状态展示不闭环

## 问题描述

- Feed 首页在当日没有新的可听文章时显示类似 "0 new articles ready to listen"，文案不自然。
- Feed 已按订阅源或快捷条件筛选时，仍展示首页 overview 入口和 featured article，容易打断筛选上下文。
- Listen 页点击 Generate 后，按钮只在请求期间显示生成中；后端后台任务完成后，前端不会自动切到 "Listen to today's podcast"，可能回到 "Generate Daily Podcast" 造成误解。

## 原因定位

### 根本原因ni

前端缺少统一的“今日播客状态”状态机。后端已有 `pending` / `generating` / `completed` / `failed` 状态，但 Feed、Listen、Podcasts 三处 UI 主要只判断 `completed` 与否，并且没有在 `pending` / `generating` 期间持续刷新状态。

### 具体流程问题

- `podcastStore.generatePodcast()` 原来只在新任务创建后刷新一次播客列表；当后端后台任务后续完成时，前端状态不会自动更新。
- 后端 `already_generated: true` 同时覆盖“已完成”和“正在生成中”，前端原来遇到该返回会直接返回，不刷新列表。
- Feed 首页 overview 与 featured 没有区分默认首页态和筛选态。
- 0 篇可听文章没有单独文案分支。

### 相关代码位置

- `frontend/src/stores/podcastStore.js`
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/ListenView.vue`
- `frontend/src/views/PodcastsView.vue`
- `frontend/src/i18n/en.json`
- `frontend/src/i18n/zh.json`

## 修复方案

- 在 `podcastStore` 中新增共享的今日播客状态：`todayPodcast`、`todayPodcastStatus`、`isTodayPodcastCompleted`、`isTodayPodcastInProgress`。
- 在 `pending` / `generating` 时启动 store 级轮询，定期 `fetchPodcasts()`，直到状态变为非进行中。
- `generatePodcast()` 对 `already_generated` 响应也刷新列表，并返回后端状态。
- Feed 首页只在默认态（All sources + All quick filter）展示 overview 和 featured；筛选态隐藏这两个模块。
- Feed 0 可听文章显示专门文案，不再显示 0 new articles ready to listen。
- Listen 和 Podcasts 页按钮接入统一今日播客状态，pending/generating 时显示生成中，completed 后自动变成收听入口。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:

- `frontend/src/stores/podcastStore.js`
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/ListenView.vue`
- `frontend/src/views/PodcastsView.vue`
- `frontend/src/i18n/en.json`
- `frontend/src/i18n/zh.json`

**修复时间**: 2026-04-23

**修改内容**:

- 新增播客状态轮询与今日播客状态计算。
- 修正 Feed 0 更新文案与筛选态展示逻辑。
- 修正 Listen / Podcasts 生成按钮在 pending、generating、completed 状态下的展示与行为。

**测试验证**:

- `node -e "JSON.parse(...en.json); JSON.parse(...zh.json)"` 通过。
- `make test-quick` 通过（35 passed, 85 deselected）。
- `cd frontend && npm run build` 通过。

## 相关提交

- `df41aab` fix(frontend): clarify feed podcast states
