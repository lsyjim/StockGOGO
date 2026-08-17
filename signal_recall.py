"""
signal_recall.py — 訊號驗證（T-4~T-1 樣本外重放）資料層

對指定清單逐檔重放過去 4 個交易日當天的分析結果，再用「之後已發生的真實價格」驗證：
  短線：T+1 收盤 vs T 收盤（隔日漲跌%）
  中/長線：對照當時 term_advice['mid']/['long'] 的方向文字，與重放日至今的走勢方向是否一致

鐵律：這是**樣本外重放，不是新的評分邏輯**。分級/建議 100% 複用既有
QuickAnalyzer.analyze_stock(analysis_date=T-N) + build_verdict() + evaluate_r_track()，
本模組不含任何自訂判定。
"""

from __future__ import annotations

import sqlite3
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 標籤優先序：賣出族 > R 軌 > 動量等級
LABELS = ('A', 'B', 'C', 'R', '賣出')

_SELL_ACTION = ('SELL', 'EXIT', 'TAKE_PROFIT')
_SELL_SCENARIO = ('SELL', 'EXIT')

# 中/長線方向關鍵字（沿用 theme.grade_tag 同一套語彙風格）
_LONG_KW = ('買進', '加碼', '持有', '偏多', '續抱', '佈局', '進場')
_SHORT_KW = ('減碼', '避開', '出場', '賣出', '偏空')


def _direction(action_text) -> str:
    """建議文字 → '多' / '空' / '中性'（中性不進勝率分母）。"""
    s = str(action_text or '')
    if any(k in s for k in _SHORT_KW):
        return '空'
    if any(k in s for k in _LONG_KW):
        return '多'
    return '中性'


