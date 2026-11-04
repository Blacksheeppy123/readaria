# Daily Podcast Button Shows "Generate" When Already Generated

## 问题描述

当日播客已生成的情况下，首页（Feed 页）和 Listen 页的按钮仍然显示"Generate Daily Podcast"（生成每日播客），而应该显示"Listen"（收听）或类似的提示。

### 用户操作步骤
1. 用户当日已有生成的播客（如截图所示，4月21日的播客状态为 "Completed"）
2. 打开 Feed 页或 Listen 页
3. 看到按钮文字仍为 "Generate today's podcast" / "Generate Daily Podcast"

### 实际表现 vs 预期表现
- **实际**: 按钮显示 "Generate Daily Podcast"，暗示用户需要重新生成
- **预期**: 当日播客已生成时，按钮应提示用户"收听"而非"生成"

## 原因定位

### 根本原因
按钮文案未根据当日播客生成状态进行动态切换。

- `FeedView.vue` 的概览按钮直接硬编码为 `$t('feed.generateTodaysPodcast')`，没有任何状态判断
- `ListenView.vue` 的按钮仅判断 `latestPodcast` 是否存在，存在即显示 "Generate Daily Podcast"，没有区分"今日已生成"和"需要生成"的情况

### 相关代码位置
- `frontend/src/views/FeedView.vue:630-632` - Feed 页概览按钮
- `frontend/src/views/ListenView.vue:248` - Listen 页生成按钮
- `frontend/src/stores/podcastStore.js` - 播客状态管理

## 修复方案

1. 新增 i18n 文案 `podcast.listenToday`："Listen to today's podcast" / "收听今日播客"
2. `FeedView.vue`：
   - 引入 `usePodcastStore`
   - 添加计算属性 `hasTodayPodcastCompleted`，判断播客列表第一个元素是否是今天创建的且状态为 `completed`
   - 在 `onMounted` 中并行获取播客列表
   - 按钮文案根据 `hasTodayPodcastCompleted` 动态切换
3. `ListenView.vue`：
   - 添加计算属性 `isLatestPodcastTodayCompleted`
   - 按钮文案：今日已完成 → `listenToday`，有播客但不是今天完成 → `generate`，无播客 → `generateFirst`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**:
- `frontend/src/views/FeedView.vue`
- `frontend/src/views/ListenView.vue`
- `frontend/src/i18n/en.json`
- `frontend/src/i18n/zh.json`

**修复时间**: 2025-04-21

**修改内容**:
- `FeedView.vue`: 引入 `usePodcastStore`，新增 `hasTodayPodcastCompleted` 计算属性，概览按钮根据状态显示"收听今日播客"或"生成今日播客"
- `ListenView.vue`: 新增 `isLatestPodcastTodayCompleted` 计算属性，生成按钮根据状态显示不同文案
- `en.json` / `zh.json`: 新增 `podcast.listenToday` 国际化文案

## 相关提交

- 待提交
