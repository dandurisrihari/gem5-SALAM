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
#   --all            Run all available benchmarks
#   --dry-run        Print commands without executing

# Available benchmarks (name:path pairs)
# Add new benchmarks here as they become available
declare -A AVAILABLE_BENCHMARKS=(
    ["mobilenetv2"]="benchmarks/mobilenetv2"
    ["lenet"]="benchmarks/lenet"
    ["bfs"]="benchmarks/sys_validation/bfs"
    ["fft"]="benchmarks/sys_validation/fft"
    ["gemm"]="benchmarks/sys_validation/gemm"
    ["md_grid"]="benchmarks/sys_validation/md_grid"
    ["md_knn"]="benchmarks/sys_validation/md_knn"
    ["nw"]="benchmarks/sys_validation/nw"
    ["spmv"]="benchmarks/sys_validation/spmv"
    ["stencil2d"]="benchmarks/sys_validation/stencil2d"
    ["stencil3d"]="benchmarks/sys_validation/stencil3d"
    ["mergesort"]="benchmarks/sys_validation/mergesort"
)

BENCH="mobilenetv2"
BENCH_PATH="benchmarks/mobilenetv2"
CONFIG_NAME="1_config.yml"
LATENCIES="0,10000,50000,100000"
PARALLEL_JOBS=4
DRY_RUN=False
ENABLE_TRACE=False
TRACE_FLAGS="LLVMInterface"
RUN_ALL_BENCHMARKS=False

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
    --all|-a)
      RUN_ALL_BENCHMARKS=True
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
      echo "  --all, -a        Run all available benchmarks"
      echo "  --trace, -t      Enable debug tracing"
      echo "  --trace-flags    Debug trace flags (default: LLVMInterface)"
      echo "  --dry-run        Print commands without executing"
      echo "  --list           List available benchmarks"
      echo ""
      echo "Available benchmarks:"
      for bench in "${!AVAILABLE_BENCHMARKS[@]}"; do
          echo "  - $bench (${AVAILABLE_BENCHMARKS[$bench]})"
      done
      echo ""
      echo "Example:"
      echo "  $0 --bench mobilenetv2 --latencies 0,5000,10000,25000,50000 --parallel 3"
      echo "  $0 --bench mobilenetv2 --latencies 10000 --trace"
      echo "  $0 --all --latencies 0,10000 --parallel 2"
      exit 0
      ;;
    --list)
      echo "Available benchmarks:"
      for bench in "${!AVAILABLE_BENCHMARKS[@]}"; do
          echo "  - $bench (${AVAILABLE_BENCHMARKS[$bench]})"
      done
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

# Determine which benchmarks to run
if [ "$RUN_ALL_BENCHMARKS" == "True" ]; then
    BENCHMARKS_TO_RUN=("${!AVAILABLE_BENCHMARKS[@]}")
else
    BENCHMARKS_TO_RUN=("$BENCH")
fi

BINARY="${M5_PATH}/build/ARM/gem5.opt"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ "$RUN_ALL_BENCHMARKS" == "True" ]; then
    BASE_OUTDIR="BM_ARM_OUT/all_benchmarks_${TIMESTAMP}"
else
    BASE_OUTDIR="BM_ARM_OUT/${BENCH}_experiments_${TIMESTAMP}"
fi

echo "=============================================="
echo "Parallel gem5-SALAM Experiment Runner"
echo "=============================================="
if [ "$RUN_ALL_BENCHMARKS" == "True" ]; then
    echo "Mode:            All benchmarks"
    echo "Benchmarks:      ${BENCHMARKS_TO_RUN[*]}"
else
    echo "Benchmark:       $BENCH"
    echo "Benchmark Path:  $BENCH_PATH"
fi
echo "Config:          $CONFIG_NAME"
echo "Latencies:       ${LAT_ARRAY[*]}"
echo "Parallel Jobs:   $PARALLEL_JOBS"
echo "Tracing:         $ENABLE_TRACE"
if [ "$ENABLE_TRACE" == "True" ]; then
    echo "Trace Flags:     $TRACE_FLAGS"
