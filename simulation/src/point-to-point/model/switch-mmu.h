#ifndef SWITCH_MMU_H
#define SWITCH_MMU_H

#include <unordered_map>
#include <ns3/node.h>

namespace ns3 {

class Packet;

class SwitchMmu: public Object{
public:
	static const uint32_t pCnt = 257;	// Number of ports used
	static const uint32_t qCnt = 8;	// Number of queues/priorities used

	static TypeId GetTypeId (void);

	SwitchMmu(void);

	bool CheckIngressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize);  //检查入队列是否可以接收数据包
	bool CheckEgressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize);  //检查出队列是否可以接收数据包
	void UpdateIngressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize);  //更新入队列的接收数据包状态
	void UpdateEgressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize);  //更新出队列的接收数据包状态
	void RemoveFromIngressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize);  //从入队列中移除数据包
	void RemoveFromEgressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize);  //从出队列中移除数据包

	bool CheckShouldPause(uint32_t port, uint32_t qIndex);  //检查是否应该暂停队列
	bool CheckShouldResume(uint32_t port, uint32_t qIndex);  //检查是否应该恢复队列
	void SetPause(uint32_t port, uint32_t qIndex);  //暂停队列
	void SetResume(uint32_t port, uint32_t qIndex);  //恢复队列
	//void GetPauseClasses(uint32_t port, uint32_t qIndex);
	//bool GetResumeClasses(uint32_t port, uint32_t qIndex);

	uint32_t GetPfcThreshold(uint32_t port);  //获取PFC阈值
	uint32_t GetSharedUsed(uint32_t port, uint32_t qIndex);  //获取共享使用的字节数

	bool ShouldSendCN(uint32_t ifindex, uint32_t qIndex);  //检查是否应该发送ECN

	void ConfigEcn(uint32_t port, uint32_t _kmin, uint32_t _kmax, double _pmax);  //配置ECN
	void ConfigHdrm(uint32_t port, uint32_t size);  //配置头空间(headroom)
	void ConfigNPort(uint32_t n_port);  //配置N端口
	void ConfigBufferSize(uint32_t size);  //配置缓冲区大小

	// config
	uint32_t node_id;
	uint32_t buffer_size;
	uint32_t pfc_a_shift[pCnt];  //PFC抖动抑制比例
	uint32_t reserve;
	uint32_t headroom[pCnt];  //头空间
	uint32_t resume_offset;  //恢复偏移量
	uint32_t kmin[pCnt], kmax[pCnt];  //ECN门限
	double pmax[pCnt];  //ECN概率
	uint32_t total_hdrm;  //总头空间
	uint32_t total_rsrv;  //总保留空间

	// runtime
	uint32_t shared_used_bytes;  //共享使用的字节数
	uint32_t hdrm_bytes[pCnt][qCnt];  //头空间使用的字节数
	uint32_t ingress_bytes[pCnt][qCnt];  //入队列使用的字节数
	uint32_t paused[pCnt][qCnt];  //暂停队列使用的字节数
	uint32_t egress_bytes[pCnt][qCnt];  //出队列使用的字节数

	//RDMA NPA
	uint32_t ingress_queue_length[pCnt][qCnt];  //入队列长度
	uint32_t egress_queue_length[pCnt][qCnt];  //出队列长度
};

} /* namespace ns3 */

#endif /* SWITCH_MMU_H */

