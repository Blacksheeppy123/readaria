<script setup>
const valueChain = [
  {
    index: '01',
    title: 'Follow what matters',
    description: 'Save the sources you actually trust across RSS and social feeds.',
  },
  {
    index: '02',
    title: 'Listen instead of scrolling',
    description: 'Turn articles into clean audio for commute, gym, or morning walks.',
  },
  {
    index: '03',
    title: 'Get a daily recap',
    description: 'Generate a podcast version when you want the full picture fast.',
  },
]
</script>

<template>
  <div class="launch-preview">
    <section class="hero-band">
      <div class="hero-shell">
        <div class="hero-copy">
          <p class="brand-mark">Readaria</p>
          <p class="eyebrow">Launch direction preview</p>
          <h1>Turn your feed into a daily brief.</h1>
          <p class="hero-text">
            A calmer editorial direction for Readaria: stronger product memory,
            clearer audio-first value, and a smoother bridge between listening
            and reading.
          </p>

          <div class="hero-actions">
            <button class="button button--primary">Start Free</button>
            <button class="button button--ghost">See Demo</button>
          </div>

          <div class="hero-audience">
            <span>For founders</span>
            <span>For investors</span>
            <span>For operators</span>
            <span>For researchers</span>
          </div>
        </div>

        <div class="hero-visual">
          <div class="hero-stage">
            <div class="hero-panel hero-panel--main">
              <div class="panel-topbar">
                <span>Readaria</span>
                <span>Sign in</span>
              </div>
              <div class="panel-copy">
                <p class="mini-label">TODAY</p>
                <h2>12 new from trusted sources</h2>
                <p>
                  Listen while moving, queue key updates, and generate a podcast
                  when you want the full picture.
                </p>
              </div>
              <div class="panel-queue">
                <div class="queue-row">
                  <div>
                    <strong>OpenAI enterprise agents update</strong>
                    <span>Deep Tech · ready to listen</span>
                  </div>
                  <span class="round-token">▶</span>
                </div>
                <div class="queue-row">
                  <div>
                    <strong>China macro note</strong>
                    <span>Queued · 6 min</span>
                  </div>
                  <span class="round-token round-token--soft">+</span>
                </div>
              </div>
              <div class="panel-podcast">
                <span>Queue: 3 articles · 14 min</span>
                <strong>Generate today's podcast</strong>
              </div>
            </div>

            <div class="hero-panel hero-panel--listen">
              <p class="mini-label">LISTEN</p>
              <h3>Continue where you left off</h3>
              <div class="listen-wave">
                <span></span>
                <span></span>
                <span></span>
                <span></span>
                <span></span>
              </div>
              <p>03:12 / 08:40</p>
            </div>

            <div class="hero-panel hero-panel--article">
              <p class="mini-label">ARTICLE</p>
              <h3>Open article while audio keeps playing</h3>
              <p>
                Review the original text without losing your listening context.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="value-band">
      <div class="section-intro">
        <p class="eyebrow">Value chain</p>
        <h2>One product story across every screen</h2>
      </div>
      <div class="value-grid">
        <article
          v-for="item in valueChain"
          :key="item.index"
          class="value-item"
        >
          <span>{{ item.index }}</span>
          <h3>{{ item.title }}</h3>
          <p>{{ item.description }}</p>
        </article>
      </div>
    </section>

    <section class="frames-band">
      <div class="section-intro">
        <p class="eyebrow">Mobile screens</p>
        <h2>Core launch screens and their relationships</h2>
      </div>

      <div class="frame-grid">
        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen landing-screen">
            <div class="screen-nav">
              <strong>Readaria</strong>
              <span>Sign in</span>
            </div>
            <div class="screen-copy">
              <p class="eyebrow eyebrow--screen">Daily listening brief</p>
              <h3>Read less. Catch more.</h3>
              <p>
                Follow the sources you trust, listen on the go, and create a
                podcast when you want the full recap.
              </p>
            </div>
            <div class="screen-actions">
              <button class="button button--primary button--small">Start Free</button>
              <button class="button button--ghost button--small">See Demo</button>
            </div>
            <div class="soft-panel">
              <div class="soft-panel__head">
                <span>TODAY</span>
                <span>12 new</span>
              </div>
              <div class="mini-row">
                <div>
                  <strong>Founder media stack</strong>
                  <span>7 min listen</span>
                </div>
                <span class="round-token">▶</span>
              </div>
              <div class="soft-cta">Generate today's podcast</div>
            </div>
          </div>
          <p class="frame-caption">Landing</p>
        </article>

        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen login-screen">
            <div class="screen-nav">
              <span>← Back</span>
            </div>
            <div class="login-copy">
              <p class="brand-mark brand-mark--small">Readaria</p>
              <h3>Bring your feeds. We'll make them playable.</h3>
              <p>
                A quieter, more product-like entry point instead of a generic
                account screen.
              </p>
            </div>
            <div class="form-shell">
              <label>
                <span>Username</span>
                <div class="input-shell"></div>
              </label>
              <label>
                <span>Password</span>
                <div class="input-shell"></div>
              </label>
              <button class="button button--primary button--block">Log in</button>
            </div>
            <p class="helper-link">New here? Create account</p>
          </div>
          <p class="frame-caption">Login</p>
        </article>

        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen onboarding-screen">
            <div class="screen-nav">
              <strong>Welcome</strong>
              <span>Step 1/2</span>
            </div>
            <div class="screen-copy">
              <h3>Choose your language first.</h3>
              <p>
                It shapes your interface, starter feeds, and podcast language.
              </p>
            </div>
            <div class="choice-stack">
              <div class="choice-card choice-card--active">
                <strong>English</strong>
                <span>Global sources, English podcast</span>
              </div>
              <div class="choice-card">
                <strong>中文</strong>
                <span>中文内容源与中文播客</span>
              </div>
            </div>
            <div class="starter-card">
              <p class="mini-label">Recommended start</p>
              <h4>Start with curated feeds</h4>
              <p>Get to content fast, then refine your feed later.</p>
            </div>
          </div>
          <p class="frame-caption">Onboarding</p>
        </article>

        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen feed-screen">
            <div class="screen-nav">
              <strong>Feed</strong>
              <span>⌕ ⋯</span>
            </div>
            <div class="overview-card">
              <p class="mini-label">Today</p>
              <h3>12 new · 5 ready to listen</h3>
              <button class="pill-action">Generate today's podcast</button>
            </div>
            <div class="pill-row">
              <span class="pill pill--active">All</span>
              <span class="pill">Unread</span>
              <span class="pill">Playable</span>
            </div>
            <div class="source-strip">
              <span class="source source--active">All feeds</span>
              <span class="source">AI</span>
              <span class="source">Macro</span>
              <span class="source">Design</span>
            </div>
            <div class="featured-card">
              <p class="mini-label">Featured</p>
              <h3>OpenAI updates enterprise agent tooling with stronger memory boundaries</h3>
              <p class="card-copy">
                A practical breakdown of what changed and why it matters.
              </p>
              <p class="meta-line">Deep Tech · 2h ago</p>
              <div class="inline-button-row">
                <button class="chip-button chip-button--dark">Listen</button>
                <button class="chip-button chip-button--soft">Queue</button>
              </div>
            </div>
            <div class="feed-line">
              <span class="feed-accent"></span>
              <div>
                <strong>A concise note on Asia liquidity conditions</strong>
                <p>China Macro · 5h ago</p>
              </div>
              <span class="tiny-actions">▶ ＋</span>
            </div>
            <div class="feed-line">
              <span class="feed-accent"></span>
              <div>
                <strong>Why founder operators are moving back to owned media</strong>
                <p>Design Notes · 7h ago</p>
              </div>
              <span class="tiny-actions">▶ ＋</span>
            </div>
          </div>
          <p class="frame-caption">Feed</p>
        </article>

        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen listen-screen">
            <div class="screen-nav">
              <strong>Listen</strong>
              <span>⋯</span>
            </div>
            <div class="stack-panel">
              <p class="mini-label">Continue</p>
              <h3>OpenAI enterprise agents update</h3>
              <p class="meta-line">03:12 / 08:40</p>
              <button class="pill-action pill-action--solid">Resume</button>
            </div>
            <div class="stack-panel">
              <div class="stack-head">
                <p class="mini-label">Your queue</p>
                <span>3 articles · 14 min</span>
              </div>
              <ul class="queue-list">
                <li><span>1</span><strong>China macro note</strong><em>≡</em></li>
                <li><span>2</span><strong>Founder media stack</strong><em>≡</em></li>
                <li><span>3</span><strong>OpenAI memory update</strong><em>≡</em></li>
              </ul>
            </div>
            <div class="stack-panel stack-panel--accent">
              <p class="mini-label">Today's recap</p>
              <h3>Your feed, summarized in 9 min</h3>
              <div class="inline-button-row">
                <button class="chip-button chip-button--light">Play</button>
                <button class="chip-button chip-button--soft">Regenerate</button>
              </div>
            </div>
          </div>
          <p class="frame-caption">Listen</p>
        </article>

        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen player-screen">
            <div class="screen-nav">
              <strong>Now playing</strong>
              <span>⋯</span>
            </div>
            <div class="player-cover">
              <div class="player-ring"></div>
              <div class="player-wave">
                <span></span>
                <span></span>
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
            <div class="screen-copy">
              <p class="eyebrow eyebrow--screen">Deep Tech</p>
              <h3>OpenAI updates enterprise agent tooling</h3>
              <p>Listen while reviewing the original article.</p>
            </div>
            <div class="progress-row">
              <span>03:12</span>
              <div class="progress-bar"><div class="progress-bar__fill"></div></div>
              <span>08:40</span>
            </div>
            <div class="control-row">
              <button class="control-button">-15</button>
              <button class="control-button control-button--primary">Pause</button>
              <button class="control-button">+15</button>
            </div>
            <div class="player-link-row">
              <span class="player-link player-link--active">Open article</span>
              <span class="player-link">Playlist</span>
            </div>
            <p class="player-note">
              Playback stays active while you open the article and inspect the text.
            </p>
          </div>
          <p class="frame-caption">Player</p>
        </article>

        <article class="phone-frame">
          <div class="phone-notch"></div>
          <div class="screen article-screen">
            <div class="screen-nav">
              <strong>Article</strong>
              <span>☆ ⤴</span>
            </div>
            <div class="screen-copy">
              <h3>OpenAI updates its enterprise agent tooling with stronger memory boundaries</h3>
              <p class="meta-line">Deep Tech · 2h ago</p>
            </div>
            <div class="summary-panel">
              <span>Summary</span>
              <p>
                A practical breakdown of how enterprise tooling is moving toward
                more auditable task systems.
              </p>
            </div>
            <div class="inline-button-row">
              <button class="chip-button chip-button--dark">Listen to this article</button>
              <button class="chip-button chip-button--light">Add to queue</button>
            </div>
            <div class="article-body">
              <p>
                Enterprise buyers are becoming more sensitive to the boundary
                between memory, retrieval, and orchestration.
              </p>
              <p>
                Systems should feel helpful, but still traceable and auditable
                when work crosses team boundaries.
              </p>
            </div>
            <div class="mini-player">
              <span>▶ Playing · 03:12</span>
              <strong>Back to player</strong>
            </div>
          </div>
          <p class="frame-caption">Article Detail</p>
        </article>
      </div>
    </section>

    <section class="closing-band">
      <div class="closing-shell">
        <p class="eyebrow">Direction</p>
        <h2>Calm, editorial, and unmistakably built around listening.</h2>
        <p>
          The launch version should feel less like a generic AI tool and more
          like a private briefing app that happens to turn feeds into audio.
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
:global(body) {
  background: #ebe2d6;
  color: #172130;
}

