<template>
  <div class="register-view">
    <van-nav-bar
      :title="$t('register.title')"
      left-arrow
      @click-left="goBack"
      fixed
      placeholder
    />

    <div class="register-container">
      <!-- Logo -->
      <div class="logo-section">
        <div class="app-title">Readaria</div>
        <h1 class="register-heading">{{ $t('register.launchHeading') }}</h1>
        <p class="app-subtitle">{{ $t('register.launchSubtitle') }}</p>
      </div>

      <!-- Register form -->
      <van-form @submit="onSubmit">
        <van-cell-group inset>
          <van-field
            v-model="formData.username"
            name="username"
            :label="$t('register.username')"
            :placeholder="$t('register.usernamePlaceholder')"
            :rules="usernameRules"
            clearable
          />
          <van-field
            v-model="formData.email"
            name="email"
            type="email"
            :label="$t('register.email')"
            :placeholder="$t('register.emailPlaceholder')"
            :rules="emailRules"
            clearable
          />
          <van-field
            v-model="formData.password"
            type="password"
            name="password"
            :label="$t('register.password')"
            :placeholder="$t('register.passwordPlaceholder')"
            :rules="passwordRules"
            clearable
          />
          <van-field
            v-model="formData.confirmPassword"
            type="password"
            name="confirmPassword"
            :label="$t('register.confirmPassword')"
            :placeholder="$t('register.confirmPasswordPlaceholder')"
            :rules="confirmPasswordRules"
            clearable
          />
        </van-cell-group>

        <div class="button-group">
          <van-button
            round
            block
            type="primary"
            native-type="submit"
            :loading="loading"
          >
            {{ $t('register.registerButton') }}
          </van-button>

          <p class="legal-notice">
            {{ $t('register.agreePrefix') }}
            <router-link to="/terms">{{ $t('register.termsLink') }}</router-link>
            {{ $t('register.agreeAnd') }}
            <router-link to="/privacy">{{ $t('register.privacyLink') }}</router-link>
          </p>

          <!-- Google Sign-In -->
          <div v-if="googleClientId" class="divider">
            <span>{{ $t('login.or') }}</span>
          </div>
          <van-button
            v-if="googleClientId"
            round
            block
            plain
            :loading="googleLoading"
            class="google-btn"
            @click="handleGoogleLogin"
          >
            <span class="google-btn-content">
              <svg class="google-icon" viewBox="0 0 24 24" width="18" height="18">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              {{ $t('login.googleSignIn') }}
            </span>
          </van-button>

          <van-button
            round
            block
            plain
            type="primary"
            @click="goToLogin"
            class="login-btn"
          >
            {{ $t('register.hasAccount') }} {{ $t('register.login') }}
          </van-button>
        </div>
      </van-form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast } from 'vant'
import { register, googleLogin, getGoogleClientId } from '@/api/auth'
import { useUserStore } from '@/stores/userStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { trackSignupCompleted, trackLoginCompleted } from '@/utils/analytics'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const onboardingStore = useOnboardingStore()

const formData = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const loading = ref(false)
const googleLoading = ref(false)
const googleClientId = ref(null)

onMounted(async () => {
  // Fetch Google OAuth client ID
  try {
    const res = await getGoogleClientId()
    const cid = res?.client_id || res?.data?.client_id
    if (cid) {
      googleClientId.value = cid
      loadGoogleScript(cid)
    }
  } catch (_) {
    // Google OAuth not configured — hide button
  }
})

const loadGoogleScript = (clientId) => {
  if (document.getElementById('google-gsi-script')) return
  const script = document.createElement('script')
  script.id = 'google-gsi-script'
  script.src = 'https://accounts.google.com/gsi/client'
  script.async = true
  script.defer = true
  script.onload = () => {
    window.google?.accounts.id.initialize({
      client_id: clientId,
      callback: onGoogleCredentialResponse
    })
  }
  document.head.appendChild(script)
}

const onGoogleCredentialResponse = async (response) => {
  if (!response?.credential) return
  googleLoading.value = true
  const toast = showLoadingToast({ message: t('common.loading'), forbidClick: true, duration: 0 })

  try {
    const res = await googleLogin(response.credential)
    await userStore.setUser(res.user, res.access_token)
    if (res.is_new_user) {
      trackSignupCompleted('google')
    } else {
      trackLoginCompleted('google')
    }
    closeToast()
    showToast({ message: t('login.loginSuccess'), icon: 'success' })
    setTimeout(() => {
      if (res.is_new_user) {
        // 新用户直接进入语言与内容源 onboarding
        router.replace({ name: 'onboarding-language' })
      } else {
        // 已有用户：主动完成 onboarding，避免 stale state 被 router guard 拉回 onboarding
        onboardingStore.markFirstAudioPlayed()
        router.replace({ name: 'feed' })
      }
    }, 500)
  } catch (error) {
    closeToast()
    const msg = error.response?.data?.detail || t('login.loginFailed')
    showToast({ message: msg, icon: 'fail' })
  } finally {
    googleLoading.value = false
  }
}

