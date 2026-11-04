import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  trackPwaPromptShown,
  trackPwaInstallAccepted,
  trackPwaInstallDismissed,
} from '@/utils/analytics'

let deferredPrompt = null
let beforeInstallListener = null
let appInstalledListener = null
let standaloneMql = null
let standaloneListener = null
let initialized = false

const detectIos = () => {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent || ''
  const isIpadDesktop = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1
  return (/iPad|iPhone|iPod/.test(ua) && !window.MSStream) || isIpadDesktop
}

const detectSafari = (isIos) => {
  if (!isIos || typeof navigator === 'undefined') return false
  const ua = navigator.userAgent || ''
  return /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua)
}

const detectStandalone = () => {
  if (typeof window === 'undefined') return false
  if (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) return true
  if (typeof window.navigator !== 'undefined' && window.navigator.standalone === true) return true
  return false
}

export const usePwaStore = defineStore('pwa', () => {
  // Reactive platform state
  const canInstall = ref(false)
  const isIos = ref(false)
  const isSafari = ref(false)
  const isStandalone = ref(false)
  const showIosGuide = ref(false)
  // Sticky flag: once a beforeinstallprompt has fired we know the platform supports install,
  // even after the deferred prompt is consumed by the first prompt() call.
  // Persists for the rest of the session so the Me-view entry stays visible after a dismissal.
  const hasInstallCapability = ref(false)

  const installAvailable = computed(
    () => canInstall.value || (isIos.value && isSafari.value)
  )

  // Whether to show a persistent install entry (e.g. in Me view). Hidden once installed.
  // hasInstallCapability keeps the entry visible on Android after the native prompt is consumed,
  // so dismissing the browser prompt does not regress the persistent entry to a one-shot.
  const shouldShowInstallEntry = computed(
    () =>
      !isStandalone.value &&
      (installAvailable.value || hasInstallCapability.value)
  )

  const initialize = () => {
    if (initialized || typeof window === 'undefined') return
    initialized = true

    isIos.value = detectIos()
    isSafari.value = detectSafari(isIos.value)
    isStandalone.value = detectStandalone()

    beforeInstallListener = (e) => {
      e.preventDefault()
      deferredPrompt = e
      canInstall.value = true
      hasInstallCapability.value = true
    }
    window.addEventListener('beforeinstallprompt', beforeInstallListener)

    if (window.matchMedia) {
      standaloneMql = window.matchMedia('(display-mode: standalone)')
      standaloneListener = (e) => {
        isStandalone.value = e.matches || isStandalone.value
      }
      if (standaloneMql.addEventListener) {
        standaloneMql.addEventListener('change', standaloneListener)
      } else if (standaloneMql.addListener) {
        standaloneMql.addListener(standaloneListener)
      }
    }

    appInstalledListener = () => {
      isStandalone.value = true
      canInstall.value = false
      hasInstallCapability.value = false
      deferredPrompt = null
    }
    window.addEventListener('appinstalled', appInstalledListener)
  }

  const triggerInstall = async (source = 'unknown') => {
    if (isStandalone.value) return 'already-installed'

    if (canInstall.value && deferredPrompt) {
      trackPwaPromptShown(source)
      try {
        deferredPrompt.prompt()
        const { outcome } = await deferredPrompt.userChoice
        if (outcome === 'accepted') {
          trackPwaInstallAccepted()
        } else {
          trackPwaInstallDismissed()
        }
        return outcome
      } catch (e) {
        return 'error'
      } finally {
        deferredPrompt = null
        canInstall.value = false
      }
    }

    if (isIos.value && isSafari.value) {
      showIosGuide.value = true
      trackPwaPromptShown(source)
      return 'ios-guide'
    }

    // The platform previously offered a deferred prompt (Android Chrome / Edge),
    // but the prompt has been consumed (user accepted or dismissed). We can't
    // programmatically re-prompt — caller should surface manual install steps.
    // We intentionally do NOT call trackPwaPromptShown here: no prompt/guide is
    // actually shown, so counting it would inflate "prompt shown" analytics.
    if (hasInstallCapability.value) {
      return 'manual-install'
    }

    return 'unavailable'
  }

  const dismissIosGuide = () => {
    showIosGuide.value = false
  }

  return {
    canInstall,
    isIos,
    isSafari,
    isStandalone,
    showIosGuide,
    hasInstallCapability,
    installAvailable,
    shouldShowInstallEntry,
    initialize,
    triggerInstall,
    dismissIosGuide,
  }
})
