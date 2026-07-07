"""
chip_data_manager.py — 籌碼資料層（FinMind 主源 + 官方備援 + 本地連買計算）

設計目標（取代舊 _analyze_chip_flow_wukong / _crawl_invest）：
  1. FinMind 為主源，資料落地 SQLite（chip_daily），單位一律「張」。
  2. 連買/連賣天數改為「依交易日曆本地計算」，而非 API 回傳筆數。
  3. 缺日偵測：交易日曆上該日無資料列或值為 NULL → 標記 reliable=False，
     列出 missing_dates。API 故障回 None（不以 0 填充），避免斷 streak。
  4. 語意鐵律：法人當日無動作 = 0（合法值，正常截斷 streak）；
             沒抓到資料 = NULL（缺日，reliable=False）。兩者不可混用。

資料來源：
  - 主源 FinMind：dataset=TaiwanStockInstitutionalInvestorsBuySell（上市＋上櫃全解決）
  - 交易日曆：dataset=TaiwanStockTradingDate（失敗 fallback 0050 TaiwanStockPrice 日期）
  - 官方備援（FinMind 掛掉才走）：
      上市 TWSE T86（rwd/zh/fund/T86, selectType=ALLBUT0999），欄位以 fields 名稱定位
      上櫃 TPEX OpenAPI（tpex_3insti_daily_trading，最新日全上櫃）

Token：只從環境變數 FINMIND_TOKEN 讀，絕不寫死。無 token 仍可運作（300 req/hr）。
"""

from __future__ import annotations

import os
import time
import json
import sqlite3
import datetime

import requests


FINMIND_URL       = "https://api.finmindtrade.com/api/v4/data"
TWSE_T86_URL      = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_OPENAPI_URL  = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
TPEX_HIST_URL     = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"

# build_prompt_09：FinMind 限流哨兵（與「查無資料」的 None 區分）
RATE_LIMITED = "RATE_LIMITED"

# FinMind 法人 name 欄位（實測 2330 確認的值集合）
_FM_FOREIGN = ("Foreign_Investor", "Foreign_Dealer_Self")   # 外資合計
_FM_TRUST   = ("Investment_Trust",)                          # 投信
_FM_DEALER  = ("Dealer_self", "Dealer_Hedging")             # 自營商合計


def _shares_to_lots(shares) -> int:
    """股 → 張（1 張 = 1000 股），四捨五入為整數。"""
    try:
        return int(round(float(shares) / 1000.0))
    except (TypeError, ValueError):
        return 0


