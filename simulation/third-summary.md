## third.cc 源码详细总结

本文档基于 `simulation/scratch/third.cc`，围绕 **数据结构、全局变量、函数逻辑** 以及 **整体调用链（附文字流程图）** 进行详细说明，方便查阅与二次开发。

---

## 1. 数据结构与核心容器

### 1.1 `Interface`

- **定义**：`struct Interface { uint32_t idx; bool up; uint64_t delay; uint64_t bw; };`
- **成员解释**：
  - **`idx`**：本节点上，用于连接到某邻居节点的 `QbbNetDevice` 接口索引（`GetIfIndex()` 返回值）。
  - **`up`**：链路是否可用；`true` 表示链路当前在线，`false` 表示被 `TakeDownLink` 逻辑“拉掉”。
  - **`delay`**：链路单向传播时延，单位为 ns，对应 `QbbChannel::GetDelay().GetTimeStep()`。
  - **`bw`**：链路带宽，单位 bit/s，对应 `QbbNetDevice::GetDataRate().GetBitRate()`。
- **作用**：
  - 构成 `nbr2if`（邻居拓扑图）的基本单元：
    - `nbr2if[a][b]` 表示从节点 `a` 到相邻节点 `b` 的链路属性。
  - 被 **路由计算**（`CalculateRoute`）、**路由重配置**（`TakeDownLink`）、**链路速率导出**（端口速率写入 `SimSetting`）等多处使用。

### 1.2 `FlowInput`

- **定义**：
  ```cpp
  struct FlowInput {
    uint32_t src, dst, pg, maxPacketCount, port, dport;
    double start_time;
    uint32_t idx;
  };
  ```
- **成员解释**：
  - **`src`**：流的源主机节点 ID（与 `n.Get(id)` 一致）。
  - **`dst`**：流的目的主机节点 ID。
  - **`pg`**：流所属“流量组/优先级/PG”编号（被 `RdmaClientHelper` 作为参数传给 RDMA 层）。
  - **`maxPacketCount`**：本流传输的总字节数（或总负载大小，以 B 计）。
  - **`port`**：源端口号字段（结构体成员，但真正生效的端口号由 `ScheduleFlowInputs` 中的 `portNumder[src][dst]` 动态分配）。
  - **`dport`**：目的端口号，从流文件中读取。
  - **`start_time`**：流计划启动时间（秒），相对于仿真起点。
  - **`idx`**：当前处理到的流索引，全局自增。
- **作用**：
  - `ReadFlowInput()` 将流文件中的一行解析填充到 `flow_input`；
  - `ScheduleFlowInputs()` 根据 `flow_input` 信息创建 RDMA 客户端应用，使用 `idx` 来判断是否已处理完所有流。

### 1.3 `QlenDistribution`

- **定义**：
  ```cpp
  struct QlenDistribution {
    vector<uint32_t> cnt; // cnt[i] 为“队列长度约为 i KB”出现的次数
    void add(uint32_t qlen);
  };
  ```
- **`add(uint32_t qlen)` 逻辑**：
  - 计算 `kb = qlen / 1000`，将字节长度粗略量化为 KB 桶；
  - 若 `cnt` 长度不够则扩容到 `kb + 1`；
  - 对应桶 `cnt[kb]++`。
- **作用**：
  - `queue_result[swId][portId]` 存的是一个 `QlenDistribution`；
  - 由 `monitor_buffer()` 周期性调用 `add()` 对各交换机端口的总队列字节数进行打点统计；
  - 当时间到达 `qlen_dump_interval` 的倍数时，将所有分布写入队列监控文件。

### 1.4 关键容器与映射

