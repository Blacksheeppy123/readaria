import { ref, onScopeDispose } from 'vue'

const audio = new Audio()
const isPlaying = ref(false)
const currentSrc = ref('')
const error = ref(false)

// Register listeners once at module level to avoid accumulation
audio.addEventListener('ended', () => { isPlaying.value = false })
audio.addEventListener('pause', () => { isPlaying.value = false })

export function useDemoAudio() {
  const play = async (src) => {
    error.value = false
    if (currentSrc.value === src && isPlaying.value) {
      audio.pause()
      isPlaying.value = false
      return true
    }
    if (currentSrc.value !== src) {
      audio.src = src
      currentSrc.value = src
    }
    try {
      await audio.play()
      isPlaying.value = true
      return true
    } catch (err) {
      console.error('Demo audio playback failed:', err)
      error.value = true
      return false
    }
  }

  const stop = () => {
    audio.pause()
    audio.currentTime = 0
    isPlaying.value = false
    currentSrc.value = ''
    error.value = false
  }

  // Clean up audio when the consuming component is unmounted
  onScopeDispose(() => {
    stop()
  })

  return { play, stop, isPlaying, currentSrc, error }
}
