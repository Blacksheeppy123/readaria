<script setup>
import { ref, onMounted, onUnmounted, computed, defineAsyncComponent } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useNetworkStatus } from '@/composables/useNetworkStatus'
import { usePlayerStore } from '@/stores/playerStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { usePwaStore } from '@/stores/pwaStore'
import { useSpeechSynthesis } from '@/composables/useSpeechSynthesis'
import { useOpenAITts } from '@/composables/useOpenAITts'
import { useTTS } from '@/composables/useTTS'
import { useBreakpoint } from '@/composables/useBreakpoint'
import DesktopShell from '@/layouts/DesktopShell.vue'
import UnifiedFloatingPlayer from '@/components/UnifiedFloatingPlayer.vue'
import CookieConsent from '@/components/CookieConsent.vue'
import PwaInstallBanner from '@/components/PwaInstallBanner.vue'
import PwaIosInstallGuide from '@/components/PwaIosInstallGuide.vue'
import { isDemoMode } from '@/demo/config'

const DemoBanner = isDemoMode
  ? defineAsyncComponent(() => import('@/demo/DemoBanner.vue'))
  : null

const router = useRouter()
const route = useRoute()
const playerStore = usePlayerStore()
const onboardingStore = useOnboardingStore()
const pwaStore = usePwaStore()

// Initialize PWA install detection (beforeinstallprompt / standalone / iOS / appinstalled).
// Idempotent — safe across HMR and re-mounts.
pwaStore.initialize()

const active = ref('feed')
const showLegacyFallbackDialog = computed(() => !!playerStore.pendingFallbackRequest)

// 桌面端外壳：≥1024px 且需要认证的应用页面（desktopBare 除外）套用侧栏布局
const { isDesktop } = useBreakpoint()
const showDesktopShell = computed(() =>
  isDesktop.value && !!route.meta.requiresAuth && !route.meta.desktopBare
)

// 监听路由变化
router.afterEach((to) => {
  active.value = to.name || 'feed'
})

const onChange = (name) => {
  router.push({ name })
}

// 启用网络状态监听
const { isOnline } = useNetworkStatus()

const handleLegacyFallbackConfirm = () => {
  playerStore.confirmLegacyFallback()
}

const handleLegacyFallbackCancel = () => {
  playerStore.cancelLegacyFallbackRequest()
  playerStore.stop()
}

// 初始化 TTS
onMounted(async () => {
  // 创建 OpenAI TTS 实例（优先）
  const openAITts = useOpenAITts(playerStore)
  playerStore.setOpenAITTSInstance(openAITts)

  // 创建 Web Speech API 实例（降级方案）
  const legacyTts = useSpeechSynthesis(playerStore)
  playerStore.setLegacyTTSInstance(legacyTts)

  // 创建新 TTS 实例（两层架构：Cloud Cached -> Cloud Realtime）
  const newTts = useTTS(playerStore)
  playerStore.setNewTTSInstance(newTts)

  // 初始化 TTS Manager
  playerStore.initializeTTSManager()

  // 恢复播放进度
  await playerStore.restoreProgress()
  playerStore.resumeInterruptedPlayback().catch(error => {
    console.warn('[App] Interrupted playback resume failed:', error)
  })

  // 监听首次音频播放，完成 onboarding 状态机
  const handleFirstAudio = () => {
    onboardingStore.markFirstAudioPlayed()
  }
  window.addEventListener('first-audio-played', handleFirstAudio)

  onUnmounted(() => {
    window.removeEventListener('first-audio-played', handleFirstAudio)
  })
})
</script>

<template>
  <div class="app-container">
    <DemoBanner v-if="isDemoMode" />
    <DesktopShell v-if="showDesktopShell">
      <router-view v-slot="{ Component }">
        <keep-alive include="FeedView,ListenView">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </DesktopShell>
    <div v-else-if="isDesktop && route.meta.desktopCenter" class="content desktop-center-page">
      <router-view v-slot="{ Component }">
        <component :is="Component" />
      </router-view>
    </div>
    <div v-else class="content">
      <router-view v-slot="{ Component }">
        <keep-alive include="FeedView,ListenView">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </div>

    <!-- 统一悬浮播放器（桌面端 v1 不做 TTS UI，隐藏悬浮球） -->
    <UnifiedFloatingPlayer v-if="!isDesktop" />

    <van-dialog
      :show="showLegacyFallbackDialog"
      :title="$t('player.ttsQuotaExhaustedFallbackTitle')"
      show-cancel-button
      :confirm-button-text="$t('player.useLocalVoice')"
      :cancel-button-text="$t('common.stopPlaying')"
      @confirm="handleLegacyFallbackConfirm"
      @cancel="handleLegacyFallbackCancel"
    >
      <div style="padding: 16px; line-height: 1.5;">
        {{ $t('player.ttsQuotaExhaustedFallbackMessage') }}
      </div>
    </van-dialog>

    <!-- Cookie 同意横幅 -->
    <CookieConsent />

    <!-- PWA 安装横幅 -->
    <PwaInstallBanner />

    <!-- PWA iOS 安装引导浮层（横幅与个人中心入口共享） -->
    <PwaIosInstallGuide />

    <van-tabbar v-if="!showDesktopShell && !route.meta.hideTabbar" v-model="active" @change="onChange">
      <van-tabbar-item name="feed" icon="newspaper-o">{{ $t('nav.feed') }}</van-tabbar-item>
      <van-tabbar-item name="listen" icon="music-o">{{ $t('nav.listen') }}</van-tabbar-item>
      <van-tabbar-item name="me" icon="user-o">{{ $t('nav.me') }}</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.content {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  /* 安全区域已在全局 style.css 中处理，这里不再需要额外 padding */
}

/* 桌面端居中窄列（登录/注册等 desktopCenter 路由）。transform 使内部 fixed 定位相对窄列生效 */
.desktop-center-page {
  max-width: 480px;
  margin: 0 auto;
  border-left: 1px solid var(--readaria-border);
  border-right: 1px solid var(--readaria-border);
  transform: translateZ(0);
}

:global(.van-button--primary) {
  background: var(--readaria-navy) !important;
  border-color: var(--readaria-navy) !important;
  color: var(--readaria-paper) !important;
}

:global(.van-button--plain.van-button--primary) {
  background: transparent !important;
  border-color: var(--readaria-navy) !important;
  color: var(--readaria-navy) !important;
}

:global(.van-tabbar-item--active) {
  color: var(--readaria-accent) !important;
}

:global(.van-slider__bar) {
  background: var(--readaria-accent) !important;
}
</style>
