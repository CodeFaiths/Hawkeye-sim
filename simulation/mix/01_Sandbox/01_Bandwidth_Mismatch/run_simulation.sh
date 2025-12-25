#!/bin/bash

# Bandwidth Mismatch 场景仿真脚本

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SIMULATION_ROOT="/home/rdmauser/users/jiangtao/workspace/Hawkeye-main/simulation"

echo "=========================================="
echo "Running Bandwidth Mismatch Scenario"
echo "=========================================="
echo ""

# 切换到仿真根目录
cd "$SIMULATION_ROOT"

# 运行仿真
echo "Running simulation..."
python2.7 ./waf --run "scratch/third $SCRIPT_DIR/config/config.txt"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Simulation completed successfully!"
    echo "=========================================="
    echo ""
    echo "Output files location:"
    echo "  - FCT: $SCRIPT_DIR/output/fct.txt"
    echo "  - PFC: $SCRIPT_DIR/output/pfc.txt"
    echo "  - QLen: $SCRIPT_DIR/output/qlen.txt"
    echo "  - Link Util: $SCRIPT_DIR/output/link_util.txt"
    echo ""
    echo "To analyze results, run:"
    echo "  cd $SCRIPT_DIR/analyze/scripts"
    echo "  python3 plot_link_util.py"
    echo "  python3 plot_pfc.py"
    echo "  python3 plot_qlen.py"
else
    echo ""
    echo "=========================================="
    echo "❌ Simulation failed!"
    echo "=========================================="
    exit 1
fi
