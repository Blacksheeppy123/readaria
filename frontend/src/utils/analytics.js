import posthog from 'posthog-js'

// ==================== PostHog 共享配置 ====================

export const POSTHOG_CONFIG = {
  api_host: 'https://eu.i.posthog.com',
  person_profiles: 'identified_only',
  autocapture: true,
  capture_pageview: true,
  capture_pageleave: true,
  session_recording: {
    maskAllInputs: true,
    maskTextSelector: '.ph-mask',
  },
}

/**
 * 初始化 PostHog（单例，重复调用无效果）
 * 如果用户已登录，会在 init 后自动 re-identify
 */
export function initPostHog(posthogKey) {
  if (!posthogKey || posthog.__loaded) return false

  posthog.init(posthogKey, POSTHOG_CONFIG)
  posthog.opt_in_capturing()

  // 异步 re-identify：如果用户已登录，确保 person profile 正确关联
  import('@/stores/userStore').then(({ useUserStore }) => {
    const userStore = useUserStore()
    if (userStore.isLoggedIn && userStore.user) {
      posthog.identify(userStore.user.id, {
        email: userStore.user.email,
        username: userStore.user.username,
      })
      applySessionRecordingSampling(userStore.user)
    }
  }).catch(() => {})

  return true
}

/**
 * 安全地 identify 用户（仅在已 consent 且 PostHog 已初始化时执行）
 */
export function identifyUser(user) {
  if (!user || !posthog.__loaded) return
  const consent = localStorage.getItem('readaria_cookie_consent')
  if (consent !== 'accepted') return
  posthog.identify(user.id, {
    email: user.email,
    username: user.username,
  })
}

// 同一会话内只决定一次 Session Replay 采样，避免多次 identify 调用重复抽样
let sessionRecordingSamplingApplied = false

/**
 * 自托管版统一按约 10% 采样 Session Replay，不再区分付费层级。
 * 同一会话只决定一次；登出时调用 resetSessionRecordingSampling() 重置。
 */
export function applySessionRecordingSampling(user) {
  if (!user || !posthog.__loaded) return
  const consent = localStorage.getItem('readaria_cookie_consent')
  if (consent !== 'accepted') return
  if (sessionRecordingSamplingApplied) return
  sessionRecordingSamplingApplied = true

  if (Math.random() > 0.1) {
    posthog.stopSessionRecording()
  } else {
    posthog.startSessionRecording()
  }
}

/**
 * 重置 Session Replay 采样决定（仅在登出 / 切换账户时调用）
 */
export function resetSessionRecordingSampling() {
  sessionRecordingSamplingApplied = false
}

/**
 * PostHog 事件发送封装
 * 命名规范: 小写蛇形 verb_noun，属性也使用蛇形
 */
export function capture(event, properties = {}) {
  if (import.meta.env.PROD && localStorage.getItem('readaria_cookie_consent') === 'accepted') {
    posthog.capture(event, properties)
  }
}

// ==================== 漏斗事件 ====================

export function trackLandingViewed(props = {}) {
  capture('landing_viewed', props)
}

export function trackSignupCompleted(method = 'email') {
  capture('signup_completed', { method })
}

export function trackLoginCompleted(method = 'email') {
  capture('login_completed', { method })
}

export function trackSubscriptionAdded(sourceType) {
  capture('subscription_added', { source_type: sourceType })
}

export function trackArticlesFirstSynced(articleCount) {
  capture('articles_first_synced', { article_count: articleCount })
}

export function trackTtsFirstPlay(props) {
  capture('tts_first_play', props)
}

export function trackPodcastGenerated(props) {
  capture('podcast_generated', props)
}

export function trackPwaPromptShown(trigger) {
  capture('pwa_prompt_shown', { trigger })
}

export function trackPwaInstallAccepted() {
  capture('pwa_install_accepted')
}

export function trackPwaInstallDismissed() {
  capture('pwa_install_dismissed')
}

export function trackPwaBannerDismissed() {
  capture('pwa_banner_dismissed')
}

export function trackArticleShared(channel) {
  capture('article_shared', { channel })
}

export function trackPodcastQaUsed(podcastId) {
  capture('podcast_qa_used', { podcast_id: podcastId })
}

// ==================== Audio QoE 事件 ====================

export function trackAudioCompleted(props) {
  capture('audio_completed', props)
}

export function trackAudioError(props) {
  capture('audio_error', props)
}

/**
 * 播放断流（stalled/waiting 或看门狗发现进度停滞）
 * props: { article_id|podcast_id, trigger: 'stalled'|'waiting'|'watchdog', mode, current_time }
 */
export function trackAudioStall(props) {
  capture('audio_stall', props)
}

/**
 * 自动恢复播放成功
 * props: { article_id|podcast_id, trigger: 'canplay'|'unintended_pause'|'foreground'|'online'|'media_session'|'watchdog', wedged }
 */
export function trackAudioAutoResume(props) {
  capture('audio_auto_resume', props)
}

/**
 * 后台/前台连播快速交接结果（iOS 后台连播核心指标）
 * props: { article_id, success, mode: 'final'|'segmented', error_message? }
 */
export function trackAudioTrackHandoff(props) {
  capture('audio_track_handoff', props)
}
