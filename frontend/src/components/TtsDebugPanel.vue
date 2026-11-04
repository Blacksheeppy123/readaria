<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast, showConfirmDialog } from 'vant'
import { exportDebugLogs, clearDebugLogs } from '@/composables/useOpenAITts'

const { t } = useI18n()

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:show'])

// 日志数据
const logs = ref([])
const loading = ref(false)

// 加载日志
const loadLogs = () => {
  try {
    const logsStr = localStorage.getItem('tts_debug_logs')
    if (!logsStr) {
      logs.value = []
      return
    }

    const parsedLogs = JSON.parse(logsStr)
    // 倒序显示（最新的在前）
    logs.value = parsedLogs.reverse()
  } catch (error) {
    console.error('加载日志失败:', error)
    showToast(t('debug.loadLogsFailed'))
    logs.value = []
  }
}

// 当弹窗打开时加载日志
const onOpen = () => {
  loadLogs()
}

// 导出日志
const exportLogs = async () => {
  try {
    const logsJson = exportDebugLogs()

    // 创建 Blob 并下载
    const blob = new Blob([logsJson], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tts-debug-${new Date().toISOString()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    showToast(t('debug.logsExported'))
  } catch (error) {
    console.error('导出日志失败:', error)
    showToast(t('debug.exportFailed'))
  }
}

// 复制日志到剪贴板
const copyLogs = async () => {
  try {
    const logsJson = exportDebugLogs()

    // 使用 Clipboard API 复制
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(logsJson)
      showToast(t('debug.logsCopied'))
    } else {
      // 降级方案：使用传统方式
      const textarea = document.createElement('textarea')
      textarea.value = logsJson
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      showToast(t('debug.logsCopiedShort'))
    }
  } catch (error) {
    console.error('复制日志失败:', error)
    showToast(t('debug.copyFailed'))
  }
}

// 清除日志
const clearLogsConfirm = async () => {
  try {
    await showConfirmDialog({
      title: t('debug.confirmClear'),
      message: t('debug.confirmClearDebugMessage'),
      confirmButtonText: t('debug.clear'),
      cancelButtonText: t('common.cancel')
    })

    clearDebugLogs()
    logs.value = []
    showToast(t('debug.logsCleared'))
  } catch (error) {
    // 用户取消
  }
}

// 格式化时间
const formatTime = (isoString) => {
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 格式化数据对象
const formatData = (data) => {
  return JSON.stringify(data, null, 2)
}

// 日志统计
const logStats = computed(() => {
  const total = logs.value.length
  const errors = logs.value.filter(log => log.type === 'error').length
  return { total, errors }
})

// 关闭弹窗
const close = () => {
  emit('update:show', false)
}
</script>

<template>
  <van-popup
    :show="show"
    position="bottom"
    :style="{ height: '80%' }"
    closeable
    @update:show="emit('update:show', $event)"
    @open="onOpen"
  >
    <div class="debug-panel">
      <div class="header">
        <h2>{{ $t('debug.ttsLogsTitle') }}</h2>
        <div class="stats">
          <span>{{ $t('debug.totalLogs') }}: {{ logStats.total }}</span>
          <span class="error-count">{{ $t('debug.errors') }}: {{ logStats.errors }}</span>
        </div>
      </div>

      <div class="actions">
        <van-button size="small" type="primary" @click="copyLogs">
          <van-icon name="copy" /> {{ $t('debug.copyLogs') }}
        </van-button>
        <van-button size="small" @click="loadLogs">
          <van-icon name="replay" /> {{ $t('debug.refresh') }}
        </van-button>
        <van-button size="small" type="danger" @click="clearLogsConfirm">
          <van-icon name="delete" /> {{ $t('debug.clear') }}
        </van-button>
      </div>

      <div class="logs-container">
        <div v-if="logs.length === 0" class="empty">
          <van-empty :description="$t('debug.noLogs')" />
        </div>

        <div v-else class="log-list">
          <div
            v-for="(log, index) in logs"
            :key="index"
            class="log-item"
            :class="{ error: log.type === 'error' }"
          >
            <div class="log-header">
              <span class="time">{{ formatTime(log.timestamp) }}</span>
              <span class="message">{{ log.key ? $t(log.key) : log.message }}</span>
            </div>
            <div v-if="log.data && Object.keys(log.data).length > 0" class="log-data">
              <pre>{{ formatData(log.data) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </van-popup>
</template>

<style scoped>
.debug-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  background: #f7f8fa;
}

.header {
  margin-bottom: 12px;
}

.header h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #323233;
}

.stats {
  display: flex;
  gap: 12px;
  font-size: 14px;
  color: #646566;
}

.error-count {
  color: #ee0a24;
  font-weight: 500;
}

.actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.logs-container {
  flex: 1;
  overflow-y: auto;
  background: white;
  border-radius: 8px;
  padding: 12px;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.log-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log-item {
  background: #f7f8fa;
  border-radius: 4px;
  padding: 8px;
  font-size: 12px;
  border-left: 3px solid #1989fa;
}

.log-item.error {
  border-left-color: #ee0a24;
  background: #fff1f0;
}

.log-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 4px;
}

.time {
  color: #969799;
  font-size: 11px;
}

.message {
  color: #323233;
  font-weight: 500;
}

.log-data {
  margin-top: 8px;
  background: white;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
}

.log-data pre {
  margin: 0;
  font-size: 11px;
  color: #646566;
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>