| 名称 | 类型 | 说明 |
| ---- | ---- | ---- |
| `NodeContainer n` | `ns3::NodeContainer` | 全网所有节点容器（主机+交换机）。 |
| `nbr2if` | `map<Ptr<Node>, map<Ptr<Node>, Interface>>` | “节点 → 邻居节点 → 链路属性”的拓扑图。 |
| `nextHop` | `map<Ptr<Node>, map<Ptr<Node>, vector<Ptr<Node>>>>` | 对于任一节点 `u` 和目的节点 `dst`，存储从 `u` 到 `dst` 的所有最短路径上的“下一跳集合”。 |
| `pairDelay` | `map<Ptr<Node>, map<Ptr<Node>, uint64_t>>` | 单向传播时延和：`pairDelay[src][dst]`。 |
| `pairTxDelay` | `map<Ptr<Node>, map<Ptr<Node>, uint64_t>>` | 发送报文的传输时延和（与 `packet_payload_size`、`bw` 相关）。 |
| `pairBw` | `map<uint32_t, map<uint32_t, uint64_t>>` | 主机对层面的瓶颈带宽（bit/s）。 |
| `pairBdp` | `map<Ptr<Node>, map<Ptr<Node>, uint64_t>>` | 主机对的 BDP（字节），基于 RTT 与带宽计算。 |
| `pairRtt` | `map<uint32_t, map<uint32_t, uint64_t>>` | 主机对的 RTT（ns），`pairRtt[srcId][dstId]`。 |
| `serverAddress` | `vector<Ipv4Address>` | 主机节点的主 IP，索引与节点 ID 一致。 |
| `portNumder` | `unordered_map<uint32_t, unordered_map<uint32_t, uint16_t>>` | 对每对主机 `(src,dst)`，记录“下一个可用源端口号”，初始为 10000。 |
| `rate2kmin/rate2kmax` | `unordered_map<uint64_t,uint32_t>` | 带宽（bit/s）→ ECN kmin/kmax；从配置文件 KMIN_MAP/KMAX_MAP 读入。 |
| `rate2pmax` | `unordered_map<uint64_t,double>` | 带宽（bit/s）→ ECN pmax。 |
| `queue_result` | `map<uint32_t, map<uint32_t, QlenDistribution>>` | 交换机端口队列分布：`queue_result[switchId][portId]`。 |
| `agent_nodes` | `set<int>` | 需要启用 RDMA NPA Agent 的主机 ID 集。 |
| `no_cc_nodes` | `set<int>` | 不启用拥塞控制（`CcMode=0`）的主机 ID 集。 |

---

## 2. 全局变量详解

### 2.1 网络与基础仿真参数

- **`uint32_t cc_mode`**  
  拥塞控制模式编号，影响：
  - `IntHeader::mode` 的选择（TS/NORMAL/PINT/NONE）；
  - 交换机 `SwitchNode` 的 `"CcMode"` 属性；
  - RDMA 硬件 `RdmaHw` 的 `"CcMode"`。

- **`bool enable_qcn`**  
  控制 `QbbNetDevice::QcnEnabled`，是否在交换机/网卡上启用基于 QCN 的 Congestion Notification。

- **`bool use_dynamic_pfc_threshold`**  
  控制 `QbbNetDevice::DynamicThreshold`，是否启用动态 PFC 阈值调整策略。

- **`uint32_t packet_payload_size`**  
  RDMA 报文负载大小（MTU），用于：
  - L2 报文切分；
  - 在 `CalculateRoute` 中估算发送传输延迟 `txDelay`；
  - 作为 `RdmaHw::Mtu`。

- **`uint32_t l2_chunk_size` / `l2_ack_interval`**  
  L2 层分块大小与 ACK 上报间隔，通过 `RdmaHw` 属性影响底层传输行为。

- **`double pause_time`**  
  传入 `QbbNetDevice::PauseTime`，控制接收到 PFC 帧后链路暂停时间。

- **`double simulator_stop_time`**  
  仿真结束时间（秒），用于 `Simulator::Stop(Seconds(simulator_stop_time))`。

- **路径/文件相关字符串**：
  - `data_rate`, `link_delay`：若配置文件写了全局带宽/时延，会记录在这里（实际 per-link 属性仍然以 topo 文件为准）。
  - `topology_file`：拓扑描述文件路径（节点数、交换机 ID 列表、链路三元组等）。
  - `flow_file`：流配置文件路径（每条流的 src/dst/pg/size/start_time 等）。
  - `trace_file`：trace 节点 ID 列表文件。
  - `trace_output_file`：trace 输出文件；可能在命令行追加后缀。
  - `dir`：输出目录，用于构造 `telemetry_path` 等。
  - `fct_output_file`：FCT 结果输出文件（默认为 `fct.txt`，可由配置覆盖）。
  - `pfc_output_file`：PFC 事件输出文件（默认为 `pfc.txt`）。

### 2.2 拥塞控制与 RDMA 相关参数

- **`double alpha_resume_interval`**  
  RDMA 算法中 alpha 的恢复间隔，通过 `RdmaHw::AlphaResumInterval` 设置。

- **`double rp_timer`**  
  重传/恢复定时器周期，通过 `RdmaHw::RPTimer` 设置。

