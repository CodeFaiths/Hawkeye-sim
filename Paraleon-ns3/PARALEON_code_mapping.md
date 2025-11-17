## PARALEON 论文思想与代码实现映射说明

本文档总结《PARALEON: Automatic and Adaptive Tuning for DCQCN Parameters in RDMA Networks》在当前 `Paraleon-ns3` 代码中的落地实现路径，帮助你从“论文概念”快速定位到“具体代码位置”。

整体上，PARALEON 实现的是一个闭环：

- **监测层（Measurement）**：在线采集 RTT / 吞吐 / PFC / 队列等指标  
- **决策层（Tuning Algorithm）**：Python 侧根据指标和效用函数自适应搜索 DCQCN 参数  
- **执行层（Parameter Application）**：NS-3 仿真运行过程中动态更新 NIC 的 DCQCN 参数及交换机 ECN 阈值  

对应到代码的总流程：

1. `third.cc` 周期性输出仿真指标到 `mix/*.tr` 文件  
2. `scratch/tuning.py` 在线解析这些 trace，计算效用函数并搜索更优参数，写入 `mix/parameter.txt`  
3. `third.cc::parameter_tuning()` 周期性读取 `mix/parameter.txt`，调用 `RdmaHw::ChangeParameters()` 和 `SwitchNode::ChangeECNthreshold()`  
4. DCQCN/ECN 内部逻辑在新的参数下继续运行，形成论文中的“自动、自适应调优”闭环  

---

## 1. 指标监控（Measurement）— 对应论文的“在线监测”

监控主要在 `scratch/third.cc` 中实现，核心函数是 `monitor_buffer_new` 和有关 PFC 的记录函数。

### 1.1 RTT 监控（端到端时延）

- **相关代码**：`third.cc` 中 `monitor_buffer_new` 函数内  
- **数据来源**：`RdmaHw::m_map_last_rtt`，每个 NIC 维护最近一次测得的 RTT  
- **数据输出**：写入 `mix/rtt.tr`  

逻辑概括：

- 遍历所有 `NodeType == 0` 的节点（NIC）  
- 从 `RdmaDriver` → `RdmaHw` 中取出 `m_map_last_rtt`（`<“sip-dip”, rtt>` 映射）  
- 写入格式类似：`time sip-dip rtt` 到 `mix/rtt.tr`  
- 写完后调用 `ClearRttMap()` 清空，避免重复统计  
- 以 `qlen_mon_interval` 为周期，用 `Simulator::Schedule` 循环调度

**论文对应关系**：  
这是论文中用来描述时延表现的关键指标，用于在调参过程中衡量延迟是否被控制在目标范围之内（例如避免过大的排队延迟）。

### 1.2 交换机端口吞吐（链路利用率）

- **相关代码**：仍在 `monitor_buffer_new` 内部  
- **数据来源**：`SwitchNode::getRxBytes()`，每个端口收到的字节数  
- **数据输出**：写入 `mix/switch_portrate.tr`  

逻辑概括：

- 遍历所有 `NodeType == 1` 的节点（交换机）  
- 调用 `SwitchNode::getRxBytes()`，拿到每个端口自上次采样后累积的 `rxBytes`  
- 对每个 `rxBytes[i] != 0` 的端口写一行：`time switchId port rxBytes`  
- 写入后将 `rxBytes[i]` 清零  

**论文对应关系**：  
这是论文中衡量“吞吐 / 链路利用率”的主要基础数据，后续在 Python 中会转成 Gbps，并归一化到效用函数中。

### 1.3 队列长度与 PFC（拥塞/严重拥塞指标）

- **队列长度（Queue Length）**  
  - 在 `monitor_buffer_new` 中，如果传入的 `qlen_output` 非空：  
    - 遍历所有交换机端口  
    - 汇总 `SwitchMmu::egress_bytes[port][q]`（所有队列的排队字节）  
    - 输出格式：`time switchId port qlen_bytes` 到指定文件（通常配置为 `mix/qlen.tr`）  
  - 反映链路上的排队状态，与 ECN 阈值 `kmin/kmax` 紧密相关  

