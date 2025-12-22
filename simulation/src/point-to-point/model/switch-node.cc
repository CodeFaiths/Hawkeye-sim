#include "ns3/ipv4.h"
#include "ns3/packet.h"
#include "ns3/ipv4-header.h"
#include "ns3/pause-header.h"
#include "ns3/flow-id-tag.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "switch-node.h"
#include "qbb-net-device.h"
#include "ppp-header.h"
#include "ns3/int-header.h"
#include "ns3/log.h"
#include <cmath>

#define ENABLE_PRINT_PACKET_LOG 0

namespace ns3 {

TypeId SwitchNode::GetTypeId (void)
{
	// 定义SwitchNode的TypeId AddConstructor<SwitchNode>()：注册构造函数 AddAttribute 定义可在运行时配置的属性
  static TypeId tid = TypeId ("ns3::SwitchNode")
    .SetParent<Node> ()
    .AddConstructor<SwitchNode> ()
	.AddAttribute("EcnEnabled",
			"Enable ECN marking.",
			BooleanValue(false),
			MakeBooleanAccessor(&SwitchNode::m_ecnEnabled),
			MakeBooleanChecker())
	.AddAttribute("CcMode",
			"CC mode.",
			UintegerValue(0),
			MakeUintegerAccessor(&SwitchNode::m_ccMode),
			MakeUintegerChecker<uint32_t>())
	.AddAttribute("AckHighPrio",
			"Set high priority for ACK/NACK or not",
			UintegerValue(0),
			MakeUintegerAccessor(&SwitchNode::m_ackHighPrio),
			MakeUintegerChecker<uint32_t>())
	.AddAttribute("MaxRtt",
			"Max Rtt of the network",
			UintegerValue(9000),
			MakeUintegerAccessor(&SwitchNode::m_maxRtt),
			MakeUintegerChecker<uint32_t>())
  ;
  return tid;
}

SwitchNode::SwitchNode(){
	m_ecmpSeed = m_id;
	m_node_type = 1;
	m_mmu = CreateObject<SwitchMmu>();
	for (uint32_t i = 0; i < pCnt; i++)
		for (uint32_t j = 0; j < pCnt; j++)
			for (uint32_t k = 0; k < qCnt; k++)
				m_bytes[i][j][k] = 0;  // 初始化三维字节统计数组 m_bytes[入端口][出端口][队列]
	for (uint32_t i = 0; i < pCnt; i++)
		m_txBytes[i] = 0;  // 初始化发送字节数计数器
	for (uint32_t i = 0; i < pCnt; i++)
		m_lastPktSize[i] = m_lastPktTs[i] = 0;  // 初始化最后一个包的大小和时间戳
	for (uint32_t i = 0; i < pCnt; i++)
		m_u[i] = 0;  // 初始化端口利用率
	
	//RDMA NPA init
	for (uint32_t i = 0; i < pCnt; i++)
		for (uint32_t j = 0; j < epochNum; j++)
			for (uint32_t k = 0; k < flowEntryNum; k++)
				m_flowTelemetryData[i][j][k].flowTuple = FiveTuple{0,0,0,0,0};  // 初始化流遥测数据条目
	for (uint32_t j = 0; j < epochNum; j++)
		for (uint32_t k = 0; k < pCnt; k++){
				m_portTelemetryData[j][k].enqQdepth = 0;
				m_portTelemetryData[j][k].pfcPausedPacketNum = 0;
				m_portTelemetryData[j][k].lastTimeStep = 0;
				m_portTelemetryData[j][k].packetNum = 0;
			}
	for (uint32_t i = 0; i < pCnt; i++)
		for (uint32_t j = 0; j < pCnt; j++){
			m_portToPortBytes[i][j] = 0;
			for(uint32_t k = 0; k < portToPortSlot; k++)
				m_portToPortBytesSlot[i][j][k] = 0;
		}
	for (uint32_t i = 0; i < pCnt; i++)
		m_lastPollingEpoch[i] = 0;
	m_slotIdx = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_lastEventID[i] = 0;
}

//根据数据包和自定义头部确定输出端口（设备），使用 ECMP（等价多路径）进行负载均衡。
int SwitchNode::GetOutDev(Ptr<const Packet> p, CustomHeader &ch){
	// look up entries
	auto entry = m_rtTable.find(ch.dip); //在路由表 m_rtTable中通过目标IP（ch.dip）查找可能的输出端口（index of dev）

	// no matching entry
	if (entry == m_rtTable.end())
		return -1;

	// entry found
	auto &nexthops = entry->second;  //nexthops是一个vector，存储了可能的输出端口（index of dev）

	// pick one next hop based on hash
	union {
		uint8_t u8[4+4+2+2];
		uint32_t u32[3];
	} buf;
	buf.u32[0] = ch.sip; // 源IP地址
	buf.u32[1] = ch.dip; // 目标IP地址
	if (ch.l3Prot == 0x6)
		buf.u32[2] = ch.tcp.sport | ((uint32_t)ch.tcp.dport << 16); //TCP源端口和目标端口
	else if (ch.l3Prot == 0x11)
		buf.u32[2] = ch.udp.sport | ((uint32_t)ch.udp.dport << 16); //UDP源端口和目标端口
	else if (ch.l3Prot == 0xFC || ch.l3Prot == 0xFD)
		buf.u32[2] = ch.ack.sport | ((uint32_t)ch.ack.dport << 16); //ACK或NACK源端口和目标端口
	else if (ch.l3Prot == 0xFA)
		buf.u32[2] = ch.polling.sport | ((uint32_t)ch.polling.dport << 16); //轮询源端口和目标端口

	uint32_t idx = EcmpHash(buf.u8, 12, m_ecmpSeed) % nexthops.size(); //使用ECMP哈希函数计算输出端口索引
	return nexthops[idx];  //返回输出端口（index of dev）
}

//检查并发送暂停信号，用于暂停队列。
void SwitchNode::CheckAndSendPfc(uint32_t inDev, uint32_t qIndex){
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldPause(inDev, qIndex)){
		device->SendPfc(qIndex, 0); //发送暂停信号
		m_mmu->SetPause(inDev, qIndex); //设置内部队列暂停（已经发送PFC暂停帧，不再重复发送）
		//打印PFC发送日志
#if ENABLE_PRINT_DEBUG_LOG
		std::cout<<"Switch["<<GetId()<<"] Port["<<inDev<<"] Send PFC Pause: queue["<<qIndex<<"]"<<std::endl;
#endif
	}
}