- **`double ewma_gain`**  
  EWMA 平滑系数，通过 `RdmaHw::EwmaGain` 设置，控制 RTT/队列等平滑程度。

- **`double rate_decrease_interval`**  
  速率递减周期，通过 `RdmaHw::RateDecreaseInterval` 设置。

- **`uint32_t fast_recovery_times`**  
  快速恢复最大次数，通过 `RdmaHw::FastRecoveryTimes`。

- **速率相关字符串（带单位）**：
  - `rate_ai`：Additive Increase 速率步长。
  - `rate_hai`：High Additive Increase 速率。
  - `dctcp_rate_ai`：DCTCP 模式下的 AI 步长。
  - `min_rate`：最小速率下限。
  → 这些全部在 `RdmaHw` 中通过 `DataRateValue` 注入。

- **控制行为开关**：
  - `clamp_target_rate`：是否“钳制”目标速率到某范围。
  - `l2_back_to_zero`：L2 是否使用 “back-to-zero” 策略。
  - `has_win`：是否在 RDMA 客户端中开启“窗口 = BDP”的窗口控制（影响 `RdmaClientHelper` 内部参数）。
  - `global_t`：为 1 时流窗口使用全局最大 BDP/RTT，否则使用主机对的 `pairBdp/pairRtt`。
  - `mi_thresh`：Multi-Increase 的门限；
  - `var_win`：是否使用可变窗口；
  - `fast_react`：是否快速对拥塞反馈作出反应；
  - `multi_rate`：是否支持多速率链路；
  - `sample_feedback`：是否只采样一部分反馈（PINT 相关）；
  - `u_target`：目标链路利用率（0~1），控制拥塞控制目标；
  - `int_multi`：INT 多跳处理模式常量（赋给 `IntHop::multi`）；
  - `rate_bound`：是否对发送速率进行约束；
  - `ack_high_prio`：是否将 ACK 放在最高优先级队列（影响 `RdmaEgressQueue::ack_q_idx`）。

### 2.3 故障与队列监控参数

- **链路故障相关**：
  - `link_down_time`：链路下线发生时间（us 偏移），实际调度时间为 `2s + MicroSeconds(link_down_time)`。
  - `link_down_A`, `link_down_B`：将被下线的两个节点 ID。

- **Trace 相关**：
  - `enable_trace`：是否启用 Qbb trace（INT/队列等）；若为 0，则不调用 `qbb.EnableTracing`。

- **缓冲区与队列监控**：
  - `buffer_size`：交换机缓冲区大小，单位 KB。实际调用 `ConfigBufferSize(buffer_size * 1024)`。
  - `qlen_dump_interval`：每隔多少个仿真时间步，把当前 `queue_result` 写入监控文件。
  - `qlen_mon_interval`：`monitor_buffer` 调度周期，单位 ns。
  - `qlen_mon_start`/`qlen_mon_end`：队列监控的起止时间（ns），超过 `qlen_mon_end` 后不再调度。
  - `qlen_mon_file`：队列监控输出文件路径。

### 2.4 RDMA NPA / Agent 相关参数

- **`set<int> agent_nodes`**  
  从配置 `AGENT_NODE` 读入，表示启用 NPA Agent 逻辑的主机集合。

- **`uint32_t agent_threshold`**  
  Agent 的触发阈值（如队列长度/流量门限），通过 `RdmaHw::m_agent_threshold` 使用。

- **`uint32_t epoch_time`**  
  交换机端的 epoch 时长，赋给 `SwitchNode::epochTime`，决定统计与重置周期。

- **`set<int> no_cc_nodes`**  
  `NO_CC_NODE` 集合；这些主机在安装 `RdmaHw` 时会强制 `CcMode = 0`，即关闭拥塞控制。

### 2.5 运行时变量

- **文件流**：
  - `std::ifstream topof`：拓扑文件；
  - `std::ifstream flowf`：流配置文件；
  - `std::ifstream tracef`：trace 节点列表文件。

- **全局节点与速率**：
  - `NodeContainer n`：所有 NS-3 节点；
  - `uint64_t nic_rate`：某主机网卡速率，用作 PFC 参数归一化的参考；
  - `uint64_t maxRtt`：遍历所有主机对得到的 **最大 RTT**；
  - `uint64_t maxBdp`：对应的 **最大 BDP**。

- **流相关**：
  - `FlowInput flow_input`：当前正在处理的一条流；
  - `uint32_t flow_num`：总流数量（从流文件开头读取）。

---

## 3. 函数详细说明

