# Jasmine 项目 Makefile
# 提供快捷命令用于测试、开发和部署

# 虚拟环境路径
VENV = venv
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
PIP = $(VENV)/bin/pip

.PHONY: help test-quick test-local test-e2e test-full test-env-up test-env-down test-watch test-cov clean venv

# 默认目标：显示帮助信息
help:
	@echo "📋 Jasmine 项目快捷命令"
	@echo ""
	@echo "🧪 测试命令："
	@echo "  make test-quick      - 快速测试（纯 Mock，< 30 秒）"
	@echo "  make test-local      - 本地测试（单元测试，< 30 秒）"
	@echo "  make test-e2e        - E2E 测试（需要 API 服务器）"
	@echo "  make test-full       - 完整测试（包括外部服务，CI 环境）"
	@echo "  make test-watch      - 监听模式（代码变更时自动测试）"
	@echo "  make test-cov        - 测试覆盖率报告"
	@echo ""
	@echo "🐳 测试环境管理："
	@echo "  make test-env-up     - 启动测试环境（PostgreSQL + Redis）"
	@echo "  make test-env-down   - 停止测试环境并清理数据"
	@echo ""
	@echo "🧹 清理命令："
	@echo "  make clean           - 清理测试缓存和临时文件"
	@echo ""
	@echo "💡 提示："
	@echo "  - 日常开发使用 test-quick 或 test-watch"
	@echo "  - 提交前使用 test-local 完整验证"
	@echo "  - CI 环境自动运行 test-full"

# 创建虚拟环境
venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo "🔧 创建虚拟环境..."; \
		python3 -m venv $(VENV); \
		$(PIP) install --upgrade pip; \
		$(PIP) install -r requirements.test.txt; \
		echo "✅ 虚拟环境创建完成"; \
	else \
		echo "✅ 虚拟环境已存在"; \
	fi

# 快速测试（纯 Mock，无需 Docker）
test-quick: venv
	@echo "🧪 运行快速测试（Mock 模式）..."
	@echo "📝 只运行单元测试，不依赖外部服务"
	$(PYTEST) -m unit -v --tb=short
	@echo "✅ 快速测试完成"

# 本地测试（需要 Docker）
test-local: venv test-env-up
	@echo "🧪 运行本地测试（Docker 模式）..."
	@echo "📝 只运行单元测试（不需要 API 服务器）"
	@sleep 3  # 等待服务就绪
	$(PYTEST) -m unit -v --tb=short
	@echo "✅ 本地测试完成"

# E2E 测试（需要 API 服务器）
test-e2e: venv test-env-up
	@echo "🧪 运行 E2E 测试..."
	@echo "⚠️  需要手动启动 API 服务器"
	@echo "💡 在另一个终端运行: uvicorn backend.api.main:app --reload"
	@echo ""
	@read -p "API 服务器已启动？按 Enter 继续..." dummy
	$(PYTEST) -m e2e -v --tb=short
	@echo "✅ E2E 测试完成"

# 完整测试（包括外部服务，仅 CI 环境）
test-full:
	@echo "⚠️  完整测试需要在 CI 环境运行"
	@echo "💡 提交代码后，GitHub Actions 会自动运行完整测试"
	@echo ""
	@echo "如需本地运行完整测试，请确保以下服务已启动："
	@echo "  - PostgreSQL (5432)"
	@echo "  - Redis (6379)"
	@echo "  - RSSHub (1200)"
	@echo ""
	@echo "然后运行: pytest -v"

# 监听模式（代码变更时自动测试）
test-watch: venv
	@echo "👀 监听模式（保存时自动测试）..."
	@echo "💡 按 Ctrl+C 退出"
	@command -v $(VENV)/bin/pytest-watch >/dev/null 2>&1 || { \
		echo "❌ pytest-watch 未安装"; \
		echo "💡 运行: $(PIP) install pytest-watch"; \
		exit 1; \
	}
	$(VENV)/bin/pytest-watch --clear --runner "$(PYTEST)" -- -m unit

# 测试覆盖率报告
test-cov: venv
	@echo "📊 生成测试覆盖率报告..."
	$(PYTEST) -m "unit or integration" --cov=backend --cov-report=html --cov-report=term
	@echo "✅ 覆盖率报告已生成: htmlcov/index.html"
	@echo "💡 运行 open htmlcov/index.html 查看详细报告"

# 启动测试环境
test-env-up:
	@echo "🚀 启动测试环境..."
	docker compose -f docker-compose.test.yml up -d
	@echo "⏳ 等待服务就绪..."
	@sleep 5
	@echo "✅ 测试环境已就绪"
	@echo ""
	@echo "📝 服务信息："
	@echo "  PostgreSQL: localhost:5433 (用户: test, 密码: test123, 数据库: jasmine_test)"
	@echo "  Redis:      localhost:6380"

# 停止测试环境
test-env-down:
	@echo "🛑 停止测试环境..."
	docker compose -f docker-compose.test.yml down -v
	@echo "✅ 测试环境已清理"

# 清理测试缓存和临时文件
clean:
	@echo "🧹 清理测试缓存和临时文件..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ 清理完成"

# 初始化测试数据库（用于本地测试）
test-db-init: test-env-up
	@echo "🗄️  初始化测试数据库..."
	@sleep 3
	POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_USER=test POSTGRES_PASSWORD=test123 POSTGRES_DB=jasmine_test \
		python manage.py db init --production
	@echo "✅ 测试数据库初始化完成"
