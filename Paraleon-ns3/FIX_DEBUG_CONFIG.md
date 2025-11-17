# 修复调试配置问题

## 问题：按 F5 后看不到 "Debug Paraleon NS-3 (third.cc)"

### 🔧 快速解决方案

#### 步骤 1: 安装 C/C++ 扩展（必需）

1. 按 `Ctrl+Shift+X` 打开扩展面板
2. 搜索 `C/C++`（Microsoft 发布）
3. 点击 **安装** (Install)
4. 安装完成后，**重新加载窗口**：
   - 按 `Ctrl+Shift+P`
   - 输入 `Reload Window` 并回车

#### 步骤 2: 手动选择调试配置

如果按 F5 后弹出调试器选择菜单：

1. **选择 "C++ (GDB/LLDB)"**（推荐选项）
2. 这会自动创建或使用现有的 `launch.json`
3. 如果创建了新文件，可能需要手动编辑

#### 步骤 3: 验证配置

1. 按 `Ctrl+Shift+D` 打开调试面板
2. 点击顶部的下拉菜单（显示 "选择配置..."）
3. 应该能看到：
   - ✅ `Debug Paraleon NS-3 (third.cc)`
   - ✅ `Debug Paraleon NS-3 (with breakpoint at main)`
   - ✅ `Debug Paraleon NS-3 (Attach to Process)`

#### 步骤 4: 开始调试

1. 选择 `Debug Paraleon NS-3 (third.cc)`
2. 在 `scratch/third.cc` 第482行设置断点
3. 按 `F5` 开始调试

---

## 如果仍然看不到配置

### 方法 A: 通过命令面板添加配置

1. 按 `Ctrl+Shift+P` 打开命令面板
2. 输入：`Debug: Add Configuration`
3. 选择：`C++ (GDB/LLDB)`
4. 这会打开 `launch.json`，**删除自动生成的内容**，复制以下配置：

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Debug Paraleon NS-3 (third.cc)",
            "type": "cppdbg",
            "request": "launch",
            "program": "${workspaceFolder}/build/scratch/third",
            "args": ["mix/config.txt"],
            "stopAtEntry": false,
            "cwd": "${workspaceFolder}",
            "environment": [],
            "externalConsole": false,
            "MIMode": "gdb",
            "setupCommands": [
                {
                    "description": "Enable pretty-printing for gdb",
                    "text": "-enable-pretty-printing",
                    "ignoreFailures": true
                }
            ],
            "preLaunchTask": "Build Debug (waf)",
            "miDebuggerPath": "/usr/bin/gdb"
        }
    ]
}
```

5. 保存文件 (`Ctrl+S`)
6. 按 `F5`，应该能看到配置了

### 方法 B: 直接编辑 launch.json

1. 按 `Ctrl+Shift+P`，输入 `Preferences: Open Workspace Settings (JSON)`
2. 或者直接打开 `.vscode/launch.json`
3. 确保文件内容正确（参考上面的 JSON）
4. 保存并重新加载窗口

---

## 验证清单

完成以上步骤后，检查：

- [ ] C/C++ 扩展已安装（扩展面板中显示 "已安装"）
- [ ] `.vscode/launch.json` 文件存在且格式正确
- [ ] 调试面板 (`Ctrl+Shift+D`) 中能看到配置
- [ ] GDB 已安装：`gdb --version`
- [ ] 项目已编译：`./waf build`

---

## 测试调试

1. 打开 `scratch/third.cc`
2. 在第482行（`main()` 函数）点击行号左侧设置断点（红色圆点）
3. 按 `F5`
4. 选择 `Debug Paraleon NS-3 (third.cc)`
5. 程序应该在断点处停止

---

## 需要帮助？

查看详细排查指南：`TROUBLESHOOTING_DEBUG.md`

