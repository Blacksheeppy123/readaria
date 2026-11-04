<template>
  <div class="article-detail">
    <!-- 顶部导航栏 -->
    <van-nav-bar
      :title="$t('articles.title')"
      left-arrow
      @click-left="goBack"
    >
      <template #right>
        <!-- TTS 播放按钮 -->
        <van-icon
          name="play-circle-o"
          size="20"
          style="margin-right: 12px;"
          @click="playCurrentArticle"
        />
        <van-icon
          :name="isSaved ? 'star' : 'star-o'"
          size="20"
          style="margin-right: 12px;"
          @click="toggleSave"
        />
        <van-icon name="share-o" size="20" @click="shareArticle" />
      </template>
    </van-nav-bar>

    <!-- 错误提示 -->
    <div v-if="error" class="error-container">
      <van-empty :description="$t('articleDetail.loadFailed')">
        <van-button round type="primary" @click="loadArticle">{{ $t('articleDetail.reload') }}</van-button>
      </van-empty>
    </div>

    <!-- 骨架屏（更丝滑的过渡，占位不抖动） -->
    <div v-else-if="loading" class="article-content">
      <div class="article-header">
        <van-skeleton title :row="2" />
      </div>
      <div class="article-summary">
        <van-skeleton :row="3" />
      </div>
      <div class="article-body">
        <van-skeleton :row="8" />
      </div>
    </div>

    <!-- 文章内容（淡入过渡） -->
    <transition name="fade" mode="out-in" appear v-else>
    <div key="article" class="article-content" :key="display.url || article?.url">
      <!-- 文章头部 -->
      <div class="article-header">
        <h1 class="article-title">{{ display.title || article?.title }}</h1>
        <div class="article-meta">
          <span class="meta-item">
            <van-icon name="user-o" />
            {{ display.author || article?.author || resolvedSourceName || $t('common.unknown') }}
          </span>
          <span class="meta-item">
            <van-icon name="clock-o" />
            {{ formatDate(display.published_at || article?.published_at) }}
          </span>
          <span v-if="resolvedSourceName" class="meta-item">
            <van-icon name="label-o" />
            {{ resolvedSourceName }}
          </span>
        </div>
      </div>

      <!-- 文章摘要 -->
      <ArticleSummaryCard :summary="display.summary || article?.summary" />

      <div class="article-primary-actions">
        <van-button round type="primary" icon="volume-o" @click="playCurrentArticle">
          {{ $t('articleDetail.listenToThisArticle') }}
        </van-button>
        <van-button round plain icon="plus" @click="addCurrentToQueue">
          {{ $t('articles.addToQueue') }}
        </van-button>
      </div>

      <!-- 文章正文：无内容时仅展示骨架，避免正文二次跳变 -->
      <div class="article-body">
        <template v-if="hasContent">
          <transition name="fade" appear>
            <div key="body" v-html="sanitizedContent"></div>
          </transition>
        </template>
        <template v-else>
          <van-skeleton :row="8" />
        </template>
      </div>

      <!-- 原文链接 -->
      <div v-if="(display.url || article?.url)" class="original-link">
        <van-button block plain icon="link-o" @click="openOriginal">
          {{ $t('articleDetail.openOriginal') }}
        </van-button>
      </div>
    </div>
    </transition>

    <!-- 播放中：功能完整的迷你播放器 -->
    <div v-if="playerStore.currentArticle" class="mini-player-bar" @click="goToPlayer">
      <div class="mini-player-content">
        <!-- 标题（点击跳转播放器页面） -->
        <div class="mini-player-title" @click="goToPlayer">
          <span v-if="playerStore.isLoadingAudio">{{ $t('tts.generating') }}</span>
          <span v-else-if="playerStore.isActivatingFallback">{{ $t('tts.fallbackMode') }}</span>
          <span v-else>{{ playerStore.currentArticle.title || $t('player.nowPlaying') }}</span>
        </div>

        <!-- 加载中 / 播放暂停按钮 -->
        <van-loading
          v-if="playerStore.isLoadingAudio || playerStore.isActivatingFallback"
          type="spinner"
          size="22"
          color="#c75b39"
          @click.stop
        />
        <van-icon
          v-else
          :name="playerStore.isPaused ? 'play-circle' : 'pause-circle'"
          size="28"
          color="#c75b39"
          @click.stop="togglePlayPause"
        />

        <!-- 进度条 -->
        <van-progress
          :percentage="playerStore.progress"
          :show-pivot="false"
          stroke-width="2"
          color="#c75b39"
          class="mini-player-progress"
        />
      </div>

      <!-- 关闭按钮 -->
      <van-icon
        name="close"
        size="16"
        color="#9a674f"
        class="mini-player-close"
        @click.stop="stopPlayer"
      />
    </div>

    <!-- 底部操作栏 -->
    <div v-if="(display.url || article?.url) && !playerStore.currentArticle" class="action-bar">
      <van-button
        :icon="isSaved ? 'star' : 'star-o'"
        @click="toggleSave"
      >
        {{ isSaved ? $t('articleDetail.saved') : $t('articleDetail.save') }}
      </van-button>
      <van-button
        icon="share-o"
        @click="shareArticle"
      >
        {{ $t('articleDetail.share') }}
      </van-button>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showDialog } from 'vant'
