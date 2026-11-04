<template>
  <div class="debug-page">
    <van-nav-bar
      :title="$t('debug.ttsTitle')"
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
          @click="generateReport"
          :loading="loading"
        >
          {{ $t('debug.generateReport') }}
        </van-button>

        <van-button
          block
          plain
          @click="exportLogs"
          style="margin-top: 10px"
        >
          {{ $t('debug.exportLogs') }}
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

      <!-- 诊断报告 -->
      <div v-if="report" class="report">
        <van-divider>{{ $t('debug.diagnosticSummary') }}</van-divider>

        <van-cell-group>
          <van-cell :title="$t('debug.totalSessions')" :value="report.totalSessions" />
          <van-cell :title="$t('debug.successCount')" :value="report.successCount" />
          <van-cell :title="$t('debug.failureCount')" :value="report.failureCount" :label-class="report.failureCount > 0 ? 'error-text' : ''" />
          <van-cell :title="$t('debug.cacheHitRate')" :value="report.cacheHitRate" />
        </van-cell-group>

        <van-divider>{{ $t('debug.avgLoadTime') }}</van-divider>

        <van-cell-group>
          <van-cell :title="$t('debug.avgAll')" :value="report.avgLoadTime.all" />
          <van-cell
            :title="$t('debug.avgCacheHit')"
            :value="report.avgLoadTime.cacheHit"
            :label="$t('debug.fromLocalCache')"
          />
          <van-cell
            :title="$t('debug.avgCacheMiss')"
            :value="report.avgLoadTime.cacheMiss"
            :label="$t('debug.needsRegeneration')"
          />
        </van-cell-group>

        <van-divider>{{ $t('debug.deviceDistribution') }}</van-divider>

        <van-cell-group>
          <van-cell :title="$t('debug.safariLabel')" :value="$t('debug.nTimes', { n: report.deviceDistribution.Safari })" />
          <van-cell :title="$t('debug.pwaLabel')" :value="$t('debug.nTimes', { n: report.deviceDistribution.PWA })" />
        </van-cell-group>

        <van-divider>{{ $t('debug.commonErrors') }}</van-divider>

        <van-cell-group v-if="report.commonErrors && report.commonErrors.length > 0">
          <van-cell
            v-for="(error, index) in report.commonErrors"
            :key="index"
            :title="error.message"
            :value="$t('debug.nTimes', { n: error.count })"
            label-class="error-text"
          />
        </van-cell-group>
        <van-empty v-else :description="$t('debug.noErrors')" />
      </div>

      <!-- 详细日志列表 -->
      <div v-if="logs && logs.length > 0" class="logs">
        <van-divider>{{ $t('debug.detailedLogs', { count: logs.length }) }}</van-divider>

        <van-collapse v-model="activeLog" accordion>
          <van-collapse-item
            v-for="(log, index) in logs"
            :key="index"
            :name="index"
          >
            <template #title>
              <div class="log-title">
                <van-tag :type="log.status === 'success' ? 'success' : 'danger'">
                  {{ log.status === 'success' ? '✓ ' + $t('debug.success') : '✗ ' + $t('debug.failure') }}
                </van-tag>
                <span class="log-article">{{ $t('debug.articleLabel', { id: log.articleId }) }}</span>
                <span class="log-duration">{{ log.totalDuration.toFixed(0) }}ms</span>
              </div>
            </template>

            <!-- 日志详情 -->
            <div class="log-detail">
              <!-- 基本信息 -->
              <div class="section">
                <div class="section-title">{{ $t('debug.basicInfo') }}</div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.articleId') }}:</span>
                  <span class="value">{{ log.articleId }}</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.textLength') }}:</span>
                  <span class="value">{{ $t('debug.nCharacters', { n: log.textLength }) }}</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.totalDuration') }}:</span>
                  <span class="value">{{ log.totalDuration.toFixed(0) }}ms</span>
                </div>
              </div>

              <!-- 关键指标 -->
              <div class="section">
                <div class="section-title">{{ $t('debug.keyMetrics') }}</div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.cacheHit') }}:</span>
                  <span class="value">{{ log.metrics.cacheHit ? '✅ ' + $t('debug.yes') : '❌ ' + $t('debug.no') }}</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.apiCall') }}:</span>
                  <span class="value">{{ log.metrics.apiCallDuration.toFixed(0) }}ms</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.audioDownload') }}:</span>
                  <span class="value">{{ log.metrics.downloadDuration.toFixed(0) }}ms</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.audioSize') }}:</span>
                  <span class="value">{{ log.metrics.audioBlobSize }}KB</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.canplayWait') }}:</span>
                  <span class="value">{{ log.metrics.canplayWaitDuration.toFixed(0) }}ms</span>
                </div>
                <div class="info-item">
                  <span class="label">{{ $t('debug.generationSpeed') }}:</span>
                  <span class="value">{{ $t('debug.nCharsPerSec', { n: log.metrics.generationSpeed.toFixed(0) }) }}</span>
                </div>
              </div>

              <!-- 设备信息 -->
              <div class="section">
                <div class="section-title">{{ $t('debug.deviceInfo') }}</div>
                <div class="info-item">
                  <span class="label">Safari:</span>
                  <span class="value">{{ log.deviceInfo.isSafari ? '✅' : '❌' }}</span>
                </div>
                <div class="info-item">
                  <span class="label">PWA:</span>
                  <span class="value">{{ log.deviceInfo.isStandalone ? '✅' : '❌' }}</span>
                </div>
                <div class="info-item" v-if="log.deviceInfo.connection !== 'unknown'">
                  <span class="label">{{ $t('debug.networkType') }}:</span>
                  <span class="value">{{ log.deviceInfo.connection.effectiveType }}</span>
                </div>
                <div class="info-item" v-if="log.deviceInfo.connection !== 'unknown'">
                  <span class="label">{{ $t('debug.downloadSpeed') }}:</span>
                  <span class="value">{{ log.deviceInfo.connection.downlink }} Mbps</span>
                </div>
              </div>

              <!-- 错误信息 -->
              <div v-if="log.errors && log.errors.length > 0" class="section">
                <div class="section-title error-title">{{ $t('debug.errorInfo') }}</div>
                <div v-for="(error, idx) in log.errors" :key="idx" class="error-item">
                  <div class="error-message">{{ error.message }}</div>
                  <div class="error-context">{{ error.context }}</div>
                </div>
              </div>
            </div>
          </van-collapse-item>
        </van-collapse>
      </div>

      <van-empty v-else :description="$t('debug.noLogsYet')" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast, showDialog } from 'vant'

