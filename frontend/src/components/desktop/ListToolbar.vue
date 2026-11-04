<script setup>
defineOptions({ name: 'ListToolbar' })
// 中栏顶部工具条：当前源名称 + 排序切换。源筛选入口在左侧栏（Readwise 式）。
defineProps({
  currentFeedName: { type: String, default: '' },
  sortField: { type: String, default: 'updated_at' }
})
const emit = defineEmits(['toggle-sort'])

// 点击后失焦，避免焦点驻留按钮导致 Enter 双触发（排序 + 打开文章）
const onToggleSort = (ev) => {
  ev?.currentTarget?.blur()
  emit('toggle-sort')
}
</script>

<template>
  <div class="list-toolbar">
    <span class="toolbar-source" :title="currentFeedName">{{ currentFeedName }}</span>
    <button class="sort-btn" @click="onToggleSort">
      {{ sortField === 'updated_at' ? $t('desktop.sortUpdated') : $t('desktop.sortPublished') }}
    </button>
  </div>
</template>

<style scoped>
.list-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--readaria-border);
  background: var(--readaria-paper);
}
.toolbar-source {
  flex: 1; min-width: 0;
  font-size: 13px; font-weight: 600; color: var(--readaria-ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sort-btn {
  padding: 7px 12px; border: 1px solid var(--readaria-border);
  border-radius: 8px; background: var(--readaria-surface);
  font-size: 12px; color: var(--readaria-muted); cursor: pointer;
  white-space: nowrap;
}
</style>
