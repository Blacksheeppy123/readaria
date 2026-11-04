# 中文 Onboarding Starter Pack 混入英文源与英文播客

## 问题描述

使用中文 onboarding 时，Quick Start 后出现了三类不一致：

1. 中文 start pack 混入英文 feed / 英文文章
2. 中文体验播客实际返回英文播客
3. 混入英文文章的 summary 也保持英文

### 用户操作步骤
1. 使用新账号完成 onboarding
2. 在语言选择页选择中文
3. 在路径选择页点击 Quick Start
4. 进入 Feed 查看 starter pack 和首个播客 CTA

### 实际表现 vs 预期表现
- **实际**：Feed 中残留英文 starter pack 内容，首个播客 CTA 指向英文体验播客，英文文章 summary 也是英文
- **预期**：中文 onboarding 只保留中文 starter pack，并返回中文体验播客与中文 summary

## 原因定位

### 根本原因

这次问题不是单点故障，而是三处实现分叉叠加：

1. **starter pack 定义分叉**
   - 后端 `/api/v1/onboarding/starter-pack`、前端 fallback 列表、体验用户初始化脚本使用了不同的中文 feed 集合
   - 体验用户脚本仍保留老钱日日谈、馆长、diygod 等旧列表，和当前产品想要的中文 starter pack 不一致

2. **Quick Start 不会清理历史 starter pack**
   - 现有流程只会继续 `addFeed`
   - 若同一账号今天先体验过英文 onboarding，再回到中文 Quick Start，英文 starter pack 会继续保留

3. **experience podcast 幂等只按“今天是否已有 onboarding_cache”判断**
   - `/api/v1/onboarding/experience-podcast` 以前只要发现当日已有 `source='onboarding_cache'`，就直接返回
   - 没有校验该缓存的脚本语言是否与当前 onboarding 语言一致
   - 结果就是同账号先拿过英文 onboarding cache 后，再走中文 onboarding，也会复用上午的英文播客

4. **体验播客离线生成脚本漏传 language**
   - `scripts/generate_experience_podcasts.py` 调用 `generate_daily_podcast()` 时没有传 `language=lang`
   - 这会让体验账号播客生成依赖默认值，而不是显式跟随 `onboarding-experience-zh/en`

### 具体流程问题

1. 中文用户点击 Quick Start
2. 前端先取 starter pack，再并行 `addFeed`
3. 旧实现不会移除历史 starter pack，导致英文源/旧中文源残留
4. 前端调用 `/api/v1/onboarding/experience-podcast?language=zh`
5. 后端若发现当天已有 `onboarding_cache`，会直接复用，不区分语言
6. 如果那条缓存来自英文 onboarding，就会把英文体验播客返回给中文流程
7. Feed 中英文文章继续读取英文 summary，于是和问题 1 一起暴露

### 相关代码位置
- `backend/config/onboarding_starter_pack.py`
- `backend/storage/database.py`
- `backend/api/main.py`
- `frontend/src/config/recommendedFeeds.js`
- `frontend/src/api/onboarding.js`
- `frontend/src/views/OnboardingPathView.vue`
- `scripts/init_onboarding_experience_users.py`
- `scripts/init_experience_users_standalone.py`
- `scripts/generate_experience_podcasts.py`

## 修复方案

1. 建立单一事实来源：后端新增共享 starter pack 配置，统一中文 starter pack 为：
   - 牧之野
   - 金渐成
   - 路透财经早报
   - 程苓峰
2. Quick Start 前先调用后端 reset 接口，停用历史 starter pack feed，避免英文源和旧中文源残留
3. `experience-podcast` 幂等检查增加语言判断，只复用与当前 onboarding 语言匹配的 cache
4. 修复体验播客生成脚本，显式传入 `language`
5. 重新同步体验用户 starter pack，停用旧 starter pack feed

## 修复状态

- [x] 问题定位
- [x] 文档记录
- [x] 代码修复
- [ ] 测试验证

## 修复记录

**修复文件**:
- `backend/config/onboarding_starter_pack.py`
- `backend/storage/database.py`
- `backend/api/main.py`
- `frontend/src/config/recommendedFeeds.js`
- `frontend/src/api/onboarding.js`
- `frontend/src/views/OnboardingPathView.vue`
- `scripts/init_onboarding_experience_users.py`
- `scripts/init_experience_users_standalone.py`
- `scripts/generate_experience_podcasts.py`
- `frontend/tests/e2e/onboarding-regressions.spec.ts`

**修复时间**: 2026-04-30

**修改内容**:
- 统一中文 starter pack 到 4 个指定 feed
- Quick Start 前新增 starter pack reset，停用历史 starter pack feed
- `onboarding_cache` 复用时增加语言判断，避免中文入口拿到英文体验播客
- 体验播客生成脚本显式传递语言参数
- 新增一条 e2e 回归测试，覆盖 reset → localized starter pack → localized experience podcast 请求顺序

## 验证建议

1. 本地：
   - `python3 -m py_compile backend/config/onboarding_starter_pack.py scripts/init_onboarding_experience_users.py scripts/init_experience_users_standalone.py scripts/generate_experience_podcasts.py`
2. 线上同步体验账号 starter pack：
   - `source venv/bin/activate`
   - `python scripts/init_onboarding_experience_users.py`
3. 线上重生成体验播客：
   - `source venv/bin/activate`
   - `python scripts/generate_experience_podcasts.py`
4. 手动验证：
   - 新账号中文 onboarding 后，Feed 顶部只出现 4 个中文 starter pack 源
   - 首个播客 CTA 返回中文标题/中文脚本
   - 不再看到英文文章与英文 summary 混入

## 相关提交

- 待提交
