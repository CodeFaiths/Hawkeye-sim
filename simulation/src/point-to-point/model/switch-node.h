#ifndef SWITCH_NODE_H
#define SWITCH_NODE_H

#include <unordered_map>
#include <ns3/node.h>
#include "qbb-net-device.h"
#include "switch-mmu.h"
#include "pint.h"

namespace ns3 {

class Packet;

class SwitchNode : public Node{
	static const uint32_t pCnt = 257;	// Number of ports used 端口数
	static const uint32_t qCnt = 8;	// Number of queues/priorities used 队列数
	uint32_t m_ecmpSeed; // ECMP种子
	std::unordered_map<uint32_t, std::vector<int> > m_rtTable; // map from ip address (u32) to possible ECMP port (index of dev)

	// monitor of PFC
	uint32_t m_bytes[pCnt][pCnt][qCnt]; // m_bytes[inDev][outDev][qidx] is the bytes from inDev enqueued for outDev at qidx
	
	uint64_t m_txBytes[pCnt]; // counter of tx bytes 发送字节数计数器

	uint32_t m_lastPktSize[pCnt]; // 最后一个包的大小
	uint64_t m_lastPktTs[pCnt]; // ns 最后一个包的时间戳
	double m_u[pCnt]; // 端口利用率

	// RDMA NPA 网络性能分析
	static const uint32_t flowHashSeed = 0x233;	// Seed for flow hash 流哈希种子
	static const uint32_t flowEntryNum = (1 << 12);	// Number of flowTelemetryData entries 流遥测数据条目数
	static const uint32_t epochNum = 2;	// 周期数
	static const uint32_t portToPortSlot = 5;	// port to port bytes slot 端口到端口字节槽
	uint64_t m_lastSignalEpoch;	// last signal time 最后一个信号时间
	uint32_t m_slotIdx;	// current epoch index 当前周期索引
	uint64_t m_lastPollingEpoch[pCnt];	// last polling epoch 最后一个轮询周期
	uint32_t m_lastEventID[pCnt];	// last event ID 最后一个事件ID
	struct FiveTuple{
		uint32_t srcIp;
		uint32_t dstIp;
		uint16_t srcPort;
		uint16_t dstPort;
		uint8_t protocol;
		bool operator==(const FiveTuple &other) const{
			return srcIp == other.srcIp
				&& dstIp == other.dstIp 
				&& srcPort == other.srcPort 
				&& dstPort == other.dstPort 
				&& protocol == other.protocol;
		}
	};
	
	struct FlowTelemetryData{
		uint16_t minSeq;           // 16-bit min_seq
		uint16_t maxSeq;           // 16-bit max_seq
		uint32_t packetNum;		// 32-bit packet_num
		uint32_t enqQdepth;		// 32-bit enq_q_depth
		uint32_t pfcPausedPacketNum;	// 32-bit pfc_paused_packet_num

		FiveTuple flowTuple;			// 5-tuple
		uint64_t lastTimeStep;		// last timestep
	};
	struct PortTelemetryData{
		uint32_t enqQdepth;		// 32-bit enq_q_depth
		uint32_t pfcPausedPacketNum;
		uint32_t packetNum;		// 32-bit packet_num

		uint32_t lastTimeStep;		// last timestep >> 5
	};
	FlowTelemetryData m_flowTelemetryData[pCnt][epochNum][flowEntryNum]; // flow telemetry data 端口 周期 流条目
	PortTelemetryData m_portTelemetryData[epochNum][pCnt]; // port telemetry data 周期 端口条目
	uint32_t m_portToPortBytes[pCnt][pCnt]; // bytes from port to port 端口到端口字节
	uint32_t m_portToPortBytesSlot[pCnt][pCnt][portToPortSlot]; // port to port bytes slot 端口到端口字节槽

protected:
	bool m_ecnEnabled;
	uint32_t m_ccMode;
	uint64_t m_maxRtt;

	uint32_t m_ackHighPrio; // set high priority for ACK/NACK

private:
	int GetOutDev(Ptr<const Packet>, CustomHeader &ch); // 获取输出设备（端口）
	void SendToDev(Ptr<Packet>p, CustomHeader &ch); // 发送数据包到设备
	static uint32_t EcmpHash(const uint8_t* key, size_t len, uint32_t seed);
	void CheckAndSendPfc(uint32_t inDev, uint32_t qIndex);
	void CheckAndSendResume(uint32_t inDev, uint32_t qIndex);
	// RDMA NPA
	static uint32_t FiveTupleHash(const FiveTuple &fiveTuple);
	uint32_t GetEpochIdx();
	void OutputTelemetry(uint32_t port, uint32_t inport, bool isSignal);

public:
	Ptr<SwitchMmu> m_mmu;

	static TypeId GetTypeId (void);
	SwitchNode();
	void SetEcmpSeed(uint32_t seed);
	void AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx); //添加路由表条目
	void ClearTable();
	bool SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch);
	void SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p);

	// for approximate calc in PINT
	int logres_shift(int b, int l);
	int log2apprx(int x, int b, int m, int l); // given x of at most b bits, use most significant m bits of x, calc the result in l bits

	// for RDMA NPA detect
	FILE *fp_telemetry = NULL;
	uint32_t epochTime = 1000000;
};

} /* namespace ns3 */

#endif /* SWITCH_NODE_H */
