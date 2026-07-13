# -*- coding: utf-8 -*-
"""
import_power_watchlist_v2.py —— 直寫版（不經過 database.py）
單一連線、busy timeout 30 秒、INSERT OR IGNORE 防重複。
放在專案根目錄執行：python import_power_watchlist_v2.py
"""
import sqlite3, datetime, os, sys

DB = "watchlist_v4.db"

STOCKS = [
    # (代號, 名稱, 族群)
    ("2481", "強茂",   "功率元件"), ("5425", "台半",   "功率元件"),
    ("3675", "德微",   "功率元件"), ("2342", "茂矽",   "功率元件"),
    ("6435", "大中",   "功率元件"), ("8261", "富鼎",   "功率元件"),
    ("5299", "杰力",   "功率元件"), ("3317", "尼克森", "功率元件"),
    ("8255", "朋程",   "功率元件"), ("2434", "統懋",   "功率元件"),
    ("6761", "穩得",   "功率元件"), ("6415", "矽力-KY","功率元件"),
    ("6138", "茂達",   "功率元件"), ("8081", "致新",   "功率元件"),
    ("6719", "力智",   "功率元件"), ("3588", "通嘉",   "功率元件"),
    ("6525", "捷敏-KY","功率元件"), ("2369", "菱生",   "功率元件"),
    ("5347", "世界",   "功率元件"), ("2351", "順德",   "功率元件"),
    ("5285", "界霖",   "功率元件"), ("6573", "虹揚-KY","功率元件"),
    ("3707", "漢磊",   "第三代半導體"), ("3016", "嘉晶", "第三代半導體"),
]
NOTES = "股癌EP671-676 MOSFET題材 2026-07"

def main():
    if not os.path.exists(DB):
        sys.exit(f"找不到 {DB}，請在 StockGOGO 專案根目錄執行。")

    conn = sqlite3.connect(DB, timeout=30)          # 最多等 30 秒
    conn.execute("PRAGMA busy_timeout=30000")
    cur = conn.cursor()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("SELECT COALESCE(MAX(sort_order), -1) FROM watchlist")
    order = cur.fetchone()[0]

    added, skipped = [], []
    for code, name, group in STOCKS:
        order += 1
        cur.execute("""
            INSERT OR IGNORE INTO watchlist
                (symbol, name, market, added_date, notes,
                 recommendation, sort_order, industry)
            VALUES (?, ?, '台股', ?, ?, '待分析', ?, ?)
        """, (code, name, now, NOTES, order, group))
        (added if cur.rowcount else skipped).append(f"{code} {name}")

    conn.commit()

    # 驗收：26 檔應全部在庫
    q = ",".join("?" * len(STOCKS))
    cur.execute(f"SELECT COUNT(*) FROM watchlist WHERE symbol IN ({q})",
                [s[0] for s in STOCKS])
    in_db = cur.fetchone()[0]
    conn.close()

    print(f"新增 {len(added)} 檔：{', '.join(added) if added else '無'}")
    print(f"已存在跳過 {len(skipped)} 檔：{', '.join(skipped) if skipped else '無'}")
    print(f"\n驗收：清單 {len(STOCKS)} 檔中，目前庫內共 {in_db} 檔 "
          f"{'✅ 全數到位' if in_db == len(STOCKS) else '❌ 有缺，把這段輸出貼給 Claude'}")
    print("下一步：開 main.py → 點工具列「Scan」開始掃描。")

if __name__ == "__main__":
    main()
