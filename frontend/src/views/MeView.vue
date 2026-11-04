<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showDialog, showToast, showLoadingToast, showConfirmDialog, closeToast } from 'vant'
import posthog from 'posthog-js'
import { initPostHog } from '@/utils/analytics'
import { useFeedStore } from '@/stores/feedStore'
import { useUserStore } from '@/stores/userStore'
import { usePwaStore } from '@/stores/pwaStore'
import { logout as logoutApi, deleteAccount, updateLanguage, updateAutoPodcast, updateTtsVoices } from '@/api/auth'
import { getTtsVoices } from '@/api/tts'
import VoicePicker from '@/components/VoicePicker.vue'
import { exportOpml, importOpml } from '@/api/feeds'
import { setLocale } from '@/i18n'
import request from '@/api/request'
import { frontendLogCollector } from '@/utils/frontendLogCollector'

const { t, locale } = useI18n({ useScope: 'global' })
const router = useRouter()
const feedStore = useFeedStore()
const userStore = useUserStore()
const pwaStore = usePwaStore()
const fileInput = ref(null)
const importing = ref(false)

const currentUser = computed(() => userStore.user)
const showDeleteConfirm = ref(false)
const deletePassword = ref('')
const settingsExpanded = ref([]) // van-collapse: empty = collapsed

// Feedback dialog
const showFeedback = ref(false)
const feedbackText = ref('')
const feedbackAttachLogs = ref(false)

onMounted(async () => {
  if (feedStore.feeds.length === 0) {
    try {
      await feedStore.fetchFeeds()
    } catch (error) {
      console.error('Failed to fetch feeds:', error)
    }
  }
})

// 响应式 consent 状态（避免直接从 localStorage 读导致开关不刷新）
const analyticsConsent = ref(localStorage.getItem('readaria_cookie_consent') === 'accepted')
const analyticsEnabled = computed(() => analyticsConsent.value)

// 同步其他组件（如 CookieConsent banner）对 localStorage 的修改
let storageListener = null
let consentChangeListener = null
onMounted(() => {
  storageListener = (e) => {
    if (e.key === 'readaria_cookie_consent') {
      analyticsConsent.value = e.newValue === 'accepted'
    }
  }
  window.addEventListener('storage', storageListener)

  // 同 tab 内 CookieConsent.vue 通过 CustomEvent 同步
  consentChangeListener = (e) => {
    if (e.detail?.consent) {
      analyticsConsent.value = e.detail.consent === 'accepted'
    }
  }
  window.addEventListener('readaria-consent-changed', consentChangeListener)
})
onUnmounted(() => {
  if (storageListener) {
    window.removeEventListener('storage', storageListener)
  }
  if (consentChangeListener) {
    window.removeEventListener('readaria-consent-changed', consentChangeListener)
  }
})

const toggleAnalytics = (enabled) => {
  if (enabled) {
    localStorage.setItem('readaria_cookie_consent', 'accepted')
    analyticsConsent.value = true
    window.dispatchEvent(new CustomEvent('readaria-consent-changed', { detail: { consent: 'accepted' } }))
    const posthogKey = import.meta.env.VITE_POSTHOG_KEY
    if (import.meta.env.PROD && posthogKey && !posthog.__loaded) {
      initPostHog(posthogKey)
    } else if (posthog.__loaded) {
      posthog.opt_in_capturing()
      // re-identify 当前登录用户
      try {
        if (userStore.isLoggedIn && userStore.user) {
          posthog.identify(userStore.user.id, {
            email: userStore.user.email,
            username: userStore.user.username,
          })
        }
      } catch (e) {}
    }
    showToast(t('common.success'))
  } else {
    localStorage.setItem('readaria_cookie_consent', 'declined')
    analyticsConsent.value = false
    window.dispatchEvent(new CustomEvent('readaria-consent-changed', { detail: { consent: 'declined' } }))
    if (posthog.__loaded) {
      posthog.opt_out_capturing()
      posthog.reset()
    }
    showToast(t('common.success'))
  }
}

