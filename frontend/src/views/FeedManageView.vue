<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast, showConfirmDialog } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { exportOpml, importOpml } from '@/api/feeds'
import { getFaviconUrl } from '@/config/recommendedFeeds'
import AddFeedPopup from '@/components/AddFeedPopup.vue'

const { t } = useI18n()
const router = useRouter()
const feedStore = useFeedStore()
const loading = ref(false)
const refreshing = ref(false)
const showAddPopup = ref(false)
const searchQuery = ref('')
const fileInput = ref(null)
const importing = ref(false)

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

const filteredFeeds = computed(() => {
  if (!searchQuery.value.trim()) return feedStore.feeds
  const q = searchQuery.value.toLowerCase()
  return feedStore.feeds.filter(f =>
    f.feed_name.toLowerCase().includes(q) || f.feed_url.toLowerCase().includes(q)
  )
})

const showSearch = computed(() => feedStore.feeds.length > 5)

const loadFeeds = async () => {
  loading.value = true
  try { await feedStore.fetchFeeds() }
  catch { showToast(t('common.loadFailed')) }
  finally { loading.value = false }
}

const onRefresh = async () => {
  refreshing.value = true
  try { await loadFeeds() }
  finally { refreshing.value = false }
}

const onDelete = async (feed) => {
  try {
    await showConfirmDialog({
      title: t('feeds.deleteConfirmTitle'),
      message: t('feeds.deleteConfirmMessage', { name: feed.feed_name })
    })
    await feedStore.removeFeed(feed.id)
    showToast({ message: t('feeds.deleteSuccess'), icon: 'success' })
  } catch (e) {
    if (e !== 'cancel') showToast({ message: t('feeds.deleteFailed'), icon: 'fail' })
  }
}

const onRefreshAll = async () => {
  const toast = showLoadingToast({ message: t('feeds.refreshing'), forbidClick: true, duration: 0 })
  try {
    await feedStore.refreshAll()
    closeToast()
    showToast({ message: t('feeds.refreshSuccess'), icon: 'success' })
  } catch {
    closeToast()
    showToast({ message: t('feeds.refreshFailed'), icon: 'fail' })
  }
}

const getStatusInfo = (feedId) => {
  const st = feedStore.refreshStatus[feedId]
  if (!st) return null
  if (st.status === 'running') return { type: 'primary', text: t('feeds.statusRunning') }
  if (st.status === 'failed') return { type: 'danger', text: t('feeds.statusFailed') }
  return null // don't show success tag (clean UI)
}

const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const getSyncText = (feedId) => {
  const st = feedStore.refreshStatus[feedId]
  if (!st?.last_success_at) return ''
  return formatDate(st.last_success_at)
}

// OPML Import
const triggerImport = () => fileInput.value?.click()

