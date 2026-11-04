import { ref } from 'vue'

const DESKTOP_MIN_WIDTH = 1024

// 模块级单例：SPA 生命周期内常驻，无需解绑
const mql = window.matchMedia(`(min-width: ${DESKTOP_MIN_WIDTH}px)`)
const isDesktop = ref(mql.matches)
mql.addEventListener('change', (e) => { isDesktop.value = e.matches })

export function useBreakpoint() {
  return { isDesktop }
}
