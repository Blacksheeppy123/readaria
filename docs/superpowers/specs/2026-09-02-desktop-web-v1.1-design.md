# Readaria 桌面端 v1.1 设计增补 —— 侧栏源筛选 / 三栏拖宽 / 沉浸阅读 / 隐藏桌面悬浮播放器

> 日期：2026-09-02 · 状态：已与用户确认 · 基于：`2026-09-02-desktop-web-version-design.md`（v1）

## 范围

1. **左侧栏订阅源列表（筛选重做）**：侧栏新增「订阅源」组——「全部来源」+ 各源（favicon + 名称），超出高度内部滚动
   - 在 `/feed`、`/article/:id`：点击源就地筛选中栏（`desktopArticleStore.selectFeed`，不离开当前页）
   - 在 `/saved`、`/feed/manage` 等其他页：先跳 `/feed` 再筛选
   - 「全部来源」= `selectFeed(null)`；当前筛选源高亮
   - 中栏顶部工具条抽为共享组件 `ListToolbar.vue`（排序切换 + 当前源名称显示，移除原生 `<select>`），`/feed` 与 `/article/:id` 的中栏都使用
   - **约束**：后端列表 API 仅支持 `feed_id`/`source`，无 author 参数；RSS 场景作者≈来源，本期只做按来源筛选
2. **三栏拖拽调宽**：侧栏|中栏、中栏|阅读面板两条分隔线可拖（4px 热区、hover 高亮）；侧栏 180–300px、中栏 280–520px；宽度持久化到 `localStorage["readaria_desktop_layout"]`
   - 实现：`useDesktopLayout` composable 持有宽度状态并直接写 `:root` CSS 变量（`--desktop-sidebar-width` / `--desktop-list-width`），所有使用者自动更新；`PaneDivider.vue` 处理拖拽
3. **沉浸式阅读**：阅读面板头部「⤢」按钮 + 快捷键 `f` 进入；隐藏左栏与中栏，正文列居中放宽至 720px；`f` / `Esc` / 按钮退出
   - `immersive` 状态在 `useDesktopLayout`；快捷键挂 DesktopShell（侧栏隐藏后仍可用 Esc/f 退出）
   - 帮助浮层补 `f` / `Esc` 说明
4. **桌面端隐藏悬浮播放器**：`App.vue` 的 `UnifiedFloatingPlayer` 加 `v-if="!isDesktop"`；移动端不变

## 非目标

- 作者维度筛选（需后端加参数，后续再说）
- 移动端任何变化；暗色模式；TTS 桌面 UI

## 新增 i18n（desktop.*）

`feeds`（订阅源/Sources）、`allFeeds`（全部来源/All sources）、`focusMode`（沉浸阅读/Focus mode）、`shortcutImmersive`（进入/退出沉浸阅读 / Toggle focus mode）

## 测试

desktop.spec.ts 增补 4 用例：
1. 侧栏源列表渲染；点击源 → 中栏请求带 `feed_id` 且工具条显示源名
2. 阅读页内点源筛选：URL 保持 `/article/...` 不变
3. 拖拽中栏分隔线 → `localStorage.readaria_desktop_layout` 更新；刷新后宽度保持
4. `f` 进入沉浸（侧栏/中栏隐藏）、`Esc` 退出；桌面端无悬浮播放器 DOM

流程同 v1：实现 → Codex review → E2E → push 自动部署 → 线上验证。
