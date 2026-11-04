import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright 配置 - 生产环境
 *
 * 用于在线上环境运行 E2E 回归测试
 * baseURL: https://readaria.com
 */
export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 60_000, // 增加超时时间（生产环境可能较慢）
  expect: { timeout: 10_000 },
  fullyParallel: false, // 生产环境顺序执行，避免并发冲突
  forbidOnly: true,
  retries: 2, // 生产环境增加重试次数
  workers: 1, // 单线程执行

  reporter: [
    ['list'],
    ['html', { outputFolder: 'tests/reports/e2e-prod', open: 'never' }],
    ['json', { outputFile: 'tests/reports/e2e-prod/results.json' }],
  ],

  use: {
    // 生产环境 URL
    baseURL: process.env.PROD_BASE_URL || 'https://readaria.com',

    // 录制选项（生产环境建议开启）
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',

    // 增加导航超时
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },

  // 生产环境不启动本地服务器
  // webServer: undefined,

  projects: [
    // 只测试关键浏览器（减少测试时间）
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1280, height: 720 },
      },
    },
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
      },
    },
  ],
});