const { t } = useI18n()

const loading = ref(false)
const report = ref(null)
const logs = ref([])
const activeLog = ref(null)

/**
 * 生成诊断报告
 */
const generateReport = () => {
  loading.value = true

  try {
    // 从全局诊断工具获取数据
    if (!window.__ttsPerformanceLogger) {
      showToast({
        message: t('debug.toolNotInit'),
        position: 'top'
      })
      return
    }

    const logger = window.__ttsPerformanceLogger
    logs.value = logger.getAllLogs()

    if (logs.value.length === 0) {
      showToast({
        message: t('debug.noData'),
        position: 'top',
        duration: 3000
      })
      return
    }

    report.value = logger.generateReport()

    showToast({
      message: t('debug.reportGenerated'),
      icon: 'success'
    })
  } catch (error) {
    console.error('[Debug] 生成报告失败:', error)
    showToast({
      message: t('debug.reportFailed') + ': ' + error.message,
      position: 'top'
    })
  } finally {
    loading.value = false
  }
}

/**
 * 导出完整日志
 */
const exportLogs = () => {
  try {
    if (!window.__ttsPerformanceLogger) {
      showToast({ message: t('debug.toolNotInit'), position: 'top' })
      return
    }

    const allLogs = window.__ttsPerformanceLogger.getAllLogs()

    if (allLogs.length === 0) {
      showToast({ message: t('debug.noLogData'), position: 'top' })
      return
    }

    const json = JSON.stringify(allLogs, null, 2)

    // 创建下载链接
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tts-performance-logs-${Date.now()}.json`
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
 * 清除所有日志
 */
const clearLogs = () => {
  showDialog({
    title: t('debug.confirmClear'),
    message: t('debug.confirmClearDiag'),
    confirmButtonColor: '#ee0a24'
  }).then(() => {
    try {
      localStorage.removeItem('tts_performance_logs')
      report.value = null
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

// 页面加载时自动生成报告
onMounted(() => {
  generateReport()
})
</script>

<style scoped>
.debug-page {
  min-height: 100vh;
  background-color: #f7f8fa;
}

.content {
  padding: 16px;
}

.actions {
  margin-bottom: 16px;
}

.report {
  background: white;
  border-radius: 8px;
  padding: 16px;
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

.log-article {
  flex: 1;
  font-size: 14px;
  color: #646566;
}

.log-duration {
  font-size: 14px;
  color: #969799;
  font-weight: 500;
}

.log-detail {
  padding: 12px;
  background: #f7f8fa;
  border-radius: 4px;
}

.section {
  margin-bottom: 16px;
}

.section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 14px;
  font-weight: 500;
  color: #323233;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #ebedf0;
}

.error-title {
  color: #ee0a24;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
}

.info-item .label {
  color: #646566;
}

.info-item .value {
  color: #323233;
  font-weight: 500;
}

.error-item {
  background: white;
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.error-item:last-child {
  margin-bottom: 0;
}

.error-message {
  color: #ee0a24;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
}

.error-context {
  color: #969799;
  font-size: 12px;
}
</style>
