<template>
  <transition name="slide-up">
    <div v-if="visible" class="pwa-banner" @click="handleBannerClick">
      <div class="pwa-banner-content">
        <img src="/pwa-192x192.png" class="pwa-banner-icon" alt="Readaria" />
        <div class="pwa-banner-text">
          <div class="pwa-banner-title">{{ $t('pwa.bannerTitle') }}</div>
          <div class="pwa-banner-message">{{ $t('pwa.bannerMessage') }}</div>
        </div>
        <div class="pwa-banner-actions" @click.stop>
          <van-button
            v-if="pwaStore.installAvailable"
            round
            size="small"
            type="primary"
            class="pwa-cta-btn"
            @click="handleCtaClick"
          >
            {{ pwaStore.canInstall ? $t('pwa.addButton') : $t('pwa.iosGuideButton') }}
          </van-button>
          <button class="pwa-dismiss-btn" @click="dismiss">
            <van-icon name="cross" />
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { usePwaStore } from '@/stores/pwaStore'
import { trackPwaPromptShown, trackPwaBannerDismissed } from '@/utils/analytics'

const pwaStore = usePwaStore()

const visible = ref(false)
let dismissTimer = null
let eventListener = null

const DISMISS_KEY = 'pwa_prompt_dismissed_at'
const DISMISS_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000 // 7 days

const shouldShow = () => {
  if (typeof window === 'undefined') return false
  if (pwaStore.isStandalone) return false

  const dismissedAt = localStorage.getItem(DISMISS_KEY)
  if (dismissedAt) {
    const elapsed = Date.now() - parseInt(dismissedAt, 10)
    if (elapsed < DISMISS_COOLDOWN_MS) return false
  }

  const ua = navigator.userAgent
  const isMobile = /iPhone|iPad|iPod|Android/i.test(ua) ||
                   (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  if (!isMobile) return false

  // Only show on Safari for iOS; other iOS browsers (Chrome, Edge, Firefox)
  // have different UI flows and Safari-specific copy would mislead users.
  if (pwaStore.isIos && !pwaStore.isSafari) return false

  return true
}

const handleBannerClick = async () => {
  const result = await pwaStore.triggerInstall('banner')
  if (result === 'accepted' || result === 'dismissed') {
    visible.value = false
  }
}

const handleCtaClick = async () => {
  const result = await pwaStore.triggerInstall('banner_cta')
  if (result === 'accepted' || result === 'dismissed') {
    visible.value = false
  }
}

const dismiss = () => {
  visible.value = false
  localStorage.setItem(DISMISS_KEY, Date.now().toString())
  trackPwaBannerDismissed()
}

const showBanner = () => {
  if (!shouldShow()) return
  // Only show when there's an actionable install path
  if (!pwaStore.installAvailable) return
  visible.value = true
  trackPwaPromptShown('first_audio_play')
}

onMounted(() => {
  if (typeof window === 'undefined') return

  // Store handles beforeinstallprompt + appinstalled + standalone tracking.
  pwaStore.initialize()

  eventListener = () => {
    const delay = 3000 + Math.random() * 2000
    dismissTimer = setTimeout(showBanner, delay)
  }
  window.addEventListener('first-audio-played', eventListener)
})

onUnmounted(() => {
  if (typeof window === 'undefined') return
  if (eventListener) {
    window.removeEventListener('first-audio-played', eventListener)
  }
  if (dismissTimer) clearTimeout(dismissTimer)
})
</script>

<style scoped>
.pwa-banner {
  position: fixed;
  bottom: calc(var(--van-tabbar-height, 50px) + 8px);
  left: 12px;
  right: 12px;
  z-index: 2000;
  background: linear-gradient(135deg, var(--readaria-navy) 0%, #1e3a5f 100%);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: transform 0.15s ease;
}

.pwa-banner:active {
  transform: scale(0.985);
}

.pwa-banner-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pwa-banner-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.pwa-banner-text {
  flex: 1;
  min-width: 0;
}

.pwa-banner-title {
  font-size: 15px;
  font-weight: 600;
  color: white;
  margin-bottom: 3px;
  line-height: 1.3;
}

.pwa-banner-message {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.4;
}

.pwa-banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.pwa-cta-btn {
  font-weight: 600;
  font-size: 13px;
}

.pwa-dismiss-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s, color 0.2s;
}

.pwa-dismiss-btn:active {
  background: rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.9);
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

:deep(.pwa-cta-btn.van-button--primary) {
  background: white;
  border-color: white;
  color: var(--readaria-navy);
  padding: 0 14px;
  height: 32px;
  line-height: 30px;
}
</style>
