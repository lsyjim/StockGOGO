# 權重調整循環規範（build_prompt_10 任務5）

評分權重/門檻的調整**必須數據驅動、可回溯、一次一變數**。禁止憑感覺改權重。

## 前置：方法論鐵律（多重比較陷阱）

對數十個指標組合暴力搜尋，最高勝率那格極可能是雜訊。
（本專案實例：頭肩底標籤 n=15 時勝率 80%，另兩輪掉到 48% / 36%。）

**採納門檻 = 分位單調性 + 時間雙半穩定（|ρ|≥0.5）+ 分位差≥1.0 + n≥30。**
嚴禁以單格最高勝率為調整依據。

## 循環步驟

1. **產生歸因**
   ```
   python signal_backtest.py --days 0 --hold 5,10,20 --symbols <清單> --out backtest_results/base
   python factor_attribution.py --trades backtest_results/base/trades.csv
   ```
   從 `factor_report.md`「權重調整候選清單」挑**一個**候選（同時滿足單調 + 穩定 + 分位差門檻）。

2. **一次只改一組權重**
   - 在 `config.py` 對應權重旁註記 baseline commit hash（`git rev-parse --short HEAD`）與改動理由。
   - 只改這一組，其他不動。

3. **重跑 walk-forward**
   ```
   python signal_backtest.py --days 0 --hold 5,10,20 --symbols <同一清單> --out backtest_results/trial
   ```

4. **期望值矩陣對比**
   - 比 `base/summary.md` 與 `trial/summary.md` 的等級×持有期期望值矩陣。
   - 也看分 regime（多頭/盤整/空頭）是否一致改善——**不可只在多頭改善就採納**。

5. **採納 / 還原**
   - A 級 10/20 日期望值提升且**跨 regime 一致**、單調性維持 → 採納，貼對比報告到 commit。
   - 任一 regime 惡化或只在單一窗口改善 → **還原**（git revert 該次權重改動），記錄「不採納 + 數據」。

## 反例守則

- 只改善多頭、盤整/空頭惡化 → 過度擬合多頭窗口，還原。
- 樣本 n<30 的因子 → 不得作為調整依據（factor_report 已列灰字附錄）。
- 單格勝率極高但非單調 → 雜訊，還原。

## 相關產出

- `factor_report.md`：因子排行榜 + 候選清單（factor_attribution.py）
- `summary.md`：等級×持有期期望值矩陣 + 分 regime（signal_backtest.py）
- `sell_wait_regime.md`：SELL/WAIT 分 regime 反向驗證
- `experiment_bp10.md`：連買窗口提純 / WAIT 動能豁免實驗