import DOMPurify from 'dompurify'
import { useArticleStore } from '@/stores/articleStore'
import { useFeedStore } from '@/stores/feedStore'
import { usePlayerStore } from '@/stores/playerStore'
import { useQueueStore } from '@/stores/queueStore'
import { resolveSourceName } from '@/utils/sourceName'
import { trackArticleShared } from '@/utils/analytics'
import ArticleSummaryCard from '@/components/ArticleSummaryCard.vue'

export default {
  name: 'ArticleDetail',
  components: { ArticleSummaryCard },
  // 预取数据，进入组件前把文章准备好，减少闪烁
  async beforeRouteEnter(to, from, next) {
    const hasFullContent = (data) => !!(data && data.content && String(data.content).trim().length > 0)
    const mergeArticleData = (fallbackArticle, fullArticle) => ({
      ...(fallbackArticle || {}),
      ...(fullArticle || {}),
      content: fullArticle?.content || fallbackArticle?.content || ''
    })

    const prefetch = async () => {
      try {
        // 1) 来自路由 state
        const stateArticle = to && to.state && to.state.article
        if (stateArticle && hasFullContent(stateArticle)) {
          return { article: stateArticle }
        }

        // 2) 解码路由参数并从 sessionStorage 读取
        let rawParam = String(to.params?.id || stateArticle?.url || '')
        let decoded = rawParam
        try {
          decoded = decodeURIComponent(decoded)
        } catch (_) {
          decoded = rawParam
        }
        const url = stateArticle?.url || decoded
        if (url) {
          const key = `article_${encodeURIComponent(url)}`
          const cached = sessionStorage.getItem(key)
          if (cached) {
            const cachedArticle = JSON.parse(cached)
            if (hasFullContent(cachedArticle)) {
              return { article: mergeArticleData(stateArticle, cachedArticle) }
            }
          }
        }

        // 3) API 获取
        if (url) {
          const { getArticleByUrl } = await import('@/api/feeds')
          const resp = await getArticleByUrl(url)
          if (resp && resp.article) {
            return { article: mergeArticleData(stateArticle, resp.article) }
          }
        }

        // 4) 搜索兜底
        if (url) {
          const { searchArticles } = await import('@/api/feeds')
          let keyword = url
          const m = url.match(/(\d{15,})/)
          if (m) keyword = m[1]
          const results = await searchArticles(keyword, 10)
          if (Array.isArray(results) && results.length) {
            const exact = results.find(a => a.url === url) || results[0]
            return { article: mergeArticleData(stateArticle, exact) }
          }
        }

        return { article: stateArticle || null }
      } catch (_) {
        return { article: null }
      }
    }

    const data = await prefetch()
    next(vm => {
      if (data.article) {
        vm.setArticleData(data.article)
      } else {
        vm.setLoadError()
      }
    })
  },
  setup() {
    const route = useRoute()
    const router = useRouter()
    const { t } = useI18n()
    const articleStore = useArticleStore()
    const feedStore = useFeedStore()
    const playerStore = usePlayerStore()
    const queueStore = useQueueStore()

    // 展示用头部信息（稳定不抖动）
    const display = ref({ title: '', summary: '', author: '', published_at: '', source: '', source_name: '', url: '' })
    // 完整文章对象（含正文等富内容）
    const article = ref(null)
    const loading = ref(true)
    const error = ref(false)
    const isSaved = ref(false)

    const toDisplayState = (data = {}, fallback = {}) => ({
      title: data.title ?? fallback.title ?? '',
      summary: data.summary ?? fallback.summary ?? '',
      author: data.author ?? fallback.author ?? '',
      published_at: data.published_at ?? fallback.published_at ?? '',
      source: data.source ?? fallback.source ?? '',
      source_name: data.source_name ?? fallback.source_name ?? '',
      url: data.url ?? fallback.url ?? ''
    })

    const scrollToTop = async () => {
      await nextTick()
      const contentEl = document.querySelector('.content')
      if (contentEl) {
        contentEl.scrollTo({ top: 0, behavior: 'auto' })
      }
      window.scrollTo({ top: 0, behavior: 'auto' })
      document.documentElement.scrollTop = 0
      document.body.scrollTop = 0
    }

    // 从路由参数获取文章数据
    let hasLoaded = false
    let headerLocked = false
    // 若全局 store 已有当前文章，直接同步渲染，避免首帧骨架
    try {
      const pre = articleStore.current
      if (pre && pre.url) {
        // 固定头部展示
        display.value = toDisplayState(pre)
        headerLocked = true
        article.value = pre
        loading.value = false
        error.value = false
        if (hasFullContent(pre)) {
          hasLoaded = true
        }
      }
    } catch (_) {}
    const hasFullContent = (data) => !!(data && data.content && String(data.content).trim().length > 0)

    const fetchFullContent = async (articleUrl) => {
      try {
        const { getArticleByUrl } = await import('@/api/feeds')
        const response = await getArticleByUrl(articleUrl)

        if (response && response.article) {
          if (!headerLocked) {
            display.value = toDisplayState(response.article, display.value)
            headerLocked = true
          }
          article.value = article.value || {}
          article.value.content = response.article.content || article.value.content
          loading.value = false
          hasLoaded = true
          await scrollToTop()
          console.log('✅ 通过API成功获取文章:', response.article.title)
        } else {
          console.error('❌ API返回的数据格式不正确')
          error.value = true
          loading.value = false
        }
      } catch (apiError) {
        console.error('❌ API获取失败，尝试搜索备用方案:', apiError)

        const { searchArticles } = await import('@/api/feeds')

        let searchKeyword = articleUrl
        const urlMatch = articleUrl.match(/(\d{15,})/)
        if (urlMatch) {
          searchKeyword = urlMatch[1]
          console.log('提取ID作为搜索关键词:', searchKeyword)
        }

        const results = await searchArticles(searchKeyword, 10)

        if (results && results.length > 0) {
          console.log('搜索返回结果数量:', results.length)
          console.log('搜索结果URL列表:', results.map(r => r.url))

          let foundArticle = results.find(a => a.url === articleUrl)

          if (!foundArticle && urlMatch) {
            const targetId = urlMatch[1]
            foundArticle = results.find(a => a.url && a.url.includes(targetId))
            if (foundArticle) {
              console.log('✅ 通过ID匹配找到文章:', foundArticle.url)
            }
          }

          if (!foundArticle) {
            console.warn('URL和ID匹配都失败，使用第一个搜索结果')
            foundArticle = results[0]
          }

          if (!headerLocked) {
            display.value = toDisplayState(foundArticle, display.value)
            headerLocked = true
          }
          article.value = article.value || {}
          article.value.content = foundArticle.content || article.value?.content
          loading.value = false
          hasLoaded = true
          await scrollToTop()
          console.log('✅ 通过搜索找到文章:', foundArticle.title)
        } else {
          console.error('❌ 未找到文章')
          error.value = true
          loading.value = false
        }
      }
    }

    const loadArticle = async () => {
      if (hasLoaded) return

      // If we already have article data but missing content, hydrate in background
      if (article.value?.url && !hasFullContent(article.value)) {
        await fetchFullContent(article.value.url)
        return
      }
      // If we already have full content, just mark loaded
      if (hasFullContent(article.value)) {
        hasLoaded = true
        return
      }

      loading.value = true
      error.value = false
      await scrollToTop()

      // 调试信息
      console.log('ArticleDetail loadArticle called')
      console.log('route.params:', route.params)
      console.log('history.state:', history.state)

      try {
        // 优先级1: 从 history.state 获取传递的数据
        let articleData = history.state.article

        if (articleData) {
          console.log('✅ 从 history.state 获取文章数据')
          if (!headerLocked) {
            display.value = toDisplayState(articleData, display.value)
            headerLocked = true
          }
          article.value = articleData
          if (hasFullContent(articleData)) {
            loading.value = false
            hasLoaded = true
            await scrollToTop()
            return
          }
          // 缺少完整内容，继续通过API获取
          const url = articleData.url
          if (url) {
            await fetchFullContent(url)
            return
          }
        } else {
          // 优先级2: 从 sessionStorage 获取备份数据
          // 还原为原始URL
          let rawParam = String(route.params.id || '')
          let decoded = rawParam
          try {
            decoded = decodeURIComponent(decoded)
          } catch (_) {
            decoded = rawParam
          }
          const articleUrl = decoded
          const articleKey = `article_${encodeURIComponent(articleUrl)}`
          const cachedData = sessionStorage.getItem(articleKey)

            if (cachedData) {
              console.log('✅ 从 sessionStorage 获取文章数据')
              articleData = JSON.parse(cachedData)
              if (!headerLocked) {
                display.value = toDisplayState(articleData, display.value)
                headerLocked = true
              }
              article.value = articleData
              if (hasFullContent(articleData)) {
                loading.value = false
                hasLoaded = true
                await scrollToTop()
              } else {
                await fetchFullContent(articleData.url)
              }
              // 不立即删除，保留作为缓存（30分钟后自动过期）
              // sessionStorage.removeItem(articleKey)
            } else {
            // 优先级3: 通过文章详情API获取
            console.warn('⚠️  未从 state/sessionStorage 获取文章数据，尝试通过API获取...')
            console.log('尝试通过API获取文章 URL:', articleUrl)
            await fetchFullContent(articleUrl)
          }
        }
      } catch (e) {
        console.error('加载文章失败:', e)
        error.value = true
        loading.value = false
      }
      // 尝试标记为已读并获取收藏状态
      try {
        if (article.value?.url) {
          const { markReadByUrl, isArticleSaved } = await import('@/api/feeds')
          // 标记为已读（静默），并广播事件以便列表即时更新样式
          try {
            await markReadByUrl(article.value.url)
          } catch (_) {}
          // 事件 + 本地缓存，双通道通知列表页更新样式
          try {
            const url = article.value.url
            window.dispatchEvent(new CustomEvent('article-read', { detail: { url } }))
            // 写入最近已读URL缓存
            const key = 'read_urls_cache'
            const raw = sessionStorage.getItem(key)
            const arr = Array.isArray(JSON.parse(raw || '[]')) ? JSON.parse(raw || '[]') : []
            if (!arr.includes(url)) {
              arr.unshift(url)
              if (arr.length > 100) arr.length = 100
              sessionStorage.setItem(key, JSON.stringify(arr))
            }
            sessionStorage.setItem('last_read_url', url)
          } catch (_) {}
          // 查询收藏状态
          const status = await isArticleSaved(article.value.url)
          if (typeof status.saved === 'boolean') {
            isSaved.value = status.saved
          }
        }
      } catch (e) {
        // 静默失败
        console.debug('读取收藏/已读状态失败', e)
      }
    }

    // 提供给 beforeRouteEnter 调用，避免首次闪烁
    const setArticleData = async (data) => {
      if (!headerLocked && data) {
        display.value = toDisplayState(data, display.value)
        headerLocked = true
      }
      article.value = data || article.value
      loading.value = false
      error.value = false
      if (hasFullContent(data)) {
        hasLoaded = true
      }
      await scrollToTop()
      try {
        const currentUrl = display.value?.url || article.value?.url
        if (currentUrl) {
          const { markReadByUrl, isArticleSaved } = await import('@/api/feeds')
          markReadByUrl(currentUrl).catch(() => {})
          const status = await isArticleSaved(currentUrl)
          if (typeof status.saved === 'boolean') isSaved.value = status.saved
        }
      } catch (_) {}
    }

    const setLoadError = () => {
      loading.value = false
      error.value = true
      hasLoaded = true
    }


    // 从 source URL 提取订阅源名称
    const getSourceName = (sourceUrl) => {
      if (!sourceUrl) return t('common.unknownSource')
      return resolveSourceName(feedStore.feeds, sourceUrl) || t('common.unknownSource')
    }

    const resolvedSourceName = computed(() => {
      const explicitSourceName = display.value?.source_name || article.value?.source_name
      if (explicitSourceName) return explicitSourceName
      const sourceUrl = display.value?.source || article.value?.source
      if (!sourceUrl) return ''
      return getSourceName(sourceUrl)
    })

    // 格式化日期
    const formatDate = (dateStr) => {
      if (!dateStr) return t('common.unknown')

      const date = new Date(dateStr)
      const now = new Date()
      const diff = now - date

      // 小于1分钟
      if (diff < 60000) {
        return t('common.justNow')
      }
      // 小于1小时
      if (diff < 3600000) {
        return t('common.minutesAgo', { n: Math.floor(diff / 60000) })
      }
      // 小于1天
      if (diff < 86400000) {
        return t('common.hoursAgo', { n: Math.floor(diff / 3600000) })
      }
      // 小于2天
      if (diff < 172800000) {
        return t('common.yesterday')
      }
      // 小于7天
      if (diff < 604800000) {
        return t('common.daysAgo', { n: Math.floor(diff / 86400000) })
      }

      // 格式化为完整日期
      return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
    }

    // 清理和格式化内容
    const hasContent = computed(() => !!(article.value && article.value.content && String(article.value.content).trim().length))
    const sanitizedContent = computed(() => {
      if (!article.value?.content) return `<p>${t('articleDetail.noContent')}</p>`

      let content = String(article.value.content)

      // 如果内容是纯文本，转换为HTML段落
      if (!content.includes('<')) {
        content = content.split('\n').map(p => `<p>${p}</p>`).join('')
      }

      // 基础增强：
      // 1) 将 <img> 的 data-src/lazy-src 等替换为 src
      content = content.replace(/<img([^>]*?)(data-src|data-original|data-url|lazy-src)=("|')([^"']+)("|')/gi, (
        _m, pre, _attr, q1, url, q2
      ) => `<img${pre}src=${q1}${url}${q2}`)

      // 2) 协议相对地址 //example.com -> https://example.com
      content = content.replace(/<img([^>]*?)src=("|')\/\/([^"']+)("|')/gi, (
        _m, pre, q1, hostpath, q2
      ) => `<img${pre}src=${q1}https://${hostpath}${q2}`)

      // 3) 给所有 <img> 添加 no-referrer 和懒加载
      content = content.replace(/<img(?![^>]*referrerpolicy)([^>]*)>/gi, '<img referrerpolicy="no-referrer" loading="lazy"$1>')

      // 4) XSS 防护：使用 DOMPurify 白名单过滤
      content = DOMPurify.sanitize(content, {
        ADD_ATTR: ['referrerpolicy', 'loading', 'target'],
      })

      return content
    })

    // 返回上一页
    const goBack = () => {
      router.back()
    }

    // 打开原文
    const openOriginal = () => {
      const currentUrl = (typeof display !== 'undefined' && display.value?.url) || article.value?.url
      if (currentUrl) {
        window.open(currentUrl, '_blank')
      }
    }

    // 切换收藏状态
    const toggleSave = async () => {
      const currentUrl = (typeof display !== 'undefined' && display.value?.url) || article.value?.url
      if (!currentUrl) return
      try {
        const { saveArticleByUrl, unsaveArticleByUrl } = await import('@/api/feeds')
        if (isSaved.value) {
          await unsaveArticleByUrl(currentUrl)
          isSaved.value = false
          showToast({ message: t('articleDetail.unsaveSuccess'), icon: 'info' })
        } else {
          await saveArticleByUrl(currentUrl)
          isSaved.value = true
          showToast({ message: t('articleDetail.saveSuccess'), icon: 'success' })
        }
      } catch (e) {
        showToast(t('common.operationFailed'))
      }
    }

    // 分享文章
    const shareArticle = () => {
      const currentUrl = (typeof display !== 'undefined' && display.value?.url) || article.value?.url
      if (currentUrl) {
        // 使用Web Share API（如果支持）
        if (navigator.share) {
          navigator.share({
            title: display.value?.title || article.value?.title || '',
            text: display.value?.summary || article.value?.summary || '',
            url: currentUrl
          })
          .then(() => {
            trackArticleShared('native_share')
          })
          .catch(err => {
            // 用户取消分享或不支持，回退到复制链接
            copyLink()
          })
        } else {
          // 不支持Web Share API，直接复制链接
          copyLink()
        }
      } else {
        showToast(t('articleDetail.noShareLink'))
      }
    }

    // 复制链接
    const copyLink = () => {
      const currentUrl = (typeof display !== 'undefined' && display.value?.url) || article.value?.url
      if (currentUrl) {
        trackArticleShared('copy_link')
        navigator.clipboard.writeText(currentUrl)
          .then(() => {
            showToast(t('articleDetail.copySuccess'))
          })
          .catch(() => {
            showToast(t('articleDetail.copyFailed'))
          })
      }
    }

    // 播放当前文章 (新的 TTS 系统)
    const playCurrentArticle = () => {
      if (!article.value && !display.value) {
        showToast(t('articleDetail.articleNotLoaded'))
        return
      }

      // 合并 display 和 article 数据，确保 url 等字段完整
      const playTarget = {
        ...article.value,
        url: (typeof display !== 'undefined' && display.value?.url) || article.value?.url,
        title: (typeof display !== 'undefined' && display.value?.title) || article.value?.title,
      }

      // 调用 Player Store 播放当前文章
      // 不再显示乐观 toast，由迷你播放条的 loading / paused 状态提供真实反馈
      playerStore.playArticle(playTarget)
    }

    const addCurrentToQueue = () => {
      const queueTarget = {
        ...article.value,
        url: display.value?.url || article.value?.url,
        title: display.value?.title || article.value?.title,
        summary: display.value?.summary || article.value?.summary,
        source: display.value?.source || article.value?.source,
      }
      queueStore.addToQueue(queueTarget)
    }

    const goToPlayer = () => {
      router.push({ name: 'player' })
    }

    const togglePlayPause = () => {
      playerStore.togglePlayPause()
    }

    const stopPlayer = () => {
      playerStore.stop()
    }

    // 页面卸载时停止朗读（由 playerStore 管理，这里仅清理 articleStore）
    onUnmounted(() => {
      try {
        articleStore.clear()
      } catch (_) {}
    })

    onMounted(async () => {
      await scrollToTop()
      // 确保订阅列表已加载，用于 source 名称映射
      if (feedStore.feeds.length === 0) {
        try {
          await feedStore.fetchFeeds()
        } catch (error) {
          console.error('加载订阅列表失败:', error)
        }
      }
      await loadArticle()

      // 从播放器页导航过来时，恢复被 Android 系统暂停的播放
      if (sessionStorage.getItem('tts_navigate_keep_playing') === 'true') {
        sessionStorage.removeItem('tts_navigate_keep_playing')
        // 延迟恢复，确保页面渲染完成且音频状态已同步
        setTimeout(() => {
          if (playerStore.isPaused && playerStore.currentArticle) {
            playerStore.togglePlayPause()
          }
        }, 200)
      }
    })

    return {
      display,
      article,
      loading,
      error,
      isSaved,
      hasContent,
      sanitizedContent,
      formatDate,
      getSourceName,
      resolvedSourceName,
      goBack,
      openOriginal,
      toggleSave,
      shareArticle,
      loadArticle,
      setArticleData,
      setLoadError,
      // 新的 TTS
      playCurrentArticle,
      addCurrentToQueue,
      goToPlayer,
      togglePlayPause,
      stopPlayer,
      playerStore,
      t
    }
  }
}
</script>

