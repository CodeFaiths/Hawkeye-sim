# 调试配置问题排查

## 问题：按 F5 后看不到 "Debug Paraleon NS-3 (third.cc)" 配置

### 解决方案 1: 安装 C/C++ 扩展（最常见）

1. **打开扩展面板**：
   - 按 `Ctrl+Shift+X` 或点击左侧扩展图标

2. **搜索并安装**：
   - 搜索 `C/C++` (Microsoft)
   - 点击 "安装" (Install)
   - 或者安装 `C/C++ Extension Pack`（包含更多工具）

3. **重新加载窗口**：
   - 按 `Ctrl+Shift+P` 打开命令面板
   - 输入 `Reload Window` 并选择

4. **再次尝试**：
   - 按 `F5`，应该能看到配置了

---

### 解决方案 2: 检查 launch.json 文件位置

确保 `.vscode/launch.json` 文件在项目根目录：

```bash
cd /home/jt/paraleon/Paraleon-ns3
ls -la .vscode/launch.json
```

如果文件不存在或位置不对，重新创建：

```bash
# 确保 .vscode 目录存在
mkdir -p .vscode

# 检查 launch.json 是否存在
cat .vscode/launch.json
```

---

### 解决方案 3: 手动选择调试配置

1. **打开调试面板**：
   - 按 `Ctrl+Shift+D` 或点击左侧调试图标

2. **点击下拉菜单**：
   - 在调试面板顶部，点击 "选择配置..." 或 "Select Configuration..."

3. **选择配置**：
   - 应该能看到 "Debug Paraleon NS-3 (third.cc)"
   - 如果看不到，选择 "添加配置..." (Add Configuration...)
   - 然后选择 "C++ (GDB/LLDB)"

---

### 解决方案 4: 验证 JSON 格式

检查 `launch.json` 格式是否正确：

```bash
cd /home/jt/paraleon/Paraleon-ns3
python3 -m json.tool .vscode/launch.json > /dev/null && echo "格式正确" || echo "格式错误"
```

如果格式错误，重新创建文件。

---

### 解决方案 5: 使用命令面板创建配置

1. **打开命令面板**：`Ctrl+Shift+P`

2. **输入**：`Debug: Add Configuration`

3. **选择**：`C++ (GDB/LLDB)`

4. **这会创建一个新的 launch.json 或添加配置到现有文件**

5. **然后手动编辑**，使用项目根目录的 `launch.json` 作为参考

---

### 解决方案 6: 检查工作区设置

确保你在正确的工作区：

1. **文件菜单** → **打开文件夹** (Open Folder)
2. 选择 `/home/jt/paraleon/Paraleon-ns3`
3. 确保这是根目录（不是子目录）

---

### 解决方案 7: 重新创建 launch.json

如果以上都不行，重新创建配置文件：

```bash
cd /home/jt/paraleon/Paraleon-ns3

# 备份现有配置（如果有）
mv .vscode/launch.json .vscode/launch.json.bak 2>/dev/null

# 重新运行环境检查脚本
./check_debug_env.sh
```

---

## 验证步骤

完成上述步骤后，验证配置：

1. **打开调试面板** (`Ctrl+Shift+D`)
2. **查看下拉菜单**，应该看到：
   - `Debug Paraleon NS-3 (third.cc)`
   - `Debug Paraleon NS-3 (with breakpoint at main)`
   - `Debug Paraleon NS-3 (Attach to Process)`

3. **如果能看到**，选择第一个配置，按 `F5` 开始调试

---

## 常见错误信息

### "无法找到调试器"
- **原因**：GDB 未安装或路径不正确
- **解决**：运行 `sudo apt-get install gdb`

### "无法找到程序"
- **原因**：可执行文件不存在或路径错误
- **解决**：运行 `./waf build` 编译项目

### "任务 'Build Debug (waf)' 未找到"
- **原因**：`tasks.json` 文件缺失或格式错误
- **解决**：检查 `.vscode/tasks.json` 文件

---

## 快速检查清单

- [ ] C/C++ 扩展已安装
- [ ] `.vscode/launch.json` 文件存在
- [ ] `.vscode/tasks.json` 文件存在
- [ ] GDB 已安装 (`gdb --version`)
- [ ] 项目已编译 (`./waf build`)
- [ ] 工作区是项目根目录
- [ ] 已重新加载窗口

---

## 仍然无法解决？

1. **查看输出面板**：
   - 按 `Ctrl+Shift+U` 打开输出面板
   - 选择 "调试控制台" (Debug Console)
   - 查看错误信息

2. **查看日志**：
   - 命令面板 (`Ctrl+Shift+P`) → `Developer: Toggle Developer Tools`
   - 查看控制台中的错误

3. **运行环境检查**：
   ```bash
   ./check_debug_env.sh
   ```