本节以“输入 → 核心逻辑 → 输出/副作用”的形式讲解，以便查找和调试。

### 3.1 流调度相关

#### 3.1.1 `ReadFlowInput()`

- **输入**：无（依赖全局 `flowf`、`flow_input.idx`、`flow_num`）。
- **核心逻辑**：
  1. 判断当前 `flow_input.idx < flow_num`，否则不再读取；
  2. 从 `flowf` 中依次读取 `src dst pg dport maxPacketCount start_time`；
  3. 检查 `n.Get(src)` 与 `n.Get(dst)` 都是主机（`GetNodeType() == 0`），否则触发 `NS_ASSERT`。
- **输出/副作用**：
  - 更新全局 `flow_input` 结构；
  - 文件指针前进到下一行。

#### 3.1.2 `ScheduleFlowInputs()`

- **输入**：无显式参数，使用全局 `flow_input`, `flow_num`, `n`, `serverAddress`, `portNumder`, `has_win`, `global_t`, `pairBdp`, `pairRtt`, `maxBdp`, `maxRtt`。
- **核心逻辑**：
  1. 在当前仿真时刻 `Now()` 下，循环处理所有 `flow_input.start_time == Now()` 的流：
     - 从 `portNumder[src][dst]` 中取当前端口并自增；
     - 根据 `has_win` / `global_t` 选择窗口/RTT 参数：
       - 若 `has_win == 1 && global_t == 1`：窗口使用 `maxBdp`，RTT 使用 `maxRtt`；
       - 若 `has_win == 1 && global_t != 1`：窗口使用 `pairBdp[srcNode][dstNode]`，RTT 使用 `pairRtt[src][dst]`；
       - 若 `has_win == 0`：窗口大小参数传 0；
     - 构造 `RdmaClientHelper`，传入 `(pg, serverAddress[src], serverAddress[dst], port, dport, size, win, rtt)`；
     - 将应用安装在源主机 `n.Get(src)` 上，并调用 `appCon.Start(Time(0))` 立即启动；
     - 打印包含 ID/端口/大小/PG/计划起始时间的详细日志；
     - `flow_input.idx++` 并调用 `ReadFlowInput()` 准备下一条。
  2. 所有“当前时刻到期”的流都调度完后：
     - 若 `flow_input.idx < flow_num`：调度下一次调用  
       `Simulator::Schedule(Seconds(flow_input.start_time) - Now(), ScheduleFlowInputs);`  
       这里 `flow_input.start_time` 已更新为下一条流的开始时间；
     - 否则：关闭 `flowf`。
- **输出/副作用**：
  - 在合适的仿真时刻安排所有 RDMA 流；
  - 不停自调度直至所有流完成装载。

#### 3.1.3 `node_id_to_ip()` / `ip_to_node_id()`

- **作用**：
  - `node_id_to_ip(id)`：将节点 ID 编码为 IP 地址 `11.x.y.1`，保证唯一可逆；
  - `ip_to_node_id(ip)`：通过 `ip.Get() >> 8 & 0xffff` 还原节点 ID。
- **使用场景**：
  - 主机 IP 分配（`serverAddress[i] = node_id_to_ip(i)`）；
  - 在 `qp_finish` 中，通过 `sip/dip` 恢复源/目的节点 ID。

#### 3.1.4 `Ipv4AddressToString()`

- **作用**：工具函数，便于在日志中打印 `Ipv4Address`。

---

### 3.2 RDMA 完成与队列/PFC 监控

#### 3.2.1 `qp_finish(FILE* fout, Ptr<RdmaQueuePair> q)`

- **输入**：FCT 输出文件指针 `fout`，完成的队列对 `q`。
- **核心逻辑**：
  1. 从 `q->sip/dip` 提取源/目节点 ID：`sid`, `did`；
  2. 从 `pairRtt[sid][did]`、`pairBw[sid][did]` 获取 RTT 与瓶颈带宽；
  3. 将逻辑“载荷大小 + 协议头部开销”合并成 `total_bytes`：
     - `m_size` 为原始应用层字节数；
     - 通过 `(m_size-1)/packet_payload_size+1` 估算需要多少个数据包，再乘以头部大小得到总开销；
  4. 假设在该带宽/RTT 的独享链路上，计算理想 FCT：  
     `standalone_fct = base_rtt + total_bytes * 8e9 / b (ns)`；
  5. 将 `sip/dip/sport/dport/size/startTime/实际FCT/standalone_fct` 写入 `fout`；
  6. 打印人类可读日志，展示 FCT 与 standalone FCT；
  7. 在接收端主机上找到 `RdmaDriver`，调用 `DeleteRxQp` 删除该接收 QP。
