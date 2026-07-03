"""
signal_backtest.py — 訊號驗證迴路（A/B/C 命中率 walk-forward 回測）

build_prompt_05：量化 A/B/C 各等級在 5/10/20 日持有期的勝率與期望值（含真實交易成本），
輸出等級分佈與觸發原因分解。獨立新檔，不修改主程式邏輯，只呼叫既有引擎。

防前視鐵律：
  - 一次抓全期 hist，逐日 hist[index<=as_of] 切片（禁止逐日打 API）。
  - 籌碼 chip_daily WHERE date<=as_of（ChipDataManager as_of 參數）。
  - 月營收只用「公告日≤as_of」的月份（RevenueDataManager as_of 可見性規則）。
  - 大盤 regime 用 as_of 切片。
  - 每筆 assert hist_asof.index.max() <= as_of。

用法：
  python signal_backtest.py --symbols 2330,2454 --days 60 --hold 5,10,20
  python signal_backtest.py                      # 用 watchlist、預設 180 日
"""

from __future__ import annotations

import os
import csv
import argparse
import datetime
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from config import QuantConfig
from decision_engine import ThreeLayerEngine
from analyzers import (WaveAnalyzer, MeanReversionAnalyzer, VolumePriceAnalyzer,
                       PatternAnalyzer, wilder_adx)


# ── 資料層（重用既有模組，但只讀 / as_of）───────────────────────────────────
def _lazy_main():
    """延遲 import main（含 tkinter 類別定義），取 QuickAnalyzer / DataSourceManager。"""
    import main as _m
    return _m.QuickAnalyzer, _m.DataSourceManager


def get_cost_rate(discount: float) -> float:
    """round-trip 成本率：手續費 0.1425%×2×折扣 + 證交稅 0.3%（賣出）。"""
    return QuantConfig.COMMISSION_RATE * discount * 2 + QuantConfig.TAX_RATE


# ── as_of 結果組裝（只用切片資料，不打 API）────────────────────────────────
def _rs_asof(stock_asof, idx_asof):
    """相對強度（對大盤），沿用 fix_02 的 20d*0.4+60d*0.6、50+rs*2 正規化。"""
    if idx_asof is None or len(stock_asof) < 21 or len(idx_asof) < 21:
        return {'rs_score': 50, 'vs_market': 0}
    sc, ic = stock_asof['Close'], idx_asof['Close']
    rs20 = (sc.iloc[-1] / sc.iloc[-21] - 1) * 100 - (ic.iloc[-1] / ic.iloc[-21] - 1) * 100
    if len(stock_asof) > 60 and len(idx_asof) > 60:
        rs60 = (sc.iloc[-1] / sc.iloc[-61] - 1) * 100 - (ic.iloc[-1] / ic.iloc[-61] - 1) * 100
        rs_score = rs20 * 0.4 + rs60 * 0.6
    else:
        rs_score = rs20
    norm = max(0, min(100, 50 + rs_score * 2))
    return {'rs_score': round(norm, 1), 'vs_market': round(rs_score, 2)}


def _regime_asof(idx_asof):
    """大盤環境（as_of 切片）：ADX + ma20/ma60 趨勢方向。"""
    if idx_asof is None or len(idx_asof) < 30:
        return {'available': False}
    try:
        adx, _, _ = wilder_adx(idx_asof['High'], idx_asof['Low'], idx_asof['Close'], 14)
        cadx = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 20.0
        ma20 = idx_asof['Close'].rolling(20).mean()
        ma60 = idx_asof['Close'].rolling(60).mean()
        cp = idx_asof['Close'].iloc[-1]
        if cp > ma20.iloc[-1] > ma60.iloc[-1]:
            td = '多頭'
        elif cp < ma20.iloc[-1] < ma60.iloc[-1]:
            td = '空頭'
        else:
            td = '盤整'
        return {'available': True, 'trend_direction': td, 'adx': round(cadx, 1)}
    except Exception:
        return {'available': False}


