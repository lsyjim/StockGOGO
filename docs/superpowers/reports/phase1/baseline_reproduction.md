# Step 0：Baseline Reproduction（基準重現）

> **閘門任務**：用現行 production code 原封不動（含 Breakout Priority 已知 bug、
> 不改任何規則）重跑全歷史，核對是否重現 bp11 已知數字。
> 未通過則不得進行 B1/B2/B3。

- 樣本期間 2019-08-28 → 2026-06-09｜universe 82 檔｜訊號 130993 筆｜walk-forward ✅（逐 as_of 切片）｜OOS：全期樣本內重放（非切分 OOS）
- 資料重用：`--reuse-data`（凍結價格快取 `_histcache_7e9dcd08c3.pkl`，與 bp11 同一份，MD5 鍵由 `HISTORY_START_DATE=2019-06-01` 決定）
- 旗標狀態：`BP11_MLITE=False`、`BP11_RSI_MOM=85`（無豁免）、`BP11_THEME=False` —— 與 bp11 baseline 完全一致
- `R_TRACK_ENABLED=True`（bp12 後新增）：經程式碼確認僅**附加** `r_signal`/`r_strength` 欄位於 row，不參與 grade 判定，故不影響本比對

### 成本模型參數（全部任務共用，不得單獨改動）

- `ENABLE_COST_MODEL` = `True`
- `COMMISSION_RATE` = `0.001425`
- `TAX_RATE` = `0.003`
- `SLIPPAGE_MODEL` = `vol_liq`
- `SLIPPAGE_BASE` = `0.001`
- `SLIPPAGE_K1` = `0.5`
- `SLIPPAGE_K2` = `0.1`


## 逐項比對

| 指標 | bp11 已知值 | 本次重跑 | 差異 | 一致 |
|---|---|---|---|---|
| A 級樣本數 | 1,305 | 1,305 | +0 | ✅ |
| A 級20日期望值 | +3.36% | +3.360% | -0.000 | ✅ |
| B 級樣本數 | 12,459 | 12,459 | +0 | ✅ |
| B 級20日期望值 | +2.41% | +2.408% | -0.000 | ✅ |
| C 級樣本數 | 30,840 | 30,840 | +0 | ✅ |
| C 級20日期望值 | +1.90% | +1.904% | +0.000 | ✅ |
| 總訊號數 | 130,993 | 130,993 | +0 | ✅ |

## 結論

**✅ 完全重現** —— 六項指標與總樣本數全部逐位吻合，無任何差異。
基準已確立，B1/B2/B3 可在此凍結資料上進行。

重現成功的關鍵條件（供日後複現）：
1. 同一份價格快取（`--reuse-data`），避免 yfinance 歷史修訂造成漂移
2. 三個 bp11 旗標維持預設關閉
3. R_TRACK 雖預設開啟，但與動能評級完全隔離

### 過程中發現（如實記錄）

- `backtest_results/bp11_expanded/trades.csv` 磁碟現存檔案**並非 baseline**，
  而是 bp11 第二輪 variant（`BP11_RSI_MOM=92`）的輸出（B 級 12,401 筆，
  對應 bp11 報告內「12459 → 12401」那一列）——baseline 輸出當時被覆蓋。
  本次是以現行 code 重新產生 baseline，而非直接讀舊檔，故此比對為真實重跑。
- bp11 報告文字記載 universe 為 81 檔，實際凍結資料為 **82 檔**；
  因兩者用的是同一份快取，不影響數字一致性，僅為文件筆誤。
