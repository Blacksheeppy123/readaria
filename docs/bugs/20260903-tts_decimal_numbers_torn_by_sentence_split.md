# TTS 朗读时小数被撕裂成两段（先读整数、停顿、再读小数部分）

## 问题描述

- **功能**：文章 TTS 朗读（Azure Speech，稳定播放路径）
- **用户操作**：播放 2026-09-03 路透早报等含小数的中文财经文章
- **实际表现**：所有小数（百分比 `0.56%`、指数点位 `295.01点`、汇率 `1.1587美元` 等）都被拆读——先读小数点前的整数部分、停顿、再读小数部分，而不是"x点x"。例如 `2.25%` 被读成"二百分之二十五"
- **预期表现**：`0.56%` 读作"百分之零点五六"，`295.01点` 读作"二百九十五点零一点"

## 原因定位

### 根本原因（两层）

**根因 1（主因，撕裂）：`split_sentences` 把小数点当句号切分**

[tts_stable_playback.py](backend/services/tts_stable_playback.py) `split_sentences()` 的切分正则 `(?<=[。！？!?\.])` 包含 ASCII 句点 `.`，会把 `295.01` 从中间撕开成 `295.` 和 `01…` 两个 unit；随后分段组合用 `" ".join` 在断口插入空格，得到 `"295. 01"`。TTS 引擎把 `295.` 末尾的点视为句号（整数+停顿），`01` 作为新句开头单独朗读。

**该问题自稳定播放（V2 分段）上线即存在**，影响所有 provider 的文章朗读路径。9 月 2 日用户反馈的"x.x% 把小数点当句号读"也是同一根因（当日修复只针对 `x.x%` 加 say-as，且由于撕裂后插入了空格，`(\d+\.\d+)%` 正则在该路径根本匹配不到，修复未生效）。

**根因 2（次因，say-as 副作用）：say-as number 会把 % 拆成"百分号"**

9 月 2 日上线的 `_apply_say_as`（`<say-as interpret-as="number">0.56</say-as>%`）经 STT 回环验证，会让 % 与数字脱离关系，读成"零点五六百分号"（新老音色均如此）；而 Flash 音色对裸文本 `0.56%` 本来就能正确读作"百分之零点五六"。say-as 方案方向错误，予以移除。

### 证据链（TTS→STT 回环，Azure 语音识别反向验证实际朗读内容）

- 线上实际音频（article 219810，9 段）STT：`上涨295。零1点涨幅零56%，报53061 89点`、`维持政策利率在200分之25不变`、`中签率为00245531五百，分号` —— 全量撕裂
- 隔离句子对照实验：裸文本 `0.56%` → 正确；say-as → `0.56百分号`；word boundary 事件确认撕裂处存在停顿
- 管线逐层比对：同一句话本地直发 Azure 朗读正确 → 差异只在生产路径的 `split_sentences` + `" ".join` 层

### 相关代码位置

- `backend/services/tts_stable_playback.py` `split_sentences()`（根因 1，切分正则）
- `backend/services/tts_stable_playback.py` 分段组合处 `" ".join(current_units)`（断口插入空格）
- `backend/nlp/azure_speech.py` `_apply_say_as()` / `_build_ssml()`（根因 2）

## 修复方案

1. `split_sentences` 切分前用哨兵字符（`\x01`）保护 `数字.数字` 中的小数点，切分后恢复。句读 `.`（前后非数字）仍正常作为边界
2. 移除 `_apply_say_as`，`_build_ssml` 恢复纯 XML 转义（数字裸文本直发）
3. 缓存 key 版本 bump `azure-speech-v2` → `azure-speech-v3`，使已生成的撕裂音频整体失效（文件缓存 + 预生成段落缓存 + DB tts_cache 经由 v2 引入的 cache_key 一致性校验自动失效旧记录）

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `backend/services/tts_stable_playback.py`（split_sentences 小数点保护）
- `backend/nlp/azure_speech.py`（移除 say-as、model bump v3）
- `tests/api/test_tts_stable_playback_manager.py`（+3 个切分回归测试）
- `tests/backend/nlp/test_azure_speech.py`（-6 个 say-as 测试，+1 个裸文本回归测试，缓存 key v3）
- `scripts/verify_decimal_fix_e2e.py` / `scripts/stt_production_segments.py` / `scripts/debug_tts_stt_roundtrip.py`（STT 回环验证工具）

**修复时间**: 2026-09-03

