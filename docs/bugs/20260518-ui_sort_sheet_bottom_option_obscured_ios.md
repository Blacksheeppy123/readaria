# iOS 排序弹窗最后一个选项被底部遮挡

## 问题描述

在 iOS 设备（含 Safari / PWA）上，打开 Feed 列表或 Articles 列表页的"排序"或"来源筛选"动作面板（`van-action-sheet`）时，弹窗最后一个选项被底部 Tabbar / Home Indicator 区域视觉遮盖，用户无法清晰看到甚至无法点击最后一项。

**用户操作步骤：**
1. 打开 Feed 列表（`/feed`）或 Articles 列表
2. 点击右上角"排序"图标（或筛选图标）
3. 弹出从底部滑入的 `van-action-sheet`

**实际表现：** 列表最后一行 cell 被底部 Tabbar（高 50px + 安全区域）或 iOS Home Indicator（约 34px）遮挡。
**预期表现：** 所有选项可见且可点击，最后一项与底部之间有合理的缓冲间距。

## 原因定位

### 根本原因

Vant 4 Popup 默认 **不 teleport**（`teleport` 为 `undefined`），导致 `position: fixed` 的弹窗渲染在 `.content { -webkit-overflow-scrolling: touch }` 内部。iOS Safari 对嵌套在 momentum-scrolling 容器内的 fixed 元素存在已知渲染异常，弹窗可能无法正确脱离滚动容器的排版上下文，导致底部选项被底部 Tabbar / Home Indicator 区域视觉遮挡。

另外，`.filter-content` 的 `padding-bottom: max(20px, env(safe-area-inset-bottom))` 虽然已包含安全区域高度，但 20px 的兜底值在 iOS 上略显不足，与弹窗内部安全区域 padding 叠加后仍可能让最后一行 cell 贴近底边。

### 具体流程问题

- Vant 4.9.21 的 `ActionSheet.safeAreaInsetBottom` 已默认 `true`（`truthProp`），Popup 容器本身已自动添加 `van-safe-area-bottom` 类（`padding-bottom: env(safe-area-inset-bottom)`）
- 但 Vant Popup 默认 **不 teleport**，弹窗仍渲染在组件原 DOM 位置（即 `.content { overflow-y: auto; -webkit-overflow-scrolling: touch }` 内部）
- iOS Safari 中，`position: fixed` 嵌套在 `-webkit-overflow-scrolling: touch` 容器内时，可能出现定位异常或 z-index 上下文被截断，导致弹窗底部被 Tabbar / Home Indicator 区域视觉覆盖
- 内部 `.filter-content` 的兜底 padding 仅 20px，与 Tabbar 高度（50px）相比缓冲不足

### 相关代码位置

- `frontend/src/views/FeedView.vue:866` - 排序弹窗 `van-action-sheet`
- `frontend/src/views/ArticlesView.vue:472` - 来源筛选弹窗 `van-action-sheet`
- `frontend/src/views/ArticlesView.vue:492` - 排序弹窗 `van-action-sheet`
- `frontend/src/views/FeedView.vue:1110-1115` - `.filter-content` 样式
- `frontend/src/views/ArticlesView.vue:570-577` - `.filter-content` 样式

## 修复方案

**方案：为所有底部弹出式 `van-action-sheet` 添加 `teleport="body"`（真正修复 iOS 渲染问题的结构改动），显式保留 `safe-area-inset-bottom` 作为防御性编码，并优化 `.filter-content` 的底部 padding。**

### 代码修改

1. **所有底部弹出的 `<van-action-sheet>`** 添加 `teleport="body"` + 显式 `safe-area-inset-bottom`：

```html
<!-- 修改前 -->
<van-action-sheet v-model:show="showSortSheet" :title="$t('articles.sortBy')">

<!-- 修改后 -->
<van-action-sheet
  v-model:show="showSortSheet"
  :title="$t('articles.sortBy')"
  safe-area-inset-bottom
  teleport="body"
>
```

2. **`.filter-content` 的 padding-bottom 提升为更稳健的写法**：

```css
.filter-content {
  max-height: 60vh;
  overflow-y: auto;
  padding-bottom: max(24px, env(safe-area-inset-bottom));
  -webkit-overflow-scrolling: touch;
}
```

### 根因说明

- **真正根因**：Vant 4 Popup 默认 **不 teleport**，导致 `position: fixed` 的弹窗渲染在 `.content { -webkit-overflow-scrolling: touch }` 内部。iOS Safari 对嵌套在 momentum-scrolling 容器内的 fixed 元素存在已知渲染异常，弹窗可能无法正确脱离滚动容器的排版上下文，导致底部选项被底部 Tabbar / Home Indicator 区域视觉遮挡。
- **`teleport="body"`** 将弹窗提升到 document body 根节点，彻底脱离 `.content` 的滚动上下文，消除 iOS Safari 的渲染异常。
- **`safe-area-inset-bottom`** 在 Vant 4.9.21 中已默认 `true`（`truthProp`），显式声明仅为防御性编码，防止未来 Vant 版本变更默认行为。
- **padding 增量**：`.filter-content` padding-bottom 从 20px 提升到 24px，所有平台均增加 4px 底部间距（iOS 上 `env(safe-area-inset-bottom)` 约为 34px，实际生效值不变；Android/桌面生效值从 20px 增加到 24px，视觉影响极小）。

### 注意事项

- `safe-area-inset-bottom` 是 Vant 4 `van-popup`（被 `van-action-sheet` 继承）的内置属性，无需额外引入
- `teleport="body"` 是 Vant 4 Popup 的标准属性，将弹窗内容渲染到 body 根节点
- 同一页面中 `showFeedFilter` 与 `showSortSheet` 必须同步修改
- 所有平台均受 `.filter-content` padding 增量影响，但视觉差异极小

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证（iOS Safari / iOS PWA / Android Chrome）

## 修复记录

**修复文件**:
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/ArticlesView.vue`
- `frontend/src/views/MeView.vue`
- `frontend/src/components/SoftPaywallSheet.vue`

**修复时间**: 2026-05-18

**修改内容**:
- FeedView.vue:866 - 给排序 `van-action-sheet` 添加 `teleport="body"` + 显式 `safe-area-inset-bottom`
- ArticlesView.vue:472 - 给来源筛选 `van-action-sheet` 添加 `teleport="body"` + 显式 `safe-area-inset-bottom`
- ArticlesView.vue:496 - 给排序 `van-action-sheet` 添加 `teleport="body"` + 显式 `safe-area-inset-bottom`
- MeView.vue:590 - 给语言选择 `van-action-sheet` 添加 `teleport="body"` + 显式 `safe-area-inset-bottom`（顺手修复）
- SoftPaywallSheet.vue:2 - 给软付费墙 `van-action-sheet` 添加 `teleport="body"` + 显式 `safe-area-inset-bottom`（顺手修复）
- FeedView.vue:1117 - `.filter-content` padding-bottom 由 20px 提升到 24px
- ArticlesView.vue:582 - `.filter-content` padding-bottom 由 20px 提升到 24px

## 相关提交

(部署后补充)
