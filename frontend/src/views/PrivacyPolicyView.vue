<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <div class="legal-page">
    <van-nav-bar title="Privacy Policy" left-arrow @click-left="router.back()" fixed placeholder />

    <div class="legal-content">
      <h1>Privacy Policy</h1>
      <p class="last-updated">Last updated: May 9, 2026</p>

      <p>Readaria ("we", "us", or "our") is operated by Marlinworks Limited, a company registered in Hong Kong. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our RSS reader and podcast service.</p>

      <h2>1. Information We Collect</h2>

      <h3>Account Information</h3>
      <p>When you create an account, we collect your username, email address, and password (stored as a bcrypt hash).</p>

      <h3>Usage Data</h3>
      <p>We collect information about how you use Readaria, including:</p>
      <ul>
        <li>RSS feeds you subscribe to</li>
        <li>Articles you read, save, or listen to</li>
        <li>Podcasts you generate</li>
        <li>TTS (text-to-speech) usage</li>
      </ul>

      <h3>Technical Data</h3>
      <p>We automatically collect device type, browser type, IP address, and access timestamps for security and performance purposes.</p>

      <h2>2. How We Use Your Information</h2>
      <ul>
        <li>To provide and maintain the Readaria service</li>
        <li>To fetch and deliver RSS feed content you subscribe to</li>
        <li>To generate AI summaries and TTS audio of articles</li>
        <li>To generate AI podcasts from your selected content</li>
        <li>To improve our service and user experience</li>
        <li>To communicate with you about service updates</li>
      </ul>

      <h2>3. Third-Party Services</h2>
      <p>We use the following third-party services to provide Readaria features:</p>
      <ul>
        <li><strong>OpenAI / Azure OpenAI</strong>: For AI article summarization and TTS audio generation. Article content is sent to these APIs for processing. See <a href="https://openai.com/privacy" target="_blank" rel="noopener">OpenAI's Privacy Policy</a>.</li>
        <li><strong>Cloudflare</strong>: For content delivery and DDoS protection. See <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noopener">Cloudflare's Privacy Policy</a>.</li>
      </ul>

      <h2>4. Data Storage and Security</h2>
      <p>Your data is stored on servers located in Hong Kong. We use industry-standard security measures including encrypted connections (HTTPS), hashed passwords, and access controls to protect your data.</p>

      <h2>5. Your Rights (GDPR)</h2>
      <p>If you are located in the European Economic Area (EEA), you have the following rights:</p>
      <ul>
        <li><strong>Right of Access</strong>: Request a copy of your personal data.</li>
        <li><strong>Right to Rectification</strong>: Request correction of inaccurate data.</li>
        <li><strong>Right to Erasure</strong>: Request deletion of your account and all associated data. You can delete your account from the app settings.</li>
        <li><strong>Right to Data Portability</strong>: Export your RSS subscriptions via OPML format, or request a JSON export of your profile, subscriptions, and saved articles from the app settings.</li>
        <li><strong>Right to Object</strong>: Object to processing of your personal data.</li>
      </ul>
      <p>To exercise these rights, contact us at <strong>privacy@marlinworks.xyz</strong>.</p>

      <h2>6. Data Retention</h2>
      <p>We retain your data for as long as your account is active. When you delete your account, all associated data (subscriptions, articles, saved items, podcasts, and usage history) is permanently deleted within 30 days.</p>

      <h2>7. Cookies & Analytics</h2>
      <p>Readaria uses essential cookies and local storage to maintain your login session and preferences.</p>
      <p>We use PostHog (hosted in the EU) for product analytics to understand how our service is used and improve your experience. Analytics tracking is disabled by default and only begins after you explicitly consent to it.</p>
      <p>When you first visit, we ask for your consent before enabling analytics. If you accept, PostHog collects usage data such as page views, button clicks, and session recordings. If you are logged in, these events are linked to your account identifiers (user ID, email, and username) so we can understand feature usage across sessions. All sensitive inputs (such as passwords) are automatically masked in session recordings. You can opt out of analytics tracking at any time from the app settings.</p>

      <h2>8. Children's Privacy</h2>
      <p>Readaria is not intended for children under 16. We do not knowingly collect personal information from children.</p>

      <h2>9. Changes to This Policy</h2>
      <p>We may update this Privacy Policy from time to time. We will notify you of significant changes by posting a notice in the app.</p>

      <h2>10. Contact Us</h2>
      <p>If you have questions about this Privacy Policy, contact us at:</p>
      <p><strong>Marlinworks Limited</strong><br>Email: privacy@marlinworks.xyz</p>
    </div>
  </div>
</template>

<style scoped>
.legal-page {
  min-height: 100vh;
  background: #fff;
}

.legal-content {
  padding: 16px 20px 40px;
  color: #323233;
  line-height: 1.7;
}

.legal-content h1 {
  font-size: 22px;
  margin-bottom: 4px;
}

.legal-content h2 {
  font-size: 17px;
  margin-top: 24px;
  margin-bottom: 8px;
  color: #1a1a1a;
}

.legal-content h3 {
  font-size: 15px;
  margin-top: 16px;
  margin-bottom: 6px;
  color: #323233;
}

.legal-content p {
  font-size: 14px;
  margin-bottom: 10px;
  color: #646566;
}

.legal-content ul {
  padding-left: 20px;
  margin-bottom: 10px;
}

.legal-content li {
  font-size: 14px;
  color: #646566;
  margin-bottom: 4px;
}

.legal-content a {
  color: #1989fa;
  text-decoration: none;
}

.last-updated {
  font-size: 13px;
  color: #969799;
  margin-bottom: 16px;
}
</style>