//检查并发送恢复信号，用于恢复被暂停的队列。
void SwitchNode::CheckAndSendResume(uint32_t inDev, uint32_t qIndex){
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldResume(inDev, qIndex)){
		device->SendPfc(qIndex, 1);
		m_mmu->SetResume(inDev, qIndex);
		//std::cout<<"Switch["<<GetId()<<"] Port["<<inDev<<"] Send PFC Resume: queue["<<qIndex<<"]"<<std::endl;
	}
}

void SwitchNode::OutputTelemetry(uint32_t port, uint32_t inport, bool isSignal){
	int epoch = GetEpochIdx();
	fprintf(fp_telemetry,"epoch now\n\n");
	if(isSignal){
		fprintf(fp_telemetry,"traffic meter form port %d to port %d\n", inport, port);
		fprintf(fp_telemetry, "portToPortBytes\n");
		fprintf(fp_telemetry, "%d\n\n", m_portToPortBytes[inport][port]);
	}
	fprintf(fp_telemetry,"port telemetry data for port %d\n", port);
	fprintf(fp_telemetry, "enqQdepth pfcPausedPacketNum packetNum\n");
	fprintf(fp_telemetry, "%d ", m_portTelemetryData[epoch][port].enqQdepth);
	fprintf(fp_telemetry, "%d ", m_portTelemetryData[epoch][port].pfcPausedPacketNum);
	fprintf(fp_telemetry, "%d\n\n", m_portTelemetryData[epoch][port].packetNum);

	fprintf(fp_telemetry,"flow telemetry data for port %d\n", port);
	fprintf(fp_telemetry, "flowIdx srcIp dstIp srcPort dstPort protocol minSeq maxSeq packetNum enqQdepth pfcPausedPacketNum\n");
	for(int i = 0; i < flowEntryNum; i++){
		if(m_flowTelemetryData[port][epoch][i].flowTuple.srcIp != 0 && Simulator::Now().GetTimeStep() - m_flowTelemetryData[port][epoch][i].lastTimeStep <= epochTime * (epochNum - 1)){
			fprintf(fp_telemetry, "%d ", i);
			fprintf(fp_telemetry, "%08x ", m_flowTelemetryData[port][epoch][i].flowTuple.srcIp);
			fprintf(fp_telemetry, "%08x ", m_flowTelemetryData[port][epoch][i].flowTuple.dstIp);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].flowTuple.srcPort);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].flowTuple.dstPort);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].flowTuple.protocol);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].minSeq);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].maxSeq);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].packetNum);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].enqQdepth);
			fprintf(fp_telemetry, "%d\n", m_flowTelemetryData[port][epoch][i].pfcPausedPacketNum);
		}
	}

	epoch = (epoch + epochNum - 1) % epochNum;

	fprintf(fp_telemetry,"\nepoch last\n\n");
	fprintf(fp_telemetry,"port telemetry data for port %d\n", port);
	fprintf(fp_telemetry, "enqQdepth pfcPausedPacketNum packetNum\n");
	fprintf(fp_telemetry, "%d ", m_portTelemetryData[epoch][port].enqQdepth);
	fprintf(fp_telemetry, "%d ", m_portTelemetryData[epoch][port].pfcPausedPacketNum);
	fprintf(fp_telemetry, "%d\n\n", m_portTelemetryData[epoch][port].packetNum);

	fprintf(fp_telemetry,"flow telemetry data for port %d\n", port);
	fprintf(fp_telemetry, "flowIdx srcIp dstIp srcPort dstPort protocol minSeq maxSeq packetNum enqQdepth pfcPausedPacketNum\n");
	for(int i = 0; i < flowEntryNum; i++){
		if(m_flowTelemetryData[port][epoch][i].flowTuple.srcIp != 0 && Simulator::Now().GetTimeStep() - m_flowTelemetryData[port][epoch][i].lastTimeStep <= epochTime * epochNum){
			fprintf(fp_telemetry, "%d ", i);
			fprintf(fp_telemetry, "%08x ", m_flowTelemetryData[port][epoch][i].flowTuple.srcIp);
			fprintf(fp_telemetry, "%08x ", m_flowTelemetryData[port][epoch][i].flowTuple.dstIp);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].flowTuple.srcPort);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].flowTuple.dstPort);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].flowTuple.protocol);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].minSeq);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].maxSeq);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].packetNum);
			fprintf(fp_telemetry, "%d ", m_flowTelemetryData[port][epoch][i].enqQdepth);
			fprintf(fp_telemetry, "%d\n", m_flowTelemetryData[port][epoch][i].pfcPausedPacketNum);
		}
	}
	fprintf(fp_telemetry,"\n");
	fflush(fp_telemetry);
}