- **PFC（Priority Flow Control）日志**  
  - 函数：`get_pfc(FILE* fout, Ptr<QbbNetDevice> dev, uint32_t type)`  
  - 写入 `mix/pfc.tr`，内容含 `time node_id node_type if_index pfc_type`  

**论文对应关系**：  
- 队列长度用来观察是否出现长期排队，验证 DCQCN + ECN 参数是否合理。  
- PFC 作为“严重拥塞”信号，用于在调参中惩罚过度拥塞情况，进入效用函数的 PFC 相关项。

### 1.4 调度时间相关参数

`third.cc` 文件开头定义了多种监控和调参周期：

- `qlen_mon_interval`, `sketch_mon_interval`, `acc_mon_interval`：控制监控频率  
- `parameter_tuning_start`, `parameter_tuning_end`, `parameter_tuning_interval`：控制参数注入的起止时间与周期  

**论文对应关系**：  
这些时间参数相当于论文中的“调参时间窗”和“采样周期”设置，决定了 PARALON 收集足够多观测值后，多久执行一次调参。

---

## 2. 调参算法（Tuning Algorithm）— 对应论文的“PARALEON 核心算法”

PARALEON 的调参逻辑主要实现在 `scratch/tuning.py` 中，包括：

- DCQCN 参数空间的定义与边界约束  
- 效用函数定义（吞吐 / 延迟 / PFC 的加权组合）  
- 流量模式识别（激进 / 保守模式）  
- 带有随机扰动和退火框架的搜索过程  

### 2.1 DCQCN 参数空间（Parameter Space）

**相关代码**：`scratch/tuning.py` 中一组数组和映射，例如：

- `time_reset, ai_rate, hai_rate, rate_to_set_on_first_cnp, rpg_min_dec_fac, ...`  
- `kmin, kmax`（ECN 阈值）  
- `DCQCN_parameter`, `DCQCN_parameter_name`, `DCQCN_name_index_mapping`  
- `parameter_min_value`, `parameter_max_value`, `parameter_step`, `default_parameters`

**论文对应关系**：  
这些就是论文中表格列出的“可调参数”以及它们的取值范围与默认值，例如：

- **`time_reset`**：控制 DCQCN 中 rate-increase 阶段的定时重置间隔  
- **`ai_rate` / `hai_rate`**：Additive Increase 的增速大小（区分不同阶段）  
- **`rate_to_set_on_first_cnp`**：首次 CNP 发生时，将当前速率乘以的因子（比如 0.5）  
- **`rpg_min_dec_fac`、`rpg_gd`**：速率减小的因子与控制 α 更新的参数  
- **`dce_tcp_g`、`initial_alpha_value`**：控制 α 更新方程中的权重和初值  
- **`kmin`、`kmax`**：交换机 ECN 阈值，对应论文中的队列标记阈值/概率

### 2.2 指标处理函数（Metrics Handling）

调参脚本需要将 `third.cc` 输出的 trace 文件转成数值特征：

- **RTT 处理：`rtt_handling2()`**  
  - 输入：`mix/rtt.tr`  
  - 输出：大小为 `[监控 NIC 数量 × 监控 NIC 数量]` 的 RTT 矩阵  
  - 将 `sip-dip` 字符串映射回 NIC 索引，并把 RTT（单位调整为 us 或 ms）填入矩阵  

- **吞吐处理：`throughput_handling2()`**  
  - 输入：`mix/switch_portrate.tr`  
  - 输出：`[监控 ToR 数量 × 监控端口数量]` 的吞吐矩阵  
  - 把 `rxBytes` 转换为 `bps`，再转成 `Gbps`，填入矩阵  

- **PFC 处理：`pfc_handling(start_time_this_round, stop_time_this_round, start_line)`**  
  - 输入：`mix/pfc.tr` 和时间窗口  
  - 输出：`node_if_pfc_count_matrix`，统计时间窗内每个 `(node, if)` 的 PFC 次数  
  - 用 `start_line` 避免从头重复读，适用于在线不断追加的 trace 文件  

