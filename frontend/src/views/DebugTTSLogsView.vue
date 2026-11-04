<template>
  <div class="debug-logs-page">
    <van-nav-bar
      :title="$t('debug.ttsLogsTitle')"
      :left-text="$t('debug.back')"
      left-arrow
      @click-left="$router.back()"
    />

    <div class="content">
      <!-- 操作按钮 -->
      <div class="actions">
        <van-button
          type="primary"
          block
          @click="loadLogs"
          :loading="loading"
        >
          {{ $t('debug.refreshLogs') }}
        </van-button>

        <van-button
          block
          plain
          @click="exportLogs"
          style="margin-top: 10px"
        >
          {{ $t('debug.exportLogsCount', { count: logs.length }) }}
        </van-button>

        <van-button
          block
          plain
          type="danger"
          @click="clearLogs"
          style="margin-top: 10px"
        >
          {{ $t('debug.clearAllLogs') }}
        </van-button>
      </div>

      <!-- 实时监控卡片 -->
      <van-cell-group inset style="margin-top: 16px">
        <van-cell :title="$t('debug.totalLogs')" :value="logs.length" />
        <van-cell :title="$t('debug.mediaSessionEvents')" :value="mediaSessionEvents" />
        <van-cell :title="$t('debug.playbackRateEvents')" :value="playbackRateEvents" />
        <van-cell :title="$t('debug.playSuccess')" :value="playSuccessEvents" />
        <van-cell :title="$t('debug.playError')" :value="playErrorEvents" :label-class="playErrorEvents > 0 ? 'error-text' : ''" />
      </van-cell-group>

      <!-- 日志列表 -->
      <div v-if="logs.length > 0" class="logs">
        <van-divider>{{ $t('debug.recentLogs') }}</van-divider>

        <van-collapse v-model="activeLog" accordion>
          <van-collapse-item
            v-for="(log, index) in recentLogs"
            :key="index"
            :name="index"
          >
            <template #title>
              <div class="log-title">
                <van-tag :type="getLogType(log)">
                  {{ getLogIcon(log) }}
                </van-tag>
                <span class="log-message">{{ log.key ? $t(log.key) : log.message }}</span>
                <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              </div>
            </template>

            <!-- 日志详情 -->
            <div class="log-detail">
              <!-- 时间戳 -->
              <div class="info-item">
                <span class="label">{{ $t('debug.time') }}:</span>
                <span class="value">{{ formatTime(log.timestamp) }}</span>
              </div>

              <!-- 消息 -->
              <div class="info-item">
                <span class="label">{{ $t('debug.message') }}:</span>
                <span class="value">{{ log.key ? $t(log.key) : log.message }}</span>
              </div>

              <!-- User Agent -->
              <div class="info-item">
                <span class="label">{{ $t('debug.device') }}:</span>
                <span class="value device-info">{{ log.userAgent }}</span>
              </div>

              <!-- 数据详情 -->
              <div v-if="log.data && Object.keys(log.data).length > 0" class="section">
                <div class="section-title">{{ $t('debug.detailedData') }}</div>
                <div class="info-item" v-for="(value, key) in log.data" :key="key">
                  <span class="label">{{ key }}:</span>
                  <span class="value">{{ formatValue(value) }}</span>
                </div>
              </div>
            </div>
          </van-collapse-item>
        </van-collapse>
      </div>

      <van-empty v-else :description="$t('debug.noDebugLogs')" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast, showDialog } from 'vant'

const { t } = useI18n()

const loading = ref(false)
const logs = ref([])
const activeLog = ref(null)

/**
 * 加载日志
 */
const loadLogs = () => {
  loading.value = true

  try {
    const logsStr = localStorage.getItem('tts_debug_logs')
    if (!logsStr) {
      logs.value = []
      showToast({
        message: t('debug.noLogData'),
        position: 'top'
      })
      return
    }

    logs.value = JSON.parse(logsStr)

    showToast({
      message: t('debug.logsLoaded', { count: logs.value.length }),
      icon: 'success'
    })
  } catch (error) {
    console.error('[Debug] 加载日志失败:', error)
    showToast({
      message: t('debug.loadFailed') + ': ' + error.message,
      position: 'top'
    })
  } finally {
    loading.value = false
  }
}

/**
 * 导出日志
 */
const exportLogs = () => {
  try {
    if (logs.value.length === 0) {
      showToast({ message: t('debug.noLogData'), position: 'top' })
      return
    }

    const json = JSON.stringify(logs.value, null, 2)

    // 创建下载链接
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tts-debug-logs-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)

    showToast({
      message: t('debug.logsExported'),
      icon: 'success'
    })
  } catch (error) {
    console.error('[Debug] 导出日志失败:', error)
    showToast({
      message: t('debug.exportFailed') + ': ' + error.message,
      position: 'top'
    })
  }
}

