import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'

/**
 * 网络状态检测 Composable
 * 监听网络连接状态，并在状态变化时显示提示
 */
export function useNetworkStatus() {
  const { t } = useI18n()
  const isOnline = ref(navigator.onLine)
  let hasShownOfflineToast = false
  let isInitialized = false // 标记是否已初始化，避免首次加载时误判

  const updateOnlineStatus = () => {
    const newStatus = navigator.onLine

    // 如果是首次初始化，不显示任何提示，只记录状态
    if (!isInitialized) {
      isOnline.value = newStatus
      isInitialized = true
      return
    }

    // 只在状态真正变化时才显示提示
    if (newStatus !== isOnline.value) {
      isOnline.value = newStatus

      if (newStatus) {
        // 网络恢复
        showToast({
          message: t('network.networkRestored'),
          icon: 'success',
          duration: 2000
        })
        hasShownOfflineToast = false
      } else {
        // 网络断开
        if (!hasShownOfflineToast) {
          showToast({
            message: t('network.networkDisconnected'),
            icon: 'fail',
            duration: 3000
          })
          hasShownOfflineToast = true
        }
      }
    }
  }

  onMounted(() => {
    // 延迟 500ms 后再标记为已初始化，避免页面加载过程中误判
    setTimeout(() => {
      isInitialized = true
    }, 500)

    window.addEventListener('online', updateOnlineStatus)
    window.addEventListener('offline', updateOnlineStatus)
  })

  onUnmounted(() => {
    window.removeEventListener('online', updateOnlineStatus)
    window.removeEventListener('offline', updateOnlineStatus)
  })

  return {
    isOnline
  }
}