void SwitchNode::SendToDev(Ptr<Packet>p, CustomHeader &ch){
	//RDMA NPA : signal packet parse 信号包解析，追踪PFC暂停->多播发送信号给下游设备
	if (ch.l3Prot == 0xFB){
		FlowIdTag t;
		p->PeekPacketTag(t);
		uint32_t inDev = t.GetFlowId();  //获取入端口（index of dev）
		int event_id = ch.signal.eventID;  //获取事件ID

		fprintf(fp_telemetry,"time %lld\n", Simulator::Now().GetTimeStep());
		fprintf(fp_telemetry,"\nsignal\n\n");
		for (uint32_t idx = 0; idx < pCnt; idx++){  //遍历所有端口
			if(m_portToPortBytes[inDev][idx] > 0){  //如果端口到端口字节流量计数器大于0，则输出遥测数据
				OutputTelemetry(idx, inDev, true);  //输出遥测数据
				//仅在检测到 PFC 暂停时才继续传播
				//如果端口遥测数据中暂停的包数大于0，或者下一个周期中暂停的包数大于0，或者出端口队列3暂停，则判定存在PFC暂停，发送信号
				if(m_portTelemetryData[GetEpochIdx()][idx].pfcPausedPacketNum > 0 || m_portTelemetryData[(GetEpochIdx() + 1) % epochNum][idx].pfcPausedPacketNum > 0 || DynamicCast<QbbNetDevice>(m_devices[idx])->GetEgressPaused(3)){
					if(event_id > m_lastEventID[idx] + 500000 || m_lastEventID[idx] == 0){  //事件ID去重：如果事件ID大于上次事件ID加500000，或者上次事件ID为0，则发送信号
						m_lastEventID[idx] = event_id;
					}else{
						continue;
					}
					DynamicCast<QbbNetDevice>(m_devices[idx])-> SendSignal(event_id); //广播发送信号给下游设备,用于轮询
				}
			}
		}
		fprintf(fp_telemetry,"end\n\n");
		return;	
	}
	//RDMA NPA : polling packet parse 
	else if(ch.l3Prot == 0xFA){  //轮询包解析，用于流路径追踪->单播发送信号给下游设备
		FlowIdTag t;
		p->PeekPacketTag(t);
		uint32_t inDev = t.GetFlowId();
		int idx = GetOutDev(p, ch);  //利用数据包头部获取输出端口（唯一端口）
		int event_id = ch.polling.eventID;
		if(m_portTelemetryData[GetEpochIdx()][idx].pfcPausedPacketNum > 0 || m_portTelemetryData[(GetEpochIdx() + 1) % epochNum][idx].pfcPausedPacketNum > 0 || DynamicCast<QbbNetDevice>(m_devices[idx])->GetEgressPaused(3)){
			if(event_id > m_lastEventID[idx] + 500000 || m_lastEventID[idx] == 0){ // 事件ID去重：如果事件ID大于上次事件ID加500000，或者上次事件ID为0，则发送信号
				m_lastEventID[idx] = event_id;
				DynamicCast<QbbNetDevice>(m_devices[idx])-> SendSignal(event_id); // 发送信号给下游设备
			}
		}
		fprintf(fp_telemetry,"time %lld\n", Simulator::Now().GetTimeStep());
		fprintf(fp_telemetry,"\npolling\n\n");
		OutputTelemetry(idx, inDev, false); //不输出端口间流量统计，只输出端口和流的遥测数据
		fprintf(fp_telemetry,"end\n\n");
	}

	int idx = GetOutDev(p, ch);
	if (idx >= 0){
		NS_ASSERT_MSG(m_devices[idx]->IsLinkUp(), "The routing table look up should return link that is up");

		// determine the qIndex 根据数据包类型确定队列索引（优先级）
		uint32_t qIndex;
		if (ch.l3Prot == 0xFA || ch.l3Prot == 0xFF || ch.l3Prot == 0xFE || (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC))){  //QCN or PFC or NACK, go highest priority
			qIndex = 0;
		}else{
			qIndex = (ch.l3Prot == 0x06 ? 1 : ch.udp.pg); // if TCP, put to queue 1
		}

		// admission control
		FlowIdTag t;
		p->PeekPacketTag(t);
		uint32_t inDev = t.GetFlowId();
		
		// Get packet sequence number for identification
		uint32_t seq = 0;
		if (ch.l3Prot == 0x06) { // TCP
			seq = ch.tcp.seq;
		} else if (ch.l3Prot == 0x11) { // UDP
			seq = ch.udp.seq;
		}
		
		// Print forwarding path log
#if ENABLE_PRINT_PACKET_LOG
		LOG_BLUE("[Packet Forwarding]:");
		std::cout << "[Packet Forwarding] Time: " << Simulator::Now().GetNanoSeconds()
		          << "s, Switch[" << GetId() << "] forwarding packet"
		          << ", Seq: " << seq
		          << " from Port[" << inDev << "] to Port[" << idx << "]" << std::endl;
#endif
		
		if (qIndex != 0){ //not highest priority
			//入队列和出队列的接收数据包状态检查
			if (m_mmu->CheckIngressAdmission(inDev, qIndex, p->GetSize()) && m_mmu->CheckEgressAdmission(idx, qIndex, p->GetSize())){			// Admission control
				m_mmu->UpdateIngressAdmission(inDev, qIndex, p->GetSize());
				m_mmu->UpdateEgressAdmission(idx, qIndex, p->GetSize());
				
#if ENABLE_PRINT_PACKET_LOG
				// Print enqueue log after admission
				std::cout << "[Enqueue] Time: " << Simulator::Now().GetSeconds() 
				          << "s, Switch[" << GetId() << "] Port[" << inDev << "] (ingress)"
				          << ", Queue[" << qIndex << "]"
				          << ", QueueLength: " << m_mmu->ingress_queue_length[inDev][qIndex]
				          << ", QueueBytes: " << m_mmu->ingress_bytes[inDev][qIndex] << " bytes"
				          << ", Seq: " << seq << std::endl;
				
				std::cout << "[Enqueue] Time: " << Simulator::Now().GetSeconds() 
				          << "s, Switch[" << GetId() << "] Port[" << idx << "] (egress)"
				          << ", Queue[" << qIndex << "]"
				          << ", QueueLength: " << m_mmu->egress_queue_length[idx][qIndex]
				          << ", QueueBytes: " << m_mmu->egress_bytes[idx][qIndex] << " bytes"
				          << ", Seq: " << seq << std::endl;
#endif
			}else{
				return; // Drop
			}
			CheckAndSendPfc(inDev, qIndex);  //检查并发送暂停信号，用于暂停队列
		}

		// RDMA NPA
		if(qIndex != 0){
			//利用滑动窗口机制维护近几个时间槽的端口到端口字节流量统计
			//如果计算出的槽索引与当前 m_slotIdx 不同，说明时间槽已切换->需要更新端口到端口字节流量计数器
			if((Simulator::Now().GetTimeStep() / (epochTime / portToPortSlot)) % portToPortSlot != m_slotIdx){
				m_slotIdx = (Simulator::Now().GetTimeStep() / (epochTime / portToPortSlot)) % portToPortSlot;  //更新时间槽索引
				for(uint32_t inDev = 0; inDev < pCnt; inDev++){
					for(uint32_t outDev = 0; outDev < pCnt; outDev++){
						m_portToPortBytes[inDev][outDev] -= m_portToPortBytesSlot[inDev][outDev][m_slotIdx];  //从总字节数中减去即将被覆盖的旧槽数据
						m_portToPortBytesSlot[inDev][outDev][m_slotIdx] = 0; //将旧槽清零，准备写入新数据
					}
				}
			}
			m_portToPortBytesSlot[inDev][idx][m_slotIdx] += p->GetSize(); //将当前数据包大小累加到当前时间槽
			m_portToPortBytes[inDev][idx] += p->GetSize(); //将当前数据包大小添加到总字节数中

			FiveTuple fiveTuple{
				.srcIp = ch.sip,
				.dstIp = ch.dip,
				.srcPort = ch.l3Prot == 0x06 ? ch.tcp.sport : ch.udp.sport,
				.dstPort = ch.l3Prot == 0x06 ? ch.tcp.dport : ch.udp.dport,
				.protocol = (uint8_t)ch.l3Prot
			}; //五元组哈希计算流索引,唯一标识一条流
			uint32_t epochIdx = GetEpochIdx();  //当前周期索引（双缓冲，0 或 1）
			uint32_t flowIdx = FiveTupleHash(fiveTuple); //五元哈希，用于索引流条目
			auto &entry = m_flowTelemetryData[idx][epochIdx][flowIdx];  //对应端口的流遥测条目引用
			bool newEntry = Simulator::Now().GetTimeStep() - entry.lastTimeStep > epochTime * (epochNum - 1); //距离上次更新时间超过1ms,视为新条目
			if (entry.flowTuple == fiveTuple && !newEntry){  //流五元组匹配且未过期，则更新流条目
				uint32_t seq = ch.l3Prot == 0x06 ? ch.tcp.seq : ch.udp.seq;
				if(seq < entry.minSeq){
					entry.minSeq = seq; //更新最小序号，用于检测乱序和重传
				}
				if(seq > entry.maxSeq){
					entry.maxSeq = seq;
				}
				entry.packetNum++;  //包计数更新
				if(DynamicCast<QbbNetDevice>(m_devices[idx])->GetEgressPaused(qIndex)){  //出端口被PFC暂停
					entry.pfcPausedPacketNum++;  
				}else{ //累加入队时的队列深度（-1 排除当前包）->啥意思？
					entry.enqQdepth += m_mmu->egress_queue_length[idx][qIndex] - 1;
				}
				entry.lastTimeStep = Simulator::Now().GetTimeStep();
			} else{  //创建新条目
				entry.flowTuple = fiveTuple;
				entry.minSeq = entry.maxSeq = ch.l3Prot == 0x06 ? ch.tcp.seq : ch.udp.seq;
				entry.packetNum = 1;
				entry.pfcPausedPacketNum = 0;
				if(DynamicCast<QbbNetDevice>(m_devices[idx])->GetEgressPaused(qIndex)){
					entry.pfcPausedPacketNum++;
				}else{
					entry.enqQdepth = m_mmu->egress_queue_length[idx][qIndex] - 1;
				}
				entry.lastTimeStep = Simulator::Now().GetTimeStep();
			}

			auto &portEntry = m_portTelemetryData[epochIdx][idx];  //当前周期和输出端口的端口遥测条目引用
			bool newPortEntry = Simulator::Now().GetTimeStep() - portEntry.lastTimeStep > epochTime * (epochNum - 1);
			if (!newPortEntry){  //更新现有端口条目
				portEntry.enqQdepth += m_mmu->egress_queue_length[idx][qIndex] - 1;
				portEntry.packetNum++;
				if(DynamicCast<QbbNetDevice>(m_devices[idx])->GetEgressPaused(qIndex)){
					portEntry.pfcPausedPacketNum++;
				}
				portEntry.lastTimeStep = Simulator::Now().GetTimeStep();
			} else{  //初始化新端口条目
				portEntry.enqQdepth = m_mmu->egress_queue_length[idx][qIndex] - 1;
				portEntry.pfcPausedPacketNum = 0;
				portEntry.packetNum = 1;
				portEntry.lastTimeStep = Simulator::Now().GetTimeStep();
			}
		}

		m_bytes[inDev][idx][qIndex] += p->GetSize();   //更新从 inDev 到 idx 在队列 qIndex 的字节数
		m_devices[idx]->SwitchSend(qIndex, p, ch); //发送数据包到输出设备
	}else
		return; // Drop
}

