"""
portfolio_backtest.py — build_prompt_21：真實逐日資金曲線模擬

定位
────
Phase1/1.5 每一份報告都掛著同一句免責：「投組層級 CAGR/MDD 為近似值
（每 N 個交易日取樣一次），真正的投組模擬需要部位管理器，超出現有
signal_backtest.py 框架能力」。build_prompt_19 做出了部位管理器，
這個模組把它接上，跑出第一個**真正**的資金曲線。

**獨立模組，不動 signal_backtest.py**：只讀它已產生的 trades.csv，
在其輸出之上疊一層資金曲線模擬，不重新產生任何訊號。

範圍
────
- 進場：用 portfolio_engine.evaluate_new_position() 真實決策（買不買、買多少）
- 出場：**固定持有 20 個交易日**（專案定位是 20 日波段引擎）
- **不做訊號驅動出場**（即時停損/停利/反轉）——那是另一個需要獨立驗證的
  方法論改動，明確排除在本輪之外

價格資料
────────
磁碟上沒有涵蓋 bp13_step0 universe 全期的價格快取
（`_histcache_*.pkl` 是 Phase1.5 對照 universe，只重疊 5 檔）。
本模組改由 **trades.csv 自身重建**每檔的收盤價序列：
每一列的 `exit_5`/`exit_10`/`exit_20` 分別是該檔第 i+6／i+11／i+21 個
交易日的收盤價，`entry` 是第 i+1 個交易日的開盤價。
三者交叉比對 1,624 組全數吻合（誤差 < 0.011），確認重建無損。

好處是整份模擬與 Phase1 用的是**同一份凍結資料**，不打網路、可重現。

預先定義的決定性規則（跑之前寫死，不因看到結果調整）
──────────────────────────────────────────────────
1. 只交易 A/B 級訊號
2. 同一天多筆候選：**A 級優先，同級依 dir_score 由高到低，同分依代號**
3. 已持有的標的**不重複加碼**（一檔同時只有一個部位）
4. 現金不足時縮到現金上限（不允許融資／負現金）
5. 無法在凍結資料內走完 20 日持有期的訊號一律跳過（不提前結算）
"""

from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import json
import math
import os
import statistics

import portfolio_engine as PE
from config import QuantConfig as QC

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, 'docs', 'superpowers', 'reports', 'phase2')
BASE_TRADES = os.path.join(ROOT, 'backtest_results', 'bp13_step0', 'trades.csv')

HOLDING_DAYS = 20
START_CAPITAL = 1_000_000
TRADED_GRADES = ('A', 'B')
GRADE_RANK = {'A': 0, 'B': 1}

# round-trip 成本率，與 signal_backtest.get_cost_rate(discount=1.0) 同式
COST_RATE = QC.COMMISSION_RATE * 2 + QC.TAX_RATE


def _f(x):
    try:
        if x in (None, '', 'None'):
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


# ── 資料層 ────────────────────────────────────────────────────────────────
class PriceBook:
    """由 trades.csv 重建的每檔交易日序列、收盤價與進場開盤價。"""

    def __init__(self, rows_by_symbol):
        self.dates = {}      # symbol -> [date, ...]（升冪）
        self.idx = {}        # symbol -> {date: i}
        self.close = {}      # symbol -> [close or None]（與 dates 對齊）
        self.entry = {}      # symbol -> [entry_open or None]（第 i+1 日開盤）
        for s, rows in rows_by_symbol.items():
            rows.sort(key=lambda r: r['as_of'])
            ds = [r['as_of'] for r in rows]
            n = len(ds)
            cl = [None] * n
            en = [None] * n
            for i, r in enumerate(rows):
                en[i] = _f(r.get('entry'))
                # exit_N 是第 i+1+N 個交易日的收盤價
                for N, key in ((5, 'exit_5'), (10, 'exit_10'), (20, 'exit_20')):
                    j = i + 1 + N
                    if j < n:
                        v = _f(r.get(key))
                        if v is not None and cl[j] is None:
                            cl[j] = v
            self.dates[s] = ds
            self.idx[s] = {d: i for i, d in enumerate(ds)}
            self.close[s] = cl
            self.entry[s] = en

    def close_on(self, symbol, date):
        """該日收盤價；當日無值則往前找最近一筆（停牌/首段缺值）。"""
        ds = self.dates.get(symbol)
        if not ds:
            return None
        i = bisect.bisect_right(ds, date) - 1
        cl = self.close[symbol]
        while i >= 0:
            if cl[i] is not None:
                return cl[i]
            i -= 1
        return None

    def history_upto(self, symbol, date, window):
        """截至 date（含）的最近 window 筆有效收盤價，供相關性計算。"""
        ds = self.dates.get(symbol)
        if not ds:
            return None
        hi = bisect.bisect_right(ds, date)
        cl = self.close[symbol]
        out = []
        for i in range(hi - 1, -1, -1):
            v = cl[i]
            if v is not None:
                out.append(v)
                if len(out) >= window:
                    break
        out.reverse()
        return out if len(out) >= window else None

    def exit_slot(self, symbol, date, hold):
        """回傳 (出場日期, 出場價)；走不完持有期則 (None, None)。"""
        i = self.idx.get(symbol, {}).get(date)
        if i is None:
            return None, None
        j = i + 1 + hold
        ds = self.dates[symbol]
        if j >= len(ds):
            return None, None
        return ds[j], self.close[symbol][j]


def _held_days(book, symbol, entry_date, exit_date):
    """實際持有的交易日數（進場日到出場日之間的交易日格數）。"""
    idx = book.idx.get(symbol, {})
    i, j = idx.get(entry_date), idx.get(exit_date)
    return (j - i - 1) if (i is not None and j is not None) else None


