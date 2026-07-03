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
        conn.commit()
        conn.close()

    def _upsert_chip(self, symbol, date, foreign_net, trust_net, dealer_net, source):
        """寫入單日籌碼。None 值以 NULL 落地（語意：未取得，非 0）。"""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO chip_daily
            (symbol, date, foreign_net, trust_net, dealer_net, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (str(symbol), date, foreign_net, trust_net, dealer_net, source,
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    # ────────────────────────────────────────────────────────────────────
    # FinMind 客戶端
    # ────────────────────────────────────────────────────────────────────
    def _finmind_get(self, dataset: str, params: dict):
        """FinMind 通用 GET。回傳 data list；失敗回 None（不以 0 填充）。"""
        q = {"dataset": dataset}
        q.update(params)
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = requests.get(FINMIND_URL, params=q, headers=headers, timeout=20)
            if r.status_code in (402, 429):
                print(f"[FinMind] 額度超限（HTTP {r.status_code}），dataset={dataset}")
                return None
            if r.status_code != 200:
                print(f"[FinMind] HTTP {r.status_code}，dataset={dataset}")
                return None
            payload = r.json()
            if payload.get("status") != 200:
                print(f"[FinMind] status={payload.get('status')} msg={payload.get('msg')}")
                return None
            data = payload.get("data", [])
            return data if data else None
        except Exception as e:
            print(f"[FinMind] 請求錯誤 dataset={dataset}: {e}")
            return None

    def _fetch_finmind_chip(self, symbol, start_date, end_date):
        """
        抓 FinMind 法人買賣超，彙總為 {date: (foreign_net, trust_net, dealer_net)}（張）。
        失敗回 None。
        """
        data = self._finmind_get(
            "TaiwanStockInstitutionalInvestorsBuySell",
            {"data_id": str(symbol), "start_date": start_date, "end_date": end_date},
        )
        if not data:
            return None
        # 依日期彙總各法人 (buy - sell)（股）
        by_date: dict[str, dict[str, float]] = {}
        for row in data:
            d = row.get("date")
            name = row.get("name", "")
            net_shares = (row.get("buy", 0) or 0) - (row.get("sell", 0) or 0)
            slot = by_date.setdefault(d, {"f": 0.0, "t": 0.0, "d": 0.0})
            if name in _FM_FOREIGN:
                slot["f"] += net_shares
            elif name in _FM_TRUST:
                slot["t"] += net_shares
            elif name in _FM_DEALER:
                slot["d"] += net_shares
        out = {}
        for d, s in by_date.items():
            out[d] = (_shares_to_lots(s["f"]), _shares_to_lots(s["t"]), _shares_to_lots(s["d"]))
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

    def get_trading_days_desc(self, limit: int = 120):
        """由新到舊回傳交易日（list[str]）。"""
        conn = self._conn()
        cur = conn.cursor()
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

        if chip:
            # 只接受在交易日曆上的日期：FinMind 法人資料集偶有假日殘留列
            # （如端午節 2026-06-19），交易日曆（TradingDate）為權威來源。
            valid = set(self.get_trading_days_desc(limit=400))
            written = 0
            for d, (f, t, dl) in chip.items():
                if valid and d not in valid:
                    continue
                self._upsert_chip(symbol, d, f, t, dl, "finmind")
                written += 1
            return written

        # FinMind 失敗 → 官方備援補最新一日（僅救急，非完整回填）
        print(f"[Backfill] {symbol} FinMind 無資料，嘗試官方備援補最新日")
        return self._backfill_official_latest(symbol)

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

        filled = 0
        for sym in symbols:
            sym = str(sym)
            have = self._existing_dates(sym, min_day)
            need = recent_days - have
            if not need:
                continue
            chip = self._fetch_finmind_chip(sym, min_day, end)
            if chip:
                for d in need:
                    if d in chip:
                        f, t, dl = chip[d]
                        self._upsert_chip(sym, d, f, t, dl, "finmind")
                        filled += 1
            time.sleep(0.2)   # 控制在額度內
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
    # 官方備援（FinMind 掛掉才走）
    # ────────────────────────────────────────────────────────────────────
    def _backfill_official_latest(self, symbol):
        """用官方來源補最新一日（上市走 TWSE，上櫃走 TPEX）。回傳 0/1。"""
        latest = self.get_latest_trading_day() or datetime.date.today().isoformat()
        # 先試 TWSE（上市）
        twse = self._fetch_twse_t86(latest)
        if twse and symbol in twse:
            f, t, dl = twse[symbol]
            self._upsert_chip(symbol, latest, f, t, dl, "twse")
            return 1
        # 再試 TPEX（上櫃，OpenAPI 為最新日）
        tpex = self._fetch_tpex_openapi()
        if tpex:
            tdate, table = tpex
            if symbol in table:
                f, t, dl = table[symbol]
                self._upsert_chip(symbol, tdate, f, t, dl, "tpex")
                return 1
        return 0

    def _fetch_twse_t86(self, date_str):
        """
        TWSE T86（上市當日全體）。date_str='YYYY-MM-DD'。
        以 fields 名稱定位欄位（不寫死 index），單位股→張。
        回傳 {symbol: (foreign_net, trust_net, dealer_net)} 或 None。
        """
        ymd = date_str.replace("-", "")
        try:
            time.sleep(3)   # TWSE 高頻會擋 IP
            r = requests.get(
                TWSE_T86_URL,
                params={"date": ymd, "selectType": "ALLBUT0999", "response": "json"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            if r.status_code != 200:
                return None
            d = r.json()
            if d.get("stat") != "OK" or not d.get("data"):
                return None
            fields = [str(f).strip() for f in d.get("fields", [])]

            def idx(name):
                # 精確比對（TWSE fields 名稱唯一），避免 '自營商買賣超股數' 誤中
                # '外資自營商買賣超股數' / '自營商買賣超股數(自行買賣)' 等子字串欄位
                for i, f in enumerate(fields):
                    if f == name:
                        return i
                return None

            i_fore     = idx("外陸資買賣超股數(不含外資自營商)")
            i_foreself = idx("外資自營商買賣超股數")
            i_trust    = idx("投信買賣超股數")
            i_dealer   = idx("自營商買賣超股數")   # 合計欄（自行買賣+避險）
            if None in (i_fore, i_trust, i_dealer):
                print("[TWSE] fields 定位失敗")
                return None

            def to_int(s):
                try:
                    return int(str(s).replace(",", "").strip() or 0)
                except ValueError:
                    return 0

            out = {}
            for row in d["data"]:
                sym = row[0].strip()
                fore = to_int(row[i_fore])
                if i_foreself is not None:
                    fore += to_int(row[i_foreself])
                trust = to_int(row[i_trust])
                dealer = to_int(row[i_dealer])
                out[sym] = (_shares_to_lots(fore), _shares_to_lots(trust), _shares_to_lots(dealer))
            return out
        except Exception as e:
            print(f"[TWSE] T86 抓取錯誤: {e}")
            return None

    def _fetch_tpex_openapi(self):
        """
        TPEX OpenAPI（上櫃當日全體，最新日）。以欄位名稱定位（key 空白不一致→正規化比對）。
        回傳 (date_str, {symbol: (f,t,d)}) 或 None。
        """
        try:
            r = requests.get(TPEX_OPENAPI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if r.status_code != 200:
                return None
            data = r.json()
            if not isinstance(data, list) or not data:
                return None

            def norm(k):
                return "".join(str(k).split())   # 移除所有空白

            # 預先建立正規化鍵對照（取第一列）
            sample = data[0]
            keymap = {norm(k): k for k in sample.keys()}

            def get_val(row, norm_key):
                real = keymap.get(norm_key)
                if real is None:
                    return 0
                v = row.get(real, 0)
                try:
                    return int(str(v).replace(",", "").strip() or 0)
                except ValueError:
                    return 0

            # 外資合計 = 外陸資(排除外資自營)差額 + 外資自營差額；投信差額；自營差額
            k_fore   = norm("Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference")
            k_foredl = norm("ForeignDealers-Difference")
            k_trust  = norm("SecuritiesInvestmentTrustCompanies-Difference")
            k_dealer = norm("Dealers-Difference")

            roc_date = str(sample.get("Date", "")).strip()
            date_str = self._roc_to_iso(roc_date)

            out = {}
            for row in data:
                sym = str(row.get("SecuritiesCompanyCode", "")).strip()
                if not sym:
                    continue
                fore = get_val(row, k_fore) + get_val(row, k_foredl)
                trust = get_val(row, k_trust)
                dealer = get_val(row, k_dealer)
                out[sym] = (_shares_to_lots(fore), _shares_to_lots(trust), _shares_to_lots(dealer))
            return (date_str, out) if date_str else None
        except Exception as e:
            print(f"[TPEX] OpenAPI 抓取錯誤: {e}")
            return None

    @staticmethod
    def _roc_to_iso(roc):
        """民國日期 '1150703' → '2025-07-03'。"""
        roc = str(roc).strip()
        if len(roc) == 7 and roc.isdigit():
            y = int(roc[:3]) + 1911
            return f"{y}-{roc[3:5]}-{roc[5:7]}"
        return roc

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

    def get_consecutive_days(self, symbol, who: str = "foreign") -> dict:
        """
        由 trading_calendar 最新交易日往回走計算連買/連賣天數。

        規則：
          - 最新端連續缺列（尚未公布）≤ MAX_PENDING_LEAD → 視為 pending，跳過不判缺日。
          - 錨定到第一筆有資料日後：某交易日無列或值為 NULL → 停止，reliable=False，
            記 missing_dates。
          - 值為 0 或方向反轉 → 正常終止 streak，reliable=True。

        回傳 {'days': int（正=連買, 負=連賣）, 'reliable': bool,
              'missing_dates': [...], 'last_date': str|None}
        """
        cal = self.get_trading_days_desc(limit=120)
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

    def _avg_net_5d(self, symbol, who="foreign"):
        """近 5 交易日該法人日均淨額（張，signed）。缺日以現有資料平均。"""
        cal = self.get_trading_days_desc(limit=5)
        rows = self._load_chip_rows(symbol, cal)
        vals = [rows[d][who] for d in cal if d in rows and rows[d][who] is not None]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    def _latest_row(self, symbol):
        """最新一個有資料的交易日 row。回傳 (date, {'foreign','trust','dealer'}) 或 (None, None)。"""
        cal = self.get_trading_days_desc(limit=120)
        rows = self._load_chip_rows(symbol, cal)
        for d in cal:
            if d in rows and rows[d]["foreign"] is not None:
                return d, rows[d]
        return None, None

    # ────────────────────────────────────────────────────────────────────
    # 統一出口
    # ────────────────────────────────────────────────────────────────────
    def get_chip_flow(self, symbol, allow_fetch: bool = True) -> dict:
        """
        取代 QuickAnalyzer._analyze_chip_flow_cached 的統一出口。

        allow_fetch：
          True（單檔分析）— DB 無資料時先 backfill 再讀。
          False（掃描熱路徑）— 只讀 DB、零 API 呼叫（daily_update 已在掃描前批次補過）。
        """
        symbol = str(symbol)

        # 確保有日曆（讀 DB；空才同步）
        if allow_fetch and not self.get_latest_trading_day():
            self.sync_calendar()

        # DB 無任何資料 → 視 allow_fetch 決定是否 backfill
        latest_date, latest_row = self._latest_row(symbol)
        if latest_row is None and allow_fetch:
            self.backfill(symbol, trading_days=90)
            latest_date, latest_row = self._latest_row(symbol)

        if latest_row is None:
            return {"available": False,
                    "message": "無法取得籌碼資料" + ("（FinMind/官方備援皆無回應）" if allow_fetch else "（DB 無資料，掃描不觸發抓取）")}

        foreign_net = latest_row["foreign"] or 0
        trust_net   = latest_row["trust"] or 0
        dealer_net  = latest_row["dealer"] or 0

        f_streak = self.get_consecutive_days(symbol, "foreign")
        t_streak = self.get_consecutive_days(symbol, "trust")

        foreign_days = f_streak["days"]
        trust_days   = t_streak["days"]
        reliable     = bool(f_streak["reliable"] and t_streak["reliable"])
        missing      = sorted(set(f_streak["missing_dates"]) | set(t_streak["missing_dates"]))

        consecutive_buy_days  = max(foreign_days if foreign_days > 0 else 0,
                                    trust_days   if trust_days   > 0 else 0)
        consecutive_sell_days = max(-foreign_days if foreign_days < 0 else 0,
                                    -trust_days   if trust_days   < 0 else 0)

        avg_sell_net_5d = self._avg_net_5d(symbol, "foreign")

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