uint32_t SwitchNode::EcmpHash(const uint8_t* key, size_t len, uint32_t seed) {
  uint32_t h = seed;
  if (len > 3) {
    const uint32_t* key_x4 = (const uint32_t*) key;
    size_t i = len >> 2;
    do {
      uint32_t k = *key_x4++;
      k *= 0xcc9e2d51;
      k = (k << 15) | (k >> 17);
      k *= 0x1b873593;
      h ^= k;
      h = (h << 13) | (h >> 19);
      h += (h << 2) + 0xe6546b64;
    } while (--i);
    key = (const uint8_t*) key_x4;
  }
  if (len & 3) {
    size_t i = len & 3;
    uint32_t k = 0;
    key = &key[i - 1];
    do {
      k <<= 8;
      k |= *key--;
    } while (--i);
    k *= 0xcc9e2d51;
    k = (k << 15) | (k >> 17);
    k *= 0x1b873593;
    h ^= k;
  }
  h ^= len;
  h ^= h >> 16;
  h *= 0x85ebca6b;
  h ^= h >> 13;
  h *= 0xc2b2ae35;
  h ^= h >> 16;
  return h;
}

uint32_t SwitchNode::FiveTupleHash(const FiveTuple &fiveTuple){
	return EcmpHash((const uint8_t*)&fiveTuple, sizeof(fiveTuple), flowHashSeed) % flowEntryNum;
}