- **输出/副作用**：
  - 更新 FCT 统计文件；
  - 回收接收端 QP 资源。

#### 3.2.2 `get_pfc(FILE* fout, Ptr<QbbNetDevice> dev, uint32_t type)`

- **输入**：输出文件指针、发生 PFC 的网卡设备、事件类型 `type`。
- **核心逻辑**：
  - 每当设备 `dev` 触发 `"QbbPfc"` trace 时调用：
    - 记录当前时间 `Now().GetTimeStep()`、节点 ID、节点类型、接口索引、事件类型到文件 `fout`。
- **输出/副作用**：
  - 累积全网 PFC 事件时间序列，用于后续排查 PFC 风暴等问题。

#### 3.2.3 `monitor_buffer(FILE* qlen_output, NodeContainer *n)`

- **输入**：队列监控输出文件、节点容器指针。
- **核心逻辑**（每次被调度执行时）：
  1. 遍历 `*n` 中所有节点：
     - 若是交换机（`GetNodeType() == 1`），取得 `SwitchNode` 指针；
     - 确保 `queue_result[swId]` 存在；
     - 遍历该交换机的所有端口 `j`（从 1 开始，跳过 CPU 端口 0）：
       - 对每个优先级队列 `k` 累加 `sw->m_mmu->egress_bytes[j][k]`；
       - 得到端口 `j` 的总队列字节数 `size`；
       - 调用 `queue_result[swId][j].add(size)` 做分布统计。
  2. 若 `Now().GetTimeStep() % qlen_dump_interval == 0`：
     - 将当前时间与所有 `queue_result` 条目写入 `qlen_output`，并 `fflush`。
  3. 若 `Now().GetTimeStep() < qlen_mon_end`：
     - `Simulator::Schedule(NanoSeconds(qlen_mon_interval), &monitor_buffer, qlen_output, n)` 继续周期调度自身。
- **输出/副作用**：
  - 周期性更新全网队列分布采样；
  - 以“时间 + (交换机ID,端口,直方图)”的形式持久化到监控文件。

---

### 3.3 路由与链路重配置

#### 3.3.1 `CalculateRoute(Ptr<Node> host)`

- **输入**：主机节点指针 `host`。
- **核心逻辑**：
  1. 初始化 BFS 队列 `q`，并将 `host` 入队：
     - `dis[host] = 0`、`delay[host] = 0`、`txDelay[host] = 0`；
     - `bw[host] = 无穷大 (0xfffffffffffffffflu)`。
  2. 对队列中每个节点 `now`：
     - 对 `now` 的每个邻居 `next`（遍历 `nbr2if[now]`）：
       - 若该链路 `up == false`，跳过；
       - 如果 `dis` 中尚未记录 `next`：
         - 记录 `dis[next] = dis[now] + 1`；
         - 传播时延累加：`delay[next] = delay[now] + link.delay`；
         - 传输时延累加：`txDelay[next] = txDelay[now] + packet_payload_size * 8e9 / link.bw`；
         - 瓶颈带宽更新：`bw[next] = min(bw[now], link.bw)`；
         - 若 `next` 是交换机（`GetNodeType()==1`），入队继续 BFS（主机不作为中转）；
       - 若 `dis[next]` 已存在，检查是否满足 `dis[now] + 1 == dis[next]`：
         - 若是，则说明 `now` 是 `next → host` 最短路径上的一个前驱，将其加入 `nextHop[next][host]` 作为“下一跳候选”。
  3. BFS 结束后：
     - 将 `delay`、`txDelay`、`bw` 拷贝到全局 `pairDelay`、`pairTxDelay`、`pairBw`。
- **输出/副作用**：
  - 填充从指定主机 `host` 出发的全网路由代价与下一跳信息；
  - 为后续 `SetRoutingEntries` 和 RTT/BDP 计算打基础。

#### 3.3.2 `CalculateRoutes(NodeContainer &n)`

- **输入**：全网节点容器。
- **核心逻辑**：
  - 遍历容器中所有节点 `node`：
    - 若 `node` 是主机（`GetNodeType()==0`），调用 `CalculateRoute(node)`。
- **输出/副作用**：
  - 为每一个主机构建 `nextHop` 中的路由树；
  - 同时更新 `pairDelay/pairTxDelay/pairBw`。

