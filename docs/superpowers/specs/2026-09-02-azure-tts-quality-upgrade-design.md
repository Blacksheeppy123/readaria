# Azure TTS 零费用质量升级设计

**日期**: 2026-09-02
**状态**: 已获用户批准（2026-09-02）
**约束**: 保持零费用（Azure AI Speech F0 免费额度，50 万字符/月）

## 背景与问题

生产环境 TTS 使用 `TTS_PROVIDER=azure_speech`（Azure AI Speech F0，eastasia），存在两个用户反馈问题：

1. **音质差距**：与此前 OpenAI TTS 相比"发闷/不清晰、机械/无感情"
   - 根因 A：输出格式为 `Audio16Khz32KBitRateMonoMp3`（电话级码率）
   - 根因 B：使用老一代音色 `zh-CN-XiaoxiaoNeural` / `zh-CN-YunjianNeural`
2. **小数点误读**：`x.x%` 中的小数点被当作句号朗读（如 "3.5%" 读成 "3。5%"）
   - 根因：SSML 为纯文本转义，未对数字使用 `<say-as interpret-as="number">` 标记

## 已验证事实（2026-09-02 实测）

- eastasia 区域 F0 key 可直接使用新一代音色：`zh-CN-Xiaoxiao:DragonHDFlashLatestNeural`、`zh-CN-Yunyi:DragonHDFlashLatestNeural`、`zh-CN-Mei:MAI-Voice-2-Flash` 等（VoiceType=`Neural`，按标准神经语音计入免费额度，非 premium NeuralHD 计费）
- 英文对应：`en-US-Tiana:DragonHDFlashLatestNeural`（女）、`en-US-Jimmie:DragonHDFlashLatestNeural`（男）
- `<say-as interpret-as="number">` 对中英文音色均可正常合成
- Azure 按字符计费，输出码率（16k32 → 48k96）不影响费用；副作用仅为缓存文件体积约 3 倍（现有 cache_cleaner：14 天过期 + 10GB 上限自动管理）
- Flash 音色 StyleList 不含 `newscast`，故 express-as 风格默认不启用
- 缓存 key 经由 `AzureSpeechService._get_cache_key` 单点生成（文件缓存、`tts_stable_playback` 预生成段落缓存、播客缓存共用），`tts_cache` 表无 DB 查询依赖 model 字段

## 设计（方案 A：配置级全面升级）

改动集中在 `backend/nlp/azure_speech.py` + `core/config/settings.py` + 测试。`podcast_generator.py` 走同一 voice map，自动受益。

### 1. 输出码率升级

- `Audio16Khz32KBitRateMonoMp3` → `Audio48Khz96KBitRateMonoMp3`
- 提取为配置项 `azure_speech_output_format: str = "Audio48Khz96KBitRateMonoMp3"`（settings.py），azure_speech.py 通过 `getattr(SpeechSynthesisOutputFormat, name)` 解析

### 2. VOICE_MAP 换新一代音色

| 逻辑名 | 现在 | 升级后 |
|---|---|---|
| nova/shimmer/alloy/default（女） | zh-CN-XiaoxiaoNeural | zh-CN-Xiaoxiao:DragonHDFlashLatestNeural |
| echo/fable/onyx（男） | zh-CN-YunjianNeural | zh-CN-Yunyi:DragonHDFlashLatestNeural |
| 英文女 | en-US-AriaNeural | en-US-Tiana:DragonHDFlashLatestNeural |
| 英文男 | en-US-GuyNeural | en-US-Jimmie:DragonHDFlashLatestNeural |

`azure_speech_tts_voice` 默认值同步改为 `zh-CN-Xiaoxiao:DragonHDFlashLatestNeural`。

### 3. 小数点修复：say-as 预处理

新增 `_apply_say_as(text) -> str`：

- 正则 `(\d+\.\d+)%` → 数字部分包裹 `<say-as interpret-as="number">...</say-as>`
- 实现顺序：按正则切分文本 → 纯文本段 XML 转义 → say-as 段内容转义后包标签 → 拼接（禁止先转义后插标签）
- 范围严格限定"小数+%"：`1024.8亿元`（不带 %）、`2026.09.02`（日期）不处理，避免误伤
- 在 `_build_ssml` 中调用，对所有分段生效

### 4. 缓存 key 版本化

`self.model`：`"azure-speech"` → `"azure-speech-v2"`，一次性失效全部旧缓存（文件缓存 + 预生成段落缓存 + 播客缓存）。旧文件由 cache_cleaner 自动清理，无需手工操作。

### 5. Settings 新增

- `azure_speech_output_format: str = "Audio48Khz96KBitRateMonoMp3"`
- `azure_speech_tts_voice` 默认值改为 `zh-CN-Xiaoxiao:DragonHDFlashLatestNeural`

### 6. 测试

- 更新 `tests/backend/nlp/test_azure_speech.py`：音色断言、输出格式 mock、默认值断言
- 新增 `_apply_say_as` 单测：
  - `增长了3.5%` → 数字包裹 say-as
  - `1024.8亿元`（无 %）→ 不处理
  - `2026.09.02`（日期）→ 不处理
  - 含 XML 特殊字符（`<`、`&`）文本仍正确转义且标签不被转义
- 流程：`make test-local` → CI → 部署 → 线上挑含 x.x% 文章试听

## 不做（YAGNI）

- express-as 风格默认不启用（Flash StyleList 无 newscast，留作后续可调项）
- "百分之三点五"文本改写方案（say-as 更通用、语言中立）
- edge-tts 非官方库（ToS 风险）
- 英文 en-US 之外的第三方音色/方言音色

## 成本与回滚

- 费用 $0：同一 F0 资源、同一 50 万字符/月额度，字符用量不变
- 回滚 = revert commit（音色可通过 `AZURE_SPEECH_TTS_VOICE` env 单独覆盖）

## 验证样本

调研样本已生成于 `audio/tts_samples/`（基线 a1、码率 b1、say-as 修复 c1、新音色 e1-e5、风格 f1），用户已听并批准换用 DragonHD Flash。
