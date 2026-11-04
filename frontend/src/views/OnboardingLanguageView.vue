<template>
  <div class="onboarding-language-view">
    <div class="content">
      <div class="header">
        <h1 class="title">{{ $t('onboarding.language.title') }}</h1>
        <p class="subtitle">{{ $t('onboarding.language.subtitle') }}</p>
      </div>

      <div class="language-cards">
        <div
          class="language-card"
          :class="{ selected: selectedLang === 'en' }"
          @click="selectLanguage('en')"
        >
          <div class="flag">🇺🇸</div>
          <div class="lang-name">{{ $t('onboarding.language.english') }}</div>
          <div class="lang-desc">English content and interface</div>
          <van-icon
            v-if="selectedLang === 'en'"
            name="success"
            class="check-icon"
            color="var(--readaria-accent)"
          />
        </div>

        <div
          class="language-card"
          :class="{ selected: selectedLang === 'zh' }"
          @click="selectLanguage('zh')"
        >
          <div class="flag">🇨🇳</div>
          <div class="lang-name">{{ $t('onboarding.language.chinese') }}</div>
          <div class="lang-desc">中文内容和界面</div>
          <van-icon
            v-if="selectedLang === 'zh'"
            name="success"
            class="check-icon"
            color="var(--readaria-accent)"
          />
        </div>
      </div>

      <van-button
        round
        block
        type="primary"
        class="continue-btn"
        :disabled="!selectedLang || saving"
        :loading="saving"
        @click="confirmLanguage"
      >
        {{ $t('common.confirm') }}
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { updateLanguage } from '@/api/auth'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useUserStore } from '@/stores/userStore'
import { setLocale } from '@/i18n'

const { t } = useI18n()
const router = useRouter()
const onboardingStore = useOnboardingStore()

const selectedLang = ref('')
const saving = ref(false)

const selectLanguage = (lang) => {
  selectedLang.value = lang
}

const confirmLanguage = async () => {
  if (!selectedLang.value) return

  saving.value = true
  try {
    await updateLanguage(selectedLang.value)
    setLocale(selectedLang.value)
    // Sync in-memory user profile so client features read the right preference
    const userStore = useUserStore()
    if (userStore.user) {
      userStore.user.preferred_language = selectedLang.value
      localStorage.setItem('readaria_user', JSON.stringify(userStore.user))
    }
    onboardingStore.markLanguageSelected()
    router.replace({ name: 'onboarding-path' })
  } catch (error) {
    console.error('Failed to save language:', error)
    showToast({ message: t('common.syncFailed'), icon: 'fail' })
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.onboarding-language-view {
  min-height: 100vh;
  background:
    radial-gradient(circle at 0% 0%, rgba(199, 91, 57, 0.1), transparent 28%),
    linear-gradient(180deg, var(--readaria-paper) 0%, var(--readaria-stone) 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.content {
  width: 100%;
  max-width: 400px;
}

.header {
  text-align: center;
  margin-bottom: 40px;
}

.title {
  font-family: var(--readaria-serif);
  font-size: 28px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 12px;
}

.subtitle {
  font-size: 14px;
  color: var(--readaria-muted);
  margin: 0;
}

.language-cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 32px;
}

.language-card {
  background: rgba(255, 252, 248, 0.88);
  border: 2px solid var(--readaria-border);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.language-card:hover,
.language-card.selected {
  border-color: var(--readaria-accent);
  box-shadow: 0 4px 16px rgba(199, 91, 57, 0.12);
}

.flag {
  font-size: 32px;
  flex-shrink: 0;
}

.lang-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--readaria-ink);
  flex: 1;
}

.lang-desc {
  font-size: 12px;
  color: var(--readaria-muted);
  position: absolute;
  bottom: 12px;
  left: 72px;
}

.check-icon {
  font-size: 20px;
}

.continue-btn {
  margin-top: 8px;
}

:deep(.van-button--primary) {
  background: var(--readaria-navy);
  border-color: var(--readaria-navy);
}

:deep(.van-button--primary.van-button--disabled) {
  opacity: 0.5;
}
</style>
