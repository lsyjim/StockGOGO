#!/usr/bin/env bash
# build_prompt_11 A/B 驗證 orchestrator
# 一次一變數：baseline（全關）+ 三單變數輪。R4（最優組合）依 r1-r3 結果另跑。
# baseline 不帶 --reuse-data → 抓取並凍結價格快取；其餘輪 --reuse-data 用同一凍結資料，
# 保證各輪只差「一個 config 旗標」，資料完全一致。
set -u
cd "$(dirname "$0")"
BASE_ARGS=(--days 0 --hold 5,10,20)

run() {
  local name="$1"; shift
  local out="backtest_results/bp11_${name}"
  echo "==================== ROUND ${name} @ $(date '+%F %T') ===================="
  python -c "from config import QuantConfig as Q; print('  config → MLITE=%s RSI_MOM=%s THEME=%s' % (Q.MLITE_RANGE_ENABLED,Q.SAFETY_VALVE_RSI_MOM,Q.THEME_GRADE_ENABLED))"
  python signal_backtest.py "${BASE_ARGS[@]}" --out "${out}" "$@"
  echo "---- ${name} done rc=$? @ $(date '+%F %T') → ${out}/summary.md"
}

# Baseline：全關（RSI_MOM=85 → 無豁免）。不帶 --reuse-data → 建立凍結快取。
export BP11_RSI_MOM=85; unset BP11_MLITE BP11_THEME
run baseline

# R1 M-Lite only：MLITE on，RSI_MOM=85（豁免關），THEME off
export BP11_MLITE=1 BP11_RSI_MOM=85; unset BP11_THEME
run r1_mlite --reuse-data

# R2 RSI only：MLITE off，RSI_MOM=92（豁免開），THEME off
export BP11_RSI_MOM=92; unset BP11_MLITE BP11_THEME
run r2_rsi --reuse-data

# R3 theme only：MLITE off，RSI_MOM=85（豁免關），THEME on
export BP11_THEME=1 BP11_RSI_MOM=85; unset BP11_MLITE
run r3_theme --reuse-data

echo "==================== A/B baseline+r1+r2+r3 完成 @ $(date '+%F %T') ===================="
