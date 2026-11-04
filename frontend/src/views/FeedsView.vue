<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast, showConfirmDialog } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { testFeedUrl } from '@/api/feeds'
import { recommendedFeeds } from '@/config/recommendedFeeds'
import { trackSubscriptionAdded } from '@/utils/analytics'

const { t, locale } = useI18n()
const feedStore = useFeedStore()
const loading = ref(false)
const refreshing = ref(false)
const showAddDialog = ref(false)
const disabledFeeds = ref(new Set())
const subscribingFeeds = ref(new Set())

const normalizeUrl = (url) => url?.replace(/\/$/, '') || url
const existingUrls = computed(() => new Set(feedStore.feeds.map(f => normalizeUrl(f.feed_url))))

const getCategoryLabel = (cat) => {
  const lang = locale.value === 'zh' ? 'zh' : 'en'
  return cat.label[lang] || cat.label.en
}

const isSubscribed = (url) => existingUrls.value.has(normalizeUrl(url))

const detectSourceType = (url) => {
  if (url.includes('bilibili')) return 'bilibili'
  if (url.includes('twitter') || url.includes('x.com')) return 'twitter'
  return 'rss'
}

const subscribeRecommended = async (feed) => {
  if (subscribingFeeds.value.has(feed.url) || isSubscribed(feed.url)) return
  subscribingFeeds.value.add(feed.url)
  try {
    await feedStore.createFeed({ feed_name: feed.name, feed_url: feed.url })
    trackSubscriptionAdded(detectSourceType(feed.url))
    showToast({ message: t('feeds.addSuccess'), icon: 'success' })
  } catch {
    showToast({ message: t('feeds.addFailed'), icon: 'fail' })
  } finally {
    subscribingFeeds.value.delete(feed.url)
  }
}

const formData = ref({
  feed_name: '',
  feed_url: ''
})

let refreshTimer = null

onMounted(async () => {
  await loadFeeds()
  const first = await feedStore.fetchRefreshStatus()
  if (first !== null) {
    refreshTimer = setInterval(() => feedStore.fetchRefreshStatus(), 8000)
  }
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})

const loadFeeds = async () => {
  loading.value = true
  try {
    await feedStore.fetchFeeds()
  } catch (error) {
    showToast(t('common.loadFailed'))
    throw error
  } finally {
    loading.value = false
  }
}

const onRefresh = async () => {
  refreshing.value = true
  try {
    await loadFeeds()
    showToast(t('feeds.refreshSuccess'))
  } catch (error) {
    showToast(t('feeds.refreshFailed'))
  } finally {
    refreshing.value = false
  }
}

const openAddDialog = () => {
  formData.value = {
    feed_name: '',
    feed_url: ''
  }
  showAddDialog.value = true
}

const onSubmit = async () => {
  if (!formData.value.feed_name || !formData.value.feed_url) {
    showToast(t('feeds.feedNameRequired'))
    return
  }

  const toast = showLoadingToast({
    message: t('common.loading'),
    forbidClick: true,
    duration: 0
  })

  try {
    await testFeedUrl(formData.value.feed_url)
    await feedStore.createFeed(formData.value)
    trackSubscriptionAdded(detectSourceType(formData.value.feed_url))
    closeToast()
    showToast({ message: t('feeds.addSuccess'), icon: 'success' })
    showAddDialog.value = false
    await loadFeeds()
  } catch (error) {
    closeToast()
    showToast({ message: t('feeds.addFailed'), icon: 'fail' })
  }
}

const onDelete = async (feed) => {
  try {
    await showConfirmDialog({
      title: t('feeds.deleteConfirmTitle'),
      message: t('feeds.deleteConfirmMessage', { name: feed.feed_name })
    })
    await feedStore.removeFeed(feed.id)
    showToast({ message: t('feeds.deleteSuccess'), icon: 'success' })
    await loadFeeds()
  } catch (error) {
    if (error !== 'cancel') {
      showToast({ message: t('feeds.deleteFailed'), icon: 'fail' })
    }
  }
}

const onRefreshFeed = async (feed) => {
  if (disabledFeeds.value.has(feed.id)) return
  disabledFeeds.value.add(feed.id)
  try {
    await feedStore.refreshFeed(feed.id)
    showToast({ message: t('feeds.refreshSuccess'), icon: 'success' })
  } catch (error) {
    showToast({ message: t('feeds.refreshFailed'), icon: 'fail' })
  } finally {
    setTimeout(() => disabledFeeds.value.delete(feed.id), 5000)
  }
}

