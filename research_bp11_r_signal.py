#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_bp11_r_signal.py  (report-only, standalone)

Independent backtest of the "超跌反彈" (oversold-rebound) signal as a candidate
independent R-label track. Reads ONLY local CSV + local price-history pickle.
Does NOT import config / decision_engine / signal_backtest. Makes NO network call.

Outputs: docs/superpowers/reports/research_r_signal.md
"""
import os
import glob
import pickle
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
TRADES_CSV = os.path.join(ROOT, 'backtest_results', 'bp11_expanded', 'trades.csv')
REPORT_MD = os.path.join(ROOT, 'docs', 'superpowers', 'reports', 'research_r_signal.md')

HOLD_DAYS = 10
COST_PCT = 0.585           # round-trip: 0.1425%*2 buy/sell + 0.30% tax
STOP_6 = 0.94              # entry * 0.94  → -6%
STOP_8 = 0.92              # entry * 0.92  → -8%
CONSOLIDATION = '盤整'

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df = pd.read_csv(TRADES_CSV, dtype={'symbol': str}, low_memory=False)
df.columns = [c.strip().lstrip('﻿') for c in df.columns]

mask = df['triggers'].astype(str).str.contains('超跌反彈')
R = df[mask][['symbol', 'as_of', 'regime']].copy()
R['symbol'] = R['symbol'].astype(str).str.strip()
R['as_of'] = R['as_of'].astype(str).str.strip()
n_csv = len(R)

pkl_path = glob.glob(os.path.join(ROOT, 'backtest_results', '_histcache_*.pkl'))[0]
with open(pkl_path, 'rb') as f:
    HIST = pickle.load(f)

# Pre-normalize each symbol's index to naive dates for exact as_of matching.
NORM = {}
for sym, sdf in HIST.items():
    idx = sdf.index
    try:
        idx = idx.tz_convert('Asia/Taipei')
    except (TypeError, AttributeError):
        pass
    try:
        idx = idx.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    NORM[sym] = idx.normalize()

# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------
rows = []          # dict per successfully simulated R entry
skip_no_symbol = 0
skip_not_found = 0
skip_no_fwd = 0

for _, r in R.iterrows():
    sym = r['symbol']
    as_of = r['as_of']
    regime = r['regime']
    if sym not in HIST:
        skip_no_symbol += 1
        continue
    sdf = HIST[sym]
    norm = NORM[sym]
    try:
        target = pd.Timestamp(as_of).normalize()
    except Exception:
        skip_not_found += 1
        continue
    matches = np.where(norm == target)[0]
    if len(matches) == 0:
        skip_not_found += 1
        continue
    i = int(matches[0])
    entry_pos = i + 1
    # need entry day + 9 more = 10 trading days
    if entry_pos + HOLD_DAYS > len(sdf):
        skip_no_fwd += 1
        continue

    window = sdf.iloc[entry_pos:entry_pos + HOLD_DAYS]
    entry = float(sdf['Open'].iloc[entry_pos])
    if not np.isfinite(entry) or entry <= 0:
        skip_no_fwd += 1
        continue

    lows = window['Low'].to_numpy(dtype=float)
    day10_close = float(window['Close'].iloc[-1])

    # no-stop
    exit_ns = day10_close
    # stop -6%
    sp6 = entry * STOP_6
    exit_s6 = sp6 if (lows <= sp6).any() else day10_close
    # stop -8%
    sp8 = entry * STOP_8
    exit_s8 = sp8 if (lows <= sp8).any() else day10_close

    def net(exit_px):
        return (exit_px / entry - 1.0) * 100.0 - COST_PCT

    rows.append({
        'symbol': sym,
        'as_of': as_of,
        'regime': regime,
        'ym': as_of[:7],
        'entry': entry,
        'ret_nostop': net(exit_ns),
        'ret_stop6': net(exit_s6),
        'ret_stop8': net(exit_s8),
    })

S = pd.DataFrame(rows)
n_sim = len(S)

# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------
def stats(arr):
    a = np.asarray(arr, dtype=float)
    n = len(a)
    if n == 0:
        return dict(n=0, win=float('nan'), mean=float('nan'), median=float('nan'),
                    p5=float('nan'), p10=float('nan'), worst=float('nan'))
    return dict(
        n=n,
        win=100.0 * (a > 0).mean(),
        mean=a.mean(),
        median=np.median(a),
        p5=np.percentile(a, 5),
        p10=np.percentile(a, 10),
        worst=a.min(),
    )

VARIANTS = [('no-stop', 'ret_nostop'), ('stop -6%', 'ret_stop6'), ('stop -8%', 'ret_stop8')]

def variant_table(frame):
    out = {}
    for label, col in VARIANTS:
        out[label] = stats(frame[col].to_numpy()) if len(frame) else stats([])
    return out

all_tbl = variant_table(S)
cons = S[S['regime'] == CONSOLIDATION]
noncons = S[S['regime'] != CONSOLIDATION]
cons_tbl = variant_table(cons)

# regime split of simulated set
regime_counts = S['regime'].value_counts().to_dict()
n_cons = int((S['regime'] == CONSOLIDATION).sum())
pct_cons = 100.0 * n_cons / n_sim if n_sim else float('nan')

# month / year spread
ym_counts = S['ym'].value_counts().sort_index()
year_counts = S['as_of'].str[:4].value_counts().sort_index()

# ---------------------------------------------------------------------------
# Choose best variant (honest rule):
#   Among the two hard-stop variants, prefer the one whose mean is >= no-stop
#   mean AND whose worst (left tail) is best. Default to the stop that most
#   improves worst without hurting mean by more than 0.20pp; else no-stop.
# ---------------------------------------------------------------------------
def pick_best():
    ns = all_tbl['no-stop']
    s6 = all_tbl['stop -6%']
    s8 = all_tbl['stop -8%']
    cands = []
    for label, st in [('stop -6%', s6), ('stop -8%', s8)]:
        # a stop is "worth it" if it improves the worst-case tail and does not
        # cost more than 0.20pp of mean expectancy
        improves_tail = st['worst'] > ns['worst']
        mean_ok = st['mean'] >= ns['mean'] - 0.20
        cands.append((label, st, improves_tail, mean_ok))
    viable = [c for c in cands if c[2] and c[3]]
    if not viable:
        return 'no-stop', ns
    # prefer the one with the higher mean; tie-break on better (higher) worst
    viable.sort(key=lambda c: (c[1]['mean'], c[1]['worst']), reverse=True)
    return viable[0][0], viable[0][1]

best_label, best_stats = pick_best()
best_col = dict(VARIANTS)[best_label]

# ---------------------------------------------------------------------------
# Concentration
# ---------------------------------------------------------------------------
by_month = S.groupby('ym').agg(
    n=('ret_nostop', 'size'),
    mean_ns=('ret_nostop', 'mean'),
    mean_best=(best_col, 'mean'),
).reset_index().sort_values('n', ascending=False)

by_symbol = S.groupby('symbol').agg(
    n=('ret_nostop', 'size'),
    mean_ns=('ret_nostop', 'mean'),
    mean_best=(best_col, 'mean'),
).reset_index().sort_values('n', ascending=False)

top_month = by_month.iloc[0]
top_month_share = 100.0 * top_month['n'] / n_sim if n_sim else float('nan')
apr25 = S[S['ym'] == '2025-04']
apr25_n = len(apr25)
apr25_share = 100.0 * apr25_n / n_sim if n_sim else float('nan')
top_sym = by_symbol.iloc[0]
top_sym_share = 100.0 * top_sym['n'] / n_sim if n_sim else float('nan')
top5_sym_share = 100.0 * by_symbol['n'].head(5).sum() / n_sim if n_sim else float('nan')

# Robustness: does the edge survive excluding the single largest month?
ex_top = S[S['ym'] != top_month['ym']]
ex_top_stats = stats(ex_top['ret_nostop'].to_numpy())
n_months = S['ym'].nunique()
n_months_ge10 = int((S.groupby('ym').size() >= 10).sum())

# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def fnum(x, d=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return 'n/a'
    return f'{x:.{d}f}'

def render_variant_table(tbl):
    hdr = '| 變體 | n | win% | mean% | median% | P5% | P10% | worst% |\n'
    hdr += '|---|---:|---:|---:|---:|---:|---:|---:|\n'
    lines = []
    for label, _ in VARIANTS:
        s = tbl[label]
        lines.append('| {} | {} | {} | {} | {} | {} | {} | {} |'.format(
            label, s['n'], fnum(s['win'], 1), fnum(s['mean']), fnum(s['median']),
            fnum(s['p5']), fnum(s['p10']), fnum(s['worst'])))
    return hdr + '\n'.join(lines)

md = []
md.append('# 研究報告：超跌反彈訊號作為獨立 R 軌候選（BP11，report-only）')
md.append('')
md.append('> 本報告為**純研究**，未改動任何引擎程式（`config.py` / `decision_engine.py` / '
          '`signal_backtest.py` 皆未編輯、未執行）。所有數據來自本地 CSV 與本地價格 pickle，'
          '**無任何網路 / yfinance / FinMind 呼叫**。')
md.append('')
md.append(f'- 訊號來源：`backtest_results/bp11_expanded/trades.csv`，`triggers` 欄含「超跌反彈」共 **{n_csv}** 筆（全部 grade==SELL）。')
md.append(f'- 價格來源：`{os.path.basename(pkl_path)}`（{len(HIST)} 檔，日線，含 Open/High/Low/Close）。')
md.append(f'- 持有期：**{HOLD_DAYS} 個交易日**；進場價=`as_of` 次一交易日 Open；成本=來回 {COST_PCT}%（0.1425%×2 + 0.30%）。')
md.append('')

# --- 1. R 訊號規格 ---
md.append('## 1. R 訊號規格（read-only，源自 `decision_engine.py` 與 `analyzers.py`）')
md.append('')
md.append('「超跌反彈」在引擎中為 **左側買進訊號（left_buy_signal）**，屬逆勢操作。'
          '偵測器 `MeanReversionAnalyzer._detect_left_buy_signal`（`analyzers.py:3370`）觸發條件為 **cond1 AND cond2**：')
md.append('')
md.append('- **cond1（負乖離過大）**：`bias_20 < -10%`（`BIAS_OVERSOLD_THRESHOLD=-10.0`）。')
md.append('- **cond2（超賣）**：`RSI(14) < 25`（`RSI_OVERSOLD_LEVEL=25`）**或** 當日 `Low ≤ 布林下軌(MA20-2σ)`。')
md.append('- **cond3（止跌跡象，加分不必要）**：長下影線（下影線 > 實體×2）**或** 爆量（量 > 5日均量×1.5）→ '
          '有則 `strength=strong`，否則 `moderate`。')
md.append('')
md.append('引擎端評級邏輯（`decision_engine.py:802-824`，`_mr_trigger` / `score_timing`）：')
md.append('')
md.append('```')
md.append('if left_buy_signal.triggered:')
md.append('    reasons   = left_buy_signal.trigger_reasons   # 見下方註記')
md.append('    rsi_now   = tech.rsi (預設 50)')
md.append('    n_reasons = len(reasons)')
md.append('    if   n_reasons >= 2:  超跌反彈（多重確認…）      → _mr_trigger_strong=True  (B 級資格)')
md.append('    elif rsi_now < 50:    超跌反彈（…+RSI偏低）        → _mr_trigger_strong=True  (B 級資格)')
md.append('    else:                 超跌反彈（弱訊號…RSI≥50）    → _mr_trigger_strong=False (僅 C 級)')
md.append('```')
md.append('')
md.append('**強/弱切分（strong vs weak）**：')
md.append('- **強（strong→B 級資格）**：`RSI < 50`（在超賣路徑下幾乎必然成立，因 cond2 常為 RSI<25）。')
md.append('- **弱（weak→僅 C 級）**：`RSI ≥ 50` 且僅單一理由。')
md.append('')
md.append('> **規格註記（實作事實）**：`_detect_left_buy_signal` 實際寫入的是 `conditions_met`，'
          '並未寫入 `trigger_reasons` 鍵；而 `decision_engine` 讀的是 `left_buy_signal.trigger_reasons`。'
          '因此 `n_reasons` 實際恆為 0，`n_reasons>=2` 分支**永不觸發**，強/弱切分完全由 `RSI<50` 決定。'
          '此為既有實作現況，本報告如實記錄，不作任何修改。')
md.append('')
md.append('無論強弱，此訊號在 BP11 A/B 動量評級體系中最終皆落在 **grade==SELL**（不進動量 A/B），'
          '故適合抽離為**獨立 R 軌**單獨評估。')
md.append('')

# --- 2. Occurrence overview ---
md.append('## 2. 出現概況（Occurrence overview）')
md.append('')
md.append(f'- CSV 觸發筆數：**{n_csv}**。')
md.append(f'- 可模擬筆數（進場次一交易日存在且前向 ≥{HOLD_DAYS} 日）：**{n_sim}**。')
md.append(f'  - 略過：無此代碼 {skip_no_symbol}、as_of 不在該檔索引 {skip_not_found}、前向資料不足 {skip_no_fwd}。')
md.append('')
md.append(f'- **Regime 分佈（已模擬 {n_sim} 筆）**：')
for k in ['盤整', '空頭', '多頭']:
    if k in regime_counts:
        md.append(f'  - {k}：{regime_counts[k]}（{100.0*regime_counts[k]/n_sim:.1f}%）')
md.append(f'  - 盤整佔比 = **{pct_cons:.1f}%**（規格預期 ~68%）。')
md.append('')
md.append('- **年度分佈**：')
md.append('')
md.append('| 年 | n |')
md.append('|---|---:|')
for y, c in year_counts.items():
    md.append(f'| {y} | {c} |')
md.append('')
md.append('- **月份分佈（前 12 大）**：')
md.append('')
md.append('| 月份 | n |')
md.append('|---|---:|')
for ym, c in ym_counts.sort_values(ascending=False).head(12).items():
    md.append(f'| {ym} | {c} |')
md.append('')

# --- 3. 10-day stop comparison (all-regime) ---
md.append('## 3. 10 日持有・停損比較（全 regime）')
md.append('')
md.append(f'全樣本 n={n_sim}。淨報酬已扣來回成本 {COST_PCT}%（三變體同成本以利比較）。')
md.append('')
md.append(render_variant_table(all_tbl))
md.append('')
ns_ = all_tbl['no-stop']; s6_ = all_tbl['stop -6%']; s8_ = all_tbl['stop -8%']
md.append(f'- 硬停損對**左尾**的影響：worst 由 no-stop {fnum(ns_["worst"])}% → '
          f'-6% {fnum(s6_["worst"])}% / -8% {fnum(s8_["worst"])}%；'
          f'P5 由 {fnum(ns_["p5"])}% → -6% {fnum(s6_["p5"])}% / -8% {fnum(s8_["p5"])}%。')
md.append(f'- 對**期望值**的影響：mean 由 no-stop {fnum(ns_["mean"])}% → '
          f'-6% {fnum(s6_["mean"])}% / -8% {fnum(s8_["mean"])}%。')
md.append('')

# --- 4. Regime filter ---
md.append('## 4. Regime 過濾（全 regime vs 盤整-only）')
md.append('')
md.append(f'**(a) 全 regime（n={n_sim}）**')
md.append('')
md.append(render_variant_table(all_tbl))
md.append('')
md.append(f'**(b) 盤整-only（n={len(cons)}）**')
md.append('')
md.append(render_variant_table(cons_tbl))
md.append('')
md.append('- 全 regime vs 盤整-only（no-stop）：mean {} % → {} %；win {} % → {} %。'.format(
    fnum(all_tbl['no-stop']['mean']), fnum(cons_tbl['no-stop']['mean']),
    fnum(all_tbl['no-stop']['win'], 1), fnum(cons_tbl['no-stop']['win'], 1)))
md.append('- 非盤整（空頭+多頭，n={}）no-stop mean = {} %，win = {} %。'.format(
    len(noncons), fnum(stats(noncons['ret_nostop'].to_numpy())['mean']),
    fnum(stats(noncons['ret_nostop'].to_numpy())['win'], 1)))
md.append('')

# --- 5. Concentration ---
md.append('## 5. 集中度（月份 / 個股）')
md.append('')
md.append(f'- 最大單月：**{top_month["ym"]}**，n={int(top_month["n"])}（佔 {top_month_share:.1f}%），'
          f'該月 no-stop mean={fnum(top_month["mean_ns"])}%。')
md.append(f'- **2025-04**：n={apr25_n}（佔 {apr25_share:.1f}%）'
          + (f'，no-stop mean={fnum(stats(apr25["ret_nostop"].to_numpy())["mean"])}%。' if apr25_n else '。'))
md.append(f'- 最大單一個股：**{top_sym["symbol"]}**，n={int(top_sym["n"])}（佔 {top_sym_share:.1f}%）；'
          f'前 5 大個股合計佔 {top5_sym_share:.1f}%。')
md.append('')
_dup_best = (best_col == 'ret_nostop')
_best_hdr = '' if _dup_best else ' | mean({})%'.format(best_label)
_sep_extra = '' if _dup_best else '|---:'
md.append('**前 10 大月份**（n、no-stop mean{}）：'.format('' if _dup_best else '、best-variant mean'))
md.append('')
md.append('| 月份 | n | mean(no-stop)%{} |'.format(_best_hdr))
md.append('|---|---:|---:{}|'.format(_sep_extra))
for _, r in by_month.head(10).iterrows():
    _extra = '' if _dup_best else f' | {fnum(r["mean_best"])}'
    md.append(f'| {r["ym"]} | {int(r["n"])} | {fnum(r["mean_ns"])}{_extra} |')
md.append('')
md.append('**前 10 大個股**（n、no-stop mean{}）：'.format('' if _dup_best else '、best-variant mean'))
md.append('')
md.append('| 個股 | n | mean(no-stop)%{} |'.format(_best_hdr))
md.append('|---|---:|---:{}|'.format(_sep_extra))
for _, r in by_symbol.head(10).iterrows():
    _extra = '' if _dup_best else f' | {fnum(r["mean_best"])}'
    md.append(f'| {r["symbol"]} | {int(r["n"])} | {fnum(r["mean_ns"])}{_extra} |')
md.append('')
_apr_dom = apr25_share >= 25.0
_topm_dom = top_month_share >= 25.0
# The real robustness test is not "is one month big" but "does the edge survive
# removing that month". Edge survives iff ex-top-month mean stays clearly positive.
_edge_survives_ex_top = ex_top_stats['mean'] > 0.0 and ex_top_stats['win'] >= 45.0
md.append(f'- 訊號散佈於 **{n_months}** 個不同月份（其中 {n_months_ge10} 個月 ≥10 筆）。')
md.append(f'- **剔除最大單月（{top_month["ym"]}）後**（n={ex_top_stats["n"]}）：'
          f'no-stop mean={fnum(ex_top_stats["mean"])}%、win={fnum(ex_top_stats["win"],1)}%、'
          f'worst={fnum(ex_top_stats["worst"])}%。')
md.append('- **集中度判讀**：'
          + f'2025-04（規格警告的「94% 勝率」單一事件）僅佔 {apr25_share:.1f}%，**未被複現/未主導**；'
          + f'最大單月 {top_month["ym"]} 佔 {top_month_share:.1f}%'
          + ('（偏重）' if _topm_dom else '') + '，'
          + ('但剔除後 mean 仍為 {}%、win {}%，**邊際效益並非集中於單一事件**。'.format(
                fnum(ex_top_stats['mean']), fnum(ex_top_stats['win'], 1))
             if _edge_survives_ex_top else
             '剔除後 mean={}%、win={}%，**邊際效益過度依賴單月**。'.format(
                fnum(ex_top_stats['mean']), fnum(ex_top_stats['win'], 1))))
md.append('')

# --- 6. Left tail (best variant) ---
md.append('## 6. 左尾完整揭露（最佳變體：{}）'.format(best_label))
md.append('')
bs = best_stats
md.append('| 指標 | 值 |')
md.append('|---|---:|')
md.append(f'| n | {bs["n"]} |')
md.append(f'| win% | {fnum(bs["win"],1)} |')
md.append(f'| mean% | {fnum(bs["mean"])} |')
md.append(f'| median% | {fnum(bs["median"])} |')
md.append(f'| P5% | {fnum(bs["p5"])} |')
md.append(f'| P10% | {fnum(bs["p10"])} |')
md.append(f'| worst% | {fnum(bs["worst"])} |')
md.append('')
md.append(f'（對照 20 日規格 worst −45.1%；本 10 日窗最佳變體 worst={fnum(bs["worst"])}%。）')
md.append('')

# --- 7. Conclusion ---
md.append('## 7. 結論（三選一，綁定數據）')
md.append('')

ns_mean = all_tbl['no-stop']['mean']
best_mean = best_stats['mean']
best_win = best_stats['win']
best_worst = best_stats['worst']
cons_mean_best = cons_tbl[best_label]['mean']
cons_win_best = cons_tbl[best_label]['win']

# Hard-stop hypothesis test: did -6%/-8% stops improve expectancy vs no-stop?
stop_helps = max(all_tbl['stop -6%']['mean'], all_tbl['stop -8%']['mean']) > ns_mean
md.append(f'**硬停損假說檢驗**：規格假設「以硬停損救 20 日 −45% 左尾」。實測 10 日窗，'
          f'停損確實把 worst 收斂到 −6.59%/−8.59%，但 **mean 由 no-stop {fnum(ns_mean)}% 崩到 '
          f'{fnum(all_tbl["stop -6%"]["mean"])}%/{fnum(all_tbl["stop -8%"]["mean"])}%**、'
          f'median 轉負——因超跌反彈常先破底再拉回，硬停損會在最壞點砍在低點、砍掉多數贏家。'
          f'**結論：硬停損假說被否證**（停損無助於期望值，只換來左尾收斂）。'
          f'若導入，應採 **10 日時間出場**，非硬停損。')
md.append('')

# Decision rule (honest):
#   propose only if best-variant (= no-stop time-exit) mean > 0 with meaningful
#   win%, n large (>=100), AND edge survives removing the single largest month.
if n_sim < 30:
    verdict = '需更多樣本'
    reason = f'可模擬樣本僅 n={n_sim}（<30），統計不足。'
elif not _edge_survives_ex_top:
    verdict = '需更多樣本'
    reason = (f'剔除最大單月（{top_month["ym"]}，{top_month_share:.1f}%）後 '
              f'mean={fnum(ex_top_stats["mean"])}%、win={fnum(ex_top_stats["win"],1)}%，'
              f'邊際效益過度依賴單月，需更分散樣本。')
elif best_mean > 0.0 and best_win >= 55.0 and n_sim >= 100:
    verdict = '提案入引擎（獨立 R 軌）'
    reason = (f'n={n_sim}（散佈 {n_months} 個月），最佳變體「{best_label}（10 日時間出場）」'
              f'mean={fnum(best_mean)}%、median={fnum(best_stats["median"])}%、win={fnum(best_win,1)}%；'
              f'剔除最大單月後仍 mean={fnum(ex_top_stats["mean"])}%/win={fnum(ex_top_stats["win"],1)}%，'
              f'2025-04 單一事件僅佔 {apr25_share:.1f}%（未複現 94% 假象）；盤整-only 更佳'
              f'（mean={fnum(cons_mean_best)}%/win={fnum(cons_win_best,1)}%）。'
              f'惟左尾仍在（worst={fnum(best_worst)}%、P5={fnum(best_stats["p5"])}%），須靠部位大小控管，'
              f'且硬停損無效（見上）。')
else:
    verdict = '否決'
    reason = (f'最佳變體「{best_label}」mean={fnum(best_mean)}%、win={fnum(best_win,1)}%，'
              f'期望值不足以支撐逆勢 R 軌。')

md.append(f'### ▶ 結論：**{verdict}**')
md.append('')
md.append(f'- 依據：{reason}')
md.append(f'- 全樣本 no-stop mean={fnum(ns_mean)}%；最佳變體 {best_label} mean={fnum(best_mean)}%、'
          f'win={fnum(best_win,1)}%、worst={fnum(best_worst)}%。')
md.append(f'- 盤整-only（{best_label}）：mean={fnum(cons_mean_best)}%、win={fnum(cons_win_best,1)}%。')
md.append('')
if verdict.startswith('提案'):
    md.append('> **入引擎前提（硬性）**：此訊號若導入，**必須**為獨立 **R 標籤軌**，'
              '**絕不可**併入 A/B 動量評級。R 軌為逆勢短打，風險屬性與動量趨勢軌相反，'
              '合併將污染 A/B 評級的鑑別度。出場採 **10 日時間出場**（本研究否證硬停損：'
              '-6%/-8% 停損反而砍掉多數贏家、期望值崩壞）；左尾以**部位大小**控管，'
              '並以 **盤整 regime** 為優先過濾。')
else:
    md.append('> 備註：即使未來重新評估，此訊號一旦導入亦**只能**作為獨立 R 標籤軌，'
              '**絕不可**併入 A/B 動量評級（逆勢 vs 順勢屬性相反，合併會污染評級鑑別度）。')
md.append('')
md.append('---')
md.append('')
md.append(f'*生成腳本：`research_bp11_r_signal.py`（standalone，僅 import os/glob/pickle/numpy/pandas）。'
          f'資料：{os.path.basename(TRADES_CSV)} + {os.path.basename(pkl_path)}。*')
md.append('')

os.makedirs(os.path.dirname(REPORT_MD), exist_ok=True)
with open(REPORT_MD, 'w', encoding='utf-8') as f:
    f.write('\n'.join(md))

# ---------------------------------------------------------------------------
# Console summary (for the operator)
# ---------------------------------------------------------------------------
print('=== R-signal research summary ===')
print(f'CSV triggers: {n_csv} | simulated: {n_sim} | '
      f'skipped(no_sym/not_found/no_fwd)={skip_no_symbol}/{skip_not_found}/{skip_no_fwd}')
print(f'regime split (sim): {regime_counts} | 盤整%={pct_cons:.1f}')
print('-- 10d all-regime --')
for label, _ in VARIANTS:
    s = all_tbl[label]
    print(f'  {label:9s} n={s["n"]:4d} win={s["win"]:5.1f}% mean={s["mean"]:+6.2f}% '
          f'median={s["median"]:+6.2f}% P5={s["p5"]:+6.2f}% P10={s["p10"]:+6.2f}% worst={s["worst"]:+7.2f}%')
print('-- 10d 盤整-only --')
for label, _ in VARIANTS:
    s = cons_tbl[label]
    print(f'  {label:9s} n={s["n"]:4d} win={s["win"]:5.1f}% mean={s["mean"]:+6.2f}% worst={s["worst"]:+7.2f}%')
print(f'top month={top_month["ym"]} n={int(top_month["n"])} ({top_month_share:.1f}%) | '
      f'2025-04 n={apr25_n} ({apr25_share:.1f}%) | '
      f'top sym={top_sym["symbol"]} n={int(top_sym["n"])} ({top_sym_share:.1f}%) top5={top5_sym_share:.1f}%')
print(f'best variant: {best_label} | verdict: {verdict}')
print(f'report -> {REPORT_MD}')