**论文对应关系**：  
这一部分对应“获取每一次调参窗口内的性能指标”，即文中每次评估某一组参数时，使用某个时间窗内的 Throughput/RTT/PFC 统计量作为反馈。

### 2.3 效用函数（Utility Function）

- **关键函数**：`utility_function(throughput, rtt, pfc, throughput_weight, rtt_weight, pfc_weight)`  
- **形式**（抽象化）：

  \[
  U = w_T \cdot \frac{T}{T_0} + w_R \cdot \frac{R_0}{R} + w_P \cdot \left(1 - \frac{\text{PFC} \cdot t_{\text{pfc}}}{t_{\text{tune}}}\right)
  \]

  其中：

  - \(T\)：当前平均吞吐；\(T_0\)：基准吞吐  
  - \(R\)：当前平均 RTT；\(R_0\)：参考 RTT（越小越好，因此写成 \(R_0 / R\)）  
  - `PFC * pfc_pause_time / t_tune`：单位时间内 PFC 带来的暂停占比  

**论文对应关系**：  
这是论文中“把多目标（吞吐、时延、PFC）统一到一个效用函数”的直观实现，权重 \(w_T, w_R, w_P\) 则由流量模式决定（见下一小节）。

### 2.4 流量模式判断与权重选择（Aggressive vs. Conservative）

- **函数**：`judge_mode(large_flow_num, small_flow_num)`  
- **逻辑**：
  - 如果大流数量 \(\ge\) 小流数量：  
    - 使用“激进模式”：吞吐权重更高（`throughput_weight = 0.5`），RTT 权重较低  
  - 否则：  
    - 使用“保守模式”：RTT 权重更高（`rtt_weight = 0.5`），吞吐权重较低  

**论文对应关系**：  
这对应论文中根据工作负载类型（大流为主 / 小流为主）来切换调参目标的思想：  
- 大流为主则倾向提高吞吐，即允许略高一点 RTT；  
- 小流为主则强调延迟（如 Web 请求），对 RTT 更敏感。

### 2.5 搜索策略（Simulated Annealing + Directed Random Perturbation）

核心由三个函数构成：

- `get_new_solution_direction(parameter_mode)`：根据当前大/小流比例和模式，决定参数微调方向（正向或反向）  
- `generate_new_parameters(parameter_mode, current_solution)`：在当前解附近生成新参数向量  
- `aggressive_tuning(...)` / `conservative_tuning(...)`：套在退火框架中的迭代搜索过程  

关键要点：

- **参数扰动方向与步长**  
  - 对于不同参数，激进模式和保守模式的调整方向不同：  
    - 比如某些参数在激进模式下一般朝着“更高吞吐”的方向移动，在保守模式则朝着“更低延迟 / 更少 PFC”的方向移动  
  - 步长 = `parameter_step[parameter_index] * random.uniform(0.5, 1)`  
  - 之后应用 `parameter_min_value` / `parameter_max_value` 做裁剪  
  - 对 `rate_to_set_on_first_cnp` 和 `rpg_min_dec_fac` 等比例类参数，保持在 \([0, 1]\) 范围内  
  - 确保 `kmin <= kmax`，否则交换两者

- **退火框架**  
  - 外层：`temperature` 从 `initial_temperature` 降到 `final_temperature`  
  - 内层：每个温度下进行 `attempt_times` 次尝试  
  - 每次尝试流程：
    1. 基于当前参数，在仿真中运行一个 `t_tune` 长度的时间窗（通过等待 trace 文件的时间戳推进）  
    2. 从 trace 文件读取新的吞吐/RTT/PFC 矩阵  
    3. 计算新的效用 `new_value = U(...)`，并与 `current_value` 做比较  
    4. 按 Metropolis 准则决定是否接受新解：  
       - 如果 \(\Delta > 0\)：总是接受  
       - 否则以概率 \(\exp(\Delta / T)\) 接受  
    5. 维护全局最好解 `best_solution`  
    6. 基于当前解生成下一组候选参数 `new_solution`，写入 `mix/parameter.txt`，供 NS-3 使用  

