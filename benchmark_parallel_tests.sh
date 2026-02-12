#!/bin/bash
# benchmark_parallel_tests.sh
# pytest-xdist 並列実行のベンチマークスクリプト

set -e

echo "========================================================================"
echo "Pytest Parallel Execution Benchmark"
echo "========================================================================"
echo "Date: $(date)"
echo "Docker Container: keikakun_app-backend-1"
echo ""

# テストマーカー除外オプション
EXCLUDE_MARKERS="-m 'not performance and not integration'"

# ベンチマーク結果を保存するディレクトリ
RESULTS_DIR="benchmark_results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_FILE="$RESULTS_DIR/benchmark_$TIMESTAMP.txt"

echo "Results will be saved to: $RESULTS_FILE"
echo ""

# ヘッダーを出力
{
    echo "========================================================================"
    echo "Pytest Parallel Execution Benchmark"
    echo "========================================================================"
    echo "Date: $(date)"
    echo ""
} > "$RESULTS_FILE"

# ベンチマーク実行関数
run_benchmark() {
    local workers=$1
    local label=$2

    echo "------------------------------------------------------------------------"
    echo "[$label] Running tests with $workers workers..."
    echo "------------------------------------------------------------------------"

    # タイムスタンプ記録
    start_time=$(date +%s)

    # テスト実行
    if [ "$workers" = "serial" ]; then
        # シリアル実行（並列なし）
        docker exec keikakun_app-backend-1 pytest tests/ -q $EXCLUDE_MARKERS 2>&1 | tee -a "$RESULTS_FILE"
    else
        # 並列実行
        docker exec keikakun_app-backend-1 pytest tests/ -n $workers -q $EXCLUDE_MARKERS 2>&1 | tee -a "$RESULTS_FILE"
    fi

    # 終了タイムスタンプ
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    echo ""
    echo "⏱️  Duration: ${duration}s"
    echo ""

    # 結果ファイルに記録
    {
        echo "Duration: ${duration}s"
        echo ""
    } >> "$RESULTS_FILE"
}

# ベンチマーク実行
echo "Starting benchmark..."
echo ""

# 1. シリアル実行（ベースライン）
run_benchmark "serial" "Baseline (Serial)"

# 2. 2並列
run_benchmark "2" "2 Workers"

# 3. 4並列
run_benchmark "4" "4 Workers"

# 4. 8並列
run_benchmark "8" "8 Workers"

# 5. 12並列
run_benchmark "12" "12 Workers"

# 6. 16並列（高負荷テスト）
run_benchmark "16" "16 Workers (High Load)"

# 7. Auto（自動調整）
run_benchmark "auto" "Auto (Dynamic)"

# ベンチマーク完了
echo "========================================================================"
echo "Benchmark Complete!"
echo "========================================================================"
echo ""
echo "Results saved to: $RESULTS_FILE"
echo ""

# 結果サマリーを表示
echo "Summary:"
echo "------------------------------------------------------------------------"
grep -A 1 "Running tests" "$RESULTS_FILE" | grep -E "(Running|Duration)" || true
echo "========================================================================"
