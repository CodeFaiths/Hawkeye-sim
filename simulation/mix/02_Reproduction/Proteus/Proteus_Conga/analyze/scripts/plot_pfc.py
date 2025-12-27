#!/usr/bin/env python3
"""
NS3 PFC Analysis Tool
合并了 PFC 统计分析与 Trace 关联分析功能。
1. 生成 PFC 帧计数、暂停率和实时计数图表。
2. (可选) 关联 Trace 数据分析 PFC 触发时的队列长度和链路利用率。
"""

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
from pathlib import Path
from collections import defaultdict

# --- Utilities ---

def canonical_label(lbl: str) -> str:
    """标准化端口标签格式: SW{node}-P{port} 或 H{node}-P{port}"""
    s = lbl.strip().upper()
    if not s: return s
    
    # 处理前缀
    prefix = ""
    if s.startswith("SW"):
        prefix = "SW"
        body = s[2:]
    elif s.startswith("S"):
        prefix = "SW"
        body = s[1:]
    elif s.startswith("H"):
        prefix = "H"
        body = s[1:]
    else:
        return s
        
    body = body.replace("-P", "-")
    parts = body.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{prefix}{int(parts[0])}-P{int(parts[1])}"
    return s

def parse_topology(topology_path):
    """解析拓扑文件，识别交换机节点和链路连接"""
    switch_nodes = set()
    link_map = {} # (node, port) -> (peer_node, peer_port)
    try:
        with open(topology_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        if len(lines) < 2: return switch_nodes, link_map
        
        switch_nodes = {int(x) for x in lines[1].split()}
        
        # 跟踪每个节点的当前端口号 (ns-3 默认从 1 开始，0 是 loopback)
        node_next_port = defaultdict(lambda: 1)
        
        for line in lines[2:]:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    u, v = int(parts[0]), int(parts[1])
                    u_port = node_next_port[u]
                    v_port = node_next_port[v]
                    
                    link_map[(u, u_port)] = (v, v_port)
                    link_map[(v, v_port)] = (u, u_port)
                    
                    node_next_port[u] += 1
                    node_next_port[v] += 1
                except: continue
    except Exception as e:
        print(f"Warning: Error parsing topology: {e}")
        
    return switch_nodes, link_map

def load_ingress_data(ingress_file):
    """加载 ingress_queue.txt 数据"""
    data = []
    if not ingress_file or not os.path.exists(ingress_file):
        return pd.DataFrame()
        
    current_time = 0
    try:
        with open(ingress_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                if line.startswith('time:'):
                    current_time = int(line.split(':')[1].strip())
                else:
                    parts = line.split()
                    if len(parts) >= 6:
                        data.append({
                            'time_us': current_time / 1000,
                            'node': int(parts[0]),
                            'port': int(parts[1]),
                            'ingress_kb': int(parts[2]) / 1024,
                            'egress_kb': int(parts[3]) / 1024,
                            'hdrm_kb': int(parts[4]) / 1024,
                            'paused': int(parts[5])
                        })
    except Exception as e:
        print(f"Warning: Error loading ingress data: {e}")
        
    return pd.DataFrame(data)

def build_port_label(node_id, port_id, switch_nodes):
    node_id = int(node_id)
    port_id = int(port_id)
    prefix = "SW" if node_id in switch_nodes else "H"
    return f"{prefix}{node_id}-P{port_id}"

# --- Parsing Logic ---

def load_pfc_events(pfc_file):
    """加载 PFC 事件为 DataFrame"""
    pfc_events = []
    if not os.path.exists(pfc_file):
        return pd.DataFrame()
        
    with open(pfc_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            parts = line.split()
            if len(parts) >= 5:
                try:
                    time_ns = int(parts[0])
                    node = int(parts[1])
                    node_type = int(parts[2])
                    port = int(parts[3])
                    pfc_type = int(parts[4])
                    pfc_events.append({
                        'time_ns': time_ns,
                        'time_us': time_ns / 1000,
                        'node': node,
                        'port': port,
                        'node_type': node_type,
                        'type': 'Pause' if pfc_type == 1 else 'Resume',
                        'type_code': pfc_type
                    })
                except: continue
    return pd.DataFrame(pfc_events)

# --- Aggregate Plotting (from old plot_pfc.py) ---

def plot_aggregate_pfc(df_pfc, output_dir, include_labels=None, switch_nodes=None):
    """生成 PFC 统计汇总图表"""
    if df_pfc.empty: return
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. PFC Frame Count
    df_pfc['label'] = df_pfc.apply(lambda r: build_port_label(r['node'], r['port'], switch_nodes or set()), axis=1)
    if include_labels:
        df_pfc = df_pfc[df_pfc['label'].apply(canonical_label).isin(include_labels)]
    
    if df_pfc.empty: return

    stats = df_pfc.groupby(['label', 'type']).size().unstack(fill_value=0)
    if 'Pause' not in stats: stats['Pause'] = 0
    if 'Resume' not in stats: stats['Resume'] = 0
    stats['Total'] = stats['Pause'] + stats['Resume']
    stats = stats.sort_values('Total', ascending=False)

    plt.figure(figsize=(12, 6))
    x = np.arange(len(stats))
    plt.bar(x, stats['Pause'], label='Pause', color='red', alpha=0.8)
    plt.bar(x, stats['Resume'], bottom=stats['Pause'], label='Resume', color='green', alpha=0.8)
    plt.xticks(x, stats.index, rotation=45, ha='right')
    plt.ylabel('Number of PFC Frames')
    plt.title('PFC Frame Count per Port')
    plt.legend()
    plt.grid(True, axis='y', ls=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_dir / 'pfc_frame_count.png', dpi=200)
    plt.close()

    # 2. Pause Rate over Time
    plt.figure(figsize=(12, 6))
    time_start = df_pfc['time_ns'].min()
    time_end = df_pfc['time_ns'].max()
    window_ns = 1000000 # 1ms
    bin_size_ns = 100000 # 0.1ms
    
    if time_end > time_start:
        bins = np.arange(time_start, time_end + bin_size_ns, bin_size_ns)
        for label, group in df_pfc[df_pfc['type'] == 'Pause'].groupby('label'):
            counts, _ = np.histogram(group['time_ns'], bins=bins)
            rates = counts / (window_ns / 1e9) / 1e6 # Mps
            plt.plot((bins[:-1] - time_start)/1e6, rates, label=label, alpha=0.8)
        
        plt.xlabel('Time (ms)')
        plt.ylabel('Pause Rate (Mps)')
        plt.title('PFC Pause Rate over Time')
        plt.legend(loc='upper right', ncol=2, fontsize='small')
        plt.grid(True, ls=':', alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_dir / 'pfc_pause_rate.png', dpi=200)
        plt.close()

    # 3. Real-time PFC Frame Count (Stacked Bar)
    plt.figure(figsize=(12, 6))
    bin_size_ns = 100000 # 0.1ms
    if time_end > time_start:
        bins = np.arange(time_start, time_end + bin_size_ns, bin_size_ns)
        bin_centers_ms = (bins[:-1] + bin_size_ns / 2 - time_start) / 1e6
        
        bottom = np.zeros(len(bins) - 1)
        for label, group in df_pfc.groupby('label'):
            counts, _ = np.histogram(group['time_ns'], bins=bins)
            if counts.sum() > 0:
                plt.bar(bin_centers_ms, counts, width=(bin_size_ns/1e6)*0.8, 
                        bottom=bottom, label=label, alpha=0.8)
                bottom += counts
        
        plt.xlabel("Time (ms)")
        plt.ylabel("PFC Frames per 0.1ms")
        plt.title("Real-time PFC Frame Count (Stacked)")
        plt.legend(loc='upper right', ncol=2, fontsize='small')
        plt.grid(True, axis='y', ls=':', alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_dir / 'pfc_interval_count.png', dpi=200)
        plt.close()

# --- Correlation Plotting (from old analyze_pfc.py) ---

def plot_pfc_correlation(df_pfc, trace_dir, output_dir, switch_nodes, link_map, df_ingress, include_labels=None):
    """分析 PFC 与队列长度、链路利用率的关联"""
    trace_dir = Path(trace_dir)
    if not trace_dir.exists(): return
    
    qlen_file = trace_dir / 'trace_queue_length.csv'
    util_file = trace_dir / 'trace_link_utilization.csv'
    if not qlen_file.exists() or not util_file.exists():
        print("Trace CSVs not found in trace_dir, skipping correlation analysis.")
        return

    df_qlen = pd.read_csv(qlen_file)
    df_util = pd.read_csv(util_file)
    
    corr_dir = Path(output_dir) / 'pfc'
    corr_dir.mkdir(parents=True, exist_ok=True)

    pfc_ports = df_pfc.groupby(['node', 'port']).size().index.tolist()
    
    for node, port in pfc_ports:
        label = build_port_label(node, port, switch_nodes)
        if include_labels and canonical_label(label) not in include_labels:
            continue
            
        port_pfc = df_pfc[(df_pfc['node'] == node) & (df_pfc['port'] == port)]
        port_qlen = df_qlen[(df_qlen['node'] == node) & (df_qlen['port'] == port)]
        port_util = df_util[(df_util['node'] == node) & (df_util['port'] == port)]
        
        # 查找对端端口的 Ingress 队列 (PFC 触发源)
        peer_node, peer_port = link_map.get((node, port), (None, None))
        peer_ingress = pd.DataFrame()
        if peer_node is not None and not df_ingress.empty:
            peer_ingress = df_ingress[(df_ingress['node'] == peer_node) & (df_ingress['port'] == peer_port)]
        
        if port_qlen.empty and port_util.empty and peer_ingress.empty: continue
        
        fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
        
        # 确定时间轴范围 (跳过无数据的空白期)
        all_times = []
        if not port_util.empty: all_times.extend([port_util['time_us'].min(), port_util['time_us'].max()])
        if not port_qlen.empty: all_times.extend([port_qlen['time_us'].min(), port_qlen['time_us'].max()])
        if not peer_ingress.empty: all_times.extend([peer_ingress['time_us'].min(), peer_ingress['time_us'].max()])
        if not port_pfc.empty: all_times.extend([port_pfc['time_us'].min(), port_pfc['time_us'].max()])
        if all_times:
            t_min, t_max = min(all_times), max(all_times)
            if t_max > t_min:
                axes[0].set_xlim(t_min, t_max)

        # 1. Utilization
        if not port_util.empty:
            axes[0].plot(port_util['time_us'], port_util['utilization_pct'], color='steelblue', label='Utilization')
        pauses = port_pfc[port_pfc['type'] == 'Pause']
        resumes = port_pfc[port_pfc['type'] == 'Resume']
        if not pauses.empty:
            axes[0].scatter(pauses['time_us'], [95]*len(pauses), color='red', marker='v', label='Pause')
        if not resumes.empty:
            axes[0].scatter(resumes['time_us'], [95]*len(resumes), color='green', marker='^', label='Resume')
        axes[0].set_ylabel('Util (%)')
        axes[0].set_ylim(0, 105)
        axes[0].legend(loc='upper right')
        axes[0].grid(True, ls=':')
        
        # 2. Queue Length (展示对端 Ingress 队列)
        max_val = 10
        if not peer_ingress.empty:
            axes[1].plot(peer_ingress['time_us'], peer_ingress['ingress_kb'], color='darkorange', label='Peer Ingress Q (MMU)')
            axes[1].set_ylabel('Ingress Q (KB)')
            max_val = peer_ingress['ingress_kb'].max()
        elif not port_qlen.empty:
            axes[1].plot(port_qlen['time_us'], port_qlen['qlen_kb'], color='coral', label='Local Egress Q (Trace)', alpha=0.5, ls='--')
            axes[1].set_ylabel('Egress Q (KB)')
            max_val = port_qlen['qlen_kb'].max()
        
        if not pauses.empty:
            axes[1].scatter(pauses['time_us'], [max_val*0.9]*len(pauses), color='red', marker='v')
        axes[1].legend(loc='upper right')
        axes[1].grid(True, ls=':')
        
        # 3. PFC State
        timeline = []
        state = 0
        for _, ev in port_pfc.sort_values('time_us').iterrows():
            timeline.append({'t': ev['time_us'], 's': state})
            state = ev['type_code']
            timeline.append({'t': ev['time_us'], 's': state})
        if timeline:
            tdf = pd.DataFrame(timeline)
            axes[2].step(tdf['t'], tdf['s'], where='post', color='purple')
            axes[2].fill_between(tdf['t'], 0, tdf['s'], step='post', alpha=0.2, color='purple')
        axes[2].set_yticks([0, 1])
        axes[2].set_yticklabels(['Run', 'Pause'])
        axes[2].set_xlabel('Time (us)')
        axes[2].grid(True, ls=':')
        
        peer_label = build_port_label(peer_node, peer_port, switch_nodes) if peer_node is not None else "Unknown"
        plt.suptitle(f'PFC Correlation Analysis: {label} (Triggered by {peer_label} Ingress Q)')
        plt.tight_layout()
        out_path = corr_dir / f'pfc_analysis_{label}.png'
        plt.savefig(out_path, dpi=150)
        plt.close()
        print(f"  Saved correlation plot: {out_path}")

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description='NS3 PFC Analysis Tool')
    parser.add_argument('pfc_file', nargs='?', default='output/pfc.txt', help='Path to pfc.txt')
    parser.add_argument('trace_dir', nargs='?', help='Optional: Directory with trace CSVs for correlation analysis')
    parser.add_argument('--output-dir', '-o', default='analyze/figures', help='Output directory for plots')
    parser.add_argument('--topology', help='Path to topology.txt')
    parser.add_argument('--ingress', help='Path to ingress_queue.txt')
    parser.add_argument('--include', nargs='+', help='Specific ports to analyze (e.g., SW6-P1)')
    
    args = parser.parse_args()
    
    df_pfc = load_pfc_events(args.pfc_file)
    if df_pfc.empty:
        print(f"No PFC events found in {args.pfc_file}")
        return

    switch_nodes, link_map = parse_topology(args.topology) if args.topology else (set(), {})
    include_labels = [canonical_label(l) for l in args.include] if args.include else None
    
    # 尝试自动查找 ingress_queue.txt
    ingress_file = args.ingress
    if not ingress_file:
        pfc_path = Path(args.pfc_file)
        potential_ingress = pfc_path.parent / 'ingress_queue.txt'
        if potential_ingress.exists():
            ingress_file = str(potential_ingress)
    
    df_ingress = load_ingress_data(ingress_file) if ingress_file else pd.DataFrame()
    
    print(f"Loaded {len(df_pfc)} PFC events.")
    if not df_ingress.empty:
        print(f"Loaded {len(df_ingress)} ingress queue records.")
    
    # 1. Aggregate Analysis
    plot_aggregate_pfc(df_pfc, args.output_dir, include_labels, switch_nodes)
    print(f"Aggregate plots saved to {args.output_dir}")
    
    # 2. Correlation Analysis (if trace_dir provided)
    if args.trace_dir:
        print("Running correlation analysis...")
        plot_pfc_correlation(df_pfc, args.trace_dir, args.output_dir, switch_nodes, link_map, df_ingress, include_labels)

if __name__ == '__main__':
    main()

