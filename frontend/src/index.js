/**
 * Cloudflare Workers 入口文件
 * 用于处理静态资产和 SPA 路由
 */

const SECURITY_HEADERS = {
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob:; connect-src 'self' https://api.marlinworks.xyz; font-src 'self' https: data:; media-src 'self' https: blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'geolocation=(), microphone=(), camera=(), payment=()',
  'Strict-Transport-Security': 'max-age=63072000; includeSubDomains; preload',
};

function addSecurityHeaders(response) {
  const newHeaders = new Headers(response.headers);
  Object.entries(SECURITY_HEADERS).forEach(([key, value]) => {
    newHeaders.set(key, value);
  });
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders,
  });
}

export default {
  async fetch(request, env) {
    // 获取静态资产绑定
    const asset = await env.ASSETS.fetch(request);

    // 如果是 404，返回 index.html（SPA 路由支持）
    if (asset.status === 404) {
      const indexResponse = await env.ASSETS.fetch(new Request(new URL('/index.html', request.url)));
      return addSecurityHeaders(new Response(indexResponse.body, {
        status: 200,
        headers: indexResponse.headers,
      }));
    }

    return addSecurityHeaders(asset);
  }
};
