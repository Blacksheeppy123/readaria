<template>
  <div class="onboarding-path-view">
    <div class="content">
      <div class="header">
        <h1 class="title">{{ $t('onboarding.path.title') }}</h1>
      </div>

      <div class="path-cards">
        <!-- Quick Start (recommended) -->
        <div class="path-card path-card--primary">
          <div class="card-badge">{{ $t('onboarding.path.recommended') }}</div>
          <div class="card-icon">⚡</div>
          <div class="card-body">
            <h3>{{ $t('onboarding.path.quickStart') }}</h3>
            <p>{{ $t('onboarding.path.quickStartDesc') }}</p>
          </div>
          <van-button
            round
            block
            type="primary"
            size="small"
            class="card-cta"
            :loading="loading"
            @click.stop="confirmQuickStart"
          >
            {{ $t('common.confirm') }}
          </van-button>
        </div>

        <!-- Curate My Own -->
        <div class="path-card" @click="selectPath('manual'); goToDiscover()">
          <div class="card-icon">🛒</div>
          <div class="card-body">
            <h3>{{ $t('onboarding.path.curate') }}</h3>
            <p>{{ $t('onboarding.path.curateDesc') }}</p>
          </div>
          <van-icon name="arrow" color="var(--readaria-muted)" />
        </div>

        <!-- Import OPML -->
        <div class="path-card path-card--text" @click="selectPath('manual'); handleImportOpml()">
          <div class="card-icon">📥</div>
          <div class="card-body">
            <h3>{{ $t('onboarding.path.import') }}</h3>
            <p>{{ $t('onboarding.path.importDesc') }}</p>
          </div>
          <van-icon name="arrow" color="var(--readaria-muted)" />
        </div>
      </div>
    </div>

    <input ref="fileInput" type="file" accept=".opml,.xml" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast } from 'vant'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { useFeedStore } from '@/stores/feedStore'
import { useUserStore } from '@/stores/userStore'
import { resetOnboardingStarterPack, activateOnboardingStarterPack, createExperiencePodcast } from '@/api/onboarding'
import { importOpml } from '@/api/feeds'

const { t, locale } = useI18n()
const router = useRouter()
const onboardingStore = useOnboardingStore()
const feedStore = useFeedStore()
const userStore = useUserStore()

const loading = ref(false)
const fileInput = ref(null)

const selectPath = (path) => {
  onboardingStore.markPathSelected(path)
}

const confirmQuickStart = async () => {
  loading.value = true
  const toast = showLoadingToast({
    message: t('onboarding.addingFeeds') || 'Adding your feeds...',
    forbidClick: true,
    duration: 0
  })

  try {
    try {
      // 仅当用户已有 feeds 时才需要 reset（新用户必然 0 feeds，省一个 RTT）
      if (feedStore.feeds.length > 0) {
        await resetOnboardingStarterPack(locale.value, { silent: true })
      }
    } catch (e) {
      console.warn('[OnboardingPathView] reset starter pack failed:', e)
    }

    // 早早标记 experience podcast 已请求（120s 窗口从此刻开始计时，覆盖 starter pack 激活
    // 以及 router.replace 后 FeedView 兜底拉 podcasts 的最坏耗时）
    // 绑定当前 userId，避免跨账号在同一浏览器内误触发 starter-pack 兜底轮询
    onboardingStore.markExperiencePodcastRequested(userStore.user?.id)

    // 与 starter pack 激活并行触发 experience podcast 复制：copy 操作不依赖用户 feeds，
    // 提前并行启动可让 cache podcast 在跳转到 FeedView 时基本已就绪。
    // 关键路径**不再 await** 这个 promise——promise 自带 catch 静默兜底，
    // FeedView 落地后由 watcher + 8s setTimeout 再 fetch 一次 podcasts 兜底发现 cache。
    createExperiencePodcast(locale.value, { silent: true })
      .catch((err) => {
        console.warn('[OnboardingPathView] createExperiencePodcast failed:', err)
        return null
      })

    // 批量激活 starter pack：后端会在返回前同步链接已有全局文章，
    // 避免进入 FeedView 后首屏空白、只能靠用户手动下拉刷新。
    const activateResult = await activateOnboardingStarterPack(locale.value, { silent: true })
    const successCount = activateResult?.feeds?.length || 0

    if (successCount === 0) {
      closeToast()
      showToast({ message: t('feeds.addFailed'), icon: 'fail' })
      // 全部激活失败，撤回 marker，避免下游 FeedView 兜底轮询误触发
      onboardingStore.clearExperiencePodcastRequested?.()
      return
    }

    // 强制刷新 feedStore，避免 FeedView 命中旧的空订阅缓存。
    await feedStore.fetchFeeds(true)

    // 同样不 await experiencePodcast：speed-priority，FeedView watcher 兜底。

    closeToast()
    showToast({
      message: t('feeds.starterPackDone', { count: successCount }),
      icon: 'success',
      duration: 1500
    })

    onboardingStore.markPathSelected('starter_pack')

    router.replace({ name: 'feed' })
  } catch {
    closeToast()
    showToast({ message: t('feeds.addFailed'), icon: 'fail' })
    // 异常路径同样撤回 marker，避免 120s 窗口内进入 FeedView 误触发兜底
    onboardingStore.clearExperiencePodcastRequested?.()
  } finally {
    loading.value = false
  }
}

