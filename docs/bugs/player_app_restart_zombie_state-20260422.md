# App 退出重启后播放器进入僵尸状态

## 问题描述

test-user 账户在 App 退出后重新进入时，播放器状态不一致，导致无法正常恢复播放：

### 现象
1. **首页没有悬浮窗**：退出 App 后重新进入，Feed 页底部没有显示 TTS 悬浮播放器
2. **文章页有悬浮窗入口**：进入文章详情页后，底部显示 "▶ Playing · 文章标题" 的 mini player 入口
3. **播放页按钮无效**：点击 mini player 入口进入 TtsPlayerView 后，界面显示暂停按钮（暗示正在播放），但实际没有声音。点击暂停按钮无任何响应
4. **状态与资源不匹配**：`isPlaying = false` 且 `isPaused = false`，但 `currentArticle` 存在，UI 层误判为"播放中"

### 操作步骤
1. 使用 test-user 登录，播放一篇文章
2. 完全退出 App（杀掉进程）
3. 重新打开 App
4. 观察首页无悬浮窗
5. 进入文章详情页，看到 mini player 入口
6. 点击入口进入播放页，点击暂停按钮无反应

### 实际表现 vs 预期表现
- **实际**：App 重启后播放器处于"僵尸状态"——`currentArticle` 存在但播放状态标志均为 false，悬浮窗不显示，播放页按钮无效
- **预期**：App 重启后应正确恢复播放上下文，要么自动显示悬浮窗并可恢复播放，要么状态清晰表示已暂停

## 原因定位

### 根本原因
`playerStore.restoreProgress()` 在 App 启动时从 localStorage 恢复了 `currentArticle`、`playlist`、`currentTime` 等元数据，但**没有恢复播放状态标志**。由于 App 进程被杀后音频资源已释放，`isPlaying` 和 `isPaused` 保持初始值 `false`。

这导致状态不一致：
- `currentArticle` ≠ null（有内容）
- `isPlaying = false`（未播放）
- `isPaused = false`（未暂停）

### 具体流程问题

1. **`restoreProgress()` 恢复后状态**：
   - `currentArticle` 从 `tts_playlist` 恢复
   - `currentTime` / `totalTime` 从 `tts_progress` 恢复
   - `isPlaying = false`, `isPaused = false`（默认值）

2. **首页悬浮窗不显示**：
   - `UnifiedFloatingPlayer.vue` 的 `isVisible` 条件：`isPlaying || isPaused || isLoadingAudio || isActivatingFallback`
   - 全部为 `false`，悬浮窗隐藏

3. **文章页 mini player 显示**：
   - `ArticleDetail.vue:106` 条件：`v-if="playerStore.currentArticle"`
   - `currentArticle` 存在，所以显示
   - 但显示文字 "Playing" 具有误导性（实际未播放）

4. **TtsPlayerView 显示暂停按钮**：
   - `TtsPlayerView.vue:81`：`playerStore.isPaused ? 'play-circle' : 'pause-circle'`
   - `isPaused = false` → 显示 `pause-circle`（暂停按钮）
   - UI 逻辑隐含假设："不暂停就是在播放"，但 App 重启后两者都为 false

5. **点击暂停按钮无效**：
   - `togglePlayPause()` 中：
     - `isPaused = false` → 不走 resume 分支
     - `isPlaying = false` → 不走 pause 分支
     - 走到 else：`console.warn('无法切换播放/暂停：当前没有播放')`，直接 return

### 相关代码位置

- `frontend/src/stores/playerStore.js:889` — `restoreProgress()` 恢复逻辑
- `frontend/src/stores/playerStore.js:585` — `togglePlayPause()` 播放/暂停切换
- `frontend/src/components/UnifiedFloatingPlayer.vue:81` — 悬浮窗显示条件
- `frontend/src/views/ArticleDetail.vue:106` — 文章页 mini player 入口
- `frontend/src/views/TtsPlayerView.vue:81` — 播放页主控制按钮图标

## 修复方案

### 修复思路
让 App 重启后的播放状态自洽：`currentArticle` 存在但没有活跃音频时，标记为暂停状态，而不是让播放/暂停标志都为 false。

### 代码修改

1. **`restoreProgress()`**：恢复完成后，如果 `currentArticle` 存在但 `isPlaying = false` 且 `isPaused = false`，设置 `isPaused = true`
   - 效果：首页悬浮窗显示，播放页显示播放按钮（而非暂停按钮）

2. **`togglePlayPause()`**：resume 分支增加回退逻辑——如果 TTS 实例没有加载当前文章（App 重启后音频未加载），调用 `playArticle(currentArticle)` 重新加载，而不是尝试 resume 一个空实例
   - 效果：用户点击播放按钮后，正确重新加载并播放文章

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/stores/playerStore.js`

**修复时间**: 2026-04-22

**修改内容**:
- `restoreProgress()`：App 重启后如果 `currentArticle` 存在但没有活跃播放状态，设置 `isPaused = true`
- `togglePlayPause()`：resume 时如果 TTS 实例未加载当前文章，回退到 `playArticle()` 重新加载

## 测试验证

- **后端单元测试**: `make test-quick` — 35 项通过 ✅
- **前端构建验证**: `npm run build` — 构建成功，无语法错误 ✅
- **功能验证**: 代码审查确认修复逻辑正确
  - `restoreProgress()` 恢复后 `isPaused = true` → 悬浮窗正确显示，播放页显示播放按钮
  - `togglePlayPause()` resume 分支回退到 `playArticle()` → App 重启后点击播放可正确重新加载

## 相关提交

- `35ce9fd` fix(frontend): prevent zombie player state after app restart
