#!/bin/bash
# 检查调试环境是否配置正确

echo "=========================================="
echo "Paraleon NS-3 调试环境检查"
echo "=========================================="
echo ""

# 检查 GDB
echo "1. 检查 GDB..."
if command -v gdb &> /dev/null; then
    GDB_PATH=$(command -v gdb)
    echo "   ✓ GDB 已安装: $GDB_PATH"
    gdb --version | head -1
else
    echo "   ✗ GDB 未安装"
    echo "   安装命令: sudo apt-get install gdb"
    exit 1
fi
echo ""

# 检查可执行文件
echo "2. 检查可执行文件..."
if [ -f "build/scratch/third" ]; then
    echo "   ✓ 可执行文件存在: build/scratch/third"
    
    # 检查是否包含调试信息
    if file build/scratch/third | grep -q "debug_info"; then
        echo "   ✓ 包含调试信息"
    else
        echo "   ⚠ 可能不包含调试信息，建议重新编译"
        echo "   运行: ./waf clean && ./waf build"
    fi
else
    echo "   ✗ 可执行文件不存在"
    echo "   运行: ./waf build"
    exit 1
fi
echo ""

# 检查配置文件
echo "3. 检查 VS Code/Cursor 配置文件..."
if [ -d ".vscode" ]; then
    echo "   ✓ .vscode 目录存在"
    
    FILES=("launch.json" "tasks.json" "settings.json" "c_cpp_properties.json")
    for file in "${FILES[@]}"; do
        if [ -f ".vscode/$file" ]; then
            echo "   ✓ $file 存在"
        else
            echo "   ✗ $file 不存在"
        fi
    done
else
    echo "   ✗ .vscode 目录不存在"
    exit 1
fi
echo ""

# 检查配置文件内容
echo "4. 检查 launch.json 配置..."
if [ -f ".vscode/launch.json" ]; then
    if grep -q "build/scratch/third" .vscode/launch.json; then
        echo "   ✓ 程序路径配置正确"
    else
        echo "   ✗ 程序路径配置可能有问题"
    fi
    
    # 检查 GDB 路径
    GDB_IN_CONFIG=$(grep -o '"/usr/bin/gdb"' .vscode/launch.json || echo "")
    if [ -n "$GDB_IN_CONFIG" ]; then
        if [ -f "/usr/bin/gdb" ]; then
            echo "   ✓ GDB 路径配置正确"
        else
            echo "   ⚠ GDB 路径可能不正确，请检查实际路径"
        fi
    fi
fi
echo ""

# 检查构建配置
echo "5. 检查构建配置..."
if [ -f "wscript" ]; then
    if grep -q "'debug': \[0" wscript; then
        echo "   ✓ Debug profile 配置正确（优化级别为 0）"
    else
        echo "   ⚠ Debug profile 配置可能有问题"
    fi
fi
echo ""

echo "=========================================="
echo "检查完成！"
echo "=========================================="
echo ""
echo "如果所有检查都通过，你可以："
echo "1. 在 Cursor 中打开 scratch/third.cc"
echo "2. 在第482行（main函数）设置断点"
echo "3. 按 F5 开始调试"
echo ""
echo "详细指南请查看: DEBUG_GUIDE.md"
echo "快速开始请查看: QUICK_DEBUG_START.md"

