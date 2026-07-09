# -*- coding: utf-8 -*-
"""
export_scan_results.py
把「批次刷新量化分析」後落在 watchlist_v4.db 的結果匯出成 CSV
放在 StockGOGO 專案根目錄執行：python export_scan_results.py
輸出：power_scan_YYYYMMDD.csv（utf-8-sig，Excel 可直接開）
把這個 CSV 丟回對話給 Claude 分析即可。
"""
import sqlite3, csv, datetime, os

DB = "watchlist_v4.db"
GROUPS = ("功率元件", "第三代半導體")

def main():
    if not os.path.exists(DB):
        print(f"找不到 {DB}，請確認在 StockGOGO 專案根目錄執行。")
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT symbol, name, industry,
               COALESCE(quant_score, 0)   AS quant_score,
               COALESCE(trend_status, '') AS trend_status,
               COALESCE(chip_signal, '')  AS chip_signal,
               COALESCE(bias_20, 0)       AS bias_20,
               COALESCE(recommendation, '') AS recommendation
        FROM watchlist
        WHERE industry IN ({','.join('?'*len(GROUPS))})
        ORDER BY quant_score DESC
    """, GROUPS)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("查無資料：請先跑 import_power_watchlist.py，再於 main.py 執行批次刷新。")
        return

    out = f"power_scan_{datetime.date.today():%Y%m%d}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["代號", "名稱", "族群", "量化分數", "趨勢狀態",
                    "籌碼訊號", "20日乖離%", "系統評級"])
        w.writerows(rows)

    print(f"已匯出 {len(rows)} 檔 → {out}\n")
    print(f"{'代號':<6}{'名稱':<8}{'分數':>6}  {'趨勢':<10}{'評級'}")
    print("-" * 46)
    for r in rows:
        print(f"{r[0]:<6}{r[1]:<8}{r[3]:>6.1f}  {str(r[4]):<10}{r[7]}")

if __name__ == "__main__":
    main()
