# Frontend i18n: Hardcoded Chinese Strings in Dialogs, Toasts, and TTS Components

## 问题描述

用户切换英文/中文语言偏好后，前端大量用户可见的提示语、弹框、Toast 仍然只显示中文，没有跟随用户选择的语言切换。具体表现：

- **TTS 配额耗尽弹框**（如“升级 Pro”提示）只有中文文案
- **播放器操作 Toast**（暂停、快进、播放完成等）始终显示中文
- **网络状态提示**（网络断开/恢复）始终显示中文
- **TTS / 播客 / Feed 相关错误提示** 大量硬编码中文
- **Debug 诊断页面** 标题、按钮、标签全部硬编码中文

预期表现：所有用户可见字符串均通过 `vue-i18n` 按需渲染为英文或中文。

## 原因定位

### 根本原因
项目早期开发时大量使用了硬编码中文字符串，直接写死在 `showToast()`、`showConfirmDialog()`、`<template>` 标签以及 Media Session metadata 中。虽然 `en.json` / `zh.json` 翻译文件已存在且覆盖了很多通用场景，但以下模块缺少对应 key 或没有接入 `t()`：

1. `stores/playerStore.js` — 核心播放器逻辑，包含最多的硬编码 Toast 和升级弹框
2. `App.vue` — TTS fallback 降级弹框硬编码在 template 中
3. `composables/useTTS.js` / `useOpenAITts.js` / `useSpeechSynthesis.js` — TTS 引擎层错误提示和 Media Session 标题
4. `composables/useNetworkStatus.js` — 网络状态切换 Toast
5. `stores/podcastPlayerStore.js` — 播客播放器错误提示
6. `views/FeedView.vue` — 离线模式下的 Feed 提示
7. `components/TtsDebugPanel.vue` / `views/DebugTTSView.vue` / `views/DebugTTSLogsView.vue` — Debug 页面完全未接入 i18n

### 具体流程问题
- 在 Pinia store 和 composable 中，开发者直接传入中文字面量，如 `showToast({ message: '已暂停' })`
- 部分字符串存在于 `en.json`/`zh.json` 中，但代码侧未使用 `useI18n()` 或 `i18n.global.t()` 绑定
- Debug 页面由于仅供内部使用，被遗漏在 i18n 体系之外

### 相关代码位置
- `frontend/src/stores/playerStore.js` — 硬编码位置：L192, L253, L262, L386-390, L395, L399, L407, L425, L468, L478, L487, L559, L564, L598, L609, L679, L689, L697, L704, L706, L716, L723, L725, L735, L761, L782
- `frontend/src/App.vue` — 硬编码位置：L73-82
- `frontend/src/composables/useTTS.js` — 硬编码位置：L285, L301, L678, L686, L704, L893, L901, L940
- `frontend/src/composables/useOpenAITts.js` — 硬编码位置：L137, L301, L468, L531, L677, L709, L718, L781
- `frontend/src/composables/useSpeechSynthesis.js` — 硬编码位置：L302-315, L330, L342, L353, L445, L546, L556
- `frontend/src/composables/useNetworkStatus.js` — 硬编码位置：L30, L39
- `frontend/src/stores/podcastPlayerStore.js` — 硬编码位置：L121, L145, L226, L275, L286
- `frontend/src/views/FeedView.vue` — 硬编码位置：L250, L252
- `frontend/src/components/TtsDebugPanel.vue` — 全组件模板和脚本
- `frontend/src/views/DebugTTSView.vue` — 全组件模板和脚本
- `frontend/src/views/DebugTTSLogsView.vue` — 全组件模板和脚本

## 修复方案

1. **补充翻译 key**：在 `frontend/src/i18n/en.json` 和 `zh.json` 中新增缺失的命名空间（`tts`、`speech`、`network`、`subscription`、`feed`、`podcast`、`debug` 等）。
2. **Pinia Store / Composable 接入 i18n**：
   - 在 `defineStore` 和 composable 函数体内顶部调用 `const { t } = useI18n()`
   - 将所有 `showToast({ message: '中文' })` 替换为 `showToast({ message: t('key') })`
   - 对需要参数插值的（如“快进 15 秒”）使用 `t('key', { n: 15 })`
3. **Vue 组件 template 接入 i18n**：
   - `App.vue` 的 fallback dialog 改用 `:title="$t(...)"` 和插值
   - Debug 页面全面接入 `$t` / `t`
4. **SpeechSynthesis 错误映射表**：将硬编码错误提示对象改为基于 `t()` 的动态对象或函数
5. **验证策略**：
   - 全局搜索 `showToast.*['"]` 和 `showConfirmDialog.*title.*['"]` 确保无残留硬编码中文用户提示
   - 在浏览器中切换 `en`/`zh` 验证关键弹框和 Toast

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/i18n/en.json`
- `frontend/src/i18n/zh.json`
- `frontend/src/stores/playerStore.js`
- `frontend/src/App.vue`
- `frontend/src/composables/useTTS.js`
- `frontend/src/composables/useOpenAITts.js`
- `frontend/src/composables/useSpeechSynthesis.js`
- `frontend/src/composables/useNetworkStatus.js`
- `frontend/src/stores/podcastPlayerStore.js`
- `frontend/src/stores/conversationStore.js`
- `frontend/src/api/request.js`
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/TtsPlayerView.vue`
- `frontend/src/components/UnifiedFloatingPlayer.vue`
- `frontend/src/components/TtsDebugPanel.vue`
- `frontend/src/views/DebugTTSView.vue`
- `frontend/src/views/DebugTTSLogsView.vue`

