# Feed 筛选栏左右滑动失效（Android）

## 问题描述

在 Android 设备上，Feed 页面顶部的筛选栏（分类筛选标签）左右滑动功能失效。用户无法通过左右滑动手势切换或查看更多筛选标签。

- **功能**: Feed 页面顶部筛选栏左右滑动
- **操作步骤**: 在 Android 设备上打开 Feed 页面，尝试左右滑动筛选栏
- **实际表现**: 左右滑动无响应，无法查看更多筛选标签
- **预期表现**: 筛选栏可以左右滑动，查看更多分类标签

## 原因定位

### 根本原因

第一次修复把横向滚动层判断错了。

Vant 4 的 `van-tabs` 在 `type="card"` + `shrink` 模式下，真正接收横向手势并被内部 `scrollLeftTo(...)` 控制的是 `.van-tabs__nav`，不是外层 `.van-tabs__wrap`。之前只给 `.van-tabs__wrap` 增加 `overflow-x: auto`，会出现两个问题：

1. **用户手势仍然落不到真正的滚动层**：`.van-tabs__nav` 仍由 Vant 自己控制滚动，`wrap` 虽然可溢出，但不是实际承接 tab 横向拖动的元素
2. **点击边缘标签会“露出一点”造成误判**：这是 Vant 在切换 active tab 后调用内部 `scrollIntoView()` 自动调整 `.van-tabs__nav.scrollLeft`，不是用户 swipe 生效
3. **`swipeable` 容易混淆问题方向**：该属性控制的是内容区左右切页，不负责顶部 tab 栏的原生横向拖动
4. **全局 `touch-action: pan-y` 覆盖了实际手指命中元素**：项目全局样式对 `*` 设置了 `touch-action: pan-y`，而用户触摸通常命中 `.van-tab` / `.van-tab__text`，即使 `.van-tabs__nav` 是 `pan-x`，浏览器仍会因为命中链路上的子元素限制而拒绝横向手势

### 相关代码位置

- [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue)
  - `<van-tabs>` 组件（第596-606行）
  - `.feed-tabs` 样式区域（第814-844行）

## 修复方案

在 `.feed-tabs` 的深层样式中显式覆盖 Vant 内部样式，但这次直接落到 `.van-tabs__nav`：

1. 保持 `.van-tabs__wrap` 为 `overflow: hidden`，避免外层成为“假滚动层”
2. 给 `.van-tabs__nav--card.van-tabs__nav--complete` 添加 `overflow-x: auto`、`-webkit-overflow-scrolling: touch`、`touch-action: pan-x`
3. 保持 `.van-tabs__nav--card` 为单行不换行，并让 `.van-tab` 使用 `flex: 0 0 auto`
4. 给 `.feed-tabs`、`.van-tabs__wrap`、`.van-tab`、`.van-tab__text` 这一整条触摸命中链显式覆盖 `touch-action: pan-x`
5. 隐藏 `.van-tabs__nav` 滚动条，保留现有视觉效果

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: [frontend/src/views/FeedView.vue](frontend/src/views/FeedView.vue)

**修复时间**: 2026-04-29

**修改内容**:
- 第一次修复：给 `.van-tabs__wrap` 增加横向滚动样式，但线上验证后确认未命中真实滚动层
- 第二次修复：将横向滚动能力改为直接作用于 `.van-tabs__nav--card.van-tabs__nav--complete`
- 补充 `touch-action: pan-x`、`overscroll-behavior-x: contain` 与 `flex: 0 0 auto`，确保 Android 上 swipe 手势稳定作用在 tab 导航栏本身
- 第三次修复：修正全局 `* { touch-action: pan-y; }` 对 tab 子元素的覆盖，给 feed tabs 命中链显式恢复 `pan-x`

## 相关提交

- `997da22` fix(feed): enforce horizontal scroll on Android tab filter bar

## 最新进展

- 2026-04-30: 用户反馈 `readaria.com` 线上最新版本仍无法直接左右 swipe，只能点击边缘来源名后露出部分 tab
- 2026-04-30: 复盘确认这是第一次修复命中了错误的容器层，已调整为作用于 `.van-tabs__nav`
- 2026-04-30: 线上再次验证发现容器样式已生效，但手势仍被全局 `touch-action: pan-y` 限制，已追加第三次修复
