import os
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# go up two levels: simulation/analysis/exp2 -> simulation, then into mix
PFC_FILE = os.path.join(BASE_DIR, "..", "..", "mix", "exp2", "pfc_exp2.txt")
OUT_PNG = os.path.join(BASE_DIR, "pfc_exp2.png")

# Switch/port IDs for exp2 topology
# P1: switch 23, port 2
P1_SWITCH = 23
P1_PORT = 2

# P2: switch 22, port 6
P2_SWITCH = 22
P2_PORT = 6

# P3: switch 26, port 1
P3_SWITCH = 26
P3_PORT = 1

# P4: switch 26, port 3
P4_SWITCH = 26
P4_PORT = 3

# P5: switch 24, port 17
P5_SWITCH = 24
P5_PORT = 17

# P6: switch 24, port 2
P6_SWITCH = 24
P6_PORT = 2

# P7: switch 18, port 1
P7_SWITCH = 18
P7_PORT = 1

# Time window for calculating pause rate (in nanoseconds)
# 1ms window
TIME_WINDOW_NS = 1000000  # 1ms = 1,000,000 ns


def parse_pfc(file_path):
    """
    Parse PFC file format: time_ns node_id node_type port_id pause_flag
    node_type: 1 = switch
    pause_flag: 1 = pause, 0 = resume
    Returns: dict mapping (switch, port) -> list of (time_ns, is_pause)
    """
    pfc_events = defaultdict(list)
    
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
                
                # Process all nodes (both hosts and switches can have PFC events)
                key = (node_id, port_id)
                # Only count pause events (pause_flag == 1)
                if pause_flag == 1:
                    pfc_events[key].append(time_ns)
            except (ValueError, IndexError):
                continue
    
    return pfc_events


def calculate_pause_rate(pfc_events, time_start_ns, time_end_ns, time_window_ns):
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
        pause_count = sum(1 for event_time in pfc_events 
                          if bin_start <= event_time < bin_end)
        
        # Calculate rate in Mps (Million per second)
        window_duration_s = time_window_ns / 1e9
        pause_rate_mps = pause_count / window_duration_s / 1e6
        
        pause_rates.append(pause_rate_mps)
    
    # Convert time to milliseconds
    time_points_ms = time_bins[1:] / 1e6
    
    return time_points_ms, pause_rates


def main():
    if not os.path.exists(PFC_FILE):
        print("PFC file not found: {}".format(PFC_FILE))
        return
    
    # Parse PFC events
    pfc_events = parse_pfc(PFC_FILE)
    
    # Get events for each port (only the specified ports)
    ports = {
        'P1': (P1_SWITCH, P1_PORT),
        'P2': (P2_SWITCH, P2_PORT),
        'P3': (P3_SWITCH, P3_PORT),
        'P4': (P4_SWITCH, P4_PORT),
        'P5': (P5_SWITCH, P5_PORT),
        'P6': (P6_SWITCH, P6_PORT),
        'P7': (P7_SWITCH, P7_PORT),
    }
    
    # Find time range from specified ports only
    all_times = []
    for port_name, (sw, port) in ports.items():
        if (sw, port) in pfc_events:
            all_times.extend(pfc_events[(sw, port)])
    
    if not all_times:
        print("No PFC events found for specified ports!")
        return
    
    time_start_ns = min(all_times)
    time_end_ns = max(all_times)
    
    print("\nTime range: {:.2f} ms to {:.2f} ms".format(
        time_start_ns / 1e6, time_end_ns / 1e6))
    
    # Calculate pause rates for each port
    port_data = {}
    for port_name, (sw, port) in ports.items():
        if (sw, port) in pfc_events:
            events = pfc_events[(sw, port)]
            print("{} ({}-{}): {} pause events".format(port_name, sw, port, len(events)))
            time_ms, pause_rate_mps = calculate_pause_rate(
                events, time_start_ns, time_end_ns, TIME_WINDOW_NS)
            port_data[port_name] = (time_ms, pause_rate_mps, sw, port)
        else:
            print("Warning: No PFC events found for {} (switch {}, port {})".format(
                port_name, sw, port))
    
    if not port_data:
        print("No PFC data available for any port!")
        return
    
    # Plot
    plt.figure(figsize=(12, 6))
    
    # Color and style mapping
    color_map = {
        'P1': 'black',
        'P2': 'red',
        'P3': 'blue',
        'P4': 'green',
        'P5': 'orange',
        'P6': 'purple',
        'P7': 'brown'
    }
    
    linestyle_map = {
        'P1': '-',
        'P2': '-',
        'P3': '--',
        'P4': '-.',
        'P5': ':',
        'P6': '-',
        'P7': '--'
    }
    
    # Plot only the specified ports
    for port_name in ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7']:
        if port_name in port_data:
            time_ms, pause_rate_mps, sw, port = port_data[port_name]
            label = "{} ({}-{})".format(port_name, sw, port)
            color = color_map.get(port_name, 'gray')
            linestyle = linestyle_map.get(port_name, '-')
            plt.plot(time_ms, pause_rate_mps, 
                    color=color, 
                    linestyle=linestyle,
                    label=label, 
                    linewidth=1.5)
    
    plt.xlabel("Time (ms)", fontsize=12)
    plt.ylabel("Pause Rate (Mps)", fontsize=12)
    plt.title("(b) PFC pause rate", fontsize=14)
    plt.legend(fontsize=10, loc='best')
    plt.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    plt.tight_layout()
    
    plt.savefig(OUT_PNG, dpi=200)
    print("Saved figure to {}".format(OUT_PNG))
    plt.show()
    
    # Print summary statistics
    print("\nSummary:")
    for port_name in ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7']:
        if port_name in port_data:
            time_ms, pause_rate_mps, sw, port = port_data[port_name]
            max_rate = max(pause_rate_mps) if pause_rate_mps else 0
            avg_rate = np.mean(pause_rate_mps) if pause_rate_mps else 0
            total_events = len(pfc_events.get((sw, port), []))
            print("{} ({}-{}): max={:.3f} Mps, avg={:.3f} Mps, total events={}".format(
                port_name, sw, port, max_rate, avg_rate, total_events))
        else:
            sw, port = ports[port_name]
            print("{} ({}-{}): No PFC events found".format(port_name, sw, port))


if __name__ == "__main__":
    main()