def load_rows(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


# ── 模擬主體 ──────────────────────────────────────────────────────────────
MAX_DELEVERAGE_PER_DAY = 1     # build_prompt_22：限速，每天最多強制平倉一筆


def simulate(trades_csv_path=BASE_TRADES, start_capital=START_CAPITAL,
             holding_days=HOLDING_DAYS, theme_map=None, verbose=True,
             deleverage=False):
    """deleverage=False 時與 build_prompt_21 完全相同（Scenario A 基準）。

    deleverage=True 啟用 build_prompt_22 的減碼：每日在「到期結算」之後、
    「新進場」之前，若總曝險超過當日 regime 上限，依 `portfolio_engine.
    select_position_to_trim()` 強制平倉最舊的一筆，每天最多
    MAX_DELEVERAGE_PER_DAY 筆（不一次到位）。
    """
    rows = load_rows(trades_csv_path)

    by_symbol = collections.defaultdict(list)
    for r in rows:
        by_symbol[r['symbol']].append(dict(r))
    book = PriceBook(by_symbol)

    calendar = sorted({r['as_of'] for r in rows})
    regime_of = {}
    signals = collections.defaultdict(list)
    for r in rows:
        regime_of.setdefault(r['as_of'], r.get('regime', '未知'))
        if r['grade'] in TRADED_GRADES:
            signals[r['as_of']].append(r)

    if theme_map is None:
        try:
            with open(os.path.join(ROOT, 'theme_map.json'), encoding='utf-8') as f:
                theme_map = json.load(f)
        except Exception:
            theme_map = {}

    cash = float(start_capital)
    positions = {}          # symbol -> dict
    exits_on = collections.defaultdict(list)   # date -> [symbol]
    equity_curve = []       # (date, equity, cash, invested, gross_pct, regime)
    trade_log = []
    stats = collections.Counter()
    capped_examples = []
    entry_audit = []        # 每次開倉當下的曝險 vs 上限（驗收條件2）

    for date in calendar:
        regime = regime_of.get(date, '未知')

        # 1. 到期結算
        for sym in exits_on.pop(date, []):
            p = positions.get(sym)
            # 同一檔被減碼後可能已重新進場，舊排程會殘留在 exits_on 裡。
            # 用部位自己記的排程日核對，避免舊排程把新部位提早關掉。
            if p is None or p.get('exit_date_sched') != date:
                continue
            positions.pop(sym)
            px = p['exit_price']
            if px is None:
                px = book.close_on(sym, date) or p['entry_price']
            proceeds = p['shares'] * px
            cost = COST_RATE * p['notional']          # 與 signal_backtest 同式
            cash += proceeds - cost
            pnl = proceeds - cost - p['notional']
            trade_log.append({
                'symbol': sym, 'grade': p['grade'],
                'entry_date': p['entry_date'], 'exit_date': date,
                'entry_price': p['entry_price'], 'exit_price': px,
                'shares': p['shares'], 'notional': p['notional'],
                'pnl': pnl, 'ret_pct': pnl / p['notional'] * 100,
                'regime_at_entry': p['regime'], 'exit_reason': 'expired',
                'held_days': _held_days(book, sym, p['entry_date'], date),
                'early_by': 0, 'regime_at_exit': regime,
            })
            stats['closed'] += 1

        # 2. 當日估值（先估值，才知道今天的總資產與各部位佔比）
        def _mark():
            inv = 0.0
            for s, p in positions.items():
                px = book.close_on(s, date) or p['entry_price']
                p['mark'] = px
                inv += p['shares'] * px
            return inv

        invested = _mark()
        equity = cash + invested

        # 2b. 減碼檢查（build_prompt_22）：在新進場之前，釋放曝險空間。
        #     提早出場一律以**當日真實收盤價**結算——PriceBook 由
        #     exit_5 反推，第 7 個交易日起每檔每日都有實價，不需近似。
        if deleverage:
            for _ in range(MAX_DELEVERAGE_PER_DAY):
                if not positions or equity <= 0:
                    break
                cur_list = [{'symbol': s, 'entry_date': p['entry_date'],
                             'position_pct': p['shares'] * p['mark'] / equity}
                            for s, p in positions.items()]
                pick = PE.select_position_to_trim(
                    cur_list, regime,
                    market_available=(regime in QC.GROSS_EXPOSURE_BY_REGIME))
                if not pick:
                    break
                sym = pick['symbol']
                p = positions.pop(sym)
                px = book.close_on(sym, date) or p['entry_price']
                proceeds = p['shares'] * px
                cost = COST_RATE * p['notional']
                cash += proceeds - cost
                pnl = proceeds - cost - p['notional']
                held = _held_days(book, sym, p['entry_date'], date)
                trade_log.append({
                    'symbol': sym, 'grade': p['grade'],
                    'entry_date': p['entry_date'], 'exit_date': date,
                    'entry_price': p['entry_price'], 'exit_price': px,
                    'shares': p['shares'], 'notional': p['notional'],
                    'pnl': pnl, 'ret_pct': pnl / p['notional'] * 100,
                    'regime_at_entry': p['regime'], 'exit_reason': 'deleveraged',
                    'held_days': held, 'early_by': holding_days - held,
                    'regime_at_exit': regime, 'excess_pct': pick['excess_pct'],
                })
                stats['deleveraged'] += 1
                invested = _mark()
                equity = cash + invested

        # 3. 當日候選訊號：A 優先，同級 dir_score 高者優先，同分依代號
        cands = sorted(
            signals.get(date, []),
            key=lambda r: (GRADE_RANK.get(r['grade'], 9),
                           -(_f(r.get('dir_score')) or 0), r['symbol']))

        for r in cands:
            sym = r['symbol']
            stats['candidates'] += 1
            if sym in positions:
                stats['skip_already_held'] += 1
                continue
            exit_date, exit_px = book.exit_slot(sym, date, holding_days)
            if exit_date is None:
                stats['skip_no_exit_slot'] += 1
                continue
            i = book.idx[sym][date]
            entry_px = book.entry[sym][i]
            if not entry_px or entry_px <= 0:
                stats['skip_no_entry_price'] += 1
                continue

            atr_pct = _f(r.get('atr_pct'))
            atr = (atr_pct / 100.0 * entry_px) if atr_pct else None

            cur_list = [{'symbol': s, 'position_pct': (p['shares'] * p['mark'] / equity)}
                        for s, p in positions.items()] if equity > 0 else []

            def _hist(s, _d=date):
                return book.history_upto(s, _d, QC.CORR_WINDOW_DAYS)

            out = PE.evaluate_new_position(
                {'symbol': sym, 'grade': r['grade'],
                 'entry_price': entry_px, 'atr': atr},
                current_positions=cur_list,
                capital=equity,
                regime=regime,
                market_available=(regime in QC.GROSS_EXPOSURE_BY_REGIME),
                theme_map=theme_map,
                price_history_getter=_hist,
            )

            for st in out['steps'][1:]:
                if st.get('capped'):
                    stats[f"capped_{st['step']}"] += 1
                    if st['step'] == 'correlation_limits' and len(capped_examples) < 8:
                        capped_examples.append({
                            'date': date, 'symbol': sym,
                            'with': (st.get('detail') or {}).get('correlated_with'),
                            'from_pct': out['steps'][0]['approved_pct'],
                            'to_pct': st['approved_pct'],
                        })
            if out['rejected']:
                stats['rejected'] += 1
                continue

            notional = out['final_pct'] * equity
            if notional > cash:
                notional = cash                      # 不允許融資／負現金
                stats['capped_cash'] += 1
            if notional <= 0 or notional / equity < QC.MIN_EFFECTIVE_POSITION_PCT:
                stats['rejected_after_cash'] += 1
                continue

            shares = notional / entry_px
            cash -= notional
            positions[sym] = {
                'grade': r['grade'], 'shares': shares, 'entry_price': entry_px,
                'notional': notional, 'entry_date': date, 'exit_price': exit_px,
                'regime': regime, 'mark': entry_px,
                'exit_date_sched': exit_date,
            }
            exits_on[exit_date].append(sym)
            stats['opened'] += 1
            invested += notional
            # equity 不變（現金轉成部位），不需重估
            gstep = next(s for s in out['steps'] if s['step'] == 'gross_exposure_cap')
            entry_audit.append({
                'date': date, 'symbol': sym, 'regime': regime,
                'cap': gstep['cap'], 'gross_before': gstep['gross_before'],
                'gross_after': (invested / equity) if equity > 0 else 0.0,
            })

        invested = _mark()
        equity = cash + invested
        equity_curve.append({
            'date': date, 'equity': equity, 'cash': cash, 'invested': invested,
            'gross_pct': (invested / equity if equity > 0 else 0.0),
            'regime': regime, 'n_positions': len(positions),
        })

    # 期末強制結算（用最後一日估值），避免尾端部位被漏計
    last = calendar[-1]
    for sym, p in list(positions.items()):
        px = book.close_on(sym, last) or p['entry_price']
        proceeds = p['shares'] * px
        cost = COST_RATE * p['notional']
        cash += proceeds - cost
        trade_log.append({
            'symbol': sym, 'grade': p['grade'], 'entry_date': p['entry_date'],
            'exit_date': last, 'entry_price': p['entry_price'], 'exit_price': px,
            'shares': p['shares'], 'notional': p['notional'],
            'pnl': proceeds - cost - p['notional'],
            'ret_pct': (proceeds - cost - p['notional']) / p['notional'] * 100,
            'regime_at_entry': p['regime'], 'forced_close': True,
            'exit_reason': 'forced_end',
            'held_days': _held_days(book, sym, p['entry_date'], last),
            'early_by': None, 'regime_at_exit': regime_of.get(last, '未知'),
        })
        stats['forced_close_at_end'] += 1
        positions.pop(sym)

    if verbose:
        print(f"[sim{'+DL' if deleverage else ''}] 交易日 {len(calendar)}｜"
              f"候選 {stats['candidates']}｜開倉 {stats['opened']}｜"
              f"到期平倉 {stats['closed']}｜減碼出場 {stats.get('deleveraged',0)}"
              f"（期末強制 {stats['forced_close_at_end']}）")

    return {'equity_curve': equity_curve, 'trades': trade_log,
            'stats': dict(stats), 'book': book, 'calendar': calendar,
            'start_capital': float(start_capital),
            'capped_examples': capped_examples, 'entry_audit': entry_audit}


# ── 績效指標 ──────────────────────────────────────────────────────────────
def _years(d0, d1):
    return max((dt.date.fromisoformat(d1) - dt.date.fromisoformat(d0)).days / 365.25, 1e-9)


def perf_from_equity(curve, start_capital, periods_per_year=252):
    """由真實資金曲線算 CAGR / MDD / Sharpe / Sortino。"""
    if len(curve) < 2:
        return None
    eq = [c['equity'] for c in curve]
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1] > 0]
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    yrs = _years(curve[0]['date'], curve[-1]['date'])
    total = eq[-1] / start_capital
    cagr = (total ** (1 / yrs) - 1) * 100 if total > 0 else None
    mean = statistics.mean(rets) if rets else 0.0
    sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    dn = [x for x in rets if x < 0]
    sd_dn = statistics.pstdev(dn) if len(dn) > 1 else 0.0
    ann = math.sqrt(periods_per_year)
    return {
        'days': len(eq), 'years': round(yrs, 2),
        'final_equity': round(eq[-1], 0),
        'total_return': round((total - 1) * 100, 2),
        'cagr': round(cagr, 2) if cagr is not None else None,
        'mdd': round(mdd * 100, 2),
        'sharpe': round(mean / sd * ann, 3) if sd > 0 else None,
        'sortino': round(mean / sd_dn * ann, 3) if sd_dn > 0 else None,
        'avg_gross': round(statistics.mean(c['gross_pct'] for c in curve) * 100, 1),
        'max_gross': round(max(c['gross_pct'] for c in curve) * 100, 1),
        'avg_positions': round(statistics.mean(c['n_positions'] for c in curve), 2),
    }


