<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useConversationStore } from '@/stores/conversationStore'
import { trackPodcastQaUsed } from '@/utils/analytics'
import { showToast } from 'vant'

const props = defineProps({
  podcastId: {
    type: [Number, String],
    required: true
  },
  podcast: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'input'])

const { t } = useI18n()
const router = useRouter()
const conversationStore = useConversationStore()

const inputMessage = ref('')
const messagesContainer = ref(null)

// 推荐问题（优先使用后端生成的，fallback 到默认）
const defaultQuestions = computed(() => [
  t('conversation.defaultQuestion1'),
  t('conversation.defaultQuestion2'),
  t('conversation.defaultQuestion3')
])
const suggestedQuestions = computed(() => {
  if (conversationStore.suggestedQuestions.length > 0) {
    return conversationStore.suggestedQuestions
  }
  return defaultQuestions.value
})

// 点击推荐问题
const askSuggested = (question) => {
  inputMessage.value = question
  sendMessage()
}

// 格式化时间
const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 追踪播客 QA 首次使用（仅一次）
const qaTrackedPodcasts = new Set()

// 发送消息
const sendMessage = async () => {
  const message = inputMessage.value.trim()
  if (!message) return

  inputMessage.value = ''

  try {
    await conversationStore.sendMessage(props.podcastId, message)
    if (!qaTrackedPodcasts.has(props.podcastId)) {
      trackPodcastQaUsed(props.podcastId)
      qaTrackedPodcasts.add(props.podcastId)
    }
    scrollToBottom()
  } catch (error) {
    showToast(t('conversation.error'))
  }
}

// 查看文章
const viewArticle = (article) => {
  if (!article.url) {
    showToast(t('podcast.articleLinkUnavailable'))
    return
  }
  emit('close')
  router.push({
    name: 'article-detail',
    params: { id: encodeURIComponent(article.url) }
  })
}

// 滚动到底部
const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// 监听消息变化，自动滚动
watch(
  () => conversationStore.messages.length,
  () => {
    scrollToBottom()
  }
)

onMounted(() => {
  // 加载对话历史
  conversationStore.loadConversations(props.podcastId)
  // 异步加载推荐问题（不阻塞页面）
  conversationStore.fetchSuggestedQuestions(props.podcastId)
  scrollToBottom()
})
</script>

<template>
  <div class="conversation-panel">
    <!-- 消息列表 -->
    <div ref="messagesContainer" class="messages-container">
      <!-- 空状态 + 推荐问题 -->
      <div v-if="conversationStore.messages.length === 0 && !conversationStore.loading" class="empty-state">
        <van-empty image="search" :description="$t('conversation.empty')">
          <p class="empty-hint">{{ $t('conversation.emptyHint') }}</p>
        </van-empty>
        <div class="suggested-questions">
          <div class="suggested-title">{{ $t('conversation.suggestedTitle') }}</div>
          <div
            v-for="(q, i) in suggestedQuestions"
            :key="i"
            class="suggested-item"
            @click="askSuggested(q)"
          >
            {{ q }}
          </div>
        </div>
      </div>

      <!-- 消息列表 -->
      <div
        v-for="(message, index) in conversationStore.messages"
        :key="index"
        :class="['message', message.role]"
      >
        <div class="message-content">
          <div class="message-text">{{ message.content }}</div>
          <div class="message-time">{{ formatTime(message.timestamp) }}</div>

          <!-- 相关文章 -->
          <div v-if="message.relatedArticles && message.relatedArticles.length > 0" class="related-articles">
            <div class="related-title">{{ $t('conversation.relatedArticles') }}</div>
            <van-tag
              v-for="article in message.relatedArticles"
              :key="article.id"
              type="primary"
              plain
              size="medium"
              @click="viewArticle(article)"
              class="article-tag"
            >
              {{ article.title }}
            </van-tag>
          </div>

          <!-- 相关片段 -->
          <div v-if="message.relatedSegments && message.relatedSegments.length > 0" class="related-segments">
            <div class="related-title">{{ $t('conversation.relatedSegments') }}</div>
            <div
              v-for="(segment, idx) in message.relatedSegments"
              :key="idx"
              class="segment-item"
            >
              <span class="segment-speaker">{{ ['host_female', 'Catherine'].includes(segment.speaker) ? 'Catherine' : 'Alex' }}:</span>
              <span class="segment-text">{{ segment.text }}</span>
            </div>
          </div>

          <!-- 错误重试 -->
          <div v-if="message.error" class="error-actions">
            <van-button
              size="small"
              type="primary"
              plain
              @click="conversationStore.retryLastMessage()"
            >
              {{ $t('conversation.retry') }}
            </van-button>
          </div>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="conversationStore.loading" class="loading-message">
        <van-loading type="spinner" size="20">{{ $t('conversation.thinking') }}</van-loading>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="input-container">
      <van-field
        v-model="inputMessage"
        :placeholder="$t('conversation.inputPlaceholder')"
        type="textarea"
        rows="1"
        autosize
        maxlength="500"
        show-word-limit
        @keydown.enter.prevent="sendMessage"
        @focus="emit('input')"
      />
      <van-button
        type="primary"
        size="small"
        :disabled="!inputMessage.trim() || conversationStore.loading"
        @click="sendMessage"
      >
        {{ $t('conversation.send') }}
      </van-button>
    </div>
  </div>
</template>

<style scoped>
.conversation-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f5;
}

.messages-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  -webkit-overflow-scrolling: touch;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 10vh;
}

.empty-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #999;
}

.suggested-questions {
  width: 100%;
  padding: 0 8px;
  margin-top: 24px;
}

.suggested-title {
  font-size: 13px;
  color: #999;
  margin-bottom: 12px;
  text-align: center;
}

.suggested-item {
  padding: 12px 16px;
  background: white;
  border-radius: 10px;
  font-size: 14px;
  color: #333;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: background 0.15s;
}

.suggested-item:active {
  background: #f0f0f0;
}

.message {
  margin-bottom: 16px;
  display: flex;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-content {
  max-width: 80%;
  padding: 12px;
  border-radius: 8px;
  background: white;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.message.user .message-content {
  background: #1989fa;
  color: white;
}

.message-text {
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.message-time {
  margin-top: 4px;
  font-size: 11px;
  opacity: 0.6;
}

.related-articles,
.related-segments {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.message.user .related-articles,
.message.user .related-segments {
  border-top-color: rgba(255, 255, 255, 0.2);
}

.related-title {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
  opacity: 0.8;
}

.article-tag {
  margin-right: 8px;
  margin-bottom: 8px;
  cursor: pointer;
}

.segment-item {
  font-size: 12px;
  line-height: 1.6;
  margin-bottom: 8px;
  padding: 8px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 4px;
}

.message.user .segment-item {
  background: rgba(255, 255, 255, 0.1);
}

.segment-speaker {
  font-weight: 600;
  margin-right: 4px;
}

.segment-text {
  opacity: 0.9;
}

.error-actions {
  margin-top: 8px;
}

.loading-message {
  display: flex;
  justify-content: center;
  padding: 12px;
}

.input-container {
  display: flex;
  gap: 8px;
  padding: 12px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom));
  background: white;
  border-top: 1px solid #eee;
  align-items: flex-end;
  flex-shrink: 0;
}

.input-container :deep(.van-field) {
  flex: 1;
  background: #f5f5f5;
  border-radius: 8px;
  padding: 8px 12px;
}

.input-container :deep(.van-field__control) {
  font-size: 14px;
}

.input-container .van-button {
  flex-shrink: 0;
  height: 36px;
  padding: 0 16px;
}
</style>
