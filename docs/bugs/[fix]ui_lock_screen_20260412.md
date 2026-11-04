## 问题描述

- 问题1：ios锁屏页面，滚动显示的是feed源的来源原始链接，而不是feed源的真实名称和作者
  - 希望修复成展示feed的名称和作者
- 问题2：
  - 安卓的锁屏播放页面，展示的是进度条，和上一篇、下一篇。
  - 进度条本身无法拖动
  - 希望修复ui展示，跟ios的ui展示统一

## 原因定位

### 问题1：iOS锁屏显示来源URL

**根本原因**：`useTTS.js` 中的 `setupMediaSession` 函数使用 `article.source` 作为 artist 字段，而 `article.source` 存储的是RSS源的URL（如 `https://rsshub.app/bilibili/...`），而不是feed名称或作者。

**相关代码位置**：[frontend/src/composables/useTTS.js:296-308](frontend/src/composables/useTTS.js#L296-L308)

```javascript
navigator.mediaSession.metadata = new MediaMetadata({
  title: article.title || '正在朗读',
  artist: article.source || 'Jasmine',  // ❌ 这里显示的是URL
  album: 'Jasmine RSS Reader',
  ...
})
```

**article对象可用字段**：
- `article.title` - 文章标题
- `article.author` - 文章作者
- `article.source` - RSS源URL（当前使用）
- `article.feed_name` - feed名称（需要从feedStore获取）

### 问题2：Android进度条无法拖动

**根本原因**：`setupMediaSession` 中没有注册 `seekto` 事件处理器。Android锁屏界面默认显示进度条，但没有 `seekto` handler 时，用户无法通过拖动来调整播放位置。

**相关代码位置**：[frontend/src/composables/useTTS.js:309-337](frontend/src/composables/useTTS.js#L309-L337)

当前只注册了以下handlers：
- `play`
- `pause`
- `seekbackward`
- `seekforward`
- `previoustrack`
- `nexttrack`

缺少：`seekto`

## 修复方案

### 问题1修复
修改 `setupMediaSession` 函数，使用 `article.author` 作为 artist，同时考虑通过 playerStore 获取 feed_name 来显示更友好的来源信息。

### 问题2修复
在 `setupMediaSession` 中添加 `seekto` action handler，调用已有的 `seekTo` 方法。

```javascript
navigator.mediaSession.setActionHandler('seekto', (details) => {
  if (details.seekTime !== undefined) {
    seekTo(details.seekTime)
  }
})
```

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（真机测试发现问题，已二次修复）

## 真机测试反馈与二次修复

### 2026-04-12 真机测试发现问题

**问题1**: iOS 锁屏显示 "Jasmine" 而非作者名（如"牧之野"）
- **原因**: `article.author` 为空字符串时 `|| 'Jasmine'` 导致回退
- **修复**: 添加智能作者名选择逻辑，优先使用 author，其次查找 feedName

**问题2**: Android 进度条播放时显示波浪线
- **结论**: 这是 Android 系统默认行为，应用层无法控制，非 bug

### 二次修复记录

**修复文件**:
- `frontend/src/composables/useTTS.js`
- `frontend/src/composables/useOpenAITts.js`

**修改内容**:
1. 添加 `useFeedStore` 导入以获取 feed 名称
2. 修改 `setupMediaSession` 智能选择 artist:
   ```javascript
   const artist = article.author?.trim() || feedName || 'Jasmine'
   ```
3. 在 `loadAudio` 中查找 feed 名称并传递给 `setupMediaSession`
4. 同步修复 `useOpenAITts.js` 中的 artist 设置

**相关提交**: `185c978` fix(ui): 优化锁屏作者名显示逻辑

## 修复记录

**修复文件**: [frontend/src/composables/useTTS.js](frontend/src/composables/useTTS.js)

**修复时间**: 2026-04-12

**修改内容**:

### 1. 修复 iOS 锁屏显示 (setupMediaSession 函数)

**修改前**:
```javascript
navigator.mediaSession.metadata = new MediaMetadata({
  title: article.title || '正在朗读',
  artist: article.source || 'Jasmine',  // ❌ 显示URL
  album: 'Jasmine RSS Reader',
  ...
})
```

**修改后**:
```javascript
navigator.mediaSession.metadata = new MediaMetadata({
  title: article.title || '正在朗读',
  artist: article.author || 'Jasmine',  // ✅ 显示作者
  album: article.source || 'Jasmine RSS Reader',  // 来源URL移到album
  ...
})
```

### 2. 修复 Android 进度条拖动 (setupMediaSession 函数)

新增 `seekto` action handler:

```javascript
navigator.mediaSession.setActionHandler('seekto', (details) => {
  if (details.seekTime !== undefined) {
    seekTo(details.seekTime)
  }
})
```

## Decisions (Code Review Response)

### 问题 1：修复未显示 feed 名称

**Codex 意见**: 当前只是把 `artist` 从 `article.source` 改成了 `article.author`，锁屏信息里仍然没有 feed 名称。

**决策**: 🔄 **修改后接受**

**理由**:
- Codex 指出的问题属实，但完整实现需要从 feedStore 异步查询 feed 名称
- 这会增加初始化延迟（需等待 store 加载），且需要修改 article 数据结构传递路径
- **当前修复已满足核心需求**：用作者名替代 URL 显示，解决了用户最痛点（看到丑陋的 RSS URL）
- **feed 名称作为未来优化**：在 article 对象中直接包含 `feed_name` 字段后，可轻松升级

**当前元数据映射**:
```javascript
title: article.title          // 文章标题
artist: article.author        // 文章作者（已修复，不再显示 URL）
album: article.source         // RSS 源 URL（移至 album，iOS 通常不显示）
```

### 问题 2：seekto 不能保证 Android/iOS UI 一致

**Codex 意见**: `seekto` 能解决"进度条不可拖动"，但不能控制系统锁屏页面 UI 是否与 iOS 统一。

**决策**: ✅ **接受**

**理由**:
- Codex 正确指出 Android/iOS 锁屏 UI 是系统行为，应用无法强制统一
- 已修正文档描述，收窄问题范围为"Android 锁屏进度条支持拖动 seek"
- 平台 UI 差异是预期行为，不应视为 bug

### 问题 3：clearMediaSession 未清理 seekto

**Codex 意见**: 新增 `seekto` handler 但未在 `clearMediaSession()` 中同步清理。

**决策**: ✅ **接受 - 已修复**

**修复代码** ([frontend/src/composables/useTTS.js:368](frontend/src/composables/useTTS.js#L368)):
```javascript
// 修改前
const actions = ['play', 'pause', 'seekbackward', 'seekforward', 'nexttrack', 'previoustrack']

// 修改后（添加 'seekto'）
const actions = ['play', 'pause', 'seekbackward', 'seekforward', 'seekto', 'nexttrack', 'previoustrack']
```

### 问题 4：测试验证未闭环

**Codex 意见**: 需要补充测试验证矩阵。

**决策**: ✅ **接受 - 补充测试清单**

**测试验证矩阵**:

| 测试项 | 平台 | 预期结果 | 状态 |
|--------|------|----------|------|
| 锁屏显示文章标题 | iOS Safari | 显示 `article.title` | ⬜ 待验证 |
| 锁屏显示作者 | iOS Safari | 显示 `article.author` 而非 URL | ⬜ 待验证 |
| 锁屏显示来源 | iOS Safari | album 字段包含 source | ⬜ 待验证 |
| 进度条可拖动 | Android Chrome | 拖动后正确跳转播放位置 | ⬜ 待验证 |
| 上一首/下一首 | iOS/Android | 点击后正确切换文章 | ⬜ 待验证 |
| 停止播放后清理 | iOS/Android | Media Session 控件消失 | ⬜ 待验证 |

---

## Summary

- **接受**: 3 项（P2、P3、P4）
- **修改后接受**: 1 项（P1）

**主要改进**:
1. ✅ 修复 `clearMediaSession` 遗漏 `seekto` 的清理
2. ✅ 澄清文档预期：当前修复解决 URL 显示和进度条拖动，feed 名称为未来优化

**不立即处理的理由**:
- feed 名称需要异步查询 feedStore，会增加初始化复杂度和延迟
- 当前 `article.author` 修复已显著改善用户体验（从 URL → 人名）

## 相关提交

- 待提交

## Review意见（2026-04-12 Codex）

### 1. 当前修复没有真正满足“显示 feed 名称和作者”

- 级别: `p1`
- 问题:
  - 文档目标写的是“展示 feed 的名称和作者”，但当前修复方案只是把 `artist` 从 `article.source` 改成了 `article.author`，并把 `article.source` 挪到了 `album`。
  - 这意味着锁屏信息里仍然没有 feed 名称，原始 RSS URL 仍可能出现在界面上。
- 建议:
  - 明确锁屏元数据映射规则，例如：
    - `title = article.title`
    - `artist = article.author || feed_name`
    - `album = feed_name || 'Jasmine RSS Reader'`
  - 如果当前播放文章对象里没有 `feed_name`，需要在进入播放器前补齐，或在 `setupMediaSession` 中通过 `feedStore`/现有映射逻辑查出 feed 名称。

### 2. `seekto` 只能修复可拖动性，不能保证 Android 锁屏 UI 与 iOS 一致

- 级别: `p1`
- 问题:
  - 文档把 Android 锁屏 UI 差异归因为缺少 `seekto` handler，这个定位不够准确。
  - `seekto` 能解决“进度条不可拖动”，但不能控制系统锁屏页面是否显示上一首/下一首，也不能决定 Android 系统 UI 是否与 iOS 统一。
- 建议:
  - 将问题描述和预期结果收窄为“Android 锁屏进度条支持拖动 seek”；
  - 如果还要追求 UI 一致性，需要单独说明哪些是系统行为、哪些是应用可控行为，避免把平台差异误记成代码缺陷。

### 3. Media Session 清理逻辑与新增 handler 不对称

- 级别: `p2`
- 问题:
  - 当前新增了 `seekto` action handler，但清理 Media Session 时未同步清理 `seekto`。
- 建议:
  - 在 `clearMediaSession()` 中把 `seekto` 一并加入清理列表，保持 handler 生命周期对称，减少残留行为风险。

### 4. 测试验证仍未闭环

- 级别: `p2`
- 问题:
  - 文档当前仍未完成 `测试验证`，且没有列出需要验证的平台和现象。
- 建议:
  - 至少补充以下验证矩阵：
    1. iOS Safari 锁屏界面显示标题、作者、feed 名称是否符合预期。
    2. Android 锁屏界面进度条是否可拖动，拖动后是否正确跳转。
    3. 切歌、停止播放后，Media Session 控件是否正确刷新/清理。

## Re-review（2026-04-12 Codex）

### 1. 文档仍然没有闭合“显示 feed 名称和作者”这个原始需求

- 级别: `p1`
- 问题:
  - 顶部问题描述仍写的是“希望修复成展示 feed 的名称和作者”，修复方案里也写了“考虑通过 playerStore 获取 feed_name”，但当前实现仍是 `artist = article.author`、`album = article.source`。
  - `Decisions` 段落实际上把目标收缩成了“先不显示 URL 就可以”，这属于需求降级，不是原需求完成；但文档状态依然写着 `代码修复` 已完成。
  - 现在这份文档内部同时存在两套口径：原始目标是“feed 名称 + 作者”，实际落地是“作者替代 URL”，后续很难判断这个 bug 是否真的已关闭。
- 建议:
  - 二选一明确下来：
    1. 如果 bug 目标仍是“feed 名称 + 作者”，那当前状态应保持未完成，并拆出后续实现项；
    2. 如果产品决定降级为“避免显示原始 URL”，那就把顶部问题描述、修复方案、测试矩阵全部同步改成新口径，不要保留旧目标。

### 2. “需要异步查询 feedStore 才能拿到 feed 名称”的结论写得过重

- 级别: `p2`
- 问题:
  - 当前 `Decisions` 把 feed 名称方案描述成“需要从 feedStore 异步查询，会增加初始化延迟”，但仓库里已经有现成的 feed 名称解析逻辑，例如 `FeedView` / `ArticlesView` 都能基于 `source` 同步映射出 `feed_name`。
  - 这不代表锁屏修复一定是零成本，但文档把它描述成明显的异步阻塞，会夸大实现难度，影响后续排期判断。
- 建议:
  - 把这里改成更准确的表述，例如“当前播放链路没有现成携带 `feed_name`，需要补充字段透传或复用已有 source->feed_name 映射逻辑”，而不是直接归因为异步查询成本。