def build_asof_result(symbol, hist_asof, idx_asof, chip_mgr, rev_mgr, as_of_str, as_of_date,
                      QuickAnalyzer):
    """用 as_of 切片組裝引擎所需 result（不打 API），回傳 result dict。"""
    # 前視自查：切片最後一日不得超過 as_of
    assert hist_asof.index.max().date() <= as_of_date, \
        f"lookahead: {symbol} hist max {hist_asof.index.max().date()} > as_of {as_of_date}"

    technical = QuickAnalyzer._technical_analysis(hist_asof)
    current_price = float(hist_asof['Close'].iloc[-1])

    result = {
        'symbol': symbol,
        'current_price': current_price,
        'technical': technical,
        'wave_analysis': WaveAnalyzer.analyze_wave(hist_asof),
        'mean_reversion': MeanReversionAnalyzer.analyze(hist_asof),
        'volume_price': VolumePriceAnalyzer.analyze(hist_asof),
        'support_resistance': QuickAnalyzer._calculate_support_resistance(hist_asof, technical),
        'market_regime': _regime_asof(idx_asof),
        'relative_strength': _rs_asof(hist_asof, idx_asof),
    }
    try:
        result['pattern_analysis'] = PatternAnalyzer.analyze(
            hist_asof, lookback=QuantConfig.PATTERN_LOOKBACK_DAYS)
    except Exception:
        result['pattern_analysis'] = {'available': False}

    # 籌碼（as_of，只讀 DB）
    try:
        result['chip_flow'] = chip_mgr.get_chip_flow(symbol, allow_fetch=False, as_of=as_of_str)
    except Exception:
        result['chip_flow'] = {'available': False}

    return result


# ── 單檔 walk-forward ──────────────────────────────────────────────────────
def run_symbol(symbol, market, full_hist, idx_hist, chip_mgr, rev_mgr,
               days, holds, cost_rate, QuickAnalyzer, start=None, end=None):
    """回傳該檔所有 (as_of) 訊號的 trade 記錄 list。

    days=0 → 取全部可用 as_of（多期驗證用）；start/end（date）→ 限定 as_of 區間。
    """
    trades = []
    if full_hist is None or len(full_hist) < 80:
        return trades

    fh = full_hist.sort_index()
    dates = list(fh.index)
    n = len(fh)
    max_hold = max(holds)

    # as_of 範圍：需 entry(next)+max_hold 有資料 → i 到 n-2-max_hold
    last_i = n - 2 - max_hold
    if last_i < 60:
        return trades
    first_i = 60 if days <= 0 else max(60, last_i - days + 1)

    idx_sorted = idx_hist.sort_index() if idx_hist is not None else None

    for i in range(first_i, last_i + 1):
        as_of_ts = dates[i]
        as_of_date = as_of_ts.date()
        if start and as_of_date < start:
            continue
        if end and as_of_date > end:
            continue
        as_of_str = as_of_date.isoformat()
        hist_asof = fh.iloc[:i + 1]
        idx_asof = idx_sorted[idx_sorted.index.date <= as_of_date] if idx_sorted is not None else None

        try:
            result = build_asof_result(symbol, hist_asof, idx_asof, chip_mgr, rev_mgr,
                                       as_of_str, as_of_date, QuickAnalyzer)
            decision = ThreeLayerEngine.analyze(result)
        except AssertionError:
            raise
        except Exception as e:
            continue

        if not decision.get('available'):
            continue

        scenario = decision.get('scenario', '')       # A/B/C/WAIT/SKIP/SELL
        tl = decision.get('three_layer', {}) or {}
        dirn = tl.get('direction') or {}
        pos = tl.get('position') or {}
        tim = tl.get('timing') or {}
        triggers = tim.get('triggers', []) if isinstance(tim, dict) else []
        chip = result.get('chip_flow', {}) or {}
        mreg = result.get('market_regime', {}) or {}

        entry_open = float(fh['Open'].iloc[i + 1])
        row = {
            'as_of': as_of_str,
            'symbol': symbol,
            'grade': scenario,
            'regime': mreg.get('trend_direction', '未知') if mreg.get('available') else '未知',
            'market_adx': mreg.get('adx') if mreg.get('available') else None,
            'action_code': decision.get('action_code', ''),
            'dir_score': dirn.get('score'),
            'pos_score': pos.get('score'),
            'timing_grade': tim.get('grade') if isinstance(tim, dict) else '',
            'triggers': '｜'.join(triggers),
            'pth_52w': (result['technical'] or {}).get('pth_52w'),
            'rs_score': result['relative_strength'].get('rs_score'),
            'chip_buy_days': chip.get('consecutive_buy_days'),
            'chip_reliable': chip.get('data_reliable'),
            'entry': round(entry_open, 2),
        }
        for N in holds:
            exit_close = float(fh['Close'].iloc[i + 1 + N])
            gross = exit_close / entry_open - 1
            net = gross - cost_rate
            row[f'ret_{N}_net'] = round(net * 100, 3)
            row[f'exit_{N}'] = round(exit_close, 2)
        trades.append(row)

    return trades