#### 3.3.3 `SetRoutingEntries()`

- **输入**：无（使用全局 `nextHop`、`nbr2if`、`n`）。
- **核心逻辑**：
  1. 对每个节点 `node`（`i->first`）的下一跳表 `table`（`i->second`）：
     - 对每一个目的节点 `dst`：
       - 获取其主 IP 地址 `dstAddr`（`dst->GetObject<Ipv4>()->GetAddress(1,0)`）；
       - 取出所有最短路径的下一跳节点集合 `nexts`；
       - 对每个 `next`：
         - 通过 `nbr2if[node][next].idx` 得到实际出口接口号；
         - 若 `node` 是交换机：`SwitchNode::AddTableEntry(dstAddr, interface)`；
         - 若是主机：`RdmaDriver::m_rdma->AddTableEntry(dstAddr, interface)`。
- **输出/副作用**：
  - 将逻辑路由信息转化为硬件/软件转发表，真正决定报文如何转发。

#### 3.3.4 `TakeDownLink(NodeContainer n, Ptr<Node> a, Ptr<Node> b)`

- **输入**：节点容器（按值传递）、两个节点指针 `a`、`b`。
- **核心逻辑**：
  1. 若 `nbr2if[a][b].up == false`，说明已经下线，直接返回；
  2. 将 `nbr2if[a][b].up` 与 `nbr2if[b][a].up` 置为 `false`；
  3. 清空 `nextHop`，重新对所有主机执行 `CalculateRoutes(n)`；
  4. 清空所有节点的路由/转发表：
     - 对每个交换机 `sw`：`sw->ClearTable()`；
     - 对每个主机的 RDMA：`rdma->m_rdma->ClearTable()`；
  5. 对实际设备层的链路调用 `TakeDown()`：
     - `DynamicCast<QbbNetDevice>(a->GetDevice(idxA))->TakeDown()`；
     - `DynamicCast<QbbNetDevice>(b->GetDevice(idxB))->TakeDown()`；
  6. 再次调用 `SetRoutingEntries()`，根据新拓扑重建转发表；
  7. 遍历所有主机，调用  
     `n.Get(i)->GetObject<RdmaDriver>()->m_rdma->RedistributeQp()`  
     让现有 QP 在新路由下重新分布。
- **输出/副作用**：
  - 模拟链路故障对全网路由的影响；
  - 保证 RDMA 连接在新的转发表下继续工作。

#### 3.3.5 `get_nic_rate(NodeContainer &n)`

- **输入**：节点容器。
- **核心逻辑**：
  - 找到容器中第一个主机节点，返回其 `QbbNetDevice(1)` 的 DataRate（bit/s）。
- **输出/副作用**：
  - 作为后续配置 PFC 抑制系数 `pfc_a_shift` 的基准。

---

### 3.4 `main(int argc, char *argv[])` 详细流程

可以把 `main` 看成一个“大状态机”，大致分 6 个阶段：

1. **读配置阶段**：解析 config 文件 → 设置全局参数；
2. **搭拓扑阶段**：读拓扑/trace/flow 文件头 → 创建节点 → 安装协议栈 → 分配主机 IP；
3. **建链路阶段**：逐条链路创建 Qbb 设备 → 绑定 PFC trace → 填充 `nbr2if`；
4. **配置交换机/主机阶段**：配置 ECN/PFC/缓冲 → 安装 RDMA → 设置 ACK 队列；
5. **路由与统计阶段**：手工计算/下发路由 → 计算 BDP/RTT → 设置 CC 参数 → 配置 trace；
6. **调度与仿真运行阶段**：初始化端口号/流调度/链路下线/队列监控 → `Simulator::Run`。

（该流程在下一节的“文字版流程图”中再做一次串联说明。）

---

## 4. 函数调用链与文字版流程图

以下按“时间顺序”描述关键函数之间的调用/触发关系，可视为文字版的流程图。

### 4.1 仿真启动阶段

1. **命令行启动**  
   `main(argc, argv)`  
   → 检查是否提供 config 文件，否则直接退出。

