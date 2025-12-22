import os
import matplotlib.pyplot as plt


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Updated paths for the new directory structure
QLEN_FILE = os.path.join(BASE_DIR, "..", "..", "output", "qlen.txt")
OUT_DIR = os.path.join(BASE_DIR, "..", "figures")
OUT_PNG = os.path.join(OUT_DIR, "qlen_plot.png")

# Ensure output directory exists
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)


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

    plt.figure(figsize=(12, 7))
    
    # Plot all ports found in the data
    # Sort keys to have consistent colors
    sorted_keys = sorted(qlen.keys())
    
    # Limit the number of ports to plot if there are too many
    max_ports = 10
    if len(sorted_keys) > max_ports:
        print("Found {} ports, only plotting the first {}.".format(len(sorted_keys), max_ports))
        sorted_keys = sorted_keys[:max_ports]

    for key in sorted_keys:
        series = qlen[key]
        L = min(len(times_ms), len(series))
        y_kb = [x / 1000.0 for x in series[:L]]
        label = "SW{}-P{}".format(key[0], key[1])
        plt.plot(times_ms[:L], y_kb, label=label, linewidth=2, marker="o", markersize=3)

    plt.xlabel("Time (ms)", fontsize=12)
    plt.ylabel("Queue (KB)", fontsize=12)
    plt.title("Queue Length over Time", fontsize=14)
    plt.legend(fontsize=8, loc='upper right', bbox_to_anchor=(1.15, 1))
    plt.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    plt.tight_layout()

    plt.savefig(OUT_PNG, dpi=200)
    print("Saved figure to {}".format(OUT_PNG))
    # plt.show() # Commented out for non-interactive environments


if __name__ == "__main__":
    main()