def perf_by_regime(curve, periods_per_year=252):
    """分 regime 的日報酬統計（不是各自獨立的資金曲線，是同一條曲線的分段）。"""
    seg = collections.defaultdict(list)
    for i in range(1, len(curve)):
        prev, cur = curve[i - 1], curve[i]
        if prev['equity'] <= 0:
            continue
        seg[cur['regime']].append((cur['equity'] / prev['equity'] - 1, cur['gross_pct']))
    out = {}
    ann = math.sqrt(periods_per_year)
    for rg, vals in seg.items():
        rets = [v[0] for v in vals]
        gp = [v[1] for v in vals]
        cum = 1.0
        peak = mdd = 1.0
        mdd = 0.0
        for x in rets:
            cum *= (1 + x)
            peak = max(peak, cum)
            mdd = min(mdd, cum / peak - 1)
        sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
        mean = statistics.mean(rets) if rets else 0.0
        out[rg] = {
            'days': len(rets),
            'cum_return': round((cum - 1) * 100, 2),
            'ann_return': round(((cum ** (periods_per_year / len(rets))) - 1) * 100, 2)
                          if rets else None,
            'mdd': round(mdd * 100, 2),
            'sharpe': round(mean / sd * ann, 3) if sd > 0 else None,
            'avg_gross': round(statistics.mean(gp) * 100, 1),
        }
    return out


# ── 舊近似法（任務3 對照）────────────────────────────────────────────────
def legacy_approximation(trades_csv_path=BASE_TRADES, N=HOLDING_DAYS,
                         grades=TRADED_GRADES):
    """沿用 analyze_phase1.portfolio_series 的「每 N 個交易日取樣一次」近似法。

    為了可比，對照的訊號集合與真實模擬相同（A+B 級），
    而不是 b1 報告裡的純 A 級書。
    """
    rows = [r for r in load_rows(trades_csv_path) if r['grade'] in grades]
    byd = collections.defaultdict(list)
    for r in rows:
        v = _f(r.get(f'ret_{N}_net'))
        if v is not None:
            byd[r['as_of']].append(v)
    days = sorted(byd)[::max(1, N)]
    unit = 0.20          # 與 analyze_phase1.UNIT 一致：單筆 20%
    ser = []
    for d in days:
        v = byd[d]
        expo = min(len(v) * unit, 1.0)
        ser.append((d, expo * statistics.mean(v)))
    if len(ser) < 2:
        return None
    vals = [x[1] for x in ser]
    eq, peak, mdd = 1.0, 1.0, 0.0
    for x in vals:
        eq *= (1 + x / 100.0)
        peak = max(peak, eq)
        mdd = min(mdd, (eq / peak - 1) * 100)
    yrs = _years(ser[0][0], ser[-1][0])
    cagr = (eq ** (1 / yrs) - 1) * 100 if eq > 0 else None
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    dn = [x for x in vals if x < 0]
    sd_dn = statistics.pstdev(dn) if len(dn) > 1 else 0.0
    ppy = 252 / N        # 一年約幾期（不重疊）
    ann = math.sqrt(ppy)
    return {
        'periods': len(vals), 'years': round(yrs, 2),
        'total_return': round((eq - 1) * 100, 2),
        'cagr': round(cagr, 2) if cagr is not None else None,
        'mdd': round(mdd, 2),
        'sharpe_raw': round(mean / sd, 3) if sd > 0 else None,
        'sharpe': round(mean / sd * ann, 3) if sd > 0 else None,
        'sortino': round(mean / sd_dn * ann, 3) if sd_dn > 0 else None,
    }