2. **配置解析**  
   `main` 内部循环读取配置文件的每一行 `key`：  
   - 对 `ENABLE_QCN` / `USE_DYNAMIC_PFC_THRESHOLD` / `CLAMP_TARGET_RATE` 等布尔量：更新对应全局变量并打印日志；  
   - 对 `DATA_RATE` / `LINK_DELAY` / `TOPOLOGY_FILE` / `FLOW_FILE` / `TRACE_FILE` / `TRACE_OUTPUT_FILE` / `DIR` 等路径或参数：保存字符串；  
   - 对 `ALPHA_RESUME_INTERVAL` / `RP_TIMER` / `EWMA_GAIN` / `FAST_RECOVERY_TIMES` / `RATE_AI` / `RATE_HAI` 等 CC 参数：填充至相应全局变量；  
   - 对 `KMAX_MAP` / `KMIN_MAP` / `PMAX_MAP`：读取 (rate, k/p) 表，填充 `rate2kmax/kmin/pmax`；  
   - 对 `AGENT_NODE` / `NO_CC_NODE` / `AGENT_THRESHOLD` / `EPOCH_TIME` 等 NPA 参数：填充集合和阈值。

3. **全局 Qbb/INT/PINT 设置**  
   - `Config::SetDefault("ns3::QbbNetDevice::PauseTime", pause_time)`；  
   - `Config::SetDefault("ns3::QbbNetDevice::QcnEnabled", enable_qcn)`；  
   - `Config::SetDefault("ns3::QbbNetDevice::DynamicThreshold", use_dynamic_pfc_threshold)`；  
   - `IntHop::multi = int_multi`；  
   - 根据 `cc_mode` 决定 `IntHeader::mode`；若为 PINT 模式则调用 `Pint::set_log_base` 并打印 PINT bit/byte 数。

### 4.2 拓扑与设备创建阶段

4. **读拓扑/流/trace 文件头**  
   - `topof >> node_num >> switch_num >> link_num`；  
   - `flowf >> flow_num`；  
   - `tracef >> trace_num`。

5. **创建节点 & 安装协议栈**  
   - 通过 `node_type` 数组标记交换机 ID；  
   - `n.Add(CreateObject<Node>())` 或 `n.Add(CreateObject<SwitchNode>())`；交换机上设置 `EcnEnabled`；  
   - `InternetStackHelper internet; internet.Install(n)` 安装 IPv4 协议栈；
   - 对所有主机节点，将 `serverAddress[i] = node_id_to_ip(i)`。

6. **链路 & 设备创建循环（link_num 次）**  
   每条链路：  
   - 从 `topof` 读入 `src, dst, data_rate, link_delay, error_rate`；  
   - 设置 `qbb.SetDeviceAttribute("DataRate")` / `SetChannelAttribute("Delay")`；  
   - 根据 `error_rate` 决定是否为该链路单独创建 `RateErrorModel`；  
   - `NetDeviceContainer d = qbb.Install(snode, dnode)` 创建成对 `QbbNetDevice` 与 `QbbChannel`；  
   - 若 `snode/dnode` 是主机：调用其 `Ipv4` 对象，为 `d.Get(0/1)` 添加接口，并使用 `serverAddress[src/dst]` 作为 primary IP；  
   - 使用 `nbr2if` 记录每条方向的接口索引、状态（up）、delay 和 bw；  
   - 通过 `Ipv4AddressHelper ipv4` 自动给链路分配 10.x.x.0/24 的辅助子网并 `Assign(d)`；  
   - 将两个 `QbbNetDevice` 上的 `"QbbPfc"` trace 绑定到 `get_pfc`。

### 4.3 交换机/主机配置与路由阶段

7. **计算 NIC 速率**  
   `nic_rate = get_nic_rate(n)`。

8. **配置交换机 MMU**  
   遍历所有 `SwitchNode`：  
   - 遍历其每个端口 `j`：  
     - 获得端口速率 `rate` 并从 `rate2kmin/kmax/pmax` 查表配置 ECN (`ConfigEcn`)；  
     - 获取链路传播延迟 `delay`，估算 headroom 大小 `headroom = rate * delay / 8 / 1e9 * 3`，调用 `ConfigHdrm`；  
     - 根据 `rate` 与 `nic_rate` 调整 `pfc_a_shift[j]`；  
   - 配置端口数、缓冲大小、节点 ID；  
   - 打开 `fp_telemetry` 文件，并设置 `AckHighPrio` 与 `epochTime`。

9. **安装 RDMA 驱动（条件编译 `ENABLE_QP`）**  
   对所有主机节点：  
   - 创建 `RdmaHw`，设置 CC/L2/PINT 相关属性；  
   - 将 `agent_threshold` 和 `agent_nodes/no_cc_nodes` 信息传入 `RdmaHw`；  
   - 创建 `RdmaDriver`，与 `RdmaHw` 和 `Node` 绑定并 `Init()`；  
   - 通过 `TraceConnectWithoutContext("QpComplete", ...)` 将 `qp_finish` 注册为队列完成回调。

