#!/bin/bash

# Playwright E2E 测试快速入门脚本

set -e

echo "🎭 Playwright E2E 测试环境设置"
echo "================================"

# 检查是否在 frontend 目录
if [ ! -f "package.json" ]; then
  echo "❌ 请在 frontend 目录下运行此脚本"
  exit 1
fi

# 检查 Node.js
echo "✓ 检查 Node.js 版本..."
node --version

# 安装依赖
echo "📦 安装项目依赖..."
npm install

# 检查是否已安装 Playwright
if ! command -v playwright &> /dev/null; then
  echo "📦 安装 Playwright..."
  npm install -D @playwright/test
fi

# 安装浏览器
echo "🌐 安装浏览器（这可能需要几分钟）..."
npx playwright install

# 创建必要的目录
echo "📁 创建测试目录..."
mkdir -p tests/reports/e2e
mkdir -p tests/reports/screenshots

# 检查后端是否运行
echo "🔍 检查后端服务..."
if ! curl -s http://localhost:8000/docs > /dev/null; then
  echo "⚠️  警告: 后端服务未运行"
  echo "   请在另一个终端运行: python backend/api/main.py"
else
  echo "✅ 后端服务正常运行"
fi

# 检查前端是否运行
if ! curl -s http://localhost:5173 > /dev/null; then
  echo "⚠️  警告: 前端服务未运行"
  echo "   测试将自动启动前端服务"
fi

echo ""
echo "✅ 设置完成！"
echo ""
echo "可用的测试命令："
echo "  npm run test:e2e           # 运行所有测试（headless）"
echo "  npm run test:e2e:headed    # 运行测试（可见浏览器）"
echo "  npm run test:e2e:ui        # 交互式UI模式"
echo "  npm run test:e2e:report    # 查看测试报告"
echo ""
echo "示例："
echo "  npx playwright test auth.spec.ts           # 只运行认证测试"
echo "  npx playwright test --project=mobile-safari # 只在 iPhone 运行"
echo "  npx playwright test --debug                # 调试模式"
echo ""
