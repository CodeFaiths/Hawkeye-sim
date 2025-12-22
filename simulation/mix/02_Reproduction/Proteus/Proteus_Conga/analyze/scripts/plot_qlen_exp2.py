import os
import matplotlib.pyplot as plt


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# go up two levels: simulation/analysis/exp2 -> simulation, then into mix
QLEN_FILE = os.path.join(BASE_DIR, "..", "..", "mix", "qlen_exp2.txt")
OUT_PNG = os.path.join(BASE_DIR, "fig2a_exp2.png")

# Switch/port IDs for exp2 topology
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


def parse_qlen(file_path, use_instantaneous=True):
    """
    Parse queue length data from file.
    
    Args:
        use_instantaneous: If True, estimate instantaneous queue length by finding
                          the maximum non-zero bin in the histogram (represents peak
                          queue length seen). If False, use cumulative average 
                          (original behavior, which doesn't reflect current state).
    """
    times_ns = []
    qlen = {}
    prev_counts = {}  # Store previous histogram to compute incremental changes

    with open(file_path, "r") as f:
        line = f.readline()
        while line:
            line = line.strip()
            if not line:
                line = f.readline()
                continue

            if line.startswith("time:"):
                t = int(line.split()[1])
                times_ns.append(t)
                # read following "<sw> <port> <hist...>" lines
                line = f.readline()
                while line and (not line.startswith("time:")):
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        sw = int(parts[0])
                        port = int(parts[1])
                        counts = list(map(int, parts[2:]))
                        key = (sw, port)

                        if use_instantaneous:
                            # Use **per-ms average** queue length based on incremental histogram.
                            # Each dump in qlen_exp2.txt is a cumulative histogram from the
                            # start of monitoring up to this time. To get the statistics
                            # for the *current 1 ms window*, we take the difference between
                            # the current histogram and the previous one, and then compute
                            # the average queue length over that window:
                            #   avg_kb = sum(i * diff[i]) / sum(diff[i])
                            #
                            # This makes each point in the time series represent the average
                            # queue length during that 1 ms interval.
                            if key in prev_counts:
                                prev = prev_counts[key]
                                # Incremental changes for this 1 ms window
                                diffs = []
                                for i in range(len(counts)):
                                    prev_val = prev[i] if i < len(prev) else 0
                                    diff = counts[i] - prev_val
                                    # Histogram should be non-decreasing, but guard just in case
                                    if diff < 0:
                                        diff = 0
                                    diffs.append(diff)

                                total_diff = sum(diffs)
                                if total_diff > 0:
                                    avg_kb = sum(i * d for i, d in enumerate(diffs)) / float(total_diff)
                                else:
                                    # No new samples in this window -> treat as empty queue
                                    avg_kb = 0.0
                            else:
                                # First time point: fall back to cumulative average
                                total_cnt = sum(counts)
                                if total_cnt > 0:
                                    avg_kb = sum(i * c for i, c in enumerate(counts)) / float(total_cnt)
                                else:
                                    avg_kb = 0.0

                            avg_bytes = avg_kb * 1000.0
                            prev_counts[key] = counts[:]  # Store current cumulative histogram
                        else:
                            # Original behavior: cumulative average
                            total_cnt = sum(counts)
                            if total_cnt > 0:
                                avg_kb = sum(i * c for i, c in enumerate(counts)) / float(total_cnt)
                                avg_bytes = avg_kb * 1000.0
                            else:
                                avg_bytes = 0.0

                        qlen.setdefault(key, []).append(avg_bytes)

                    line = f.readline()
                # continue outer loop with current line (time: or EOF)
                continue

            line = f.readline()

    return times_ns, qlen


def main():
    if not os.path.exists(QLEN_FILE):
        print("QLEN file not found: {}".format(QLEN_FILE))
        return

    # Use instantaneous queue length estimation instead of cumulative average
    # This better reflects the current queue state rather than historical average
    times_ns, qlen = parse_qlen(QLEN_FILE, use_instantaneous=True)
    if not times_ns:
        print("No time points parsed from {}".format(QLEN_FILE))
        return

    times_ms = [t / 1e6 for t in times_ns]

    # Get queue data for all ports
    p2_series = qlen.get((P2_SWITCH, P2_PORT))
    p3_series = qlen.get((P3_SWITCH, P3_PORT))
    p4_series = qlen.get((P4_SWITCH, P4_PORT))
    p5_series = qlen.get((P5_SWITCH, P5_PORT))
    p6_series = qlen.get((P6_SWITCH, P6_PORT))

    # Check if all ports have data
    missing_ports = []
    if p2_series is None:
        missing_ports.append("P2 (switch {}, port {})".format(P2_SWITCH, P2_PORT))
    if p3_series is None:
        missing_ports.append("P3 (switch {}, port {})".format(P3_SWITCH, P3_PORT))
    if p4_series is None:
        missing_ports.append("P4 (switch {}, port {})".format(P4_SWITCH, P4_PORT))
    if p5_series is None:
        missing_ports.append("P5 (switch {}, port {})".format(P5_SWITCH, P5_PORT))
    if p6_series is None:
        missing_ports.append("P6 (switch {}, port {})".format(P6_SWITCH, P6_PORT))
    
    if missing_ports:
        print("Warning: No queue data found for: {}".format(", ".join(missing_ports)))
        # Continue with available ports

    # Find minimum length to ensure all series have the same length
    series_list = [s for s in [p2_series, p3_series, p4_series, p5_series, p6_series] if s is not None]
    if not series_list:
        print("No queue data available for any port!")
        return
    
    L = min(len(times_ms), *[len(s) for s in series_list])
    times_ms = times_ms[:L]

    plt.figure(figsize=(10, 6))
    
    # Plot each port with different colors and styles
    # Helper to plot a series and annotate each ms point with its value (in KB)
    def plot_and_annotate(label, color, series, linestyle="--"):
        if series is None:
            return
        y_kb = [x / 1000.0 for x in series[:L]]
        plt.plot(times_ms, y_kb, color=color, linestyle=linestyle, label=label, linewidth=4, marker="o", markersize=2)
        # Annotate each ms point slightly above the marker
        for x, y in zip(times_ms, y_kb):
            plt.text(x, y, f"{y:.1f}", fontsize=6, ha="center", va="bottom", color=color, alpha=0.7)

    plot_and_annotate("P2 (22-6)", "red", p2_series)
    plot_and_annotate("P3 (26-1)", "blue", p3_series)
    plot_and_annotate("P4 (26-3)", "green", p4_series)
    plot_and_annotate("P5 (24-17)", "orange", p5_series)
    plot_and_annotate("P6 (24-2)", "purple", p6_series)

    plt.xlabel("Time (ms)", fontsize=12)
    plt.ylabel("Queue (KB)", fontsize=12)
    plt.legend(fontsize=10, loc='best')
    plt.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    plt.tight_layout()

    plt.savefig(OUT_PNG, dpi=200)
    print("Saved figure to {}".format(OUT_PNG))
    plt.show()


if __name__ == "__main__":
    main()

