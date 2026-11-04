# Readaria 桌面端 Web 版本设计文档（v1）

> 日期：2026-09-02 · 状态：已与用户确认 · 类型：功能设计（brainstorm 输出）
> 配套启动 prompt：`docs/[plan]desktop_web_kickoff_prompt.md`

## 1. 背景与目标

Readaria 目前是移动端优先的 PWA（Vue 3 + Vant 4），桌面浏览器打开 readaria.com 只能看到被拉伸的移动端布局。

**目标**：桌面浏览器访问 readaria.com 时，获得复刻 Readwise Reader 风格的三栏桌面体验。

**v1 范围**（已与用户确认）：

- ✅ 阅读与筛选（Reading & triage）：文章列表、阅读面板、保存/取消保存、分区导航
- ✅ Feed 管理：添加/删除/刷新 feed、Feed Discover 页面
- ✅ Readwise 式键盘快捷键
- ✅ 中文衬线排版（宋体系）
- ❌ 桌面端 TTS 播放器 UI（全局 `UnifiedFloatingPlayer` 保持原样，不做桌面适配）
- ❌ Podcasts、Search、Me/Profile 页面的桌面版
- ❌ Onboarding 流程重设计（保持现状，功能可用即可）
- ❌ 暗色模式、字体切换器（serif/sans 切换）

## 2. 架构：响应式 Shell，同 URL 双布局

**核心决策（已确认）**：同一应用、同一路由表、同一 URL，按断点切换布局。不新建独立桌面应用，不新增 `/desktop/*` 路由前缀。

### 2.1 断点

- 桌面布局：viewport **≥ 1024px**
- < 1024px（手机、平板）：保持现有移动布局，零改动
- 窗口缩放跨过断点时**实时切换**布局（`matchMedia` 监听，非仅加载时判断）

### 2.2 新增代码结构

```
frontend/src/
├─ composables/
│  └─ useBreakpoint.js        # matchMedia 封装，导出 isDesktop (ref)
├─ layouts/
│  └─ DesktopShell.vue        # 桌面外壳：左侧导航栏 + 主区域 <router-view>
├─ views/desktop/
│  ├─ DesktopFeedView.vue         # 三栏：列表 + 阅读面板（对应 /feed）
│  ├─ DesktopArticleReader.vue    # 三栏 + 加载指定文章（对应 /article/:id）
│  ├─ DesktopSavedView.vue        # 三栏，Saved 列表（对应 /saved）
│  ├─ DesktopFeedManageView.vue   # Feed 管理桌面版（对应 /manage/feeds 等）
│  └─ DesktopFeedDiscoverView.vue # Feed Discover 桌面版
└─ components/desktop/
   ├─ DesktopSidebar.vue      # 左栏导航（Feeds / Saved / Manage + 底部用户入口）
   ├─ ArticleListPane.vue      # 中栏文章列表（无限滚动、选中态高亮）
   ├─ ReadingPane.vue          # 右栏阅读面板（排版核心）
   └─ ShortcutHelpOverlay.vue  # ? 键快捷键帮助浮层
```

### 2.3 路由解析

- 路由表增加一个 `responsive(mobileComponent, desktopComponent)` 辅助函数，按 `isDesktop` 返回对应组件；`/feed`、`/article/:id`、`/saved`、`/manage/*` 四条路由使用它，其余路由不变
- `App.vue` 按断点选择渲染 `DesktopShell` 或现有 `van-tabbar` 外壳
- `/article/:id` 在桌面端渲染 `DesktopArticleReader`（三栏布局 + 指定文章），保证链接可深链、可分享

### 2.4 复用与约束

- **零后端 API 改动**。桌面视图复用现有 Pinia stores（`articleStore`、`feedStore` 等）、`services/`、`i18n`
- 桌面组件**不使用 Vant 布局/表单组件**（van-nav-bar/van-list/van-tabbar/van-cell 等触屏组件）；命令式反馈服务（`showToast`/`showConfirmDialog`/`showLoadingToast`）沿用 Vant —— 其渲染为居中浮层，桌面端表现正常
- 登录/注册页不做独立桌面视图：路由 meta 加 `desktopCenter: true`，桌面端以居中 480px 窄列渲染现有视图即可（不经 DesktopShell）

## 3. 三栏阅读体验（核心页面）