const handleFileSelect = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  if (!file.name.match(/\.(opml|xml)$/i)) {
    showToast(t('me.opmlInvalidFile'))
    return
  }
  importing.value = true
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
    await feedStore.fetchFeeds(true)
  } catch {
    closeToast()
    showToast({ message: t('me.opmlImportFailed'), icon: 'fail' })
  } finally {
    importing.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

// OPML Export
const handleExport = async () => {
  const toast = showLoadingToast({ message: t('me.opmlExporting'), forbidClick: true, duration: 0 })
  try {
    const res = await exportOpml()
    const blob = res.data || res
    const url = URL.createObjectURL(blob instanceof Blob ? blob : new Blob([blob], { type: 'application/xml' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'readaria_feeds.opml'
    a.click()
    URL.revokeObjectURL(url)
    closeToast()
    showToast({ message: t('me.opmlExportSuccess'), icon: 'success' })
  } catch {
    closeToast()
    showToast({ message: t('me.opmlExportFailed'), icon: 'fail' })
  }
}

const goBack = () => router.back()
const goDiscover = () => router.push('/feed/discover')
</script>

<template>
  <div class="feed-manage-view">
    <van-nav-bar :title="$t('feeds.title')" left-arrow @click-left="goBack" fixed placeholder>
      <template #right>
        <van-icon name="add-o" size="22" @click="showAddPopup = true" />
      </template>
    </van-nav-bar>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh" :pull-distance="80" :head-height="50">
      <!-- Skeleton loading -->
      <template v-if="feedStore.feeds.length === 0 && loading">
        <div v-for="i in 4" :key="i" class="skeleton-item">
          <van-skeleton title :row="1" />
        </div>
      </template>

      <!-- Empty state -->
      <div v-else-if="feedStore.feeds.length === 0 && !loading" class="empty-state">
        <van-empty :description="$t('feeds.empty')" />
        <div class="empty-actions">
          <van-button type="primary" round @click="goDiscover">
            {{ $t('feeds.discoverTitle') }}
          </van-button>
          <van-button plain round @click="showAddPopup = true">
            {{ $t('feeds.addCustom') }}
          </van-button>
        </div>
      </div>

      <!-- Feed list -->
      <template v-else>
        <van-search
          v-if="showSearch"
          v-model="searchQuery"
          :placeholder="$t('feeds.searchFeeds')"
          shape="round"
        />

        <!-- Discover Feeds card -->
        <div
          class="discover-card"
          role="button"
          tabindex="0"
          :aria-label="$t('feeds.discoverTitle')"
          @click="goDiscover"
          @keydown.enter.prevent="goDiscover"
          @keydown.space.prevent="goDiscover"
        >
          <div class="discover-icon">✨</div>
          <div class="discover-text">
            <div class="discover-title">{{ $t('feeds.discoverTitle') }}</div>
            <div class="discover-sub">{{ $t('feeds.discoverDesc') }}</div>
          </div>
          <van-icon name="arrow" class="discover-arrow" />
        </div>

        <div class="feed-list">
          <van-swipe-cell v-for="feed in filteredFeeds" :key="feed.id">
            <van-cell center class="feed-cell" @click="$router.push({ name: 'feed', query: { source: feed.id } })">
              <template #icon>
                <img
                  :src="getFaviconUrl(feed.feed_url)"
                  class="feed-favicon"
                  @error="(e) => e.target.style.display = 'none'"
                />
              </template>
              <template #title>
                <div class="feed-title-row">
                  <span class="feed-name">{{ feed.feed_name }}</span>
                  <van-tag v-if="getStatusInfo(feed.id)" :type="getStatusInfo(feed.id).type" plain size="medium">
                    {{ getStatusInfo(feed.id).text }}
                  </van-tag>
                </div>
              </template>
              <template #label>
                <span class="feed-sync-time" v-if="getSyncText(feed.id)">{{ getSyncText(feed.id) }}</span>
              </template>
            </van-cell>
            <template #right>
              <van-button square type="danger" :text="$t('common.delete')" class="swipe-btn" @click="onDelete(feed)" />
            </template>
          </van-swipe-cell>
        </div>

        <!-- Actions section -->
        <van-cell-group inset class="action-group">
          <van-cell icon="replay" :title="$t('feeds.refreshAll')" is-link @click="onRefreshAll" />
          <van-cell icon="down" :title="$t('me.opmlImport')" is-link @click="triggerImport" />
          <van-cell icon="upgrade" :title="$t('me.opmlExport')" is-link @click="handleExport" />
        </van-cell-group>
      </template>
    </van-pull-refresh>

    <input ref="fileInput" type="file" accept=".opml,.xml" style="display:none" @change="handleFileSelect" />
    <AddFeedPopup v-if="showAddPopup" v-model:show="showAddPopup" @added="loadFeeds" />
  </div>
</template>

<style scoped>
.feed-manage-view {
  min-height: 100vh;
  background: #f7f8fa;
  padding-bottom: calc(20px + env(safe-area-inset-bottom, 0px));
}

.skeleton-item {
  padding: 12px 16px;
}

.empty-state {
  padding: 40px 16px;
  text-align: center;
}

.empty-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 40px;
  margin-top: 16px;
}

.feed-list {
  margin-bottom: 16px;
}

.feed-cell {
  padding: 12px 16px;
}

.feed-favicon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  margin-right: 12px;
  flex-shrink: 0;
}

.feed-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.feed-name {
  font-size: 15px;
  font-weight: 500;
  color: #323233;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feed-sync-time {
  font-size: 12px;
  color: #c8c9cc;
}

.swipe-btn {
  height: 100%;
}

.action-group {
  margin: 16px 16px 0;
}

:deep(.van-swipe-cell) {
  margin-bottom: 1px;
}

.discover-card {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 16px;
  padding: 14px 16px;
  background: var(--readaria-surface);
  border: 1px solid var(--readaria-accent-soft);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
}

.discover-card:active {
  transform: scale(0.98);
  background: var(--readaria-stone);
}

.discover-icon {
  font-size: 24px;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--readaria-accent-soft);
  border-radius: 12px;
}

.discover-text {
  flex: 1;
  min-width: 0;
}

.discover-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--readaria-accent);
  margin-bottom: 2px;
}

.discover-sub {
  font-size: 12px;
  color: var(--readaria-muted);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow-wrap: anywhere;
}

.discover-arrow {
  color: var(--readaria-accent);
  font-size: 16px;
}
</style>
