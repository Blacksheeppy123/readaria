import { onMounted, onUnmounted } from 'vue'
import { useBreakpoint } from './useBreakpoint'
import { isTypingTarget } from '@/utils/keyboard'

/**
 * 列表上下文快捷键：j/k/↓/↑ 移动选中，Enter 打开，s 保存。
 * 仅在桌面断点激活；输入框聚焦或按住修饰键时忽略。
 * 所有回调由调用方提供，composable 不感知具体 store。
 */
export function useDesktopShortcuts({ getCount, getIndex, setIndex, onOpen, onSave }) {
  const { isDesktop } = useBreakpoint()

  const onKeydown = (e) => {
    if (!isDesktop.value) return
    if (e.metaKey || e.ctrlKey || e.altKey) return
    if (isTypingTarget(e.target)) return

    const count = getCount()
    if (count === 0) return
    const i = getIndex()

    if (e.key === 'j' || e.key === 'ArrowDown') {
      e.preventDefault()
      setIndex(i < 0 ? 0 : Math.min(i + 1, count - 1))
    } else if (e.key === 'k' || e.key === 'ArrowUp') {
      e.preventDefault()
      setIndex(i < 0 ? 0 : Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (i >= 0) { e.preventDefault(); onOpen(i) }
    } else if (e.key === 's') {
      if (i >= 0) { e.preventDefault(); onSave(i) }
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}
