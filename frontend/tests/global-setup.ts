import { request, type FullConfig } from '@playwright/test';

/**
 * Authenticate once per Playwright run. Functional specs inject this session;
 * auth.spec.ts owns the interactive login/registration coverage.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use?.baseURL || config.use?.baseURL || 'http://localhost:5173';
  const context = await request.newContext({ baseURL });

  try {
    const response = await context.post('/api/auth/login', {
      data: { username: 'test-user', password: 'test1234' },
    });
    if (!response.ok()) {
      throw new Error(`E2E global login failed (${response.status()}): ${await response.text()}`);
    }
    process.env.E2E_AUTH_SESSION = JSON.stringify(await response.json());
  } finally {
    await context.dispose();
  }
}
