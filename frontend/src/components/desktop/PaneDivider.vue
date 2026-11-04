<script setup>
import { onUnmounted } from 'vue'
defineOptions({ name: 'PaneDivider' })
// 拖拽分隔线：delta 为相对拖拽起点的横向位移（px），由调用方换算成新宽度
const emit = defineEmits(['dragstart', 'drag', 'dragend'])
let cleanupDrag = null

const stopDrag = () => {
  cleanupDrag?.()
  cleanupDrag = null
}

const onMousedown = (e) => {
  if (e.button !== 0) return
  e.preventDefault()
  // Defensive cleanup if a second drag starts before the first one ended.
  stopDrag()
  emit('dragstart')
  const startX = e.clientX
  const onMove = (ev) => emit('drag', ev.clientX - startX)
  const onUp = () => {
    stopDrag()
    emit('dragend')
  }
  cleanupDrag = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    window.removeEventListener('blur', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  window.addEventListener('blur', onUp)
}

onUnmounted(stopDrag)
</script>

<template>
  <div class="pane-divider" @mousedown="onMousedown" />
</template>

<style scoped>
.pane-divider {
  width: 4px; flex-shrink: 0; cursor: col-resize;
  border-left: 1px solid var(--readaria-border);
  transition: background 0.15s;
}
.pane-divider:hover, .pane-divider:active { background: var(--readaria-accent-soft); }
</style>
