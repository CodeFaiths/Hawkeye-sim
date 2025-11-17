# Paraleon NS-3 调试指南

本指南详细说明如何在 Cursor/VS Code 中配置和进行单步调试。

## 目录
1. [环境准备](#环境准备)
2. [调试配置](#调试配置)
3. [调试步骤](#调试步骤)
4. [常用断点位置](#常用断点位置)
5. [调试技巧](#调试技巧)
6. [常见问题](#常见问题)

---

## 环境准备

### 1. 检查 GDB 是否安装

```bash
gdb --version
```

如果没有安装，在 Ubuntu/Debian 上：
```bash
sudo apt-get update
sudo apt-get install gdb
```

**详细安装说明**: 查看 `INSTALL_DEBUG_TOOLS.md`

**快速验证**: 运行 `./check_debug_env.sh` 检查所有必需工具

### 2. 确保项目编译为 Debug 模式

NS-3 默认使用 debug profile（已在 `wscript` 中配置），但为了确保：

```bash
cd /home/jt/paraleon/Paraleon-ns3
CC='gcc-5' CXX='g++-5' python2 ./waf configure --build-profile=debug
./waf build
```

验证可执行文件包含调试信息：
```bash
file build/scratch/third
# 应该显示: with debug_info, not stripped
```

### 3. 安装 C/C++ 扩展

在 Cursor/VS Code 中安装以下扩展：
- **C/C++** (Microsoft) - 提供 IntelliSense 和调试支持
- **C/C++ Extension Pack** (可选，包含更多工具)

---

## 调试配置

### 配置文件说明

项目已创建以下配置文件：

1. **`.vscode/launch.json`** - 调试启动配置
   - `Debug Paraleon NS-3 (third.cc)` - 标准调试配置
   - `Debug Paraleon NS-3 (with breakpoint at main)` - 在 main 函数入口停止
   - `Debug Paraleon NS-3 (Attach to Process)` - 附加到运行中的进程

2. **`.vscode/tasks.json`** - 构建任务
   - `Build Debug (waf)` - 编译项目（默认构建任务）
   - `Build Clean (waf)` - 清理构建
   - `Configure Debug Build (waf)` - 配置 debug 构建
   - `Run without Debug` - 不调试直接运行

3. **`.vscode/settings.json`** - 项目设置
   - IntelliSense 配置
   - 包含路径设置

---

## 调试步骤

### 方法一：使用 F5 快速调试

1. **打开主文件**
   - 打开 `scratch/third.cc`

2. **设置断点**
   - 在代码行号左侧点击，或按 `F9` 设置断点
   - 推荐在 `main()` 函数开始处设置断点（第482行）

3. **开始调试**
   - 按 `F5` 或点击调试面板的 "Start Debugging"
   - 选择配置：`Debug Paraleon NS-3 (third.cc)`
   - 程序会在断点处停止

4. **调试控制**
   - `F5` - Continue（继续执行）
   - `F10` - Step Over（单步跳过）
   - `F11` - Step Into（单步进入）
   - `Shift+F11` - Step Out（跳出函数）
   - `Shift+F5` - Stop（停止调试）

### 方法二：在 main 函数入口自动停止

1. 选择调试配置：`Debug Paraleon NS-3 (with breakpoint at main)`
2. 按 `F5` 开始调试
3. 程序会自动在 `main()` 函数入口停止

### 方法三：附加到运行中的进程

1. 先运行程序：
   ```bash
   ./waf --run 'scratch/third mix/config.txt'
   ```
2. 在另一个终端找到进程ID：
   ```bash
   ps aux | grep third
   ```
3. 在 Cursor 中选择配置：`Debug Paraleon NS-3 (Attach to Process)`
4. 按 `F5`，选择进程ID

---

## 常用断点位置

### 1. 程序入口和初始化

```cpp
// scratch/third.cc

// 主函数入口
第482行: int main(int argc, char *argv[])

// 配置读取
第492行: ReadConfigFile() 开始处

// 节点创建
第857行: 创建主机节点
第860行: 创建交换机节点

// RDMA初始化
第1007行: 创建 RdmaHw 对象
第1020行: RdmaDriver::Init()
```

### 2. 路由计算

```cpp
// scratch/third.cc

第329行: CalculateRoute() - BFS路由计算
第376行: CalculateRoutes() - 路由计算入口
第384行: SetRoutingEntries() - 设置路由表
```

### 3. 应用启动

```cpp
// scratch/third.cc

第136行: ScheduleFlowInputs() - 流调度
第130行: ReadFlowInput() - 读取流输入

// src/applications/model/rdma-client.cc
第135行: RdmaClient::StartApplication()
```

### 4. 数据包发送

```cpp
// src/point-to-point/model/rdma-hw.cc
查找: RdmaHw::SendPkt()

// src/point-to-point/model/qbb-net-device.cc
第258行: QbbNetDevice::DequeueAndTransmit()
第350行: QbbNetDevice::Receive()
```

### 5. 拥塞控制

```cpp
// src/point-to-point/model/rdma-hw.cc
查找: RdmaHw::ProcessAck()
查找: RdmaHw::UpdateNextAvail()

// 根据 CC_MODE 查找对应的拥塞控制更新函数
// CC_MODE=3 (HPCC): 查找 HPCC 相关函数
```

### 6. 交换机处理

```cpp
// src/point-to-point/model/switch-node.cc
查找: SwitchNode::SwitchReceiveFromDevice()
第122行: SwitchNode::CheckAndSendPfc()
```

---

## 调试技巧

### 1. 查看变量

- **悬停查看**: 鼠标悬停在变量上
- **监视窗口**: 在 "WATCH" 面板添加表达式
- **局部变量**: "VARIABLES" 面板自动显示当前作用域的变量
- **调用堆栈**: "CALL STACK" 面板显示函数调用链

### 2. 条件断点

1. 右键点击断点
2. 选择 "Edit Breakpoint"
3. 设置条件，例如：
   - `i == 5` - 只在 i 等于 5 时停止
   - `node_num > 10` - 只在节点数大于 10 时停止
   - `cc_mode == 3` - 只在 HPCC 模式时停止

### 4. 日志断点

1. 右键点击断点
2. 选择 "Edit Breakpoint"
3. 勾选 "Logpoint"
4. 输入日志消息，例如：`Node {i}, CC Mode: {cc_mode}`

### 5. 调试控制台

在调试控制台中可以执行 GDB 命令：

```gdb
# 打印变量
print variable_name

# 打印数组
print array[0]@10

# 打印结构体
print *ptr

# 设置变量值
set variable i = 10

# 查看内存
x/10x &variable

# 查看寄存器
info registers

# 查看线程
info threads
```

### 6. 多线程调试

NS-3 是单线程事件驱动，但如果有多个线程：

```gdb
# 切换线程
thread 2

# 查看所有线程
info threads

# 只在特定线程停止
break function_name thread 2
```

### 7. 查看调用堆栈

- 在 "CALL STACK" 面板中点击任意帧
- 可以查看该帧的局部变量
- 使用 `Shift+F5` 可以查看反汇编

### 8. 内存检查

```gdb
# 检查内存泄漏（需要 valgrind）
valgrind --leak-check=full ./build/scratch/third mix/config.txt

# 在 GDB 中检查内存
(gdb) x/100x 0x地址
```

---

## 常见问题

### 1. 断点不生效

**问题**: 设置了断点但程序没有停止

**解决方案**:
- 确保编译为 debug 模式：`./waf configure --build-profile=debug && ./waf build`
- 检查可执行文件：`file build/scratch/third` 应该显示 `with debug_info`
- 确保断点设置在可执行代码行（不是注释或空行）
- 重新编译：`./waf clean && ./waf build`

### 2. 找不到源文件

**问题**: GDB 提示找不到源文件

**解决方案**:
- 检查 `launch.json` 中的 `cwd` 设置
- 确保工作目录正确：`"cwd": "${workspaceFolder}"`
- 在 GDB 中设置源文件路径：
  ```gdb
  directory /home/jt/paraleon/Paraleon-ns3
  ```

### 3. 变量显示 `<optimized out>`

**问题**: 变量显示为 `<optimized out>`

**解决方案**:
- 确保使用 debug 模式编译（优化级别为 0）
- 检查 `wscript` 中的 profile 配置：
  ```python
  'debug': [0, 2, 3],  # 优化级别为 0
  ```
- 重新编译：`./waf clean && ./waf build`

### 4. 调试速度慢

**问题**: 调试时程序运行很慢

**解决方案**:
- 这是正常的，debug 模式会关闭优化
- 可以设置条件断点，只在需要时停止
- 使用日志断点而不是普通断点
- 减少仿真时间：在 `config.txt` 中设置较小的 `SIMULATOR_STOP_TIME`

### 5. GDB 版本问题

**问题**: GDB 版本太旧或不兼容

**解决方案**:
- 更新 GDB：`sudo apt-get update && sudo apt-get install gdb`
- 检查 GDB 版本：`gdb --version`
- 如果使用 WSL，确保 GDB 支持调试

### 6. 无法附加到进程

**问题**: 无法附加到运行中的进程

**解决方案**:
- 确保进程仍在运行：`ps aux | grep third`
- 检查进程权限
- 在 Linux 上可能需要：`echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope`

### 7. IntelliSense 不工作

**问题**: 代码补全和错误检查不工作

**解决方案**:
- 安装 C/C++ 扩展
- 重新加载窗口：`Ctrl+Shift+P` -> "Reload Window"
- 检查 `.vscode/settings.json` 中的包含路径
- 生成 `c_cpp_properties.json`（C/C++ 扩展会自动生成）

---

## 调试工作流示例

### 示例1：调试路由计算

1. 在 `scratch/third.cc` 第376行设置断点：`CalculateRoutes(n)`
2. 按 `F5` 开始调试
3. 程序停止后，按 `F11` 进入 `CalculateRoutes()`
4. 在监视窗口添加：`node_num`, `switch_num`
5. 按 `F10` 单步执行，观察路由计算过程
6. 在 `CalculateRoute()` 函数中设置断点，观察 BFS 遍历

### 示例2：调试拥塞控制

1. 在 `src/point-to-point/model/rdma-hw.cc` 中找到 `ProcessAck()` 函数
2. 设置断点
3. 添加条件：`cc_mode == 3`（只调试 HPCC）
4. 在监视窗口添加：`qp->hp.m_curRate`, `qp->hp.m_lastUpdateSeq`
5. 按 `F5` 继续，观察拥塞控制更新

### 示例3：调试数据包发送

1. 在 `qbb-net-device.cc` 第258行设置断点：`DequeueAndTransmit()`
2. 添加日志断点：`Packet size: {p->GetSize()}`
3. 在 `Receive()` 函数（第350行）设置断点
4. 观察数据包从发送到接收的完整流程

---

## 高级调试技巧

### 1. 使用 GDB 脚本

创建 `.gdbinit` 文件：

```gdb
# 自动设置常用断点
break main
break CalculateRoutes
break RdmaHw::ProcessAck

# 定义宏
define print_qp
    print $arg0->m_size
    print $arg0->m_rate
end
```

### 2. 使用 Core Dump

如果程序崩溃：

```bash
# 启用 core dump
ulimit -c unlimited

# 运行程序（如果崩溃会生成 core 文件）
./waf --run 'scratch/third mix/config.txt'

# 使用 GDB 分析
gdb ./build/scratch/third core
```

### 3. 远程调试

如果需要远程调试：

```bash
# 在远程机器上
gdbserver :1234 ./build/scratch/third mix/config.txt

# 在本地
gdb ./build/scratch/third
(gdb) target remote remote_ip:1234
```

---

## 参考资源

- [GDB 官方文档](https://sourceware.org/gdb/documentation/)
- [VS Code C++ 调试文档](https://code.visualstudio.com/docs/cpp/cpp-debug)
- [NS-3 调试指南](https://www.nsnam.org/docs/manual/html/debugging.html)

---

## 快速参考

| 操作 | 快捷键 | 说明 |
|------|--------|------|
| 开始调试 | `F5` | 启动调试会话 |
| 继续执行 | `F5` | 从断点继续 |
| 单步跳过 | `F10` | 执行当前行，不进入函数 |
| 单步进入 | `F11` | 进入函数内部 |
| 跳出函数 | `Shift+F11` | 执行到函数返回 |
| 停止调试 | `Shift+F5` | 停止调试会话 |
| 重启调试 | `Ctrl+Shift+F5` | 重新启动调试 |
| 切换断点 | `F9` | 在当前行设置/取消断点 |

---

**祝调试顺利！** 🐛🔍

