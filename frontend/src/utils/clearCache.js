/**
 * 清理所有 TTS 音频缓存
 * 用于解决格式变更后的兼容性问题
 */
export async function clearAllTtsCache() {
  const results = []

  try {
    // 1. 清理 IndexedDB (TTS 音频缓存)
    const dbName = 'ttsAudioCache'
    await new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(dbName)
      request.onsuccess = () => {
        results.push(`✅ IndexedDB '${dbName}' 已删除`)
        resolve()
      }
      request.onerror = () => {
        results.push(`❌ IndexedDB '${dbName}' 删除失败: ${request.error}`)
        reject(request.error)
      }
      request.onblocked = () => {
        results.push(`⚠️  IndexedDB '${dbName}' 被阻止（请关闭其他标签页）`)
        reject(new Error('Database blocked'))
      }
    })
  } catch (error) {
    results.push(`❌ IndexedDB 清理错误: ${error.message}`)
  }

  try {
    // 2. 清理 localStorage (TTS 相关配置和日志)
    const keysToRemove = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key.startsWith('tts_') || key.startsWith('audio_') || key.includes('playback') || key.startsWith('debug_logs_')) {
        keysToRemove.push(key)
      }
    }

    keysToRemove.forEach(key => localStorage.removeItem(key))
    results.push(`✅ localStorage 已清理 ${keysToRemove.length} 项`)
  } catch (error) {
    results.push(`❌ localStorage 清理错误: ${error.message}`)
  }

  try {
    // 3. 清理 sessionStorage (文章缓存、过滤状态等)
    const sessionKeysToRemove = []
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)
      if (key.startsWith('article_') || key.includes('tts') || key.includes('audio')) {
        sessionKeysToRemove.push(key)
      }
    }

    sessionKeysToRemove.forEach(key => sessionStorage.removeItem(key))
    results.push(`✅ sessionStorage 已清理 ${sessionKeysToRemove.length} 项`)
  } catch (error) {
    results.push(`❌ sessionStorage 清理错误: ${error.message}`)
  }

  try {
    // 4. 吊销所有 Blob URLs（释放内存）
    if (window.URL && window.URL.revokeObjectURL) {
      // 注意：我们无法枚举已创建的 Blob URLs，只能在代码中手动管理
      results.push(`⚠️  Blob URLs 需要页面重新加载才能完全释放`)
    }
  } catch (error) {
    results.push(`❌ Blob URL 清理错误: ${error.message}`)
  }

  console.log('[Cache Clear] 清理完成：')
  results.forEach(msg => console.log(msg))

  return {
    success: !results.some(r => r.startsWith('❌')),
    results
  }
}

/**
 * 获取当前缓存统计信息
 */
export async function getCacheStats() {
  const stats = {
    indexedDB: { exists: false, size: 0 },
    localStorage: { count: 0, estimatedSize: 0 },
    sessionStorage: { count: 0, estimatedSize: 0 }
  }

  try {
    // 检查 IndexedDB
    const databases = await indexedDB.databases()
    const ttsDb = databases.find(db => db.name === 'ttsAudioCache')
    if (ttsDb) {
      stats.indexedDB.exists = true
      stats.indexedDB.version = ttsDb.version
    }
  } catch (error) {
    console.warn('无法获取 IndexedDB 信息:', error)
  }

  try {
    // 统计 localStorage
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key.startsWith('tts_') || key.startsWith('audio_') || key.startsWith('debug_logs_')) {
        stats.localStorage.count++
        stats.localStorage.estimatedSize += localStorage.getItem(key).length
      }
    }
  } catch (error) {
    console.warn('无法获取 localStorage 信息:', error)
  }

  try {
    // 统计 sessionStorage
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i)
      if (key.startsWith('article_') || key.includes('tts')) {
        stats.sessionStorage.count++
        stats.sessionStorage.estimatedSize += sessionStorage.getItem(key).length
      }
    }
  } catch (error) {
    console.warn('无法获取 sessionStorage 信息:', error)
  }

  return stats
}