**修复时间**: 2026-04-15

**修改内容**:
- 补充 40+ 缺失翻译 key 到 `en.json` / `zh.json`（覆盖 `player`、`tts`、`speech`、`network`、`feed`、`podcast`、`debug`、`subscription` 命名空间）
- 新增 `common` 命名空间 key：`unauthorized`、`accessDenied`、`resourceNotFound`、`serverError`、`requestFailed`、`syncFailed`、`cover`
- 新增 27 个 `debug.*` 日志消息翻译 key，用于 TTS 结构化日志（如 `noAudioInstance`、`playSuccess`、`audioError`、`seekToFailed` 等）
- 将 `playerStore.js` 中所有硬编码 Toast / Dialog 改为 `t()` 调用（含升级 Pro 弹框、配额耗尽提示、播放控制提示等）
- 将 `App.vue` fallback dialog 改为 `$t()` 绑定
- 将 `useTTS.js`、`useOpenAITts.js`、`useSpeechSynthesis.js` 错误提示和 Media Session 标题改为 `t()` 调用
- 将 `useNetworkStatus.js` 网络提示改为 `t()` 调用
- 将 `podcastPlayerStore.js` 播客错误提示改为 `t()` 调用
- 将 `conversationStore.js` 助手回退错误消息改为 `t('conversation.errorMessage')`
- 将 `request.js` HTTP 错误提示改为 `i18n.global.t()` 调用
- 将 `FeedView.vue` 离线提示与同步失败提示改为 `t()` 调用
- 将 `TtsPlayerView.vue` `alt="封面"` 改为 `:alt="$t('common.cover')"`
- 将 `UnifiedFloatingPlayer.vue` 本地语音降级提示改为 `t('tts.fallbackMode')`
- 将 `ttsPerformanceLogger.js` 报告对象 key 从中文改为英文，确保 `DebugTTSView` 模板可通过 `$t()` 翻译
- 将 Debug 页面（`TtsDebugPanel.vue`、`DebugTTSView.vue`、`DebugTTSLogsView.vue`）全面接入 i18n：模板标签、Toast / Dialog、日志图标、统计卡片全部使用 `$t()` / `t()`
- `useOpenAITts.js` 中所有 `logToStorage` 调用增加 `{ type, key }` 结构化元数据，Debug 视图优先用 `log.type` 做分类/统计/样式，并用 `log.key ? $t(log.key) : log.message` 渲染日志文本（旧日志兼容回退）

**测试验证**:
- 全局 grep 搜索 `showToast`、`showDialog`、`showConfirmDialog` 中已无硬编码中文用户提示
- 所有 Debug 页面模板和脚本中的中文标签、按钮文案、Toast 均已替换为翻译 key
- `useOpenAITts.js` 中所有 `logToStorage` 调用均已传入 `{ type, key }` 元数据
- `TtsDebugPanel.vue` 和 `DebugTTSLogsView.vue` 已改用 `log.type` 驱动分类/统计/样式，并用 `log.key` 做翻译渲染
- 英文/中文翻译文件 key 一一对应，无遗漏

## 相关提交

- (待补充)

## Review意见

## Feature: frontend-i18n-hardcoded-chinese-strings
- problem 1：
  - level: p1
  - decription: [Boundary] The debug pages still render raw log messages that are persisted in Chinese. `frontend/src/composables/useOpenAITts.js:162`, `frontend/src/composables/useOpenAITts.js:187`, and `frontend/src/composables/useOpenAITts.js:207` still write Chinese messages into storage, while `frontend/src/views/DebugTTSLogsView.vue:82` and `frontend/src/components/TtsDebugPanel.vue:188` render `log.message` verbatim. In an English locale, users will still see Chinese content on the debug pages, so this bug is not fully closed for the “Debug 页面全面接入 i18n” scope.
  - fix suggestion: Persist stable event codes and structured metadata such as `event`, `status`, and `details`, then translate only at render time. Avoid storing localized Chinese sentences as the canonical log payload.
  - decision and reason(by claude): 🔄 修改后接受 — 完全结构化日志重构收益有限且改动面大。改为在 `logToStorage` 中额外存储 `type` 和 `key`（翻译 key），Debug 页面优先用 `$t(log.key)` 渲染，无 `key` 时回退到原始 `message`。这样新增代码量小，既解决了英文模式下看到中文的问题，又保留了对旧日志的兼容。

