import os
import matplotlib.pyplot as plt
import numpy as np
import argparse
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Updated paths for the new directory structure
PFC_FILE = os.path.join(BASE_DIR, "..", "..", "output", "pfc.txt")
OUT_DIR = os.path.join(BASE_DIR, "..", "figures")
OUT_PNG1 = os.path.join(OUT_DIR, "pfc_frame_count.png")
OUT_PNG2 = os.path.join(OUT_DIR, "pfc_pause_rate.png")
OUT_PNG3 = os.path.join(OUT_DIR, "pfc_interval_count.png")

# Ensure output directory exists
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)

# Time window for calculating pause rate (in nanoseconds)
# 1ms window
TIME_WINDOW_NS = 1000000  # 1ms = 1,000,000 ns


def parse_pfc(file_path):
    """
    Parse PFC file format: time_ns node_id node_type port_id pause_flag
    node_type: 0 = host, 1 = switch
    pause_flag: 1 = pause, 0 = resume
    Returns: dict mapping (node_id, port_id) -> {'pause': [times], 'resume': [times]}
    """
    pfc_events = defaultdict(lambda: {'pause': [], 'resume': []})
    
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split()
            if len(parts) < 5:
                continue
            
            try:
                time_ns = int(parts[0])
                node_id = int(parts[1])
                node_type = int(parts[2])  # 0 = host, 1 = switch
                port_id = int(parts[3])
                pause_flag = int(parts[4])
                
                key = (node_id, port_id, node_type)
                if pause_flag == 1:
                    pfc_events[key]['pause'].append(time_ns)
                else:  # pause_flag == 0
                    pfc_events[key]['resume'].append(time_ns)
            except (ValueError, IndexError):
                continue
    
    return pfc_events


def calculate_pause_rate(pause_events, time_start_ns, time_end_ns, time_window_ns):
    """
    Calculate pause rate (Mps - Million per second) over time using sliding window.
    Returns: (time_points_ms, pause_rates_mps)
    """
    # Create time bins (every 0.1ms = 100,000 ns)
    bin_size_ns = 100000  # 0.1ms
    time_bins = np.arange(time_start_ns, time_end_ns + bin_size_ns, bin_size_ns)
    pause_rates = []
    
    for bin_end in time_bins[1:]:
        bin_start = bin_end - time_window_ns
        if bin_start < time_start_ns:
            bin_start = time_start_ns
        
        # Count pause events in this window
        pause_count = sum(1 for event_time in pause_events 
                          if bin_start <= event_time < bin_end)
        
        # Calculate rate in Mps (Million per second)
        window_duration_s = time_window_ns / 1e9
        pause_rate_mps = pause_count / window_duration_s / 1e6
        
        pause_rates.append(pause_rate_mps)
    
    # Convert time to milliseconds
    time_points_ms = time_bins[1:] / 1e6
    
    return time_points_ms, pause_rates