**论文对应关系**：  
这部分直接对应论文“使用类退火的元启发式搜索，在在线环境下不断试探、评估并更新 DCQCN 参数”的实现细节。  
激进 / 保守两种模式分别实现针对不同流量模式的搜索策略。

### 2.6 参数文件输出（Parameter Output）

- **文件**：`mix/parameter.txt`  
- **写入逻辑**：在每次产生 `new_solution` 或最终 `best_solution` 时，用 `key=value` 行格式写入  

示例内容（逻辑形式）：

```text
time_reset=300
ai_rate=5
hai_rate=50
rate_to_set_on_first_cnp=0.5
...
kmin=400
kmax=1600
```

**论文对应关系**：  
`parameter.txt` 相当于论文中“PARALEON 算法输出的一组 DCQCN 和 ECN 参数”，下一阶段仿真将按这组参数运行。

---

## 3. 参数注入与协议行为（Execution）— 对应论文的“运行时参数更新”

这一层负责把 `tuning.py` 的输出真正施加到仿真的 DCQCN/ECN 算法中。

### 3.1 调参调度：`third.cc::parameter_tuning`

- **函数**：`parameter_tuning(NodeContainer *n)`  
- **流程**：
  1. 调用 `readParameterText("mix/parameter.txt")` 得到 `std::map<std::string, std::string>`  
  2. 遍历所有节点：  
     - 对于 NIC (`NodeType == 0`)：  
       - `n->Get(i)->GetObject<RdmaDriver>()->m_rdma->ChangeParameters(parameter_map);`  
     - 对于交换机 (`NodeType == 1`)：  
       - `n->Get(i)->GetObject<SwitchNode>()->ChangeECNthreshold(parameter_map);`  
  3. 如果当前时间未超过 `parameter_tuning_end`，则 `Simulator::Schedule` 下一次调用，间隔为 `parameter_tuning_interval`  

**论文对应关系**：  
这是在 NS-3 仿真内部实现的“在线热更新参数”机制。PARALEON 算法在 Python 中计算好新参数后，通过文件与这个函数协作，确保参数在仿真进行期间被更新，而不是只在仿真开始时静态设定。

### 3.2 NIC / DCQCN 参数更新：`RdmaHw::ChangeParameters`

- **文件**：`src/point-to-point/model/rdma-hw.cc`  
- **函数**：`void RdmaHw::ChangeParameters(std::map<std::string, std::string> parameter_map)`  
- **主要作用**：把 `parameter.txt` 中的键值映射到 DCQCN 内部状态变量。

关键映射关系：

- `rate_to_set_on_first_cnp` → `m_rateOnFirstCNP`  
- `rpg_min_dec_fac` → `m_min_dec_fac`  
- `time_reset` → `m_rpgTimeReset`  
- `min_time_between_cnps` → `m_rateDecreaseInterval`  
- `ai_rate` → `m_rai`（以 `Mb/s` 生成 `DataRate`）  
- `hai_rate` → `m_rhai`  
- `rpg_min_rate` → `m_minRate`  
- `rpg_gd` → `m_rpg_gd`  
- `dce_tcp_g` → `m_dce_tcp_g`

这些成员变量被下游 DCQCN 算法使用，例如：

- **α 更新：`UpdateAlphaMlx`**  
  - 使用 `m_dce_tcp_g` 控制：
    - 有 CNP 到达：\(\alpha \leftarrow \frac{g}{2^{10}} \alpha + (2^{10} - g)\)  
    - 无 CNP：\(\alpha \leftarrow \frac{g}{2^{10}} \alpha\)  
- **速率减小：`CheckRateDecreaseMlx`**  
  - 新速率大致为：  
    \[
    r_{\text{new}} = \max\left(m_{\text{minRate}}, m_{\text{min\_dec\_fac}} \cdot r, r \cdot \left(1 - \frac{\alpha}{2^{m_{\text{rpg\_gd}}}}\right)\right)
    \]
  - 其中 `m_min_dec_fac`, `m_rpg_gd`, `m_minRate` 直接来自 PARALON 调整的参数  
