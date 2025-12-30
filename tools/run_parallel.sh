#!/bin/bash
# Parallel gem5-SALAM experiment runner
# 
# - Benchmark GROUPS run in PARALLEL (bfs, fft, gemm, etc.)
# - Configs within a group run SEQUENTIALLY (mobilenetv2 -> mobilenetv2_35 -> mobilenetv2_75)
# - Latencies for each config run SEQUENTIALLY
#
# Usage: ./tools/run_parallel.sh --all
#        ./tools/run_parallel.sh --bench bfs
#        ./tools/run_parallel.sh --all --outdir BM_ARM_OUT/experiments_20251230_010000

set -e

# ============================================================================
# BENCHMARK DEFINITIONS
# ============================================================================
declare -A BENCHMARK_GROUPS=(
    ["mobilenetv2"]="mobilenetv2,mobilenetv2_35,mobilenetv2_75"
    ["lenet"]="lenet_a,lenet_b,lenet_c"
    ["bfs"]="bfs"
    ["fft"]="fft"
    ["gemm"]="gemm"
    ["md_grid"]="md_grid"
    ["md_knn"]="md_knn"
    ["nw"]="nw"
    ["spmv"]="spmv"
    ["stencil2d"]="stencil2d"
    ["stencil3d"]="stencil3d"
    ["mergesort"]="mergesort"
)

declare -A BENCH_PATH=(
    ["mobilenetv2"]="benchmarks/mobilenetv2"
    ["mobilenetv2_35"]="benchmarks/mobilenetv2"
    ["mobilenetv2_75"]="benchmarks/mobilenetv2"
    ["lenet_a"]="benchmarks/lenet/design_a"
    ["lenet_b"]="benchmarks/lenet/design_b"
    ["lenet_c"]="benchmarks/lenet/design_c"
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

declare -A BENCH_CONFIG=(
    ["mobilenetv2"]="1_config.yml"
    ["mobilenetv2_35"]="35_config.yml"
    ["mobilenetv2_75"]="75_config.yml"
    ["lenet_a"]="config.yml"
    ["lenet_b"]="config.yml"
    ["lenet_c"]="config.yml"
    ["bfs"]="config.yml"
    ["fft"]="config.yml"
    ["gemm"]="config.yml"
    ["md_grid"]="config.yml"
    ["md_knn"]="config.yml"
    ["nw"]="config.yml"
    ["spmv"]="config.yml"
    ["stencil2d"]="config.yml"
    ["stencil3d"]="config.yml"
    ["mergesort"]="config.yml"
)

# ============================================================================
# DEFAULTS & ARGUMENT PARSING
# ============================================================================
LATENCIES="0,1000000,5000000"
PARALLEL_JOBS=12
DRY_RUN=false
RUN_ALL=false
SINGLE_BENCH=""
OUTPUT_DIR=""
EXCLUDE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --all|-a)       RUN_ALL=true; shift ;;
        --bench|-b)     SINGLE_BENCH="$2"; shift 2 ;;
        --latencies|-l) LATENCIES="$2"; shift 2 ;;
        --parallel|-j)  PARALLEL_JOBS="$2"; shift 2 ;;
        --outdir|-o)    OUTPUT_DIR="$2"; shift 2 ;;
        --exclude|-x)   EXCLUDE="$2"; shift 2 ;;
        --dry-run)      DRY_RUN=true; shift ;;
        --list)
            echo "Available groups:"
            for g in "${!BENCHMARK_GROUPS[@]}"; do
                echo "  $g: ${BENCHMARK_GROUPS[$g]}"
            done
            exit 0 ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "  --all, -a          Run all benchmarks"
            echo "  --bench, -b NAME   Run single benchmark"
            echo "  --latencies, -l    Latencies (default: 0,1000000,5000000)"
            echo "  --parallel, -j N   Parallel groups (default: 12)"
            echo "  --outdir, -o DIR   Output directory"
            echo "  --exclude, -x LIST Skip benchmarks"
            echo "  --dry-run          Show plan only"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# ============================================================================
# SETUP
# ============================================================================
[[ -z "$M5_PATH" ]] && { echo "M5_PATH not set"; exit 1; }

IFS=',' read -ra LAT_ARRAY <<< "$LATENCIES"
IFS=',' read -ra EXCLUDE_ARRAY <<< "$EXCLUDE"

# Build groups to run
declare -A GROUPS_TO_RUN
if $RUN_ALL; then
    for g in "${!BENCHMARK_GROUPS[@]}"; do
        GROUPS_TO_RUN["$g"]="${BENCHMARK_GROUPS[$g]}"
    done
