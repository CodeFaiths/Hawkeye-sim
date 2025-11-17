# Paraleon NS-3 项目函数执行流分析

## 1. 程序入口点

**文件**: `scratch/third.cc`  
**函数**: `main(int argc, char *argv[])` (第482行)

### 执行命令
```bash
./waf --run 'scratch/third mix/config.txt'
```

---

## 2. 主函数执行流程

### 2.1 初始化阶段 (main函数开始)

```
main()
├── 记录开始时间 (clock_t begint)
├── 读取配置文件 (argv[1] = "mix/config.txt")
│   └── ReadConfigFile() [内联在main中，第492-809行]
│       ├── 解析配置参数 (ENABLE_QCN, CC_MODE, U_TARGET等)
│       └── 设置全局变量
├── delete_files() [第442行]
│   └── 删除旧的追踪文件
└── 设置NS-3默认配置
    ├── Config::SetDefault("ns3::QbbNetDevice::PauseTime")
    ├── Config::SetDefault("ns3::QbbNetDevice::QcnEnabled")
    └── Config::SetDefault("ns3::QbbNetDevice::DynamicThreshold")
```

### 2.2 配置INT (In-band Network Telemetry) 模式

```cpp
// 根据CC_MODE设置INT模式
if (cc_mode == 3) // HPCC
    IntHeader::mode = IntHeader::NORMAL;
else if (cc_mode == 10) // HPCC-PINT
    IntHeader::mode = IntHeader::PINT;
```

### 2.3 读取拓扑和流文件

```
├── topof.open(topology_file)  // 打开拓扑文件
├── flowf.open(flow_file)      // 打开流文件
├── tracef.open(trace_file)    // 打开追踪文件
└── 读取文件头信息
    ├── topof >> node_num >> switch_num >> link_num
    ├── flowf >> flow_num
    └── tracef >> trace_num
```

---

## 3. 网络拓扑构建

### 3.1 创建节点

**函数**: `main()` 第857-872行

```
创建节点容器 (NodeContainer n)
├── 读取交换机ID列表
├── 标记节点类型 (0=主机, 1=交换机)
└── 创建节点对象
    ├── 主机节点: CreateObject<Node>()
    └── 交换机节点: CreateObject<SwitchNode>()
```

**关键代码**:
```cpp
for (uint32_t i = 0; i < node_num; i++){
    if (node_type[i] == 0)
        n.Add(CreateObject<Node>());
    else{
        Ptr<SwitchNode> sw = CreateObject<SwitchNode>();
        n.Add(sw);
    }
}
```

### 3.2 安装网络协议栈

**函数**: `main()` 第876-877行

```cpp
InternetStackHelper internet;
internet.Install(n);  // 为所有节点安装IP协议栈
```

### 3.3 分配IP地址

**函数**: `main()` 第882-887行

```cpp
for (uint32_t i = 0; i < node_num; i++){
    if (n.Get(i)->GetNodeType() == 0){ // 主机
        serverAddress[i] = node_id_to_ip(i);
    }
}
```

**IP地址映射函数**: `node_id_to_ip()` (第156行)
- 将节点ID转换为IP地址: `0x0b000001 + (id/256)*0x00010000 + (id%256)*0x00000100`

### 3.4 创建链路和网络设备

**函数**: `main()` 第906-970行

```
for each link in topology:
├── QbbHelper::Install() [创建QbbNetDevice和QbbChannel]
│   ├── 设置链路带宽 (DataRate)
│   ├── 设置链路延迟 (Delay)
│   └── 设置错误模型 (ErrorModel)
├── 分配IP地址
│   ├── 主机节点: 使用serverAddress
│   └── 其他节点: 使用自动分配的IP
├── 记录邻居接口信息 (nbr2if)
│   ├── 接口索引 (idx)
│   ├── 链路状态 (up)
│   ├── 延迟 (delay)
│   └── 带宽 (bw)
└── 连接PFC追踪回调
    └── QbbNetDevice::TraceConnectWithoutContext("QbbPfc", ...)
```

**关键组件**:
- **QbbHelper**: 创建QbbNetDevice和QbbChannel的辅助类
- **QbbNetDevice**: 支持PFC (Priority Flow Control) 的网络设备
- **QbbChannel**: 点对点信道

---

## 4. 交换机配置

**函数**: `main()` 第974-1004行

