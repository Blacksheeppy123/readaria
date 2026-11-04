# Android TTS 中途播放中断

## 问题描述

用户反馈：Android 播放文章时，播放一段时间后自动中断；中午时段较容易复现，今天再次发生。预期是在网络短暂波动、PWA 生命周期变化或 TTS 分段切换后自动继续播放。

## 当前定位

### 已确认的历史关联

- `docs/bugs/20260602-tts_midplay_stops_on_mobile.md` 记录过同一账号、Android Chrome、中午时段的中途停止。
- 该次 13:48 左右出现前端 `Mounting app...` 和 `refreshUser timeout`，与播放在 82% 处停止吻合；后端 TTS 文件返回完整，没有证据支持音频生成失败。
- `docs/bugs/20260721-tts_background_playback_failures.md` 后续加入了断流监听、看门狗和恢复链路，但真机 Android 场景仍未完成线上验证。

### 2026-10-22 这次复现的证据

- 设备 UA 是 Pixel/Android Chrome，PWA，前端在 **13:26:21** 启动。
- 文章 ID 是 **280151**。13:29:51 开始云端实时 TTS，13:30–13:32 连续成功播放 segment 0–3；每个 segment 的 HTTP 响应都是 200，音频文件完整返回。
- 后端在 13:39:25 完成了该文章的分段生成，记录 `first_playable_ready_ms=10503`。没有看到 TTS 生成失败或播放文件 4xx/5xx。
- 13:32:55 后，客户端到 13:49:35 之间没有新的 TTS 请求，且没有新的 `Mounting app...`。这排除了“页面在 13:00 左右被整页重载”作为本次直接原因。
- 13:49:35 回到前台后，前端同时出现 `Cloud polling failed: timeout of 180000ms`、`Cloud segment transition failed: Network Error`、`Cloud playback recovery failed`，随后 13:49:36 成功获取 final 播放 URL，13:50:39 完整 MP3 返回 200，并恢复播放。
- 13:40:28 有一条 Sentry uptime 对 API 根路径的 504，但没有对应的 TTS API 5xx；它只能说明当时 API 进程存在短暂响应拥塞，不能直接解释音频文件损坏。

### 当前判断与证据边界

日志确认 **分段边界的异步切换链路发生错误**：当前分段播放完后，需要 JavaScript 发起 `prepare` 状态查询、取下一段或 final URL，再替换 `Audio.src`。13:32:55–13:49:35 的请求空窗、切段错误和回前台恢复事件支持“下一段未及时接上”的判断；现有日志无法精确确定停止时间，也无法区分 Android 后台冻结、网络中断或两者同时发生。回前台后上传了超时与切段错误日志，随后通过 final MP3 恢复。由于日志使用服务器接收时间，不能把错误日志的写入时刻当作设备实际发生时刻。

没有看到本次 TTS 音频生成失败、音频文件 HTTP 错误或权限错误。现有恢复机制能在回前台后恢复，但恢复前的空窗期过长；客户端还在异常态反复执行播放状态同步，造成大量重复日志和请求。

### 可确定的客户端放大因素

`playerStore.syncPlaybackState()` 在请求失败时保留 `pendingPlaybackSync=true`，`finally` 里立即调用强制同步。网络异常时，这会绕过 10 秒节流，连续触发更多失败请求。已改为每次请求前消费 pending 标记，失败后也更新时间节流基准；若请求期间有新状态变化，再按正常节流排队。

## 相关代码位置

- `frontend/src/composables/useTTS.js`：音频事件、看门狗、断点恢复和分段切换。
- `frontend/src/stores/playerStore.js`：播放状态同步、进度保存和恢复意图。
- `frontend/src/services/tts/playbackRecoveryPolicy.js`：异常暂停和看门狗判定。
- `backend/services/tts_stable_playback.py`：分段生成、超时和 manifest 状态。

## 当前限制

生产日志已对齐这次会话。前端日志在后台上传到服务器时使用服务器写入时间，原始客户端事件时间没有写入 `frontend.log`，因此无法精确标出分段结束的秒数，也无法从日志单独证明 Android 系统冻结还是网络中断。反馈中虽然勾选“附加最近日志”，但本次反馈记录里的 `frontend_logs_count=0`；自动上传的独立前端日志仍可用。

## 待补证据

- Android 设备侧的网络连接变化和屏幕/后台状态（现有前端日志没有采集）。
- PostHog 中 `audio_stall`、`audio_auto_resume`、`audio_track_handoff` 事件。

## 修复状态

- [x] 问题记录
- [x] 历史根因对照
- [x] 今天复现的线上日志定位
- [x] 确认分段切换错误；后台冻结与网络中断仍无法细分
- [x] 修复同步失败时的请求风暴
- [ ] Android 真机验证

## 验证与交付

- 播放恢复策略与持久化单元测试：22/22 通过。
- 注入模拟请求与定时器验证同步失败后按 10 秒节流重试，通过。
- `npm run build` 通过；存在 chunk 大小、动态导入与浏览器数据版本警告。
- 修改仅在本地，未部署。同步节流修复减少异常时重复请求，尚不能证明解决此次播放中断。
