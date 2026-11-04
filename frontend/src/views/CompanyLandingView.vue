<template>
  <div class="company-landing">
    <!-- Hero Section -->
    <section class="hero-section">
      <div class="lang-switcher">
        <button class="lang-btn" @click="toggleLocale">
          EN / 中文
        </button>
      </div>
      <div class="hero-content">
        <div class="brand-mark">
          <img src="/icon.svg" alt="Readaria" class="brand-icon" />
        </div>
        <div class="logo-section">
          <h1 class="company-name">MarlinWorks Limited</h1>
          <p class="company-location">Hong Kong</p>
        </div>
        <h2 class="tagline">{{ $t('company.hero.tagline') }}</h2>
        <p class="description">{{ $t('company.hero.description') }}</p>
        <div class="cta-buttons">
          <button
            class="cta-btn primary"
            @click="goToApp"
          >
            {{ $t('company.hero.cta') }}
          </button>
          <button
            class="cta-btn secondary"
            @click="scrollToProduct"
          >
            {{ $t('company.hero.learnMore') }}
          </button>
        </div>
      </div>
    </section>

    <!-- About Section -->
    <section class="about-section">
      <div class="section-content">
        <h2 class="section-title">{{ $t('company.about.title') }}</h2>
        <p class="section-text">{{ $t('company.about.description1') }}</p>
        <p class="section-text">{{ $t('company.about.description2') }}</p>
      </div>
    </section>

    <!-- Product Section -->
    <section class="product-section" ref="productSection">
      <div class="section-content">
        <h2 class="section-title">{{ $t('company.product.title') }}</h2>
        <p class="product-subtitle">{{ $t('company.product.subtitle') }}</p>
        <p class="section-text">{{ $t('company.product.description') }}</p>

        <!-- Product Demo / Screenshot placeholder -->
        <div class="product-demo">
          <div class="demo-placeholder">
            <p>{{ $t('company.product.demoText') }}</p>
          </div>
        </div>

        <div class="features-grid">
          <div
            v-for="(feature, index) in features"
            :key="index"
            class="feature-card"
          >
            <div class="feature-icon">{{ feature.icon }}</div>
            <h3 class="feature-title">{{ feature.title }}</h3>
            <p class="feature-desc">{{ feature.description }}</p>
          </div>
        </div>

        <!-- Value Proposition -->
        <div class="value-prop">
          <h3 class="value-title">{{ $t('company.product.valueTitle') }}</h3>
          <p class="value-text">{{ $t('company.product.valueText') }}</p>
        </div>
      </div>
    </section>

    <!-- Technology Section -->
    <section class="tech-section">
      <div class="section-content">
        <h2 class="section-title">{{ $t('company.tech.title') }}</h2>
        <div class="tech-stack">
          <div class="tech-category">
            <h4>{{ $t('company.tech.frontend') }}</h4>
            <p>Vue 3, Vite, Progressive Web App</p>
          </div>
          <div class="tech-category">
            <h4>{{ $t('company.tech.backend') }}</h4>
            <p>FastAPI, PostgreSQL, Redis</p>
          </div>
          <div class="tech-category">
            <h4>{{ $t('company.tech.ai') }}</h4>
            <p>OpenAI GPT, Azure OpenAI</p>
          </div>
          <div class="tech-category">
            <h4>{{ $t('company.tech.infrastructure') }}</h4>
            <p>Docker, Cloudflare Workers</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Contact Section -->
    <section class="contact-section">
      <div class="section-content">
        <h2 class="section-title">{{ $t('company.contact.title') }}</h2>
        <p class="contact-email">
          <a href="mailto:you@example.com">you@example.com</a>
        </p>
        <div class="footer-links">
          <router-link to="/privacy">{{ $t('company.contact.privacy') }}</router-link>
          <span class="separator">|</span>
          <router-link to="/terms">{{ $t('company.contact.terms') }}</router-link>
        </div>
        <p class="copyright">{{ $t('company.contact.copyright') }}</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale } from '@/i18n'

const { t, locale } = useI18n()
const productSection = ref(null)

const toggleLocale = () => {
  setLocale(locale.value === 'zh' ? 'en' : 'zh')
}

const features = computed(() => [
  {
    icon: '📰',
    title: t('company.product.features.aggregation.title'),
    description: t('company.product.features.aggregation.description')
  },
  {
    icon: '🤖',
    title: t('company.product.features.ai.title'),
    description: t('company.product.features.ai.description')
  },
  {
    icon: '🎧',
    title: t('company.product.features.tts.title'),
    description: t('company.product.features.tts.description')
  },
  {
    icon: '📱',
    title: t('company.product.features.pwa.title'),
    description: t('company.product.features.pwa.description')
  }
])

const goToApp = () => {
  window.location.href = 'https://readaria.com'
}

