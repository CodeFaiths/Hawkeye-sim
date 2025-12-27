#!/bin/bash
# =================================================================
# NS3 Trace Analysis Suite - 一键分析脚本
# 执行所有分析脚本，生成完整的分析报告
# =================================================================

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 实验目录 (analyze/scripts -> analyze -> experiment)
ANALYZE_DIR="$(dirname "$SCRIPT_DIR")"
EXPERIMENT_DIR="$(dirname "$ANALYZE_DIR")"

# 默认路径
OUTPUT_DIR="$EXPERIMENT_DIR/output"
TRACE_ANALYSIS_DIR="$ANALYZE_DIR/trace_analysis"
FIGURES_DIR="$ANALYZE_DIR/figures"
CONFIG_DIR="$EXPERIMENT_DIR/config"

# 默认文件
TRACE_FILE="$OUTPUT_DIR/trace_out.tr"
PFC_FILE="$OUTPUT_DIR/pfc.txt"
INGRESS_FILE="$OUTPUT_DIR/ingress_queue.txt"
LINK_UTIL_FILE="$OUTPUT_DIR/link_util.txt"
QLEN_FILE="$OUTPUT_DIR/qlen.txt"

# 自动查找拓扑文件
TOPOLOGY_FILE=""
if [ -f "$CONFIG_DIR/topo_incast_5to1.txt" ]; then
    TOPOLOGY_FILE="$CONFIG_DIR/topo_incast_5to1.txt"
elif [ -f "$CONFIG_DIR/topology.txt" ]; then
    TOPOLOGY_FILE="$CONFIG_DIR/topology.txt"
elif [ -f "$EXPERIMENT_DIR/topology.txt" ]; then
    TOPOLOGY_FILE="$EXPERIMENT_DIR/topology.txt"
fi

# 端口过滤参数 (可选)
INCLUDE_PORTS=""

print_banner() {
    echo -e "${BLUE}==================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==================================================================${NC}"
}

print_step() {
    echo -e "\n${GREEN}▶ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -t, --trace FILE       Trace file path (default: output/trace_out.tr)"
    echo "  -p, --pfc FILE         PFC file path (default: output/pfc.txt)"
    echo "  -i, --ingress FILE     Ingress queue file (default: output/ingress_queue.txt)"
    echo "  -o, --output DIR       Output directory for analysis results"
    echo "  --include PORTS        Only include specified ports (e.g., 'SW6-P1 SW6-P6 H0-P1')"
    echo "  -h, --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run with default paths"
    echo "  $0 --include 'SW6-P1 SW6-P6'          # Only analyze specific ports"
    echo "  $0 -t custom/trace.tr -p custom/pfc.txt"
    exit 0
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--trace)
            TRACE_FILE="$2"
            shift 2
            ;;
        -p|--pfc)
            PFC_FILE="$2"
            shift 2
            ;;
        -i|--ingress)
            INGRESS_FILE="$2"
            shift 2
            ;;
        -o|--output)
            TRACE_ANALYSIS_DIR="$2"
            shift 2
            ;;
        --include)
            INCLUDE_PORTS="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

print_banner "NS3 Trace Analysis Suite"

echo ""
echo "Experiment Directory: $EXPERIMENT_DIR"
echo "Output Directory:     $OUTPUT_DIR"
echo "Analysis Output:      $TRACE_ANALYSIS_DIR"
echo "Figures Output:       $FIGURES_DIR"
if [ -n "$INCLUDE_PORTS" ]; then
    echo "Port Filter:          $INCLUDE_PORTS"
fi

# 创建输出目录
mkdir -p "$TRACE_ANALYSIS_DIR"
mkdir -p "$FIGURES_DIR"

# 构建端口过滤参数
INCLUDE_ARGS=""
if [ -n "$INCLUDE_PORTS" ]; then
    INCLUDE_ARGS="--include $INCLUDE_PORTS"
fi

# =================================================================
# Step 1: 分析Trace文件 (链路利用率与队列长度)
# =================================================================
if [ -f "$TRACE_FILE" ]; then
    print_step "Step 1/5: Plotting trace data..."
    echo "  Input:  $TRACE_FILE"
    echo "  Output: $FIGURES_DIR/"
    
    # 同时生成CSV和图表
    python3 "$SCRIPT_DIR/plot_trace.py" "$TRACE_FILE" \
        --output-dir "$FIGURES_DIR" \
        --csv-dir "$TRACE_ANALYSIS_DIR" \
        --topology "$TOPOLOGY_FILE" \
        $INCLUDE_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "Trace plotting completed"
    else
        print_error "Trace plotting failed"
    fi
