# Readaria 测试指南

> **版本**: v3.0（开源自托管版）  
> **更新日期**: 2026-11-04

本文以仓库当前的 [`Makefile`](../Makefile)、[`pytest.ini`](../pytest.ini) 和 [`tests/conftest.py`](../tests/conftest.py) 为准。

## 快速开始

```bash
cp .env.example .env
make test-quick
```

`make test-quick` 会在首次运行时创建 `venv/` 并安装 `requirements.test.txt`，然后执行：

```bash
pytest -m unit -v --tb=short
```

单元测试使用 Mock，不需要真实 OpenAI、TTS、RSSHub、PostgreSQL 或 Redis 服务。`tests/conftest.py` 为测试提供 dummy 配置；`.env.example` 中的占位值不能用于真实第三方 API。首次安装依赖的时间不计入“快速测试”的耗时目标。

## Makefile 命令

| 命令 | 实际行为 | 外部依赖 |
|---|---|---|
| `make help` | 显示命令摘要 | 无 |
| `make test-quick` | 创建测试虚拟环境并运行 `unit` 测试 | Python 3；首次运行需要安装依赖 |
| `make test-local` | 启动测试 PostgreSQL/Redis，然后仍只运行 `unit` 测试 | Docker Compose v2 |
| `make test-watch` | 文件变化时重复运行 `unit` 测试 | `pytest-watch` |
| `make test-cov` | 运行 `unit or integration` 并生成覆盖率报告 | 集成用例所需服务 |
| `make test-e2e` | 交互式确认 API 已启动后运行 pytest 的 `e2e` 标记 | 手动启动的 API、测试环境 |
| `make test-env-up` | 启动 `docker-compose.test.yml` 中的 PostgreSQL 和 Redis | Docker Compose v2 |
| `make test-env-down` | 停止测试环境并删除测试数据卷 | Docker Compose v2 |
| `make test-db-init` | 启动测试环境并初始化测试数据库 | Docker Compose v2 |
| `make clean` | 清理 Python/pytest 缓存与覆盖率临时文件 | 无 |

`make test-full` 当前只打印 CI/手动运行提示，不会自己执行完整测试，不应把它当作本地验证命令。

## 直接使用 pytest

```bash
source venv/bin/activate

# 单元测试
pytest -m unit -v

# 集成测试（先启动相应服务）
pytest -m integration -v

# 指定文件或测试
pytest tests/api/test_auth.py -v
pytest tests/backend/nlp/test_openai_client_params.py -v

# 排除需要第三方服务的测试
pytest -m 'not external' -v

# 失败排查
pytest --lf -v
pytest --pdb -x
```

常用 marker 定义在 `pytest.ini`：

- 类型：`unit`、`integration`、`e2e`
- 场景：`api`、`functional`、`smoke`
- 外部依赖/速度：`external`、`slow`
- 模块：`auth`、`rss`、`tts`、`database`

新增测试至少应添加合适的类型 marker，否则 `make test-quick` 不会选中它。

## Docker 测试环境

`docker-compose.test.yml` 使用独立端口，避免与默认开发服务冲突：

| 服务 | 地址 | 测试凭据 |
|---|---|---|
| PostgreSQL | `localhost:5433` | 用户 `test`，密码 `test123`，数据库 `jasmine_test` |
| Redis | `localhost:6380` | 无密码 |

PostgreSQL 数据位于 `tmpfs`，Redis 禁用持久化；该环境仅用于测试。`make test-env-down` 会删除测试数据卷，不要在其中存放需要保留的数据。

```bash
make test-env-up
make test-db-init
# 运行所需测试
make test-env-down
```

如果测试容器端口被占用，先确认占用进程，再调整本地环境；不要盲目删除其他项目的容器或数据卷。

## 前端测试

### 构建与 Node 单元测试

```bash
cd frontend
npm ci
npm run build
node --test tests/unit/*.test.mjs
```

### Playwright E2E

```bash
cd frontend
npm ci
npx playwright install
npm run test:e2e
```

本地配置会自动启动或复用 `http://localhost:5173` 的 Vite 服务。需要真实后端的场景还应先初始化测试数据库、启动 `http://localhost:8000` 的 API，并创建测试用户。前端测试可能 Mock 网络请求，因此并非所有用例都要求真实第三方服务。

其他常用命令：

```bash
npm run test:e2e:headed
npm run test:e2e:ui
npx playwright test --project=chromium
npx playwright test tests/e2e/smoke.spec.ts
npm run test:e2e:report
```

详细配置见 [`frontend/playwright.config.ts`](../frontend/playwright.config.ts) 和 [`frontend/tests/README.md`](../frontend/tests/README.md)。注意：Makefile 的 `test-e2e` 运行的是 **pytest e2e marker**，与这里的 **Playwright** 命令是两套入口。

## 本地 API / E2E 测试账号

需要使用真实 API 的测试可在临时数据库中注册 `test-user`：

```bash
curl -fsS -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"test-user","email":"test-user@example.com","password":"test1234","full_name":"Test User"}'
```

`tests/conftest.py` 中部分旧 fixture 的默认密码可能与上述账号不同；运行相关用例前，用环境变量显式统一：

```bash
export TEST_BASE_URL=http://localhost:8000
export TEST_USERNAME=test-user
export TEST_PASSWORD=test1234
```

只使用临时测试账号和临时数据库，不要在测试脚本中写入真实个人账号或生产凭据。

## Mock 原则

应 Mock 网络与第三方服务，例如 OpenAI-compatible LLM、云端 TTS、RSSHub 和可选的 wechat2rss，以保证单元测试稳定且不产生费用。数据库集成测试应使用独立测试实例，不要连接个人或生产数据库。

当前自托管版没有付费订阅、Pro/Free 额度或邀请码测试流程。用量统计与预算相关代码的测试不应被理解为功能门控测试。

## CI

GitHub Actions 定义位于 [`.github/workflows/`](../.github/workflows/)。运行哪组测试、安装哪些依赖、服务如何初始化，均以各 workflow 的当前步骤为准。CI 不能替代本地验证；修改 workflow 后应检查其实际执行结果，而不是只确认 YAML 已提交。

## 提交前检查

后端小改动：

```bash
make test-quick
```

涉及数据库、集成行为或共享调用链时，再运行相关的 integration/API 测试。前端改动至少执行构建和相关 Node/Playwright 测试。跨栈改动还应检查所有 API 调用点、并行 composable/service、错误处理和数据库字段。

## 部署后回归

在自托管 Compose 项目目录检查：

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 api | grep 'ERROR' || true
curl --fail http://localhost:8000/docs >/dev/null
```

按变更范围验证 RSS 添加/刷新、文章阅读、收藏、搜索、TTS 和播客。测试云端功能时使用你自己的测试配置，并注意第三方 API 费用。日志和 issue 中不要粘贴真实 token、Cookie、密钥或私人 feed URL。

## 相关文件

- [`Makefile`](../Makefile)
- [`requirements.test.txt`](../requirements.test.txt)
- [`pytest.ini`](../pytest.ini)
- [`tests/conftest.py`](../tests/conftest.py)
- [`docker-compose.test.yml`](../docker-compose.test.yml)
- [`frontend/package.json`](../frontend/package.json)
- [`docs/self-hosting.md`](self-hosting.md)