const scrollToProduct = () => {
  productSection.value?.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
.company-landing {
  min-height: 100vh;
  background: #f7f8fa;
}

/* Hero Section */
.hero-section {
  background: linear-gradient(135deg, #172130 0%, #1b293a 100%);
  color: #fbf7f0;
  padding: 80px 20px;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.hero-section::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -20%;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(199, 91, 57, 0.15) 0%, transparent 70%);
  pointer-events: none;
}

.lang-switcher {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 10;
}

.lang-btn {
  background: rgba(251, 247, 240, 0.1);
  border: 1px solid rgba(251, 247, 240, 0.3);
  color: #fbf7f0;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.lang-btn:hover {
  background: rgba(251, 247, 240, 0.2);
  border-color: rgba(251, 247, 240, 0.5);
}

.brand-mark {
  margin-bottom: 24px;
}

.brand-icon {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.hero-content {
  max-width: 800px;
  margin: 0 auto;
}

.company-name {
  font-size: 48px;
  font-weight: bold;
  margin-bottom: 8px;
  line-height: 1.2;
}

.company-location {
  font-size: 16px;
  opacity: 0.85;
  margin-bottom: 30px;
  letter-spacing: 1px;
}

.tagline {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 20px;
  opacity: 0.95;
  line-height: 1.3;
}

.description {
  font-size: 18px;
  line-height: 1.6;
  margin-bottom: 40px;
  opacity: 0.9;
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;
}

.cta-buttons {
  display: flex;
  gap: 15px;
  justify-content: center;
  flex-wrap: wrap;
}

.cta-btn {
  min-width: 180px;
  height: 50px;
  font-size: 18px;
  border-radius: 25px;
  border: none;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.3s ease;
  padding: 0 30px;
}

.cta-btn.primary {
  background: #c75b39;
  color: #fbf7f0;
}

.cta-btn.primary:hover {
  background: #b54d2e;
  transform: translateY(-2px);
}

.cta-btn.secondary {
  background: transparent;
  color: #fbf7f0;
  border: 2px solid rgba(251, 247, 240, 0.4);
}

.cta-btn.secondary:hover {
  background: rgba(251, 247, 240, 0.1);
  border-color: rgba(251, 247, 240, 0.7);
  transform: translateY(-2px);
}

/* Section Styles */
section {
  padding: 60px 20px;
}

.section-content {
  max-width: 1000px;
  margin: 0 auto;
}

.section-title {
  font-size: 36px;
  font-weight: bold;
  margin-bottom: 30px;
  text-align: center;
  color: #333;
}

.section-text {
  font-size: 18px;
  line-height: 1.8;
  color: #666;
  margin-bottom: 20px;
  text-align: center;
}

/* About Section */
.about-section {
  background: white;
}

/* Product Section */
.product-section {
  background: #f7f8fa;
}

.product-subtitle {
  font-size: 20px;
  color: #c75b39;
  text-align: center;
  margin-bottom: 20px;
  font-weight: 600;
}

.product-demo {
  margin: 40px auto;
  max-width: 900px;
}

.demo-placeholder {
  background: white;
  border-radius: 12px;
  padding: 80px 40px;
  text-align: center;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  border: 2px dashed #e0e0e0;
}

.demo-placeholder p {
  font-size: 16px;
  color: #999;
}

.value-prop {
  margin-top: 60px;
  padding: 40px;
  background: linear-gradient(135deg, rgba(199, 91, 57, 0.08) 0%, rgba(27, 41, 58, 0.08) 100%);
  border-radius: 12px;
  text-align: center;
  border: 1px solid rgba(199, 91, 57, 0.15);
}

.value-title {
  font-size: 24px;
  font-weight: bold;
  color: #333;
  margin-bottom: 15px;
}

.value-text {
  font-size: 18px;
  line-height: 1.8;
  color: #666;
  max-width: 800px;
  margin: 0 auto;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 30px;
  margin-top: 50px;
}

.feature-card {
  background: white;
  padding: 30px;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  text-align: center;
  transition: transform 0.3s ease;
}

.feature-card:hover {
  transform: translateY(-5px);
}

.feature-icon {
  font-size: 48px;
  margin-bottom: 20px;
}

.feature-title {
  font-size: 20px;
  font-weight: bold;
  margin-bottom: 15px;
  color: #333;
}

.feature-desc {
  font-size: 16px;
  line-height: 1.6;
  color: #666;
}

/* Technology Section */
.tech-section {
  background: white;
}

.tech-stack {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 30px;
  margin-top: 40px;
}

.tech-category {
  text-align: center;
  padding: 20px;
}

.tech-category h4 {
  font-size: 18px;
  font-weight: bold;
  color: #c75b39;
  margin-bottom: 10px;
}

.tech-category p {
  font-size: 16px;
  color: #666;
  line-height: 1.6;
}

/* Contact Section */
.contact-section {
  background: #f7f8fa;
  text-align: center;
}

.contact-email {
  font-size: 20px;
  margin-bottom: 30px;
}

.contact-email a {
  color: #c75b39;
  text-decoration: none;
  font-weight: 600;
}

.contact-email a:hover {
  text-decoration: underline;
}

.footer-links {
  margin-bottom: 20px;
  font-size: 16px;
}

.footer-links a {
  color: #666;
  text-decoration: none;
}

.footer-links a:hover {
  color: #c75b39;
}

.separator {
  margin: 0 15px;
  color: #ccc;
}

.copyright {
  font-size: 14px;
  color: #999;
}

/* Responsive Design */
@media (max-width: 768px) {
  .company-name {
    font-size: 36px;
  }

  .tagline {
    font-size: 20px;
  }

  .description {
    font-size: 16px;
  }

  .section-title {
    font-size: 28px;
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .tech-stack {
    grid-template-columns: 1fr;
  }
}
</style>
