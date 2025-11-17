# 调试环境设置 - 完整步骤

## 📋 设置清单

- [ ] 安装 GDB
- [ ] 配置 Debug 编译
- [ ] 编译项目
- [ ] 验证可执行文件
- [ ] 运行环境检查

---

## 步骤 1: 安装 GDB

```bash
sudo apt-get update
sudo apt-get install gdb
gdb --version  # 验证
```

## 步骤 2: 配置 Debug 编译

```bash
cd /home/jt/paraleon/Paraleon-ns3
./waf configure --build-profile=debug
```

## 步骤 3: 编译项目

```bash
./waf build
```

## 步骤 4: 验证

```bash
# 检查可执行文件
file build/scratch/third
# 应该显示: with debug_info, not stripped

# 运行环境检查
./check_debug_env.sh
```

## 步骤 5: 开始调试

1. 在 Cursor 中打开项目
2. 打开 `scratch/third.cc`
3. 在第482行（main函数）设置断点
4. 按 `F5` 开始调试

---

## 📚 文档索引

- **快速开始**: `QUICK_DEBUG_START.md`
- **详细指南**: `DEBUG_GUIDE.md`
- **工具安装**: `INSTALL_DEBUG_TOOLS.md`
- **环境检查**: `./check_debug_env.sh`

---

**完成以上步骤后，你就可以开始调试了！** 🎉
