# Incast Congestion 场景 (5:1)

## 📋 场景描述

测试拥塞控制算法对**多对一（Many-to-One）拥塞**的抑制能力，这是数据中心网络的典型问题。

## 🔌 网络拓扑

```
主机0 ─┐
主机1 ─┤
主机2 ─┤
主机3 ─┼─ 交换机6 ── [接收端]
主机4 ─┤
主机5 ─┘
```

- **节点数**: 7 (6主机 + 1交换机)
- **流量模式**: 5个发送端 → 1个接收端
- **所有链路**: 100Gbps, 2us延迟

## 🎯 测试目标

- [ ] 评估算法对 Incast 拥塞的抑制能力
- [ ] 减少 PFC（优先级流控）触发频率
- [ ] 避免流完成时间(FCT)的长尾分布
- [ ] 保持队列长度稳定

## 📊 关键指标

| 指标 | 说明 | 期望结果 |
|------|------|----------|
| PFC trigger frequency | PFC触发次数 | 显著降低 |
| Max queue length | 最大队列长度 | 稳定在合理范围 |
| FCT distribution | 流完成时间分布 | 99th百分位接近平均值 |
| Flow completion time | 平均流完成时间 | 最小化 |

## 🚀 运行仿真

### 1. 修改配置文件

```bash
cd mix/01_Sandbox/02_Incast_Congestion/config
# 根据需要修改 flow.txt 中的流量配置
```

### 2. 运行仿真

```bash
# 方式1: 使用脚本（推荐）
cd mix/01_Sandbox/02_Incast_Congestion
./run_simulation.sh

# 方式2: 直接运行
cd /home/rdmauser/users/jiangtao/workspace/Hawkeye-main/simulation
python2.7 ./waf --run "scratch/third mix/01_Sandbox/02_Incast_Congestion/config/config.txt"
```

**注意**: 在此服务器环境下，需要使用 `python2.7 ./waf` 而不是直接 `./waf`

### 3. 查看结果

```bash
cd mix/01_Sandbox/02_Incast_Congestion/output
cat fct.txt      # 流完成时间
cat pfc.txt      # PFC统计
cat qlen.txt     # 队列长度
cat link_util.txt # 链路利用率
```

## 📈 数据分析

### 生成可视化图表

```bash
cd mix/01_Sandbox/02_Incast_Congestion/analyze/scripts
python3 plot_link_util.py
python3 plot_pfc.py
python3 plot_qlen.py
```

### 预期结果

- ✅ 队列长度应该保持稳定，不会出现剧烈波动
- ✅ PFC 触发次数应该显著降低
- ✅ FCT 的 99th 百分位应该接近平均值（避免长尾）
- ✅ 链路利用率应该高效且稳定

## 🔧 配置说明

### 主要配置参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `SIMULATOR_STOP_TIME` | 0.1s | 仿真运行时间 |
| `BUFFER_SIZE` | 1000 | 交换机缓冲区大小 |
| `PACKET_PAYLOAD_SIZE` | 1000 | 数据包大小 |

### 流量配置 (flow.txt)

```
# 格式: src dst pg port size start_time
# 示例:
# 0 6 3 10000 3000000 0.0001  (从主机0到主机6，3MB，0.1ms开始)
# 1 6 3 10001 3000000 0.0001  (从主机1到主机6，3MB，0.1ms开始)
# ...
```

### Incast 典型问题

当多个发送端同时向同一个接收端发送数据时会出现：

```
时间轴：
T0: 所有5个发送端同时开始发送数据
    ↓
T1: 交换机队列迅速填满 (出现拥塞)
    ↓
T2: PFC 触发，发送端被暂停 (可能导致队头阻塞)
    ↓
T3: 接收端 ACK 超时 (性能下降)
    ↓
T4: 出现严重的性能降级 (长尾延迟)
```

## 📚 相关论文

- **Hawkeye**: Latency-based Congestion Control for RDMA
- **Proteus**: Fast, Flexible, Fair
- **TIMELY**: RTT-based Congestion Control for Datacenter Networks
- **Incast Congestion Control in Datacenter Networks**: Survey and Challenges

## 🔬 实验对比

可以通过修改 `config.txt` 中的 `CC_MODE` 参数来对比不同算法：

| CC_MODE | 算法 | 特点 |
|---------|------|------|
| 1 | DCQCN | 基于ECN的经典算法 |
| 3 | HPCC | 高精度拥塞控制，使用INT |
| 7 | TIMELY | 基于RTT的拥塞控制 |
| 8 | DCTCP | 简单的ECN算法 |
| 10 | HPCC-PINT | HPCC的优化版本 |

## 🐛 故障排查

### 问题1: 仿真输出为空

**解决方案**: 检查 config.txt 中的路径是否正确，确保指向本场景目录。

### 问题2: PFC 触发次数过多

**可能原因**:
- 缓冲区大小过小（增加 `BUFFER_SIZE`）
- 流量过载（减少流量大小或发送端数量）
- 拥塞控制算法未正确配置

### 问题3: FCT 长尾现象严重

**解决方案**:
- 调整 ECN 阈值 (`KMIN_MAP`, `KMAX_MAP`)
- 启用或调整 PFC 阈值
- 尝试不同的 CC_MODE

## 📊 性能基准

### 期望性能指标

- **PFC 触发频率**: < 100次/秒（根据流量负载）
- **最大队列长度**: < 500 KB
- **FCT (99th percentile)**: < 2× 平均 FCT
- **链路利用率**: > 80%

---

**创建时间**: 2025-12-25
**最后更新**: 2025-12-25
