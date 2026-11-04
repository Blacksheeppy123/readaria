<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter, useRoute } from 'vue-router'
import posthog from 'posthog-js'
import { initPostHog } from '@/utils/analytics'
import { usePlayerStore } from '@/stores/playerStore'
import { usePodcastPlayerStore } from '@/stores/podcastPlayerStore'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const playerStore = usePlayerStore()
const podcastPlayerStore = usePodcastPlayerStore()
const visible = ref(false)

const STORAGE_KEY = 'readaria_cookie_consent'

const hasFloatingPlayer = computed(() => {
  if (route.name === 'player') {
    return false
  }

  const articlePlayerActive =
    playerStore.isPlaying ||
    playerStore.isPaused ||
    playerStore.isLoadingAudio ||
    playerStore.isActivatingFallback

  const podcastPlayerActive =
    podcastPlayerStore.isPlaying ||
    podcastPlayerStore.isPaused ||
    podcastPlayerStore.isLoading

  return articlePlayerActive || podcastPlayerActive
})

const bannerClass = computed(() => ({
  'cookie-banner--with-tabbar': !route.meta.hideTabbar,
  'cookie-banner--with-player': hasFloatingPlayer.value
}))

onMounted(() => {
  const consent = localStorage.getItem(STORAGE_KEY)
  if (!consent) {
    visible.value = true
  }
  window.addEventListener('readaria-consent-changed', () => {
    visible.value = false
  })
})

const accept = () => {
  localStorage.setItem(STORAGE_KEY, 'accepted')
  visible.value = false
  window.dispatchEvent(new CustomEvent('readaria-consent-changed', { detail: { consent: 'accepted' } }))
  // 如果 PostHog 因首次访问未初始化，现在启用
  const posthogKey = import.meta.env.VITE_POSTHOG_KEY
  if (import.meta.env.PROD && posthogKey) {
    initPostHog(posthogKey)
  }
}

const decline = () => {
  localStorage.setItem(STORAGE_KEY, 'declined')
  visible.value = false
  window.dispatchEvent(new CustomEvent('readaria-consent-changed', { detail: { consent: 'declined' } }))
  // 如果 PostHog 已初始化，停止跟踪
  if (posthog.__loaded) {
    posthog.opt_out_capturing()
    posthog.reset()
  }
}

const goToPrivacy = () => {
  router.push({ name: 'privacy' })
}
</script>

<template>
  <transition name="cookie-slide">
    <div v-if="visible" class="cookie-banner" :class="bannerClass">
      <div class="cookie-content">
        <div class="cookie-copy">
          <p class="cookie-eyebrow">{{ t('common.hint') }}</p>
          <p class="cookie-text">
            {{ $t('cookie.message') }}
            <a class="cookie-link" @click.prevent="goToPrivacy">{{ $t('cookie.learnMore') }}</a>
          </p>
        </div>
        <div class="cookie-actions">
          <van-button size="small" plain type="primary" class="cookie-button cookie-button--secondary" @click="decline">
            {{ $t('cookie.decline') }}
          </van-button>
          <van-button size="small" type="primary" class="cookie-button" @click="accept">
            {{ $t('cookie.accept') }}
          </van-button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.cookie-banner {
  position: fixed;
  left: 12px;
  right: 12px;
  bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  z-index: 9999;
  background:
    linear-gradient(180deg, rgba(255, 250, 243, 0.98) 0%, rgba(251, 247, 240, 0.98) 100%);
  border: 1px solid var(--readaria-border);
  border-radius: 26px;
  box-shadow: 0 22px 44px rgba(64, 45, 31, 0.16);
  padding: 14px 16px;
  backdrop-filter: blur(16px);
}

.cookie-banner--with-tabbar {
  bottom: calc(74px + env(safe-area-inset-bottom, 0px));
}

.cookie-banner--with-player {
  bottom: calc(132px + env(safe-area-inset-bottom, 0px));
}

.cookie-content {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  max-width: 720px;
  margin: 0 auto;
}

.cookie-copy {
  flex: 1;
  min-width: 0;
}

.cookie-eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--readaria-accent);
}

.cookie-text {
  font-size: 13px;
  color: var(--readaria-muted);
  margin: 0;
  line-height: 1.5;
}

.cookie-link {
  color: var(--readaria-accent);
  text-decoration: none;
  font-weight: 600;
  cursor: pointer;
}

.cookie-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.cookie-button {
  min-width: 88px;
  border-radius: 999px;
}

.cookie-slide-enter-active,
.cookie-slide-leave-active {
  transition: transform 0.28s ease, opacity 0.28s ease;
}

.cookie-slide-enter-from,
.cookie-slide-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

@media (max-width: 640px) {
  .cookie-content {
    flex-direction: column;
    align-items: stretch;
  }

  .cookie-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .cookie-button {
    flex: 1;
  }
}
</style>
