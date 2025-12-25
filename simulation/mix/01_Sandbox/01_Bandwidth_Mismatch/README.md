# Bandwidth Mismatch 场景

## 📋 场景描述

测试拥塞控制算法在**异构带宽网络**中的公平性和性能表现。

测试拥塞控制算法在**异构带宽网络**中的公平性和性能表现。

## 🔌 网络拓扑

```
主机0 (100Gbps) ─┐
                  ├─ 交换机2
主机1 (50Gbps)  ─┘
```

- **节点数**: 3 (2主机 + 1交换机)
- **链路配置**:
  - 主机0 → 交换机2: 100Gbps, 2us延迟
  - 主机1 → 交换机2: 50Gbps, 2us延迟

## 🎯 测试目标

- [ ] 验证拥塞控制算法在异构网络中的公平性
- [ ] 测试带宽分配效率
- [ ] 分析不同带宽链路的流完成时间(FCT)差异
- [ ] 确保低带宽链路不成为全局瓶颈

## 📊 关键指标

| 指标 | 说明 | 期望结果 |
|------|------|----------|
| Flow Completion Time (FCT) | 各流的完成时间 | 差异在可接受范围内 |
| Throughput per flow | 每条流的吞吐量 | 按带宽比例分配 |
| Queue length | 队列长度分布 | 稳定在合理范围 |
| Link utilization | 链路利用率 | 高效利用 |

## 🚀 运行仿真

### 1. 修改配置文件

```bash
cd mix/01_Sandbox/01_Bandwidth_Mismatch/config
# 根据需要修改 flow.txt 中的流量配置
```

### 2. 运行仿真

```bash
# 方式1: 使用脚本（推荐）
cd mix/01_Sandbox/01_Bandwidth_Mismatch
./run_simulation.sh

# 方式2: 直接运行
cd /home/rdmauser/users/jiangtao/workspace/Hawkeye-main/simulation
python2.7 ./waf --run "scratch/third mix/01_Sandbox/01_Bandwidth_Mismatch/config/config.txt"
```

**注意**: 在此服务器环境下，需要使用 `python2.7 ./waf` 而不是直接 `./waf`

### 3. 查看结果

```bash
cd mix/01_Sandbox/01_Bandwidth_Mismatch/output
cat fct.txt      # 流完成时间
cat pfc.txt      # PFC统计
cat qlen.txt     # 队列长度
cat link_util.txt # 链路利用率
```

## 📈 数据分析

### 生成可视化图表

```bash
cd mix/01_Sandbox/01_Bandwidth_Mismatch/analyze/scripts
python3 plot_link_util.py
python3 plot_pfc.py
python3 plot_qlen.py
```

### 预期结果

- ✅ 100Gbps链路的流应该获得约2倍于50Gbps链路的吞吐量
- ✅ 队列长度应该保持稳定，不会出现剧烈波动
- ✅ PFC触发次数应该很少（除非流量过载）

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
# 1 0 3 10000 3000000 0.0001  (从主机1到主机0，3MB，0.1ms开始)
```

## 📚 相关论文

- **Hawkeye**: Latency-based Congestion Control for RDMA
- **DCQCN**: Adding Congestion Control to RoCEv2

## 🐛 故障排查

### 问题1: 仿真输出为空

**解决方案**: 检查 config.txt 中的路径是否正确，确保指向本场景目录。

### 问题2: FCT差异过大

**可能原因**: 拥塞控制算法未正确配置，检查 `ENABLE_QCN` 和相关参数。

---

**创建时间**: 2025-12-25
**最后更新**: 2025-12-25
