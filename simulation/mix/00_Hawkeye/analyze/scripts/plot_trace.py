#!/usr/bin/env python3
"""
NS3 Binary Trace Plotter
合并了解析和可视化功能，直接从trace_out.tr生成图表
"""

import struct
import sys
from collections import defaultdict
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- Parser Logic (from parse_trace.py) ---

# Event types
EVENT_RECV = 0
EVENT_ENQU = 1
EVENT_DEQU = 2
EVENT_DROP = 3

EVENT_NAMES = {
    0: "Recv",
    1: "Enqu",
    2: "Dequ",
    3: "Drop"
}

# Node types
NODE_HOST = 0
NODE_SWITCH = 1

class SimSetting:
    """仿真配置信息"""
    def __init__(self):
        self.port_speed = {}  # {node_id: {port_id: speed_bps}}
        self.win = 0

    def deserialize(self, file):
        """从文件读取SimSetting"""
        data = file.read(4)
        if len(data) < 4:
            return False
        length = struct.unpack('<I', data)[0]
        
        for _ in range(length):
            data = file.read(2 + 1 + 8)  # node(2) + intf(1) + bps(8)
            if len(data) < 11:
                return False
            node, intf, bps = struct.unpack('<HBQ', data)
            if node not in self.port_speed:
                self.port_speed[node] = {}
            self.port_speed[node][intf] = bps
        
        data = file.read(4)
        if len(data) < 4:
            return False
        self.win = struct.unpack('<I', data)[0]
        return True

class TraceRecord:
    """单条trace记录"""
    STRUCT_FORMAT = '<QHBBIIIHBBBBxx'  # 前32字节
    STRUCT_SIZE = 56
    
    def __init__(self):
        self.time = 0
        self.node = 0
        self.intf = 0
        self.qidx = 0
        self.qlen = 0
        self.sip = 0
        self.dip = 0
        self.size = 0
        self.l3Prot = 0
        self.event = 0
        self.ecn = 0
        self.nodeType = 0
        self.sport = 0
        self.dport = 0
        self.seq = 0
        self.ts = 0
        self.pg = 0
        self.payload = 0
    
    def deserialize(self, file):
        data = file.read(self.STRUCT_SIZE)
        if len(data) < self.STRUCT_SIZE:
            return False
        
        (self.time, self.node, self.intf, self.qidx, 
         self.qlen, self.sip, self.dip, self.size,
         self.l3Prot, self.event, self.ecn, self.nodeType) = struct.unpack(
            self.STRUCT_FORMAT, data[:32])
        
        union_data = data[32:56]
        if len(union_data) >= 20:
            (self.sport, self.dport, self.seq, self.ts, 
             self.pg, self.payload) = struct.unpack('<HHIQHH', union_data[:20])
        
        return True

class TraceAnalyzer:
    """Trace文件分析器"""
    def __init__(self, trace_file):
        self.trace_file = Path(trace_file)
        self.sim_setting = SimSetting()
        self.records = []
        self.port_stats = defaultdict(lambda: {
            'tx_bytes': [],
            'rx_bytes': [],
            'queue_len': [],
            'enqueue_events': [],
            'dequeue_events': [],
            'drop_events': []
        })
        
    def parse(self):
        print(f"Parsing trace file: {self.trace_file}")
        with open(self.trace_file, 'rb') as f:
            if not self.sim_setting.deserialize(f):
                print("Warning: Failed to read SimSetting")
            
            count = 0
            while True:
                record = TraceRecord()
                if not record.deserialize(f):
                    break
                self.records.append(record)
                count += 1
                if count % 50000 == 0:
                    print(f"  Parsed {count} records...", end='\r')
            print(f"\nTotal records parsed: {count}")
    
    def analyze(self):
        print("Analyzing trace data...")
        tx_cumulative = defaultdict(lambda: defaultdict(int))
        rx_cumulative = defaultdict(lambda: defaultdict(int))
        
        for rec in self.records:
            port_key = (rec.node, rec.intf)
            stats = self.port_stats[port_key]
            stats['queue_len'].append((rec.time, rec.qlen))
            
            if rec.event == EVENT_ENQU:
                stats['enqueue_events'].append((rec.time, rec.size))
            elif rec.event == EVENT_DEQU:
                stats['dequeue_events'].append((rec.time, rec.size))
                tx_cumulative[rec.node][rec.intf] += rec.size
                stats['tx_bytes'].append((rec.time, tx_cumulative[rec.node][rec.intf]))
            elif rec.event == EVENT_RECV:
                rx_cumulative[rec.node][rec.intf] += rec.size
                stats['rx_bytes'].append((rec.time, rx_cumulative[rec.node][rec.intf]))
            elif rec.event == EVENT_DROP:
                stats['drop_events'].append((rec.time, rec.size))

    def get_utilization_df(self):
        rows = []
        for port_key, stats in self.port_stats.items():
            node, intf = port_key
            if not stats['tx_bytes'] or len(stats['tx_bytes']) < 2:
                continue
            
            port_speed = self.sim_setting.port_speed.get(node, {}).get(intf, 0)
            if port_speed == 0: continue
            
            tx_series = stats['tx_bytes']
            for i in range(1, len(tx_series)):
                t1, b1 = tx_series[i-1]
                t2, b2 = tx_series[i]
                if t2 == t1: continue
                tp = (b2 - b1) * 8 / (t2 - t1)
                util = (tp * 1e9 / port_speed) * 100
                rows.append({
                    'time_us': t2 / 1000,
                    'node': node,
                    'port': intf,
                    'throughput_gbps': tp,
                    'utilization_pct': min(util, 100.0)
                })
        return pd.DataFrame(rows)

    def get_qlen_df(self):
        rows = []
        for port_key, stats in self.port_stats.items():
            node, intf = port_key
            for t, qlen in stats['queue_len']:
                rows.append({
                    'time_us': t / 1000,
                    'node': node,
                    'port': intf,
                    'qlen_kb': qlen / 1000
                })
        return pd.DataFrame(rows)