```
for each switch node:
├── 获取SwitchNode对象
├── 配置ECN (Explicit Congestion Notification)
│   ├── 根据链路速率查找KMIN, KMAX, PMAX
│   └── SwitchMmu::ConfigEcn()
├── 配置PFC (Priority Flow Control)
│   ├── 计算headroom: rate * delay / 8 / 1e9 * 3
│   └── SwitchMmu::ConfigHdrm()
├── 配置PFC alpha参数
└── 配置缓冲区大小
    └── SwitchMmu::ConfigBufferSize(buffer_size * 1024 * 1024)
```

---

## 5. RDMA初始化

**函数**: `main()` 第1007-1051行

### 5.1 为每个主机安装RDMA驱动

```
for each host node:
├── 创建RdmaHw对象
│   ├── 设置拥塞控制参数 (CC_MODE, U_TARGET等)
│   ├── 设置速率参数 (RateAI, RateHAI, MinRate)
│   └── 设置窗口参数 (HAS_WIN, VAR_WIN等)
├── 创建RdmaDriver对象
│   ├── RdmaDriver::SetNode()
│   ├── RdmaDriver::SetRdmaHw()
│   └── node->AggregateObject(rdma)
└── 初始化RDMA驱动
    └── RdmaDriver::Init()
        ├── 为每个网络接口创建RdmaInterfaceMgr
        ├── 创建RdmaQueuePairGroup
        └── RdmaHw::Setup()
```

**关键文件**:
- `src/point-to-point/model/rdma-hw.h/cc`: RDMA硬件抽象
- `src/point-to-point/model/rdma-driver.h/cc`: RDMA驱动接口
- `src/point-to-point/model/rdma-queue-pair.h/cc`: RDMA队列对

### 5.2 RDMA驱动初始化流程

**函数**: `RdmaDriver::Init()` (`src/point-to-point/model/rdma-driver.cc` 第21行)

```
RdmaDriver::Init()
├── 遍历所有网络设备
│   ├── 查找QbbNetDevice
│   ├── 创建RdmaInterfaceMgr
│   └── 创建RdmaQueuePairGroup
├── RdmaHw::SetNode()
└── RdmaHw::Setup()
    └── 设置回调函数 (QpComplete)
```

---

## 6. 路由计算

**函数**: `main()` 第1059-1061行

### 6.1 计算路由表

**函数**: `CalculateRoutes()` (第376行)

```
CalculateRoutes(NodeContainer &n)
└── for each host node:
    └── CalculateRoute(host)
        ├── BFS遍历网络拓扑
        ├── 计算到每个节点的最短路径
        ├── 计算延迟 (pairDelay)
        ├── 计算传输延迟 (pairTxDelay)
        ├── 计算带宽 (pairBw) - 取路径最小带宽
        └── 记录下一跳 (nextHop)
```

**函数**: `CalculateRoute()` (第329行)
- 使用BFS算法计算最短路径
- 只允许通过交换机转发，不经过其他主机

### 6.2 设置路由条目

**函数**: `SetRoutingEntries()` (第384行)

```
SetRoutingEntries()
└── for each node:
    └── for each destination:
        ├── 获取目标IP地址
        ├── 获取下一跳节点列表
        └── 添加路由表项
            ├── 交换机: SwitchNode::AddTableEntry()
            └── 主机: RdmaHw::AddTableEntry()
```

### 6.3 计算BDP和RTT

**函数**: `main()` 第1064-1086行

```
计算最大RTT和BDP
├── for each host pair:
│   ├── 计算RTT: delay * 2 + txDelay
│   ├── 计算BDP: rtt * bw / 1e9 / 8
│   ├── 更新pairRtt[i][j]
│   └── 更新pairBdp[node_i][node_j]
└── 更新全局maxRtt和maxBdp
```

---

## 7. 应用层启动

**函数**: `main()` 第1135-1152行

### 7.1 初始化端口号

```cpp
for each host pair:
    portNumder[i][j] = 10000;  // 每个主机对从10000开始分配端口
```

### 7.2 调度流输入

**函数**: `ScheduleFlowInputs()` (第136行)

```
ScheduleFlowInputs()
├── while (有流需要启动 && 当前时间 == 流启动时间):
│   ├── 获取新端口号
│   ├── 创建RdmaClientHelper
│   │   └── 参数: pg, sip, dip, sport, dport, maxPacketCount, win, baseRtt
│   ├── 安装应用
│   │   └── RdmaClientHelper::Install()
│   ├── 启动应用
│   │   └── ApplicationContainer::Start(Time(0))
│   └── 读取下一个流
└── 如果还有流，调度下次执行
```

**流输入读取函数**: `ReadFlowInput()` (第130行)

```cpp
ReadFlowInput()
└── flowf >> src >> dst >> pg >> dport >> maxPacketCount >> start_time
```

### 7.3 RdmaClient应用启动