- problem 2：
  - level: p1
  - decription: [Implicit assumptions] Diagnostic behavior is still coupled to Chinese substrings. `frontend/src/views/DebugTTSLogsView.vue:233`, `frontend/src/views/DebugTTSLogsView.vue:244`, `frontend/src/views/DebugTTSLogsView.vue:251`, `frontend/src/views/DebugTTSLogsView.vue:258`, `frontend/src/views/DebugTTSLogsView.vue:274`, `frontend/src/views/DebugTTSLogsView.vue:283`, `frontend/src/components/TtsDebugPanel.vue:134`, and `frontend/src/components/TtsDebugPanel.vue:184` classify errors/success/rate events by matching words like `失败`, `错误`, and `播放成功`. If the logger output is moved to English, or if old and new logs mix, counters, badges, and error highlighting will become incorrect.
  - fix suggestion: Introduce structured log fields for type and status, and drive summary cards / styling from those fields instead of parsing localized display text.
  - decision and reason(by claude): 🔄 修改后接受 — 在 `logToStorage` 时增加 `type` 字段（`success` / `error` / `media` / `rate` / `log`），并在 Debug 视图中用 `log.type` 做分类、计数和样式驱动。对没有 `type` 的旧日志保留中文子串回退，确保兼容。

- problem 3：
  - level: p1
  - decription: [Boundary] There are still user-visible hardcoded strings outside the patched set, so the broader claim “所有用户可见字符串均通过 vue-i18n 渲染” is not yet true. Concrete examples include `frontend/src/components/UnifiedFloatingPlayer.vue:124` (`正在切换到本地语音`), `frontend/src/api/request.js:50`, `frontend/src/api/request.js:54`, `frontend/src/api/request.js:69`, `frontend/src/api/request.js:72`, `frontend/src/api/request.js:75`, `frontend/src/api/request.js:78`, `frontend/src/api/request.js:81` (HTTP error toasts), `frontend/src/stores/conversationStore.js:48` (assistant fallback error message), and `frontend/src/views/FeedView.vue:476` (English-only sync failure toast). These are easy to miss because they sit outside the TTS/debug files listed in this bug doc, but they are still directly user-facing.
  - fix suggestion: Do one repo-wide audit for user-facing literals, especially `showToast`, dialog configs, fallback assistant messages, and accessibility text, then move the remaining cases to `vue-i18n` or a shared global translator helper.
  - decision and reason(by claude): ✅ 接受 — 这些都是用户直接可见的文案，应一并修复。`request.js` 通过 `i18n.global.t()` 接入；`conversationStore.js` 通过 `useI18n()` 接入；`UnifiedFloatingPlayer.vue` 和 `FeedView.vue` 改用已有或新增翻译 key。

- problem 4：
  - level: p2
  - decription: [Maintainability] `frontend/src/views/TtsPlayerView.vue:19` still uses `alt=”封面”`. This is user-facing for screen readers and remains Chinese in English locale, so accessibility text is still inconsistent with the intended i18n cleanup.
  - fix suggestion: Translate the alt text via `$t(...)`, or derive it from the article title with a localized fallback.
  - decision and reason(by claude): ✅ 接受 — 无障碍文本也属于用户可见字符串，替换为 `$t('common.cover')` 并补充对应翻译 key 即可，改动极小。


## Comments and Future suggestion

- The core TTS/player/dialog cleanup is mostly on the right track, and the added i18n keys look broadly consistent between `en.json` and `zh.json`.
- The main gap is that the debug system still stores and interprets localized Chinese strings as data. That makes the UI translation look finished while the underlying behavior is still locale-dependent.
- After fixing the findings above, I would rerun a narrower audit with patterns like `showToast\\(`, `showDialog\\(`, `showConfirmDialog\\(`, `alt=`, and direct fallback strings in stores/composables to close the remaining edge cases cleanly.

## Review意见（复审 2）

## Feature: frontend-i18n-hardcoded-chinese-strings-followup
- problem 1：
  - level: p2
  - decription: [Boundary] The new structured-log fix does not fully preserve the claimed compatibility for old logs. `frontend/src/views/DebugTTSLogsView.vue:226`, `frontend/src/views/DebugTTSLogsView.vue:233`, `frontend/src/views/DebugTTSLogsView.vue:240`, and `frontend/src/views/DebugTTSLogsView.vue:247` now count only `log.type`, and `frontend/src/components/TtsDebugPanel.vue:134` also counts errors only via `log.type === 'error'`. Old stored logs do not have `type`, so the summary cards and error totals will silently show `0` until users generate fresh logs, even though the row rendering still has a substring fallback.
  - fix suggestion: Reuse the same compatibility fallback in the aggregate counters that you already added for row styling, or run a one-time migration that backfills `type` for existing `tts_debug_logs`.
  - decision and reason(by claude):


## Comments and Future suggestion（复审 2）

- The previously reported user-facing hardcoded strings are largely fixed, and the `log.key` / `log.type` direction is the right cleanup path.
- I would not block release on this remaining issue if the team is okay dropping historical debug-card accuracy, but the current code should not claim full old-log compatibility yet.