elif [[ -n "$SINGLE_BENCH" ]]; then
    for g in "${!BENCHMARK_GROUPS[@]}"; do
        if [[ "${BENCHMARK_GROUPS[$g]}" == *"$SINGLE_BENCH"* ]]; then
            GROUPS_TO_RUN["$g"]="$SINGLE_BENCH"
            break
        fi
    done
    [[ ${#GROUPS_TO_RUN[@]} -eq 0 ]] && { echo "Unknown benchmark: $SINGLE_BENCH"; exit 1; }
else
    echo "Specify --all or --bench NAME"; exit 1
fi

# Apply excludes
for x in "${EXCLUDE_ARRAY[@]}"; do
    for g in "${!GROUPS_TO_RUN[@]}"; do
        new=$(echo "${GROUPS_TO_RUN[$g]}" | sed "s/\b$x\b//g" | sed 's/,,/,/g;s/^,//;s/,$//')
        [[ -z "$new" ]] && unset GROUPS_TO_RUN["$g"] || GROUPS_TO_RUN["$g"]="$new"
    done
done

# Output directory - ONE directory for everything
if [[ -n "$OUTPUT_DIR" ]]; then
    BASE_OUTDIR="$(cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"
    mkdir -p "$BASE_OUTDIR"
else
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BASE_OUTDIR="${M5_PATH}/BM_ARM_OUT/experiments_${TIMESTAMP}"
    mkdir -p "$BASE_OUTDIR"
fi

# Count
total_bench=0
total_exp=0
for g in "${!GROUPS_TO_RUN[@]}"; do
    IFS=',' read -ra b <<< "${GROUPS_TO_RUN[$g]}"
    for x in "${b[@]}"; do [[ -n "$x" ]] && ((total_bench++)) && ((total_exp+=${#LAT_ARRAY[@]})); done
done

echo "=============================================="
echo "gem5-SALAM Experiment Runner"
echo "=============================================="
echo "Groups:      ${#GROUPS_TO_RUN[@]} parallel"
echo "Benchmarks:  $total_bench"  
echo "Latencies:   ${LAT_ARRAY[*]}"
echo "Total:       $total_exp experiments"
echo "Output:      $BASE_OUTDIR"
echo "=============================================="

# Pre-create directories
for g in "${!GROUPS_TO_RUN[@]}"; do
    IFS=',' read -ra benches <<< "${GROUPS_TO_RUN[$g]}"
    for bench in "${benches[@]}"; do
        [[ -z "$bench" ]] && continue
        for lat in "${LAT_ARRAY[@]}"; do
            [[ "$lat" -eq 0 ]] && mkdir -p "${BASE_OUTDIR}/${bench}/baseline_no_validation" \
                               || mkdir -p "${BASE_OUTDIR}/${bench}/latency_${lat}"
        done
    done
done

$DRY_RUN && { echo "DRY RUN - would run ${#GROUPS_TO_RUN[@]} groups"; exit 0; }

# ============================================================================
# RUN FUNCTIONS  
# ============================================================================
run_benchmark() {
    local bench="$1"
    local path="${BENCH_PATH[$bench]}"
    local config="${BENCH_CONFIG[$bench]}"
    local log="${BASE_OUTDIR}/${bench}_build.log"
    
    echo "[${bench}] Building..."
    
    # Configure & build
    "${M5_PATH}/tools/SALAM-Configurator/systembuilder.py" \
        --sys-name "$bench" --bench-path "$path" --config-name "$config" \
        > "$log" 2>&1 || { echo "[${bench}] CONFIG FAILED"; return 1; }
    
    make -C "${M5_PATH}/${path}" clean >> "$log" 2>&1
    make -C "${M5_PATH}/${path}" >> "$log" 2>&1 || { echo "[${bench}] BUILD FAILED"; return 1; }
    
    # Run latencies
    for lat in "${LAT_ARRAY[@]}"; do
        local outdir val_opts
        [[ "$lat" -eq 0 ]] && outdir="${BASE_OUTDIR}/${bench}/baseline_no_validation" && val_opts="" \
                           || outdir="${BASE_OUTDIR}/${bench}/latency_${lat}" && val_opts="--enable-kernel-validation --kernel-validation-latency=$lat"
        
        echo "[${bench}] Running lat=$lat..."
        
        "${M5_PATH}/build/ARM/gem5.opt" --outdir="$outdir" \
            "${M5_PATH}/configs/SALAM/fs_${bench}.py" \
            --mem-size=4GB --mem-type=DDR4_2400_8x8 \
            --kernel="${M5_PATH}/${path}/sw/main.elf" \
            --disk-image="${M5_PATH}/benchmarks/common/fake.iso" \
            --machine-type=VExpress_GEM5_V1 --dtb-file=none --bare-metal \
            --cpu-type=DerivO3CPU \
            --accpath="${M5_PATH}/${path}" --accbench="$bench" \
            --caches --l2cache $val_opts \
            > "$outdir/run.log" 2>&1
        
        [[ -f "$outdir/stats.txt" ]] && echo "[${bench}] ✓ lat=$lat" || echo "[${bench}] ✗ lat=$lat FAILED"
    done
}

run_group() {
    local group="$1"
    IFS=',' read -ra benches <<< "${GROUPS_TO_RUN[$group]}"
    for bench in "${benches[@]}"; do
        [[ -n "$bench" ]] && run_benchmark "$bench"
    done
    echo "[GROUP:${group}] Done"
}

# ============================================================================
# MAIN - Launch groups in parallel
# ============================================================================
pids=()
for group in "${!GROUPS_TO_RUN[@]}"; do
    while [[ ${#pids[@]} -ge $PARALLEL_JOBS ]]; do
        for i in "${!pids[@]}"; do
            kill -0 "${pids[$i]}" 2>/dev/null || { wait "${pids[$i]}" 2>/dev/null; unset 'pids[i]'; pids=("${pids[@]}"); break; }
        done
        sleep 1
    done
    run_group "$group" &
    pids+=($!)
done

for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null; done

echo ""
echo "=============================================="
echo "Done! Results: $BASE_OUTDIR"
echo "Completed: $(find "$BASE_OUTDIR" -name stats.txt -size +0 2>/dev/null | wc -l) / $total_exp"
echo "=============================================="
