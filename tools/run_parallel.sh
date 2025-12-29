#!/bin/bash
# Parallel gem5-SALAM experiment runner with separate output directories
# Usage: ./tools/run_parallel.sh [OPTIONS]
#
# Options:
#   --bench          Benchmark name (default: mobilenetv2)
#   --bench-path     Benchmark path (default: benchmarks/mobilenetv2)
#   --config-name    Config file name (default: 1_config.yml)
#   --latencies      Comma-separated list of latencies (default: 0,10000,50000,100000)
#   --parallel       Number of parallel jobs (default: 4)
#   --dry-run        Print commands without executing

BENCH="mobilenetv2"
BENCH_PATH="benchmarks/mobilenetv2"
CONFIG_NAME="1_config.yml"
LATENCIES="0,10000,50000,100000"
PARALLEL_JOBS=4
DRY_RUN=False
ENABLE_TRACE=False
TRACE_FLAGS="LLVMInterface"

while [[ $# -gt 0 ]]; do
  case $1 in
    --bench)
      BENCH="$2"
      shift; shift
      ;;
    --bench-path)
      BENCH_PATH="$2"
      shift; shift
      ;;
    --config-name)
      CONFIG_NAME="$2"
      shift; shift
      ;;
    --latencies)
      LATENCIES="$2"
      shift; shift
      ;;
    --parallel|-j)
      PARALLEL_JOBS="$2"
      shift; shift
      ;;
    --dry-run)
      DRY_RUN=True
      shift
      ;;
    --trace|-t)
      ENABLE_TRACE=True
      shift
      ;;
    --trace-flags)
      TRACE_FLAGS="$2"
      shift; shift
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --bench          Benchmark name (default: mobilenetv2)"
      echo "  --bench-path     Benchmark path (default: benchmarks/mobilenetv2)"
      echo "  --config-name    Config file name (default: 1_config.yml)"
      echo "  --latencies      Comma-separated latencies (default: 0,10000,50000,100000)"
      echo "  --parallel, -j   Number of parallel jobs (default: 4)"
      echo "  --trace, -t      Enable debug tracing"
      echo "  --trace-flags    Debug trace flags (default: LLVMInterface,NoncoherentDma,CommInterface)"
      echo "  --dry-run        Print commands without executing"
      echo ""
      echo "Example:"
      echo "  $0 --bench mobilenetv2 --latencies 0,5000,10000,25000,50000 --parallel 3"
      echo "  $0 --bench mobilenetv2 --latencies 10000 --trace"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ "$M5_PATH" == "" ]; then
    echo "M5_PATH env var is not set, exiting"
    exit 1
fi

# Convert comma-separated latencies to array
IFS=',' read -ra LAT_ARRAY <<< "$LATENCIES"

BINARY="${M5_PATH}/build/ARM/gem5.opt"
KERNEL="${M5_PATH}/${BENCH_PATH}/sw/main.elf"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BASE_OUTDIR="BM_ARM_OUT/${BENCH}_experiments_${TIMESTAMP}"

echo "=============================================="
echo "Parallel gem5-SALAM Experiment Runner"
echo "=============================================="
echo "Benchmark:       $BENCH"
echo "Benchmark Path:  $BENCH_PATH"
echo "Config:          $CONFIG_NAME"
echo "Latencies:       ${LAT_ARRAY[*]}"
echo "Parallel Jobs:   $PARALLEL_JOBS"
echo "Tracing:         $ENABLE_TRACE"
if [ "$ENABLE_TRACE" == "True" ]; then
    echo "Trace Flags:     $TRACE_FLAGS"
fi
echo "Output Base:     $BASE_OUTDIR"
echo "=============================================="

# Run configurator first
echo "Running SALAM Configurator..."
if [ "$DRY_RUN" == "False" ]; then
    if (! "${M5_PATH}"/tools/SALAM-Configurator/systembuilder.py \
        --sys-name "$BENCH" \
        --bench-path "$BENCH_PATH" \
        --config-name "$CONFIG_NAME") then
        echo "Configurator failed"
        exit 1
    fi
fi

# Create base output directory
mkdir -p "$BASE_OUTDIR"

# Array to store PIDs
declare -a PIDS=()
declare -a OUTDIRS=()

