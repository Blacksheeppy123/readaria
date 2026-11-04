import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api/request'
import i18n from '@/i18n'

export const useConversationStore = defineStore('conversation', () => {
  // 状态
  const messages = ref([])
  const loading = ref(false)
  const currentPodcastId = ref(null)
  const suggestedQuestions = ref([])
  const suggestedQuestionsLoading = ref(false)

  // 发送消息
  const sendMessage = async (podcastId, message) => {
    if (!message.trim()) return

    // 添加用户消息
    messages.value.push({
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    })

    loading.value = true

    try {
      const response = await api.post(
        `/api/v1/podcasts/${podcastId}/chat`,
        { message }
      )

      // 添加助手回复（响应拦截器已经返回 response.data）
      messages.value.push({
        role: 'assistant',
        content: response.assistant_message,
        relatedArticles: response.related_articles || [],
        relatedSegments: response.related_segments || [],
        timestamp: new Date().toISOString()
      })

      return response
    } catch (error) {
      console.error('发送消息失败:', error)

      // 添加错误消息
      messages.value.push({
        role: 'assistant',
        content: i18n.global.t('conversation.errorMessage'),
        error: true,
        timestamp: new Date().toISOString()
      })

      throw error
    } finally {
      loading.value = false
    }
  }

  // 加载对话历史
  const loadConversations = async (podcastId, limit = 20) => {
    loading.value = true
    try {
      const response = await api.get(
        `/api/v1/podcasts/${podcastId}/conversations`,
        { params: { limit } }
      )

      // 转换为消息格式（响应拦截器已经返回 response.data）
      const conversations = response.conversations || []
      messages.value = conversations.map(conv => ({
        role: conv.role,
        content: conv.content,
        timestamp: conv.timestamp || new Date().toISOString()
      }))

      currentPodcastId.value = podcastId
    } catch (error) {
      console.error('加载对话历史失败:', error)
      messages.value = []
    } finally {
      loading.value = false
    }
  }

  // 获取推荐问题（基于播客脚本生成）
  const fetchSuggestedQuestions = async (podcastId) => {
    suggestedQuestionsLoading.value = true
    try {
      const response = await api.get(
        `/api/v1/podcasts/${podcastId}/suggested-questions`
      )
      suggestedQuestions.value = response.questions || []
    } catch (error) {
      console.error('获取推荐问题失败:', error)
      suggestedQuestions.value = []
    } finally {
      suggestedQuestionsLoading.value = false
    }
  }

  // 清空消息
  const clearMessages = () => {
    messages.value = []
    suggestedQuestions.value = []
    currentPodcastId.value = null
  }

  // 重试最后一条消息
  const retryLastMessage = async () => {
    if (messages.value.length < 2) return

    // 找到最后一条用户消息
    const lastUserMessage = [...messages.value]
      .reverse()
      .find(msg => msg.role === 'user')

    if (!lastUserMessage || !currentPodcastId.value) return

    // 移除最后的助手回复（如果有错误）
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage.role === 'assistant' && lastMessage.error) {
      messages.value.pop()
    }

    // 重新发送
    await sendMessage(currentPodcastId.value, lastUserMessage.content)
  }

  return {
    // 状态
    messages,
    loading,
    currentPodcastId,
    suggestedQuestions,
    suggestedQuestionsLoading,

    // 方法
    sendMessage,
    loadConversations,
    fetchSuggestedQuestions,
    clearMessages,
    retryLastMessage
  }
})