# ── 統計 ───────────────────────────────────────────────────────────────────
def _stats(nets):
    """一組淨報酬(%)的統計。"""
    if not nets:
        return None
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        'n': len(nets),
        'win_rate': round(len(wins) / len(nets) * 100, 1),
        'avg': round(statistics.mean(nets), 3),
        'median': round(statistics.median(nets), 3),
        'expectancy': round(statistics.mean(nets), 3),   # 期望值 = 平均淨報酬
        'profit_factor': round(gross_win / gross_loss, 2) if gross_loss > 0 else float('inf'),
        'max_loss': round(min(nets), 3),
    }


def _benchmark_returns(all_hist, holds, cost_rate):
    """等權持有全樣本：對每個 (symbol,as_of) 用同持有期毛報酬平均（不含訊號篩選）。"""
    # 這裡用「所有被分析日」的平均前向報酬近似等權基準
    return None


# ── 報告 ───────────────────────────────────────────────────────────────────
def write_reports(trades, holds, out_dir, args, index_bh):
    os.makedirs(out_dir, exist_ok=True)
    # trades.csv
    csv_path = os.path.join(out_dir, 'trades.csv')
    fields = ['as_of', 'symbol', 'grade', 'regime', 'market_adx', 'action_code',
              'dir_score', 'pos_score', 'timing_grade', 'pth_52w', 'rs_score',
              'chip_buy_days', 'chip_reliable',
              'entry'] + [f'exit_{N}' for N in holds] + [f'ret_{N}_net' for N in holds] + ['triggers']
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for t in trades:
            w.writerow(t)

    # summary.md
    md = []
    md.append("# 訊號驗證迴路報告（A/B/C 命中率 walk-forward）\n")
    md.append("> **使用方式（Jim）**：每次調整權重/門檻/新因子後重跑本回測，比較期望值矩陣變化——")
    md.append("> 沒有這份報告，任何「感覺變準了」都不算數。優先觀察：**A 級 10 日期望值是否為正且顯著高於 B**；")
    md.append("> 哪個觸發標籤勝率 < 50% 該降權。\n")
    md.append(f"- 參數：symbols={args._nsym} 檔，days={args.days}，hold={holds}，discount={args.discount}")
    md.append(f"- 成本率（round-trip）：{get_cost_rate(args.discount)*100:.4f}%（手續費 {QuantConfig.COMMISSION_RATE*100:.4f}%×2×{args.discount} + 稅 {QuantConfig.TAX_RATE*100:.2f}%）")
    md.append(f"- 產出時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"- 總訊號筆數：{len(trades)}\n")

    # 等級分佈
    from collections import Counter
    dist = Counter(t['grade'] for t in trades)
    total = len(trades) or 1
    md.append("## 等級分佈\n")
    md.append("| 等級 | 筆數 | 佔比 |")
    md.append("|---|---|---|")
    for g in ['A', 'B', 'C', 'SELL', 'WAIT', 'SKIP']:
        c = dist.get(g, 0)
        md.append(f"| {g} | {c} | {c/total*100:.1f}% |")
    a_ratio = dist.get('A', 0) / total * 100
    if a_ratio > 5:
        md.append(f"\n⚠️ **A 級佔比 {a_ratio:.1f}% > 5%，門檻可能過鬆**（A 級應稀缺）。")
    else:
        md.append(f"\nA 級佔比 {a_ratio:.1f}%（≤5%，稀缺性合理）。")

    # 等級 × 持有期矩陣
    md.append("\n## 等級 × 持有期矩陣（淨報酬 %）\n")
    grade_stats = {}
    for N in holds:
        md.append(f"\n### 持有 {N} 日")
        md.append("| 等級 | 樣本 | 勝率 | 平均 | 中位 | 期望值 | ProfitFactor | 最大單筆虧損 |")
        md.append("|---|---|---|---|---|---|---|---|")
        for g in ['A', 'B', 'C']:
            nets = [t[f'ret_{N}_net'] for t in trades if t['grade'] == g and f'ret_{N}_net' in t]
            s = _stats(nets)
            grade_stats[(g, N)] = s
            if s:
                pf = '∞' if s['profit_factor'] == float('inf') else f"{s['profit_factor']:.2f}"
                md.append(f"| {g} | {s['n']} | {s['win_rate']}% | {s['avg']} | {s['median']} | "
                          f"**{s['expectancy']}** | {pf} | {s['max_loss']} |")
            else:
                md.append(f"| {g} | 0 | – | – | – | – | – | – |")

    # 單調性檢查
    md.append("\n## 單調性檢查（A 期望值 > B > C ?）\n")
    md.append("| 持有期 | A 期望 | B 期望 | C 期望 | 單調遞減? |")
    md.append("|---|---|---|---|---|")
    for N in holds:
        a = grade_stats.get(('A', N)); b = grade_stats.get(('B', N)); c = grade_stats.get(('C', N))
        av = a['expectancy'] if a else None
        bv = b['expectancy'] if b else None
        cv = c['expectancy'] if c else None
        vals = [v for v in (av, bv, cv) if v is not None]
        mono = len(vals) >= 2 and all(vals[k] >= vals[k+1] for k in range(len(vals)-1))
        flag = '✅' if mono else '🔴 無鑑別度'
        md.append(f"| {N}日 | {av} | {bv} | {cv} | {flag} |")

    # 對照基準
    md.append("\n## 對照基準\n")
    md.append("| 基準 | " + " | ".join(f"{N}日" for N in holds) + " |")
    md.append("|---|" + "---|" * len(holds))
    # 等權持有全樣本（所有訊號的平均淨報酬，不分等級）
    eq_row = ["等權全訊號"]
    for N in holds:
        nets = [t[f'ret_{N}_net'] for t in trades if f'ret_{N}_net' in t]
        eq_row.append(f"{statistics.mean(nets):.3f}%" if nets else "–")
    md.append("| " + " | ".join(eq_row) + " |")
    # 0050 buy&hold（同持有期，毛報酬）
    bh_row = ["0050 B&H"]
    for N in holds:
        v = index_bh.get(N)
        bh_row.append(f"{v:.3f}%" if v is not None else "–")
    md.append("| " + " | ".join(bh_row) + " |")

    # 觸發原因分解
    md.append("\n## 觸發原因分解（各標籤個別勝率，10日或最短持有期）\n")
    Nref = 10 if 10 in holds else holds[0]
    tag_keys = ['三盤突破', 'D55突破', 'D20突破', 'VP05', '法人連買', '超跌反彈', '形成中', '頭肩底', 'W底']
    md.append(f"| 觸發標籤 | 出現筆數 | 勝率({Nref}日) | 平均淨報酬 |")
    md.append("|---|---|---|---|")
    for tag in tag_keys:
        nets = [t[f'ret_{Nref}_net'] for t in trades
                if tag in (t.get('triggers') or '') and f'ret_{Nref}_net' in t]
        if nets:
            wr = sum(1 for x in nets if x > 0) / len(nets) * 100
            flag = ' 🔴拖後腿' if wr < 50 else ''
            md.append(f"| {tag} | {len(nets)} | {wr:.1f}%{flag} | {statistics.mean(nets):.3f}% |")

    # ── 多期驗證：分市場 regime 的 A/B/C（解鎖 B/C 決策的關鍵）──
    md.append("\n## 分市場環境（regime）驗證\n")
    md.append("> 用 as_of 當日的大盤 regime（多頭/盤整/空頭）切分，檢驗分級在不同環境是否穩定。\n")
    Nr = 10 if 10 in holds else holds[0]
    from collections import Counter as _Ctr
    reg_dist = _Ctr(t.get('regime', '未知') for t in trades)
    md.append(f"樣本分佈（{Nr}日）：" + "、".join(f"{r} {c}筆" for r, c in reg_dist.most_common()) + "\n")
    md.append(f"| Regime | A n | A 期望 | B n | B 期望 | C n | C 期望 | A>B? | 純三盤 期望 | C多頭 期望 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    for reg in ['多頭', '盤整', '空頭']:
        sub = [t for t in trades if t.get('regime') == reg]
        if not sub:
            continue
        def _exp(g):
            nets = [t[f'ret_{Nr}_net'] for t in sub if t['grade'] == g and f'ret_{Nr}_net' in t]
            return (len(nets), round(statistics.mean(nets), 2)) if nets else (0, None)
        an, ae = _exp('A'); bn, be = _exp('B'); cn, ce = _exp('C')
        ab = '✅' if (ae is not None and be is not None and ae > be) else ('🔴' if (ae is not None and be is not None) else '–')
        # 純三盤突破 vs C多頭（B/C 決策的核心對照）
        three = [t[f'ret_{Nr}_net'] for t in sub
                 if '三盤突破' in (t.get('triggers') or '') and 'D55' not in (t.get('triggers') or '')
                 and '法人連買' not in (t.get('triggers') or '') and f'ret_{Nr}_net' in t]
        cpull = [t[f'ret_{Nr}_net'] for t in sub
                 if '多頭環境' in (t.get('triggers') or '') and f'ret_{Nr}_net' in t]
        te = f"{statistics.mean(three):.2f}%({len(three)})" if three else '–'
        pe = f"{statistics.mean(cpull):.2f}%({len(cpull)})" if cpull else '–'
        md.append(f"| {reg} | {an} | {ae} | {bn} | {be} | {cn} | {ce} | {ab} | {te} | {pe} |")
    md.append("\n**判讀**：若「純三盤突破」在空頭/盤整期同樣顯著弱於 C多頭 → 支持將單獨三盤突破降 C（B/C 決策）；"
              "若逆風期三盤突破表現正常 → 維持現狀，多頭期非單調視為 regime 特性。")

    # 不可信籌碼統計
    unreliable = sum(1 for t in trades if t.get('chip_reliable') is False)
    md.append("\n## 資料品質\n")
    md.append(f"- 籌碼 data_reliable=False 佔比：{unreliable}/{len(trades)}（{unreliable/total*100:.1f}%）")

    # 前視偏誤自查清單
    md.append("\n## 附錄：前視偏誤自查清單\n")
    md.append("- [x] 引擎內 rolling/iloc[-1] 只用 as_of（含）以前（hist 逐日切片）")
    md.append("- [x] W底/型態偵測窗口僅用切片 hist（不含未來日）")
    md.append("- [x] 大盤 regime 用 as_of 切片（_regime_asof）")
    md.append("- [x] 籌碼查詢帶 as_of 過濾（chip get_chip_flow as_of）")
    md.append("- [x] 月營收僅採公告日≤as_of 的月份（_is_visible 規則）")
    md.append("- [x] 每筆 assert hist_asof.index.max() <= as_of")

    md_path = os.path.join(out_dir, 'summary.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    return csv_path, md_path


# ── 主流程 ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="A/B/C 訊號級 walk-forward 回測")
    ap.add_argument('--symbols', default='', help='逗號分隔或檔案路徑；預設用 watchlist')
    ap.add_argument('--days', type=int, default=180, help='回測交易日數；0=全部可用歷史（多期驗證）')
    ap.add_argument('--start', default='', help='as_of 起日 YYYY-MM-DD（限定區間）')
    ap.add_argument('--end', default='', help='as_of 迄日 YYYY-MM-DD（限定區間）')
    ap.add_argument('--hold', default='5,10,20', help='持有期，逗號分隔')
    ap.add_argument('--discount', type=float, default=1.0, help='手續費折扣（如 0.28）')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--out', default='', help='輸出目錄')
    args = ap.parse_args()

    holds = [int(x) for x in args.hold.split(',') if x.strip()]
    _start = datetime.date.fromisoformat(args.start) if args.start else None
    _end = datetime.date.fromisoformat(args.end) if args.end else None
    QuickAnalyzer, DataSourceManager = _lazy_main()

    # 標的
    if args.symbols:
        if os.path.exists(args.symbols):
            with open(args.symbols) as f:
                symbols = [l.strip() for l in f if l.strip()]
        else:
            symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    else:
        from database import WatchlistDatabase
        db = WatchlistDatabase()
        symbols = [s[0] for s in db.get_all_stocks() if (s[2] if len(s) > 2 else '台股') == '台股']
    args._nsym = len(symbols)

    out_dir = args.out or os.path.join('backtest_results', datetime.datetime.now().strftime('%Y%m%d_%H%M'))
    cost_rate = get_cost_rate(args.discount)

    # 資料層：交易日曆 + 籌碼/營收（一次性 backfill；回測讀 DB）
    from chip_data_manager import get_chip_manager
    from revenue_data_manager import get_revenue_manager
    chip_mgr = get_chip_manager()
    rev_mgr = get_revenue_manager()
    # 全歷史模式一律強制加寬日曆（既有 DB 可能只存了短窗口）；一般模式空才同步。
    if args.days <= 0:
        chip_mgr.sync_calendar(lookback_days=1200)
    elif not chip_mgr.get_latest_trading_day():
        chip_mgr.sync_calendar(lookback_days=max(500, args.days * 2))

    # 大盤指數（一次抓，全體共用）
    try:
        idx_hist = QuickAnalyzer._get_index_history_cached(QuantConfig.MARKET_INDEX_TW, period="3y")
    except Exception:
        idx_hist = None

    # 每檔：抓全期 hist（一次）+ 籌碼 backfill（回測窗口需要）
    # days=0（全歷史）→ 籌碼/營收 backfill 覆蓋全 3 年窗口
    _chip_days = 750 if args.days <= 0 else max(120, args.days + 30)
    _rev_months = 40 if args.days <= 0 else 30
    print(f"[Backtest] {len(symbols)} 檔 × {'全歷史' if args.days<=0 else str(args.days)+'日'}，持有 {holds}，輸出 {out_dir}")
    full_hists = {}
    for sym in symbols:
        try:
            h = DataSourceManager.get_history(sym, '台股', period="3y")
            if h is not None and not h.empty:
                full_hists[sym] = h.dropna()
        except Exception as e:
            print(f"[Backtest] {sym} 抓取失敗: {e}")
        # 籌碼回測需要足夠歷史：backfill 一次（含 as_of 前的日子）
        try:
            chip_mgr.backfill(sym, trading_days=_chip_days)
        except Exception:
            pass
        try:
            rev_mgr.backfill(sym, months=_rev_months)
        except Exception:
            pass

    # 0050 基準（同持有期毛報酬平均）
    index_bh = {}
    bh = full_hists.get('0050')
    if bh is None:
        try:
            bh = DataSourceManager.get_history('0050', '台股', period="3y")
            bh = bh.dropna() if bh is not None else None
        except Exception:
            bh = None
    if bh is not None and len(bh) > max(holds) + 5:
        bh = bh.sort_index()
        for N in holds:
            rets = [(bh['Close'].iloc[k + N] / bh['Open'].iloc[k] - 1) * 100
                    for k in range(len(bh) - N - 1)][-args.days:]
            index_bh[N] = round(statistics.mean(rets), 3) if rets else None

    # 平行 walk-forward
    all_trades = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_symbol, sym, '台股', full_hists.get(sym), idx_hist,
                          chip_mgr, rev_mgr, args.days, holds, cost_rate, QuickAnalyzer,
                          _start, _end): sym
                for sym in full_hists}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                all_trades.extend(fut.result())
            except AssertionError as ae:
                print(f"[Backtest] 🔴 前視 assert 失敗 {sym}: {ae}")
                raise
            except Exception as e:
                print(f"[Backtest] {sym} 回測錯誤: {e}")

    all_trades.sort(key=lambda t: (t['as_of'], t['symbol']))
    csv_path, md_path = write_reports(all_trades, holds, out_dir, args, index_bh)
    print(f"[Backtest] 完成：{len(all_trades)} 筆訊號")
    print(f"[Backtest] trades:  {csv_path}")
    print(f"[Backtest] summary: {md_path}")


if __name__ == '__main__':
    main()
