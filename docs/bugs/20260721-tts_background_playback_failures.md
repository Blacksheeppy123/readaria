# TTS background auto-advance fails on iOS & abnormal pause never resumes (iOS/Android)

## 问题描述

用户反馈两类播放控制问题（2026-07-21）：

1. **iOS 后台不连播**：播放完一篇后，如果 app 不在前台（锁屏/切后台），不会自动播放下一篇；重新打开 app 后才会继续。
2. **异常暂停不恢复**（iOS + Android）：播放途中异常暂停后不会自动恢复，需要手动干预。

与 `20260602-tts_midplay_stops_on_mobile.md` 的关系：上一轮修复的是 **app 重启后** 的恢复（SW reload、metadata 补全、resume intent），本轮问题发生在 **同一会话内** 的后台切换与中断恢复链路，此前从未被覆盖。

## 原因定位

### 根本原因

两个 bug 共享同一个根因：**代码把"曲目切换"和"暂停恢复"当作普通的异步前端逻辑处理，但 iOS（以及部分 Android 场景）会在音频停止的瞬间开始挂起 JS 进程**。`ended` 事件触发后，任何非平凡的异步链都会在进程挂起时冻结。

#### Bug #1：iOS 后台不连播 —— ended → play() 链路太长且主动销毁音频会话

`ended` 事件（`useTTS.js:413`）触发后的完整链路：

1. `playerStore.onPlaybackEnd()` → `playNext()` → `playArticle()` → `newTts.loadAudio()`
2. `loadAudio()` 第一步就调用 `cleanupAudio()`：`pause()` + `src=''` + `load()`（`useTTS.js:314-330`）—— **主动拆除 iOS 音频会话**，等于告诉系统"播放彻底结束"
3. `checkCloudCache()` —— HTTP #1（`ttsManager.js:209`）
4. `startTtsPrepare()` —— HTTP #2（`useTTS.js:1168`）
5. `fetchCloudPrepareStatus()` —— HTTP #3（`useTTS.js:1074`）
6. `getTtsPlayUrl()` —— HTTP #4（`useTTS.js:927`）
7. `waitForAudioReady()` —— 等待 `loadedmetadata`/`canplay` 事件 + 15s `setTimeout` 兜底（`useTTS.js:635-703`）
8. 最后才 `play()`（`useTTS.js:973`）

若下一篇未完成服务端生成，还会进入 `waitForCloudPlayable` 的 **`setTimeout(250-1500ms)` 轮询循环**（`useTTS.js:1117-1119`）。

iOS 现实约束：

- 音频播放期间 iOS 保持 PWA web 进程存活，`ended` 事件能正常派发；
- 音频一停（且 `cleanupAudio` 主动释放会话），iOS 立即开始挂起倒计时（无文档保证的短暂宽限期）；
- 进程挂起后 JS 线程冻结：fetch 回调、`setTimeout`、媒体事件派发全部停止 → 链条死在中途；
- 用户重新打开 app 时 JS 恢复，被冻结的 promise 链继续执行 —— 表现为"回到前台才开始放下一篇"。

分段模式（segmented）更严重：每个分段边界（几分钟一次）都有一条类似的异步链（`handleCloudSegmentEnded` → 状态请求 → URL 请求 → `waitForAudioReady` → `play()`，`useTTS.js:1123-1159`），每个边界都是后台死亡点。

#### Bug #2：异常暂停不恢复 —— 四个独立缺口

**A. 网络断流完全无处理。** 整个播放栈没有任何 `stalled`/`waiting`/`suspend` 监听器。连接中断时：Chrome 触发 `stalled` 后通常（不总是）自行恢复；**iOS Safari 静默断流，网络恢复后也永不续播**。且断流不触发 `pause` 事件，`isPlaying` 保持 `true` —— UI 显示播放中，实际无声，彻底卡死。

**B. iOS 音频会话中断（来电/Siri/闹钟/其他 app）。** 元素收到 `pause` 事件；中断结束时 web 平台**没有任何事件**通知。锁屏播放键走 Media Session handler（`useTTS.js:526-528`），只做 `audio.play()` —— 中断后元素常处于损坏态（需要 `load()` + seek + `play()`），恢复失败只 toast（锁屏上看不见）。

**C. iOS 后台挂起进程后无状态 reconcile。** 热恢复（非冷启动）时什么都不执行：`resumeInterruptedPlayback` 只在 mount 时跑一次（`App.vue:71`），全 app 没有任何 `visibilitychange` 监听。

