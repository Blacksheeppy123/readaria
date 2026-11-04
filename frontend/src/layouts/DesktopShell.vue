<script setup>
defineOptions({ name: 'DesktopShell' })
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useDesktopLayout } from '@/composables/useDesktopLayout'
import { isTypingTarget } from '@/utils/keyboard'
import DesktopSidebar from '@/components/desktop/DesktopSidebar.vue'
import PaneDivider from '@/components/desktop/PaneDivider.vue'

const route = useRoute()
const { isDesktop } = useBreakpoint()
const { immersive, sidebarWidth, setSidebarWidth, toggleImmersive, exitImmersive, persistLayout } = useDesktopLayout()

// 有桌面变体的路由（meta.desktop）占满主区域；其余移动视图在居中窄列中渲染
const useCanvas = computed(() => !route.meta.desktop)

// 侧栏拖拽调宽
let sidebarDragStart = 0
const onSidebarDragStart = () => { sidebarDragStart = sidebarWidth.value }
const onSidebarDrag = (delta) => setSidebarWidth(sidebarDragStart + delta)

// 沉浸模式快捷键：f 仅在文章阅读页切换；Esc 在任何页面退出沉浸
const onKeydown = (e) => {
  if (!isDesktop.value || e.metaKey || e.ctrlKey || e.altKey) return
  // Escape must remain available while focus is on the focus-mode button.
  if (e.key === 'Escape' && immersive.value) {
    e.preventDefault()
    exitImmersive()
    return
  }
  if (isTypingTarget(e.target)) return
  if (e.key === 'f' && route.name === 'article-detail') {
    e.preventDefault()
    toggleImmersive()
  }
}

// Focus mode belongs to the article reader. Leaving that route (or the shell
// entirely on a breakpoint change) must not leave the shared singleton stuck.
watch(() => route.name, (name) => {
  if (name !== 'article-detail') exitImmersive()
})

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  exitImmersive()
})
</script>

<template>
  <div class="desktop-shell" :class="{ immersive }">
    <DesktopSidebar v-show="!immersive" />
    <PaneDivider
      v-show="!immersive"
      @dragstart="onSidebarDragStart"
      @drag="onSidebarDrag"
      @dragend="persistLayout"
    />
    <main class="desktop-main" :class="{ 'desktop-canvas': useCanvas }">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.desktop-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--readaria-paper);
}
.desktop-main {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
}
/* 无桌面变体的移动视图：居中窄列。transform 使内部 fixed 定位（如 van-nav-bar）相对窄列生效 */
.desktop-canvas {
  max-width: 480px;
  margin: 0 auto;
  border-left: 1px solid var(--readaria-border);
  border-right: 1px solid var(--readaria-border);
  overflow-y: auto;
  transform: translateZ(0);
  background: var(--readaria-paper);
}
</style>