**验证**:
- 单元测试 33/33 通过（TDD：4 个回归测试先 RED 后 GREEN）
- 端到端 STT 回环：路透早报 5 个此前误读的真实句子（`295.01点`/`0.56%`/`2.25%`/`0.02455315%`/`1.1587美元` 等）经完整生产管线合成后识别全部正确
- 线上验证：部署 `3f4bbc1` 后以 `segv2|azure-speech-v3|...` key 重新生成 article 219810（9/9 段），STT 复核生产音频：
  - `上涨295.01点，涨幅0.56%，报53061.89点`（此前 `295。零1点涨幅零56%，报53061 89点` → 现 `上涨295.01点，涨幅0.56%，报53061.89点 ✓
- `2.25%`（此前 `二百分之二十五` → 现正确读作"百分之二点二五" ✓
- 全线段（9/9）STT 复核全部正确，日志无 TTS 相关 ERROR

## 相关提交

- `3f4bbc1` fix(tts): 修复小数被 split_sentences 撕裂朗读，移除 say-as 副作用
- `1f10b60` feat(tts): Azure Speech 零费用质量升级（前一日，本 bug 的 say-as 副作用引入 commit，已在本修复中回退 say-as

## Code Review (2026-09-03)

### Review notes (Codex)

#### P1: 缓存版本只失效 Azure Speech，和“所有 provider”影响范围不一致

稳定播放缓存 key 由 `StableTtsPlaybackManager.build_cache_key()` 直接委托给
provider 的 `_get_cache_key()` 生成。此次只有 `AzureSpeechService.model` 从 v2 升到
v3；`OpenAISpeechService` 和 `GoogleSpeechService` 对同一 article_id 仍生成与修复前
相同的 key。它们会继续命中旧的 manifest / final 音频 / `tts_cache` 记录，用户仍会听到
被撕裂的小数，直到缓存被人工清理或文章 ID 改变。应在稳定播放层引入独立的分段算法版本
到 cache key，或同步版本化所有受该分段逻辑影响的 provider key，并覆盖旧缓存命中场景。

#### P2: `数字.数字` 保护不涵盖无前导零小数

`_DECIMAL_DOT_RE = r"(\d)\.(\d)"` 不匹配 `.5` / `-.5`。这类合法数字仍会被切成
`"."` 与 `"5"` 两个 unit。建议将小数判断改为同时支持 `\d+\.\d+` 和 `\.\d+`，并补充
`.5%` 的回归测试。多段版本号 `1.2.3` 也仍会在第二个点切开，是否需要保持完整应由产品
语义明确后再处理。

#### P2: 固定长度兜底切块仍可能从小数中间切断

句子级哨兵保护后，超长且无标点的 unit 仍会进入 `_chunk_text_by_length()`，其固定
120 字边界可能落在 `1.23` 内部，随后稳定播放层用空格拼接，仍会产生同样的停顿误读。

### Decisions

#### P1: 缓存版本只失效 Azure Speech

✅ 接受 - 这是发布后仍可复现的行为问题，不是理论边界。修复应让稳定播放的缓存身份包含
分段算法版本，确保所有 provider 的既有受影响音频均重新生成。

  - decision and reason(by claude): **Fixed** — 已验证属实：`build_cache_key` 直接委托 provider
    `_get_cache_key`，OpenAI fallback（Azure 初始化失败时）和 7 月前 OpenAI 时代的旧缓存确实
    不受 AzureSpeechService.model bump 影响。修复：稳定播放层新增 `SEGMENT_ALGO_VERSION = "segv2"`，
    `build_cache_key` 返回 `segv2|<provider_key>`（单点生效，DB 读写同函数已确认一致：
    upsert 于 :863 使用同一 cache_key）。新增 `test_build_cache_key_includes_segment_algo_version`；
    既有 DB 匹配测试改用 `build_cache_key` 计算期望值。

#### P2: 无前导零小数未保护

✅ 接受 - `.5` 是常见且合法的数值写法，扩展正则和增加一个回归用例的复杂度很低。

  - decision and reason(by claude): **Fixed（方案简化）** — 未按建议拆两种形态，而是把保护
    正则从 `(\d)\.(\d)` 改为 `\.(?=\d)`（点后紧跟数字即保护），一个正则同时覆盖
    `0.5` / `.5` / `1.2.3` / `2026.09.02`（多段点也自然保持完整，无需另作产品决策）；
    句读 `". "`（点后空格）不受影响。新增 `test_split_sentences_preserves_leading_dot_decimals`
    与 `test_split_sentences_preserves_multi_dot_versions_and_dates`。

#### P2: 固定长度兜底切块仍可能从小数中间切断

✅ 接受 - 这是同一用户可见故障在长句兜底路径的真实复现，修复成本低于继续依赖句子级保护。

  - decision and reason(by claude): **Fixed** — `_chunk_text_by_length` 现在检测切块边界是否落在
    含小数点的数字 token 内；优先把 token 整体放入下一块（若 token 位于块首则放入当前块），
    并增加 `test_split_sentences_preserves_decimal_across_fixed_chunk_boundary` 回归测试。

### Summary

- 接受：3 项
- 拒绝：0 项
- 修改后接受：0 项

主要改进：缓存失效范围需与稳定播放共享的分段逻辑一致；小数保护覆盖无前导零写法及固定长度兜底切块。
