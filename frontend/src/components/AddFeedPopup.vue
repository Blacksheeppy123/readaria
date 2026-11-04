<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { showToast } from 'vant'
import { useFeedStore } from '@/stores/feedStore'
import { testFeedUrl } from '@/api/feeds'

const { t } = useI18n()
const feedStore = useFeedStore()
const emit = defineEmits(['close', 'added'])

const show = defineModel('show', { type: Boolean, default: false })

const urlInput = ref(null)
const feedUrl = ref('')
const validating = ref(false)
const validated = ref(false)
const validationResult = ref(null)
const subscribing = ref(false)

let debounceTimer = null

const reset = () => {
  feedUrl.value = ''
  validating.value = false
  validated.value = false
  validationResult.value = null
  subscribing.value = false
}

watch(show, (val) => {
  if (!val) reset()
})

const onOpened = () => {
  urlInput.value?.focus()
}

watch(feedUrl, (val) => {
  validated.value = false
  validationResult.value = null
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!val || !val.trim()) return

  // Basic URL check
  const trimmed = val.trim()
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) return

  debounceTimer = setTimeout(() => validateUrl(trimmed), 600)
})

const validateUrl = async (url) => {
  validating.value = true
  validated.value = false
  validationResult.value = null
  try {
    const res = await testFeedUrl(url)
    const data = res.data || res
    validationResult.value = data
    validated.value = true
  } catch {
    validationResult.value = { status: 'error', message: t('feeds.testFailed') }
    validated.value = true
  } finally {
    validating.value = false
  }
}

const onSubscribe = async () => {
  if (subscribing.value || !validationResult.value) return
  const result = validationResult.value
  const url = result.optimal_url || feedUrl.value.trim()
  const name = result.feed_title || new URL(url).hostname

  subscribing.value = true
  try {
    await feedStore.createFeed({ feed_name: name, feed_url: url })
    showToast({ message: t('feeds.addSuccess'), icon: 'success' })
    show.value = false
    emit('added')
  } catch {
    showToast({ message: t('feeds.addFailed'), icon: 'fail' })
  } finally {
    subscribing.value = false
  }
}
</script>

<template>
  <van-popup
    v-model:show="show"
    position="bottom"
    round
    closeable
    :style="{ maxHeight: '60vh' }"
    @opened="onOpened"
  >
    <div class="add-feed-popup">
      <h3 class="popup-title">{{ $t('feeds.addFeed') }}</h3>

      <van-field
        ref="urlInput"
        v-model="feedUrl"
        :placeholder="$t('feeds.feedUrlPlaceholder')"
        clearable
        type="url"
        left-icon="link-o"
      />

      <!-- Validating -->
      <div v-if="validating" class="status-area">
        <van-loading size="20" />
        <span class="status-text">{{ $t('feeds.testing') }}</span>
      </div>

      <!-- Validation result -->
      <div v-else-if="validated && validationResult" class="status-area">
        <template v-if="validationResult.status === 'success'">
          <van-icon name="checked" color="#07c160" size="20" />
          <div class="result-info">
            <div class="result-title">{{ validationResult.feed_title || $t('feeds.testSuccess') }}</div>
            <div v-if="validationResult.item_count" class="result-meta">
              {{ validationResult.item_count }} {{ $t('feeds.itemCount') }}
            </div>
          </div>
        </template>
        <template v-else-if="validationResult.status === 'warning'">
          <van-icon name="warning-o" color="#ff976a" size="20" />
          <span class="status-text warning">{{ validationResult.message }}</span>
        </template>
        <template v-else>
          <van-icon name="close" color="#ee0a24" size="20" />
          <span class="status-text error">{{ validationResult.message }}</span>
        </template>
      </div>

      <van-button
        type="primary"
        block
        round
        :disabled="!validated || validationResult?.status !== 'success' || subscribing"
        :loading="subscribing"
        class="subscribe-btn"
        @click="onSubscribe"
      >
        {{ $t('feeds.subscribe') }}
      </van-button>
    </div>
  </van-popup>
</template>

<style scoped>
.add-feed-popup {
  padding: 20px 16px calc(20px + env(safe-area-inset-bottom, 0px));
}

.popup-title {
  font-size: 17px;
  font-weight: 600;
  text-align: center;
  margin: 0 0 16px;
  color: #323233;
}

.status-area {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0;
  min-height: 44px;
}

.status-text {
  font-size: 14px;
  color: #646566;
}

.status-text.warning {
  color: #ff976a;
}

.status-text.error {
  color: #ee0a24;
}

.result-info {
  flex: 1;
}

.result-title {
  font-size: 14px;
  font-weight: 500;
  color: #323233;
}

.result-meta {
  font-size: 12px;
  color: #969799;
  margin-top: 2px;
}

.subscribe-btn {
  margin-top: 12px;
}
</style>
