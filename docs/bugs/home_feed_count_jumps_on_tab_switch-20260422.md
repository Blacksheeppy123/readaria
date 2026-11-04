# 首页 Feed 计数在 Tab 切换时跳动

## 问题描述

首页顶部的 "X new · Y ready to listen" 计数在切换 Tab 后会不一致：
- 打开首页时显示 "40 new · 40 ready to listen"
- 切换到 Listen Tab 再切回 Feed，计数变成 "20 new · 20 ready to listen"
- 再次操作后数字又可能变回 40

预期：计数应该稳定，反映真实状态。

## 原因定位

### 根本原因

1. **首页顶部计数绑定了前端当前已加载数组长度**：`feed.launchOverviewSummary` 使用的是 `articles.length` 和 `playableArticlesCount`。这两个值反映的是“前端此刻列表里有多少条”，不是“当前筛选条件下真实有多少条文章”。

2. **Feed 首屏会自动连续加载多页**：线上 `test-user` 账户进入 Feed 首页后，`van-list` 会为了填满首屏自动请求 `page=1` 和 `page=2`，因此顶部一开始就显示 `40 new · 40 ready to listen`，即使用户没有手动下滑。

3. **Keep-Alive 只解决了“切 Tab 后整页重建”的一种路径，但没有解决计数设计本身不稳定的问题**：即使 Feed/Listen 之间的组件缓存已经生效，只要 `articles` 数组因为任意页内重置、刷新、筛选恢复、首屏重新测量等原因回到第一页，顶部数字仍会从 40 变成 20。

### 具体流程问题

```
用户打开 Feed
  → onMounted 调用 onLoad() 加载第 1 页 (20 篇)
  → 首屏内容高度不足，van-list 自动继续加载第 2 页 (20 篇)
  → articles.length = 40，显示 "40 new · 40 ready to listen"

随后任意导致列表重新回到第一页的路径（例如页内 reset / refresh / 筛选恢复）
  → articles.length = 20
  → 顶部概览也被一起改写成 "20 new · 20 ready to listen"
```

### 相关代码位置