# ── 快取表 ────────────────────────────────────────────────────────────────
def ensure_cache_table(db_name):
    conn = sqlite3.connect(db_name)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS recall_cache (
            symbol         TEXT NOT NULL,
            as_of_date     TEXT NOT NULL,
            name           TEXT,
            label          TEXT,
            score          REAL,
            t_close        REAL,
            t1_date        TEXT,
            t1_close       REAL,
            next_day_pct   REAL,
            mid_direction  TEXT,
            long_direction TEXT,
            computed_at    TEXT,
            PRIMARY KEY (symbol, as_of_date)
        )
    ''')
    conn.commit()
    conn.close()


_FIELDS = ('symbol', 'as_of_date', 'name', 'label', 'score', 't_close', 't1_date',
           't1_close', 'next_day_pct', 'mid_direction', 'long_direction')


# 負向快取標記：該 (symbol,date) 重放後無有效訊號（X 級或資料不足）。
# 不記錄的話每次開視窗都會重跑這些組合（歷史重放成本高），違反「第二次秒開」。
_NO_SIGNAL = '_NONE_'


def _load_cached(db_name, pairs):
    """pairs: {(symbol, date)}。回傳 (命中集合, {(symbol,date): row_dict})。
    命中集合含負向快取；row_dict 只含有效訊號。"""
    if not pairs:
        return set(), {}
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()
    hit, out = set(), {}
    cur.execute(f"SELECT {','.join(_FIELDS)} FROM recall_cache")
    for r in cur.fetchall():
        d = dict(zip(_FIELDS, r))
        key = (str(d['symbol']), d['as_of_date'])
        if key not in pairs:
            continue
        hit.add(key)
        if d.get('label') == _NO_SIGNAL:
            continue                      # 負向快取：已知無訊號，不進結果
        d['date'] = d.pop('as_of_date')
        out[key] = d
    conn.close()
    return hit, out


def _save_rows(db_name, rows):
    if not rows:
        return
    conn = sqlite3.connect(db_name)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.executemany(
        "INSERT OR REPLACE INTO recall_cache "
        "(symbol, as_of_date, name, label, score, t_close, t1_date, t1_close, "
        " next_day_pct, mid_direction, long_direction, computed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r['symbol'], r['date'], r.get('name'), r.get('label'), r.get('score'),
          r.get('t_close'), r.get('t1_date'), r.get('t1_close'), r.get('next_day_pct'),
          r.get('mid_direction'), r.get('long_direction'), now) for r in rows])
    conn.commit()
    conn.close()


# ── 主流程 ────────────────────────────────────────────────────────────────
def recent_trading_days(db_name, n=4, exclude_today=True):
    """取最近 n 個「已收盤」交易日（新→舊排序後回傳由舊到新）。"""
    from chip_data_manager import get_chip_manager
    days = get_chip_manager(db_name).get_trading_days_desc(limit=30)
    today = datetime.date.today().isoformat()
    if exclude_today:
        days = [d for d in days if d < today]      # 今日尚未收盤，不納入
    return sorted(days[:n])


def _label_of(verdict, r):
    """標籤優先序：賣出族 > R 軌 > 動量等級。X 回 None（不進統計）。"""
    ac = str(verdict.get('action_code', '')).upper()
    scn = str(verdict.get('grade', ''))
    if scn in _SELL_SCENARIO or ac.startswith('SELL') or ac in _SELL_ACTION:
        return '賣出'
    if (r or {}).get('r_signal') in ('R-TRADE', 'R-WATCH'):
        return 'R'
    return scn if scn in ('A', 'B', 'C') else None


def run_recall(symbols, as_of_dates, db_name, progress_cb=None,
               use_cache=True, max_workers=6):
    """
    symbols: [(code, name, market), ...]
    as_of_dates: T-4..T-1 交易日（任意順序，內部排序）
    回傳 list[dict]：{date, symbol, name, label, score, t_close, t1_date,
                      t1_close, next_day_pct, mid_direction, long_direction}
    """
    from main import QuickAnalyzer, DataSourceManager
    from report_formatter import build_verdict
    try:
        from r_track import evaluate_r_track
    except Exception:
        evaluate_r_track = None

    ensure_cache_table(db_name)
    dates = sorted(set(as_of_dates))
    # 去重（同股票只跑一次）
    seen, uniq = set(), []
    for s in symbols:
        code = str(s[0])
        if code in seen:
            continue
        seen.add(code)
        uniq.append((code, (s[1] if len(s) > 1 else code), (s[2] if len(s) > 2 else '台股')))

    want = {(c, d) for c, _, _ in uniq for d in dates}
    hit, cached = _load_cached(db_name, want) if use_cache else (set(), {})

    todo = [(c, n, m, d) for c, n, m in uniq for d in dates if (c, d) not in hit]
    total = len(todo)
    done_lock = threading.Lock()
    done = {'n': 0}
    results = list(cached.values())

    # 交易日曆（R 軌出場日用；由舊到新）
    try:
        from chip_data_manager import get_chip_manager
        trading_days = sorted(get_chip_manager(db_name).get_trading_days_desc(limit=400))
    except Exception:
        trading_days = []

    # 每檔歷史抓一次，供 T/T+1/今日收盤查表（避免逐日重抓）
    hist_cache = {}
    hist_lock = threading.Lock()

    def _hist(code, market):
        with hist_lock:
            if code in hist_cache:
                return hist_cache[code]
        h = None
        try:
            h = DataSourceManager.get_history(code, market, period='1y')
        except Exception:
            h = None
        with hist_lock:
            hist_cache[code] = h
        return h

    def _close_on(h, date_str):
        """該交易日收盤（無資料回 None）。"""
        if h is None or len(h) == 0:
            return None
        try:
            for ts, row in zip(h.index, h['Close']):
                if ts.date().isoformat() == date_str:
                    return float(row)
        except Exception:
            pass
        return None

    def _next_trading_day(date_str):
        after = [d for d in trading_days if d > date_str]
        return after[0] if after else None

    def _no_signal(code, date_str):
        """負向快取列（下次直接略過，不再重放）。"""
        return {'date': date_str, 'symbol': code, 'name': None, 'label': _NO_SIGNAL,
                'score': None, 't_close': None, 't1_date': None, 't1_close': None,
                'next_day_pct': None, 'mid_direction': None, 'long_direction': None}

    def _one(code, name, market, date_str):
        try:
            dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            result = QuickAnalyzer.analyze_stock(code, market, analysis_date=dt, scan_mode=True)
            if not result:
                return _no_signal(code, date_str)
            verdict = build_verdict(result)
            r = {}
            if evaluate_r_track is not None:
                try:
                    r = evaluate_r_track(result, date_str, trading_days)
                except Exception:
                    r = {}
            label = _label_of(verdict, r)
            if label is None:
                return _no_signal(code, date_str)   # X：無明確方向，不進統計（但快取）

            h = _hist(code, market)
            t_close = _close_on(h, date_str)
            t1_date = _next_trading_day(date_str)
            t1_close = _close_on(h, t1_date) if t1_date else None
            nxt = (round((t1_close / t_close - 1) * 100, 2)
                   if (t_close and t1_close and t_close > 0) else None)

            ta = verdict.get('term_advice', {}) or {}
            return {
                'date': date_str, 'symbol': code, 'name': name, 'label': label,
                'score': verdict.get('score'),
                't_close': (round(t_close, 2) if t_close else None),
                't1_date': t1_date,
                't1_close': (round(t1_close, 2) if t1_close else None),
                'next_day_pct': nxt,
                'mid_direction': _direction((ta.get('mid') or {}).get('action')),
                'long_direction': _direction((ta.get('long') or {}).get('action')),
            }
        except Exception as e:
            print(f"[訊號驗證] {code}@{date_str} 重放失敗: {e}")
            return None    # 例外不快取（可能是暫時性網路問題，下次應重試）
        finally:
            with done_lock:
                done['n'] += 1
                if progress_cb:
                    try:
                        progress_cb(done['n'], total)
                    except Exception:
                        pass

    fresh = []
    if todo:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(_one, c, n, m, d) for c, n, m, d in todo]
            for f in as_completed(futs):
                row = f.result()
                if row:
                    fresh.append(row)
        _save_rows(db_name, fresh)      # 含負向列，避免下次重跑
    # 負向列只入庫、不進結果
    results.extend([r for r in fresh if r.get('label') != _NO_SIGNAL])
    results.sort(key=lambda x: (x['date'], x['symbol']))
    return results


# ── 統計 ──────────────────────────────────────────────────────────────────
def summarize_by_date(rows):
    """每個重放日 × 標籤：{date: {label: {'n':檔數, 'up':隔日上漲數, 'valid':有隔日資料數}}}"""
    out = {}
    for r in rows:
        d = out.setdefault(r['date'], {})
        s = d.setdefault(r['label'], {'n': 0, 'up': 0, 'valid': 0})
        s['n'] += 1
        if r.get('next_day_pct') is not None:
            s['valid'] += 1
            if r['next_day_pct'] > 0:
                s['up'] += 1
    return out


def summarize_totals(rows, cur_close_fn=None):
    """
    合計表：{label: {'short':(hit,total), 'mid':(hit,total), 'long':(hit,total), 'n':檔數}}
    中/長線用「方向一致性」：重放日→今日的區間報酬符號 vs 當時方向。
    中性方向不計入分母；R 軌無中長方向（回 None）。
    """
    out = {}
    for r in rows:
        lab = r['label']
        s = out.setdefault(lab, {'short': [0, 0], 'mid': [0, 0], 'long': [0, 0], 'n': 0})
        s['n'] += 1
        # 短線：隔日漲跌（賣出族「跌」才算命中；其餘「漲」算命中）
        nxt = r.get('next_day_pct')
        if nxt is not None:
            s['short'][1] += 1
            hit = (nxt < 0) if lab == '賣出' else (nxt > 0)
            if hit:
                s['short'][0] += 1
        # 中/長線：R 軌不適用
        if lab == 'R':
            continue
        cur = cur_close_fn(r['symbol']) if cur_close_fn else None
        if cur and r.get('t_close'):
            ret = cur / r['t_close'] - 1
            for key in ('mid', 'long'):
                d = r.get(f'{key}_direction')
                if d not in ('多', '空'):
                    continue         # 中性不進分母
                s[key][1] += 1
                if (ret > 0 and d == '多') or (ret < 0 and d == '空'):
                    s[key][0] += 1
    return {k: {kk: (tuple(vv) if isinstance(vv, list) else vv) for kk, vv in v.items()}
            for k, v in out.items()}


def fmt_rate(hit_total):
    """(hit,total) → '3/5 60%'；total=0 → '—'。"""
    if not hit_total:
        return '—'
    hit, total = hit_total
    if not total:
        return '—'
    return f"{hit}/{total}  {hit/total*100:.0f}%"
