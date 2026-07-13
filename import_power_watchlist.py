# -*- coding: utf-8 -*-
"""
import_power_watchlist.py
把功率元件題材 26 檔批次匯入 StockGOGO 自選股（watchlist_v4.db）
放在 StockGOGO 專案根目錄執行：python import_power_watchlist.py
- 已存在的股票自動跳過（靠 UNIQUE 約束，不會重複）
- 族群欄位直接標「功率元件」/「第三代半導體」，與 theme_map.json 對齊
"""
from database import WatchlistDatabase

POWER = {
    # IDM
    "2481": "強茂", "5425": "台半", "3675": "德微", "2342": "茂矽",
    # MOSFET / 二極體
    "6435": "大中", "8261": "富鼎", "5299": "杰力", "3317": "尼克森",
    "8255": "朋程", "2434": "統懋", "6761": "穩得",
    # PMIC
    "6415": "矽力-KY", "6138": "茂達", "8081": "致新", "6719": "力智", "3588": "通嘉",
    # 功率封測
    "6525": "捷敏-KY", "2369": "菱生",
    # 週邊
    "5347": "世界", "2351": "順德", "5285": "界霖", "6573": "虹揚-KY",
}
SIC = {"3707": "漢磊", "3016": "嘉晶"}

def main():
    db = WatchlistDatabase()
    added, skipped = [], []
    for group, table in (("功率元件", POWER), ("第三代半導體", SIC)):
        for code, name in table.items():
            ok = db.add_stock(code, name, market="台股",
                              notes="股癌EP671-676 MOSFET題材 2026-07",
                              industry=group)
            (added if ok else skipped).append(f"{code} {name}")
    print(f"\n新增 {len(added)} 檔：{', '.join(added) if added else '無'}")
    print(f"已存在跳過 {len(skipped)} 檔：{', '.join(skipped) if skipped else '無'}")
    print("\n完成。開啟 main.py 後對自選股執行「批次刷新量化分析」即可。")

if __name__ == "__main__":
    main()
