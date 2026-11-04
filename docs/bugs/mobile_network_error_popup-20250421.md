# Android 上频繁弹出网络错误提示

## 问题描述

在新版 Android 上使用 test-user 账号时，Feed 页面经常弹出 "Network error, please check your connection" 报错弹窗。

- **出现场景**: Feed 页面浏览文章列表时
- **触发频率**: 经常性出现，非偶发
- **网络环境**: 5G 信号满格（见截图）
- **账号**: test-user
- **实际表现**: 页面能正常显示内容，但频繁弹出网络错误 Toast
- **预期表现**: 网络正常时不应弹出错误提示

## 原因定位

### 根本原因

错误提示来自 `frontend/src/api/request.js` 响应拦截器第 82 行：

```javascript
} else if (error.request) {
  message = i18n.global.t('common.networkError')
}
```

当请求发出但未收到响应（`error.request` 存在但 `error.response` 不存在）时触发，对应 i18n key `common.networkError`，英文文案为 "Network error, please check your connection"。

### 日志分析发现

通过检查生产环境 Nginx 访问日志和前端日志，发现以下关键问题：

1. **真正持续触发 Toast 的不是文章列表，而是白名单前端日志上传接口**：`test-user` 登录后会自动启动 `frontendLogCollector`，每 15 秒向 `/api/v1/frontend-logs` 上传诊断日志。Android 线上 Nginx 访问日志显示该接口在 `2026-04-22` 持续出现 `OPTIONS /api/v1/frontend-logs`，但没有后续 `POST`；同时前端日志持续记录 `AxiosError: Network Error`。进一步对生产接口执行预检请求发现，`/api/v1/frontend-logs` 的预检响应头仍写死为 `Access-Control-Allow-Origin: https://app.marlinworks.xyz`，并未更新到 `https://readaria.com`。品牌/主域名迁移后，这个接口在 `readaria.com` 下会被浏览器直接拦截，于是跨页面、周期性地产生全局 `network error` Toast。

2. **之前关于大响应体的判断只解释了部分风险，不是本次主根因**：文章列表接口此前确实较大，压缩和摘要化方向本身是合理的，但并不能解释“跨多个页面都出现”以及“只在白名单用户更明显”这两个现象。真正符合现象的链路是白名单专属的前端日志上传。

3. **文章详情变慢来自“列表瘦身后仍保留旧的预取链路”**：`FeedView.vue` 点击文章时先异步预取一次 `/api/articles/by-url`，随后立即把 summary-only 的文章对象塞进 router state；`ArticleDetail.vue` 进入后又因缺少 `content` 再发一次 `/api/articles/by-url` 获取正文。生产访问日志已观察到同一篇文章连续两次 `OPTIONS + GET /api/articles/by-url`。因此之前将列表切为 `only_summary=True` 后，正文加载路径从“列表已带正文”退化成“至少一跳详情请求”，并且在 Feed → Detail 路径上还出现了重复请求。

4. **双重 Toast 问题曾经存在，但不是当前剩余主因**：Feed 页面同时存在两处错误提示：
   - `request.js` 拦截器弹出 "Network error, please check your connection"
   - `FeedView.vue` 的 `onLoad()` catch 块弹出 "Failed to load articles"
   单次网络错误会导致连续两个 Toast 弹窗。

### 相关代码位置

- **错误提示源**: `frontend/src/api/request.js:44-87`（响应拦截器）
- **Feed 页面 API 调用**: `frontend/src/views/FeedView.vue`
- **Feed 相关 API**: `frontend/src/api/feeds.js`
  - `getUserFeeds()` - 无 silent 标志
  - `getArticles()` - 无 silent 标志
  - `refreshFeed()` / `refreshAllFeeds()` - 无 silent 标志
  - `getRefreshStatus()` - 有 silent 标志
- **前端日志上传**: `frontend/src/utils/frontendLogCollector.js`
- **白名单启动入口**: `frontend/src/stores/userStore.js`
- **文章详情预取/补全**: `frontend/src/views/FeedView.vue`, `frontend/src/views/ArticleDetail.vue`
- **生产 Nginx 特殊配置漂移**: 线上 `/api/v1/frontend-logs` location 中写死 `https://app.marlinworks.xyz`

## 修复方案

### 方案 1：为 Feed 页面非关键请求添加 silent 模式（已实施）

Feed 页面的列表加载请求在网络错误时不应打断用户体验，可设置 `silent: true`。

