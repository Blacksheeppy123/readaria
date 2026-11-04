#!/bin/bash
# 音频缓存清理测试脚本
# 用途：测试缓存清理功能（模拟运行和实际运行）
# 使用方法：bash scripts/test_cache_cleanup.sh

set -e

echo "=========================================="
echo "音频缓存清理测试脚本"
echo "=========================================="

# 检查是否在项目根目录
if [ ! -f "backend/services/cache_cleaner.py" ]; then
    echo "❌ 错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 1. 模拟运行（不实际删除文件）
echo ""
echo "[1/2] 模拟运行（Dry Run）"
echo "----------------------------------------"
python3 -m backend.services.cache_cleaner --dry-run

# 2. 询问是否执行实际清理
echo ""
echo "----------------------------------------"
read -p "是否执行实际清理？(y/N): " confirm

if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    echo ""
    echo "[2/2] 执行实际清理"
    echo "----------------------------------------"
    python3 -m backend.services.cache_cleaner
    echo ""
    echo "✅ 清理完成！"
else
    echo ""
    echo "⚠️ 已取消实际清理"
fi

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
