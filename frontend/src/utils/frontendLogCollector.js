/**
 * 前端日志收集器
 *
 * 功能：
 * 1. 拦截 console.log/warn/error
 * 2. 批量上传日志到后端（仅白名单用户）
 * 3. 自动过滤敏感信息
 *
 * 创建时间：2025-12-30
 */

import request from '@/api/request'

class FrontendLogCollector {
  constructor() {
    this.logs = []
    this.isEnabled = false
    this.uploadInterval = null
    this.originalConsole = {
      log: console.log,
      warn: console.warn,
      error: console.error
    }

    // 配置
    this.config = {
      maxLogsPerBatch: 20,  // ✅ 减小批量大小：50 → 20（避免请求过大）
      uploadIntervalMs: 15000,  // ✅ 增加上传频率：30s → 15s（避免积压）
      maxQueueSize: 100,  // ✅ 减小队列上限：200 → 100（避免内存占用）
      maxMessageLength: 1000  // ✅ 单条日志消息最大长度（字符）
    }
  }

  /**
   * 启动日志收集（仅白名单用户）
   */
  start() {
    if (this.isEnabled) {
      console.log('[LogCollector] Already started')
      return
    }

    this.isEnabled = true
    this.interceptConsole()
    this.startUploadTimer()

    console.log('[LogCollector] Started - logs will be uploaded to backend')
  }

  /**
   * 停止日志收集
   */
  stop() {
    if (!this.isEnabled) {
      return
    }

    this.isEnabled = false
    this.restoreConsole()
    this.stopUploadTimer()

    // 最后一次上传剩余日志
    if (this.logs.length > 0) {
      this.uploadLogs()
    }

    console.log('[LogCollector] Stopped')
  }

  /**
   * 拦截 console 方法
   */
  interceptConsole() {
    const self = this

    console.log = function(...args) {
      self.collectLog('info', args)
      self.originalConsole.log.apply(console, args)
    }

    console.warn = function(...args) {
      self.collectLog('warn', args)
      self.originalConsole.warn.apply(console, args)
    }

    console.error = function(...args) {
      self.collectLog('error', args)
      self.originalConsole.error.apply(console, args)
    }
  }

  /**
   * 恢复原始 console
   */
  restoreConsole() {
    console.log = this.originalConsole.log
    console.warn = this.originalConsole.warn
    console.error = this.originalConsole.error
  }

  /**
   * 判断是否为 Error / DOMException 等错误对象
   */
  isErrorLike(value) {
    return !!(
      value &&
      typeof value === 'object' &&
      (
        value instanceof Error ||
        typeof value.message === 'string' ||
        typeof value.stack === 'string' ||
        typeof value.name === 'string'
      )
    )
  }

  /**
   * 安全序列化日志参数
   */
  serializeArg(arg) {
    if (typeof arg === 'string') {
      return arg
    }

    if (this.isErrorLike(arg)) {
      const errorData = {
        name: arg.name,
        message: arg.message,
        stack: arg.stack,
        code: arg.code,
        line: arg.line,
        column: arg.column,
        sourceURL: arg.sourceURL
      }

      return JSON.stringify(errorData, null, 2)
    }

    if (typeof arg === 'object' && arg !== null) {
      const seen = new WeakSet()
      return JSON.stringify(arg, (key, value) => {
        if (this.isErrorLike(value)) {
          return {
            name: value.name,
            message: value.message,
            stack: value.stack,
            code: value.code,
            line: value.line,
            column: value.column,
            sourceURL: value.sourceURL
          }
        }

        if (typeof value === 'object' && value !== null) {
          if (seen.has(value)) {
            return '[Circular]'
          }
          seen.add(value)
        }

        if (typeof value === 'function') {
          return `[Function ${value.name || 'anonymous'}]`
        }

        return value
      }, 2)
    }

    return String(arg)
  }

  /**
   * 提取错误堆栈
   */
  extractStack(args) {
    const errorLikeArg = args.find(arg => this.isErrorLike(arg))
    return errorLikeArg?.stack || null
  }