### 方案 2：增加错误重试机制

对网络错误进行 1-2 次自动重试，避免瞬时网络波动导致误报。

### 方案 3：查看生产环境日志定位具体失败请求

检查线上 API 日志，确认哪些端点返回异常，针对性修复后端问题。

### 方案 4：启用 Nginx gzip 压缩 JSON 响应

在 Nginx 配置中添加 `gzip_types application/json`，减少 API 响应体积，降低移动网络传输失败概率。

### 方案 5：列表 API 不返回完整 content（已实施）

Feed 列表视图仅需标题、摘要、作者等元数据，不需要完整 HTML content。将 `only_summary=False` 改为 `only_summary=True`，可大幅缩小响应体积（从 500KB-1.6MB 降至约 50KB）。文章详情页通过独立接口 `/api/articles/by-url` 获取完整内容。

### 方案 6：将前端日志上传改为真正静默的后台诊断流（本次新增）

给 `frontendLogCollector` 的上传请求显式加上 `silent: true` 和 `X-Silent`，避免日志上传失败时进入全局 axios 错误 Toast，也避免拦截器 `console.error('Response error')` 被收集器再次捕获，形成噪音放大。

### 方案 7：修复生产 Nginx 对 `/api/v1/frontend-logs` 的旧域名 CORS 写死（本次新增）

生产机当前存在未入库的特殊 location，硬编码 `Access-Control-Allow-Origin: https://app.marlinworks.xyz`。需要把仓库中的 Nginx 配置补齐为“不自管 CORS，只保留 body size / timeout，交给 FastAPI CORSMiddleware 统一处理”，并同步部署到 VPS。

### 方案 8：先移除 Feed → Detail 的重复正文预取（本次新增）

先移除 `FeedView` 中多余的后台 `/api/articles/by-url` 预取，避免点击文章时立刻产生一轮额外详情请求；详情页保留现有的正文补全链路。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证
- [x] Nginx gzip 配置

## 修复记录

**修复文件**:
- `frontend/src/api/feeds.js`
- `frontend/src/views/FeedView.vue`
- `frontend/src/utils/frontendLogCollector.js`
- `deploy/nginx/jasmine_fixed.conf`

**修复时间**: 2026-04-22

**修改内容**:
1. `frontend/src/api/feeds.js`: 为 `getUserFeeds()` 和 `getArticles()` 添加 `silent: true` 和 `headers: { 'X-Silent': '1' }`，避免网络错误时触发 request.js 拦截器的 Toast
2. `frontend/src/views/FeedView.vue`: 移除 `onLoad()` catch 块中在线状态下的 `showToast(t('articles.loadFailed'))`，仅保留离线状态下的缓存提示 Toast。在线状态下的请求失败不再弹出干扰性提示
3. `frontend/src/views/ArticleDetail.vue` (Review Problem 1): 新增 `hasFullContent()` 和 `fetchFullContent()`，仅在数据包含完整 `content` 时才设置 `hasLoaded = true`。来自 state/sessionStorage/store 的预取数据若缺少正文，自动触发 API 补全
4. `frontend/src/api/feeds.js` (Review Problem 2): `getArticles()` 支持可选 `options` 参数覆盖 `silent` 行为
5. `frontend/src/views/FeedView.vue` (Review Problem 2): `onRefresh()` 传入 `{ silent: false }`，失败时显示 `articles.loadFailed` Toast，保留用户主动操作的错误反馈
6. `frontend/src/stores/podcastStore.js` (追加修复): `fetchPodcasts()` 添加 `silent: true`，Feed 页面 `onMounted` 中并行调用 `podcastStore.fetchPodcasts()` 时网络错误不再弹出 Toast
7. `frontend/src/utils/frontendLogCollector.js`: 日志上传请求改为 `silent: true`，避免 `/api/v1/frontend-logs` 的网络失败触发全局 `network error` Toast
8. `frontend/src/views/FeedView.vue`: 移除点击文章时额外的 `/api/articles/by-url` 后台预取，避免详情页重复请求正文
9. `deploy/nginx/jasmine_fixed.conf`: 新增 `/api/v1/frontend-logs` location，但不再在 Nginx 中写死 `Access-Control-Allow-Origin`，改由 FastAPI CORSMiddleware 统一处理，规避品牌迁移后旧域名 CORS 漂移

## 待办