const handleExportData = async () => {
  const toast = showLoadingToast({ message: t('me.dataExporting'), duration: 0, forbidClick: true })
  try {
    const res = await request({ url: '/api/auth/data-export', method: 'get', responseType: 'blob' })
    const data = res.data || res
    const blob = data instanceof Blob ? data : new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `readaria_data_export_${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
    closeToast()
    showToast({ message: t('me.dataExportSuccess'), icon: 'success' })
  } catch (error) {
    closeToast()
    showToast({ message: t('me.dataExportFailed'), icon: 'fail' })
  }
}

const isOAuthUser = computed(() => currentUser.value?.auth_provider === 'google')

const handleContactUs = () => {
  window.location.href = 'mailto:you@example.com'
}

const handleInstallApp = async () => {
  const result = await pwaStore.triggerInstall('me_view')
  if (result === 'manual-install') {
    showToast({ message: t('me.installAppManualHint'), duration: 4000 })
  } else if (result === 'unavailable') {
    showToast({ message: t('me.installAppUnavailable'), icon: 'fail' })
  }
}

const handleDeleteAccount = async () => {
  try {
    await showConfirmDialog({
      title: t('me.deleteAccount'),
      message: t('me.deleteAccountConfirm'),
      confirmButtonColor: '#ee0a24'
    })
  } catch {
    return // user cancelled
  }

  // OAuth users (Google) don't have a password — skip password input
  if (isOAuthUser.value) {
    await doDeleteAccount()
    return
  }

  // Show password input dialog for password-registered users
  deletePassword.value = ''
  showDeleteConfirm.value = true
}

const beforeDeleteClose = (action) => {
  if (action !== 'confirm') return true
  if (!deletePassword.value) {
    showToast({ message: t('me.deleteAccountPassword'), icon: 'fail' })
    return false
  }
  doDeleteAccount()
  return true
}

const doDeleteAccount = async () => {
  const toast = showLoadingToast({ message: t('common.loading'), duration: 0, forbidClick: true })
  try {
    await deleteAccount(deletePassword.value)
    closeToast()
    showToast({ message: t('me.deleteAccountSuccess'), icon: 'success' })
    await userStore.logout()
    setTimeout(() => router.replace({ name: 'login' }), 500)
  } catch (error) {
    closeToast()
    showToast({ message: t('me.deleteAccountFailed'), icon: 'fail' })
  }
}

const handleLogout = () => {
  showDialog({
    title: t('me.logoutConfirmTitle'),
    message: t('me.logoutConfirmMessage'),
  }).then(async () => {
    try {
      await logoutApi()
    } catch (error) {
      console.error('Logout API failed:', error)
    }

    await userStore.logout()

    showToast({
      message: t('me.logoutSuccess'),
      icon: 'success'
    })

    setTimeout(() => {
      router.replace({ name: 'login' })
    }, 500)
  }).catch(() => {})
}

// Language picker
const showLangPicker = ref(false)
const langActions = computed(() => [
  { name: '中文', value: 'zh', className: locale.value === 'zh' ? 'lang-active' : '' },
  { name: 'English', value: 'en', className: locale.value === 'en' ? 'lang-active' : '' },
])
const onLangSelect = async (action) => {
  setLocale(action.value)
  showLangPicker.value = false
  try {
    await updateLanguage(action.value)
    // 同步更新本地用户信息
    if (userStore.user) {
      userStore.user.preferred_language = action.value
    }
  } catch (e) {
    console.error('同步语言偏好失败', e)
  }
}

const onAutoPodcastChange = async (value) => {
  try {
    await updateAutoPodcast(value)
    if (userStore.user) {
      userStore.user.auto_podcast_enabled = value
      localStorage.setItem('readaria_user', JSON.stringify(userStore.user))
    }
  } catch (e) {
    console.error('同步自动播客设置失败', e)
    showToast({ message: t('common.updateFailed'), icon: 'fail' })
  }
}

// TTS 音色选择
const showVoicePicker = ref(false)
const voicePickerLang = ref('zh')
const voiceCatalog = ref({ zh: [], en: [] })
let voiceCatalogLoaded = false

const openVoicePicker = async (lang) => {
  voicePickerLang.value = lang
  showVoicePicker.value = true
  if (!voiceCatalogLoaded) {
    voiceCatalogLoaded = true
    try {
      voiceCatalog.value = await getTtsVoices()
    } catch (e) {
      voiceCatalogLoaded = false
      console.error('加载音色目录失败', e)
      showToast({ message: t('common.loadFailed'), icon: 'fail' })
    }
  }
}

const voiceCellLabel = (lang) => {
  const voiceId = lang === 'zh'
    ? currentUser.value?.tts_voice_zh
    : currentUser.value?.tts_voice_en
  if (!voiceId) return t('me.voiceDefault')
  const hit = (voiceCatalog.value[lang] || []).find(v => v.id === voiceId)
  if (hit) return hit.name
  // 目录未加载时从音色 id 提取可读名（如 zh-CN-YunyangNeural → Yunyang）
  const m = voiceId.match(/^[a-z]{2}-[A-Z]{2}-([A-Za-z]+)/)
  return m ? m[1] : voiceId
}

const onVoiceSelect = async (voiceId) => {
  const field = voicePickerLang.value === 'zh' ? 'tts_voice_zh' : 'tts_voice_en'
  try {
    await updateTtsVoices({ [field]: voiceId })
    if (userStore.user) {
      userStore.user[field] = voiceId
      localStorage.setItem('readaria_user', JSON.stringify(userStore.user))
    }
    showVoicePicker.value = false
    showToast({ message: t('common.success'), icon: 'success' })
  } catch (e) {
    console.error('保存音色偏好失败', e)
    showToast({ message: t('common.updateFailed'), icon: 'fail' })
  }
}

// Feedback
const openFeedback = () => {
  feedbackText.value = ''
  feedbackAttachLogs.value = false
  showFeedback.value = true
}

const submitFeedback = async () => {
  if (!feedbackText.value.trim()) return
  const toast = showLoadingToast({ message: t('common.loading'), duration: 0, forbidClick: true })
  try {
    const payload = {
      message: feedbackText.value,
      attach_logs: feedbackAttachLogs.value,
    }
    if (feedbackAttachLogs.value) {
      payload.frontend_logs = frontendLogCollector.logs || []
    }
    await request({
      url: '/api/v1/feedback',
      method: 'post',
      data: payload
    })
    closeToast()
    showFeedback.value = false
    showToast({ message: t('me.feedbackSent'), icon: 'success' })
  } catch {
    closeToast()
    showToast({ message: t('me.feedbackFailed'), icon: 'fail' })
    // 保持对话框打开，让用户可以重试
  }
}

const handleExportOpml = async () => {
  const toast = showLoadingToast({ message: t('me.opmlExporting'), duration: 0, forbidClick: true })
  try {
    const res = await exportOpml()
    const blob = new Blob([res.data || res], { type: 'application/xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `readaria_feeds_${Date.now()}.opml`
    a.click()
    URL.revokeObjectURL(url)
    closeToast()
    showToast({ message: t('me.opmlExportSuccess'), icon: 'success' })
  } catch (error) {
    closeToast()
    showToast({ message: t('me.opmlExportFailed'), icon: 'fail' })
  }
}

const triggerImportOpml = () => {
  fileInput.value?.click()
}

const handleImportOpml = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return

  // Reset input so same file can be selected again
  event.target.value = ''

  if (!file.name.endsWith('.opml') && !file.name.endsWith('.xml')) {
    showToast({ message: t('me.opmlInvalidFile'), icon: 'fail' })
    return
  }

  importing.value = true
  const toast = showLoadingToast({ message: t('me.opmlImporting'), duration: 0, forbidClick: true })
  try {
    const res = await importOpml(file)
    const data = res.data || res
    closeToast()
    importing.value = false

    const msg = t('me.opmlImportResult', {
      imported: data.imported || 0,
      skipped: data.skipped || 0,
      failed: data.failed || 0
    })
    showDialog({ title: t('me.opmlImportDone'), message: msg })

    // Refresh feed list
    if (data.imported > 0) {
      await feedStore.fetchFeeds(true)
    }
  } catch (error) {
    closeToast()
    importing.value = false
    showToast({ message: t('me.opmlImportFailed'), icon: 'fail' })
  }
}
</script>

<template>
  <div class="me-view">
    <van-nav-bar :title="$t('me.title')" fixed placeholder />

    <!-- User info card -->
    <div class="user-card">
      <div class="avatar">{{ currentUser?.username?.charAt(0).toUpperCase() || 'U' }}</div>
      <div class="user-info">
        <div class="username">{{ currentUser?.username || $t('me.notLoggedIn') }}</div>
        <div class="email">{{ currentUser?.email || '' }}</div>
      </div>
    </div>

    <!-- My content -->
    <van-cell-group inset :title="$t('me.myContent')">
      <van-cell :title="$t('me.manageFeeds')" is-link @click="router.push({ name: 'feed-manage' })" />
      <van-cell :title="$t('me.mySaved')" is-link @click="router.push({ name: 'saved' })" />
    </van-cell-group>

    <!-- PWA install entry (only shown when app is not yet installed) -->
    <div
      v-if="pwaStore.shouldShowInstallEntry"
      class="install-card"
      role="button"
      tabindex="0"
      :aria-label="$t('me.installApp')"
      @click="handleInstallApp"
      @keydown.enter.prevent="handleInstallApp"
      @keydown.space.prevent="handleInstallApp"
    >
      <div class="install-card-icon">
        <img src="/pwa-192x192.png" alt="Readaria" />
      </div>
      <div class="install-card-text">
        <div class="install-card-title">{{ $t('me.installApp') }}</div>
        <div class="install-card-subtitle">
          {{ (pwaStore.isIos && pwaStore.isSafari) ? $t('me.installAppDescIos') : $t('me.installAppDescAndroid') }}
        </div>
      </div>
      <van-icon name="arrow" class="install-card-arrow" />
    </div>

    <!-- OPML -->
    <van-cell-group inset :title="$t('me.opmlTitle')">
      <van-cell :title="$t('me.opmlImport')" is-link @click="triggerImportOpml" />
      <van-cell :title="$t('me.opmlExport')" is-link @click="handleExportOpml" />
      <input ref="fileInput" type="file" accept=".opml,.xml" style="display:none" @change="handleImportOpml" />
    </van-cell-group>

    <!-- Settings -->
    <van-cell-group inset :title="$t('me.settings')">
      <van-cell
        :title="$t('me.language')"
        :value="locale === 'en' ? 'English' : '中文'"
        is-link
        @click="showLangPicker = true"
      />
      <van-cell
        :title="$t('me.ttsVoiceZh')"
        :value="voiceCellLabel('zh')"
        is-link
        @click="openVoicePicker('zh')"
      />
      <van-cell
        :title="$t('me.ttsVoiceEn')"
        :value="voiceCellLabel('en')"
        is-link
        @click="openVoicePicker('en')"
      />
      <van-cell :title="$t('me.autoPodcast')">
        <template #right-icon>
          <van-switch
            :model-value="currentUser?.auto_podcast_enabled ?? true"
            @update:model-value="onAutoPodcastChange"
            size="20px"
          />
        </template>
      </van-cell>
      <van-cell :title="$t('me.analytics')" :label="$t('me.analyticsDesc')">
        <template #right-icon>
          <van-switch
            :model-value="analyticsEnabled"
            @update:model-value="toggleAnalytics"
            size="20px"
          />
        </template>
      </van-cell>
      <van-cell
        :title="$t('me.feedback')"
        :label="$t('me.feedbackDesc')"
        is-link
        @click="openFeedback"
      />
    </van-cell-group>

    <!-- Language picker -->
    <van-action-sheet
      v-model:show="showLangPicker"
      :actions="langActions"
      :cancel-text="$t('common.cancel')"
      safe-area-inset-bottom
      teleport="body"
      @select="onLangSelect"
    />

    <!-- TTS voice picker -->
    <VoicePicker
      v-model:show="showVoicePicker"
      :title="voicePickerLang === 'zh' ? $t('me.voicePickerZh') : $t('me.voicePickerEn')"
      :lang="voicePickerLang"
      :voices="voiceCatalog[voicePickerLang] || []"
      :model-value="voicePickerLang === 'zh' ? (currentUser?.tts_voice_zh ?? null) : (currentUser?.tts_voice_en ?? null)"
      @select="onVoiceSelect"
    />

    <!-- Advanced settings (collapsed by default) -->
    <van-collapse v-model="settingsExpanded" class="settings-collapse">
      <van-collapse-item name="advanced" :title="$t('me.about')">
        <van-cell-group inset>
          <van-cell :title="$t('me.dataExport')" is-link @click="handleExportData" />
          <van-cell :title="$t('me.privacyPolicy')" is-link @click="router.push({ name: 'privacy' })" />
          <van-cell :title="$t('me.termsOfService')" is-link @click="router.push({ name: 'terms' })" />
          <van-cell
            :title="$t('me.contactUs')"
            is-link
            @click="handleContactUs"
          />
          <van-cell
            :title="$t('me.deleteAccount')"
            title-class="danger-text"
            is-link
            @click="handleDeleteAccount"
          />
        </van-cell-group>
      </van-collapse-item>
    </van-collapse>

    <!-- Logout -->
    <div class="logout-section">
      <van-button
        type="danger"
        block
        round
        @click="handleLogout"
      >
        {{ $t('me.logout') }}
      </van-button>
    </div>

    <!-- Feedback dialog -->
    <van-dialog
      v-model:show="showFeedback"
      :title="$t('me.feedback')"
      show-cancel-button
      :before-close="(action) => { if (action === 'confirm') { submitFeedback(); return false } return true }"
    >
      <div style="padding: 16px">
        <van-field
          v-model="feedbackText"
          type="textarea"
          :placeholder="$t('me.feedbackPlaceholder')"
          rows="4"
          autosize
        />
        <van-checkbox v-model="feedbackAttachLogs" style="margin-top: 8px">
          {{ $t('me.feedbackAttachLogs') }}
        </van-checkbox>
      </div>
    </van-dialog>

    <!-- Delete account password confirmation dialog -->
    <van-dialog
      v-model:show="showDeleteConfirm"
      :title="t('me.deleteAccount')"
      show-cancel-button
      :confirm-button-color="'#ee0a24'"
      :before-close="beforeDeleteClose"
    >
      <div style="padding: 16px">
        <van-field
          v-model="deletePassword"
          type="password"
          :placeholder="t('me.deleteAccountPassword')"
        />
      </div>
    </van-dialog>
  </div>
</template>

<style scoped>
.me-view {
  min-height: 100vh;
  background:
    radial-gradient(circle at top, rgba(199, 91, 57, 0.1), transparent 30%),
    linear-gradient(180deg, var(--readaria-paper) 0%, var(--readaria-stone) 100%);
  padding-top: 12px;
  padding-bottom: calc(50px + env(safe-area-inset-bottom, 0px) + 20px);
}

.user-card {
  display: flex;
  align-items: center;
  background: rgba(255, 250, 243, 0.92);
  padding: 20px 16px;
  margin: 12px;
  border-radius: 24px;
  border: 1px solid var(--readaria-border);
  box-shadow: 0 16px 36px rgba(64, 45, 31, 0.1);
}

.avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--readaria-accent) 0%, #9a674f 100%);
  color: var(--readaria-paper);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 600;
  margin-right: 16px;
  flex-shrink: 0;
}

.user-info {
  flex: 1;
}

.username {
  font-size: 18px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin-bottom: 4px;
}

.email {
  font-size: 14px;
  color: var(--readaria-muted);
}

/* PWA install entry card */
.install-card {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 12px;
  padding: 14px 16px;
  border-radius: 22px;
  background: linear-gradient(135deg, var(--readaria-navy) 0%, #1e3a5f 100%);
  color: white;
  box-shadow: 0 14px 30px rgba(23, 33, 48, 0.18);
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.install-card:active {
  transform: scale(0.985);
  box-shadow: 0 8px 18px rgba(23, 33, 48, 0.22);
}

.install-card:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.85);
  outline-offset: 2px;
}

.install-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  overflow: hidden;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
  background: rgba(255, 255, 255, 0.06);
}

.install-card-icon img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.install-card-text {
  flex: 1;
  min-width: 0;
}

.install-card-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  margin-bottom: 3px;
}

.install-card-subtitle {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.4;
}

.install-card-arrow {
  color: rgba(255, 255, 255, 0.7);
  font-size: 16px;
  flex-shrink: 0;
}

/* Settings collapse */
.settings-collapse {
  margin: 0 12px;
}

.settings-collapse :deep(.van-collapse-item__title) {
  padding: 12px 16px;
}

.settings-collapse :deep(.van-collapse-item__content) {
  padding: 0;
}

.settings-collapse :deep(.van-cell-group--inset) {
  margin: 0;
}

.danger-text {
  color: #b42318 !important;
}

.logout-section {
  padding: 20px 16px;
  margin-top: 12px;
}

:deep(.lang-active) {
  color: var(--readaria-accent) !important;
  font-weight: 600;
}

:deep(.van-cell-group--inset) {
  margin: 12px;
  overflow: hidden;
  border-radius: 22px;
  border: 1px solid var(--readaria-border);
  box-shadow: 0 14px 30px rgba(64, 45, 31, 0.08);
}

:deep(.van-cell-group__title) {
  padding-left: 18px;
  color: var(--readaria-muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

:deep(.van-cell) {
  background: rgba(255, 250, 243, 0.92);
  color: var(--readaria-ink);
}

:deep(.van-cell__label),
:deep(.van-cell__value) {
  color: var(--readaria-muted);
}

:deep(.van-switch--on) {
  background: var(--readaria-accent) !important;
}

</style>
