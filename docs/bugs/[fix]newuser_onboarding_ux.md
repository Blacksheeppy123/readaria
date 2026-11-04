# 新用户体验：引导流程与文案体验

## 问题描述

1. **OPML 导入误导性文案**
   - Onboarding 中「无缝迁移」卡片文案写"一键迁移" / "one click import"，但用户点击后直接弹出文件选择器，没有任何提示说明需要先从 Feedly、Inoreader 等应用中导出 OPML 文件。
   - 新用户往往不知道 OPML 是什么，也不知道如何导出，导致操作中断或困惑。

## 根因定位

- `frontend/src/views/FeedView.vue` 中 `handleImportOpml()` 直接调用 `fileInput.value?.click()`，没有任何前置引导或说明。
- i18n 文案（`frontend/src/i18n/zh.json`、`frontend/src/i18n/en.json`）使用"一键迁移""Seamless Migration"等过于理想化的描述，与实际流程不符。

## 修复方案

### 1. 前置引导弹窗

修改 `handleImportOpml()` 逻辑：
- 点击 OPML 卡片后，先弹出 `van-dialog`（或自定义引导弹窗），分步骤说明：
  1. 从旧阅读器（Feedly / Inoreader / Reeder 等）导出 OPML 文件
  2. 点击下方按钮选择刚才导出的文件
  3. 等待导入完成
- 弹窗底部提供两个按钮：
  - "我已导出，选择文件" → 触发 `fileInput.click()`
  - "取消"

### 2. i18n 文案修正

更新 `frontend/src/i18n/zh.json` 和 `frontend/src/i18n/en.json` 的相关键值：

**zh:**
```json
{
  "importFeedList": "导入订阅列表",
  "importFeedListDesc": "从 Feedly、Inoreader 导出 OPML 文件并导入",
  "importOpmlGuideTitle": "如何导入订阅？",
  "importOpmlGuideStep1": "1. 在 Feedly / Inoreader / 其他阅读器中找到「导出 OPML」选项",
  "importOpmlGuideStep2": "2. 将导出的 .opml 文件保存到设备",
  "importOpmlGuideStep3": "3. 点击下方按钮选择该文件完成导入",
  "importOpmlGuideConfirm": "我已导出，选择文件",
  "importOpmlGuideCancel": "取消"
}
```

**en:**
```json
{
  "importFeedList": "Import Subscriptions",
  "importFeedListDesc": "Export OPML from Feedly, Inoreader and import it here",
  "importOpmlGuideTitle": "How to import?",
  "importOpmlGuideStep1": "1. Find the \"Export OPML\" option in Feedly / Inoreader / your reader",
  "importOpmlGuideStep2": "2. Save the exported .opml file to your device",
  "importOpmlGuideStep3": "3. Tap the button below to select the file",
  "importOpmlGuideConfirm": "I've exported, select file",
  "importOpmlGuideCancel": "Cancel"
}
```

### 3. 可选优化
- 在弹窗中加入外部链接（如 Feedly 导出帮助页面），方便用户跳转查看具体步骤。
- 导入过程中显示 loading 和进度提示，导入完成后显示成功/失败统计。

## 验收标准
- [ ] 点击「导入订阅列表」卡片后先弹出引导说明，而不是直接打开文件选择器
- [ ] 文案从"一键迁移"改为更准确的"导出 OPML 并导入"
- [ ] 中英文 i18n 键值已补充完整
- [ ] 弹窗中提供明确的"选择文件"和"取消"操作按钮
