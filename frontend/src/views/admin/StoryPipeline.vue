<template>
  <div class="pl">
    <div class="pl-steps">
      <template v-for="(st, i) in stages" :key="st.key">
        <div class="pl-step" :data-state="stateOf(st)">
          <span class="pl-dot"></span>
          <span class="pl-label">{{ st.label }}</span>
          <span v-if="tokenBadge(st)" class="pl-tokens">{{ tokenBadge(st) }}</span>
        </div>
        <span v-if="i < stages.length - 1" class="pl-link" :data-done="stateOf(st) === 'done'"></span>
      </template>
    </div>

    <div class="pl-panels">
      <details v-for="p in panels" :key="p.key" class="pl-panel">
        <summary>{{ p.title }}</summary>
        <div class="pl-body">
          <template v-if="p.key === 'scout'">
            <div v-for="(c, i) in p.data.candidates" :key="i" class="pl-item">
              <strong>{{ i + 1 }}. {{ c.topic }}</strong><span class="pl-score">{{ c.score }}</span>
              <p>证据：{{ c.evidence }}</p>
              <p>理由：{{ c.reasoning }}</p>
              <p class="pl-muted">种子：{{ (c.seed_refs || []).join(', ') || '无' }}</p>
            </div>
          </template>
          <template v-else-if="p.key === 'research'">
            <p class="pl-item">{{ p.data.background }}</p>
            <div v-if="p.data.timeline?.length" class="pl-item">
              <strong>时间线</strong>
              <p v-for="(t, i) in asList(p.data.timeline)" :key="i">{{ t }}</p>
            </div>
            <div v-if="p.data.key_facts?.length" class="pl-item"><strong>关键事实</strong>
              <ul><li v-for="(f, i) in p.data.key_facts" :key="i">{{ f }}</li></ul>
            </div>
            <div v-if="p.data.sources?.length" class="pl-item">
              <strong>调研来源</strong>
              <p v-for="(s, i) in p.data.sources" :key="i" class="pl-muted">{{ s.ref }}<template v-if="s.url"> · {{ s.url }}</template></p>
            </div>
            <div v-if="p.data.third_party_takes?.length" class="pl-item">
              <strong>第三方观点</strong>
              <div v-for="(t, i) in p.data.third_party_takes" :key="i" class="pl-take">
                <span class="pl-attr">{{ t.attribution }}</span>：{{ t.claim }}
                <span class="pl-muted">（{{ t.stance }}）</span>
              </div>
            </div>
          </template>
          <template v-else-if="p.key === 'claims'">
            <div v-for="(c, i) in p.data.claims" :key="i" class="pl-item">
              <span class="pl-conf" :data-conf="c.confidence">{{ c.confidence }}</span> {{ c.text }}
            </div>
            <div v-if="p.data.dropped?.length" class="pl-item pl-muted">
              已丢弃（无法核实）：{{ p.data.dropped.length }} 条
            </div>
          </template>
          <template v-else-if="p.key === 'analysis'">
            <p class="pl-item"><strong>为什么重要：</strong>{{ p.data.why_it_matters }}</p>
            <p class="pl-item"><strong>背景：</strong>{{ p.data.context }}</p>
            <div v-if="p.data.pro_con?.length" class="pl-item">
              <strong>正反观点</strong>
              <div v-for="(v, i) in p.data.pro_con" :key="i" class="pl-take">
                <span class="pl-conf" :data-conf="v.stance">{{ v.stance }}</span>
                <span class="pl-attr">{{ v.attribution }}</span>：{{ v.claim }}
              </div>
            </div>
            <p v-if="p.data.outlook" class="pl-item"><strong>后续关注：</strong>{{ p.data.outlook }}</p>
          </template>
          <template v-else-if="p.key === 'critic'">
            <div v-for="(r, i) in p.data" :key="i" class="pl-item">
              <span class="pl-conf" :data-conf="r.passed ? 'verified' : 'disputed'">
                第 {{ i + 1 }} 轮 {{ r.passed ? '通过' : '打回' }}</span>
              <ul v-if="r.issues?.length"><li v-for="(iss, j) in r.issues" :key="j">{{ iss }}</li></ul>
              <p v-if="r.revision_instructions" class="pl-muted">{{ r.revision_instructions }}</p>
            </div>
          </template>
          <template v-else-if="p.key === 'drafts'">
            <details v-for="(d, i) in p.data" :key="i" class="pl-item">
              <summary>被替换草稿 {{ i + 1 }}：{{ d.title }}</summary>
              <pre class="pl-pre">{{ d.article_text }}</pre>
            </details>
          </template>
          <template v-else-if="p.key === 'sources'">
            <details v-for="(s, i) in p.data" :key="i" class="pl-item">
              <summary>
                <span class="pl-conf" :data-conf="s.role">{{ s.role }}</span>
                {{ s.title || s.ref }}
              </summary>
              <p class="pl-muted">
                <a v-if="s.url" :href="s.url" target="_blank" rel="noopener">{{ s.url }}</a>
                <template v-else>{{ s.ref }}</template>
              </p>
              <p v-if="s.excerpt">{{ s.excerpt }}</p>
              <p v-else class="pl-muted">（无摘录——外部 URL 请到原文查看）</p>
            </details>
          </template>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  story: { type: Object, required: true },
})