const onRefreshAll = async () => {
  const toast = showLoadingToast({
    message: t('feeds.refreshing'),
    forbidClick: true,
    duration: 0
  })
  try {
    await feedStore.refreshAll()
    closeToast()
    showToast({ message: t('feeds.refreshSuccess'), icon: 'success' })
  } catch (error) {
    closeToast()
    showToast({ message: t('feeds.refreshFailed'), icon: 'fail' })
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const getLastSuccessText = (feedId) => {
  const st = feedStore.refreshStatus[feedId]
  if (!st) return t('feeds.neverSuccess')
  if (st.last_success_at) return t('feeds.lastSuccess', { time: formatDate(st.last_success_at) })
  return t('feeds.lastSuccessNone')
}

const getStatusText = (status) => {
  if (status === 'running') return t('feeds.statusRunning')
  if (status === 'success') return t('feeds.statusSuccess')
  return t('feeds.statusFailed')
}
</script>

<template>
  <div class="feeds-view">
    <van-nav-bar :title="$t('feeds.title')" fixed placeholder>
      <template #right>
        <van-space>
          <van-button size="small" @click="onRefreshAll">{{ $t('feeds.refreshAll') }}</van-button>
          <van-button size="small" type="primary" @click="openAddDialog">{{ $t('feeds.add') }}</van-button>
        </van-space>
      </template>
    </van-nav-bar>

    <van-pull-refresh
      v-model="refreshing"
      @refresh="onRefresh"
      :pull-distance="80"
      :head-height="50"
      :success-text="$t('feeds.refreshSuccess')"
      :success-duration="800"
    >
      <!-- 骨架屏 -->
      <template v-if="feedStore.feeds.length === 0 && loading">
        <div v-for="i in 3" :key="i" class="skeleton-card">
          <van-skeleton title :row="2" />
        </div>
      </template>

      <!-- 空状态：推荐订阅源 -->
      <div v-else-if="feedStore.feeds.length === 0 && !loading" class="empty-state">
        <div class="discover-header">
          <h3 class="discover-title">{{ $t('feeds.discoverTitle') }}</h3>
          <p class="discover-desc">{{ $t('feeds.discoverDesc') }}</p>
        </div>

        <div class="recommend-categories">
          <div v-for="cat in recommendedFeeds" :key="cat.category" class="recommend-category">
            <div class="category-label">{{ getCategoryLabel(cat) }}</div>
            <van-cell-group inset>
              <van-cell
                v-for="feed in cat.feeds"
                :key="feed.url"
                :title="feed.name"
                center
              >
                <template #right-icon>
                  <van-button
                    size="small"
                    :type="isSubscribed(feed.url) ? 'default' : 'primary'"
                    :disabled="isSubscribed(feed.url) || subscribingFeeds.has(feed.url)"
                    :loading="subscribingFeeds.has(feed.url)"
                    @click="subscribeRecommended(feed)"
                  >
                    {{ isSubscribed(feed.url) ? $t('feeds.subscribed') : $t('feeds.subscribe') }}
                  </van-button>
                </template>
              </van-cell>
            </van-cell-group>
          </div>
        </div>

        <div class="custom-feed-hint">
          <van-button plain type="primary" size="small" @click="openAddDialog">
            {{ $t('feeds.addCustom') }}
          </van-button>
        </div>
      </div>

      <!-- 订阅列表 -->
      <van-list v-else>
        <van-card
          v-for="feed in feedStore.feeds"
          :key="feed.id"
          :title="feed.feed_name"
          :desc="feed.feed_url"
        >
          <template #footer>
            <div class="card-footer">
              <span class="feed-time">{{ getLastSuccessText(feed.id) }}</span>
              <div class="actions">
                <van-tag
                  v-if="feedStore.refreshStatus[feed.id]?.status"
                  :type="feedStore.refreshStatus[feed.id]?.status === 'success' ? 'success' : (feedStore.refreshStatus[feed.id]?.status === 'running' ? 'primary' : 'danger')"
                  plain
                  style="margin-right: 8px;"
                >
                  {{ getStatusText(feedStore.refreshStatus[feed.id]?.status) }}
                </van-tag>
                <van-button size="small" :disabled="disabledFeeds.has(feed.id) || feedStore.refreshStatus[feed.id]?.status==='running'" @click="onRefreshFeed(feed)">{{ $t('common.refresh') }}</van-button>
                <van-button size="small" type="danger" @click="onDelete(feed)">{{ $t('common.delete') }}</van-button>
              </div>
            </div>
          </template>
        </van-card>
      </van-list>
    </van-pull-refresh>

    <!-- 添加订阅对话框 -->
    <van-dialog v-model:show="showAddDialog" :title="$t('feeds.addFeed')" show-cancel-button @confirm="onSubmit">
      <van-form @submit="onSubmit">
        <van-field
          v-model="formData.feed_name"
          name="feed_name"
          :label="$t('feeds.feedName')"
          :placeholder="$t('feeds.feedNamePlaceholder')"
          :rules="[{ required: true, message: $t('feeds.feedNameRequired') }]"
        />
        <van-field
          v-model="formData.feed_url"
          name="feed_url"
          :label="$t('feeds.feedUrl')"
          :placeholder="$t('feeds.feedUrlPlaceholder')"
          :rules="[{ required: true, message: $t('feeds.feedUrlRequired') }]"
        />
      </van-form>
    </van-dialog>
  </div>
</template>

<style scoped>
.feeds-view {
  padding-bottom: 60px;
}

.skeleton-card {
  padding: 16px;
  margin-bottom: 12px;
}

.empty-state {
  padding: 20px 0;
}

.discover-header {
  text-align: center;
  padding: 16px 20px 8px;
}

.discover-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 4px;
  color: #323233;
}

.discover-desc {
  font-size: 13px;
  color: #969799;
  margin: 0;
}

.recommend-categories {
  padding: 8px 0;
}

.recommend-category {
  margin-bottom: 12px;
}

.category-label {
  font-size: 13px;
  font-weight: 600;
  color: #646566;
  padding: 4px 20px 4px;
}

.custom-feed-hint {
  text-align: center;
  padding: 12px 0 20px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
}

.feed-time {
  font-size: 12px;
  color: #969799;
}

.actions {
  display: flex;
  gap: 8px;
}

:deep(.van-card) {
  margin-bottom: 12px;
}
</style>