**文件**: `src/applications/model/rdma-client.cc`

```
RdmaClient::StartApplication()
└── RdmaDriver::AddQueuePair()
    ├── 创建RdmaQueuePair对象
    ├── 设置队列对参数 (size, win, baseRtt)
    └── RdmaHw::AddQueuePair()
        ├── 创建队列对
        ├── 添加到队列对组 (RdmaQueuePairGroup)
        ├── 初始化拥塞控制状态
        │   ├── CC_MODE=1 (DCQCN): mlx.m_targetRate
        │   ├── CC_MODE=3 (HPCC): hp.m_curRate
        │   └── CC_MODE=10 (HPCC-PINT): hpccPint.m_curRate
        └── 通知网络设备
            └── QbbNetDevice::NewQp()
```

---

## 8. 监控和追踪设置

**函数**: `main()` 第1100-1166行

### 8.1 设置包级追踪

```cpp
if (enable_trace)
    qbb.EnableTracing(trace_output, trace_nodes);
```

### 8.2 调度监控任务

```cpp
// 队列长度监控
Simulator::Schedule(NanoSeconds(qlen_mon_start), 
                    &monitor_buffer_new, qlen_output, &n);

// Sketch监控
Simulator::Schedule(NanoSeconds(qlen_mon_start), 
                    &monitor_sketch, &n);

// 参数调优
Simulator::Schedule(NanoSeconds(parameter_tuning_start), 
                    &parameter_tuning, &n);
```

**监控函数**:
- `monitor_buffer_new()` (第215行): 监控队列长度、RTT、吞吐量
- `monitor_sketch()` (第279行): 监控交换机sketch
- `parameter_tuning()` (第311行): 运行时参数调优

### 8.3 链路故障处理

```cpp
if (link_down_time > 0)
    Simulator::Schedule(Seconds(2) + MicroSeconds(link_down_time), 
                        &TakeDownLink, n, n.Get(link_down_A), n.Get(link_down_B));
```

**函数**: `TakeDownLink()` (第410行)
- 断开指定链路
- 重新计算路由
- 重新分配队列对

---

## 9. 仿真运行

**函数**: `main()` 第1171-1176行

```cpp
Simulator::Stop(Seconds(simulator_stop_time));
Simulator::Run();      // 执行仿真事件循环
Simulator::Destroy();  // 清理资源
```

### 9.1 NS-3事件调度器

NS-3使用离散事件仿真，主要事件包括:
1. **流启动事件**: `ScheduleFlowInputs()`
2. **包传输事件**: `QbbNetDevice::DequeueAndTransmit()`
3. **包接收事件**: `QbbNetDevice::Receive()`
4. **拥塞控制事件**: `RdmaHw::UpdateNextAvail()`
5. **PFC事件**: `SwitchNode::CheckAndSendPfc()`
6. **监控事件**: `monitor_buffer_new()`, `monitor_sketch()`

---

## 10. 关键组件交互流程

### 10.1 数据包发送流程

```
RdmaQueuePair (应用层)
    ↓
RdmaHw::SendPkt()
    ↓
QbbNetDevice::SwitchSend()
    ↓
BEgressQueue::Enqueue()  (入队)
    ↓
QbbNetDevice::DequeueAndTransmit()
    ↓
QbbNetDevice::TransmitStart()
    ↓
QbbChannel::TransmitStart()
    ↓
对端 QbbNetDevice::Receive()
```

### 10.2 拥塞控制流程 (HPCC)

```
数据包经过交换机
    ↓
SwitchNode::SendToDev()
    ↓
SwitchMmu::CheckIngressAdmission() / CheckEgressAdmission()
    ↓
如果队列长度超过阈值 → 设置ECN标记
    ↓
接收端收到带ECN标记的ACK
    ↓
RdmaHw::ProcessAck()
    ↓
根据CC_MODE更新速率
    ├── HPCC: 根据INT信息计算新速率
    └── 更新RdmaQueuePair::m_rate
```

### 10.3 PFC (Priority Flow Control) 流程

```
交换机队列长度超过PFC阈值
    ↓
SwitchMmu::CheckShouldPause()
    ↓
SwitchNode::CheckAndSendPfc()
    ↓
QbbNetDevice::SendPfc()  (发送PFC暂停帧)
    ↓
对端QbbNetDevice::Receive()  (接收PFC帧)
    ↓
设置m_paused[qIndex] = true
    ↓
暂停该优先级队列的发送
```

---

## 11. 关键文件结构

### 11.1 核心文件