const handleGoogleLogin = () => {
  if (window.google?.accounts?.id) {
    window.google.accounts.id.prompt()
  } else {
    showToast(t('login.googleNotReady'))
  }
}

// Validation rules
const usernameRules = [
  { required: true, message: t('register.usernameRequired') },
  { pattern: /^[a-zA-Z0-9_-]{3,20}$/, message: t('register.usernameFormat') }
]

const emailRules = [
  { required: true, message: t('register.emailRequired') },
  { pattern: /^[\w-]+(\.[\w-]+)*@[\w-]+(\.[\w-]+)+$/, message: t('register.emailInvalid') }
]

const passwordRules = [
  { required: true, message: t('register.passwordRequired') },
  { min: 8, message: t('register.passwordMinLength') }
]

const confirmPasswordRules = [
  { required: true, message: t('register.confirmPasswordRequired') },
  {
    validator: (value) => value === formData.value.password,
    message: t('register.passwordMismatch')
  }
]

const onSubmit = async () => {
  if (formData.value.password !== formData.value.confirmPassword) {
    showToast({
      message: t('register.passwordMismatch'),
      icon: 'fail'
    })
    return
  }

  // 自托管版注册无需邀请码

  loading.value = true
  showLoadingToast({
    message: t('common.loading'),
    forbidClick: true,
    duration: 0
  })

  try {
    const payload = {
      username: formData.value.username,
      email: formData.value.email,
      password: formData.value.password,
      preferred_language: locale.value || localStorage.getItem('locale') || 'en'
    }
    const response = await register(payload)

    console.log('Register response:', response)

    await userStore.setUser(response.user, response.access_token)
    trackSignupCompleted('email')

    closeToast()
    showToast({
      message: t('register.registerSuccess'),
      icon: 'success'
    })

    setTimeout(() => {
      router.replace({ name: 'onboarding-language' })
    }, 500)

  } catch (error) {
    closeToast()
    console.error('Register failed:', error)
    console.error('Register request details:', {
      method: error.config?.method,
      url: error.config?.url,
      baseURL: error.config?.baseURL,
      status: error.response?.status,
      statusText: error.response?.statusText,
      responseData: error.response?.data
    })

    let errorMessage = t('register.registerFailed')
    if (error.response?.data?.detail) {
      errorMessage = error.response.data.detail
    } else if (error.response?.status === 405) {
      errorMessage = 'Registration method not allowed. Please clear app cache and try again.'
    } else if (error.message) {
      errorMessage = error.message
    }

    showToast({
      message: errorMessage,
      icon: 'fail'
    })
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.back()
}

const goToLogin = () => {
  router.replace({ name: 'login', query: route.query.redirect ? { redirect: route.query.redirect } : {} })
}
</script>

<style scoped>
.register-view {
  min-height: 100vh;
  background:
    radial-gradient(circle at 0% 0%, rgba(199, 91, 57, 0.1), transparent 28%),
    linear-gradient(180deg, var(--readaria-paper) 0%, var(--readaria-stone) 100%);
  color: var(--readaria-ink);
}

.register-container {
  padding: 24px 18px 48px;
}

.logo-section {
  margin-bottom: 32px;
  padding-top: 10px;
  display: grid;
  gap: 12px;
}

.app-title {
  font-family: var(--readaria-serif);
  font-size: 24px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--readaria-ink);
}

.register-heading {
  font-family: var(--readaria-serif);
  font-size: 34px;
  line-height: 1.04;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0;
}

.app-subtitle {
  font-size: 14px;
  color: var(--readaria-muted);
  margin: 0;
  line-height: 1.6;
}

.button-group {
  margin-top: 24px;
  padding: 0 16px;
}

.login-btn {
  margin-top: 12px;
}

.divider {
  display: flex;
  align-items: center;
  margin: 16px 0;
  color: var(--readaria-muted);
  font-size: 13px;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--readaria-border);
}

.divider span {
  padding: 0 12px;
}

.google-btn {
  margin-bottom: 12px;
  background: rgba(255, 252, 248, 0.88) !important;
  color: var(--readaria-ink) !important;
  border-color: var(--readaria-border) !important;
}

.google-btn-content {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
}

.google-icon {
  flex-shrink: 0;
}

.legal-notice {
  text-align: center;
  font-size: 12px;
  color: var(--readaria-muted);
  margin: 12px 0 0;
  line-height: 1.5;
}

.legal-notice a {
  color: var(--readaria-accent);
  text-decoration: underline;
}

.van-cell-group {
  background: rgba(255, 252, 248, 0.88);
  border-radius: 22px;
  overflow: hidden;
  border: 1px solid var(--readaria-border);
  box-shadow: 0 18px 40px rgba(64, 45, 31, 0.08);
}

:deep(.van-button--primary) {
  background: var(--readaria-navy);
  border-color: var(--readaria-navy);
}

:deep(.van-button--plain) {
  color: var(--readaria-navy);
  border-color: var(--readaria-navy);
}
</style>