```
┌────────────┬──────────────────┬────────────────────────┐
│ 左栏        │ 中栏              │ 右栏                    │
│ Sidebar    │ ArticleListPane  │ ReadingPane            │
│  200-240px │  320-400px       │  自适应，内容列 ≤660px   │
│            │                  │                        │
│ Feeds      │ 文章卡片列表       │ 衬线标题                │
│ Saved      │ (无限滚动)        │ 来源 · 日期 · 阅读时长    │
│ Manage     │ 选中项高亮        │ 正文（宋体，1.9 行高）     │
│            │                  │                        │
│ ─────────  │                  │                        │
│ 用户入口*   │                  │                        │
└────────────┴──────────────────┴────────────────────────┘
```

\* 左栏底部用户入口：显示当前用户 + 退出登录；`/me` 不做桌面版，桌面访问时以居中窄列渲染现有移动视图，保证功能可用

- 点击中栏文章（或对选中项按 `Enter`）→ 右栏加载正文，**同时 URL 变为 `/article/:id`**（与 Readwise 一致：URL 始终反映当前选中文章，天然支持深链与分享；列表状态由 store 保留，不随路由变化丢失）
- Saved 页复用同一三栏模式
- Feed 管理/Discover 桌面版：双栏或单主区即可，复用现有 store 逻辑，排版对齐桌面风格

## 4. 阅读排版规范（Readwise 核心复刻）

| 项目 | 值 |
|---|---|
| 中文字体 | `'Songti SC', 'Noto Serif SC', serif`（沿用并扩展 `--jasmine-serif`） |
| 西文字体 | `Georgia, 'Times New Roman', serif` 回退 |
| 正文号 | 17-18px |
| 行高 | 1.9 |
| 段落间距 | ≥ 1em |
| 内容列宽（measure） | 65-75 字符，约 660px，居中 |
| 标题 | 衬线、大号、加粗 |
| 背景 | `--jasmine-paper` (#fbf7f0) |
| 元信息行 | 来源 · 日期 · 预计阅读时长，弱化色 `--jasmine-muted` |

新增 CSS 变量（如 `--reading-measure`、`--reading-line-height`）统一放在 `style.css` 的 `:root` 中。

仅浅色主题；暗色模式为后续迭代。

## 5. 键盘快捷键

| 键 | 行为 |
|---|---|
| `j` / `k` 或 `↓` / `↑` | 中栏列表上下移动选中 |
| `Enter` | 在右栏打开选中文章 |
| `s` | 保存 / 取消保存当前文章 |
| `1` / `2` / `3` | 切换左栏分区（Feeds / Saved / Manage） |
| `?` | 快捷键帮助浮层 |

约束：输入框聚焦时快捷键全局禁用；仅在桌面布局且处于 feed/saved/article 上下文时激活。

## 6. 边界与错误处理

- **实时缩放**：跨过 1024px 时布局即时互换；桌面三栏 → 移动端时保持当前文章上下文（`/article/:id` 深链天然保证）
- **平板宽度**（768-1023px）：走移动布局，不做中间态
- **加载/错误态**：阅读面板加载与 API 错误沿用现有 toast/重试模式，不新建机制
- **无选中文章**（`/feed` 初始态）：右栏显示空态引导（"选择一篇文章开始阅读"）

## 7. 测试计划

前端无 vitest/jest 设施，v1 不新增单测框架；逻辑保持薄，以 E2E 覆盖：

- **Playwright 桌面视口**（1280×800）新增用例：
  1. `/feed` 渲染三栏布局
  2. 点击文章 → 右栏阅读面板加载
  3. `s` 快捷键保存文章生效
  4. `?` 帮助浮层开合
  5. Feed 管理：添加/删除 feed
- **移动端回归**：现有 37 个 Playwright E2E 全部保持绿色（共享代码库最大风险点）
- 提交前执行 `make test-local`（遵循 `docs/TESTING_GUIDE.md`）

## 8. 验收标准

1. 桌面 Chrome/Safari 打开 readaria.com（≥1024px）呈现三栏布局；<1024px 完全保持现有移动体验
2. 阅读面板排版符合 §4 规范（宋体正文、1.9 行高、660px 内容列）
3. §5 快捷键全部可用且不干扰输入
4. Feed 管理（增删刷新、Discover）桌面端可用
5. 无后端 API 变更；移动端 E2E 零回归
6. 部署：纯前端变更，走 GitHub Actions → Cloudflare Workers 前端流水线，**无需后端部署**

## 9. 交付物

- 本设计文档（source of truth）
- 启动 prompt：`docs/[plan]desktop_web_kickoff_prompt.md` —— 粘贴到新 Claude Code 会话即可启动实现
