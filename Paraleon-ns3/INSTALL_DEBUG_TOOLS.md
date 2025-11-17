# 调试工具安装指南

## 必需工具：GDB

GDB (GNU Debugger) 是调试 C/C++ 程序的必需工具。

### 安装 GDB

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install gdb
```

#### 验证安装
```bash
gdb --version
# 应该显示类似: GNU gdb (Ubuntu 9.2-0ubuntu1~20.04.1) 9.2
```

#### 检查安装位置
```bash
which gdb
# 通常显示: /usr/bin/gdb
```

### 如果 GDB 不在标准路径

如果 GDB 安装在其他位置，需要更新 `.vscode/launch.json`：

1. 找到 GDB 的实际路径：
   ```bash
   find /usr -name gdb 2>/dev/null
   ```

2. 编辑 `.vscode/launch.json`，更新 `miDebuggerPath`：
   ```json
   "miDebuggerPath": "/实际路径/gdb"
   ```

---

## 可选工具

### 1. Valgrind (内存检查)

用于检测内存泄漏和错误：

```bash
sudo apt-get install valgrind
```

使用示例：
```bash
valgrind --leak-check=full ./build/scratch/third mix/config.txt
```

### 2. GDB 增强工具

#### GDB Dashboard (可视化界面)
```bash
# 安装
wget -P ~ https://raw.githubusercontent.com/cyrus-and/gdb-dashboard/master/.gdbinit

# 使用
gdb ./build/scratch/third
```

#### GDB TUI (文本用户界面)
GDB 自带，启动时使用：
```bash
gdb -tui ./build/scratch/third
```

---

## 验证环境

运行检查脚本：
```bash
./check_debug_env.sh
```

如果所有检查通过，就可以开始调试了！

---

## 故障排除

### 问题：GDB 无法附加到进程

在某些 Linux 发行版上，需要调整 ptrace 设置：

```bash
# 临时设置（当前会话）
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# 永久设置（需要编辑 /etc/sysctl.conf）
# 添加: kernel.yama.ptrace_scope = 0
```

### 问题：WSL 中的 GDB

在 WSL (Windows Subsystem for Linux) 中，GDB 应该可以正常工作。如果遇到问题：

1. 确保使用 WSL2（不是 WSL1）
2. 更新 WSL：
   ```bash
   wsl --update
   ```
3. 如果仍有问题，尝试使用 Windows 版本的 GDB（通过 MinGW）

---

## 下一步

安装完 GDB 后：
1. 运行 `./check_debug_env.sh` 验证环境
2. 查看 `QUICK_DEBUG_START.md` 快速开始
3. 查看 `DEBUG_GUIDE.md` 了解详细调试方法

