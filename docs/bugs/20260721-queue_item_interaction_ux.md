# 播放列表条目交互问题：删除按钮易误触、无法进入文章详情

## 问题描述

Listen 页听读队列的条目交互有两个问题：

1. **删除按钮易误触**：删除某个内容需要点击条目右侧的 `x` 图标（16px），触控热区太小，且紧邻条目本体，容易点错（误删或误触播放）
2. **无法进入文章内容页**：点击队列条目只有"播放"一个行为，没有办法从播放列表跳转到文章内容页面（阅读原文）

- 功能：Listen 页听读队列（`ListenView.vue`）
- 实际表现：删除靠 16px 小图标；条目点击 = 播放，无详情入口
- 预期表现：删除操作不易误触；可以方便地从队列进入文章详情页

## 原因定位

### 具体原因

1. **删除按钮**：`van-icon name="cross" size="16"`，图标本身 16px，没有额外 padding 扩大热区（移动端推荐最小触控目标 44×44px），且 `@click.stop` 直接调 `removeQueueItem`，无任何确认或容错
2. **无详情入口**：`.queue-item` 整行 `@click="playQueueItem(article, index)"` 只有播放行为，模板中没有跳转到 `article-detail` 路由（`/article/:id`）的任何入口。队列项数据里有 `id` 字段，具备跳转条件，只是 UI 未提供

### 相关代码位置

- `frontend/src/views/ListenView.vue:246-265` — 队列列表模板（整行点击播放 + 16px cross 删除）
- `frontend/src/views/ListenView.vue:66-72` — `playQueueItem` / `removeQueueItem`
- `frontend/src/router/index.js:120-123` — 文章详情路由 `article-detail`（`/article/:id`）
- `frontend/src/main.js:48,136` — `SwipeCell` 已全局注册，滑动操作可直接使用

## 修复方案

已与用户确认采用「点击进详情 + 独立播放按钮 + 左滑删除」方案：

1. **点击条目 = 进入文章详情页**：跳转 `article-detail` 路由，数据传递方式与 FeedView 一致（`sessionStorage` 备份 + `state` 传递，路由参数为 URL 编码后的文章地址）；队列项无 `content` 时由 ArticleDetail 自动拉取全文
2. **独立播放按钮**：条目右侧 40px 圆形播放按钮（`@click.stop`），点击从该条开始播放整个队列；若为当前播放条目则切换播放/暂停（图标随之切换 play/pause）
3. **左滑删除**：`van-swipe-cell` 包裹条目（组件已全局注册），滑出红色删除按钮（大热区、有意识手势，不误触）；移除原 16px `x` 图标
4. 新增 i18n 文案 `listen.playFromHere`（播放按钮 aria-label）；删除按钮复用 `common.delete`

### 注意事项

- 滑动删除与条目点击共存：SwipeCell 内部处理手势与点击冲突，播放按钮用 `@click.stop` 防止冒泡到条目
- 条目需要不透明背景（`#fdf9f3`），否则滑动时底层删除按钮会透出
- 跳转详情不中断播放：未触碰 playerStore 状态，仅路由跳转
- 附带清理：i18n 文件（zh/en）历史上存在大量重复 key（JSON last-wins，行为不变），本次重写已去重，解析结果与 HEAD 完全一致（已逐 key 校验）

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 测试验证

- `npm run build` 通过；生产 bundle 确认包含新代码
- 线上验证（Playwright + API stub，生产环境真实 bundle，375×812 移动视口）：
  - 队列条目渲染为 `van-swipe-cell` + 40px 播放按钮，旧 16px cross 图标为 0
  - 点击条目 → 跳转 `/article/<encoded-url>` 文章详情页（与 FeedView 同一数据通道）
  - TouchEvent 左滑 → 露出 74px 宽「删除」按钮；点击删除 → 条目移除（3→2 行）
  - console 无 JS 异常（仅 stub 环境预期的 401/404 资源错误）
- 真机滑动手感（iOS PWA）需用户实测

## 修复记录

**修复文件**: `frontend/src/views/ListenView.vue`、`frontend/src/i18n/zh.json`、`frontend/src/i18n/en.json`

**修复时间**: 2026-07-21

**修改内容**:
- 队列条目用 `van-swipe-cell` 包裹，右滑出 `删除` 按钮（`type="danger"`，全高）
- 条目点击从 `playQueueItem` 改为 `openArticle`（跳转文章详情，数据通道与 FeedView 一致）
- 新增 `onQueuePlayButton`：播放/暂停切换 + 从当前条播放队列，40px 圆形按钮带 aria-label
- 删除原 16px cross 图标；新增 `.queue-play-btn` / `.queue-delete-btn` / 条目不透明背景样式
- i18n 新增 `listen.playFromHere`（zh: 播放此篇 / en: Play this article）

## 相关提交

- `66fac24` fix(queue): stop deleted items reappearing across devices, revamp queue item UX