- [x] 服务器配置：在 Nginx 中启用 JSON gzip 压缩 (`gzip_types application/json;`)
- [x] 测试验证：curl 验证 `/api/v1/frontend-logs` 预检响应当前仍返回旧域名 `https://app.marlinworks.xyz`
- [ ] 部署更新后的 Nginx 配置到 VPS 并 reload
- [ ] 部署更新后的前端到 Cloudflare Workers
- [ ] 线上验证：在 Android 设备上验证网络错误 Toast 不再频繁弹出
- [ ] 线上验证：确认文章详情正文不再出现重复 `OPTIONS + GET /api/articles/by-url`

## 相关提交

- 待补充

## Review意见

## Feature: mobile-network-error-popup-fix
- problem 1：
  - level: p0
  - decription:
    `[backend/api/main.py:1502-1513]` changes the feed list endpoint to `only_summary=True`, but the current article-detail flow still treats the list item as if it may already contain full content. From Feed page navigation, `[frontend/src/views/FeedView.vue:402-418]` pushes the list item into router state, then `beforeRouteEnter` passes that object into `[frontend/src/views/ArticleDetail.vue:191-195]`, and `[frontend/src/views/ArticleDetail.vue:438-453]` marks the page as loaded immediately. Because `onMounted` later calls `loadArticle()` and it exits early when `hasLoaded` is already true (`[frontend/src/views/ArticleDetail.vue:240-241,685-686]`), the detail page no longer guarantees a follow-up fetch for full HTML content. With this patch, opening an article from Feed can regress into a summary-only detail page showing the skeleton/no-content fallback forever.
  - fix suggestion:
    Keep the payload reduction, but make ArticleDetail distinguish between "header/summary-prefetched" and "full article loaded". For example, only set `hasLoaded = true` when `content` is present, or always trigger a background `getArticleByUrl()` hydration when the incoming article has empty content.
  - decision and reason(by claude):
    Fixed. Added `hasFullContent()` helper and `fetchFullContent()` in `ArticleDetail.vue`. `hasLoaded = true` is now only set when `content` is present. For `setArticleData` (beforeRouteEnter), store prefetch, and sessionStorage branches, if content is missing, `fetchFullContent()` is triggered to hydrate the full article. This ensures the detail page never gets stuck showing only a summary.

- problem 2：
  - level: p1
  - decription:
    `[frontend/src/api/feeds.js:125-131]` makes `getArticles()` fully silent, while `[frontend/src/views/FeedView.vue:248-261]` now shows a toast only for the offline branch. As a result, an online timeout / 5xx / proxy failure during user-initiated pull-to-refresh no longer produces any visible feedback, and `[frontend/src/views/FeedView.vue:267-275]` simply ends refresh with no success or failure signal. This fixes the noisy passive toast, but it also removes necessary feedback for an explicit user action.
  - fix suggestion:
    Scope `silent: true` to passive/background loads only, or add a local non-duplicated error surface for manual refresh / explicit retry paths. A common pattern here is `getArticles(params, { silent: isBackgroundLoad })` plus a single contextual toast in `onRefresh()` when the request fails.
  - decision and reason(by claude):
    Fixed. `getArticles()` now accepts an `options` parameter (`getArticles(params, { silent: false })`). `FeedView.vue` `onRefresh()` calls `onLoad({ silent: false })` so user-initiated pull-to-refresh shows network errors. Passive loads (initial mount, infinite scroll) remain silent. `onRefresh()` catch block now shows a single `articles.loadFailed` toast with `icon: 'fail'` on failure.


## Comments and Future suggestion

- The direction of shrinking feed-list payloads is good, but this patch mixes two concerns: transport-size reduction and UI error-policy changes. They should ideally be validated separately because each one changes different user-facing behavior.
- `getUserFeeds()` was also changed to silent globally (`[frontend/src/api/feeds.js:50-56]`), so pages that previously relied on interceptor toasts now fail quietly unless they add their own UI handling. That broader UX impact is not covered in the bug note yet.
- 这次复盘确认：品牌/域名迁移确实影响到了线上问题，因为生产 Nginx 针对 `/api/v1/frontend-logs` 的特殊 CORS 逻辑仍停留在旧域名 `app.marlinworks.xyz`，而仓库代码中的 FastAPI CORS 已经包含 `https://readaria.com`。这是一次“线上配置漂移”，不是前端业务代码本身能完全解释的问题。
