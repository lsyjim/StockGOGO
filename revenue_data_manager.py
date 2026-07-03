"""
revenue_data_manager.py — 月營收動能資料層（FinMind TaiwanStockMonthRevenue）

模式比照 chip_data_manager.ChipDataManager：FinMind 抓取 → SQLite 落地 → 讀 DB 算指標。
台股月營收每月 10 日前強制揭露，是台灣市場特有的高頻基本面優勢（FinLab 實證：
投信買超 + 營收創12月新高 + YoY>20% + 300張均量 的交集，含成本回測年化 33.9%）。

語意：revenue 為 NULL = 未取得；revenue_month key = 'YYYY-MM'（營收所屬月份，
非公告日）。FinMind 回傳 revenue_year / revenue_month（int）即營收歸屬年月。

Token：只從環境變數 FINMIND_TOKEN 讀，絕不寫死。
"""

from __future__ import annotations

import os
import time
import sqlite3
import datetime

import requests


FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


class RevenueDataManager:
    """月營收資料管理器：抓取 → 落地 → 讀 DB 算 YoY / 創12月高。"""

    def __init__(self, db_name: str = "watchlist_v4.db"):
        self.db_name = db_name
        self.token = os.environ.get("FINMIND_TOKEN", "")
        self._ensure_schema()

    def _conn(self):
        return sqlite3.connect(self.db_name)

    def _ensure_schema(self):
        conn = self._conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS revenue_monthly (
                symbol        TEXT NOT NULL,
                revenue_month TEXT NOT NULL,   -- 'YYYY-MM'（營收所屬月份）
                revenue       INTEGER,          -- 元；NULL=未取得
                PRIMARY KEY (symbol, revenue_month)
            )
        ''')
        conn.commit()
        conn.close()

    # ── FinMind ──────────────────────────────────────────────────────────
    def _finmind_get(self, params: dict):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = requests.get(FINMIND_URL, params=params, headers=headers, timeout=25)
            if r.status_code in (402, 429):
                print(f"[Revenue] FinMind 額度超限（HTTP {r.status_code}）")
                return None
            if r.status_code != 200:
                print(f"[Revenue] FinMind HTTP {r.status_code}")
                return None
            payload = r.json()
            if payload.get("status") != 200:
                print(f"[Revenue] status={payload.get('status')} msg={payload.get('msg')}")
                return None
            return payload.get("data") or None
        except Exception as e:
            print(f"[Revenue] 請求錯誤: {e}")
            return None

    def backfill(self, symbol, months: int = 24):
        """一檔一請求，抓近 months 個月營收 upsert。回傳寫入筆數。"""
        symbol = str(symbol)
        end = datetime.date.today()
        start = end - datetime.timedelta(days=int(months * 31) + 40)
        data = self._finmind_get({
            "dataset": "TaiwanStockMonthRevenue",
            "data_id": symbol,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        })
        if not data:
            return 0
        conn = self._conn()
        cur = conn.cursor()
        n = 0
        for row in data:
            ry = row.get("revenue_year")
            rm = row.get("revenue_month")
            rev = row.get("revenue")
            if ry is None or rm is None:
                continue
            key = f"{int(ry):04d}-{int(rm):02d}"
            cur.execute(
                "INSERT OR REPLACE INTO revenue_monthly (symbol, revenue_month, revenue) VALUES (?, ?, ?)",
                (symbol, key, int(rev) if rev is not None else None),
            )
            n += 1
        conn.commit()
        conn.close()
        return n

    def monthly_update(self, symbols: list):
        """
        月更：對 watchlist 逐檔補當月營收（每月 10–12 日執行一次）。
        當月已有資料則跳過，避免重複打 API。回傳補齊檔數。
        """
        if not symbols:
            return 0
        this_month = datetime.date.today().strftime("%Y-%m")
        # 營收公告有一個月遞延：本月公告的是「上個月」營收
        last_month = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
        updated = 0
        for sym in symbols:
            sym = str(sym)
            if self._has_month(sym, last_month):
                continue
            if self.backfill(sym, months=3) > 0:
                updated += 1
            time.sleep(0.2)
        return updated

    def _has_month(self, symbol, month_key):
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM revenue_monthly WHERE symbol=? AND revenue_month=? AND revenue IS NOT NULL",
            (str(symbol), month_key),
        ).fetchone()
        conn.close()
        return row is not None

    # ── 指標（讀 DB，不打 API）─────────────────────────────────────────────
    def _load_series(self, symbol):
        """回傳 [(month_key, revenue)]，由新到舊，僅非 NULL。"""
        conn = self._conn()
        rows = conn.execute(
            "SELECT revenue_month, revenue FROM revenue_monthly "
            "WHERE symbol=? AND revenue IS NOT NULL ORDER BY revenue_month DESC",
            (str(symbol),),
        ).fetchall()
        conn.close()
        return rows

    def get_revenue_momentum(self, symbol) -> dict:
        """
        讀 DB 計算月營收動能指標（零 API）。

        回傳 {
          'available': bool, 'latest_month': 'YYYY-MM'|None, 'revenue': int|None,
          'revenue_yoy': float|None,      # 最新月 / 去年同月 − 1（去年同月缺→None）
          'is_12m_high': bool,            # 最新月營收 == 近12月最大
          'yoy_3m_avg': float|None,       # 近3月 yoy 平均
        }
        """
        rows = self._load_series(symbol)
        if not rows:
            return {"available": False, "latest_month": None, "revenue": None,
                    "revenue_yoy": None, "is_12m_high": False, "yoy_3m_avg": None}

        rev_map = {m: r for m, r in rows}          # month_key -> revenue
        latest_month, latest_rev = rows[0]

        def yoy_for(month_key):
            y, mo = month_key.split("-")
            prev_key = f"{int(y) - 1:04d}-{mo}"
            prev = rev_map.get(prev_key)
            if prev and prev > 0:
                return round(rev_map[month_key] / prev - 1, 4)
            return None

        revenue_yoy = yoy_for(latest_month)

        last12 = [r for _, r in rows[:12]]
        is_12m_high = bool(last12 and latest_rev == max(last12))

        yoys = [yoy_for(m) for m, _ in rows[:3]]
        yoys = [y for y in yoys if y is not None]
        yoy_3m_avg = round(sum(yoys) / len(yoys), 4) if yoys else None

        return {
            "available": True,
            "latest_month": latest_month,
            "revenue": latest_rev,
            "revenue_yoy": revenue_yoy,
            "is_12m_high": is_12m_high,
            "yoy_3m_avg": yoy_3m_avg,
        }


_manager_singleton = None


def get_revenue_manager(db_name: str = "watchlist_v4.db") -> RevenueDataManager:
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = RevenueDataManager(db_name)
    return _manager_singleton
