# 快速调试开始指南

## 🚀 5分钟快速开始

### 步骤 0: 安装 GDB（如果还没有）

```bash
# 检查 GDB 是否已安装
gdb --version

# 如果没有安装，运行：
sudo apt-get update
sudo apt-get install gdb

# 验证安装
which gdb
# 应该显示: /usr/bin/gdb
```

**详细安装说明**: 查看 `INSTALL_DEBUG_TOOLS.md`

### 步骤 1: 检查环境

```bash
# 运行环境检查脚本
./check_debug_env.sh
```

### 步骤 2: 确保 Debug 编译

```bash
cd /home/jt/paraleon/Paraleon-ns3

# 配置为 debug 模式（如果还没配置）
./waf configure --build-profile=debug

# 编译项目
./waf build
```

### 步骤 3: 在 Cursor 中开始调试

1. **打开项目**
   - 在 Cursor 中打开 `/home/jt/paraleon/Paraleon-ns3`

2. **打开主文件**
   - 打开 `scratch/third.cc`
   - 找到 `main()` 函数（第482行）

3. **设置断点**
   - 点击第482行左侧，或按 `F9`
   - 红色圆点表示断点已设置

4. **开始调试**
   - 按 `F5` 或点击左侧调试图标 ▶️
   - 选择：`Debug Paraleon NS-3 (third.cc)`
   - 程序会在断点处停止

5. **调试控制**
   - `F10` - 单步跳过（Step Over）
   - `F11` - 单步进入（Step Into）
   - `F5` - 继续执行（Continue）
   - `Shift+F5` - 停止调试

---

## 📍 推荐的第一个断点位置

### 1. main() 函数入口
```cpp
// scratch/third.cc 第482行
int main(int argc, char *argv[])
```
**为什么**: 从这里可以看到整个程序的执行流程

### 2. 配置读取后
```cpp
// scratch/third.cc 第492行附近
ReadConfigFile()  // 内联函数
```
**为什么**: 可以检查配置是否正确加载

### 3. 节点创建
```cpp
// scratch/third.cc 第857行
for (uint32_t i = 0; i < node_num; i++){
```
**为什么**: 观察网络拓扑的构建过程

---

## 🎯 调试关键函数

### 路由计算
```cpp
// scratch/third.cc 第376行
CalculateRoutes(n)
```
**设置断点**: 观察路由表如何计算

### RDMA初始化
```cpp
// scratch/third.cc 第1020行
rdma->Init()
```
**设置断点**: 观察RDMA驱动如何初始化

### 流启动
```cpp
// scratch/third.cc 第136行
ScheduleFlowInputs()
```
**设置断点**: 观察流如何被调度和启动

---

## 💡 调试技巧

### 查看变量值
- **悬停**: 鼠标放在变量上
- **监视**: 在 WATCH 面板添加变量名
- **局部变量**: VARIABLES 面板自动显示

### 条件断点
1. 右键点击断点
2. 选择 "Edit Breakpoint"
3. 输入条件，例如：`i == 5` 或 `cc_mode == 3`

### 调试控制台
在调试控制台可以执行 GDB 命令：
```gdb
print variable_name
print array[0]@10
set variable i = 10
```

---

## ⚠️ 常见问题快速解决

### 问题1: 断点不生效
```bash
# 重新编译
./waf clean
./waf build
```

### 问题2: 找不到源文件
- 检查 `.vscode/launch.json` 中的 `cwd` 设置
- 确保是：`"cwd": "${workspaceFolder}"`

### 问题3: 变量显示 `<optimized out>`
```bash
# 确保使用 debug 模式
./waf configure --build-profile=debug
./waf build
```

---

## 📚 更多信息

详细调试指南请查看：`DEBUG_GUIDE.md`

---

**现在就开始调试吧！** 🎉

1. 打开 `scratch/third.cc`
2. 在第482行设置断点
3. 按 `F5`
4. 开始探索！

