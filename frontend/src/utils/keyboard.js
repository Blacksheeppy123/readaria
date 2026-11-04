/**
 * 键盘事件目标是否为交互控件（输入框/下拉框/按钮/可编辑区域）。
 * 控件获得键盘焦点时，应由控件自身处理 Enter/方向键，避免与全局快捷键叠加。
 */
export function isTypingTarget(el) {
  return !!el && (
    ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(el.tagName) ||
    el.isContentEditable
  )
}
