<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { showToast, showLoadingToast, closeToast } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { useOnboardingStore } from '@/stores/onboardingStore'
import { recommendedFeeds, getFaviconUrl } from '@/config/recommendedFeeds'
import AddFeedPopup from '@/components/AddFeedPopup.vue'

const { t, locale } = useI18n()
const router = useRouter()
const feedStore = useFeedStore()
const onboardingStore = useOnboardingStore()
const subscribingFeeds = ref(new Set())
const searchQuery = ref('')
const activeNames = ref(['popular'])
const showAddPopup = ref(false)

const isOnboardingManual = computed(() => onboardingStore.isManualSelected)

const normalizeUrl = (url) => url?.replace(/\/$/, '') || url
const existingUrls = computed(() => new Set(feedStore.feeds.map(f => normalizeUrl(f.feed_url))))
const isSubscribed = (url) => existingUrls.value.has(normalizeUrl(url))

const getCategoryLabel = (cat) => {
  const lang = locale.value === 'zh' ? 'zh' : 'en'
  return cat.label[lang] || cat.label.en
}

const filteredCategories = computed(() => {
  if (!searchQuery.value.trim()) return recommendedFeeds
  const q = searchQuery.value.toLowerCase()
  return recommendedFeeds
    .map(cat => ({
      ...cat,
      feeds: cat.feeds.filter(f =>
        f.name.toLowerCase().includes(q) ||
        (f.desc && f.desc.toLowerCase().includes(q))
      )
    }))
    .filter(cat => cat.feeds.length > 0)
})

const subscribeOne = async (feed) => {
  if (subscribingFeeds.value.has(feed.url) || isSubscribed(feed.url)) return
  subscribingFeeds.value.add(feed.url)
  try {
    await feedStore.createFeed({ feed_name: feed.name, feed_url: feed.url })
    showToast({ message: t('feeds.addSuccess'), icon: 'success' })
  } catch {
    showToast({ message: t('feeds.addFailed'), icon: 'fail' })
  } finally {
    subscribingFeeds.value.delete(feed.url)
  }
}

const goBack = () => router.back()
const finishOnboarding = async () => {
  const toast = showLoadingToast({ message: t('common.loading'), forbidClick: true, duration: 0 })
  try {
    await feedStore.fetchFeeds(true)
    if (feedStore.feeds.length === 0) {
      closeToast()
      showToast({ message: t('feeds.discoverDoneEmpty'), icon: 'fail' })
      return
    }
    closeToast()
    router.replace({ name: 'feed' })
  } catch {
    closeToast()
    showToast({ message: t('common.loadFailed'), icon: 'fail' })
  }
}
</script>

<template>
  <div class="feed-discover-view" :class="{ 'has-onboarding-bar': isOnboardingManual }">
    <van-nav-bar :title="$t('feeds.discoverTitle')" left-arrow @click-left="goBack" fixed placeholder>
      <template #right>
        <van-icon name="add-o" size="22" @click="showAddPopup = true" />
      </template>
    </van-nav-bar>

    <van-search
      v-model="searchQuery"
      :placeholder="$t('feeds.searchFeeds')"
      shape="round"
    />

    <div class="category-list">
      <van-collapse v-model="activeNames" accordion>
        <van-collapse-item
          v-for="cat in filteredCategories"
          :key="cat.category"
          :name="cat.category"
          :title="`${cat.icon} ${getCategoryLabel(cat)}`"
        >
          <van-cell
            v-for="feed in cat.feeds"
            :key="feed.url"
            center
            class="feed-cell"
          >
            <template #icon>
              <img
                :src="getFaviconUrl(feed.url)"
                class="feed-favicon"
                @error="(e) => e.target.style.display = 'none'"
              />
            </template>
            <template #title>
              <div class="feed-name">{{ feed.name }}</div>
              <div v-if="feed.desc" class="feed-desc">{{ feed.desc }}</div>
            </template>
            <template #right-icon>
              <van-button
                size="small"
                :type="isSubscribed(feed.url) ? 'default' : 'primary'"
                :disabled="isSubscribed(feed.url) || subscribingFeeds.has(feed.url)"
                :loading="subscribingFeeds.has(feed.url)"
                round
                @click.stop="subscribeOne(feed)"
              >
                {{ isSubscribed(feed.url) ? $t('feeds.subscribed') : '+ ' + $t('feeds.subscribe') }}
              </van-button>
            </template>
          </van-cell>
        </van-collapse-item>
      </van-collapse>
    </div>

    <div class="bottom-hint" @click="showAddPopup = true">
      <van-icon name="link-o" />
      <span>{{ $t('feeds.addCustom') }}</span>
    </div>

    <!-- Onboarding done button -->
    <div v-if="isOnboardingManual" class="onboarding-done-bar">
      <van-button type="primary" round block @click="finishOnboarding">
        {{ $t('feeds.discoverDone') }}
      </van-button>
    </div>

    <AddFeedPopup v-if="showAddPopup" v-model:show="showAddPopup" @added="feedStore.fetchFeeds(true)" />
  </div>
</template>

<style scoped>
.feed-discover-view {
  min-height: 100vh;
  background: #f7f8fa;
  padding-bottom: calc(20px + env(safe-area-inset-bottom, 0px));
}

.feed-discover-view.has-onboarding-bar {
  padding-bottom: calc(76px + env(safe-area-inset-bottom, 0px));
}

.category-list {
  padding: 0 0 12px;
}

.feed-cell {
  padding: 10px 16px;
}

.feed-favicon {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  margin-right: 10px;
  flex-shrink: 0;
}

.feed-name {
  font-size: 14px;
  font-weight: 500;
  color: #323233;
  line-height: 1.4;
}

.feed-desc {
  font-size: 12px;
  color: #969799;
  margin-top: 2px;
  line-height: 1.3;
}

.bottom-hint {
  text-align: center;
  padding: 16px;
  color: #1989fa;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

:deep(.van-collapse-item__content) {
  padding: 0;
}

:deep(.van-collapse-item__title) {
  font-weight: 600;
}

.onboarding-done-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
  background: #fff;
  border-top: 1px solid #ebedf0;
  z-index: 100;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.04);
}
</style>