// 阶段定义：key 与 status 值 / artifacts key 对齐
const stages = [
  { key: 'scout', label: '选题', doneFrom: 'proposed' },
  { key: 'researcher', label: '调研', doneFrom: 'verifying' },
  { key: 'verifier', label: '核查', doneFrom: 'analyzing' },
  { key: 'analyst', label: '分析', doneFrom: 'writing' },
  { key: 'writer', label: '撰稿', doneFrom: 'reviewing' },
  { key: 'critic', label: '审稿', doneFrom: 'draft' },
  { key: 'assembly', label: '装配', doneFrom: 'draft' },
]

// 状态在 pipeline 中的序位；failed:<stage> 单独处理
const ORDER = ['scouting', 'proposed', 'approved', 'researching', 'verifying',
  'analyzing', 'writing', 'reviewing', 'draft', 'published']

const status = computed(() => props.story?.status || '')
const failedStage = computed(() =>
  status.value.startsWith('failed:') ? status.value.slice(7) : '')
// failed:<stage> 时序位取「该阶段运行时的 status」——否则 ORDER.indexOf 得 -1，
// 失败点之前的已完成阶段会全部错误显示为 pending（assembly 无独立运行态，取 draft）
const FAILED_ORDER_IDX = { scout: 0, researcher: 3, verifier: 4, analyst: 5, writer: 6, critic: 7, assembly: 8 }
const orderIdx = computed(() => {
  if (failedStage.value) return Object.hasOwn(FAILED_ORDER_IDX, failedStage.value) ? FAILED_ORDER_IDX[failedStage.value] : -1
  // rejected 是终态但 scout 必然完成过（能 reject 说明到过 proposed）——按 proposed 序位渲染
  if (status.value === 'rejected') return ORDER.indexOf('proposed')
  return ORDER.indexOf(status.value)
})

function stateOf(st) {
  if (failedStage.value === st.key) return 'failed'
  if (orderIdx.value === -1) return 'pending'
  if (orderIdx.value >= ORDER.indexOf(st.doneFrom)) return 'done'
  // 当前进行中的阶段：status 名与阶段运行时 status 对齐
  if (ORDER[orderIdx.value] === activeStatusOf(st)) return 'active'
  return 'pending'
}

// 阶段运行时对应的 status 值（scout→scouting, researcher→researching, ...）
const ACTIVE_STATUS = { scout: 'scouting', researcher: 'researching', verifier: 'verifying',
  analyst: 'analyzing', writer: 'writing', critic: 'reviewing', assembly: null }

function activeStatusOf(st) {
  return ACTIVE_STATUS[st.key]
}