**D. 僵尸态边界会主动销毁会话。** `pause` 处理器用 `if (currentTime < totalTime) isPaused = true` 推断"未结束"（`useTTS.js:407-409`）。系统暂停恰好落在 `totalTime=0` 或 `currentTime ≈ totalTime` 时，得到 `isPlaying=false, isPaused=false, isLoading=false` 僵尸态；store 的 idle 计数（10 × 100ms）随后调用 `clearInactiveCurrentArticle()` 清空 `currentArticle` 和进度（`playerStore.js:552-568`、`368-378`）—— 一次暂时性系统暂停直接把播放会话**删除**而不是恢复。分段切换链条在后台冻结时同理：永久 `isLoading=true`，无出口。

### 相关代码位置

- `frontend/src/composables/useTTS.js:413-446` — ended 处理器
- `frontend/src/composables/useTTS.js:314-330` — cleanupAudio（拆会话）
- `frontend/src/composables/useTTS.js:635-703` — waitForAudioReady（setTimeout 兜底）
- `frontend/src/composables/useTTS.js:1068-1121` — waitForCloudPlayable（setTimeout 轮询）
- `frontend/src/composables/useTTS.js:395-410` — pause 处理器（僵尸态源头）
- `frontend/src/composables/useTTS.js:511-564` — Media Session（play handler 无韧性）
- `frontend/src/stores/playerStore.js:552-568` — idle 计数误清状态
- `frontend/src/stores/playerStore.js:368-378` — clearInactiveCurrentArticle
- `frontend/src/stores/podcastPlayerStore.js` — 同样的断流/恢复缺口（无连播问题）
- `frontend/src/App.vue:71` — resumeInterruptedPlayback 仅冷启动

## 修复方案

### Fix 1：下一篇预取 + 同步交接（Bug #1，P0）

原则：**曲目 N 结束前把 N+1 所需的一切取到内存；`ended` 处理器的前两个语句必须是同步的 `src=url; play()`。**

1. 播放 N 期间保留现有的服务端预热（play 开始后 5s `preloadNextArticle`）。
2. 剩余 ≤75s 时（timeupdate 驱动）：查 `getTtsPrepareStatus(N+1)`；`final_ready` 则取 `getTtsPlayUrl(N+1)` 并用隐藏预加载 `Audio` 预热字节流；只有分段就绪则预取 segment 0 URL。未就绪则按时间间隔重试（播放中进程存活，timer 可用）。
3. `ended` 时若预取命中且 playlist 下一篇 id 匹配：**同一 audio 元素直接换 src + `play()`**（不走 `cleanupAudio`、不走 `loadAudio`、不等 `waitForAudioReady`），立即更新 Media Session metadata；随后的 store 簿记（index 前进、完成上报、状态保存、N+2 预热）全部异步进行。
4. 预取未命中 → 回退现有链路（不劣于现状）。
5. 分段边界同样：本地偏移为 0 的顺序切换跳过 `waitForAudioReady`，prefetch URL 直接换 src + `play()`。
6. 切换关键路径禁止 `setTimeout`（后台 timer 冻结）。

### Fix 2：断流看门狗 + 韧性恢复（Bug #2，P0）

1. 新增 `stalled`/`waiting`/`canplay`/`playing` 监听 + **无进展看门狗**（周期检查 currentTime 是否前进）：元素自认为在播但 ~10s 无进展且在线 → 复用 `recoverCloudPlayback()` 重载续播；`canplay` 到达且非手动暂停 → 自动续播。
2. 非预期 `pause`（`manualPause=false`、非内部切换、`!audio.ended`）：前台时立即 + 2s 后各尝试一次自动恢复；后台时不自动恢复（避免与其他 app 抢音频焦点），交给回前台 reconcile。
3. Media Session `play` handler 韧性化：元素损坏（`error`/`readyState===0`）时重载 src + 回到断点 + `play()`，而非裸 `play()`；手动恢复重置恢复次数预算。
4. `visibilitychange`（回前台）reconcile：意图在播但元素已停 → 自动恢复；`manualPause` 和"自然结束"标记阻止误恢复。`online` 事件同样触发恢复。
5. 僵尸态修复：`pause` 分类改用 `audio.ended` 属性；store idle 清理在中途（`0 < currentTime < totalTime`）改为标记 `isPaused=true` 而非清空会话。
6. TTS 路径同步 `navigator.mediaSession.playbackState`（podcast store 已有）。
7. 新增 PostHog 事件：`audio_stall`、`audio_auto_resume`、`audio_track_handoff`（success/failure），用于线上量化修复效果。
8. `podcastPlayerStore` 同步加固（无连播问题，但断流/恢复缺口相同）。

