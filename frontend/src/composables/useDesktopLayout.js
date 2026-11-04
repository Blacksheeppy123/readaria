import { ref } from 'vue'

const LS_KEY = 'readaria_desktop_layout'
const LIMITS = {
  sidebar: { min: 180, max: 300, def: 220 },
  list: { min: 280, max: 520, def: 360 }
}

const sidebarWidth = ref(LIMITS.sidebar.def)
const listWidth = ref(LIMITS.list.def)
const immersive = ref(false)

const clamp = (v, { min, max }) => Math.min(max, Math.max(min, v))

function applyCssVars() {
  const root = document.documentElement
  root.style.setProperty('--desktop-sidebar-width', `${sidebarWidth.value}px`)
  root.style.setProperty('--desktop-list-width', `${listWidth.value}px`)
}

function persist() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      sidebar: sidebarWidth.value,
      list: listWidth.value
    }))
  } catch (_) {}
}

// 模块加载时恢复（SPA 单例）
try {
  const saved = JSON.parse(localStorage.getItem(LS_KEY) || 'null')
  if (saved?.sidebar) sidebarWidth.value = clamp(saved.sidebar, LIMITS.sidebar)
  if (saved?.list) listWidth.value = clamp(saved.list, LIMITS.list)
} catch (_) {}
applyCssVars()

export function useDesktopLayout() {
  const setSidebarWidth = (px) => { sidebarWidth.value = clamp(px, LIMITS.sidebar); applyCssVars() }
  const setListWidth = (px) => { listWidth.value = clamp(px, LIMITS.list); applyCssVars() }
  const toggleImmersive = () => { immersive.value = !immersive.value }
  const exitImmersive = () => { immersive.value = false }
  return { sidebarWidth, listWidth, immersive, setSidebarWidth, setListWidth, toggleImmersive, exitImmersive, persistLayout: persist }
}
