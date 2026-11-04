# iOS 播放列表长按无法拖动

## 问题描述

- **功能**: Listen 页面播放队列（Queue）的拖拽排序
- **现象**: iOS 上播放列表长按无法拖动排序，安卓可以正常拖动
- **预期**: 长按拖拽手柄（bars 图标）或列表项后可以上下拖动调整顺序
- **实际**: iOS 设备上长按/拖拽无响应，无法触发排序

## 原因定位

### 根本原因

播放队列的拖拽排序功能使用了 **HTML5 原生拖放 API**（`draggable="true"` + `dragstart`/`dragover`/`drop` 等事件）。

然而，**iOS Safari 对 HTML5 DnD API 的支持非常有限**：在触摸设备上，只有 `<a>` 链接、`<img>` 图片等少数元素支持原生拖拽，普通的 `<div>` 元素即使设置了 `draggable="true"`，在 iOS 触摸屏上通常也不会触发拖拽事件。Android 浏览器对 HTML5 DnD 的触摸支持相对更好，因此出现平台差异。

### 相关代码位置

- **文件**: [`frontend/src/views/ListenView.vue`](../../frontend/src/views/ListenView.vue)
- **关键代码行**:
  - L69-L99: 拖拽相关的方法 (`onDragStart`, `onDragEnd`, `onDragOver`, `onDrop`, `onDragEnter`)
  - L294: `draggable="true"`
  - L296-L300: `@dragstart`, `@dragend`, `@dragover`, `@drop`, `@dragenter`
  - L302-L309: 拖拽手柄（`.queue-item-drag-handle`）

## 修复方案

### 思路

为 iOS / 移动触摸屏设备增加基于 **Touch 事件** 的拖拽降级方案。在拖拽手柄上绑定 `touchstart`/`touchmove`/`touchend`：

1. `touchstart` 时记录被拖拽项的索引；
2. `touchmove` 时通过 `document.elementFromPoint(x, y)` 计算当前触摸位置对应的列表项索引并高亮目标位置（复用 `dragOverIndex`）；
3. `touchend` 时调用已有的 `queueStore.reorder()` 完成排序。

### 代码修改建议

1. 给 `.queue-item-drag-handle` 增加 `@touchstart.stop.prevent` / `@touchmove.stop.prevent` / `@touchend.stop` 事件处理器。
2. 在 `ListenView.vue` 的 script 中新增 `onQueueTouchStart`, `onQueueTouchMove`, `onQueueTouchEnd` 方法，复用现有的 `draggedIndex` / `dragOverIndex` / `onDrop` 状态。
3. 给 `.queue-item-drag-handle` 添加 `touch-action: none`、`-webkit-touch-callout: none`、`user-select: none` CSS，防止触摸拖拽时页面滚动和误触。

### 注意事项

- 只在 **拖拽手柄**（`.queue-item-drag-handle`）上绑定 touch 事件，避免与 `van-swipe-cell` 的左右滑动删除手势冲突。
- `touchmove` 中调用 `e.preventDefault()` 并结合 `touch-action: none` 阻止页面滚动，保证拖拽体验。

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证
- [x] 在线部署

## 修复记录

**修复文件**: `frontend/src/views/ListenView.vue`

**修复时间**: 2026-04-13

**修改内容**:
- 在 `ListenView.vue` 中新增 `onQueueTouchStart`、`onQueueTouchMove`、`onQueueTouchEnd` 三个方法，为 iOS 提供 Touch 事件 fallback 拖拽逻辑。
- 在 `.queue-item-drag-handle` 元素上绑定 `@touchstart.stop.prevent`、`@touchmove.stop.prevent`、`@touchend.stop`，使用户可以通过长按并移动拖拽手柄来调整播放列表顺序。
- 更新 `.queue-item-drag-handle` 的 CSS，增加 `touch-action: none`、`-webkit-touch-callout: none`、`user-select: none`，防止拖拽过程中的页面滚动和误触。
- 前端构建验证通过，无编译错误。

## 相关提交

- `1147636` fix(ui): 修复 iOS 播放队列无法长按拖动排序的问题
