# iOS 锁屏显示 "Jasmine" 而非作者/Feed 名称

## 问题描述

用户在 iOS 设备上播放 TTS 音频时，锁屏界面显示的艺术家（artist）信息为 "Jasmine"，而不是文章作者或 Feed 名称。

**实际表现**: 锁屏显示 "从这些内幕里，我们能看到什么?" - "Jasmine"  
**预期表现**: 锁屏应显示 "从这些内幕里，我们能看到什么?" - "牧之野"（或对应 Feed 名称）

## 原因定位

### 根本原因
1. `article.author` 字段从 RSS 抓取时，如果文章没有作者信息会被设为空字符串 `''`
2. 原代码使用 `article.author || 'Jasmine'`，空字符串被视为 falsy 值，导致回退到 "Jasmine"
3. 同时存在两个 TTS composable（`useTTS.js` 和 `useOpenAITts.js`），需要同步修复

### 相关代码位置
- `frontend/src/composables/useTTS.js:302` - setupMediaSession artist 设置
- `frontend/src/composables/useOpenAITts.js:138` - setupMediaSession artist 设置

## 修复方案

1. **智能作者名选择逻辑**:
   - 优先使用 `article.author?.trim()`（如果存在且非空）
   - 其次从 `feedStore` 查找对应 feed 的 `feed_name`
   - 最后回退到 "Jasmine"

2. **双文件同步修复**:
   - 修改 `useTTS.js` 添加 feedStore 查找逻辑
   - 修改 `useOpenAITts.js` 同样使用 `article.author`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/composables/useTTS.js`
- `frontend/src/composables/useOpenAITts.js`

**修复时间**: 2026-04-12

**修改内容**:
1. `useTTS.js`:
   - 添加 `useFeedStore` 导入
   - 修改 `setupMediaSession` 函数签名，接受可选 `feedName` 参数
   - 添加智能作者名选择逻辑：`article.author?.trim() || feedName || 'Jasmine'`
   - 在 `loadAudio` 中调用 `setupMediaSession` 前查找 feed 名称

2. `useOpenAITts.js`:
   - 修改 artist 从 `article.source` 改为 `article.author?.trim() || 'Jasmine'`

## 相关提交

- `185c978` fix(ui): 优化锁屏作者名显示逻辑
