<template>
  <div
    v-if="isVisible"
    class="unified-floating-player"
    :class="[
      { 'no-tabbar': route.meta.hideTabbar },
      itemType === 'podcast' ? 'podcast-theme' : 'article-theme'
    ]"
    @click="goToPlayer"
  >
    <div class="player-content">
      <!-- 标题 -->
      <div class="player-title">
        {{ displayTitle }}
      </div>

      <!-- 播放/暂停按钮 或 加载图标 -->
      <van-loading
        v-if="isLoading"
        type="spinner"
        size="24"
        :color="themeColor"
        @click.stop
      />
      <van-icon
        v-else
        :name="isPaused ? 'play-circle' : 'pause-circle'"
        size="32"
        :color="themeColor"
        @click.stop="togglePlay"
      />

      <!-- 进度条 -->
      <van-progress
        :percentage="isLoading ? 0 : progressValue"
        :show-pivot="false"
        stroke-width="2"
        :color="themeColor"
        class="progress-bar"
      />
    </div>

    <!-- 关闭按钮 -->
    <van-icon
      name="close"
      size="18"
      class="close-btn"
      @click.stop="stopPlayer"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { usePlayerStore } from '@/stores/playerStore'
import { usePodcastPlayerStore } from '@/stores/podcastPlayerStore'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const playerStore = usePlayerStore()
const podcastPlayer = usePodcastPlayerStore()

// 当前播放的类型（互斥保证同时只有一侧活跃，这里做防御性判断）
const itemType = computed(() => {
  const podcastActive = podcastPlayer.isPlaying || podcastPlayer.isPaused || podcastPlayer.isLoading
  const articleActive =
    playerStore.isPlaying ||
    playerStore.isPaused ||
    playerStore.isLoadingAudio ||
    playerStore.isActivatingFallback
  // 如果双方都活跃（不应发生，但防御），以播客优先
  if (podcastActive) return 'podcast'
  if (articleActive) return 'article'
  return 'article'
})

// 是否显示
const isVisible = computed(() => {
  const articleActive =
    playerStore.isPlaying ||
    playerStore.isPaused ||
    playerStore.isLoadingAudio ||
    playerStore.isActivatingFallback
  const podcastActive = podcastPlayer.isPlaying || podcastPlayer.isPaused || podcastPlayer.isLoading

  // 在全屏播放器页隐藏
  if (route.path === '/player') return false

  // 文章详情页已经有内嵌 mini player，避免双层播放器条重叠
  if (route.name === 'article-detail') return false

  return articleActive || podcastActive
})

// 是否加载中
const isLoading = computed(() => {
  if (itemType.value === 'podcast') return podcastPlayer.isLoading
  return playerStore.isLoadingAudio || playerStore.isActivatingFallback
})

// 是否暂停
const isPaused = computed(() => {
  if (itemType.value === 'podcast') return podcastPlayer.isPaused
  return playerStore.isPaused
})

// 进度
const progressValue = computed(() => {
  if (itemType.value === 'podcast') return podcastPlayer.progress
  return playerStore.progress
})

// 主题色
const themeColor = computed(() => {
  return itemType.value === 'podcast' ? '#9a674f' : '#c75b39'
})

// 显示标题
const displayTitle = computed(() => {
  if (itemType.value === 'podcast') {
    if (podcastPlayer.isLoading) return t('common.loading')
    return podcastPlayer.currentPodcast?.title || t('podcast.playing')
  }
  if (playerStore.isActivatingFallback) return t('tts.fallbackMode')
  if (playerStore.isLoadingAudio) return t('tts.generating')
  return playerStore.currentArticle?.title || t('tts.playing')
})

// 跳转到对应播放器页
const goToPlayer = () => {
  if (itemType.value === 'podcast') {
    if (podcastPlayer.currentPodcast?.id) {
      const targetPath = `/podcasts/${podcastPlayer.currentPodcast.id}`
      if (route.path !== targetPath) {
        router.push({ name: 'podcast-detail', params: { id: podcastPlayer.currentPodcast.id } })
      }
    }
  } else {
    if (route.path !== '/player') {
      router.push('/player')
    }
  }
}

// 播放/暂停切换
const togglePlay = () => {
  if (itemType.value === 'podcast') {
    podcastPlayer.togglePlayPause()
  } else {
    playerStore.togglePlayPause()
  }
}

// 停止
const stopPlayer = () => {
  if (itemType.value === 'podcast') {
    podcastPlayer.stop()
  } else {
    playerStore.stop()
  }
}
</script>

<style scoped>
.unified-floating-player {
  position: fixed;
  bottom: calc(60px + env(safe-area-inset-bottom, 0px));
  left: 12px;
  right: 12px;
  height: 60px;
  background: rgba(255, 252, 248, 0.96);
  border: 1px solid var(--readaria-border);
  border-radius: 30px;
  box-shadow: 0 18px 34px rgba(64, 45, 31, 0.14);
  z-index: 1000;
  display: flex;
  align-items: center;
  padding: 0 16px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.unified-floating-player.no-tabbar {
  bottom: calc(12px + env(safe-area-inset-bottom, 0px));
}

.unified-floating-player.podcast-theme {
  box-shadow: 0 18px 34px rgba(154, 103, 79, 0.18);
}

.unified-floating-player:hover {
  box-shadow: 0 20px 38px rgba(64, 45, 31, 0.18);
}

.player-content {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  overflow: hidden;
}

.player-title {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--readaria-ink);
}

.progress-bar {
  width: 60px;
  flex-shrink: 0;
}

.close-btn {
  margin-left: 8px;
  color: var(--readaria-muted);
  cursor: pointer;
  flex-shrink: 0;
}

.close-btn:hover {
  color: var(--readaria-ink);
}
</style>
