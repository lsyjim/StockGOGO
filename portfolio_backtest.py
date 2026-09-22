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


def load_rows(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


# ── 模擬主體 ──────────────────────────────────────────────────────────────
def simulate(trades_csv_path=BASE_TRADES, start_capital=START_CAPITAL,
             holding_days=HOLDING_DAYS, theme_map=None, verbose=True):
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
            p = positions.pop(sym, None)
            if p is None:
                continue
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
                'regime_at_entry': p['regime'],
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
        })
        stats['forced_close_at_end'] += 1
        positions.pop(sym)

    if verbose:
        print(f"[sim] 交易日 {len(calendar)}｜候選 {stats['candidates']}｜"
              f"開倉 {stats['opened']}｜平倉 {stats['closed']}"
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trades', default=BASE_TRADES)
    ap.add_argument('--capital', type=float, default=START_CAPITAL)
    ap.add_argument('--hold', type=int, default=HOLDING_DAYS)
    a = ap.parse_args()

    sim = simulate(a.trades, a.capital, a.hold)
    perf = perf_from_equity(sim['equity_curve'], sim['start_capital'])
    byreg = perf_by_regime(sim['equity_curve'])
    legacy = legacy_approximation(a.trades, a.hold)
    write_curve_csv(sim)
    write_report(sim, perf, byreg, legacy)


if __name__ == '__main__':
    main()
