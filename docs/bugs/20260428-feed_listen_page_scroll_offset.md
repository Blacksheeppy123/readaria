# Feed 页面跳转 Listen 页面滚动定位不准确

## 问题描述

在 Feed 页面点击 "Listen to today's podcast" 按钮后，跳转到 Listen 页面时：
- 页面没有完整显示 Podcast 卡片区域
- Podcast section 只露出顶部一小部分（被 fixed nav bar 遮挡）
- 用户看到的只是一个角落，造成困惑和误解

**用户操作步骤：**
1. 打开 Feed 页面
2. 点击 "Listen to today's podcast" / "Generate today's podcast"
3. 跳转到 Listen 页面
4. Podcast section 只露出一小部分，没有完整展示

**预期表现：** Podcast 卡片区域应该完整、清晰地展示在视口中
**实际表现：** Podcast section 顶部被 fixed nav bar 遮挡，只露出底部一小部分

## 原因定位

### 根本原因
Feed 页面通过 `router.push({ name: 'listen', query: { scrollTo: 'podcast' } })` 跳转，Listen 页面在 `onMounted` 中使用 `scrollIntoView({ behavior: 'smooth', block: 'start' })` 滚动到 podcast section。

问题：`block: 'start'` 会将元素的顶部与视口顶部对齐，但 Listen 页面有一个 fixed 定位的 `van-nav-bar`（高度约 46px+），导致 podcast section 的顶部被 nav bar 遮挡。

### 相关代码位置
- **Feed 页面跳转**: `frontend/src/views/FeedView.vue:603`
  ```javascript
  router.push({ name: 'listen', query: { scrollTo: 'podcast' } })
  ```
- **Listen 页面滚动**: `frontend/src/views/ListenView.vue:38-46`
  ```javascript
  if (route.query.scrollTo === 'podcast') {
    nextTick(() => {
      if (podcastSectionRef.value) {
        podcastSectionRef.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
      router.replace({ query: {} })
    })
  }
  ```

## 修复方案

将 `scrollIntoView` 的 `block` 参数从 `'start'` 改为 `'center'`，让 podcast section 在视口中居中显示，确保不被 nav bar 遮挡且完整可见。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/views/ListenView.vue`

**修复时间**: 2026-04-28

**修改内容**:
- `scrollIntoView({ behavior: 'smooth', block: 'start' })` → `scrollIntoView({ behavior: 'smooth', block: 'center' })`

## 相关提交

## Review意见（2026-04-28 Codex）

No obvious issues found in the current `scrollIntoView({ block: 'center' })` change. Review passed.

Residual risk: there is still no automated mobile regression that asserts the podcast card is not hidden under the fixed nav bar on iOS Safari / Android Chrome, so this fix currently depends on manual verification.

## Review意见（2026-04-28 Codex 复审）

No new issues found in the current implementation. The previous pass still stands.