- **首次 CNP 时的速率调整：`cnp_received_mlx`**  
  - `q->mlx.m_targetRate = q->m_rate = m_rateOnFirstCNP * q->m_rate;`  
  - 也就是论文中的“第一次出现 CNP 时，将速率乘以某个比例”的逻辑

**论文对应关系**：  
这部分代码承载了 DCQCN 方程本身，PARALEON 调的就是这些方程中的参数。  
`ChangeParameters` 负责把外部的调参结果写入这些控制变量，从而改变 DCQCN 后续对 CNP/ECN 的反应速度和幅度。

### 3.3 交换机 ECN 阈值更新：`SwitchNode::ChangeECNthreshold`

- **文件**：`src/point-to-point/model/switch-node.cc`  
- **函数**：`void SwitchNode::ChangeECNthreshold(std::map<std::string, std::string> parameter_map)`  

主要逻辑：

- 从 `parameter_map` 中读取 `kmin`, `kmax`, `pmax`（如果配置了）  
- 对所有端口调用 `m_mmu->ConfigEcn(i, kmin, kmax, pmax)`  

配合下面的 ECN 标记逻辑：

- 在 `SwitchNode::SwitchNotifyDequeue` 中，每次出队一个包时，若 `m_ecnEnabled`，则调用 `m_mmu->ShouldSendCN(...)` 判断是否标记 ECN（或发送 CNP），其内部使用的阈值就是 `kmin`/`kmax`/`pmax`。

**论文对应关系**：  
通过调整 ECN 阈值和标记概率，PARALEON 间接影响 CNP/ECN 信号的频率，从而联动 DCQCN 算法对拥塞的感知和反应。  
结合 NIC 侧参数调节，实现论文中描述的“端到端 + 网络侧联合调优”。

---

## 4. 整体闭环与实用阅读路径

### 4.1 闭环总览

- **监测**：  
  - `third.cc` 中的 `monitor_buffer_new` / `get_pfc` 把 RTT / 吞吐 / 队列 / PFC 信息写入 `mix/*.tr`  
- **决策**：  
  - `scratch/tuning.py` 周期性解析这些 trace，计算效用函数，通过激进/保守两套策略搜索更优 DCQCN + ECN 参数，输出到 `mix/parameter.txt`  
- **执行**：  
  - `third.cc::parameter_tuning()` 读入 `mix/parameter.txt` 并调用：  
    - `RdmaHw::ChangeParameters()` 更新 NIC 上 DCQCN 参数  
    - `SwitchNode::ChangeECNthreshold()` 更新交换机 ECN 阈值  
- **协议行为**：  
  - `rdma-hw.cc` 内 DCQCN 实现（α 更新、速率增减、CNP 处理等）在新的参数下继续运行  

在仿真时间推进过程中，这个闭环会多次重复，形成论文所说的“自动且自适应”的调参过程。

### 4.2 推荐的代码阅读顺序

如果你希望进一步深入代码实现，可以按照以下顺序阅读：

1. `scratch/third.cc`  
   - 看整体拓扑构建、仿真入口 `main` 以及监控相关函数、`parameter_tuning` 调度  
2. `scratch/tuning.py`  
   - 看参数空间定义、`utility_function`、`generate_new_parameters`、`aggressive_tuning`/`conservative_tuning`  
3. `src/point-to-point/model/rdma-hw.cc`  
   - 重点看 `ChangeParameters`、`UpdateAlphaMlx`、`CheckRateDecreaseMlx`、`cnp_received_mlx` 等 DCQCN 相关函数  
4. `src/point-to-point/model/switch-node.cc`  
   - 看 `ChangeECNthreshold` 和 ECN 标记逻辑（`SwitchNotifyDequeue` 中 ECN 相关部分）  

结合论文阅读上述代码，可以较容易地把每个公式、参数和行为找到具体实现位置。


