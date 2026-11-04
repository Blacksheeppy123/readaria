# TTS 播放速率在新音频加载后被重置

## 问题描述

用户在 TTS 播放器中设置了播放速率（如 1.5x），但切换到新文章播放时，速率又恢复成了默认的 1.0x。

## 原因定位

### 根本原因
浏览器在改变 Audio 元素的 `src` 属性或调用 `load()` 方法后，会将 `playbackRate` 重置为默认值 `1.0`。代码虽然在 `ensureAudioInstance()` 中设置了 playbackRate，但在设置音频源后没有重新设置，导致播放速率丢失。

### 问题区分
- ✅ **设置持久化**：`playerStore.saveSettings()` 和 `restoreProgress()` 已正确持久化 `playbackRate` 到 localStorage
- ❌ **新音频启动时重新应用**：设置新音频 src 后未重新应用 playbackRate，导致浏览器重置为 1.0

### 具体流程问题

1. **播放流程**（以 `playKokoroAudio` 为例）：
   - 调用 `ensureAudioInstance()` → 设置 `globalAudio.value.playbackRate = 1.5`
   - 设置 `globalAudio.value.src = audioUrl` → **浏览器重置 playbackRate 为 1.0**
   - 调用 `globalAudio.value.play()` → 以 1.0x 速率播放

2. **受影响的函数**：
   - `playKokoroAudio()` (line 855-871)
   - `playCloudAudio()` (line 876-895)
   - `playSegmentByTime()` (line 529-577)
   - `playFinalAudio()` (line 579-612)

### 相关代码位置

- `frontend/src/composables/useTTS.js`:
  - Line 165: `ensureAudioInstance()` 中设置 playbackRate
  - Line 858: `playKokoroAudio` 中设置 src
  - Line 884: `playCloudAudio` 中设置 src
  - Line 553: `playSegmentByTime` 中设置 src 并调用 load()
  - Line 591: `playFinalAudio` 中设置 src 并调用 load()

## 修复方案

在设置音频源（`src`）和/或调用 `load()` 之后，重新设置 playbackRate。

### 修复代码示例

```javascript
// playKokoroAudio 修复
const playKokoroAudio = async (audioUrl, duration) => {
  ensureAudioInstance()

  // 设置音频源
  globalAudio.value.src = audioUrl
  currentAudioUrl.value = audioUrl

  // ✅ 关键修复：重新设置播放速率（浏览器改变 src 后可能重置 playbackRate）
  globalAudio.value.playbackRate = playbackRate.value

  // ... 后续代码
}
```

### 修复的函数

1. `playKokoroAudio()` - 在设置 src 后添加 playbackRate 设置
2. `playCloudAudio()` - 在设置 src 后添加 playbackRate 设置
3. `playSegmentByTime()` - 在调用 load() 后添加 playbackRate 设置
4. `playFinalAudio()` - 在调用 load() 后添加 playbackRate 设置

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## Review 评估与决策

### 问题 1：文档标题和根因表述不够准确
**Codex 意见**：标题应改为"播放速率在新音频加载后被重置"，并区分设置持久化和新音频重新应用两个层面。

**决策**：✅ 接受 - 已更新文档标题和根因描述，明确区分：
- 设置持久化：`playerStore.saveSettings()` / `restoreProgress()` 已正确工作
- 实际修复点：设置新音频 src 后需重新应用 playbackRate

### 问题 2：测试验证项缺失
**Codex 意见**：建议补充测试用例验证各播放路径。

**决策**：🔄 修改后接受 - 测试验证是必需的，但目前无法构建可执行的自动化测试。已在下方补充测试验证清单，后续需手动验证各场景。

## 测试验证清单

### 必测场景
- [ ] 1. 将播放速率设为 1.5x，切换到下一篇文章后仍保持 1.5x
- [ ] 2. 页面刷新/重新进入后，从已保存设置恢复为 1.5x
- [ ] 3. 分段播放模式下 seek/续播后，速率仍保持正确
- [ ] 4. final audio 模式下速率保持正确

### 覆盖路径
- [ ] `playKokoroAudio()` - Kokoro 本地合成
- [ ] `playCloudAudio()` - 云端音频（非分段）
- [ ] `playSegmentByTime()` - 云端分段播放
- [ ] `playFinalAudio()` - 云端完整音频

## 修复详情

**修复文件**: `frontend/src/composables/useTTS.js`

**修复时间**: 2026-04-12

**修改内容**:
- 在 `playKokoroAudio` 函数中，设置 src 后添加 `globalAudio.value.playbackRate = playbackRate.value`
- 在 `playCloudAudio` 函数中，设置 src 后添加 `globalAudio.value.playbackRate = playbackRate.value`
- 在 `playSegmentByTime` 函数中，调用 load() 后添加 `globalAudio.value.playbackRate = playbackRate.value`
- 在 `playFinalAudio` 函数中，调用 load() 后添加 `globalAudio.value.playbackRate = playbackRate.value`

## Summary

- **接受**：1 项（文档标题和根因表述修正）
- **修改后接受**：1 项（测试验证项 - 补充清单待手动验证）

**关键改进**：
1. 澄清了问题的本质：不是设置没保存，而是新音频加载后浏览器重置了 playbackRate
2. 明确了修复点：在设置 src/load() 后重新应用 playbackRate

**后续行动**：
- 待部署后手动验证测试清单中的各场景

## Review意见（2026-04-12 Codex）

### 1. 文档标题和根因表述不够准确，容易把问题带偏

- 级别: `p1`
- 问题:
  - 当前文档标题和描述强调“播放速率设置不保存”，但 `playerStore` 里其实已经有 `saveSettings()` / `restoreProgress()` 来持久化 `playbackRate`。
  - 真正的问题不是“没保存”，而是“新音频加载后浏览器把 Audio 的 `playbackRate` 重置了，而代码没有重新应用已保存的值”。
- 建议:
  - 建议把文档标题和根因改成“播放速率在新音频加载后被重置”或类似描述；
  - 在文档中明确区分：
    - 设置持久化：已存在
    - 新音频启动时重新应用设置：这里才是实际修复点

### 2. 测试验证项缺失，暂时无法判断修复是否完整覆盖所有播放路径

- 级别: `p2`
- 问题:
  - 当前文档还未完成 `测试验证`，同时没有列出各播放路径的验证结果。
  - 这次修改涉及 `playKokoroAudio`、`playCloudAudio`、`playSegmentByTime`、`playFinalAudio` 四条路径，最好分别确认。
- 建议:
  - 补充以下最小验证用例：
    1. 将播放速率设为 `1.5x`，切换到下一篇文章后仍保持 `1.5x`。
    2. 页面刷新/重新进入后，从已保存设置恢复为 `1.5x`。
    3. 分段播放与 final audio 模式下 seek/续播后，速率仍保持正确。

## Re-review（2026-04-12 Codex）

### 复审结论

- 本轮没有发现新的明显问题。
- 上一轮 review 提到的标题与根因表述偏差，已经被正确吸收进主文档。
- 当前剩余风险主要是验证尚未执行，结论仍应以实际手动测试结果为准。