<style scoped>
.article-detail {
  min-height: 100vh;
  background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%);
  padding-bottom: 92px;
  color: var(--readaria-ink);
}

/* 进入/离开淡入动画，尽量短以降低感知 */
.fade-enter-active, .fade-leave-active { transition: opacity .16s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.loading-container,
.error-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}

.article-content {
  background: transparent;
}

.article-header {
  padding: 22px 18px 14px;
  border-bottom: 0;
}

.article-title {
  font-family: var(--readaria-serif);
  font-size: 30px;
  font-weight: 600;
  line-height: 1.08;
  margin: 0 0 12px 0;
  color: var(--readaria-ink);
}

.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  color: var(--readaria-muted);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.article-summary {
  margin: 0 16px 16px;
}

.article-primary-actions {
  padding: 0 16px 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.article-primary-actions .van-button {
  flex: 1;
  min-width: 150px;
}

.article-body {
  padding: 4px 18px 18px;
  font-size: 16px;
  line-height: 1.8;
  color: var(--readaria-ink);
  word-wrap: break-word;
}

/* 文章内容样式 */
.article-body :deep(p) {
  margin: 0 0 16px 0;
}

.article-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 14px;
  margin: 12px 0;
  box-shadow: 0 12px 26px rgba(64, 45, 31, 0.12);
}