### 平台限制说明（不遮掩）

- iOS 对 `ended` 后的后台 JS 无任何 API 保证，同步交接方案可将其变为小概率失败，但 web 代码无法做到 100%。彻底方案只有原生壳（Capacitor + 原生播放器），列为长期选项。
- Android Chrome 后台媒体播放期间 JS 基本存活，Fix 1 收益较小；Fix 2 看门狗是主要收益。OEM 电池杀进程无法从代码解决，只能优雅恢复。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（自动化部分；真机后台场景需用户实测 + PostHog 量化观察）

## 修复记录

**修复文件**:
- `frontend/src/composables/useTTS.js`（主体：预取器、快速交接、看门狗、韧性恢复、生命周期 reconcile）
- `frontend/src/stores/playerStore.js`（onNextTrackHandoff 簿记、idle 收口护栏、resumePlayback 路由）
- `frontend/src/stores/podcastPlayerStore.js`（断流/中断恢复加固）
- `frontend/src/services/tts/playbackRecoveryPolicy.js`（新增纯函数决策模块）
- `frontend/src/utils/analytics.js`（audio_stall / audio_auto_resume / audio_track_handoff 事件）
- `frontend/tests/unit/playbackRecoveryPolicy.test.mjs`（新增 20 个单元测试）

**修复时间**: 2026-07-21

**修改内容**:
- Fix 1（iOS 后台连播）：当前曲目剩余 ≤75s 时客户端预取下一篇签名 URL + 预热字节；`ended` 事件内同步换 `src` + `play()`（零网络请求、不拆音频会话、不走 cleanupAudio/loadAudio），store 簿记（`onNextTrackHandoff`）异步跟进；预取未命中回退原链路。分段边界顺序切换（offset=0）跳过 `waitForAudioReady`；分段播放中 final 就绪后立即预热整篇字节。
- Fix 2（异常暂停恢复）：`stalled`/`waiting`/`canplay`/`playing` 监听 + 无进展看门狗（~10s 进度冻结且在线 → `recoverCloudPlayback`，预算 2 次后落为可恢复暂停）；非预期暂停前台 0s/2s 两次自动恢复（后台不恢复避免抢焦点）；Media Session play 与 store 恢复入口走韧性恢复（元素损坏先重载再断点续播）；`visibilitychange` 回前台 + `online` 事件 reconcile；`pause` 分类改用 `audio.ended`；store idle 收口在中途改为标记可恢复暂停且保留同步 interval；TTS 路径补 `mediaSession.playbackState` 同步。
- 护栏：`manualPause`（用户暂停不恢复）、`suppressAutoResume`（自然结束/显式停止不恢复）、`playbackStartedThisSource`（初始加载 canplay 不触发自动恢复，避免与 loadAudio 的 play() 竞争 AbortError）。
- Codex review 发现并修复 3 个问题：Pinia 代理 ref 已解包导致预取/交接永不执行（P0）、预取期间列表变更的过期缓存竞态（P1）、podcast 前台异常暂停未覆盖（P1）。审核记录：`codex-review-notes/[review]tts-background-playback-audit-20260721.md`。
- 验证：`npm run build` 通过；`node --test tests/unit/` 22/22 通过。
- 线上验证（2026-07-21，commit `0ca95bd`，Deploy Frontend workflow #29823135455 成功）：
  - 生产 bundle `assets/index-4Ur4wWag.js` 已包含全部新代码标记（Fast handoff / watchdog / reconcile / prefetch / audio_track_handoff 各 1 处命中）。
  - Playwright 移动视口（375×812）加载 readaria.com 首页与 /login：console 0 错误 0 警告，App mount 路径（含新 useTTS 实例化）无 TDZ/引用错误。
  - 真机后台连播/断流恢复无法自动化验证（需要登录态 + 物理设备后台），已通过 PostHog 事件 `audio_track_handoff`(success/failure)、`audio_stall`、`audio_auto_resume` 建立线上量化通道，需用户实测观察。

## 相关提交

- `0ca95bd` fix(tts): iOS background auto-advance and abnormal-pause recovery