class ChipDataManager:
    """籌碼資料管理器：抓取 → 落地 → 本地連買計算 → 統一出口 get_chip_flow。"""

    # 交易日曆上，最新端可容忍幾個「尚未公布」的交易日（法人資料盤後才更新）。
    # 這幾天的缺列視為「pending 未公布」而非「歷史缺口」，不判 reliable=False；
    # 超過此數的最新缺口，或錨定資料後任何內部缺口 → reliable=False。
    MAX_PENDING_LEAD = 2

    def __init__(self, db_name: str = "watchlist_v4.db"):
        self.db_name = db_name
        self.token = os.environ.get("FINMIND_TOKEN", "")
        self._ensure_schema()

    # ────────────────────────────────────────────────────────────────────
    # DB
    # ────────────────────────────────────────────────────────────────────
    def _conn(self):
        return sqlite3.connect(self.db_name)

    # build_prompt_06 任務0：買/賣分列欄位（單位張，NULL=未取得）
    _BUYSELL_COLS = ('foreign_buy', 'foreign_sell', 'trust_buy', 'trust_sell',
                     'dealer_buy', 'dealer_sell')

    def _ensure_schema(self):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chip_daily (
                symbol      TEXT NOT NULL,
                date        TEXT NOT NULL,
                foreign_net INTEGER,
                trust_net   INTEGER,
                dealer_net  INTEGER,
                source      TEXT,
                fetched_at  TEXT,
                PRIMARY KEY (symbol, date)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS trading_calendar (
                date   TEXT PRIMARY KEY,
                source TEXT
            )
        ''')
        # migration：舊表補買/賣分列欄位（INTEGER NULL），舊資料列保持 NULL
        cur.execute("PRAGMA table_info(chip_daily)")
        existing = {row[1] for row in cur.fetchall()}
        for col in self._BUYSELL_COLS:
            if col not in existing:
                try:
                    cur.execute(f"ALTER TABLE chip_daily ADD COLUMN {col} INTEGER")
                except sqlite3.OperationalError:
                    pass
        conn.commit()
        conn.close()

    def _upsert_chip(self, symbol, date, foreign_net, trust_net, dealer_net, source,
                     foreign_buy=None, foreign_sell=None, trust_buy=None, trust_sell=None,
                     dealer_buy=None, dealer_sell=None):
        """寫入單日籌碼。None 值以 NULL 落地（語意：未取得，非 0）。"""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO chip_daily
            (symbol, date, foreign_net, trust_net, dealer_net, source, fetched_at,
             foreign_buy, foreign_sell, trust_buy, trust_sell, dealer_buy, dealer_sell)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (str(symbol), date, foreign_net, trust_net, dealer_net, source,
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              foreign_buy, foreign_sell, trust_buy, trust_sell, dealer_buy, dealer_sell))
        conn.commit()
        conn.close()

    # ────────────────────────────────────────────────────────────────────
    # FinMind 客戶端
    # ────────────────────────────────────────────────────────────────────
    def _finmind_get(self, dataset: str, params: dict):
        """
        FinMind 通用 GET。build_prompt_09：
          - 冷卻中/達額度 → 回哨兵 RATE_LIMITED（呼叫端切官方備援，不發請求）
          - 收到 402/429 → 進入冷卻並回 RATE_LIMITED
          - 查無資料 → None（None 語意不變，抓不到 ≠ 0）
        """
        import finmind_budget as _fb
        if not _fb.before_request():
            return RATE_LIMITED
        q = {"dataset": dataset}
        q.update(params)
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = requests.get(FINMIND_URL, params=q, headers=headers, timeout=20)
            if r.status_code in (402, 429):
                print(f"[FinMind] 額度超限（HTTP {r.status_code}），dataset={dataset}")
                _fb.note_rate_limited()
                return RATE_LIMITED
            if r.status_code != 200:
                print(f"[FinMind] HTTP {r.status_code}，dataset={dataset}")
                return None
            payload = r.json()
            if payload.get("status") != 200:
                _msg = str(payload.get("msg", ""))
                # FinMind 以 status!=200 + 訊息表達額度超限
                if "limit" in _msg.lower() or "request" in _msg.lower() and "exceed" in _msg.lower():
                    print(f"[FinMind] 額度訊息：{_msg}")
                    _fb.note_rate_limited()
                    return RATE_LIMITED
                print(f"[FinMind] status={payload.get('status')} msg={_msg}")
                return None
            data = payload.get("data", [])
            return data if data else None
        except Exception as e:
            print(f"[FinMind] 請求錯誤 dataset={dataset}: {e}")
            return None

    def _fetch_finmind_chip(self, symbol, start_date, end_date):
        """
        抓 FinMind 法人買賣超，彙總為 {date: dict}（單位張）。失敗回 None。
        每日 dict 欄位：f_net/t_net/d_net + f_buy/f_sell/t_buy/t_sell/d_buy/d_sell。
        彙總規則同淨額：外資=Foreign_Investor+Foreign_Dealer_Self、自營=Dealer_self+Dealer_Hedging。
        """
        data = self._finmind_get(
            "TaiwanStockInstitutionalInvestorsBuySell",
            {"data_id": str(symbol), "start_date": start_date, "end_date": end_date},
        )
        if data == RATE_LIMITED:
            return RATE_LIMITED
        if not data:
            return None
        # 依日期彙總各法人 buy/sell（股）
        by_date = {}
        for row in data:
            d = row.get("date")
            name = row.get("name", "")
            buy = row.get("buy", 0) or 0
            sell = row.get("sell", 0) or 0
            slot = by_date.setdefault(d, {"fb": 0.0, "fs": 0.0, "tb": 0.0, "ts": 0.0, "db": 0.0, "ds": 0.0})
            if name in _FM_FOREIGN:
                slot["fb"] += buy; slot["fs"] += sell
            elif name in _FM_TRUST:
                slot["tb"] += buy; slot["ts"] += sell
            elif name in _FM_DEALER:
                slot["db"] += buy; slot["ds"] += sell
        out = {}
        for d, s in by_date.items():
            fb, fs = _shares_to_lots(s["fb"]), _shares_to_lots(s["fs"])
            tb, ts = _shares_to_lots(s["tb"]), _shares_to_lots(s["ts"])
            db, ds = _shares_to_lots(s["db"]), _shares_to_lots(s["ds"])
            out[d] = {
                "f_net": _shares_to_lots(s["fb"] - s["fs"]),
                "t_net": _shares_to_lots(s["tb"] - s["ts"]),
                "d_net": _shares_to_lots(s["db"] - s["ds"]),
                "f_buy": fb, "f_sell": fs, "t_buy": tb, "t_sell": ts,
                "d_buy": db, "d_sell": ds,
            }
        return out

    # ────────────────────────────────────────────────────────────────────
    # 交易日曆
    # ────────────────────────────────────────────────────────────────────
    def sync_calendar(self, lookback_days: int = 400):
        """同步台股交易日曆到 trading_calendar 表。回傳寫入筆數。"""
        end = datetime.date.today()
        start = end - datetime.timedelta(days=lookback_days)
        s_str, e_str = start.isoformat(), end.isoformat()

        days = None
        source = "finmind"
        data = self._finmind_get(
            "TaiwanStockTradingDate", {"start_date": s_str, "end_date": e_str}
        )
        if data:
            days = sorted({row["date"] for row in data if row.get("date")})
        else:
            # 備援：以 0050 的日 K 日期序列充當交易日曆
            print("[Calendar] TaiwanStockTradingDate 失敗，改用 0050 TaiwanStockPrice 日期")
            px = self._finmind_get(
                "TaiwanStockPrice",
                {"data_id": "0050", "start_date": s_str, "end_date": e_str},
            )
            if px:
                days = sorted({row["date"] for row in px if row.get("date")})
                source = "finmind_0050"

        if not days:
            print("[Calendar] 交易日曆同步失敗（FinMind 無回應）")
            return 0

        conn = self._conn()
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO trading_calendar (date, source) VALUES (?, ?)",
            [(d, source) for d in days],
        )
        conn.commit()
        conn.close()
        print(f"[Calendar] 同步 {len(days)} 個交易日（{source}）")
        return len(days)

    def get_trading_days_desc(self, limit: int = 120, as_of: str = None):
        """由新到舊回傳交易日（list[str]）。as_of 給定時只取 <= as_of（回測防前視）。"""
        conn = self._conn()
        cur = conn.cursor()
        if as_of:
            cur.execute(
                "SELECT date FROM trading_calendar WHERE date <= ? ORDER BY date DESC LIMIT ?",
                (as_of, limit),
            )
        else:
            cur.execute(
                "SELECT date FROM trading_calendar ORDER BY date DESC LIMIT ?", (limit,)
            )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows

    def get_latest_trading_day(self):
        days = self.get_trading_days_desc(limit=1)
        return days[0] if days else None

    # ────────────────────────────────────────────────────────────────────
    # backfill / daily_update
    # ────────────────────────────────────────────────────────────────────
    def backfill(self, symbol, trading_days: int = 90):
        """
        一次 FinMind 請求回填 ~trading_days 個交易日（start_date 往回推約 1.6 倍日曆日）。
        FinMind 掛掉時嘗試官方備援補「最新一日」。回傳寫入天數。
        """
        symbol = str(symbol)
        end = datetime.date.today()
        # 90 交易日 ≈ 128 日曆日，抓寬一點確保足量
        start = end - datetime.timedelta(days=int(trading_days * 1.6) + 20)
        chip = self._fetch_finmind_chip(symbol, start.isoformat(), end.isoformat())

        if chip and chip != RATE_LIMITED:
            # 只接受在交易日曆上的日期：FinMind 法人資料集偶有假日殘留列
            # （如端午節 2026-06-19），交易日曆（TradingDate）為權威來源。
            valid = set(self.get_trading_days_desc(limit=400))
            written = 0
            for d, v in chip.items():
                if valid and d not in valid:
                    continue
                self._upsert_chip(symbol, d, v["f_net"], v["t_net"], v["d_net"], "finmind",
                                  v["f_buy"], v["f_sell"], v["t_buy"], v["t_sell"],
                                  v["d_buy"], v["d_sell"])
                written += 1
            return written

        # build_prompt_09：FinMind 限流/無資料 → 官方歷史備援補「完整缺洞」（非只補最新日）
        reason = "限流" if chip == RATE_LIMITED else "FinMind 無資料"
        cal = self.get_trading_days_desc(limit=trading_days)
        if not cal:
            return 0
        have = self._existing_dates(symbol, min(cal))
        miss = set(cal) - have
        if not miss:
            return 0
        print(f"[Backfill] {symbol} {reason} → 官方歷史備援補 {len(miss)} 個缺洞")
        return self._backfill_official_range([symbol], {symbol: miss})

    def daily_update(self, symbols: list, holes: int = 5):
        """
        對 watchlist 逐檔補「最近 holes 個交易日」的洞（含節流 0.2s）。
        只補缺列/NULL 的日子，已有資料不重抓。回傳補齊的 (symbol,date) 數。
        """
        if not symbols:
            return 0
        recent_days = set(self.get_trading_days_desc(limit=holes))
        if not recent_days:
            # 無日曆先同步
            self.sync_calendar()
            recent_days = set(self.get_trading_days_desc(limit=holes))
        if not recent_days:
            return 0
        min_day = min(recent_days)
        end = datetime.date.today().isoformat()

        # 各 symbol 的缺洞
        need_map = {}
        for sym in symbols:
            sym = str(sym)
            need = recent_days - self._existing_dates(sym, min_day)
            if need:
                need_map[sym] = need
        if not need_map:
            return 0

        # build_prompt_09 任務5：大量補洞（≥門檻）或 FinMind 冷卻中 → 官方 per-date 為主源
        import finmind_budget as _fb
        try:
            from config import QuantConfig as _QC
            _bulk = _QC.CHIP_BULK_PREFER_GOV and len(need_map) >= _QC.CHIP_BULK_GOV_THRESHOLD
        except Exception:
            _bulk = False
        if _fb.is_cooling() or _bulk:
            _why = "FinMind 冷卻中" if _fb.is_cooling() else f"大量補洞（{len(need_map)}檔≥門檻）"
            print(f"[daily_update] {_why} → 官方 per-date 備援")
            return self._backfill_official_range(list(need_map), need_map)

        # 一般：逐檔 FinMind；遇限流即切官方備援補剩餘
        filled = 0
        rl_map = {}
        for sym, need in need_map.items():
            chip = self._fetch_finmind_chip(sym, min_day, end)
            if chip == RATE_LIMITED:
                rl_map[sym] = need
                continue
            if chip:
                for d in need:
                    if d in chip:
                        v = chip[d]
                        self._upsert_chip(sym, d, v["f_net"], v["t_net"], v["d_net"], "finmind",
                                          v["f_buy"], v["f_sell"], v["t_buy"], v["t_sell"],
                                          v["d_buy"], v["d_sell"])
                        filled += 1
            time.sleep(0.2)   # 控制在額度內
        if rl_map:
            print(f"[daily_update] FinMind 限流 → 官方備援補 {len(rl_map)} 檔剩餘缺洞")
            filled += self._backfill_official_range(list(rl_map), rl_map)
        return filled

    def _existing_dates(self, symbol, since_date):
        """回傳 symbol 在 since_date（含）之後、值非 NULL 的日期集合。"""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT date FROM chip_daily WHERE symbol=? AND date>=? AND foreign_net IS NOT NULL",
            (str(symbol), since_date),
        )
        out = {r[0] for r in cur.fetchall()}
        conn.close()
        return out

    # ────────────────────────────────────────────────────────────────────
    # 官方備援（FinMind 限流/故障才走）— build_prompt_09
    # 回傳 9 元組：(f_net,t_net,d_net,f_buy,f_sell,t_buy,t_sell,d_buy,d_sell)（張）
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _market_of(symbol):
        """twstock 市場別：'上市'/'上櫃'/None。"""
        try:
            import twstock
            info = twstock.codes.get(str(symbol))
            return getattr(info, "market", None) if info else None
        except Exception:
            return None

    def _gov_get(self, url, params, label):
        """官方端點請求禮儀：sleep(1.5~3.0) + UA + timeout=15 + 403/429 指數退避（≤3 次）。"""
        import random
        for attempt in range(3):
            try:
                time.sleep(random.uniform(1.5, 3.0))
                r = requests.get(
                    url, params=params, timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                )
                if r.status_code in (403, 429):
                    _w = (2 ** attempt) * 3
                    print(f"[官方備援] {label} HTTP {r.status_code}，退避 {_w}s（第{attempt+1}次）")
                    time.sleep(_w)
                    continue
                if r.status_code != 200:
                    return None
                return r.json()
            except Exception as e:
                print(f"[官方備援] {label} 錯誤: {e}")
                time.sleep(2 ** attempt)
        return None

    def _upsert9(self, symbol, date, v9, source):
        """以 9 元組寫入 chip_daily。"""
        self._upsert_chip(symbol, date, v9[0], v9[1], v9[2], source,
                          v9[3], v9[4], v9[5], v9[6], v9[7], v9[8])

    def _fetch_twse_t86(self, date_str):
        """
        TWSE T86（上市當日全體，任意歷史日期）。以 fields 名稱定位（名稱唯一），股→張。
        回傳 {symbol: 9元組} 或 None（整張失敗）。
        外資口徑對齊 FinMind：外陸資(不含外資自營) + 外資自營商。
        """
        ymd = date_str.replace("-", "")
        d = self._gov_get(TWSE_T86_URL,
                          {"date": ymd, "selectType": "ALLBUT0999", "response": "json"},
                          f"{date_str} T86")
        if not d or d.get("stat") != "OK" or not d.get("data"):
            return None
        fields = [str(f).strip() for f in d.get("fields", [])]

        def idx(name):
            for i, f in enumerate(fields):
                if f == name:
                    return i
            return None

        ix = {
            'fe_net': idx("外陸資買賣超股數(不含外資自營商)"),
            'fe_buy': idx("外陸資買進股數(不含外資自營商)"),
            'fe_sell': idx("外陸資賣出股數(不含外資自營商)"),
            'fs_net': idx("外資自營商買賣超股數"),
            'fs_buy': idx("外資自營商買進股數"),
            'fs_sell': idx("外資自營商賣出股數"),
            't_net': idx("投信買賣超股數"), 't_buy': idx("投信買進股數"), 't_sell': idx("投信賣出股數"),
            'd_net': idx("自營商買賣超股數"),
            'ds_buy': idx("自營商買進股數(自行買賣)"), 'ds_sell': idx("自營商賣出股數(自行買賣)"),
            'dh_buy': idx("自營商買進股數(避險)"), 'dh_sell': idx("自營商賣出股數(避險)"),
        }
        if None in (ix['fe_net'], ix['t_net'], ix['d_net']):
            print("[TWSE] T86 fields 定位失敗")
            return None

        def gi(row, key):
            i = ix.get(key)
            if i is None:
                return 0
            try:
                return int(str(row[i]).replace(",", "").strip() or 0)
            except (ValueError, IndexError):
                return 0

        out = {}
        for row in d["data"]:
            sym = str(row[0]).strip()
            f_net = gi(row, 'fe_net') + gi(row, 'fs_net')
            f_buy = gi(row, 'fe_buy') + gi(row, 'fs_buy')
            f_sell = gi(row, 'fe_sell') + gi(row, 'fs_sell')
            t_net, t_buy, t_sell = gi(row, 't_net'), gi(row, 't_buy'), gi(row, 't_sell')
            d_net = gi(row, 'd_net')
            d_buy = gi(row, 'ds_buy') + gi(row, 'dh_buy')
            d_sell = gi(row, 'ds_sell') + gi(row, 'dh_sell')
            out[sym] = tuple(_shares_to_lots(x) for x in
                             (f_net, t_net, d_net, f_buy, f_sell, t_buy, t_sell, d_buy, d_sell))
        return out

    def _fetch_tpex_hist(self, date_str):
        """
        TPEx 歷史三大法人（上櫃當日全體，任意歷史日期）。
        欄名重複 → 以「固定位置」映射，並用最末欄「三大法人合計」錨點驗證（防位置漂移）。
        位置：外資含自營合計 idx8-10；投信 idx11-13；自營合計 idx20-22；合計 idx23。
        回傳 {symbol: 9元組} 或 None。
        """
        y, m, dd = date_str.split("-")
        roc = f"{int(y) - 1911}/{m}/{dd}"   # 民國年/MM/DD（常見雷點，單元測試鎖住）
        ymd = date_str.replace("-", "")
        d = self._gov_get(TPEX_HIST_URL, {"l": "zh-tw", "d": roc, "se": "EW", "t": "D"},
                          f"{date_str} TPEx")
        if not d or str(d.get("stat", "")).lower() != "ok":
            return None
        # 日期校驗：回應日期需與請求日一致（避免無資料日回退最新日）
        if str(d.get("date", "")).strip() not in (ymd, ""):
            return None
        tables = d.get("tables") or []
        if not tables or not tables[0].get("data"):
            return None
        rows = tables[0]["data"]

        def gi(row, i):
            try:
                return int(str(row[i]).replace(",", "").strip() or 0)
            except (ValueError, IndexError):
                return 0

        out = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 24:
                continue
            sym = str(row[0]).strip()
            f_buy, f_sell, f_net = gi(row, 8), gi(row, 9), gi(row, 10)
            t_buy, t_sell, t_net = gi(row, 11), gi(row, 12), gi(row, 13)
            d_buy, d_sell, d_net = gi(row, 20), gi(row, 21), gi(row, 22)
            total = gi(row, 23)
            # 錨點驗證：三法人淨額和 == 合計欄（不符 → 位置漂移，跳過該列）
            if abs((f_net + t_net + d_net) - total) > max(1, abs(total) * 0.001):
                continue
            out[sym] = tuple(_shares_to_lots(x) for x in
                             (f_net, t_net, d_net, f_buy, f_sell, t_buy, t_sell, d_buy, d_sell))
        return out

    def _fetch_tpex_openapi(self):
        """TPEX OpenAPI（上櫃最新日；保留供最新日備援）。回傳 (date_str, {symbol:9元組}) 或 None。"""
        try:
            r = requests.get(TPEX_OPENAPI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if r.status_code != 200:
                return None
            data = r.json()
            if not isinstance(data, list) or not data:
                return None

            def norm(k):
                return "".join(str(k).split())

            sample = data[0]
            keymap = {norm(k): k for k in sample.keys()}

            def gv(row, nk):
                real = keymap.get(nk)
                if real is None:
                    return 0
                try:
                    return int(str(row.get(real, 0)).replace(",", "").strip() or 0)
                except ValueError:
                    return 0

            k_fore = norm("Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference")
            k_foredl = norm("ForeignDealers-Difference")
            k_trust = norm("SecuritiesInvestmentTrustCompanies-Difference")
            k_dealer = norm("Dealers-Difference")
            date_str = self._roc_to_iso(str(sample.get("Date", "")).strip())
            out = {}
            for row in data:
                sym = str(row.get("SecuritiesCompanyCode", "")).strip()
                if not sym:
                    continue
                fore = gv(row, k_fore) + gv(row, k_foredl)
                trust = gv(row, k_trust)
                dealer = gv(row, k_dealer)
                # OpenAPI 無買/賣分列 → buy/sell 補 None
                out[sym] = (_shares_to_lots(fore), _shares_to_lots(trust), _shares_to_lots(dealer),
                            None, None, None, None, None, None)
            return (date_str, out) if date_str else None
        except Exception as e:
            print(f"[TPEX] OpenAPI 抓取錯誤: {e}")
            return None

    @staticmethod
    def _roc_to_iso(roc):
        """民國日期 '1150703' → '2026-07-03'。"""
        roc = str(roc).strip()
        if len(roc) == 7 and roc.isdigit():
            y = int(roc[:3]) + 1911
            return f"{y}-{roc[3:5]}-{roc[5:7]}"
        return roc

    def _backfill_official_range(self, symbols, missing):
        """
        歷史備援路由（核心）：對各 symbol 的缺洞日期，per-date 一次 T86/TPEx 請求服務所有股票。
        missing: {symbol: set(dates)}。回傳寫入筆數。
        真零原則：整張表抓成功但表中查無該股 → 寫 0（當日無法人活動）；
        整張表抓失敗 → 不寫，維持缺洞（None 原則，嚴禁以 0 填充）。
        """
        from collections import defaultdict
        date_to_syms = defaultdict(set)
        for sym, dates in missing.items():
            for dd in dates:
                date_to_syms[dd].add(str(sym))
        valid_cal = set(self.get_trading_days_desc(limit=800))
        written = 0
        for dd in sorted(date_to_syms):
            if valid_cal and dd not in valid_cal:
                continue   # 假日殘留防線
            syms = set(date_to_syms[dd])
            listed = {s for s in syms if self._market_of(s) != '上櫃'}   # 上市 + 未知
            otc = {s for s in syms if self._market_of(s) == '上櫃'}
            # 上市（+未知）→ T86 一次服務全體
            if listed:
                t86 = self._fetch_twse_t86(dd)
                if t86 is not None:
                    n = 0
                    for s in list(listed):
                        v = t86.get(s)
                        if v is None:
                            if self._market_of(s) is None:
                                otc.add(s)   # 未知且 T86 查無 → 改試 TPEx
                                continue
                            v = (0, 0, 0, 0, 0, 0, 0, 0, 0)   # 上市真零
                        self._upsert9(s, dd, v, "t86")
                        written += 1; n += 1
                    print(f"[官方備援] {dd} T86 ✓ 覆蓋 {n} 檔")
            # 上櫃 → TPEx 一次服務全體
            if otc:
                tp = self._fetch_tpex_hist(dd)
                if tp is not None:
                    n = 0
                    for s in otc:
                        v = tp.get(s) or (0, 0, 0, 0, 0, 0, 0, 0, 0)   # 表中查無 → 真零
                        self._upsert9(s, dd, v, "tpex_hist")
                        written += 1; n += 1
                    print(f"[官方備援] {dd} TPEx ✓ 覆蓋 {n} 檔")
        return written

    def _backfill_official_latest(self, symbol):
        """補最新一日（委派 _backfill_official_range）。回傳 0/1+。"""
        latest = self.get_latest_trading_day() or datetime.date.today().isoformat()
        return self._backfill_official_range([str(symbol)], {str(symbol): {latest}})

    # ────────────────────────────────────────────────────────────────────
    # 本地連買/連賣計算（依交易日曆）
    # ────────────────────────────────────────────────────────────────────
    def _load_chip_rows(self, symbol, dates):
        """回傳 {date: {'foreign','trust','dealer'}}；缺列不進 dict。"""
        if not dates:
            return {}
        conn = self._conn()
        cur = conn.cursor()
        qmarks = ",".join("?" * len(dates))
        cur.execute(
            f"SELECT date, foreign_net, trust_net, dealer_net FROM chip_daily "
            f"WHERE symbol=? AND date IN ({qmarks})",
            [str(symbol), *dates],
        )
        out = {}
        for d, f, t, dl in cur.fetchall():
            out[d] = {"foreign": f, "trust": t, "dealer": dl}
        conn.close()
        return out

    def get_consecutive_days(self, symbol, who: str = "foreign", as_of: str = None) -> dict:
        """
        由 trading_calendar 最新交易日往回走計算連買/連賣天數。
        as_of 給定時，最新交易日 = as_of（含）以前（回測防前視）。

        規則：
          - 最新端連續缺列（尚未公布）≤ MAX_PENDING_LEAD → 視為 pending，跳過不判缺日。
          - 錨定到第一筆有資料日後：某交易日無列或值為 NULL → 停止，reliable=False，
            記 missing_dates。
          - 值為 0 或方向反轉 → 正常終止 streak，reliable=True。

        回傳 {'days': int（正=連買, 負=連賣）, 'reliable': bool,
              'missing_dates': [...], 'last_date': str|None}
        """
        cal = self.get_trading_days_desc(limit=120, as_of=as_of)
        if not cal:
            return {"days": 0, "reliable": False, "missing_dates": [], "last_date": None}

        rows = self._load_chip_rows(symbol, cal)

        missing = []
        anchored = False
        pending_lead = 0
        direction = None      # +1 買, -1 賣, 0 平
        streak = 0
        last_date = None

        for d in cal:
            row = rows.get(d)
            val = row.get(who) if row else None

            if val is None:
                if not anchored:
                    # 最新端尚未錨定：容忍 pending 未公布
                    pending_lead += 1
                    if pending_lead > self.MAX_PENDING_LEAD:
                        missing.append(d)
                        return {"days": _signed(direction, streak), "reliable": False,
                                "missing_dates": missing, "last_date": last_date}
                    continue
                else:
                    # 已錨定後的缺口 → 不可信
                    missing.append(d)
                    return {"days": _signed(direction, streak), "reliable": False,
                            "missing_dates": missing, "last_date": last_date}

            # 有值
            if not anchored:
                anchored = True
                last_date = d
                if val > 0:
                    direction, streak = 1, 1
                elif val < 0:
                    direction, streak = -1, 1
                else:
                    direction, streak = 0, 0   # 最新日持平 → streak 0
                continue

            # 已錨定，往回延伸
            if val == 0:
                break                          # 0 合法截斷
            if direction == 1 and val > 0:
                streak += 1
            elif direction == -1 and val < 0:
                streak += 1
            else:
                break                          # 方向反轉

        return {"days": _signed(direction, streak), "reliable": True,
                "missing_dates": missing, "last_date": last_date}

    def _avg_net_5d(self, symbol, who="foreign", as_of: str = None):
        """近 5 交易日該法人日均淨額（張，signed）。缺日以現有資料平均。"""
        cal = self.get_trading_days_desc(limit=5, as_of=as_of)
        rows = self._load_chip_rows(symbol, cal)
        vals = [rows[d][who] for d in cal if d in rows and rows[d][who] is not None]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    def _latest_row(self, symbol, as_of: str = None):
        """最新一個有資料的交易日 row。回傳 (date, {'foreign','trust','dealer'}) 或 (None, None)。"""
        cal = self.get_trading_days_desc(limit=120, as_of=as_of)
        rows = self._load_chip_rows(symbol, cal)
        for d in cal:
            if d in rows and rows[d]["foreign"] is not None:
                return d, rows[d]
        return None, None

    def get_daily_detail(self, symbol, days: int = 10, as_of: str = None) -> list:
        """
        近 N 個交易日的買/賣/淨逐日明細（build_prompt_06 任務0）。

        由 trading_calendar 取最近 N 個交易日（新→舊），逐日回傳：
          {date, foreign_buy, foreign_sell, foreign_net, trust_buy, trust_sell,
           trust_net, dealer_net, total_net, is_missing}
        DB 無該日或 foreign_net 為 NULL → is_missing=True（其餘欄位 None）。
        """
        symbol = str(symbol)
        cal = self.get_trading_days_desc(limit=days, as_of=as_of)
        if not cal:
            return []
        conn = self._conn()
        cur = conn.cursor()
        qmarks = ",".join("?" * len(cal))
        cur.execute(
            f"SELECT date, foreign_net, trust_net, dealer_net, "
            f"foreign_buy, foreign_sell, trust_buy, trust_sell, dealer_buy, dealer_sell "
            f"FROM chip_daily WHERE symbol=? AND date IN ({qmarks})",
            [symbol, *cal],
        )
        rows = {r[0]: r for r in cur.fetchall()}
        conn.close()

        out = []
        for d in cal:
            r = rows.get(d)
            if r is None or r[1] is None:   # 無列 或 foreign_net NULL
                out.append({"date": d, "is_missing": True,
                            "foreign_buy": None, "foreign_sell": None, "foreign_net": None,
                            "trust_buy": None, "trust_sell": None, "trust_net": None,
                            "dealer_net": None, "total_net": None})
                continue
            (_d, f_net, t_net, d_net, f_buy, f_sell, t_buy, t_sell, _db, _ds) = r
            total = sum(x for x in (f_net, t_net, d_net) if x is not None)
            out.append({
                "date": d, "is_missing": False,
                "foreign_buy": f_buy, "foreign_sell": f_sell, "foreign_net": f_net,
                "trust_buy": t_buy, "trust_sell": t_sell, "trust_net": t_net,
                "dealer_net": d_net, "total_net": total,
            })
        return out

    # ────────────────────────────────────────────────────────────────────
    # 統一出口
    # ────────────────────────────────────────────────────────────────────
    def get_chip_flow(self, symbol, allow_fetch: bool = True, as_of: str = None) -> dict:
        """
        取代 QuickAnalyzer._analyze_chip_flow_cached 的統一出口。

        allow_fetch：
          True（單檔分析）— DB 無資料時先 backfill 再讀。
          False（掃描熱路徑）— 只讀 DB、零 API 呼叫（daily_update 已在掃描前批次補過）。
        as_of：回測用，只看該日（含）以前的籌碼（防前視）；此模式一律不觸發 backfill。
        """
        symbol = str(symbol)

        # 確保有日曆（讀 DB；空才同步）
        if allow_fetch and not as_of and not self.get_latest_trading_day():
            self.sync_calendar()

        # DB 無任何資料 → 視 allow_fetch 決定是否 backfill（as_of 回測模式不 backfill）
        latest_date, latest_row = self._latest_row(symbol, as_of=as_of)
        if latest_row is None and allow_fetch and not as_of:
            self.backfill(symbol, trading_days=90)
            latest_date, latest_row = self._latest_row(symbol, as_of=as_of)

        if latest_row is None:
            return {"available": False,
                    "message": "無法取得籌碼資料" + ("（FinMind/官方備援皆無回應）" if allow_fetch else "（DB 無資料）")}

        foreign_net = latest_row["foreign"] or 0
        trust_net   = latest_row["trust"] or 0
        dealer_net  = latest_row["dealer"] or 0

        f_streak = self.get_consecutive_days(symbol, "foreign", as_of=as_of)
        t_streak = self.get_consecutive_days(symbol, "trust", as_of=as_of)

        foreign_days = f_streak["days"]
        trust_days   = t_streak["days"]
        reliable     = bool(f_streak["reliable"] and t_streak["reliable"])
        missing      = sorted(set(f_streak["missing_dates"]) | set(t_streak["missing_dates"]))

        consecutive_buy_days  = max(foreign_days if foreign_days > 0 else 0,
                                    trust_days   if trust_days   > 0 else 0)
        consecutive_sell_days = max(-foreign_days if foreign_days < 0 else 0,
                                    -trust_days   if trust_days   < 0 else 0)

        avg_sell_net_5d = self._avg_net_5d(symbol, "foreign", as_of=as_of)

        # 顯示字串（沿用現有格式）
        foreign_text, foreign_signal = _fmt_streak(foreign_days, foreign_net)
        trust_text,   trust_signal   = _fmt_streak(trust_days, trust_net)
        dealer_text = "買超" if dealer_net > 0 else ("賣超" if dealer_net < 0 else "觀望")

        # 綜合訊號（沿用現有規則）
        if foreign_signal == "偏多" and trust_signal == "偏多":
            signal, signal_color = "籌碼集中", "positive"
        elif foreign_signal == "偏多" or trust_signal == "偏多":
            signal, signal_color = "籌碼偏多", "positive"
        elif foreign_signal == "偏空" and trust_signal == "偏空":
            signal, signal_color = "籌碼分散", "warning"
        elif foreign_signal == "偏空" or trust_signal == "偏空":
            signal, signal_color = "籌碼偏空", "warning"
        else:
            signal, signal_color = "籌碼中性", "neutral"

        msg = f"最新資料日期：{latest_date}（FinMind）"
        if not reliable and missing:
            msg += f"｜⚠️ 缺 {len(missing)} 日：{','.join(missing[:3])}"

        return {
            "available": True,
            "data_source": "finmind",
            "foreign_net": foreign_net,               # 張
            "trust_net": trust_net,
            "dealer_net": dealer_net,
            "foreign_consecutive_days": foreign_days,  # 正買負賣
            "trust_consecutive_days": trust_days,
            "consecutive_buy_days": consecutive_buy_days,
            "consecutive_sell_days": consecutive_sell_days,
            "avg_sell_net_5d": avg_sell_net_5d,        # 張，賣訊 3b 用
            "data_reliable": reliable,
            "missing_dates": missing,
            "foreign": f"{foreign_text} ({_fmt_lots(foreign_net)})",
            "trust":   f"{trust_text} ({_fmt_lots(trust_net)})",
            "dealer":  f"{dealer_text} ({_fmt_lots(dealer_net)})",
            "foreign_continuous": foreign_text,
            "trust_continuous": trust_text,
            "signal": signal,
            "signal_color": signal_color,
            "message": msg,
        }


# ── 模組層小工具 ─────────────────────────────────────────────────────────
def _signed(direction, streak):
    if not direction:
        return 0
    return streak * direction


def _fmt_lots(val):
    val = int(val or 0)
    if abs(val) >= 10000:
        return f"{val / 10000:.2f}萬張"
    return f"{val:,}張"


def _fmt_streak(days, net):
    """(顯示字串, 訊號) — 沿用舊 wukong 格式語意。"""
    if days > 0:
        if days >= 2:
            return f"連{days}日買超", "偏多"
        return "買超", "中性偏多"
    elif days < 0:
        n = abs(days)
        if n >= 2:
            return f"連{n}日賣超", "偏空"
        return "賣超", "中性偏空"
    else:
        # 持平或無方向
        if net > 0:
            return "買超", "中性偏多"
        elif net < 0:
            return "賣超", "中性偏空"
        return "觀望", "中性"


# 單例（與 QuickAnalyzer.get_db 同一 DB 檔）
_manager_singleton = None


def get_chip_manager(db_name: str = "watchlist_v4.db") -> ChipDataManager:
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = ChipDataManager(db_name)
    return _manager_singleton