uint32_t SwitchNode::GetEpochIdx(){
	return Simulator::Now().GetTimeStep() / epochTime % epochNum;
}

void SwitchNode::SetEcmpSeed(uint32_t seed){
	m_ecmpSeed = seed;
}

void SwitchNode::AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx){
	uint32_t dip = dstAddr.Get();
	m_rtTable[dip].push_back(intf_idx);
}

void SwitchNode::ClearTable(){
	m_rtTable.clear();
}

// This function can only be called in switch mode
bool SwitchNode::SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch){
	uint32_t inPort = device->GetIfIndex();
	// Get packet sequence number for identification
	uint32_t seq = 0;
	if (ch.l3Prot == 0x06) { // TCP
		seq = ch.tcp.seq;
	} else if (ch.l3Prot == 0x11) { // UDP
		seq = ch.udp.seq;
	}
	
	// Print packet arrival log
#if ENABLE_PRINT_PACKET_LOG
	LOG_GREEN("[Packet Arrival]:SwitchReceiveFromDevice");
	std::cout << "[Packet Arrival] Time: " << Simulator::Now().GetNanoSeconds()
	          << "s, Switch[" << GetId() << "] Port[" << inPort << "] received packet"
	          << ", Seq: " << seq 
	          << ", Size: " << packet->GetSize() << " bytes"
	          << ", Src: " << Ipv4Address(ch.sip) 
	          << ", Dst: " << Ipv4Address(ch.dip) << std::endl;
#endif
	
	SendToDev(packet, ch);
	return true;
}