else
    print_warning "Step 1/5: Trace file not found: $TRACE_FILE (skipped)"
fi

# =================================================================
# Step 2: PFC分析 (统计汇总与Trace关联分析)
# =================================================================
if [ -f "$PFC_FILE" ]; then
    print_step "Step 2/5: Analyzing PFC events..."
    echo "  Input:  $PFC_FILE"
    echo "  Output: $FIGURES_DIR/"
    
    # 运行合并后的 plot_pfc.py
    # 如果存在 trace_analysis 目录，则进行关联分析
    TRACE_ARG=""
    if [ -d "$TRACE_ANALYSIS_DIR" ]; then
        TRACE_ARG="$TRACE_ANALYSIS_DIR"
    fi
    
    python3 "$SCRIPT_DIR/plot_pfc.py" "$PFC_FILE" $TRACE_ARG \
        --output-dir "$FIGURES_DIR" \
        --topology "$TOPOLOGY_FILE" \
        --ingress "$INGRESS_FILE" \
        $INCLUDE_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "PFC analysis completed"
    else
        print_error "PFC analysis failed"
    fi
else
    print_warning "Step 2/5: PFC file not found: $PFC_FILE (skipped)"
fi

# =================================================================
# Step 3: Ingress队列分析 (用于PFC触发分析)
# =================================================================
if [ -f "$INGRESS_FILE" ]; then
    print_step "Step 3/5: Analyzing ingress queue (PFC trigger analysis)..."
    echo "  Input:  $INGRESS_FILE"
    echo "  Output: $FIGURES_DIR/"
    
    python3 "$SCRIPT_DIR/plot_ingress_qlen.py" "$INGRESS_FILE" "$FIGURES_DIR" \
        --topology "$TOPOLOGY_FILE" \
        $INCLUDE_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "Ingress queue analysis completed"
    else
        print_error "Ingress queue analysis failed"
    fi
else
    print_warning "Step 3/5: Ingress queue file not found: $INGRESS_FILE (skipped)"
fi

# =================================================================
# Step 4: 链路利用率分析 (从monitor输出)
# =================================================================
if [ -f "$LINK_UTIL_FILE" ]; then
    print_step "Step 4/5: Analyzing link utilization (from monitor)..."
    echo "  Input:  $LINK_UTIL_FILE"
    echo "  Output: $FIGURES_DIR/"
    
    python3 "$SCRIPT_DIR/plot_link_util.py" \
        --topology "$TOPOLOGY_FILE" \
        $INCLUDE_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "Link utilization analysis completed"
    else
        print_error "Link utilization analysis failed"
    fi
else
    print_warning "Step 4/5: Link util file not found: $LINK_UTIL_FILE (skipped)"
fi

# =================================================================
# Step 5: Egress队列长度分析 (从monitor输出)
# =================================================================
if [ -f "$QLEN_FILE" ]; then
    print_step "Step 5/5: Analyzing egress queue length (from monitor)..."
    echo "  Input:  $QLEN_FILE"
    echo "  Output: $FIGURES_DIR/"
    
    python3 "$SCRIPT_DIR/plot_egress_qlen.py" $INCLUDE_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "Egress queue length analysis completed"
    else
        print_error "Egress queue length analysis failed"
    fi
else
    print_warning "Step 5/5: Qlen file not found: $QLEN_FILE (skipped)"
fi

# =================================================================
# 完成
# =================================================================
print_banner "Analysis Complete!"

echo ""
echo "📁 Results saved to:"
echo ""
echo "   CSV Data:    $TRACE_ANALYSIS_DIR/"
if [ -d "$TRACE_ANALYSIS_DIR" ]; then
    ls -1 "$TRACE_ANALYSIS_DIR"/*.csv 2>/dev/null | while read f; do
        echo "                - $(basename $f)"
    done
fi
echo ""
echo "   Figures:     $FIGURES_DIR/"
if [ -d "$FIGURES_DIR" ]; then
    find "$FIGURES_DIR" -name "*.png" -type f 2>/dev/null | while read f; do
        echo "                - ${f#$FIGURES_DIR/}"
    done
fi
echo ""
echo -e "${GREEN}Done!${NC}"
