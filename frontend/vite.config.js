import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  build: {
    sourcemap: true,
  },
  define: {
    'import.meta.env.VITE_GIT_SHA': JSON.stringify(process.env.GITHUB_SHA || 'dev'),
  },
  plugins: [
    vue(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['favicon.ico', 'robots.txt', 'apple-touch-icon.png'],
      manifest: {
        name: 'Readaria - Your Feeds, Narrated',
        short_name: 'Readaria',
        description: 'RSS reader with AI summaries and text-to-speech. Turn your feeds into a daily brief.',
        theme_color: '#1989fa',
        background_color: '#ffffff',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // 关键修复: 防止 navigateFallback 拦截 API 请求
        navigateFallbackDenylist: [/^\/api\//, /^\/user\//, /^\/articles\//],
        // 清理旧版本缓存，避免历史配置残留影响
        cleanupOutdatedCaches: true,
        // 关闭导航预加载，避免开发模式下的预加载错误
        navigationPreload: false,
        // 缓存策略
        runtimeCaching: [
          {
            // TTS 播放专用 - 完全绕过 SW 缓存
            // 同时覆盖 final / segment / 签名 URL 获取，避免 SW 参与跨域音频切段链路
            // 导致浏览器对同一音频资源走出不同的请求/缓存语义。
            urlPattern: ({ url }) => (
              url.origin === 'https://api.marlinworks.xyz' &&
              (
                url.pathname.startsWith('/api/v1/tts/play/') ||
                url.pathname.startsWith('/api/v1/tts/segments/') ||
                url.pathname.startsWith('/api/v1/tts/play-url/') ||
                url.pathname.startsWith('/api/v1/tts/segment-play-url/')
              )
            ),
            handler: 'NetworkOnly'
            // 注意：NetworkOnly 不支持 networkTimeoutSeconds 参数
            // 超时控制由 Nginx proxy_read_timeout 处理
          },
          {
            // 图片资源 - Cache First
            urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'images-cache',
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 60 * 60 * 24 * 30 // 30 days
              }
            }
          }
        ],
        // 导航回退到主页面（SPA 路由需要）
        navigateFallback: '/index.html'
      },
      devOptions: {
        enabled: true, // 开发模式也启用 PWA
        type: 'module',
        // 与生产保持一致：SPA 路由回退到主页面
        navigateFallback: 'index.html'
      },
      // 确保开发模式使用 generateSW 策略
      strategies: 'generateSW',
      injectRegister: 'auto'
    }),
    sentryVitePlugin({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      release: { name: process.env.GITHUB_SHA || 'dev' },
      sourcemaps: {
        assets: './dist/**',
        filesToDeleteAfterUpload: './dist/**/*.map',
      },
      disable: !process.env.SENTRY_AUTH_TOKEN,
    })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0', // 允许局域网访问
    port: 5173,
    proxy: {
      // 只代理API请求，前端路由不代理
      '^/user/.*': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '^/api/.*': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '^/articles/.*': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '^/feeds/.*': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
