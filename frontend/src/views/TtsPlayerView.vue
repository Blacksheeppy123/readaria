<template>
  <div class="tts-player-page">
    <!-- 顶部导航栏 -->
    <van-nav-bar
      :title="$t('player.nowPlaying')"
      left-arrow
      @click-left="goBack"
    />

    <!-- 文章封面区 -->
    <div class="cover-section">
      <!-- 加载中骨架屏 -->
      <div v-if="playerStore.isLoadingAudio" class="loading-cover">
        <van-loading type="spinner" size="48" color="#c75b39" />
        <p class="loading-text">{{ $t('tts.generating') }}</p>
      </div>
      <!-- 正常封面 -->
      <template v-else>
        <img v-if="currentArticle?.cover" :src="currentArticle.cover" :alt="$t('common.cover')" />
        <div v-else class="placeholder-cover">
          <div class="wave-shell">
            <div class="wave-ring"></div>
            <div class="wave-bars">
              <span></span><span></span><span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 文章信息 -->
    <div class="article-info">
      <h2 class="title">{{ currentArticle?.title || $t('tts.noTitle') }}</h2>
      <p class="source">{{ getSourceName(currentArticle?.source) }}</p>
      <div class="source-actions">
        <van-button
          round
          plain
          size="small"
          class="source-action"
          :disabled="!canOpenArticle"
          @click="openArticle"
        >
          {{ $t('player.openArticle') }}
        </van-button>
        <van-button round plain size="small" class="source-action" @click="showPlaylist = true">
          {{ $t('player.playlist') }}
        </van-button>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-section">
      <van-slider
        v-model="progressValue"
        @change="onSeek"
        :min="0"
        :max="100"
        active-color="#c75b39"
      />
      <div class="time-info">
        <span>{{ formatTime(playerStore.currentTime) }}</span>
        <span>{{ formatTime(playerStore.totalTime) }}</span>
      </div>
    </div>

    <!-- 主控制按钮 -->
    <div class="main-controls">
      <van-button
        round
        icon="replay-5"
        size="large"
        :disabled="playerStore.isLoadingAudio"
        @click="skipBackward"
      >
        -15s
      </van-button>

      <van-button
        round
        :icon="playerStore.isLoadingAudio ? '' : (playerStore.isPaused ? 'play-circle' : 'pause-circle')"
        :loading="playerStore.isLoadingAudio"
        size="large"
        type="primary"
        class="play-btn"
        :disabled="playerStore.isLoadingAudio"
        @click="togglePlay"
      />

      <van-button
        round
        icon="play-forward-5"
        size="large"
        :disabled="playerStore.isLoadingAudio"
        @click="skipForward"
      >
        +15s
      </van-button>
    </div>

    <!-- 底部控制栏 -->
    <div class="bottom-controls">
      <!-- 播放速度 -->
      <div class="speed-control">
        <span class="label">{{ $t('tts.speed') }}</span>
        <van-button
          v-for="rate in [0.75, 1.0, 1.25, 1.5, 2.0]"
          :key="rate"
          size="mini"
          :type="playerStore.playbackRate === rate ? 'primary' : 'default'"
          @click="setSpeed(rate)"
        >
          {{ rate }}x
        </van-button>
      </div>

      <div class="player-bridge">
        {{ $t('player.bridgeText') }}
      </div>

      <!-- 上一篇/下一篇 -->
      <div class="navigation">
        <van-button
          icon="arrow-left"
          :disabled="playerStore.currentIndex === 0"
          @click="playPrevious"
        >
          {{ $t('player.previous') }}
        </van-button>
        <van-button
          icon="arrow"
          :disabled="playerStore.currentIndex >= playerStore.playlist.length - 1"
          @click="playNext"
        >
          {{ $t('player.next') }}
        </van-button>
      </div>

      <!-- 播放列表 -->
      <van-button
        icon="bars"
        block
        @click="showPlaylist = true"
      >
        {{ $t('player.playlist') }} ({{ playerStore.playlist.length }})
      </van-button>
    </div>

    <!-- 播放列表抽屉 -->
    <van-popup
      v-model:show="showPlaylist"
      position="bottom"
      :style="{ height: '60%' }"
      round
    >
      <div class="playlist-header">
        <h3>{{ $t('player.playlist') }} ({{ playerStore.playlist.length }})</h3>
        <van-icon name="cross" @click="showPlaylist = false" />
      </div>
      <van-list class="playlist-content">
        <div
          v-for="(item, index) in playerStore.playlist"
          :key="item.url"
          class="playlist-item"
          :class="{ active: index === playerStore.currentIndex }"
          @click="playAtIndex(index)"
        >
          <div class="item-info">
            <span class="item-title">{{ item.title }}</span>
            <span class="item-source">{{ getSourceName(item.source) }}</span>
          </div>
          <span v-if="index === playerStore.currentIndex" class="item-progress">
            {{ Math.floor(playerStore.progress) }}%
          </span>
          <van-icon
            v-if="index === playerStore.currentIndex"
            name="volume-o"
            color="var(--readaria-accent)"
          />
        </div>
      </van-list>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useArticleStore } from '@/stores/articleStore'