//数据包出队
void SwitchNode::SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p){
	FlowIdTag t;
	p->PeekPacketTag(t);
	
	// Get packet sequence number for identification
	CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
	p->PeekHeader(ch);
	uint32_t seq = 0;
	if (ch.l3Prot == 0x06) { // TCP
		seq = ch.tcp.seq;
	} else if (ch.l3Prot == 0x11) { // UDP
		seq = ch.udp.seq;
	}
	
	if (qIndex != 0){
		uint32_t inDev = t.GetFlowId();
		
		// Print dequeue log before removing from admission
#if ENABLE_PRINT_PACKET_LOG
		LOG_YELLOW("[Normal Dequeue]:");
		std::cout << "[Dequeue] Time: " << Simulator::Now().GetNanoSeconds()
		          << "s, Switch[" << GetId() << "] Port[" << ifIndex << "] (egress)"
		          << ", Queue[" << qIndex << "]"
		          << ", QueueLength: " << m_mmu->egress_queue_length[ifIndex][qIndex] << std::endl;
#endif
		
		m_mmu->RemoveFromIngressAdmission(inDev, qIndex, p->GetSize());  //入端口准入控制更新:从入端口 inDev 的队列 qIndex 中移除数据包大小
		m_mmu->RemoveFromEgressAdmission(ifIndex, qIndex, p->GetSize()); //出端口准入控制更新:从出端口 ifIndex 的队列 qIndex 中移除数据包大小
		m_bytes[inDev][ifIndex][qIndex] -= p->GetSize();
		if (m_ecnEnabled){
			bool egressCongested = m_mmu->ShouldSendCN(ifIndex, qIndex);
			if (egressCongested){
				PppHeader ppp;
				Ipv4Header h;
				p->RemoveHeader(ppp);
				p->RemoveHeader(h);
				h.SetEcn((Ipv4Header::EcnType)0x03);
				p->AddHeader(h);
				p->AddHeader(ppp);
			}
		}
		//CheckAndSendPfc(inDev, qIndex);
		CheckAndSendResume(inDev, qIndex);
	} else {
		// Print dequeue log for highest priority queue (qIndex == 0)
#if ENABLE_PRINT_PACKET_LOG
		LOG_YELLOW("[High Priority Dequeue]:");
		std::cout << "[Dequeue] Time: " << Simulator::Now().GetNanoSeconds()
		          << "s, Switch[" << GetId() << "] Port[" << ifIndex << "] (egress)"
		          << ", Queue[" << qIndex << "] (highest priority)"
		          << ", Seq: " << seq << std::endl;
#endif
	}
	if (1){
		uint8_t* buf = p->GetBuffer();
		if (buf[PppHeader::GetStaticSize() + 9] == 0x11){ // udp packet
			IntHeader *ih = (IntHeader*)&buf[PppHeader::GetStaticSize() + 20 + 8 + 6]; // ppp, ip, udp, SeqTs, INT
			Ptr<QbbNetDevice> dev = DynamicCast<QbbNetDevice>(m_devices[ifIndex]);
			if (m_ccMode == 3){ // HPCC
				ih->PushHop(Simulator::Now().GetTimeStep(), m_txBytes[ifIndex], dev->GetQueue()->GetNBytesTotal(), dev->GetDataRate().GetBitRate());
			}else if (m_ccMode == 10){ // HPCC-PINT
				uint64_t t = Simulator::Now().GetTimeStep();
				uint64_t dt = t - m_lastPktTs[ifIndex];
				if (dt > m_maxRtt)
					dt = m_maxRtt;
				uint64_t B = dev->GetDataRate().GetBitRate() / 8; //Bps
				uint64_t qlen = dev->GetQueue()->GetNBytesTotal();
				double newU;

				/**************************
				 * approximate calc
				 *************************/
				int b = 20, m = 16, l = 20; // see log2apprx's paremeters
				int sft = logres_shift(b,l);
				double fct = 1<<sft; // (multiplication factor corresponding to sft)
				double log_T = log2(m_maxRtt)*fct; // log2(T)*fct
				double log_B = log2(B)*fct; // log2(B)*fct
				double log_1e9 = log2(1e9)*fct; // log2(1e9)*fct
				double qterm = 0;
				double byteTerm = 0;
				double uTerm = 0;
				if ((qlen >> 8) > 0){
					int log_dt = log2apprx(dt, b, m, l); // ~log2(dt)*fct
					int log_qlen = log2apprx(qlen >> 8, b, m, l); // ~log2(qlen / 256)*fct
					qterm = pow(2, (
								log_dt + log_qlen + log_1e9 - log_B - 2*log_T
								)/fct
							) * 256;
					// 2^((log2(dt)*fct+log2(qlen/256)*fct+log2(1e9)*fct-log2(B)*fct-2*log2(T)*fct)/fct)*256 ~= dt*qlen*1e9/(B*T^2)
				}
				if (m_lastPktSize[ifIndex] > 0){
					int byte = m_lastPktSize[ifIndex];
					int log_byte = log2apprx(byte, b, m, l);
					byteTerm = pow(2, (
								log_byte + log_1e9 - log_B - log_T
								)/fct
							);
					// 2^((log2(byte)*fct+log2(1e9)*fct-log2(B)*fct-log2(T)*fct)/fct) ~= byte*1e9 / (B*T)
				}
				if (m_maxRtt > dt && m_u[ifIndex] > 0){
					int log_T_dt = log2apprx(m_maxRtt - dt, b, m, l); // ~log2(T-dt)*fct
					int log_u = log2apprx(int(round(m_u[ifIndex] * 8192)), b, m, l); // ~log2(u*512)*fct
					uTerm = pow(2, (
								log_T_dt + log_u - log_T
								)/fct
							) / 8192;
					// 2^((log2(T-dt)*fct+log2(u*512)*fct-log2(T)*fct)/fct)/512 = (T-dt)*u/T
				}
				newU = qterm+byteTerm+uTerm;

				#if 0
				/**************************
				 * accurate calc
				 *************************/
				double weight_ewma = double(dt) / m_maxRtt;
				double u;
				if (m_lastPktSize[ifIndex] == 0)
					u = 0;
				else{
					double txRate = m_lastPktSize[ifIndex] / double(dt); // B/ns
					u = (qlen / m_maxRtt + txRate) * 1e9 / B;
				}
				newU = m_u[ifIndex] * (1 - weight_ewma) + u * weight_ewma;
				printf(" %lf\n", newU);
				#endif

				/************************
				 * update PINT header
				 ***********************/
				uint16_t power = Pint::encode_u(newU);
				if (power > ih->GetPower())
					ih->SetPower(power);

				m_u[ifIndex] = newU;
			}
		}
	}
	m_txBytes[ifIndex] += p->GetSize();
	m_lastPktSize[ifIndex] = p->GetSize();
	m_lastPktTs[ifIndex] = Simulator::Now().GetTimeStep();
}

int SwitchNode::logres_shift(int b, int l){
	static int data[] = {0,0,1,2,2,3,3,3,3,4,4,4,4,4,4,4,4,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5};
	return l - data[b];
}

int SwitchNode::log2apprx(int x, int b, int m, int l){
	int x0 = x;
	int msb = int(log2(x)) + 1;
	if (msb > m){
		x = (x >> (msb - m) << (msb - m));
		#if 0
		x += + (1 << (msb - m - 1));
		#else
		int mask = (1 << (msb-m)) - 1;
		if ((x0 & mask) > (rand() & mask))
			x += 1<<(msb-m);
		#endif
	}
	return int(log2(x) * (1<<logres_shift(b, l)));
}

} /* namespace ns3 */