- [frontend/src/views/FeedView.vue:196](frontend/src/views/FeedView.vue#L196) — 文章分页加载逻辑
- [frontend/src/views/FeedView.vue:648](frontend/src/views/FeedView.vue#L648) — 首页概览文案此前使用 `articles.length`
- [frontend/src/api/request.js:37](frontend/src/api/request.js#L37) — 响应拦截器此前会直接解包 `articles`，导致前端拿不到 `pagination.total`
- [backend/api/main.py:1424](backend/api/main.py#L1424) — 文章列表接口此前 `pagination.total` 仅等于当前页返回数量
- [backend/storage/database.py](backend/storage/database.py) — 新增稳定统计查询 `get_user_articles_stats()`

## 修复方案

将首页顶部概览和分页列表彻底解耦，并把产品语义简化成单个数字：

1. 保留现有 keep-alive 修复，继续避免 Feed/Listen Tab 来回切换时整页重建
2. 后端 `/api/user/{user_id}/feeds/articles` 返回真实稳定的 `pagination.total`
3. 同时返回 `overview.today_ready_count`，表示 Asia/Shanghai 当日用户 feed 中新更新的文章数
4. 前端 `FeedView` 顶部概览改为使用 `overview.today_ready_count`，而不是 `articles.length`
5. 首页文案改为 `X new articles ready to listen` / `X 篇新文章可收听`，避免 `new` 和 `ready to listen` 两个数字重复表达

这样顶部数字表达的是“今日新文章”，不再受当前前端已加载页数影响，也不再显示 329 这种历史总量。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复迭代

### 第一次修复（未生效）

**问题**：`<keep-alive include="FeedView,ListenView"><router-view /></keep-alive>` 这种写法在 Vue Router 4 中**不会正确缓存路由组件**。Keep-alive 缓存的是 `<router-view>` 组件本身，而非其渲染的实际路由组件。

**验证方式**：Playwright 在线测试确认，切换 Tab 后仍有 articles API 请求，组件被重新创建。

### 第二次修复（部分生效）

**正确写法**：使用 Vue Router 4 推荐的 `v-slot` 模式：
```vue
<router-view v-slot="{ Component }">
  <keep-alive include="FeedView,ListenView">
    <component :is="Component" />
  </keep-alive>
</router-view>
```

**验证方式**：Playwright 在线测试确认，切换 Tab 后无 articles API 请求，组件实例被正确缓存。

### 第三次修复（本次）

**新增定位证据**：
- Playwright 在线复现 `test-user`，首页初始即触发两个文章请求：
  - `page=1&size=20`
  - `page=2&size=20`
- 回切 Listen → Feed 后没有新的文章请求，说明 keep-alive 已生效，原问题并不只在“切 tab 重建”
- 因此顶部计数的真正不稳定点是“绑定分页数组长度”，而不是 keep-alive 本身

**本次修复内容**：
- 后端新增 `get_user_articles_stats()`，按去重后的全局文章维度返回稳定 `total` / `playable_total`
- `GET /api/user/{user_id}/feeds/articles` 的 `pagination.total` 不再等于当前页返回条数
- 前端 `FeedView` 使用 `pagination.total` / `pagination.playable_total` 渲染顶部概览
- `frontend/src/api/request.js` 支持 `preserveEnvelope`，允许 `FeedView` 获取完整响应元数据

## 修复记录

**修复文件**: 
- [frontend/src/App.vue](frontend/src/App.vue)
- [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue)
- [frontend/src/views/ListenView.vue](frontend/src/views/ListenView.vue)
- [frontend/src/api/request.js](frontend/src/api/request.js)
- [frontend/src/api/feeds.js](frontend/src/api/feeds.js)
- [backend/api/main.py](backend/api/main.py)
- [backend/storage/database.py](backend/storage/database.py)
- [tests/backend/storage/test_cross_user_sharing.py](tests/backend/storage/test_cross_user_sharing.py)
- [tests/api/test_articles.py](tests/api/test_articles.py)

**修复时间**: 2026-04-22

**修改内容**:
- App.vue: `<router-view />` 改为 Vue Router 4 推荐的 `v-slot` 模式：
  ```vue
  <router-view v-slot="{ Component }">
    <keep-alive include="FeedView,ListenView">
      <component :is="Component" />
    </keep-alive>
  </router-view>
  ```
- FeedView.vue: 添加 `defineOptions({ name: 'FeedView' })` 和 `onActivated` 同步已读状态
- ListenView.vue: 添加 `defineOptions({ name: 'ListenView' })`
- FeedView.vue: 首页顶部概览改为使用后端稳定统计值，不再依赖 `articles.length`
- request.js / feeds.js: 允许指定接口保留完整 envelope，读取 `pagination`
- backend/api/main.py / database.py: 文章接口返回真实 `total` 与 `playable_total`
- tests/backend/storage/test_cross_user_sharing.py: 新增统计查询单测
- tests/api/test_articles.py: 断言文章接口返回 `pagination.total` / `playable_total`
- backend/api/main.py / database.py: 文章接口新增 `overview.today_ready_count`
- FeedView.vue / i18n: 首页概览改为单个 `X new articles ready to listen` 数字
- tests/backend/storage/test_cross_user_sharing.py / tests/api/test_articles.py: 覆盖 `overview.today_ready_count`

### 第四次修复（产品语义调整）

**调整原因**：
- 线上修复后 `test-user` 显示 `329 new · 329 ready to listen`，数字稳定但语义过宽，表达的是历史总量
- 两个数字重复，因为当前产品上所有文章都可进入收听流程

**本次调整**：
- 后端 `/api/user/{user_id}/feeds/articles` 新增 `overview.today_ready_count`
- 统计口径改为：Asia/Shanghai 当日、用户订阅范围内新更新的去重文章数
- 前端首页只展示单个数字：`X new articles ready to listen` / `X 篇新文章可收听`
- 修正 `0` 计数不能 fallback 到历史总量的问题

## 相关提交

- `f956b56` fix(frontend): keep-alive FeedView/ListenView + sync read state on re-activate
- `62b5ec7` fix(frontend): use router-view v-slot for keep-alive to properly cache route components

## 验证记录

- [x] Playwright 在线复现 `test-user` 首页初始 `40 new · 40 ready to listen`
- [x] Playwright 在线确认 Feed → Listen → Feed 不会重新请求 articles，说明 keep-alive 已生效
- [x] 本地单测：`tests/backend/storage/test_cross_user_sharing.py -k get_user_articles` 通过
- [ ] 本地 API 集成测试：`tests/api/test_articles.py -k articles_list_and_detail`
  - 阻塞原因：本地测试服务器未启动，`wait_for_server` 在 60 秒后超时
- [x] 线上 API 验证：`test-user` 文章接口返回 `pagination.total=329`、`pagination.playable_total=329`、第一页 `articles=20`
- [x] 线上 Playwright 验证：`test-user` 首页显示 `329 new · 329 ready to listen`
- [x] 线上 Playwright 验证：Feed → Listen → Feed 后仍显示 `329 new · 329 ready to listen`，未再出现 40 → 20 跳动