import { usePlayerStore } from '@/stores/playerStore'
import { useFeedStore } from '@/stores/feedStore'
import { resolveSourceName } from '@/utils/sourceName'

const router = useRouter()
const articleStore = useArticleStore()
const playerStore = usePlayerStore()
const feedStore = useFeedStore()
const { t } = useI18n()

// 确保订阅列表已加载，用于 source 名称映射
onMounted(async () => {
  if (feedStore.feeds.length === 0) {
    try {
      await feedStore.fetchFeeds()
    } catch (error) {
      console.error('加载订阅列表失败:', error)
    }
  }
})

// 从 source URL 提取订阅源名称
const getSourceName = (sourceUrl) => {
  if (!sourceUrl) return t('common.unknownSource')
  return resolveSourceName(feedStore.feeds, sourceUrl) || t('common.unknownSource')
}

// 播放列表抽屉显示状态
const showPlaylist = ref(false)

// 当前文章
const currentArticle = computed(() => playerStore.currentArticle)
const canOpenArticle = computed(() => !!currentArticle.value?.url)

// 进度条值 (0-100)
const progressValue = computed({
  get: () => playerStore.progress,
  set: (val) => {
    // ✅ 关键修复：如果总时长无效（Infinity、NaN等），禁止拖动
    if (!Number.isFinite(playerStore.totalTime) || playerStore.totalTime <= 0) {
      console.warn('[TtsPlayer] 总时长无效，禁止拖动进度条')
      return
    }

    // 拖动进度条时,将百分比转换为时间
    const targetTime = (val / 100) * playerStore.totalTime
    playerStore.seekTo(targetTime)
  }
})

/**
 * 格式化时间
 * @param {number} seconds - 秒数
 * @returns {string} 格式化的时间 (mm:ss)
 */