.article-body :deep(a) {
  color: var(--readaria-accent);
  text-decoration: none;
}

.article-body :deep(h1),
.article-body :deep(h2),
.article-body :deep(h3) {
  margin: 20px 0 12px 0;
  font-weight: 600;
}

.article-body :deep(h1) {
  font-size: 20px;
}

.article-body :deep(h2) {
  font-size: 18px;
}

.article-body :deep(h3) {
  font-size: 16px;
}

.article-body :deep(ul),
.article-body :deep(ol) {
  padding-left: 20px;
  margin: 12px 0;
}

.article-body :deep(li) {
  margin: 8px 0;
}

.article-body :deep(blockquote) {
  border-left: 4px solid var(--readaria-accent);
  padding-left: 16px;
  margin: 16px 0;
  color: var(--readaria-muted);
  background: rgba(255, 252, 248, 0.8);
  padding: 12px 16px;
  border-radius: 12px;
}

.article-body :deep(code) {
  background: var(--readaria-stone);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
}

.article-body :deep(pre) {
  background: var(--readaria-stone);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
}

.article-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.original-link {
  padding: 16px;
  border-top: 1px solid rgba(23, 33, 48, 0.08);
}

.mini-player-bar {
  position: fixed;
  left: 12px;
  right: 12px;
  bottom: max(14px, env(safe-area-inset-bottom));
  z-index: 1001;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 18px;
  background: rgba(23, 33, 48, 0.94);
  color: var(--readaria-paper);
  box-shadow: 0 18px 34px rgba(23, 33, 48, 0.2);
}

.mini-player-content {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  overflow: hidden;
}

.mini-player-title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgba(248, 242, 232, 0.9);
  cursor: pointer;
}

.mini-player-progress {
  width: 50px;
  flex-shrink: 0;
}

.mini-player-close {
  flex-shrink: 0;
  cursor: pointer;
  color: rgba(248, 242, 232, 0.6);
}

.mini-player-close:hover {
  color: rgba(248, 242, 232, 0.9);
}

.action-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: rgba(255, 252, 248, 0.96);
  border-top: 1px solid var(--readaria-border);
  box-shadow: 0 -8px 24px rgba(64, 45, 31, 0.08);
  z-index: 1000;
}

.action-bar .van-button {
  flex: 1;
}
</style>