/**
 * 清除日志
 */
const clearLogs = () => {
  showDialog({
    title: t('debug.confirmClear'),
    message: t('debug.confirmClearDebug'),
    confirmButtonColor: '#ee0a24'
  }).then(() => {
    try {
      localStorage.removeItem('tts_debug_logs')
      logs.value = []

      showToast({
        message: t('debug.logsCleared'),
        icon: 'success'
      })
    } catch (error) {
      showToast({
        message: t('debug.clearFailed') + ': ' + error.message,
        position: 'top'
      })
    }
  }).catch(() => {
    // 用户取消
  })
}

/**
 * 获取最近的日志（倒序，最多 100 条）
 */
const recentLogs = computed(() => {
  return logs.value.slice(-100).reverse()
})

/**
 * 统计 Media Session 事件数
 */
const mediaSessionEvents = computed(() => {
  return logs.value.filter(log => log.type === 'media').length
})

/**
 * 统计播放速率设置事件数
 */
const playbackRateEvents = computed(() => {
  return logs.value.filter(log => log.type === 'rate').length
})

/**
 * 统计播放成功事件数
 */
const playSuccessEvents = computed(() => {
  return logs.value.filter(log => log.type === 'success').length
})

/**
 * 统计播放失败事件数
 */
const playErrorEvents = computed(() => {
  return logs.value.filter(log => log.type === 'error').length
})

/**
 * 获取日志类型（用于显示不同颜色）
 */
const getLogType = (log) => {
  const type = log.type
  if (type === 'error' || type === 'danger') {
    return 'danger'
  }
  if (type === 'success') {
    return 'success'
  }
  if (type === 'media' || type === 'primary') {
    return 'primary'
  }
  if (type === 'warning') {
    return 'warning'
  }
  // 旧日志兼容：回退到中文子串匹配
  if (log.message.includes('失败') || log.message.includes('错误') || log.message.includes('异常')) {
    return 'danger'
  }
  if (log.message.includes('成功')) {
    return 'success'
  }
  if (log.message.includes('Media Session')) {
    return 'primary'
  }
  return 'default'
}

/**
 * 获取日志图标
 */
const getLogIcon = (log) => {
  const type = log.type
  if (type === 'error' || type === 'danger') {
    return '✗ ' + t('debug.failure')
  }
  if (type === 'success') {
    return '✓ ' + t('debug.success')
  }
  if (type === 'media' || type === 'primary') {
    return '🎵 ' + t('debug.media')
  }
  if (type === 'rate') {
    return '⚡ ' + t('debug.rate')
  }
  // 旧日志兼容：回退到中文子串匹配
  if (log.message.includes('失败') || log.message.includes('错误')) {
    return '✗ ' + t('debug.failure')
  }
  if (log.message.includes('成功')) {
    return '✓ ' + t('debug.success')
  }
  if (log.message.includes('Media Session')) {
    return '🎵 ' + t('debug.media')
  }
  if (log.message.includes('播放速率')) {
    return '⚡ ' + t('debug.rate')
  }
  return '📝 ' + t('debug.log')
}

/**
 * 格式化时间
 */
const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

/**
 * 格式化值
 */
const formatValue = (value) => {
  if (value === null || value === undefined) {
    return 'N/A'
  }
  if (typeof value === 'boolean') {
    return value ? '✅' : '❌'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

// 页面加载时自动加载日志
onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.debug-logs-page {
  min-height: 100vh;
  background-color: #f7f8fa;
}

.content {
  padding: 16px;
}

.actions {
  margin-bottom: 16px;
}

.error-text {
  color: #ee0a24;
}

.logs {
  margin-top: 16px;
}

.log-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.log-message {
  flex: 1;
  font-size: 13px;
  color: #646566;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-time {
  font-size: 12px;
  color: #969799;
  white-space: nowrap;
}

.log-detail {
  padding: 12px;
  background: #f7f8fa;
  border-radius: 4px;
}

.section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ebedf0;
}

.section-title {
  font-size: 14px;
  font-weight: 500;
  color: #323233;
  margin-bottom: 8px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
  gap: 8px;
}

.info-item .label {
  color: #646566;
  flex-shrink: 0;
}

.info-item .value {
  color: #323233;
  font-weight: 500;
  text-align: right;
  word-break: break-all;
}

.device-info {
  font-size: 11px;
  color: #969799;
}
</style>