fi
echo "Output Base:     $BASE_OUTDIR"
echo "=============================================="

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
for current_bench in "${BENCHMARKS_TO_RUN[@]}"; do
    # Determine benchmark path
    if [ "$RUN_ALL_BENCHMARKS" == "True" ]; then
        current_bench_path="${AVAILABLE_BENCHMARKS[$current_bench]}"
    else
        current_bench_path="$BENCH_PATH"
    fi

    KERNEL="${M5_PATH}/${current_bench_path}/sw/main.elf"

    # Check if config script exists
    if [ ! -f "${M5_PATH}/configs/SALAM/fs_${current_bench}.py" ]; then
        echo "[SKIP] Config script not found: configs/SALAM/fs_${current_bench}.py"
        continue
    fi

    # Build kernel if it doesn't exist
    if [ ! -f "$KERNEL" ]; then
        echo "[BUILD] Kernel not found for $current_bench, building..."
        if [ "$DRY_RUN" == "False" ]; then
            if (! make -C "${M5_PATH}/${current_bench_path}" 2>&1); then
                echo "[SKIP] Build failed for $current_bench, skipping..."
                continue
            fi
            # Check again after build
            if [ ! -f "$KERNEL" ]; then
                echo "[SKIP] Kernel still not found after build: $KERNEL"
                continue
            fi
            echo "[BUILD] Successfully built $current_bench"
        else
            echo "[DRY-RUN] Would build: make -C ${M5_PATH}/${current_bench_path}"
        fi
    fi

    # Run configurator for this benchmark
    echo "Running SALAM Configurator for $current_bench..."
    if [ "$DRY_RUN" == "False" ]; then
        if (! "${M5_PATH}"/tools/SALAM-Configurator/systembuilder.py \
            --sys-name "$current_bench" \
            --bench-path "$current_bench_path" \
            --config-name "$CONFIG_NAME" 2>/dev/null) then
            echo "[WARN] Configurator failed for $current_bench, skipping..."
            continue
        fi
    fi

    for lat in "${LAT_ARRAY[@]}"; do
        wait_for_slot

        if [ "$RUN_ALL_BENCHMARKS" == "True" ]; then
            BENCH_OUTDIR="${BASE_OUTDIR}/${current_bench}"
        else
            BENCH_OUTDIR="${BASE_OUTDIR}"
        fi

        if [ "$lat" -eq 0 ]; then
            OUTDIR="${BENCH_OUTDIR}/baseline_no_validation"
            VALIDATION_OPTS=""
            LABEL="${current_bench}: baseline (no validation)"
        else
            OUTDIR="${BENCH_OUTDIR}/latency_${lat}"
            VALIDATION_OPTS="--enable-kernel-validation --kernel-validation-latency=$lat"
            LABEL="${current_bench}: latency=${lat}"
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
             ${M5_PATH}/configs/SALAM/fs_${current_bench}.py $SYS_OPTS \
             --accpath=${M5_PATH}/${current_bench_path} \
             --accbench=$current_bench $CACHE_OPTS $VALIDATION_OPTS"

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
    echo "Benchmark,Latency,SimTicks,SimSeconds,TotalValidations,ValidationRequests,ValidationLatencyTotal" > "$SUMMARY_FILE"

    # Handle both single benchmark and all benchmarks directory structures
    find "$BASE_OUTDIR" -name "stats.txt" -type f | while read statsfile; do
        dir=$(dirname "$statsfile")
        
        # Determine benchmark name and latency from path
        if [ "$RUN_ALL_BENCHMARKS" == "True" ]; then
            bench_name=$(echo "$dir" | sed "s|$BASE_OUTDIR/||" | cut -d'/' -f1)
            lat_dir=$(basename "$dir")
        else
            bench_name="$BENCH"
            lat_dir=$(basename "$dir")
        fi

        if [[ "$lat_dir" == *"baseline"* ]]; then
            lat="0"
        else
            lat=$(echo "$lat_dir" | grep -oP 'latency_\K\d+' || echo "0")
        fi

        ticks=$(grep "^simTicks" "$statsfile" | head -1 | awk '{print $2}')
        secs=$(grep "^simSeconds" "$statsfile" | head -1 | awk '{print $2}')
        validations=$(grep "totalKernelValidations" "$statsfile" | head -1 | awk '{print $2}')
        requests=$(grep "kernelValidationRequests" "$statsfile" | head -1 | awk '{print $2}')
        lat_total=$(grep "kernelValidationLatencyTotal" "$statsfile" | head -1 | awk '{print $2}')
        echo "${bench_name},${lat},${ticks:-N/A},${secs:-N/A},${validations:-N/A},${requests:-N/A},${lat_total:-N/A}" >> "$SUMMARY_FILE"
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
