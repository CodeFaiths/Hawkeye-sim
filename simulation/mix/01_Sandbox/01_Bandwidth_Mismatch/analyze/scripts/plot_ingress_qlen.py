#!/usr/bin/env python3
"""
Visualize Ingress Queue Data for PFC Analysis
分析交换机MMU的入队队列长度，用于理解PFC触发机制
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import sys
import os
from pathlib import Path

def parse_ingress_file(filepath):
    """解析ingress_queue.txt文件"""
    data = []
    current_time = 0
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            if line.startswith('time:'):
                current_time = int(line.split(':')[1].strip())
            else:
                parts = line.split()
                if len(parts) >= 6:
                    data.append({
                        'time_ns': current_time,
                        'switch_id': int(parts[0]),
                        'port_id': int(parts[1]),
                        'ingress_bytes': int(parts[2]),
                        'egress_bytes': int(parts[3]),
                        'hdrm_bytes': int(parts[4]),
                        'paused': int(parts[5])
                    })
    
    return pd.DataFrame(data)

def load_topology(topo_file):
    """加载拓扑文件获取节点信息"""
    node_names = {}
    try:
        with open(topo_file, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        if len(lines) < 2: return node_names
        
        first_line = lines[0].split()
        node_num = int(first_line[0])
        
        # 第二行是交换机节点ID列表
        switch_nodes = {int(x) for x in lines[1].split()}
        
        for i in range(node_num):
            if i in switch_nodes:
                node_names[i] = f'SW{i}'
            else:
                node_names[i] = f'H{i}'
    except Exception as e:
        print(f"Warning: Error loading topology: {e}")
    return node_names

def plot_ingress_analysis(df, output_dir, node_names=None):
    """生成ingress队列分析图"""
    
    if df.empty:
        print("No data to plot")
        return
    
    # 转换时间为微秒
    df['time_us'] = df['time_ns'] / 1000
    
    # 获取所有交换机和端口
    switches = df['switch_id'].unique()
    
    for sw in switches:
        sw_data = df[df['switch_id'] == sw]
        ports = sorted(sw_data['port_id'].unique())
        
        sw_name = node_names.get(sw, f'SW{sw}') if node_names else f'SW{sw}'
        
        # 创建图表
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True)
        
        colors = plt.cm.tab10(np.linspace(0, 1, len(ports)))
        
        # 图1: Ingress Queue (入队队列 - PFC触发依据)
        ax1 = axes[0]
        for i, port in enumerate(ports):
            port_data = sw_data[sw_data['port_id'] == port]
            if port_data['ingress_bytes'].max() > 0:
                ax1.plot(port_data['time_us'], port_data['ingress_bytes']/1024, 
                        label=f'P{port}', color=colors[i], linewidth=1)
        
        ax1.set_ylabel('Ingress Queue (KB)', fontsize=11)
        ax1.set_title(f'{sw_name} - Ingress Queue (PFC Trigger Basis: ingress_bytes)', fontsize=12)
        ax1.legend(loc='upper right', ncol=3)
        ax1.grid(True, alpha=0.3)
        
        # 设置时间轴范围 (跳过无数据的空白期)
        t_min, t_max = sw_data['time_us'].min(), sw_data['time_us'].max()
        if t_max > t_min:
            ax1.set_xlim(t_min, t_max)
        
        # 图2: Egress Queue (出队队列)
        ax2 = axes[1]
        for i, port in enumerate(ports):
            port_data = sw_data[sw_data['port_id'] == port]
            if port_data['egress_bytes'].max() > 0:
                ax2.plot(port_data['time_us'], port_data['egress_bytes']/1024, 
                        label=f'P{port}', color=colors[i], linewidth=1)
        
        ax2.set_ylabel('Egress Queue (KB)', fontsize=11)
        ax2.set_title(f'{sw_name} - Egress Queue', fontsize=12)
        ax2.legend(loc='upper right', ncol=3)
        ax2.grid(True, alpha=0.3)
        
        # 图3: Ingress vs Egress 对比 (总和)
        ax3 = axes[2]
        
        # 按时间聚合所有端口的ingress和egress
        time_groups = sw_data.groupby('time_us').agg({
            'ingress_bytes': 'sum',
            'egress_bytes': 'sum',
            'paused': 'max'
        }).reset_index()
        
        ax3.fill_between(time_groups['time_us'], 0, time_groups['ingress_bytes']/1024,
                        alpha=0.5, label='Total Ingress', color='blue')
        ax3.fill_between(time_groups['time_us'], 0, time_groups['egress_bytes']/1024,
                        alpha=0.5, label='Total Egress', color='red')
        
        # 标记PFC暂停时刻 (使用浅绿色阴影表示暂停状态)
        max_q = max(time_groups['ingress_bytes'].max(), time_groups['egress_bytes'].max()) / 1024
        ax3.fill_between(time_groups['time_us'], 0, max_q * 1.1, 
                        where=(time_groups['paused'] == 1),
                        color='green', alpha=0.15, label='PFC Paused')
        
        ax3.set_xlabel('Time (μs)', fontsize=11)
        ax3.set_ylabel('Queue Size (KB)', fontsize=11)
        ax3.set_title(f'{sw_name} - Total Ingress vs Egress Queue', fontsize=12)
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        output_file = os.path.join(output_dir, f'{sw_name}_ingress_analysis.png')
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved: {output_file}")
        
        # 生成统计报告
        print(f"\n=== {sw_name} Queue Statistics ===")
        print(f"{'Port':<6} {'Type':<10} {'Max(KB)':<12} {'Avg(KB)':<12} {'Paused':<8}")
        print("-" * 50)
        for port in ports:
            port_data = sw_data[sw_data['port_id'] == port]
            ing_max = port_data['ingress_bytes'].max() / 1024
            ing_avg = port_data['ingress_bytes'].mean() / 1024
            egr_max = port_data['egress_bytes'].max() / 1024
            egr_avg = port_data['egress_bytes'].mean() / 1024
            paused = port_data['paused'].max()
            
            if ing_max > 0:
                print(f"P{port:<5} {'Ingress':<10} {ing_max:<12.1f} {ing_avg:<12.1f} {paused}")
            if egr_max > 0:
                print(f"P{port:<5} {'Egress':<10} {egr_max:<12.1f} {egr_avg:<12.1f} {paused}")


def canonical_label(lbl: str) -> str:
    """Normalize user-specified labels to the script's canonical format."""
    s = lbl.strip().upper()
    if not s:
        return s
    
    # 处理 SW{node}-P{port} 或 SW{node}-{port}
    if s.startswith("SW"):
        body = s[2:]
        body = body.replace("-P", "-")
        parts = body.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"SW{int(parts[0])}-P{int(parts[1])}"
        return s
    
    # 处理 S{node}-P{port} 或 S{node}-{port}
    if s.startswith("S"):
        body = s[1:]
        body = body.replace("-P", "-")
        parts = body.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"SW{int(parts[0])}-P{int(parts[1])}"
        return s
    
    return s


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Visualize ingress queue data for PFC analysis')
    parser.add_argument('ingress_file', nargs='?', help='Ingress queue file path')
    parser.add_argument('output_dir', nargs='?', help='Output directory for figures')
    parser.add_argument('--topology', help='Path to topology file')
    parser.add_argument('--include', nargs='*', help='Filter by port labels (e.g., SW6-P1 SW6-P6)')
    
    args = parser.parse_args()
    
    # 默认路径
    base_dir = Path(__file__).parent.parent.parent
    ingress_file = Path(args.ingress_file) if args.ingress_file else base_dir / 'output' / 'ingress_queue.txt'
    topo_file = Path(args.topology) if args.topology else base_dir / 'config' / 'topo_incast_5to1.txt'
    output_dir = Path(args.output_dir) if args.output_dir else base_dir / 'analyze' / 'figures'
    
    # 解析端口过滤参数
    include_ports = None
    if args.include:
        include_ports = set()
        for lbl in args.include:
            normalized = canonical_label(lbl)
            # 提取端口号 (SW6-P1 -> 1)
            if '-P' in normalized:
                port = int(normalized.split('-P')[1])
                include_ports.add(port)
        print(f"Filtering ports: {sorted(include_ports)}")
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Reading: {ingress_file}")
    
    # 加载数据
    df = parse_ingress_file(ingress_file)
    node_names = load_topology(topo_file)
    
    if df.empty:
        print("No data found in ingress file")
        return
    
    # 按端口过滤
    if include_ports:
        df = df[df['port_id'].isin(include_ports)]
    
    print(f"Loaded {len(df)} records")
    print(f"Time range: {df['time_ns'].min()/1e6:.3f} - {df['time_ns'].max()/1e6:.3f} ms")
    
    # 生成可视化
    plot_ingress_analysis(df, str(output_dir), node_names)
    
    print(f"\nFigures saved to: {output_dir}")

if __name__ == '__main__':
    main()