# Function to wait for a slot to be available
wait_for_slot() {
    while [ ${#PIDS[@]} -ge $PARALLEL_JOBS ]; do
        for i in "${!PIDS[@]}"; do
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                wait "${PIDS[$i]}"
                exit_code=$?
                if [ $exit_code -eq 0 ]; then
                    echo "[DONE] Experiment completed: ${OUTDIRS[$i]}"
                else
                    echo "[FAIL] Experiment failed (exit $exit_code): ${OUTDIRS[$i]}"
                fi
                unset 'PIDS[i]'
                unset 'OUTDIRS[i]'
                PIDS=("${PIDS[@]}")
                OUTDIRS=("${OUTDIRS[@]}")
                return
            fi
        done
        sleep 1
    done
}

# Launch experiments
for lat in "${LAT_ARRAY[@]}"; do
    wait_for_slot

    if [ "$lat" -eq 0 ]; then
        OUTDIR="${BASE_OUTDIR}/baseline_no_validation"
        VALIDATION_OPTS=""
        LABEL="baseline (no validation)"
    else
        OUTDIR="${BASE_OUTDIR}/latency_${lat}"
        VALIDATION_OPTS="--enable-kernel-validation --kernel-validation-latency=$lat"
        LABEL="latency=${lat}"
    fi

    mkdir -p "$OUTDIR"

    SYS_OPTS="--mem-size=4GB \
              --mem-type=DDR4_2400_8x8 \
              --kernel=$KERNEL \
              --disk-image=$M5_PATH/benchmarks/common/fake.iso \
              --machine-type=VExpress_GEM5_V1 \
              --dtb-file=none --bare-metal \
              --cpu-type=DerivO3CPU"

    CACHE_OPTS="--caches --l2cache"

    # Build trace options if enabled
    if [ "$ENABLE_TRACE" == "True" ]; then
        TRACE_OPTS="--debug-flags=$TRACE_FLAGS --debug-file=debug-trace.txt"
    else
        TRACE_OPTS=""
    fi

    CMD="$BINARY --outdir=$OUTDIR $TRACE_OPTS \
         ${M5_PATH}/configs/SALAM/fs_${BENCH}.py $SYS_OPTS \
         --accpath=${M5_PATH}/${BENCH_PATH} \
         --accbench=$BENCH $CACHE_OPTS $VALIDATION_OPTS"

    if [ "$DRY_RUN" == "True" ]; then
        echo "[DRY-RUN] Would launch: $LABEL"
        echo "  Output: $OUTDIR"
        echo "  Command: $CMD"
        echo ""
    else
        echo "[START] Launching experiment: $LABEL"
        $CMD > "$OUTDIR/run.log" 2>&1 &
        pid=$!
        PIDS+=($pid)
        OUTDIRS+=("$OUTDIR")
        echo "  PID: $pid, Output: $OUTDIR"
    fi
done

# Wait for all remaining jobs
if [ "$DRY_RUN" == "False" ]; then
    echo ""
    echo "Waiting for all experiments to complete..."
    for i in "${!PIDS[@]}"; do
        wait "${PIDS[$i]}"
        exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "[DONE] Experiment completed: ${OUTDIRS[$i]}"
        else
            echo "[FAIL] Experiment failed (exit $exit_code): ${OUTDIRS[$i]}"
        fi
    done

    echo ""
    echo "=============================================="
    echo "All experiments completed!"
    echo "Results saved in: $BASE_OUTDIR"
    echo "=============================================="

    # Generate summary
    SUMMARY_FILE="$BASE_OUTDIR/summary.csv"
    echo "Latency,SimTicks,SimSeconds,TotalValidations,ValidationRequests,ValidationLatencyTotal" > "$SUMMARY_FILE"

    for dir in "$BASE_OUTDIR"/*/; do
        if [ -f "$dir/stats.txt" ]; then
            if [[ "$dir" == *"baseline"* ]]; then
                lat="0"
            else
                lat=$(basename "$dir" | grep -oP 'latency_\K\d+' || echo "0")
            fi
            ticks=$(grep "^simTicks" "$dir/stats.txt" | head -1 | awk '{print $2}')
            secs=$(grep "^simSeconds" "$dir/stats.txt" | head -1 | awk '{print $2}')
            validations=$(grep "totalKernelValidations" "$dir/stats.txt" | head -1 | awk '{print $2}')
            requests=$(grep "kernelValidationRequests" "$dir/stats.txt" | head -1 | awk '{print $2}')
            lat_total=$(grep "kernelValidationLatencyTotal" "$dir/stats.txt" | head -1 | awk '{print $2}')
            echo "${lat},${ticks:-N/A},${secs:-N/A},${validations:-N/A},${requests:-N/A},${lat_total:-N/A}" >> "$SUMMARY_FILE"
        fi
    done

    echo ""
    echo "Summary saved to: $SUMMARY_FILE"
    echo ""
    echo "Results:"
    # Use cat if column command is not available
    if command -v column &> /dev/null; then
        column -t -s',' "$SUMMARY_FILE"
    else
        cat "$SUMMARY_FILE"
    fi
fi
