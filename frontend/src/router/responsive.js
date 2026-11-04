import { defineComponent, defineAsyncComponent, h } from 'vue'
import { useBreakpoint } from '@/composables/useBreakpoint'

/**
 * 路由级响应式组件：桌面断点渲染 desktopLoader，否则 mobileLoader。
 * 手动转发 attrs（路由 props: true 注入的 :id 等）到实际组件。
 * name 透传移动端视图名，保证 App.vue 的 keep-alive include="FeedView,ListenView"
 * 对 /feed 路由继续生效（keep-alive 按组件名匹配）。
 */
export function responsive(mobileLoader, desktopLoader, name = 'ResponsiveRoute') {
  const Mobile = defineAsyncComponent(mobileLoader)
  const Desktop = defineAsyncComponent(desktopLoader)
  return defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { attrs }) {
      const { isDesktop } = useBreakpoint()
      return () => h(isDesktop.value ? Desktop : Mobile, { ...attrs })
    }
  })
}