  /**
   * 收集日志
   */
  collectLog(level, args) {
    if (!this.isEnabled) {
      return
    }

    try {
      // 将参数转换为字符串
      let message = args.map(arg => this.serializeArg(arg)).join(' ')

      // ✅ 限制消息长度（避免单条日志过大）
      if (message.length > this.config.maxMessageLength) {
        message = message.substring(0, this.config.maxMessageLength) + '... [truncated]'
      }

      // 过滤敏感信息
      const sanitizedMessage = this.sanitizeMessage(message)

      // 创建日志条目
      const logEntry = {
        timestamp: this.getTimestamp(),
        level,
        message: sanitizedMessage,
        context: {
          url: window.location.href,
          userAgent: navigator.userAgent,
          viewport: {
            width: window.innerWidth,
            height: window.innerHeight
          }
        }
      }

      // 如果是 error，尝试获取堆栈
      if (level === 'error') {
        const stack = this.extractStack(args)
        if (stack) {
          logEntry.stack = stack.substring(0, 1000)
        }
      }

      // 添加到队列
      this.logs.push(logEntry)

      // 超出队列大小限制，删除最旧的
      if (this.logs.length > this.config.maxQueueSize) {
        this.logs.shift()
      }

      // 如果队列满了，立即上传
      if (this.logs.length >= this.config.maxLogsPerBatch) {
        this.uploadLogs()
      }
    } catch (err) {
      // 日志收集失败，不影响主流程
      this.originalConsole.error('[LogCollector] Failed to collect log:', err)
    }
  }

  /**
   * 过滤敏感信息
   */
  sanitizeMessage(message) {
    let sanitized = message

    // 过滤 Token
    sanitized = sanitized.replace(/Bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+/gi, 'Bearer [FILTERED]')
    sanitized = sanitized.replace(/"token"\s*:\s*"[^"]+"/gi, '"token":"[FILTERED]"')
    sanitized = sanitized.replace(/"password"\s*:\s*"[^"]+"/gi, '"password":"[FILTERED]"')

    // 过滤手机号（中国）
    sanitized = sanitized.replace(/1[3-9]\d{9}/g, '1********')

    // 过滤邮箱
    sanitized = sanitized.replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '***@***.***')

    return sanitized
  }

  /**
   * 获取东八区时间戳
   */
  getTimestamp() {
    const now = new Date()
    const year = now.getFullYear()
    const month = String(now.getMonth() + 1).padStart(2, '0')
    const day = String(now.getDate()).padStart(2, '0')
    const hours = String(now.getHours()).padStart(2, '0')
    const minutes = String(now.getMinutes()).padStart(2, '0')
    const seconds = String(now.getSeconds()).padStart(2, '0')

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
  }

  /**
   * 启动上传定时器
   */
  startUploadTimer() {
    this.uploadInterval = setInterval(() => {
      if (this.logs.length > 0) {
        this.uploadLogs()
      }
    }, this.config.uploadIntervalMs)
  }

  /**
   * 停止上传定时器
   */
  stopUploadTimer() {
    if (this.uploadInterval) {
      clearInterval(this.uploadInterval)
      this.uploadInterval = null
    }
  }

  /**
   * 上传日志到后端
   */
  async uploadLogs() {
    if (this.logs.length === 0) {
      return
    }

    // 取出待上传的日志
    const logsToUpload = this.logs.splice(0, this.config.maxLogsPerBatch)

    try {
      const response = await request.post(
        '/api/v1/frontend-logs',
        { logs: logsToUpload },
        {
          // 日志上传属于后台诊断流，失败时不应打断用户，也不应触发全局 network toast。
          silent: true,
          headers: { 'X-Silent': '1' }
        }
      )

      // ✅ 修复：增加安全检查，避免 undefined 访问
      if (response?.data?.success) {
        this.originalConsole.log(`[LogCollector] Uploaded ${response.data.received_count} logs`)
      }
    } catch (error) {
      // 上传失败，重新加入队列（放回队首）
      this.logs.unshift(...logsToUpload)

      // 如果是 403 权限错误，停止收集
      if (error.response?.status === 403) {
        this.originalConsole.warn('[LogCollector] Not authorized - stopping log collection')
        this.stop()
      } else {
        // ✅ 修复：增强错误信息，避免二次错误
        const errorMsg = error?.message || String(error)
        this.originalConsole.error('[LogCollector] Upload failed:', errorMsg)
      }
    }
  }

  /**
   * 获取当前队列中的日志数量
   */
  getQueueSize() {
    return this.logs.length
  }

  /**
   * 清空日志队列
   */
  clearQueue() {
    this.logs = []
  }
}

// 导出单例
export const frontendLogCollector = new FrontendLogCollector()

// 导出到全局（方便控制台调试）
if (typeof window !== 'undefined') {
  window.__frontendLogCollector = frontendLogCollector
}