10. **设置 ACK 优先级队列**  
    - 若 `ack_high_prio` 为 1：`RdmaEgressQueue::ack_q_idx = 0`；  
    - 否则置为 3。

11. **计算路由、下发转发表**  
    - `CalculateRoutes(n)`：对所有主机执行 BFS，填充 `nextHop` 与 `pairDelay/pairTxDelay/pairBw`；  
    - `SetRoutingEntries()`：将 `nextHop` 写入各节点转发表/路由表。

12. **计算 RTT/BDP 并同步到 CC**  
    - 遍历所有主机对 `(i,j)`：  
      - 从 `pairDelay/pairTxDelay/pairBw` 计算 RTT 与 BDP；  
      - 写入 `pairBdp` 与 `pairRtt`；  
      - 更新 `maxRtt` 与 `maxBdp`；  
    - 再遍历交换机，为其设置 `"CcMode"` 与 `"MaxRtt"`。

13. **配置 Trace 与导出端口速率**  
    - 从 `tracef` 读取 `trace_num` 个节点 ID 构造 `trace_nodes`；  
    - 打开 `trace_output` 文件；  
    - 若 `enable_trace`，调用 `qbb.EnableTracing(trace_output, trace_nodes)`；  
    - 遍历 `nbr2if` 中的所有 `(node, intf)`，根据 `QbbNetDevice::GetDataRate()` 填写 `SimSetting::port_speed`；  
    - 设置 `sim_setting.win = maxBdp`，调用 `Serialize(trace_output)` 输出仿真参数。

14. **补充 IP 层路由**  
    - 调用 `Ipv4GlobalRoutingHelper::PopulateRoutingTables()`，让 ns-3 自动构建 IP 层路由表（与自定义转发表并存）。

### 4.4 流调度、链路下线与监控阶段

15. **端口号表与流调度初始化**
    - 遍历所有主机对 `(i,j)`，将 `portNumder[i][j] = 10000`；
    - 将 `flow_input.idx = 0`；
    - 若 `flow_num > 0`：  
      - 先 `ReadFlowInput()` 读取第一条流；  
      - 调度第一次 `ScheduleFlowInputs`：  
        `Simulator::Schedule(Seconds(flow_input.start_time) - Now(), ScheduleFlowInputs);`

16. **拓扑/trace 文件关闭**  
    - 提前关闭 `topof` 与 `tracef`。

17. **链路下线事件调度（可选）**  
    - 若 `link_down_time > 0`：  
      `Simulator::Schedule(Seconds(2) + MicroSeconds(link_down_time), &TakeDownLink, n, n.Get(link_down_A), n.Get(link_down_B));`

18. **队列监控调度**  
    - 打开队列监控输出 `qlen_output`；  
    - `Simulator::Schedule(NanoSeconds(qlen_mon_start), &monitor_buffer, qlen_output, &n);`  
      后续由 `monitor_buffer` 自己周期性调度自己。

### 4.5 仿真运行与结束阶段

19. **启动仿真**  
    - 打印 “Hello Hawkeye! / Running Simulation.”；  
    - `Simulator::Stop(Seconds(simulator_stop_time))`；  
    - `Simulator::Run()`：  
      - 期间按计划触发：  
        - 流调度链：`ScheduleFlowInputs` ⇄ `ReadFlowInput` → `RdmaClientHelper::Install` → 应用启动；  
        - QP 完成链：`RdmaDriver::QpComplete` → `qp_finish`；  
        - PFC 链：`QbbNetDevice::QbbPfc` → `get_pfc`；  
        - 链路下线链：`TakeDownLink` → `CalculateRoutes` → `SetRoutingEntries` → `RedistributeQp`；  
        - 队列监控链：`monitor_buffer` 周期性扫描 `SwitchNode::m_mmu` → 写队列分布。

20. **结束与清理**  
    - `Simulator::Destroy()` 清理 ns-3 内部资源；  
    - 关闭 `trace_output`；  
    - 用 `clock()` 计算总运行时间并打印秒数。

---

通过上述更细致的变量解释与流程化调用链描述，可以较为完整地从 **配置 → 拓扑 → 路由 → 流量 → 监控** 的角度理解 `third.cc`。如果你希望，我也可以按这份说明帮你画一张正式的流程图（例如 Mermaid 或 Visio 结构），便于写报告或放在 PPT 里。***

