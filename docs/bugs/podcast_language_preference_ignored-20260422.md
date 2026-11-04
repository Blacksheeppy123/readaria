# Podcast Language Preference Ignored - Chinese Content Generated for English Preference

## 问题描述

test-user 账户在界面中选择了英文偏好（English），但生成的每日播客内容是中文的。

### 用户操作步骤
1. 以 test-user 身份登录
2. 进入 Profile -> Settings（MeView）
3. 选择语言为 English
4. 触发每日播客生成（或等待系统自动生成）
5. 查看生成的播客内容

### 实际表现 vs 预期表现
- **实际**: 播客脚本内容为中文（主播对话、标题、简介均为中文）
- **预期**: 播客脚本内容应为英文，与用户的语言偏好设置一致

## 原因定位

### 初步分析

**前端传参逻辑**（[`frontend/src/stores/podcastStore.js:43-48`](frontend/src/stores/podcastStore.js#L43-L48))：
```javascript
const language = i18n.global.locale.value || localStorage.getItem('locale') || 'zh'
const response = await api.post('/api/v1/podcasts/generate', {
    style: options.style || 'deep_dive',
    time_range_hours: options.time_range_hours || 24,
    max_articles: options.max_articles || 10,
    language: language === 'en' ? 'en' : 'zh'
})
```

- 播客生成时读取 `i18n.global.locale.value` 或 `localStorage.getItem('locale')`
- 只有精确等于 `'en'` 时才传 `'en'`，否则传 `'zh'`

**后端接收**（[`backend/api/main.py:2443-2448`](backend/api/main.py#L2443-L2448))：
```python
class PodcastGenerateRequest(BaseModel):
    style: str = "deep_dive"
    time_range_hours: int = 24
    max_articles: int = 10
    language: str = "en"  # 默认 "en"
```

**播客生成器**（[`backend/services/podcast_generator.py:46`](backend/services/podcast_generator.py#L46))：
```python
async def generate_daily_podcast(
    self,
    user_id: str,
    style: str = "deep_dive",
    time_range_hours: int = 24,
    max_articles: int = 10,
    language: str = "zh"  # 默认 "zh"
):
```

注意：播客生成器方法签名默认 `language="zh"`，但 API 层传入的是请求参数，所以实际以前端传入为准。

**语言影响逻辑**：
- `language='en'` → 使用英文系统提示 + 英文 prompt + 要求 GPT 输出英文脚本
- `language='zh'` → 使用中文系统提示 + 中文 prompt + 要求 GPT 输出中文脚本

### 可能的根因

1. **前端 locale 未正确同步**：用户选择 English 后，`i18n.global.locale.value` 或 `localStorage` 中的值可能未正确更新为 `'en'`，导致生成播客时仍传 `'zh'`
2. **用户偏好后端未同步**：`updateLanguage('en')` 调用失败，或用户偏好后端存储的是 `'en'`，但前端播客生成时没有从后端读取用户偏好
3. **GPT 忽略语言指令**：即使传了 `'en'`，由于文章内容是中文的，GPT 可能仍用中文生成对话（但 prompt 中明确要求用英文输出，这种情况概率较低）
4. **缓存/旧数据**：用户看到的是之前生成的中文播客，而非选择英文后新生成的播客

### 待验证

- [ ] 前端生成播客请求中的 `language` 参数实际值
- [ ] test-user 的 `preferred_language` 数据库值
- [ ] 播客生成时的 API 请求日志

## 修复方案

**方案一：前端播客生成使用用户偏好（推荐）**
- 修改 `podcastStore.js`，从 `userStore.user.preferred_language` 读取语言偏好，而非仅依赖 i18n locale
- 这样即使用户在多个设备上登录，也能使用正确的语言偏好

**方案二：后端使用用户偏好兜底（已采用）**
- 在 `generate_podcast` API 中，使用数据库中 `current_user['preferred_language']` 决定播客语言
- 前端传入的 `language` 参数不再作为播客语言依据
- 确保所有设备上播客语言与用户账户偏好一致

**方案三：确保前端 locale 同步正确**
- 检查 `MeView.vue` 中 `onLangSelect` 回调是否正确更新了 i18n 和 localStorage
- 检查 `podcastStore.js` 读取 locale 的逻辑是否可靠

## 验证结果

**部署后线上验证**（2026-04-22）：

1. **test-user 播客内容**：
   - Podcast 213（4月22日）：**英文** — 标题 "Daily Podcast (April 22) - Bitcoin Halving, US-Iran Tensions & Fed Chair Transition"
   - Podcast 212（4月21日）：**中文** — "每日播客（4月21日）- 主题关键词：美股百年走势..."
   - Podcast 211（4月20日）：**中文**

2. **数据库用户偏好**：
   - test-user `preferred_language` = **`zh`**（不是 `en`）

3. **关键发现**：
   - 4月22日的播客是英文，因为它是**修复前**生成的，当时前端仍驱动语言参数
   - 修复后，后端忽略前端传入的 `language`，改为使用数据库 `preferred_language`
   - 由于 test-user 的数据库偏好为 `zh`，**未来新生成的播客将为中文**

4. **后续建议**：
   - 如果 test-user 确实希望播客为英文，需要在 Profile → Settings 中重新选择 English，确保数据库同步为 `en`
   - 或手动将数据库中 test-user 的 `preferred_language` 更新为 `en`

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [x] 测试验证（快速单元测试通过，35/35）
- [x] 部署上线
- [x] 线上验证

## 修复记录

**修复文件**: [`backend/api/main.py`](backend/api/main.py)

**修复时间**: 2026-04-22

**修改内容**:
- 播客生成 API (`/api/v1/podcasts/generate`) 中，不再使用前端传入的 `payload.language`，改为从 `current_user['preferred_language']` 读取用户数据库中的语言偏好
- 语言值归一化：只有 `'en'` 时生成英文播客，其他情况（包括 `None`、空字符串、其他语言代码）统一使用 `'zh'`

## 相关提交

- `42e1741` fix(backend): use user's preferred_language for podcast generation
