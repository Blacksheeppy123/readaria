# Onboarding PWA Install Prompt Not Reappearing

## 问题描述

在 Android 新人 onboarding 流程中，预期应在第一次音频开始播放后 3-5 秒出现 PWA 安装引导横幅。

实际测试中，使用同一浏览器连续注册/登录多个新账号时，后续账号即使成功播放了 onboarding 首次音频，也可能始终看不到安装提示，表现为“似乎从没弹出过安卓添加桌面提示”。

**预期表现**:
- Android Chrome 新用户在首次音频播放后看到自定义 PWA 安装横幅
- iOS Safari 看到手动添加到主屏幕提示
- 已 dismiss 的用户 7 天内不重复提示

**实际表现**:
- 同一浏览器里，第一个账号触发过首次音频后，后续账号可能不再触发 PWA 引导显示逻辑

## 原因定位

### 根本原因

首次音频事件通过 `window.__firstAudioPlayedEmitted` 做全局“一次性闸门”。

该标记在账号切换、登出、重新走 onboarding 时没有被重置，导致：

1. 第一个账号成功播放后，将 `window.__firstAudioPlayedEmitted = true`
2. 后续账号再次播放首次音频时，`emitFirstAudioPlayed()` 被直接短路
3. `PwaInstallBanner` 监听不到 `first-audio-played`
4. 因此不会再进入 3-5 秒延迟展示逻辑

### 相关流程说明

- `frontend/src/stores/playerStore.js`
- `frontend/src/stores/podcastPlayerStore.js`
- `frontend/src/components/PwaInstallBanner.vue`
- `frontend/src/utils/authSessionReset.js`

另外，`PwaInstallBanner.vue` 还存在一个**符合设计**的冷却逻辑：

- `localStorage['pwa_prompt_dismissed_at']` 会让用户 dismiss 后 7 天内不再显示

所以“同一浏览器多账号回归”里，可能同时受到：

1. 运行时 bug：首次音频事件未重置
2. 产品规则：7 天 dismiss 冷却

## 修复方案

- 在统一的登录/登出会话重置流程中，显式清除 `window.__firstAudioPlayedEmitted`
- 保持 `pwa_prompt_dismissed_at` 的 7 天冷却规则不变，因为这是设计预期，不应因切账号而自动清空

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/utils/authSessionReset.js`

**修复时间**: 2026-04-30

**修改内容**:
- 在 auth session reset 流程里重置 `window.__firstAudioPlayedEmitted`，确保重新登录或切账号后，新的首次音频仍能触发 onboarding/PWA 引导事件链

## 验证建议

1. 在 Android Chrome 中使用全新浏览器状态测试一个新账号，确认首次音频后会出现 PWA 横幅
2. 点击 `Not now` 后，再注册第二个账号，确认 7 天冷却仍会阻止再次显示
3. 不 dismiss、仅切账号重测时，确认后续账号仍会重新触发 `first-audio-played`
