/**
 * TTS 性能诊断工具
 * 用于收集 iPhone Safari 上的播放性能数据
 *
 * 创建时间：2025-12-16
 * 目的：定位 iPhone 播放慢/失败的根本原因
 */

export class TTSPerformanceLogger {
  constructor() {
    this.logs = []
    this.currentSession = null
  }

  /**
   * 开始新的播放会话
   */
  startSession(articleId, textLength) {
    this.currentSession = {
      articleId,
      textLength,
      startTime: performance.now(),
      timestamps: {},
      errors: [],
      deviceInfo: {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        memory: navigator.deviceMemory || 'unknown',
        connection: navigator.connection ? {
          effectiveType: navigator.connection.effectiveType,
          downlink: navigator.connection.downlink,
          rtt: navigator.connection.rtt
        } : 'unknown',
        isSafari: /^((?!chrome|android).)*safari/i.test(navigator.userAgent),
        isStandalone: window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight
        }
      }
    }
  }

  /**
   * 记录时间戳
   * @param {string} event - 事件名称
   * @param {object} data - 附加数据
   */
  logEvent(event, data = {}) {
    if (!this.currentSession) return

    const timestamp = performance.now()
    const elapsed = timestamp - this.currentSession.startTime

    this.currentSession.timestamps[event] = {
      time: timestamp,
      elapsed,
      ...data
    }

    console.log(`[TTS Performance] ${event}: ${elapsed.toFixed(0)}ms`, data)
  }

  /**
   * 记录错误
   */
  logError(error, context) {
    if (!this.currentSession) return

    this.currentSession.errors.push({
      message: error.message,
      stack: error.stack?.substring(0, 200),
      context,
      timestamp: performance.now()
    })
  }

  /**
   * 结束会话并上传日志
   */
  async endSession(status = 'success') {
    if (!this.currentSession) return

    const session = {
      ...this.currentSession,
      status,
      totalDuration: performance.now() - this.currentSession.startTime
    }

    // 计算关键指标
    const metrics = this.calculateMetrics(session)
    session.metrics = metrics

    // 保存到本地
    this.logs.push(session)
    this.saveToLocalStorage()

    // 打印摘要
    this.printSummary(session)

    // 上传到后端（可选）
    try {
      await this.uploadToServer(session)
    } catch (err) {
      console.warn('[TTS Performance] 上传日志失败:', err)
    }

    this.currentSession = null
  }

  /**
   * 计算关键性能指标
   */
  calculateMetrics(session) {
    const { timestamps, textLength } = session

    return {
      // 缓存检查耗时
      cacheCheckDuration: timestamps.cacheChecked ?
        timestamps.cacheChecked.elapsed : 0,

      // API 调用耗时（如果未命中缓存）
      apiCallDuration: timestamps.apiCallComplete && timestamps.apiCallStart ?
        timestamps.apiCallComplete.elapsed - timestamps.apiCallStart.elapsed : 0,

      // 音频下载耗时
      downloadDuration: timestamps.audioDownloaded && timestamps.apiCallComplete ?
        timestamps.audioDownloaded.elapsed - timestamps.apiCallComplete.elapsed : 0,

      // IndexedDB 写入耗时
      indexedDBWriteDuration: timestamps.indexedDBWriteComplete && timestamps.indexedDBWriteStart ?
        timestamps.indexedDBWriteComplete.elapsed - timestamps.indexedDBWriteStart.elapsed : 0,

      // 音频设置耗时（Blob URL 创建）
      audioSetupDuration: timestamps.audioSetup && timestamps.audioDownloaded ?
        timestamps.audioSetup.elapsed - timestamps.audioDownloaded.elapsed : 0,

      // canplay 等待时间
      canplayWaitDuration: timestamps.canplayTriggered && timestamps.audioSetup ?
        timestamps.canplayTriggered.elapsed - timestamps.audioSetup.elapsed : 0,

      // 首次播放延迟（总时间）
      totalLoadDuration: timestamps.playStarted ?
        timestamps.playStarted.elapsed : session.totalDuration,

      // 平均生成速度（字符/秒）
      generationSpeed: timestamps.apiCallComplete && timestamps.apiCallStart ?
        textLength / ((timestamps.apiCallComplete.elapsed - timestamps.apiCallStart.elapsed) / 1000) : 0,

      // 音频大小（KB）
      audioBlobSize: timestamps.audioDownloaded?.blobSize ?
        (timestamps.audioDownloaded.blobSize / 1024).toFixed(1) : 0,

      // 是否命中缓存
      cacheHit: timestamps.cacheHit?.hit || false
    }
  }

  /**
   * 打印性能摘要
   */
  printSummary(session) {
    const { metrics, deviceInfo, status, errors } = session

    console.group(`📊 [TTS Performance Summary] ${status.toUpperCase()}`)

    console.log('设备信息:', {
      平台: deviceInfo.platform,
      Safari: deviceInfo.isSafari ? '✅' : '❌',
      PWA: deviceInfo.isStandalone ? '✅' : '❌',
      网络: deviceInfo.connection !== 'unknown' ?
        `${deviceInfo.connection.effectiveType} (${deviceInfo.connection.downlink}Mbps, RTT ${deviceInfo.connection.rtt}ms)` :
        'unknown'
    })

    console.log('性能指标:', {
      '总加载时间': `${metrics.totalLoadDuration.toFixed(0)}ms`,
      '缓存命中': metrics.cacheHit ? '✅' : '❌',
      'API 调用': `${metrics.apiCallDuration.toFixed(0)}ms`,
      '音频下载': `${metrics.downloadDuration.toFixed(0)}ms`,
      '音频大小': `${metrics.audioBlobSize}KB`,
      'IndexedDB 写入': `${metrics.indexedDBWriteDuration.toFixed(0)}ms`,
      'canplay 等待': `${metrics.canplayWaitDuration.toFixed(0)}ms`,
      '生成速度': `${metrics.generationSpeed.toFixed(0)} 字符/秒`
    })

    if (errors.length > 0) {
      console.error('错误列表:', errors)
    }

    console.groupEnd()
  }

  /**
   * 保存到 localStorage
   */
  saveToLocalStorage() {
    try {
      // 只保留最近 20 条记录
      const recentLogs = this.logs.slice(-20)
      localStorage.setItem('tts_performance_logs', JSON.stringify(recentLogs))
    } catch (err) {
      console.warn('[TTS Performance] 保存日志到 localStorage 失败:', err)
    }
  }

  /**
   * 从 localStorage 加载历史日志
   */
  loadFromLocalStorage() {
    try {
      const saved = localStorage.getItem('tts_performance_logs')
      if (saved) {
        this.logs = JSON.parse(saved)
      }
    } catch (err) {
      console.warn('[TTS Performance] 加载历史日志失败:', err)
    }
  }

  /**
   * 上传到服务器
   */
  async uploadToServer(session) {
    // TODO: 实现服务器端点 POST /api/v1/analytics/tts-performance
    // 暂时只在本地记录
    return Promise.resolve()
  }

  /**
   * 获取所有日志（供调试使用）
   */
  getAllLogs() {
    return this.logs
  }

  /**
   * 生成诊断报告
   */
  generateReport() {
    const logs = this.logs

    if (logs.length === 0) {
      return '暂无性能日志'
    }

    const report = {
      totalSessions: logs.length,
      successCount: logs.filter(l => l.status === 'success').length,
      failureCount: logs.filter(l => l.status === 'error').length,
      cacheHitRate: `${((logs.filter(l => l.metrics.cacheHit).length / logs.length) * 100).toFixed(1)}%`,
      avgLoadTime: {
        all: `${(logs.reduce((sum, l) => sum + l.metrics.totalLoadDuration, 0) / logs.length).toFixed(0)}ms`,
        cacheHit: `${(logs.filter(l => l.metrics.cacheHit).reduce((sum, l) => sum + l.metrics.totalLoadDuration, 0) / logs.filter(l => l.metrics.cacheHit).length || 0).toFixed(0)}ms`,
        cacheMiss: `${(logs.filter(l => !l.metrics.cacheHit).reduce((sum, l) => sum + l.metrics.totalLoadDuration, 0) / logs.filter(l => !l.metrics.cacheHit).length || 0).toFixed(0)}ms`
      },
      deviceDistribution: {
        Safari: logs.filter(l => l.deviceInfo.isSafari).length,
        PWA: logs.filter(l => l.deviceInfo.isStandalone).length
      },
      commonErrors: this.getMostCommonErrors(logs)
    }

    console.table(report)
    return report
  }

  /**
   * 获取最常见的错误
   */
  getMostCommonErrors(logs) {
    const errorCounts = {}

    logs.forEach(log => {
      log.errors.forEach(error => {
        const key = error.message
        errorCounts[key] = (errorCounts[key] || 0) + 1
      })
    })

    return Object.entries(errorCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([message, count]) => ({ message, count }))
  }
}

// 导出单例
export const performanceLogger = new TTSPerformanceLogger()

// 页面加载时恢复历史日志
performanceLogger.loadFromLocalStorage()

// 导出到全局（方便控制台调试）
if (typeof window !== 'undefined') {
  window.__ttsPerformanceLogger = performanceLogger
}