# --- Visualization Logic (from visualize_trace.py) ---

def canonical_label(lbl: str) -> str:
    s = lbl.strip().upper()
    if not s: return s
    if s.startswith("H"):
        body = s[1:].replace("-P", "-")
        parts = body.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"H{int(parts[0])}-P{int(parts[1])}"
    elif s.startswith("SW") or s.startswith("S"):
        prefix = "SW" if s.startswith("SW") else "S"
        body = s[len(prefix):].replace("-P", "-")
        parts = body.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"SW{int(parts[0])}-P{int(parts[1])}"
    return s

def parse_topology(topology_path):
    try:
        with open(topology_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        if len(lines) < 2: return set()
        # 第二行是交换机节点ID列表
        return {int(x) for x in lines[1].split()}
    except Exception as e:
        print(f"Warning: Could not parse topology {topology_path}: {e}")
        return set()

def build_port_label(node_id, port_id, switch_nodes):
    node_id = int(node_id)
    port_id = int(port_id)
    prefix = "SW" if node_id in switch_nodes else "H"
    return f"{prefix}{node_id}-P{port_id}"

def plot_results(df_util, df_qlen, output_dir, switch_nodes, include_labels=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Link Utilization
    if not df_util.empty:
        df_util['label'] = df_util.apply(lambda r: build_port_label(r['node'], r['port'], switch_nodes), axis=1)
        if include_labels:
            df_util = df_util[df_util['label'].isin(include_labels)]
        
        if not df_util.empty:
            fig, axes = plt.subplots(2, 1, figsize=(12, 8))
            for label, group in df_util.groupby('label'):
                # 对吞吐量和利用率进行平滑处理，避免瞬时波动导致图表出现“方块”状
                # 使用滑动平均 (Rolling Mean)，窗口大小设为 50 个采样点
                window_size = min(50, len(group))
                if window_size > 1:
                    smooth_tp = group['throughput_gbps'].rolling(window=window_size, center=True, min_periods=1).mean()
                    smooth_util = group['utilization_pct'].rolling(window=window_size, center=True, min_periods=1).mean()
                else:
                    smooth_tp = group['throughput_gbps']
                    smooth_util = group['utilization_pct']

                axes[0].plot(group['time_us'], smooth_tp, label=label, alpha=0.8)
                axes[1].plot(group['time_us'], smooth_util, label=label, alpha=0.8)
            
            axes[0].set_ylabel('Throughput (Gbps)')
            axes[0].set_title('Link Throughput (from Trace, Smoothed)')
            axes[0].legend(loc='upper right', fontsize='small', ncol=2)
            axes[0].grid(True, ls=':')
            
            axes[1].set_ylabel('Utilization (%)')
            axes[1].set_xlabel('Time (us)')
            axes[1].set_ylim(0, 105)
            axes[1].set_title('Link Utilization (from Trace, Smoothed)')
            axes[1].grid(True, ls=':')
            
            plt.tight_layout()
            plt.savefig(output_dir / 'trace_link_utilization.png', dpi=200)
            plt.close()

    # 2. Queue Length
    if not df_qlen.empty:
        df_qlen['label'] = df_qlen.apply(lambda r: build_port_label(r['node'], r['port'], switch_nodes), axis=1)
        if include_labels:
            df_qlen = df_qlen[df_qlen['label'].isin(include_labels)]
            
        if not df_qlen.empty:
            plt.figure(figsize=(12, 5))
            for label, group in df_qlen.groupby('label'):
                plt.plot(group['time_us'], group['qlen_kb'], label=label, alpha=0.8)
            plt.title('Queue Length (from Trace)')
            plt.ylabel('Queue Length (KB)')
            plt.xlabel('Time (us)')
            plt.legend(loc='upper right', fontsize='small', ncol=2)
            plt.grid(True, ls=':')
            plt.tight_layout()
            plt.savefig(output_dir / 'trace_queue_length.png', dpi=200)
            plt.close()

def main():
    parser = argparse.ArgumentParser(description='Plot NS3 trace results')
    parser.add_argument('trace_file', help='Path to trace_out.tr')
    parser.add_argument('--output-dir', '-o', default='analyze/figures', help='Output directory for plots')
    parser.add_argument('--csv-dir', help='Optional: Output directory for CSV files')
    parser.add_argument('--topology', help='Path to topology.txt to identify switches')
    parser.add_argument('--include', nargs='+', help='Specific ports to plot (e.g., SW6-P1 H0-P1)')
    
    args = parser.parse_args()
    
    analyzer = TraceAnalyzer(args.trace_file)
    analyzer.parse()
    analyzer.analyze()
    
    df_util = analyzer.get_utilization_df()
    df_qlen = analyzer.get_qlen_df()
    
    if args.csv_dir:
        csv_path = Path(args.csv_dir)
        csv_path.mkdir(parents=True, exist_ok=True)
        df_util.to_csv(csv_path / 'trace_link_utilization.csv', index=False)
        df_qlen.to_csv(csv_path / 'trace_queue_length.csv', index=False)
        print(f"CSVs saved to {args.csv_dir}")

    switch_nodes = parse_topology(args.topology) if args.topology else set()
    include_labels = [canonical_label(l) for l in args.include] if args.include else None
    
    plot_results(df_util, df_qlen, args.output_dir, switch_nodes, include_labels)
    print(f"Plots saved to {args.output_dir}")

if __name__ == '__main__':
    main()