const goToDiscover = () => {
  router.replace({ name: 'feed-discover' })
}

const handleImportOpml = () => {
  fileInput.value?.click()
}

const onFileSelected = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  if (!file.name.match(/\.(opml|xml)$/i)) {
    showToast(t('me.opmlInvalidFile'))
    return
  }
  const toast = showLoadingToast({ message: t('me.opmlImporting'), forbidClick: true, duration: 0 })
  try {
    const res = await importOpml(file)
    const data = res.data || res
    closeToast()
    showToast({
      message: t('me.opmlImportResult', {
        imported: data.imported || 0,
        skipped: data.skipped || 0,
        failed: data.failed || 0
      }),
      duration: 3000
    })
    router.replace({ name: 'feed' })
  } catch {
    closeToast()
    showToast({ message: t('me.opmlImportFailed'), icon: 'fail' })
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}
</script>

<style scoped>
.onboarding-path-view {
  min-height: 100vh;
  background:
    radial-gradient(circle at 0% 0%, rgba(199, 91, 57, 0.1), transparent 28%),
    linear-gradient(180deg, var(--readaria-paper) 0%, var(--readaria-stone) 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px;
}

.content {
  width: 100%;
  max-width: 400px;
  padding-top: 40px;
}

.header {
  text-align: center;
  margin-bottom: 32px;
}

.title {
  font-family: var(--readaria-serif);
  font-size: 24px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0;
}

.path-cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.path-card {
  background: rgba(255, 252, 248, 0.88);
  border: 1.5px solid var(--readaria-border);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.path-card:hover {
  border-color: var(--readaria-accent);
  box-shadow: 0 4px 16px rgba(199, 91, 57, 0.1);
}

.path-card--primary {
  border-color: var(--readaria-accent);
  border-width: 2px;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
}

.path-card--text {
  border-style: dashed;
}

.card-badge {
  align-self: flex-start;
  background: var(--readaria-accent);
  color: white;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.card-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.card-body {
  flex: 1;
}

.card-body h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--readaria-ink);
  margin: 0 0 4px;
}

.card-body p {
  font-size: 13px;
  color: var(--readaria-muted);
  margin: 0;
}

.topic-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill {
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 14px;
  background: var(--readaria-stone);
  color: var(--readaria-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;
}

.pill:hover,
.pill.active {
  background: rgba(199, 91, 57, 0.1);
  color: var(--readaria-accent);
  border-color: var(--readaria-accent);
}

.card-cta {
  margin-top: 4px;
}

:deep(.van-button--primary) {
  background: var(--readaria-navy);
  border-color: var(--readaria-navy);
}
</style>