.launch-preview {
  min-height: 100vh;
  background:
    radial-gradient(circle at 0% 10%, rgba(199, 91, 57, 0.12), transparent 24%),
    radial-gradient(circle at 100% 0%, rgba(26, 38, 57, 0.08), transparent 20%),
    linear-gradient(180deg, #f5eee3 0%, #ece2d4 46%, #e6dccd 100%);
  color: #172130;
}

.hero-band,
.value-band,
.frames-band,
.closing-band {
  padding: 32px 20px 0;
}

.hero-shell,
.value-grid,
.frame-grid,
.section-intro,
.closing-shell {
  max-width: 1280px;
  margin: 0 auto;
}

.hero-shell {
  display: grid;
  gap: 28px;
  min-height: min(920px, calc(100svh - 32px));
  align-items: center;
}

.hero-copy {
  display: grid;
  gap: 18px;
}

.brand-mark {
  font-size: 30px;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.brand-mark--small {
  font-size: 22px;
}

.eyebrow,
.mini-label,
.summary-panel span {
  font-size: 11px;
  line-height: 1;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #9a674f;
}

.eyebrow--screen {
  margin-bottom: 2px;
}

.hero-copy h1,
.hero-panel h2,
.hero-panel h3,
.section-intro h2,
.value-item h3,
.screen h3,
.closing-shell h2 {
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-weight: 600;
}

.hero-copy h1 {
  font-size: clamp(54px, 9vw, 98px);
  line-height: 0.94;
  max-width: 7.2ch;
}

.hero-text,
.closing-shell p,
.screen-copy p,
.login-copy p,
.hero-panel p,
.card-copy,
.player-note,
.article-body p {
  color: rgba(23, 33, 48, 0.76);
  line-height: 1.7;
}

.hero-text {
  max-width: 560px;
  font-size: 16px;
}

.hero-actions,
.screen-actions,
.inline-button-row,
.player-link-row,
.control-row,
.pill-row,
.source-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.button,
.chip-button,
.control-button {
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
}

.button {
  padding: 14px 22px;
}

.button--small {
  padding: 10px 16px;
  font-size: 13px;
}

.button--block {
  width: 100%;
}

.button--primary,
.chip-button--dark,
.control-button--primary {
  background: #1b293a;
  color: #f8f2e8;
  box-shadow: 0 16px 30px rgba(27, 41, 58, 0.18);
}

.button--ghost,
.chip-button--light,
.control-button {
  background: rgba(255, 252, 248, 0.74);
  border-color: rgba(23, 33, 48, 0.12);
  color: #1b293a;
}

.hero-audience {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-audience span {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 252, 248, 0.5);
  border: 1px solid rgba(23, 33, 48, 0.08);
  font-size: 12px;
  color: rgba(23, 33, 48, 0.68);
}

.hero-visual {
  display: flex;
  justify-content: center;
}

.hero-stage {
  position: relative;
  width: min(100%, 640px);
  min-height: 620px;
}

.hero-panel {
  position: absolute;
  background: rgba(255, 251, 245, 0.9);
  border: 1px solid rgba(23, 33, 48, 0.08);
  box-shadow: 0 28px 80px rgba(64, 45, 31, 0.18);
  backdrop-filter: blur(8px);
}

.hero-panel--main {
  inset: 0 24px 44px 0;
  border-radius: 34px;
  padding: 24px;
  display: grid;
  gap: 20px;
  animation: floatCard 9s ease-in-out infinite;
}

.hero-panel--listen {
  right: 0;
  top: 54px;
  width: 220px;
  border-radius: 28px;
  padding: 18px;
  display: grid;
  gap: 10px;
  animation: floatCard 7s ease-in-out infinite reverse;
}

.hero-panel--article {
  left: 28px;
  bottom: 0;
  width: 250px;
  border-radius: 24px;
  padding: 18px;
  display: grid;
  gap: 10px;
  animation: floatCard 8s ease-in-out infinite;
}

.panel-topbar,
.screen-nav,
.soft-panel__head,
.stack-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-copy {
  display: grid;
  gap: 12px;
}

.panel-copy h2 {
  font-size: 42px;
  line-height: 1.02;
  max-width: 10ch;
}

.panel-queue,
.soft-panel,
.overview-card,
.featured-card,
.stack-panel,
.summary-panel,
.form-shell,
.starter-card,
.choice-card {
  background: rgba(255, 252, 248, 0.88);
  border: 1px solid rgba(23, 33, 48, 0.08);
  box-shadow: 0 16px 34px rgba(66, 49, 33, 0.08);
}

.panel-queue,
.soft-panel,
.overview-card,
.featured-card,
.stack-panel,
.summary-panel,
.starter-card {
  border-radius: 24px;
  padding: 16px;
}

.queue-row,
.mini-row,
.feed-line,
.mini-player {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.queue-row div,
.mini-row div {
  display: grid;
  gap: 4px;
}

.queue-row span,
.mini-row span:last-child,
.meta-line,
.helper-link,
.choice-card span,
.starter-card p,
.feed-line p {
  color: rgba(23, 33, 48, 0.68);
}

.round-token {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: rgba(199, 91, 57, 0.12);
  color: #b55333;
  font-size: 13px;
}

.round-token--soft {
  background: rgba(23, 33, 48, 0.06);
  color: rgba(23, 33, 48, 0.76);
}

.panel-podcast,
.soft-cta,
.pill-action {
  min-height: 40px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
  background: rgba(199, 91, 57, 0.1);
  color: #b55333;
  font-size: 13px;
  font-weight: 600;
}

.panel-podcast {
  justify-content: space-between;
}

.pill-action--solid {
  background: #1b293a;
  color: #f8f2e8;
  width: fit-content;
}

.listen-wave,
.player-wave {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 58px;
}

.listen-wave span,
.player-wave span {
  width: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #c75b39, rgba(199, 91, 57, 0.3));
  animation: pulseBar 1.8s ease-in-out infinite;
}

.listen-wave span:nth-child(1),
.player-wave span:nth-child(1) {
  height: 16px;
}

.listen-wave span:nth-child(2),
.player-wave span:nth-child(2) {
  height: 30px;
  animation-delay: 0.12s;
}

.listen-wave span:nth-child(3),
.player-wave span:nth-child(3) {
  height: 22px;
  animation-delay: 0.24s;
}

.listen-wave span:nth-child(4),
.player-wave span:nth-child(4) {
  height: 34px;
  animation-delay: 0.36s;
}

.listen-wave span:nth-child(5),
.player-wave span:nth-child(5) {
  height: 18px;
  animation-delay: 0.48s;
}

.value-band,
.frames-band,
.closing-band {
  padding-bottom: 72px;
}

.section-intro {
  display: grid;
  gap: 10px;
  margin-bottom: 26px;
}

.section-intro h2,
.closing-shell h2 {
  font-size: clamp(32px, 5vw, 56px);
  line-height: 1.02;
  max-width: 12ch;
}

.value-grid {
  display: grid;
  gap: 18px;
}

.value-item {
  border-top: 1px solid rgba(23, 33, 48, 0.12);
  padding: 22px 0 0;
  display: grid;
  gap: 8px;
}

.value-item span {
  color: #9a674f;
  font-size: 12px;
  letter-spacing: 0.14em;
}

.frame-grid {
  display: grid;
  gap: 20px;
}

.phone-frame {
  background: rgba(24, 33, 45, 0.96);
  border-radius: 38px;
  padding: 14px 14px 22px;
  box-shadow: 0 32px 70px rgba(25, 35, 48, 0.24);
}

.phone-notch {
  width: 106px;
  height: 20px;
  margin: 0 auto 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.screen {
  min-height: 650px;
  border-radius: 28px;
  padding: 18px;
  background:
    linear-gradient(180deg, #fbf7f0 0%, #f4ede3 100%);
  display: grid;
  align-content: start;
  gap: 14px;
}

.screen-copy,
.login-copy {
  display: grid;
  gap: 8px;
}

.screen h3 {
  font-size: 32px;
  line-height: 1.04;
}

.login-screen .screen-nav,
.landing-screen .screen-nav,
.onboarding-screen .screen-nav,
.feed-screen .screen-nav,
.listen-screen .screen-nav,
.player-screen .screen-nav,
.article-screen .screen-nav {
  font-size: 14px;
}

.form-shell {
  border-radius: 24px;
  padding: 16px;
  display: grid;
  gap: 14px;
}

.form-shell label {
  display: grid;
  gap: 8px;
  font-size: 13px;
  color: rgba(23, 33, 48, 0.78);
}

.input-shell {
  height: 48px;
  border-radius: 14px;
  background: rgba(23, 33, 48, 0.05);
  border: 1px solid rgba(23, 33, 48, 0.08);
}

.choice-stack {
  display: grid;
  gap: 12px;
}

.choice-card {
  border-radius: 22px;
  padding: 16px;
  display: grid;
  gap: 6px;
}

.choice-card--active {
  border-color: rgba(199, 91, 57, 0.34);
  background: linear-gradient(180deg, rgba(199, 91, 57, 0.12), rgba(255, 252, 248, 0.92));
}

.starter-card {
  display: grid;
  gap: 8px;
}

.pill,
.source,
.player-link,
.chip-button {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
}

.pill,
.source,
.player-link,
.chip-button--light,
.chip-button--soft {
  background: rgba(23, 33, 48, 0.06);
  color: rgba(23, 33, 48, 0.72);
}

.pill--active,
.source--active,
.player-link--active,
.chip-button--soft {
  background: rgba(199, 91, 57, 0.12);
  color: #b55333;
}

.featured-card {
  display: grid;
  gap: 10px;
}

.card-copy {
  font-size: 14px;
}

.feed-line {
  align-items: flex-start;
  padding: 14px 0;
  border-bottom: 1px solid rgba(23, 33, 48, 0.08);
}

.feed-line div {
  flex: 1;
  display: grid;
  gap: 4px;
}

.feed-accent {
  width: 4px;
  min-height: 38px;
  border-radius: 999px;
  background: linear-gradient(180deg, #c75b39, #d89a74);
}

.tiny-actions {
  white-space: nowrap;
  color: #b55333;
  font-size: 13px;
}

.stack-panel {
  display: grid;
  gap: 10px;
}

.stack-panel--accent {
  background: linear-gradient(180deg, rgba(199, 91, 57, 0.12), rgba(255, 252, 248, 0.92));
}

.queue-list {
  list-style: none;
  display: grid;
  gap: 10px;
}

.queue-list li {
  display: grid;
  grid-template-columns: 18px 1fr 14px;
  gap: 10px;
  align-items: center;
}

.queue-list span {
  color: #9a674f;
}

.player-cover {
  height: 220px;
  border-radius: 28px;
  background: radial-gradient(circle at center, rgba(27, 41, 58, 0.12), rgba(27, 41, 58, 0.02));
  display: grid;
  place-items: center;
  position: relative;
  overflow: hidden;
}

.player-ring {
  width: 160px;
  height: 160px;
  border-radius: 50%;
  border: 14px solid rgba(27, 41, 58, 0.92);
  box-shadow: 0 0 0 16px rgba(199, 91, 57, 0.12);
}

.player-wave {
  position: absolute;
  bottom: 56px;
}

.progress-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  color: rgba(23, 33, 48, 0.68);
}

.progress-bar {
  height: 4px;
  border-radius: 999px;
  background: rgba(23, 33, 48, 0.12);
}

.progress-bar__fill {
  width: 38%;
  height: 100%;
  border-radius: inherit;
  background: #c75b39;
}

.control-button {
  padding: 10px 16px;
}

.summary-panel {
  border-left: 4px solid #c75b39;
}

.article-body {
  display: grid;
  gap: 12px;
}

.mini-player {
  margin-top: auto;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(23, 33, 48, 0.94);
  color: #f8f2e8;
  align-items: center;
}

.mini-player span {
  color: rgba(248, 242, 232, 0.72);
}

.frame-caption {
  margin-top: 14px;
  text-align: center;
  color: rgba(248, 242, 232, 0.78);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 12px;
}

.closing-shell {
  border-top: 1px solid rgba(23, 33, 48, 0.12);
  padding-top: 24px;
  display: grid;
  gap: 12px;
}

@keyframes floatCard {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@keyframes pulseBar {
  0%, 100% {
    opacity: 0.48;
    transform: scaleY(0.84);
  }
  50% {
    opacity: 1;
    transform: scaleY(1.08);
  }
}

@media (min-width: 980px) {
  .hero-shell {
    grid-template-columns: minmax(0, 0.9fr) minmax(520px, 0.95fr);
  }

  .value-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 24px;
  }

  .frame-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1360px) {
  .frame-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
