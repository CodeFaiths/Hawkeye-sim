#include <iostream>
#include <fstream>
#include "ns3/packet.h"
#include "ns3/simulator.h"
#include "ns3/object-vector.h"
#include "ns3/uinteger.h"
#include "ns3/log.h"
#include "ns3/assert.h"
#include "ns3/global-value.h"
#include "ns3/boolean.h"
#include "ns3/simulator.h"
#include "ns3/random-variable.h"
#include "switch-mmu.h"

NS_LOG_COMPONENT_DEFINE("SwitchMmu");
namespace ns3 {
	TypeId SwitchMmu::GetTypeId(void){
		static TypeId tid = TypeId("ns3::SwitchMmu")
			.SetParent<Object>()
			.AddConstructor<SwitchMmu>();
		return tid;
	}

	SwitchMmu::SwitchMmu(void){
		buffer_size = 12 * 1024 * 1024;
		reserve = 4 * 1024;
		resume_offset = 3 * 1024;

		// headroom
		shared_used_bytes = 0;
		memset(hdrm_bytes, 0, sizeof(hdrm_bytes));
		memset(ingress_bytes, 0, sizeof(ingress_bytes));
		memset(paused, 0, sizeof(paused));
		memset(egress_bytes, 0, sizeof(egress_bytes));

		memset(ingress_queue_length, 0, sizeof(ingress_queue_length));
		memset(egress_queue_length, 0, sizeof(egress_queue_length));
	}
	bool SwitchMmu::CheckIngressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize){
		//std::cout << "CheckIngressAdmission: port:" << port << " queue:" << qIndex << " size:" << psize << std::endl;
		//如果头空间不足或者共享使用的字节数超过PFC阈值，则拒绝接收数据包
		if (psize + hdrm_bytes[port][qIndex] > headroom[port] && psize + GetSharedUsed(port, qIndex) > GetPfcThreshold(port)){
			printf("%lu %u Drop: queue:%u,%u: Headroom full\n", Simulator::Now().GetTimeStep(), node_id, port, qIndex);
			for (uint32_t i = 1; i < 64; i++)
				printf("(%u,%u)", hdrm_bytes[i][3], ingress_bytes[i][3]); //打印头空间和入队列使用的字节数
			printf("\n");
			return false;
		}
		return true;
	}
	bool SwitchMmu::CheckEgressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize){
		//std::cout << "CheckEgressAdmission: port:" << port << " queue:" << qIndex << " size:" << psize << std::endl;
		return true;
	}
	void SwitchMmu::UpdateIngressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize){
		uint32_t new_bytes = ingress_bytes[port][qIndex] + psize;
		if (new_bytes <= reserve){  //如果入队列使用的字节数小于保留空间，则直接添加
			ingress_bytes[port][qIndex] += psize;
		}else {
			uint32_t thresh = GetPfcThreshold(port);  
			if (new_bytes - reserve > thresh){  //如果入队列使用的字节数大于PFC阈值，则需要添加到头空间
				hdrm_bytes[port][qIndex] += psize;
			}else {
				ingress_bytes[port][qIndex] += psize;  //如果入队列使用的字节数小于PFC阈值，则需要添加到共享使用的字节数
				shared_used_bytes += std::min(psize, new_bytes - reserve);
			}
		}

		ingress_queue_length[port][qIndex]++;  //入队列长度加1
	}
	void SwitchMmu::UpdateEgressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize){
		egress_bytes[port][qIndex] += psize;  //转入有要求，转出无限制

		egress_queue_length[port][qIndex]++;  //出队列长度加1
	}
	void SwitchMmu::RemoveFromIngressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize){
		//std::cout << "RemoveFromIngressAdmission: port:" << port << " queue:" << qIndex << " size:" << psize << std::endl;
		uint32_t from_hdrm = std::min(hdrm_bytes[port][qIndex], psize);  
		uint32_t from_shared = std::min(psize - from_hdrm, ingress_bytes[port][qIndex] > reserve ? ingress_bytes[port][qIndex] - reserve : 0);
		hdrm_bytes[port][qIndex] -= from_hdrm; //头空间中移除数据包
		ingress_bytes[port][qIndex] -= psize - from_hdrm; //入队列中移除数据包
		shared_used_bytes -= from_shared; //共享使用的字节数中移除数据包

		ingress_queue_length[port][qIndex]--;  //入队列长度减1
	}
	void SwitchMmu::RemoveFromEgressAdmission(uint32_t port, uint32_t qIndex, uint32_t psize){
		//std::cout << "RemoveFromEgressAdmission: port:" << port << " queue:" << qIndex << " size:" << psize << std::endl;
		egress_bytes[port][qIndex] -= psize;

		egress_queue_length[port][qIndex]--;
	}
	bool SwitchMmu::CheckShouldPause(uint32_t port, uint32_t qIndex){
		//如果队列未暂停且头空间或共享使用的字节数大于PFC阈值，则需要暂停队列->之后需要发送PFC暂停帧给上游设备
		return !paused[port][qIndex] && (hdrm_bytes[port][qIndex] > 0 || GetSharedUsed(port, qIndex) >= GetPfcThreshold(port));
	}
	bool SwitchMmu::CheckShouldResume(uint32_t port, uint32_t qIndex){
		if (!paused[port][qIndex]) //如果队列未暂停，则不需要恢复队列
			return false;
		uint32_t shared_used = GetSharedUsed(port, qIndex); //获取共享使用的字节数
		//如果头空间为0且共享使用的字节数为0或小于恢复偏移量，则需要恢复队列
		return hdrm_bytes[port][qIndex] == 0 && (shared_used == 0 || shared_used + resume_offset <= GetPfcThreshold(port));
	}
	void SwitchMmu::SetPause(uint32_t port, uint32_t qIndex){  //暂停队列
		paused[port][qIndex] = true;  //设置队列暂停
	}
	void SwitchMmu::SetResume(uint32_t port, uint32_t qIndex){  //恢复队列
		paused[port][qIndex] = false;  //设置队列恢复
	}

	uint32_t SwitchMmu::GetPfcThreshold(uint32_t port){  //获取PFC阈值
		//计算PFC阈值，公式为：(缓冲区大小 - 总头空间 - 总保留空间 - 共享使用的字节数) >> PFC抖动抑制比例(右移位数，相当于除以2的PFC抖动抑制比例次方)
		return (buffer_size - total_hdrm - total_rsrv - shared_used_bytes) >> pfc_a_shift[port];
	}
	uint32_t SwitchMmu::GetSharedUsed(uint32_t port, uint32_t qIndex){
		uint32_t used = ingress_bytes[port][qIndex];
		return used > reserve ? used - reserve : 0;
	}
	bool SwitchMmu::ShouldSendCN(uint32_t ifindex, uint32_t qIndex){ //检查是否应该发送ECN
		if (qIndex == 0) //如果队列索引为0，则不发送ECN
			return false;
		if (egress_bytes[ifindex][qIndex] > kmax[ifindex]) //如果出队列使用的字节数大于ECN门限，则100%发送ECN
			return true;
		if (egress_bytes[ifindex][qIndex] > kmin[ifindex]){ //如果出队列使用的字节数大于ECN门限，则根据ECN概率发送ECN
			double p = pmax[ifindex] * double(egress_bytes[ifindex][qIndex] - kmin[ifindex]) / (kmax[ifindex] - kmin[ifindex]);
			if (UniformVariable(0, 1).GetValue() < p)
				return true;
		}
		return false;
	}
	void SwitchMmu::ConfigEcn(uint32_t port, uint32_t _kmin, uint32_t _kmax, double _pmax){
		kmin[port] = _kmin * 1000; //ECN门限转换为千字节
		kmax[port] = _kmax * 1000;
		pmax[port] = _pmax;
	}
	void SwitchMmu::ConfigHdrm(uint32_t port, uint32_t size){
		headroom[port] = size; //头空间大小
	}
	void SwitchMmu::ConfigNPort(uint32_t n_port){
		total_hdrm = 0; //总头空间
		total_rsrv = 0; //总保留空间
		for (uint32_t i = 1; i <= n_port; i++){
			total_hdrm += headroom[i]; //总头空间累加
			total_rsrv += reserve; //总保留空间累加
		}
	}
	void SwitchMmu::ConfigBufferSize(uint32_t size){
		buffer_size = size; //缓冲区大小
	}
}
