# Sandbox 测试场景

本目录包含多个测试场景，用于评估 Hawkeye 拥塞控制算法在不同网络环境下的性能。

## 📁 目录结构

```
01_Sandbox/
├── 01_Bandwidth_Mismatch/           # 场景1: 带宽不匹配测试
├── 02_Incast_Congestion/             # 场景2: Incast拥塞测试
├── config/                           # (保留，历史配置)
├── analyze/                          # (保留，历史分析)
└── output/                           # (保留，历史输出)
```

## 🔬 测试场景概览

### 场景 1: Bandwidth Mismatch (带宽不匹配)

**目录**: `01_Bandwidth_Mismatch/`

**目的**: 测试拥塞控制算法在异构带宽网络中的公平性

**拓扑**: 3节点网络 (2主机 + 1交换机)，带宽分别为 100Gbps 和 50Gbps

**关键指标**:
- 流完成时间(FCT)差异
- 吞吐量分配公平性
- 队列稳定性

**详情**: [查看 README](./01_Bandwidth_Mismatch/README.md)

---

### 场景 2: Incast Congestion (Incast拥塞)

**目录**: `02_Incast_Congestion/`

**目的**: 测试拥塞控制算法对多对一拥塞的抑制能力

**拓扑**: 7节点网络 (6主机 + 1交换机)，5:1 Incast 模式

**关键指标**:
- PFC 触发频率
- 队列长度稳定性
- FCT 长尾分布

**详情**: [查看 README](./02_Incast_Congestion/README.md)

---

## 🚀 快速开始

### 运行单个场景

```bash
# 场景1: 带宽不匹配
cd mix/01_Sandbox/01_Bandwidth_Mismatch
./run_simulation.sh

# 场景2: Incast拥塞
cd mix/01_Sandbox/02_Incast_Congestion
./run_simulation.sh

# 或直接使用 waf
cd /home/rdmauser/users/jiangtao/workspace/Hawkeye-main/simulation
python2.7 ./waf --run "scratch/third mix/01_Sandbox/01_Bandwidth_Mismatch/config/config.txt"
python2.7 ./waf --run "scratch/third mix/01_Sandbox/02_Incast_Congestion/config/config.txt"
```

**注意**: 在此服务器环境下，需要使用 `python2.7 ./waf` 而不是直接 `./waf`

### 批量运行所有场景

```bash
cd /home/rdmauser/users/jiangtao/workspace/Hawkeye-main/simulation

# 运行场景1
python2.7 ./waf --run "scratch/third mix/01_Sandbox/01_Bandwidth_Mismatch/config/config.txt"

# 运行场景2
python2.7 ./waf --run "scratch/third mix/01_Sandbox/02_Incast_Congestion/config/config.txt"
```

## 📊 结果分析

每个场景都有独立的分析脚本：

```bash
# 分析场景1
cd mix/01_Sandbox/01_Bandwidth_Mismatch/analyze/scripts
python3 plot_link_util.py
python3 plot_pfc.py
python3 plot_qlen.py

# 分析场景2
cd mix/01_Sandbox/02_Incast_Congestion/analyze/scripts
python3 plot_link_util.py
python3 plot_pfc.py
python3 plot_qlen.py
```

## 🔧 自定义配置

### 修改流量模式

编辑对应场景的 `config/flow.txt`:

```
# 格式: src dst pg port size start_time
# 示例:
0 1 3 10000 3000000 0.0001
1 0 3 10001 3000000 0.0001
```

### 修改拥塞控制算法

编辑对应场景的 `config/config.txt`:

```
# 可用的 CC_MODE:
# 1  = DCQCN
# 3  = HPCC
# 7  = TIMELY
# 8  = DCTCP
# 10 = HPCC-PINT

CC_MODE 3
```

## 📈 性能对比

可以通过运行不同 CC_MODE 来对比算法性能：

| 算法 | CC_MODE | 适用场景 |
|------|---------|----------|
| DCQCN | 1 | 通用场景 |
| HPCC | 3 | 低延迟要求 |
| TIMELY | 7 | RTT敏感场景 |
| DCTCP | 8 | 简单部署 |
| HPCC-PINT | 10 | 精确控制 |

## 📝 目录说明

### 标准场景目录结构

每个测试场景都遵循统一的目录结构：

```
场景目录/
├── config/              # 配置文件
│   ├── config.txt      # 主配置文件
│   ├── topology.txt    # 网络拓扑
│   ├── flow.txt        # 流量配置
│   └── trace.txt       # 监控节点
├── analyze/            # 分析工具
│   ├── scripts/        # Python分析脚本
│   └── figures/        # 生成的图表
├── output/             # 仿真输出
│   ├── fct.txt         # 流完成时间
│   ├── pfc.txt         # PFC统计
│   ├── qlen.txt        # 队列长度
│   └── link_util.txt   # 链路利用率
└── README.md           # 场景说明文档
```

## 🆕 添加新场景

如需添加新的测试场景：

1. **创建目录结构**:
   ```bash
   mkdir -p 03_New_Scenario/{config,analyze/scripts,analyze/figures,output}
   ```

2. **复制模板配置**:
   ```bash
   cp 01_Bandwidth_Mismatch/config/config.txt 03_New_Scenario/config/
   cp 01_Bandwidth_Mismatch/config/topology.txt 03_New_Scenario/config/
   cp 01_Bandwidth_Mismatch/config/flow.txt 03_New_Scenario/config/
   cp 01_Bandwidth_Mismatch/config/trace.txt 03_New_Scenario/config/
   cp 01_Bandwidth_Mismatch/analyze/scripts/*.py 03_New_Scenario/analyze/scripts/
   ```

3. **修改配置**:
   - 更新 `config.txt` 中的路径引用
   - 修改 `topology.txt` 定义网络拓扑
   - 修改 `flow.txt` 定义流量模式

4. **创建 README**: 参考现有场景的 README.md 格式

## 🐛 常见问题

### Q: 仿真输出路径配置错误

**A**: 检查 `config.txt` 中的所有路径是否正确指向当前场景目录

### Q: 找不到拓扑/流量文件

**A**: 确保文件名和路径与 `config.txt` 中的配置一致

### Q: 分析脚本无法找到输出文件

**A**: 检查输出文件是否生成在正确的 `output/` 目录中

## 📚 参考资料

- [Hawkeye 论文](https://arxiv.org/abs/...)
- [DCQCN 规范](https://...)
- [NS-3 仿真器文档](https://www.nsnam.org/)

---

**维护者**: Hawkeye Simulation Team
**最后更新**: 2025-12-25
