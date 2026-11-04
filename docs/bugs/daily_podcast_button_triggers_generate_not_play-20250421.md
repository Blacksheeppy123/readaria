# Listen Page "Listen" Button Triggers Generate Instead of Play

## 问题描述

在 Listen 页面，当日播客已生成完成时，按钮文案正确显示为 "Listen to today's podcast"，但点击按钮后触发的不是播放/进入播客详情，而是重新触发生成播客的逻辑。

### 用户操作步骤
1. 用户当日已有生成的播客（状态为 completed）
2. 打开 Listen 页面
3. 看到按钮文字显示 "Listen to today's podcast"
4. 点击该按钮
5. 触发了生成播客的 API 调用，而非进入播客播放/详情页

### 实际表现 vs 预期表现
- **实际**: 点击按钮调用 `podcastStore.generatePodcast()`，提示 "生成已开始"
- **预期**: 今日播客已完成时，点击按钮应进入播客详情页（播放页面），如同点击上面的播客卡片一样

## 原因定位

### 根本原因
按钮的文案和点击事件没有联动。文案根据 `isLatestPodcastTodayCompleted` 动态切换，但 `@click` 始终绑定 `onGenerate` 函数。

### 相关代码位置
- `frontend/src/views/ListenView.vue:248-258` - 生成按钮的 `@click` 绑定

```vue
<van-button
  round
  type="primary"
  :loading="generating"
  :disabled="generating"
  :loading-text="$t('podcast.generating')"
  @click="onGenerate"
>
  {{ isLatestPodcastTodayCompleted ? $t('podcast.listenToday') : (latestPodcast ? $t('podcast.generate') : $t('podcast.generateFirst')) }}
</van-button>
```

`viewPodcast` 函数（第 89-95 行）已经实现了播客卡片点击进入详情页的逻辑，但按钮没有复用该逻辑。

## 修复方案

1. 创建一个新的点击处理函数 `onPodcastAction`，根据 `isLatestPodcastTodayCompleted` 决定行为：
   - 今日已完成 → 调用 `viewPodcast(latestPodcast)` 进入详情页
   - 未完成 → 调用 `onGenerate()` 触发生成
2. 将按钮的 `@click="onGenerate"` 改为 `@click="onPodcastAction"`
3. 确保按钮文案和点击行为保持一致

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证

## 修复记录

**修复文件**: `frontend/src/views/ListenView.vue`

**修复时间**: 2025-04-21

**修改内容**:
- 新增 `onPodcastAction` 函数，根据播客完成状态路由到播放或生成
- 按钮 `@click` 从 `onGenerate` 改为 `onPodcastAction`

## 相关提交

- 待提交