const formatTime = (seconds) => {
  // ✅ 关键修复：处理无效值（NaN、Infinity、负数等）
  if (!seconds || isNaN(seconds) || !Number.isFinite(seconds) || seconds < 0) {
    return '--:--'
  }

  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

/**
 * 返回上一页
 */
const goBack = () => {
  router.back()
}

/**
 * 切换播放/暂停
 */
const togglePlay = () => {
  playerStore.togglePlayPause()
}

/**
 * 快进 15 秒
 */
const skipForward = () => {
  playerStore.skipForward(15)
}

/**
 * 快退 15 秒
 */
const skipBackward = () => {
  playerStore.skipBackward(15)
}

/**
 * 设置播放速度
 * @param {number} rate - 播放速度
 */
const setSpeed = (rate) => {
  playerStore.setPlaybackRate(rate)
}

/**
 * 播放下一篇
 */
const playNext = () => {
  playerStore.playNext()
}

/**
 * 播放上一篇
 */
const playPrevious = () => {
  playerStore.playPrevious()
}

/**
 * 跳转到播放列表指定位置
 * @param {number} index - 目标索引
 */
const playAtIndex = (index) => {
  playerStore.playAtIndex(index)
  showPlaylist.value = false
}

const openArticle = () => {
  if (!currentArticle.value?.url) return
  const article = {
    ...currentArticle.value,
    url: currentArticle.value.url,
    title: currentArticle.value.title || t('tts.noTitle'),
    source: currentArticle.value.source || t('common.unknownSource')
  }

  try {
    articleStore.setCurrent(article)
  } catch (_) {}

  try {
    const articleKey = `article_${encodeURIComponent(article.url)}`
    sessionStorage.setItem(articleKey, JSON.stringify(article))
  } catch (_) {}

  // 如果正在播放，保存标记以便文章页恢复（Android 导航可能自动暂停音频）
  if (playerStore.isPlaying && !playerStore.isPaused) {
    sessionStorage.setItem('tts_navigate_keep_playing', 'true')
  }

  router.push({
    name: 'article-detail',
    params: { id: encodeURIComponent(article.url) }
  })
}

/**
 * 进度条拖动事件
 * @param {number} value - 进度值 (0-100)
 */
const onSeek = (value) => {
  const targetTime = (value / 100) * playerStore.totalTime
  playerStore.seekTo(targetTime)
}
</script>

<style scoped>
.tts-player-page {
  min-height: 100vh;
  background: linear-gradient(180deg, var(--readaria-paper) 0%, #f2eadf 100%);
  padding-bottom: 20px;
}

.cover-section {
  width: 100%;
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.cover-section img {
  max-width: 240px;
  max-height: 240px;
  border-radius: 28px;
  box-shadow: 0 18px 36px rgba(64, 45, 31, 0.14);
  object-fit: cover;
}

.placeholder-cover {
  width: 240px;
  height: 240px;
  background: radial-gradient(circle at center, rgba(27, 41, 58, 0.12), rgba(27, 41, 58, 0.02));
  border-radius: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wave-shell {
  position: relative;
  width: 160px;
  height: 160px;
  display: grid;
  place-items: center;
}

.wave-ring {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 14px solid rgba(27, 41, 58, 0.92);
  box-shadow: 0 0 0 16px rgba(199, 91, 57, 0.12);
}

.wave-bars {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 8px;
}

.wave-bars span {
  width: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #c75b39, rgba(199, 91, 57, 0.26));
  animation: pulseBar 1.8s ease-in-out infinite;
}

.wave-bars span:nth-child(1) { height: 16px; }
.wave-bars span:nth-child(2) { height: 30px; animation-delay: .12s; }
.wave-bars span:nth-child(3) { height: 22px; animation-delay: .24s; }
.wave-bars span:nth-child(4) { height: 34px; animation-delay: .36s; }
.wave-bars span:nth-child(5) { height: 18px; animation-delay: .48s; }

.loading-cover {
  width: 240px;
  height: 240px;
  background: rgba(255, 252, 248, 0.88);
  border-radius: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.loading-text {
  font-size: 14px;
  color: var(--readaria-muted);
  margin: 0;
}

.article-info {
  text-align: center;
  padding: 20px;
}

.title {
  font-family: var(--readaria-serif);
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--readaria-ink);
  line-height: 1.1;
}

.source {
  font-size: 14px;
  color: var(--readaria-muted);
}

.source-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.source-action {
  background: rgba(255, 252, 248, 0.76) !important;
  border-color: var(--readaria-border) !important;
  color: var(--readaria-navy) !important;
}

.progress-section {
  padding: 0 24px;
  margin: 20px 0;
}

.time-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--readaria-muted);
  margin-top: 8px;
}

.main-controls {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  padding: 20px;
}

.play-btn {
  width: 70px;
  height: 70px;
  font-size: 40px;
}

.bottom-controls {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.speed-control {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.speed-control .label {
  font-size: 14px;
  color: var(--readaria-muted);
  margin-right: 4px;
}

.player-bridge {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(199, 91, 57, 0.08);
  color: var(--readaria-muted);
  line-height: 1.5;
}

.navigation {
  display: flex;
  gap: 12px;
}

.navigation .van-button {
  flex: 1;
}

.playlist-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--readaria-border);
}

.playlist-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0;
}

.playlist-content {
  max-height: calc(60vh - 60px);
  overflow-y: auto;
}

.playlist-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--readaria-border);
  cursor: pointer;
  transition: background 0.2s;
}

.playlist-item:hover {
  background: var(--readaria-stone);
}

.playlist-item.active {
  background: rgba(199, 91, 57, 0.08);
}

.item-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.item-title {
  font-size: 14px;
  color: var(--readaria-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-source {
  font-size: 12px;
  color: var(--readaria-muted);
}

.item-progress {
  font-size: 12px;
  color: var(--readaria-accent);
  margin-right: 8px;
  flex-shrink: 0;
}

@keyframes pulseBar {
  0%, 100% { opacity: 0.48; transform: scaleY(0.84); }
  50% { opacity: 1; transform: scaleY(1.08); }
}
</style>