function tokenBadge(st) {
  const usage = props.story?.usage || {}
  if (st.key === 'scout' && usage.scout) return fmt(usage.scout)
  if (st.key === 'assembly' && usage.writing_phase) return '写作合计 ' + fmt(usage.writing_phase)
  return ''
}

function fmt(u) {
  const total = (u.input_tokens || 0) + (u.output_tokens || 0)
  return total >= 1000 ? `${(total / 1000).toFixed(1)}k tok` : `${total} tok`
}

const PANEL_DEFS = [
  { key: 'scout', title: '选题候选', artifact: 'scout' },
  { key: 'research', title: '调研笔记', artifact: 'research' },
  { key: 'claims', title: '核查声称', artifact: 'claims' },
  { key: 'analysis', title: '分析框架', artifact: 'analysis' },
  { key: 'critic', title: '审稿记录', artifact: 'critic' },
  { key: 'drafts', title: '历史草稿', artifact: 'drafts' },
  { key: 'sources', title: '溯源来源', artifact: null },
]

const panels = computed(() => {
  const artifacts = props.story?.artifacts || {}
  const out = []
  for (const def of PANEL_DEFS) {
    if (def.key === 'sources') {
      const sd = props.story?.sources_detail || []
      if (sd.length) out.push({ ...def, data: sd })
    } else {
      const data = artifacts[def.artifact]
      if (data && (Array.isArray(data) ? data.length : Object.keys(data).length)) {
        out.push({ ...def, data })
      }
    }
  }
  return out
})

function asList(v) {
  return Array.isArray(v) ? v : [v]
}
</script>

<style scoped>
.pl-steps { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-bottom: 14px; }
.pl-step { display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 56px; }
.pl-dot { width: 12px; height: 12px; border-radius: 50%; background: #d1d5db; }
.pl-step[data-state="done"] .pl-dot { background: #059669; }
.pl-step[data-state="active"] .pl-dot { background: #4f46e5; animation: pl-pulse 1.2s infinite; }
.pl-step[data-state="failed"] .pl-dot { background: #dc2626; }
.pl-label { font-size: 12px; color: #6b7280; }
.pl-step[data-state="active"] .pl-label { color: #4f46e5; font-weight: 600; }
.pl-step[data-state="failed"] .pl-label { color: #dc2626; }
.pl-tokens { font-size: 10px; color: #9ca3af; }
.pl-link { flex: 1; min-width: 12px; height: 2px; background: #e5e7eb; }
.pl-link[data-done="true"] { background: #059669; }
.pl-panels { display: flex; flex-direction: column; gap: 8px; }
.pl-panel { border: 1px solid #e5e7eb; border-radius: 8px; }
.pl-panel summary { padding: 8px 12px; cursor: pointer; font-weight: 600; font-size: 13px; }
.pl-body { padding: 4px 12px 12px; font-size: 13px; }
.pl-item { margin: 6px 0; }
.pl-score { margin-left: 8px; color: #4f46e5; font-size: 12px; }
.pl-take { margin: 4px 0; }
.pl-attr { color: #059669; font-size: 12px; }
.pl-conf { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 11px; background: #eef2ff; color: #4f46e5; margin-right: 6px; }
.pl-conf[data-conf="verified"], .pl-conf[data-conf="pro"] { background: #ecfdf5; color: #059669; }
.pl-conf[data-conf="disputed"], .pl-conf[data-conf="con"] { background: #fef2f2; color: #dc2626; }
.pl-conf[data-conf="single-source"] { background: #fffbeb; color: #d97706; }
.pl-muted { color: #9ca3af; }
.pl-pre { white-space: pre-wrap; background: #f9fafb; padding: 10px; border-radius: 6px; max-height: 320px; overflow: auto; font-size: 12px; }
@keyframes pl-pulse { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) {
  .pl-step[data-state="active"] .pl-dot { animation: none; }
}
@media (prefers-color-scheme: dark) {
  .pl-label { color: #9ca3af; }
  .pl-link { background: #374151; }
  .pl-panel { border-color: #374151; }
  .pl-pre { background: #111827; }
}
</style>