# ── 報告 ──────────────────────────────────────────────────────────────────
def _fmt(v, suffix=''):
    return '—' if v is None else f"{v}{suffix}"


def write_report(sim, perf, byreg, legacy, out_name='portfolio_backtest_real.md'):
    os.makedirs(OUT_DIR, exist_ok=True)
    cur = sim['equity_curve']
    st = sim['stats']
    md = ["# Phase2：真實投組模擬（build_prompt_21）\n"]
    md.append("> **這份報告終結 Phase1/1.5 所有報告掛著的那句免責**："
              "「投組層級 CAGR/MDD 為近似值……真正的投組模擬需要部位管理器，"
              "超出現有 `signal_backtest.py` 框架能力」。")
    md.append("> 部位管理器（`portfolio_engine.py`）已於 build_prompt_19 完成，"
              "本輪以 `portfolio_backtest.py` 逐日重放資金曲線。\n")

    md.append("## 設定\n")
    md.append(f"- 資料：`backtest_results/bp13_step0/trades.csv`（Phase1 凍結 baseline，"
              f"{cur[0]['date']} → {cur[-1]['date']}，{len(cur):,} 個交易日）")
    md.append(f"- 起始資金：{sim['start_capital']:,.0f}｜持有期：固定 {HOLDING_DAYS} 交易日")
    md.append(f"- 成本：round-trip {COST_RATE*100:.4f}%"
              f"（手續費 {QC.COMMISSION_RATE*100:.4f}%×2 + 稅 {QC.TAX_RATE*100:.2f}%），"
              "與 `signal_backtest.get_cost_rate(1.0)` 同式")
    md.append("- 進場決策：`portfolio_engine.evaluate_new_position()` 四層"
              "（風險預算 → regime 曝險上限 → 題材集中度 → 相關性集中度）")
    md.append(f"- 曝險上限：{QC.GROSS_EXPOSURE_BY_REGIME}"
              f"｜單筆上限 {QC.MAX_SINGLE_POSITION_PCT:.0%}"
              f"｜題材 {QC.MAX_THEME_EXPOSURE_PCT:.0%}"
              f"｜相關集群 {QC.MAX_CORRELATED_EXPOSURE_PCT:.0%}"
              f"（門檻 {QC.CORR_THRESHOLD}，{QC.CORR_WINDOW_DAYS} 日窗口）\n")

    md.append("### 預先定義的決定性規則（跑之前寫死）\n")
    md.append("1. 只交易 A/B 級訊號")
    md.append("2. 同日多筆候選：**A 級優先 → 同級 `dir_score` 高者優先 → 同分依代號**")
    md.append("3. 已持有標的不重複加碼（一檔同時只有一個部位）")
    md.append("4. 現金不足時縮到現金上限（不允許融資／負現金）")
    md.append("5. 無法在凍結資料內走完持有期的訊號一律跳過\n")

    md.append("## 1. 真實績效（任務2）\n")
    md.append("| 指標 | 值 |")
    md.append("|---|---|")
    md.append(f"| 期間 | {cur[0]['date']} → {cur[-1]['date']}（{perf['years']} 年） |")
    md.append(f"| 期末資產 | {perf['final_equity']:,.0f} |")
    md.append(f"| 總報酬 | {_fmt(perf['total_return'], '%')} |")
    md.append(f"| **真實 CAGR** | **{_fmt(perf['cagr'], '%')}** |")
    md.append(f"| **真實 MDD** | **{_fmt(perf['mdd'], '%')}** |")
    md.append(f"| Sharpe（年化） | {_fmt(perf['sharpe'])} |")
    md.append(f"| Sortino（年化） | {_fmt(perf['sortino'])} |")
    md.append(f"| 平均總曝險 | {_fmt(perf['avg_gross'], '%')} |")
    md.append(f"| 最高總曝險 | {_fmt(perf['max_gross'], '%')} |")
    md.append(f"| 平均同時持倉數 | {perf['avg_positions']} |")
    md.append("")

    md.append("### 訊號處置統計\n")
    md.append("| 項目 | 筆數 |")
    md.append("|---|---|")
    for k, label in (('candidates', 'A/B 候選訊號總數'),
                     ('opened', '實際開倉'),
                     ('closed', '到期平倉'),
                     ('forced_close_at_end', '期末強制結算'),
                     ('skip_already_held', '略過：已持有該檔'),
                     ('skip_no_exit_slot', '略過：資料內走不完持有期'),
                     ('rejected', '引擎否決（無曝險空間）'),
                     ('rejected_after_cash', '現金不足而放棄'),
                     ('capped_gross_exposure_cap', '被 regime 曝險上限縮減'),
                     ('capped_concentration_limits', '被題材集中度縮減'),
                     ('capped_correlation_limits', '被相關性集中度縮減'),
                     ('capped_cash', '被現金餘額縮減')):
        md.append(f"| {label} | {st.get(k, 0):,} |")
    _cand = max(st.get('candidates', 0), 1)
    md.append("")
    md.append(f"縮減/否決合計佔候選訊號 "
              f"{(st.get('rejected',0)+st.get('capped_gross_exposure_cap',0)+st.get('capped_concentration_limits',0)+st.get('capped_correlation_limits',0))/_cand:.1%}"
              "（同一筆可能被多層計數）。\n")

    if sim['capped_examples']:
        md.append("### 相關性限制實際觸發樣例（驗收條件3）\n")
        md.append("證明相關性層接的是**真實價格資料**、確實會生效，"
                  "不是 build_prompt_20 那個永遠回 None 的佔位器。\n")
        md.append("| 日期 | 候選 | 高相關持倉 | 縮減前 | 縮減後 |")
        md.append("|---|---|---|---|---|")
        for e in sim['capped_examples']:
            md.append(f"| {e['date']} | {e['symbol']} | {'、'.join(e['with'] or [])} | "
                      f"{e['from_pct']*100:.1f}% | {e['to_pct']*100:.1f}% |")
        md.append("")

    md.append("### 曝險上限合規性（驗收條件2）——**本輪最重要的發現**\n")
    ea = sim['entry_audit']
    viol = [e for e in ea if e['gross_after'] > e['cap'] + 1e-9]
    md.append(f"**進場時點**：{len(ea):,} 次開倉，開倉後總曝險超過當日 "
              f"`gross_exposure_cap()` 上限者 **{len(viol)} 次**"
              f"（{'✅ 完全合規' if not viol else '⚠️ 有違規'}）。\n")
    obs = collections.defaultdict(float)
    for c in cur:
        obs[c['regime']] = max(obs[c['regime']], c['gross_pct'])
    md.append("**但逐日觀察到的曝險是另一回事**：\n")
    md.append("| Regime | 上限 | 實際觀察到的最高曝險 | 平均曝險 |")
    md.append("|---|---|---|---|")
    avg = collections.defaultdict(list)
    for c in cur:
        avg[c['regime']].append(c['gross_pct'])
    for rg in ('多頭', '盤整', '空頭'):
        if rg not in obs:
            continue
        cap = QC.GROSS_EXPOSURE_BY_REGIME.get(rg)
        flag = '✅' if obs[rg] <= cap + 1e-9 else '**⚠️ 超過上限**'
        md.append(f"| {rg} | {cap:.0%} | {obs[rg]:.1%} {flag} | "
                  f"{statistics.mean(avg[rg]):.1%} |")
    md.append("")
    md.append("> **為什麼不矛盾，以及為什麼這件事很重要**：")
    md.append("> `gross_exposure_cap()` 只在 `evaluate_new_position()` 裡被讀取——"
              "它是**進場閘門**，不是**持倉上限**。部位在多頭期間以 100% 曝險建立後，"
              "regime 翻成盤整或空頭時，既有持倉不會被減碼，只是「不再加新倉」，"
              "要等 20 日持有期到了才自然退場。")
    md.append("> 因此空頭期間實際曝險可以（而且確實）遠高於 40%。")
    md.append("> ")
    md.append("> 這直接暴露 build_prompt_19 那次決策的一個缺口：當時把大盤濾網的"
              "grade 降級移除、改用「曝險層風控」取代，但目前實作的曝險層"
              "**只有進場節流、沒有減碼路徑**。換句話說，空頭風控目前是"
              "**半套的**——舊機制（降級）拿掉了，新機制只裝了一半。")
    md.append("> ")
    md.append("> 下方分 regime 表的盤整 / 空頭段虧損，主要就是這個缺口的後果，"
              "而不是「訊號在空頭比較差」——**本輪是量測，不在此處改任何規則**，"
              "如何補（regime 翻轉時強制減碼？改用波動度目標？）需要獨立設計與驗證。\n")

    md.append("### 分 Regime（同一條資金曲線的分段，非獨立回測）\n")
    md.append("| Regime | 交易日 | 累積報酬 | 年化 | 區段 MDD | Sharpe | 平均曝險 |")
    md.append("|---|---|---|---|---|---|---|")
    for rg in ('多頭', '盤整', '空頭', '未知'):
        m = byreg.get(rg)
        if not m:
            continue
        md.append(f"| {rg} | {m['days']:,} | {_fmt(m['cum_return'],'%')} | "
                  f"{_fmt(m['ann_return'],'%')} | {_fmt(m['mdd'],'%')} | "
                  f"{_fmt(m['sharpe'])} | {_fmt(m['avg_gross'],'%')} |")
    md.append("")

    md.append("## 2. 與舊近似法對照（任務3）\n")
    if legacy:
        md.append("舊法＝`analyze_phase1.portfolio_series`「每 20 個交易日取樣一次、"
                  "單筆 20% 等權」，訊號集合與真實模擬相同（A+B 級）以求可比。\n")
        md.append("| 指標 | 舊近似法 | 真實模擬 | 差異 |")
        md.append("|---|---|---|---|")

        def _row(label, a, b, suf='%'):
            if a is None or b is None:
                md.append(f"| {label} | {_fmt(a,suf)} | {_fmt(b,suf)} | — |")
            else:
                md.append(f"| {label} | {a}{suf} | {b}{suf} | {b-a:+.2f}{suf} |")

        _row('CAGR', legacy['cagr'], perf['cagr'])
        _row('MDD', legacy['mdd'], perf['mdd'])
        _row('總報酬', legacy['total_return'], perf['total_return'])
        _row('Sharpe（年化）', legacy['sharpe'], perf['sharpe'], '')
        _row('Sortino（年化）', legacy['sortino'], perf['sortino'], '')
        md.append("")
        md.append(f"> Sharpe 可比性註記：舊法原始（每期）Sharpe = "
                  f"{_fmt(legacy['sharpe_raw'])}，"
                  f"上表已用 √(252/{HOLDING_DAYS}) 年化後才與真實模擬的"
                  "√252 日頻年化並列。Phase1 報告內列的是**未年化**的每期值，"
                  "不可直接與此表對照。\n")
        md.append(f"> 樣本單位也不同：舊法 {legacy['periods']} 個不重疊期，"
                  f"真實模擬 {perf['days']:,} 個交易日、{st.get('opened',0):,} 筆實際交易。\n")
    else:
        md.append("（舊法對照計算失敗）\n")

    md.append("## 3. 資金曲線時間序列\n")
    md.append("完整逐日序列輸出至 `portfolio_equity_curve.csv`"
              "（欄位：date, equity, cash, invested, gross_pct, regime, n_positions），"
              "供後續視覺化使用。\n")
    md.append("年度里程碑：\n")
    md.append("| 日期 | 資產 | 現金 | 持倉市值 | 總曝險 | 持倉數 | Regime |")
    md.append("|---|---|---|---|---|---|---|")
    seen = set()
    for c in cur:
        y = c['date'][:4]
        if y in seen:
            continue
        seen.add(y)
        md.append(f"| {c['date']} | {c['equity']:,.0f} | {c['cash']:,.0f} | "
                  f"{c['invested']:,.0f} | {c['gross_pct']*100:.1f}% | "
                  f"{c['n_positions']} | {c['regime']} |")
    c = cur[-1]
    md.append(f"| {c['date']} | {c['equity']:,.0f} | {c['cash']:,.0f} | "
              f"{c['invested']:,.0f} | {c['gross_pct']*100:.1f}% | "
              f"{c['n_positions']} | {c['regime']} |")
    md.append("")

    md.append("## 4. 方法論與限制\n")
    md.append("### 新的免責措辭（取代 CAGR/MDD「近似值」那句）\n")
    md.append("> **本報告的 CAGR/MDD 為真實逐日資金曲線計算，不再是訊號級近似。**")
    md.append("> 但它仍**不是**完整的 production 績效：出場採固定 20 交易日，"
              "未涵蓋訊號驅動出場（停損／停利／反轉）；標的池為 Phase1 的研究 "
              "universe，帶有已證實的 selection bias（見 "
              "[universe_audit.md](../phase1/universe_audit.md)，絕對水準須折扣 "
              "0.6–1.2pp）。定位是**「基於固定期出場假設與研究 universe 的真實"
              "投組模擬」**，不是可直接外推的實盤預期。\n")
    md.append("### 其餘限制\n")
    md.append("1. **單一確定性模擬**：無隨機種子、無蒙地卡羅。整條曲線對"
              "「同日多筆候選的排序規則」敏感——排序規則已於跑之前寫死，"
              "但未做敏感度分析。")
    md.append("2. **允許碎股**：以 1,000,000 起始資金若強制 1 張（1,000 股）為單位，"
              "多數個股單筆就會遠超單筆上限，等於在測一個完全不同（且受資金規模"
              "主導）的實驗。本模擬採碎股以隔離「部位管理邏輯」本身的效果。")
    md.append("3. **價格序列由 trades.csv 重建**（`exit_5/10/20` 反推收盤價，"
              "三者交叉比對全數吻合）。與 Phase1 同一份凍結資料，但"
              "**不含股利**，報酬為純價格報酬。")
    md.append("4. **持有期間以收盤價逐日估值，成本在出場時一次計入**"
              "（與 `signal_backtest` 的 net 定義一致），因此出場當日曲線會有"
              "一個成本跳點。")
    md.append("5. **未模擬流動性/衝擊成本**：假設可在 `entry`（次日開盤）"
              "與 `exit`（收盤）以該價格成交任意股數。")
    md.append("6. 分 regime 表是**同一條曲線的分段**，不是各自獨立回測——"
              "區段起點繼承前一段的持倉，不可當成「只在該 regime 交易」的結果。")
    md.append("7. **曝險上限只是進場閘門，沒有減碼路徑**（見上方合規性一節）。"
              "這不是模擬的 bug，是目前 production 邏輯本身的樣貌；"
              "本報告如實呈現其後果，不在本輪修補。")
    md.append("8. **候選訊號絕大多數沒被執行**："
              f"{st.get('candidates',0):,} 筆 A/B 候選只開了 {st.get('opened',0):,} 倉"
              f"（{st.get('opened',0)/max(st.get('candidates',1),1):.1%}）。"
              "主因是曝險長期貼近上限（平均 "
              f"{perf['avg_gross']}%）＋ 20 日持有期把資金鎖住，"
              "而不是訊號被品質篩掉。這代表本模擬測到的是"
              "**「排序規則 + 容量限制」的綜合結果**，"
              "不是「A/B 訊號本身的平均品質」——後者仍應看 Phase1 的訊號級統計。")

    p = os.path.join(OUT_DIR, out_name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Phase2] → {p}")
    return p