| 文件 | 功能 |
|------|------|
| `scratch/third.cc` | 主程序入口，仿真配置和初始化 |
| `src/point-to-point/model/rdma-hw.h/cc` | RDMA硬件抽象，拥塞控制实现 |
| `src/point-to-point/model/rdma-driver.h/cc` | RDMA驱动接口 |
| `src/point-to-point/model/rdma-queue-pair.h/cc` | RDMA队列对 |
| `src/point-to-point/model/qbb-net-device.h/cc` | Qbb网络设备，PFC支持 |
| `src/point-to-point/model/switch-node.h/cc` | 交换机节点，路由和PFC |
| `src/applications/model/rdma-client.h/cc` | RDMA客户端应用 |

### 11.2 配置文件

| 文件 | 功能 |
|------|------|
| `mix/config.txt` | 仿真配置文件 |
| `mix/topology.txt` | 网络拓扑文件 |
| `mix/flow.txt` | 流定义文件 |
| `mix/trace.txt` | 追踪节点列表 |

### 11.3 输出文件

| 文件 | 内容 |
|------|------|
| `mix/fct.txt` | 流完成时间 (Flow Completion Time) |
| `mix/pfc.txt` | PFC事件记录 |
| `mix/qlen.txt` | 队列长度监控 |
| `mix/mix.tr` | 包级追踪文件 |

---

## 12. 函数调用关系图

```
main()
├── ReadConfigFile() [内联]
├── delete_files()
├── 创建节点和网络设备
│   ├── CreateObject<Node>()
│   ├── CreateObject<SwitchNode>()
│   └── QbbHelper::Install()
├── 配置交换机
│   └── SwitchMmu::ConfigEcn() / ConfigHdrm()
├── 初始化RDMA
│   ├── CreateObject<RdmaHw>()
│   ├── CreateObject<RdmaDriver>()
│   └── RdmaDriver::Init()
│       └── RdmaHw::Setup()
├── 计算路由
│   ├── CalculateRoutes()
│   │   └── CalculateRoute() [BFS]
│   └── SetRoutingEntries()
├── 启动应用
│   ├── ScheduleFlowInputs()
│   │   ├── ReadFlowInput()
│   │   └── RdmaClientHelper::Install()
│   │       └── RdmaClient::StartApplication()
│   │           └── RdmaDriver::AddQueuePair()
│   │               └── RdmaHw::AddQueuePair()
└── Simulator::Run()
    ├── 事件调度
    ├── 包传输/接收
    ├── 拥塞控制更新
    └── 监控任务
```

---

## 13. 关键数据结构

### 13.1 全局变量 (third.cc)

- `NodeContainer n`: 所有节点的容器
- `map<Ptr<Node>, map<Ptr<Node>, Interface> > nbr2if`: 邻居接口映射
- `map<Ptr<Node>, map<Ptr<Node>, vector<Ptr<Node> > > > nextHop`: 路由下一跳
- `map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairDelay`: 节点对延迟
- `map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairBw`: 节点对带宽
- `map<uint32_t, map<uint32_t, uint64_t> > pairRtt`: 节点对RTT
- `map<uint32_t, map<uint32_t, uint64_t> > pairBdp`: 节点对BDP

### 13.2 核心类

- **RdmaQueuePair**: RDMA队列对，包含拥塞控制状态
- **RdmaHw**: RDMA硬件抽象，实现拥塞控制算法
- **QbbNetDevice**: 支持PFC的网络设备
- **SwitchNode**: 交换机节点，实现路由和PFC
- **SwitchMmu**: 交换机内存管理单元，管理队列和PFC阈值

---

## 14. 拥塞控制算法支持

根据 `CC_MODE` 参数:
- **1**: DCQCN (Data Center Quantized Congestion Notification)
- **3**: HPCC (High Precision Congestion Control) ← 本项目主要算法
- **7**: Timely
- **10**: HPCC-PINT

每种算法在 `RdmaHw` 中有对应的状态结构:
- `mlx`: DCQCN状态
- `hp`: HPCC状态
- `tmly`: Timely状态
- `hpccPint`: HPCC-PINT状态

---

## 15. 总结

这个项目是一个基于NS-3的RDMA网络仿真器，主要特点:

1. **模块化设计**: 清晰的组件分离 (驱动、硬件抽象、网络设备、交换机)
2. **事件驱动**: 使用NS-3的离散事件仿真引擎
3. **灵活配置**: 通过配置文件控制所有参数
4. **完整追踪**: 支持包级追踪和统计监控
5. **多种CC算法**: 支持多种拥塞控制算法，重点是HPCC

执行流程: **配置读取 → 拓扑构建 → RDMA初始化 → 路由计算 → 应用启动 → 仿真运行**