def main():
    parser = argparse.ArgumentParser(description="Plot PFC events and pause rates.")
    parser.add_argument("--include", nargs="*", help=(
        "Optional list of port labels to keep (supports H and S/SW prefixes), e.g. H8-1 S10-3 SW10-3."
    ))
    args = parser.parse_args()

    def canonical_label(lbl: str) -> str:
        """Normalize user-specified labels to the script's canonical format.

        - Hosts: always H{node}-{port}
        - Switches: accept S{node}-{port} or SW{node}-{port}, normalize to SW{node}-{port}
        """
        s = lbl.strip().upper()
        if not s:
            return s
        if s.startswith("H"):
            body = s[1:]
            parts = body.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"H{int(parts[0])}-{int(parts[1])}"
            return s
        if s.startswith("SW"):
            body = s[2:]
            parts = body.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"SW{int(parts[0])}-{int(parts[1])}"
            return s
        if s.startswith("S"):
            body = s[1:]
            parts = body.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return f"SW{int(parts[0])}-{int(parts[1])}"
            return s
        return s

    if not os.path.exists(PFC_FILE):
        print("PFC file not found: {}".format(PFC_FILE))
        return
    
    # Parse PFC events
    pfc_events = parse_pfc(PFC_FILE)
    
    if not pfc_events:
        print("No PFC events found!")
        return
    
    include_labels = set(canonical_label(x) for x in args.include) if args.include else None
    
    # Prepare data for first plot: frame count by port
    port_data_list = []
    
    for node_id, port_id, node_type in pfc_events.keys():
        # Create label: H{node_id}-{port_id} for hosts, SW{node_id}-{port_id} for switches
        if node_type == 0:  # host
            label = "H{}-{}".format(node_id, port_id)
        else:  # switch
            label = "SW{}-{}".format(node_id, port_id)
        # Filter by normalized labels if provided
        if include_labels and canonical_label(label) not in include_labels:
            continue
            
        pause_count = len(pfc_events[(node_id, port_id, node_type)]['pause'])
        resume_count = len(pfc_events[(node_id, port_id, node_type)]['resume'])
        total_count = pause_count + resume_count
        
        port_data_list.append({
            'label': label,
            'pause': pause_count,
            'resume': resume_count,
            'total': total_count,
            'node_id': node_id,
            'port_id': port_id,
            'node_type': node_type
        })
    
    # Sort by total count (descending) for better visualization
    port_data_list.sort(key=lambda x: x['total'], reverse=True)
    
    port_labels = [item['label'] for item in port_data_list]
    pause_counts = [item['pause'] for item in port_data_list]
    resume_counts = [item['resume'] for item in port_data_list]
    
    # Plot 1: Stacked bar chart for PFC frame count
    plt.figure(figsize=(14, 8))
    x_pos = np.arange(len(port_labels))
    width = 0.6
    
    # Create stacked bars
    bars1 = plt.bar(x_pos, pause_counts, width, label='Pause', color='red', alpha=0.8)
    bars2 = plt.bar(x_pos, resume_counts, width, bottom=pause_counts, label='Resume', color='green', alpha=0.8)
    
    plt.xlabel('Port', fontsize=12)
    plt.ylabel('Number of PFC Frames', fontsize=12)
    plt.title('Number of PFC Frames', fontsize=14)
    plt.xticks(x_pos, port_labels, rotation=45, ha='right')
    plt.legend(fontsize=10, title='PFC Type')
    plt.grid(True, axis='y', linestyle=':', linewidth=0.5, alpha=0.7)
    plt.tight_layout()
    
    plt.savefig(OUT_PNG1, dpi=200, bbox_inches='tight')
    print("Saved first figure to {}".format(OUT_PNG1))
    plt.close()
    
    # Prepare data for second plot: pause rate over time
    # Find time range from all events
    all_times = []
    for key in pfc_events:
        all_times.extend(pfc_events[key]['pause'])
        all_times.extend(pfc_events[key]['resume'])
    
    if not all_times:
        print("No time data found!")
        return
    
    time_start_ns = min(all_times)
    time_end_ns = max(all_times)
    
    print("\nTime range: {:.2f} ms to {:.2f} ms".format(
        time_start_ns / 1e6, time_end_ns / 1e6))
    
    # Calculate pause rates for each port
    port_data = {}
    for item in port_data_list:
        node_id = item['node_id']
        port_id = item['port_id']
        node_type = item['node_type']
        label = item['label']
        
        pause_events = pfc_events[(node_id, port_id, node_type)]['pause']
        if len(pause_events) > 0:
            time_ms, pause_rate_mps = calculate_pause_rate(
                pause_events, time_start_ns, time_end_ns, TIME_WINDOW_NS)
            # Adjust time to start from 0 (relative to first event)
            time_ms = time_ms - time_start_ns / 1e6
            port_data[label] = (time_ms, pause_rate_mps, node_id, port_id, node_type)
    
    if not port_data:
        print("No pause events found for any port!")
        return
    
    # Plot 2: Pause rate over time
    plt.figure(figsize=(12, 6))
    
    # Use different colors and line styles for different ports
    colors = plt.cm.tab10(np.linspace(0, 1, len(port_data)))
    linestyles = ['-', '--', '-.', ':'] * ((len(port_data) // 4) + 1)
    
    for idx, (label, (time_ms, pause_rate_mps, node_id, port_id, node_type)) in enumerate(sorted(port_data.items())):
        color = colors[idx % len(colors)]
        linestyle = linestyles[idx % len(linestyles)]
        plt.plot(time_ms, pause_rate_mps, 
                color=color, 
                linestyle=linestyle,
                label=label, 
                linewidth=1.5)
    
    plt.xlabel("Time (ms)", fontsize=12)
    plt.ylabel("Pause Rate (Mps)", fontsize=12)
    plt.title("(b) PFC pause rate", fontsize=14)
    plt.legend(fontsize=9, loc='best', ncol=2)
    plt.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    plt.tight_layout()
    
    plt.savefig(OUT_PNG2, dpi=200, bbox_inches='tight')
    print("Saved second figure to {}".format(OUT_PNG2))
    plt.close()
    
    # Plot 3: PFC count per time interval (Real-time count - Stacked Bar Chart)
    plt.figure(figsize=(12, 6))
    
    # Define bin size for real-time count (0.1ms = 100,000 ns)
    bin_size_ns = 100000 
    time_bins = np.arange(time_start_ns, time_end_ns + bin_size_ns, bin_size_ns)
    bin_centers_ms = (time_bins[:-1] + bin_size_ns / 2 - time_start_ns) / 1e6
    
    # Initialize bottom for stacking
    bottom_counts = np.zeros(len(time_bins) - 1)
    
    # Sort ports to have consistent stacking order
    sorted_port_labels = sorted(port_data.keys())
    
    for idx, label in enumerate(sorted_port_labels):
        _, _, node_id, port_id, node_type = port_data[label]
        # Get all events for this port (pause + resume)
        events = pfc_events[(node_id, port_id, node_type)]
        all_event_times = np.array(events['pause'] + events['resume'])
        
        if len(all_event_times) == 0:
            continue
            
        # Calculate counts per bin
        counts, _ = np.histogram(all_event_times, bins=time_bins)
        
        if np.sum(counts) == 0:
            continue
            
        color = colors[idx % len(colors)]
        
        # Use bar chart with stacking
        plt.bar(bin_centers_ms, counts, width=(bin_size_ns / 1e6) * 0.8, 
                bottom=bottom_counts, color=color, label=label, alpha=0.8)
        
        # Update bottom for next stack
        bottom_counts += counts

    plt.xlabel("Time (ms)", fontsize=12)
    plt.ylabel("PFC Frames per 0.1ms", fontsize=12)
    plt.title("Real-time PFC Frame Count (Stacked Bar Chart, Interval: 0.1ms)", fontsize=14)
    plt.legend(fontsize=9, loc='best', ncol=2)
    plt.grid(True, axis='y', linestyle=":", linewidth=0.5, alpha=0.7)
    plt.tight_layout()
    
    plt.savefig(OUT_PNG3, dpi=200, bbox_inches='tight')
    print("Saved third figure to {}".format(OUT_PNG3))
    plt.close()
    
    # Print summary statistics
    print("\nSummary Statistics:")
    print("=" * 80)
    print("{:<20} {:<15} {:<15} {:<15} {:<15}".format(
        "Port", "Pause Events", "Resume Events", "Total Events", "Max Rate (Mps)"))
    print("=" * 80)
    
    for item in port_data_list:
        label = item['label']
        pause_count = item['pause']
        resume_count = item['resume']
        total_count = item['total']
        
        max_rate = 0
        if label in port_data:
            _, pause_rate_mps, _, _, _ = port_data[label]
            max_rate = max(pause_rate_mps) if pause_rate_mps else 0
        
        print("{:<20} {:<15} {:<15} {:<15} {:<15.6f}".format(
            label, pause_count, resume_count, total_count, max_rate))


if __name__ == "__main__":
    main()

