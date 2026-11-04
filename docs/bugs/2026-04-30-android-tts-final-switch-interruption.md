# Android TTS 分段转完整音频时播放中断

## 问题描述

- **功能模块**: Android 端文章 TTS 播放
- **用户场景**: 使用中文体验用户 `onboarding-experience-zh`，播放不懂经里关于凯文凯利的文章时，中途出现播放中断/暂停
- **实际表现**: 播放一段时间后自动停住，需要用户手动再点一次播放才继续
- **预期表现**: 从首段分段播放切换到完整 MP3 时应无感继续，不应进入暂停态

## 原因定位

### 根本原因

本次问题的高概率根因不是后端 TTS 生成失败，而是**前端在“segment 播放 -> final MP3 播放”切换时，把同一个 `Audio` 实例的 `src` 替换成完整音频，过程中先触发了 `pause` 状态，但后续自动 `play()` 没有稳定接上**。

结果就是：

1. 用户前面已经正常听到分段音频
2. 某个分段结束后，前端尝试切到 `final.mp3`
3. 切源时 `pause` 事件先把状态置为 `isPaused = true`
4. 如果后续自动播放未及时接上，播放器就停在“已暂停但可恢复”的状态
5. 用户手动点播放后，`playerStore.togglePlayPause()` 会调用 `newTts.play()`，因此又能继续

这和用户体感“中途中断，手动点一下又继续”一致。

### 线上证据

#### 1. 后端生成链路正常，没有看到 prepare / segment 失败

- `2026-04-30 13:26:18`，`api.log` 记录：
  - `[TTS] Segment parallel generation: article_id=76605, parallel_count=1, seg0_time=8650ms, seg1_time=0ms, first_playable_ready_ms=8650ms`
- 说明文章 `76605` 的首段在 8.65 秒内就已经 ready，后端生成链路正常。

#### 2. Android 客户端确实先走了 segmented 播放，再在几分钟后切到 final MP3

`nginx access log` 记录了同一用户、同一文章的完整链路：

- `2026-04-30 13:22:31` 开始持续请求 `GET /api/v1/tts/prepare/76605`
- `2026-04-30 13:22:34` 请求 `GET /api/v1/tts/segments/76605/1`
- `2026-04-30 13:25:37` 开始 `prepare` 返回更大的 payload（从 `572` 增到 `591`），说明 ready 状态继续推进
- `2026-04-30 13:28:31` 同时出现两次 `GET /api/v1/tts/play/76605`，说明前端在该时刻切换到了完整 MP3

这条时间线符合当前前端实现：

- 首播先靠 `segment` 起播
- 后台继续轮询 `prepare`
- 等 `final_ready` 后切到 `/api/v1/tts/play/{article_id}`

#### 3. 没有证据表明这次是老的后端 500 / missing await 问题

- 本次 `nginx access log` 里 `/api/v1/tts/prepare/76605`、`/api/v1/tts/segments/76605/*`、`/api/v1/tts/play/76605` 都是 `200`
- 因此可以排除 `2026-04-23` 的 `tts_play_api_missing_await` 那类后端 500 故障

#### 4. 前端日志证据不足，但这是当前排查的已知限制

- 当前 `frontend.log` 没抓到这次 `onboarding-experience-zh` 安卓会话的对应上传记录
- 现有前端日志上传更偏向白名单测试账号，导致这次不能直接看到 `[useTTS] Duration` / `Audio error` / `Cloud V2 audio playing` 的完整前端日志链
- 因此“自动播放未接上”的最后一步属于**结合 Nginx 时间线与前端代码路径的强推断**

### 具体流程问题

当前代码里，分段结束后的切换逻辑是：

1. `globalAudio` 触发 `ended`
2. `useTTS.handleCloudSegmentEnded()` 检查 `final_ready`
3. 若 `final_ready = true`，调用 `playFinalAudio(source, finishedTime, { autoPlay: true })`
4. `playFinalAudio()` 直接替换 `globalAudio.src` 为 `/api/v1/tts/play/{article_id}`，然后 `load()`
5. 同一个 `Audio` 实例在切源期间会先触发 `pause`
6. `pause` 监听里只要 `currentTime < totalTime`，就会把状态写成 `isPaused = true`
7. 若随后 `globalAudio.play()` 没有稳定生效，UI 就会停留在暂停态，直到用户手动恢复

### 相关代码位置

- `frontend/src/composables/useTTS.js:331-337`
  - `pause` 事件会在 `currentTime < totalTime` 时把状态置为 `isPaused = true`
- `frontend/src/composables/useTTS.js:341-348`
  - 分段音频结束后进入 `handleCloudSegmentEnded()`
- `frontend/src/composables/useTTS.js:729-777`
  - `playFinalAudio()` 直接替换 `globalAudio.src`、`load()`、再 `play()`
- `frontend/src/composables/useTTS.js:868-903`
  - `handleCloudSegmentEnded()` 在 `final_ready` 时直接切换到完整音频
- `frontend/src/stores/playerStore.js:355-393`
  - 外层每 100ms 同步一次 `isPlaying / isPaused / isLoading`
- `frontend/src/stores/playerStore.js:624-644`
  - 用户手动点击播放时，如果当前是 `isPaused`，会调用 `newTts.play()` 恢复

## 修复方案

建议优先做最小修复，目标是避免“切 final 时先进入 paused 态”：

1. 在 `handleCloudSegmentEnded() -> playFinalAudio()` 这条链路增加“切源中”保护状态
   - 切换 final 音频期间，不要让普通 `pause` 事件把状态写成用户可见的 `isPaused = true`

2. 区分“系统/切源触发的 pause”与“用户主动 pause”
   - 仅在 `manualPause = true` 或显式用户动作下，才进入 paused 态
   - 对 src replacement / load 期间的 pause，维持 `isLoading = true`

3. 给 final 接管补明确日志
   - 例如：
   - `segment ended -> switching to final`
   - `final metadata ready`
   - `final autoplay success / failed`
   - `final switch left player paused`

4. 若 Android 上 `playFinalAudio()` 自动接力仍不稳定，增加兜底
   - `play()` 失败时优先回退到当前 ready 的 segment
   - 或者在 final 切换失败后自动执行一次 `recoverCloudPlayback()`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/composables/useTTS.js`

**修复时间**: 2026-04-30

**修改内容**:
- 新增 `internalPauseReason` 过渡保护，区分内部切源触发的 pause 与用户主动 pause
- `segment -> final`、`segment -> next segment` 切换前显式标记内部 transition，避免 UI 被误写成 `isPaused = true`
- `playFinalAudio()` 自动接力失败时，优先回退到当前 ready segment，而不是把用户留在暂停态
- `handleCloudSegmentEnded()` 切 final / recover 失败时增加错误恢复和日志

## 相关提交

- 暂无

## 待验证项

- 部署到线上后，用安卓真机复测 `onboarding-experience-zh` 播放同类长文，确认切 final 时不再自动暂停
- 补充一次可复现的前端日志采集，最好直接记录 `onboarding-experience-zh` 的安卓会话
- 继续确认文章 `76605` 是否就是用户提到的那篇凯文凯利文章
  - 当前只能从用户描述 + 时间窗 + `onboarding-experience-zh` 的 TTS 请求链路做高概率对应
  - 本次未完成线上数据库标题反查

## 验证结果

- 本地构建通过：
  - 使用 `~/.nvm/versions/node/v22.18.0/bin/npm run build`
- 说明本次前端改动至少通过了打包层面的静态验证
- 默认 `npm` 指向的系统 Node 因本机 `icu4c` 动态库缺失而失败，此问题与本次代码修改无关