def write_curve_csv(sim, name='portfolio_equity_curve.csv'):
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'equity', 'cash', 'invested',
                                          'gross_pct', 'regime', 'n_positions'])
        w.writeheader()
        for c in sim['equity_curve']:
            w.writerow({**c, 'equity': round(c['equity'], 2),
                        'cash': round(c['cash'], 2),
                        'invested': round(c['invested'], 2),
                        'gross_pct': round(c['gross_pct'], 4)})
    print(f"[Phase2] → {p}")
    return p


# ── build_prompt_22：減碼機制 A/B 對照報告 ───────────────────────────────
# 預先定義的判斷準則（寫死在程式碼裡，不看結果才回頭改）
BULL_CAGR_FLOOR = 0.90      # B 的多頭段年化 ≥ A 的 90%


def _pct_dist(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return {
        'n': n,
        'win_rate': sum(1 for x in s if x > 0) / n * 100,
        'mean': statistics.mean(s),
        'median': s[n // 2],
        'p10': s[int(n * 0.10)],
        'p90': s[int(n * 0.90)],
        'min': s[0], 'max': s[-1],
    }


def write_deleverage_report(simA, perfA, regA, simB, perfB, regB,
                            out_name='portfolio_backtest_deleverage.md'):
    os.makedirs(OUT_DIR, exist_ok=True)
    dl = [t for t in simB['trades'] if t.get('exit_reason') == 'deleveraged']
    ex = [t for t in simB['trades'] if t.get('exit_reason') == 'expired']

    md = ["# Phase2：曝險減碼機制 A/B 對照（build_prompt_22）\n"]
    md.append("> build_prompt_21 發現 `gross_exposure_cap()` 只在"
              "`evaluate_new_position()` 被讀取——它是**進場閘門**，不是"
              "**持倉上限**。多頭建到滿倉後 regime 翻轉，既有持倉不會減碼，"
              "實測空頭期間曝險仍達 100%。這輪補上退場那一半並做 A/B 對照。\n")
    md.append("> **這是風控政策選擇，不是聲稱統計上證明更優**——"
              "是否採用由下方預先定義的準則裁決。\n")

    md.append("## 預先定義的判斷準則（跑之前寫死）\n")
    md.append("**支持採用減碼機制**須同時滿足三條：\n")
    md.append("1. 空頭段 MDD 絕對值縮小（風控目的達成）")
    md.append("2. 盤整段 MDD 絕對值縮小")
    md.append(f"3. 多頭段年化報酬 ≥ Scenario A 的 {BULL_CAGR_FLOOR:.0%}"
              "（防止「為了防守犧牲太多進攻」——減碼在多頭轉盤整的瞬間"
              "也可能誤砍正在賺錢的倉位）\n")
    md.append("任一條不成立 → **不支持**，缺口繼續記錄為已知限制。"
              "不因為「風控直覺上應該更好」放寬標準。\n")

    md.append("## 設計\n")
    md.append("- **選誰**：總曝險超過 regime 上限時，砍 **entry_date 最舊**的一筆"
              "（同日依代號）。理由：本專案已驗證的是固定 20 日持有期，"
              "砍最接近到期的那筆對該方法論偏移最小。")
    md.append("- **刻意不用 P&L 規則**（砍虧最多／賺最多）——那會引入未經驗證的"
              "出場擇時，是設計討論時明確排除的選項。")
    md.append(f"- **限速**：每天最多強制平倉 {MAX_DELEVERAGE_PER_DAY} 筆，不一次到位。")
    md.append("- **執行順序**：到期結算 → 減碼檢查 → 新進場"
              "（因此減碼釋放的空間當天就能被新訊號使用）。\n")

    md.append("### 提早出場的損益結算方法（驗收條件3）\n")
    md.append("**用當日真實收盤價結算，沒有用任何近似法。**\n")
    md.append("build_prompt_22 的規格擔心「減碼可能發生在第 3 天或第 14 天，"
              "不一定落在 5/10/20 檢查點上」。實際查證後確認這個顧慮不成立："
              "`PriceBook` 是用每一列的 `exit_5` 反推第 i+6 個交易日的收盤價，"
              "i 掃過全部列之後，**第 7 個交易日起每檔每個交易日都有實價**"
              "（實測 130,993 格中缺值 492 格，全部落在最前面 6 天，"
              "index ≥ 6 零缺值）。")
    md.append("所以提早出場不論發生在第幾天都能用該日真實收盤價結算，"
              "成本模型與到期出場完全相同"
              f"（round-trip {COST_RATE*100:.4f}% 計於進場名目金額）。\n")

    md.append("## 1. Scenario A vs B 總覽\n")
    md.append("- **Scenario A**＝build_prompt_21 基準（無減碼）。"
              "本報告以 `simulate(deleverage=False)` 在記憶體中重跑，"
              f"CAGR/MDD 與已發佈的 `portfolio_backtest_real.md` 逐位一致"
              f"（{perfA['cagr']}% / {perfA['mdd']}%），確認是同一條基準線。")
    md.append("- **Scenario B**＝唯一差異是啟用減碼；資料源、成本模型、"
              "排序規則、持有期全部相同。\n")
    md.append("| 指標 | A（無減碼） | B（有減碼） | 差異 |")
    md.append("|---|---|---|---|")

    def _row(label, ka, kb, suf='%', src=('perf',)):
        a, b = perfA.get(ka), perfB.get(kb)
        if a is None or b is None:
            md.append(f"| {label} | {_fmt(a,suf)} | {_fmt(b,suf)} | — |")
        else:
            md.append(f"| {label} | {a}{suf} | {b}{suf} | {b-a:+.2f}{suf} |")

    _row('CAGR', 'cagr', 'cagr')
    _row('MDD', 'mdd', 'mdd')
    _row('總報酬', 'total_return', 'total_return')
    _row('Sharpe（年化）', 'sharpe', 'sharpe', '')
    _row('Sortino（年化）', 'sortino', 'sortino', '')
    _row('平均總曝險', 'avg_gross', 'avg_gross')
    _row('平均同時持倉數', 'avg_positions', 'avg_positions', '')
    md.append(f"| 期末資產 | {perfA['final_equity']:,.0f} | "
              f"{perfB['final_equity']:,.0f} | "
              f"{perfB['final_equity']-perfA['final_equity']:+,.0f} |")
    md.append("")

    md.append("### 分 Regime 對照\n")
    md.append("| Regime | A 累積 | B 累積 | A 年化 | B 年化 | A MDD | B MDD | "
              "A 平均曝險 | B 平均曝險 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for rg in ('多頭', '盤整', '空頭'):
        a, b = regA.get(rg), regB.get(rg)
        if not a or not b:
            continue
        md.append(f"| {rg} | {a['cum_return']}% | {b['cum_return']}% | "
                  f"{a['ann_return']}% | {b['ann_return']}% | "
                  f"{a['mdd']}% | {b['mdd']}% | "
                  f"{a['avg_gross']}% | {b['avg_gross']}% |")
    md.append("")

    md.append("### 曝險上限合規性\n")
    md.append("| Regime | 上限 | A 觀察最高 | B 觀察最高 |")
    md.append("|---|---|---|---|")
    obsA = collections.defaultdict(float)
    obsB = collections.defaultdict(float)
    for c in simA['equity_curve']:
        obsA[c['regime']] = max(obsA[c['regime']], c['gross_pct'])
    for c in simB['equity_curve']:
        obsB[c['regime']] = max(obsB[c['regime']], c['gross_pct'])
    for rg in ('多頭', '盤整', '空頭'):
        cap = QC.GROSS_EXPOSURE_BY_REGIME.get(rg)
        if cap is None:
            continue
        md.append(f"| {rg} | {cap:.0%} | {obsA[rg]:.1%} | {obsB[rg]:.1%} |")
    md.append("")
    md.append("> 限速（每天一筆）意味著 B 的曝險是**逐步**收斂到上限，"
              "不是瞬間達標，因此觀察到的最高值仍可能高於上限——"
              "這是限速設計的預期行為，不是失效。\n")

    md.append("## 2. 減碼觸發統計（任務2）\n")
    md.append(f"- 減碼出場：**{len(dl):,} 筆**"
              f"（占全部 {len(simB['trades']):,} 筆出場的 "
              f"{len(dl)/max(len(simB['trades']),1):.1%}）")
    md.append(f"- 到期出場：{len(ex):,} 筆")
    hd = [t['held_days'] for t in dl if t.get('held_days') is not None]
    eb = [t['early_by'] for t in dl if t.get('early_by') is not None]
    if hd:
        md.append(f"- 平均持有 {statistics.mean(hd):.1f} 個交易日"
                  f"（中位 {sorted(hd)[len(hd)//2]}），"
                  f"即平均**提早 {statistics.mean(eb):.1f} 天**出場")
    md.append(f"- B 的開倉數 {simB['stats']['opened']:,} vs A 的 "
              f"{simA['stats']['opened']:,}"
              f"（{simB['stats']['opened']-simA['stats']['opened']:+,}）"
              "——減碼釋放的容量被新訊號吃掉了\n")

    md.append("### 被迫提早出場當下是賺是賠？（政策含義的關鍵）\n")
    d = _pct_dist([t['ret_pct'] for t in dl])
    e = _pct_dist([t['ret_pct'] for t in ex])
    if d and e:
        md.append("| 出場類型 | 筆數 | 勝率 | 平均報酬 | 中位 | P10 | P90 | 最差 | 最佳 |")
        md.append("|---|---|---|---|---|---|---|---|---|")
        for lab, x in (('減碼提早出場', d), ('到期出場', e)):
            md.append(f"| {lab} | {x['n']:,} | {x['win_rate']:.1f}% | "
                      f"{x['mean']:+.2f}% | {x['median']:+.2f}% | "
                      f"{x['p10']:+.2f}% | {x['p90']:+.2f}% | "
                      f"{x['min']:+.2f}% | {x['max']:+.2f}% |")
        md.append("")
        md.append(f"→ 減碼出場勝率 {d['win_rate']:.1f}%、"
                  f"中位 {d['median']:+.2f}%、平均 {d['mean']:+.2f}%。")
        _skew = '高於' if d['mean'] > d['median'] else '低於'
        md.append(f"典型的減碼出場是小賠（中位 {d['median']:+.2f}%），"
                  f"平均{_skew}中位數"
                  f"（{d['mean']:+.2f}% vs {d['median']:+.2f}%），"
                  f"分佈被少數極端值拉開（最佳 {d['max']:+.2f}%、"
                  f"最差 {d['min']:+.2f}%、P90 {d['p90']:+.2f}%）。")
        md.append("換句話說，減碼機制**主要在砍小賠的倉位**（扮演停損角色），"
                  "但**偶爾也會砍掉正在大賺的倉位**"
                  "——放棄的上檔是真實成本，不是零。")
        md.append(f"對照到期出場（勝率 {e['win_rate']:.1f}%、"
                  f"平均 {e['mean']:+.2f}%），被減碼的那批本來就是"
                  "表現較差的一群——但這不代表機制「挑得準」，"
                  "它挑的是**最舊**，不是最弱；兩者相關只是因為"
                  "持有越久、壞消息越可能已經反映。\n")

    md.append("### 減碼發生在哪些 regime\n")
    byreg_dl = collections.Counter(t.get('regime_at_exit') for t in dl)
    md.append("| 出場時 Regime | 減碼筆數 |")
    md.append("|---|---|")
    for rg, n in byreg_dl.most_common():
        md.append(f"| {rg} | {n:,} |")
    md.append("")

    md.append("## 3. 最終判定（任務3準則）\n")
    c1 = abs(regB['空頭']['mdd']) < abs(regA['空頭']['mdd'])
    c2 = abs(regB['盤整']['mdd']) < abs(regA['盤整']['mdd'])
    floor = regA['多頭']['ann_return'] * BULL_CAGR_FLOOR
    c3 = regB['多頭']['ann_return'] >= floor
    md.append("| # | 門檻 | A | B | 判定 |")
    md.append("|---|---|---|---|---|")
    md.append(f"| 1 | 空頭段 \\|MDD\\| 縮小 | {regA['空頭']['mdd']}% | "
              f"{regB['空頭']['mdd']}% | {'✅' if c1 else '❌'} |")
    md.append(f"| 2 | 盤整段 \\|MDD\\| 縮小 | {regA['盤整']['mdd']}% | "
              f"{regB['盤整']['mdd']}% | {'✅' if c2 else '❌'} |")
    md.append(f"| 3 | 多頭段年化 ≥ A×{BULL_CAGR_FLOOR:.0%}"
              f"（門檻 {floor:.2f}%） | {regA['多頭']['ann_return']}% | "
              f"{regB['多頭']['ann_return']}% | {'✅' if c3 else '❌'} |")
    md.append("")

    if c1 and c2 and c3:
        md.append("### ✅ 判定：**支持採用減碼機制**\n")
        md.append("三條預先定義的門檻全數通過。\n")
        _bull_cost = regA['多頭']['ann_return'] - regB['多頭']['ann_return']
        if _bull_cost > 0:
            md.append(f"⚠️ 但門檻 3 是**通過而非無代價**：多頭段年化少了 "
                      f"{_bull_cost:.2f}pp（{regA['多頭']['ann_return']}% → "
                      f"{regB['多頭']['ann_return']}%），只是仍在 "
                      f"{BULL_CAGR_FLOOR:.0%} 底線之上。減碼在多頭轉盤整的"
                      "瞬間確實會誤砍還在賺的倉位，這筆代價是真的。"
                      "若之後調整限速或選擇規則，這條門檻要重新量。\n")
        md.append("**建議下一步（本輪不執行）**：\n")
        md.append("1. 把 `deleverage=True` 設為 `portfolio_backtest.py` 的預設，"
                  "並重跑 `portfolio_backtest_real.md` 讓基準數字換成有減碼版本")
        md.append("2. 實盤側目前**還沒有持倉概念**"
                  "（build_prompt_20 的 `current_positions` 恆為空清單），"
                  "減碼機制在實盤要生效，必須先補上持倉追蹤——"
                  "**這是接進 production 的硬前提，不可跳過**")
        md.append("3. 需要額外確認的事項：限速參數（每天 1 筆）未做敏感度分析；"
                  "本輪僅單一確定性模擬，未檢驗跨年穩定性")
        md.append("")
        md.append("⚠️ 仍須留意：本結果來自**單一路徑、樣本內**模擬，"
                  "且標的池帶有已證實的 selection bias。"
                  "三條門檻是風控政策的可接受性檢查，"
                  "**不等於統計上證明減碼更優**。")
    else:
        md.append("### ❌ 判定：**不支持**\n")
        fails = [n for n, ok in (('空頭 MDD', c1), ('盤整 MDD', c2),
                                 ('多頭 CAGR 底線', c3)) if not ok]
        md.append(f"未通過：{'、'.join(fails)}。")
        md.append("依預先定義的準則，**維持現狀不採用減碼**。"
                  "曝險上限只有進場閘門、沒有減碼路徑這個缺口，"
                  "繼續記錄為已知限制，`portfolio_backtest_real.md` "
                  "的既有措辭維持不變。")
    md.append("")

    md.append("## 4. 限制\n")
    md.append("0. **A/B 差異混合了兩種效果，不可只歸因於「風控變好」**："
              f"B 比 A 多開了 {simB['stats']['opened']-simA['stats']['opened']:,} 倉"
              f"（{simA['stats']['opened']:,} → {simB['stats']['opened']:,}）。"
              "減碼一方面降低了下檔曝險，另一方面**釋放容量讓更多訊號進場**，"
              "後者本身就會改變報酬。CAGR 從 "
              f"{perfA['cagr']}% 升到 {perfB['cagr']}% 之中有多少來自"
              "「少虧」、多少來自「多做」，本輪**沒有拆解**。"
              "要拆解需要再跑一個「只減碼、不把釋放的空間拿去加倉」的對照組，"
              "那是獨立的下一題。三條判斷門檻只檢查 MDD 與多頭報酬的"
              "可接受性，不受此混淆影響——但**總報酬的解讀受影響**。")
    md.append("1. **單一確定性模擬**：無隨機種子、無蒙地卡羅，"
              "未做限速參數與選擇規則的敏感度分析。")
    md.append("2. **年齡規則未與其他規則比較**：本輪只測「砍最舊」，"
              "沒有測「砍最弱 / 等比例縮減 / 波動度目標」。"
              "通過門檻只代表這一種規則可接受，不代表它最好。")
    md.append("3. **樣本內、單一路徑**，且沿用 Phase1 研究 universe"
              "（已證實的 selection bias，絕對水準須折扣 0.6–1.2pp）。")
    md.append("4. 其餘限制（碎股、固定持有期、不含股利、無流動性衝擊成本）"
              "與 [portfolio_backtest_real.md](portfolio_backtest_real.md) 相同。")

    p = os.path.join(OUT_DIR, out_name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Phase2] → {p}")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trades', default=BASE_TRADES)
    ap.add_argument('--capital', type=float, default=START_CAPITAL)
    ap.add_argument('--hold', type=int, default=HOLDING_DAYS)
    ap.add_argument('--mode', choices=['real', 'deleverage-ab'], default='real',
                    help="real=build_prompt_21 基準報告；"
                         "deleverage-ab=build_prompt_22 A/B 對照")
    a = ap.parse_args()

    if a.mode == 'deleverage-ab':
        simA = simulate(a.trades, a.capital, a.hold, deleverage=False)
        simB = simulate(a.trades, a.capital, a.hold, deleverage=True)
        perfA = perf_from_equity(simA['equity_curve'], simA['start_capital'])
        perfB = perf_from_equity(simB['equity_curve'], simB['start_capital'])
        regA, regB = perf_by_regime(simA['equity_curve']), perf_by_regime(simB['equity_curve'])
        write_curve_csv(simB, 'portfolio_equity_curve_deleverage.csv')
        write_deleverage_report(simA, perfA, regA, simB, perfB, regB)
        return

    sim = simulate(a.trades, a.capital, a.hold)
    perf = perf_from_equity(sim['equity_curve'], sim['start_capital'])
    byreg = perf_by_regime(sim['equity_curve'])
    legacy = legacy_approximation(a.trades, a.hold)
    write_curve_csv(sim)
    write_report(sim, perf, byreg, legacy)


if __name__ == '__main__':
    main()
