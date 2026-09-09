"""
research_chip_strength.py — build_prompt_12 任務4：籌碼強度四因子探索性回測（report-only）

輸出 docs/superpowers/reports/chip_strength_report.md

紀律（沿用 build_prompt_10 反過擬合門檻）：
  採納候選 = 分位單調 + 時間雙半穩定（前後半段 Spearman ρ≥0.5）+ 樣本足夠。
  嚴禁以單格最高勝率下結論。本腳本**不修改任何評分邏輯**，只產報告。

效能：逐 (symbol,date) 呼叫 ChipDataManager 方法會做上萬次 DB 查詢，過慢。
      故以「每檔載入一次序列 → 記憶體內計算」的快路徑計算因子，
      並在報告中附上「與正式函式的一致性抽驗」證明兩者等價。

用法：python research_chip_strength.py [--symbols a,b,c] [--years 2] [--no-etl]
"""

from __future__ import annotations

import os
import sys
import json
import time
import sqlite3
import argparse
import datetime
import statistics

try:
    from scipy.stats import spearmanr
except Exception:
    spearmanr = None

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, 'watchlist_v4.db')
OUT_DIR = os.path.join(ROOT, 'docs', 'superpowers', 'reports')
OUT_MD = os.path.join(OUT_DIR, 'chip_strength_report.md')

HOLDS = (5, 10, 20)
MIN_CELL = 30          # 每格樣本門檻


# ── 資料載入 ──────────────────────────────────────────────────────────────
def load_symbols(arg_syms=None):
    if arg_syms:
        return [s.strip() for s in arg_syms.split(',') if s.strip()]
    conn = sqlite3.connect(DB)
    wl = [str(r[0]) for r in conn.execute("SELECT symbol FROM watchlist")]
    conn.close()
    th = set()
    try:
        with open(os.path.join(ROOT, 'theme_map.json'), encoding='utf-8') as f:
            th = {str(s) for v in json.load(f)['themes'].values() for s in v}
    except Exception:
        pass
    return sorted(set(wl) | th)


CLOSES_CACHE = os.path.join(ROOT, 'backtest_results', 'bp12_closes_cache.json')


def _save_closes(closes):
    try:
        os.makedirs(os.path.dirname(CLOSES_CACHE), exist_ok=True)
        with open(CLOSES_CACHE, 'w') as f:
            json.dump(closes, f)
        print(f"[ETL] 收盤價快取 → {CLOSES_CACHE}（{len(closes)} 檔）")
    except Exception as e:
        print(f"[ETL] 快取寫入略過: {e}")


def _load_closes():
    """--no-etl 用：讀回收盤價快取（遠期報酬需要完整價格序列，DB 只存淨買超日）。"""
    try:
        with open(CLOSES_CACHE) as f:
            c = json.load(f)
        print(f"[ETL] 讀取收盤價快取（{len(c)} 檔）")
        return c
    except Exception:
        print("[ETL] 無收盤價快取 → --no-etl 無法計算遠期報酬，請先跑一次含 ETL")
        return {}


def etl(symbols, years):
    """補 margin_daily 與收盤價（同一次 TaiwanStockPrice 呼叫兼供遠期報酬用）。
    回傳 {symbol: {date: close}}。"""
    from chip_data_manager import get_chip_manager, RATE_LIMITED
    import finmind_budget as fb
    mgr = get_chip_manager(DB)
    end = datetime.date.today()
    start = end - datetime.timedelta(days=int(365 * years) + 60)
    s_str, e_str = start.isoformat(), end.isoformat()

    closes = {}
    n_m = n_p = 0
    for i, sym in enumerate(symbols, 1):
        if fb.is_cooling():
            print(f"[ETL] FinMind 冷卻中，停止補資料（已完成 {i-1}/{len(symbols)}）")
            break
        # 融資
        got = mgr._fetch_finmind_margin(sym, s_str, e_str)
        if got and got != RATE_LIMITED:
            rows = [(sym, d, v['margin_balance'], v['margin_change'],
                     v['short_balance'], v['short_change'], 'finmind',
                     datetime.datetime.now().isoformat(timespec='seconds'))
                    for d, v in got.items()]
            conn = sqlite3.connect(DB)
            conn.executemany(
                "INSERT OR REPLACE INTO margin_daily (symbol,date,margin_balance,"
                "margin_change,short_balance,short_change,source,fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?)", rows)
            conn.commit(); conn.close()
            n_m += len(rows)
        # 收盤價
        px = mgr._fetch_finmind_close(sym, s_str, e_str)
        if px and px != RATE_LIMITED:
            closes[sym] = px
            n_p += len(px)
        if i % 20 == 0:
            print(f"[ETL] {i}/{len(symbols)}  margin={n_m} price={n_p}")
    print(f"[ETL] 完成：margin {n_m} 筆、price {n_p} 筆、{len(closes)} 檔有價")
    _save_closes(closes)
    return closes


def load_series(symbol):
    """回傳 (dates[], f[], t[], d[], margin{}, proxy{})，依日期升冪。"""
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT date, foreign_net, trust_net, dealer_net, foreign_buy_price_proxy "
        "FROM chip_daily WHERE symbol=? ORDER BY date", (symbol,)).fetchall()
    mrows = conn.execute(
        "SELECT date, margin_balance FROM margin_daily WHERE symbol=? "
        "AND margin_balance IS NOT NULL ORDER BY date", (symbol,)).fetchall()
    conn.close()
    dates = [r[0] for r in rows]
    return (dates, [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows],
            {d: b for d, b in mrows}, {r[0]: r[4] for r in rows if r[4] is not None})


# ── 因子（記憶體快路徑；與 chip_data_manager 同公式）────────────────────
def _z(today, hist):
    vals = [v for v in hist if v is not None]
    if today is None or len(vals) < 20:
        return None
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    sd = var ** 0.5
    return None if sd <= 0 else round((today - mean) / sd, 2)


def factors_at(i, dates, F, T, D, margin, proxy, closes, window=60):
    """計算第 i 日（as-of）的四因子。缺資料回 None，不以 0 充數。"""
    out = {}
    # 1) 強度 Z（合計淨額序列，分布不含今日）
    def s3(k):
        vs = [v for v in (F[k], T[k], D[k]) if v is not None]
        return sum(vs) if vs else None
    lo = max(0, i - window)
    out['combined_z'] = _z(s3(i), [s3(k) for k in range(lo, i)])
    out['foreign_z'] = _z(F[i], F[lo:i])

    # 2) 一致性（近 5 日三者同向比例）
    seg = range(max(0, i - 4), i + 1)
    same = checked = 0
    for k in seg:
        checked += 1
        f, t, d = F[k], T[k], D[k]
        if None in (f, t, d):
            continue
        if (f > 0 and t > 0 and d > 0) or (f < 0 and t < 0 and d < 0):
            same += 1
    out['consistency_ratio'] = round(same / checked, 3) if checked else None

    # 3) 融資背離（近 10 日）
    seg10 = [F[k] for k in range(max(0, i - 9), i + 1) if F[k] is not None]
    fnet10 = sum(seg10) if seg10 else None
    mdates = [dates[k] for k in range(max(0, i - 9), i + 1) if dates[k] in margin]
    if fnet10 is not None and len(mdates) >= 2:
        mchg = margin[mdates[-1]] - margin[mdates[0]]
        out['margin_change_10d'] = mchg
        if fnet10 > 0 and mchg < 0:
            out['divergence_type'] = '正向背離'
        elif fnet10 < 0 and mchg > 0:
            out['divergence_type'] = '負向背離'
        else:
            out['divergence_type'] = '無背離'
    else:
        out['margin_change_10d'] = None
        out['divergence_type'] = None

    # 4) 法人均價近似 vs 現價（近 5 日淨買超日加權；價用當日收盤）
    w = wp = 0
    for k in range(max(0, i - 4), i + 1):
        fk, dk = F[k], dates[k]
        px = proxy.get(dk) or (closes.get(dk) if closes else None)
        if fk is not None and fk > 0 and px:
            w += fk; wp += fk * px
    cur = closes.get(dates[i]) if closes else None
    if w > 0 and cur:
        avg = wp / w
        out['premium_pct'] = round((cur / avg - 1) * 100, 2)
    else:
        out['premium_pct'] = None
    return out


# ── 統計 ──────────────────────────────────────────────────────────────────
def quintile_table(rows, key, N):
    pairs = [(r[key], r[f'ret_{N}']) for r in rows
             if r.get(key) is not None and r.get(f'ret_{N}') is not None]
    if len(pairs) < 5 * MIN_CELL:
        return None
    xs = sorted(p[0] for p in pairs)
    n = len(xs)
    edges = [xs[int(n * p / 5)] for p in (1, 2, 3, 4)]
    bins = [[] for _ in range(5)]
    for v, ret in pairs:
        b = 0
        while b < 4 and v > edges[b]:
            b += 1
        bins[b].append(ret)
    stats = []
    for b in bins:
        if not b:
            stats.append(None); continue
        stats.append({'n': len(b), 'mean': round(statistics.mean(b), 3),
                      'win': round(sum(1 for x in b if x > 0) / len(b) * 100, 1)})
    return stats, edges


def monotonic_flag(means):
    m = [x for x in means if x is not None]
    if len(m) < 3:
        return '樣本不足'
    if all(m[k] <= m[k + 1] for k in range(len(m) - 1)) or \
       all(m[k] >= m[k + 1] for k in range(len(m) - 1)):
        return '✅單調'
    mid = statistics.median(m[1:-1]) if len(m) > 2 else m[0]
    spread = (max(m[1:-1]) - min(m[1:-1])) if len(m) > 2 else 0
    if abs(m[0] - mid) > 2 * max(0.5, spread) or abs(m[-1] - mid) > 2 * max(0.5, spread):
        return '⚠️閾值型'
    return '🔴雜訊'


def stability_rho(rows, key, N):
    """時間對半切：前後半段五分位平均報酬的 Spearman（ρ≥0.5 才算穩定）。"""
    if spearmanr is None:
        return None
    dated = sorted([r for r in rows if r.get(key) is not None and r.get(f'ret_{N}') is not None],
                   key=lambda r: r['date'])
    if len(dated) < 400:
        return None
    mid = len(dated) // 2
    a, b = quintile_table(dated[:mid], key, N), quintile_table(dated[mid:], key, N)
    if not a or not b:
        return None
    m1 = [s['mean'] if s else None for s in a[0]]
    m2 = [s['mean'] if s else None for s in b[0]]
    if any(x is None for x in m1 + m2):
        return None
    try:
        rho, _ = spearmanr(m1, m2)
        return round(float(rho), 2) if rho == rho else None
    except Exception:
        return None


def verdict_for(flag, rho, diff):
    """結論標記：有鑑別度 / 維持顯示層。"""
    if flag == '✅單調' and rho is not None and rho >= 0.5 and abs(diff) >= 1.0:
        return '**有鑑別度，值得考慮進權重**'
    reasons = []
    if flag != '✅單調':
        reasons.append(f'非單調（{flag}）')
    if rho is None:
        reasons.append('穩定性不可得')
    elif rho < 0.5:
        reasons.append(f'雙半不穩定 ρ={rho}')
    if abs(diff) < 1.0:
        reasons.append(f'分位差僅 {diff}')
    return f'無顯著鑑別度，**維持顯示層**（{"；".join(reasons)}）'


# ── 主流程 ────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbols', default='')
    ap.add_argument('--years', type=float, default=2.0)
    ap.add_argument('--no-etl', action='store_true')
    args = ap.parse_args()

    symbols = load_symbols(args.symbols or None)
    print(f"[Research] 標的 {len(symbols)} 檔，回溯 {args.years} 年")

    closes_map = {}
    if not args.no_etl:
        closes_map = etl(symbols, args.years)
    else:
        print("[Research] --no-etl：用現有 DB + 收盤價快取")
        closes_map = _load_closes()

    cutoff = (datetime.date.today() - datetime.timedelta(days=int(365 * args.years))).isoformat()
    rows = []
    for sym in symbols:
        dates, F, T, D, margin, proxy = load_series(sym)
        if len(dates) < 90:
            continue
        closes = closes_map.get(sym, {})
        maxN = max(HOLDS)
        for i in range(60, len(dates) - maxN):
            if dates[i] < cutoff:
                continue
            fac = factors_at(i, dates, F, T, D, margin, proxy, closes)
            if all(fac.get(k) is None for k in
                   ('combined_z', 'consistency_ratio', 'divergence_type', 'premium_pct')):
                continue
            rec = {'symbol': sym, 'date': dates[i], **fac}
            c0 = closes.get(dates[i])
            ok = False
            for N in HOLDS:
                cN = closes.get(dates[i + N]) if i + N < len(dates) else None
                rec[f'ret_{N}'] = (round((cN / c0 - 1) * 100, 3)
                                   if (c0 and cN and c0 > 0) else None)
                ok = ok or rec[f'ret_{N}'] is not None
            if ok:
                rows.append(rec)
        if len(rows) and len(rows) % 5000 < 50:
            print(f"[Research] 已累積 {len(rows)} 筆…")

    print(f"[Research] 樣本 {len(rows)} 筆")
    if not rows:
        print("[Research] 無樣本，中止"); return

    # 抽驗：快路徑 vs 正式函式一致性
    agree = check_agreement(rows)

    write_report(rows, agree, args)


def check_agreement(rows, k=8):
    """抽驗快路徑因子 == chip_data_manager 正式函式（證明兩者等價）。"""
    import random
    from chip_data_manager import get_chip_manager
    mgr = get_chip_manager(DB)
    random.seed(42)
    sample = random.sample(rows, min(k, len(rows)))
    ok = tot = 0
    detail = []
    for r in sample:
        tot += 1
        st = mgr.get_chip_strength(r['symbol'], as_of=r['date'])
        cs = mgr.get_institutional_consistency(r['symbol'], as_of=r['date'])
        a = st.get('combined_z') if st.get('available') else None
        b = cs.get('consistency_ratio') if cs.get('available') else None
        match = (a == r.get('combined_z')) and (b == r.get('consistency_ratio'))
        ok += 1 if match else 0
        detail.append((r['symbol'], r['date'], r.get('combined_z'), a,
                       r.get('consistency_ratio'), b, match))
    print(f"[抽驗] 快路徑與正式函式一致 {ok}/{tot}")
    return {'ok': ok, 'total': tot, 'detail': detail}


def write_report(rows, agree, args):
    os.makedirs(OUT_DIR, exist_ok=True)
    md = ["# 籌碼強度四因子探索性回測（build_prompt_12 任務4）\n"]
    md.append("> **方法論**：採納門檻＝**分位單調 + 時間雙半穩定（ρ≥0.5）+ 分位差≥1.0**，")
    md.append("> 每格 n≥30。嚴禁以單格最高報酬下結論（多重比較陷阱）。")
    md.append("> 本報告**不修改任何評分邏輯**，結論供人工決策。\n")
    md.append(f"- 樣本：**{len(rows)}** 筆（{len({r['symbol'] for r in rows})} 檔，"
              f"回溯 {args.years} 年）｜報酬為毛報酬（未計成本），持有 {list(HOLDS)} 日\n")
    md.append(f"- 快路徑一致性抽驗：**{agree['ok']}/{agree['total']}** 與 "
              f"`chip_data_manager` 正式函式完全相同\n")
    md.append("- ⚠️ 法人均價 premium_pct 使用**當日收盤價近似**，非真實逐筆成交均價\n")

    ranking = []

    # 1) 連續因子五分位
    md.append("\n## 1. 單因子五分位（連續型）\n")
    for key, label in [('combined_z', '法人買賣強度 Z（三大法人合計）'),
                       ('consistency_ratio', '三大法人一致性比例'),
                       ('premium_pct', '法人均價溢價 %（現價 vs 近似成本）'),
                       ('margin_change_10d', '融資餘額 10 日變化（張）')]:
        md.append(f"### {label} — `{key}`\n")
        base = quintile_table(rows, key, 10)
        if not base:
            md.append("樣本不足（每格需 n≥30），略過。\n"); continue
        stats, edges = base
        md.append("| 分位 | n | 5日 | 10日 | 20日 | 10日勝率 |")
        md.append("|---|---|---|---|---|---|")
        per_hold = {N: quintile_table(rows, key, N) for N in HOLDS}
        for qi in range(5):
            cells = []
            for N in HOLDS:
                t = per_hold[N]
                s = t[0][qi] if t else None
                cells.append(f"{s['mean']:+.2f}%" if s else '—')
            s10 = stats[qi]
            md.append(f"| Q{qi+1} | {s10['n'] if s10 else 0} | {cells[0]} | {cells[1]} | "
                      f"{cells[2]} | {s10['win'] if s10 else '—'}% |")
        means = [s['mean'] if s else None for s in stats]
        flag = monotonic_flag(means)
        rho = stability_rho(rows, key, 10)
        diff = round((means[-1] or 0) - (means[0] or 0), 3)
        md.append(f"\n- 分位邊界：{', '.join(f'{e:.2f}' for e in edges)}")
        md.append(f"- 10日分位差（Q5−Q1）：**{diff}**｜單調性：{flag}｜"
                  f"雙半穩定 ρ={rho if rho is not None else '—'}")
        md.append(f"- **結論**：{verdict_for(flag, rho, diff)}\n")
        ranking.append((label, diff, flag, rho))

    # 2) 融資背離分組 + 正向背離 vs 全樣本
    md.append("\n## 2. 融資背離分組 vs 全樣本基準\n")
    groups = {}
    for r in rows:
        dt = r.get('divergence_type')
        if dt:
            groups.setdefault(dt, []).append(r)
    md.append("| 分組 | n | 5日 | 10日 | 20日 | 10日勝率 |")
    md.append("|---|---|---|---|---|---|")

    def _mean(rs, N):
        v = [r[f'ret_{N}'] for r in rs if r.get(f'ret_{N}') is not None]
        return (round(statistics.mean(v), 3), len(v)) if v else (None, 0)

    base_line = {}
    for N in HOLDS:
        base_line[N] = _mean(rows, N)[0]
    for g in ('正向背離', '無背離', '負向背離'):
        rs = groups.get(g)
        if not rs:
            md.append(f"| {g} | 0 | — | — | — | — |"); continue
        m = [_mean(rs, N)[0] for N in HOLDS]
        v10 = [r['ret_10'] for r in rs if r.get('ret_10') is not None]
        win = round(sum(1 for x in v10 if x > 0) / len(v10) * 100, 1) if v10 else '—'
        md.append(f"| {g} | {len(rs)} | " +
                  " | ".join(f"{x:+.2f}%" if x is not None else '—' for x in m) +
                  f" | {win}% |")
    md.append(f"| **全樣本基準** | {len(rows)} | " +
              " | ".join(f"{base_line[N]:+.2f}%" if base_line[N] is not None else '—'
                         for N in HOLDS) + " | — |")
    pos = groups.get('正向背離') or []
    neg = groups.get('負向背離') or []
    p10, pn = _mean(pos, 10)
    n10, nn = _mean(neg, 10)
    md.append("")
    if p10 is not None and base_line[10] is not None and pn >= MIN_CELL:
        edge = round(p10 - base_line[10], 3)
        ok = edge >= 0.5 and (n10 is None or p10 > n10)
        md.append(f"- 正向背離 10日 {p10:+.2f}%（n={pn}）vs 全樣本 {base_line[10]:+.2f}%"
                  f" → 超額 **{edge:+.3f}pp**"
                  f"；負向背離 {n10:+.2f}%（n={nn}）" if n10 is not None else "")
        md.append(f"- **結論**：{'**有鑑別度，值得考慮進權重**' if ok else '差距不足，**維持顯示層**'}")
    else:
        md.append(f"- **結論**：正向背離樣本 {pn}（需 ≥{MIN_CELL}）→ **維持顯示層／需更多樣本**")

    # 3) premium_pct 分桶（套牢 vs 獲利）
    md.append("\n## 3. 法人均價溢價分桶（套牢區 vs 已獲利區）\n")
    buckets = [('法人套牢 (<-5%)', lambda v: v < -5),
               ('小幅套牢 (-5~0%)', lambda v: -5 <= v < 0),
               ('小幅獲利 (0~5%)', lambda v: 0 <= v < 5),
               ('明顯獲利 (>5%)', lambda v: v >= 5)]
    md.append("| 分桶 | n | 5日 | 10日 | 20日 | 10日勝率 |")
    md.append("|---|---|---|---|---|---|")
    bstats = []
    for lab, cond in buckets:
        rs = [r for r in rows if r.get('premium_pct') is not None and cond(r['premium_pct'])]
        if not rs:
            md.append(f"| {lab} | 0 | — | — | — | — |"); continue
        m = [_mean(rs, N)[0] for N in HOLDS]
        v10 = [r['ret_10'] for r in rs if r.get('ret_10') is not None]
        win = round(sum(1 for x in v10 if x > 0) / len(v10) * 100, 1) if v10 else '—'
        md.append(f"| {lab} | {len(rs)} | " +
                  " | ".join(f"{x:+.2f}%" if x is not None else '—' for x in m) + f" | {win}% |")
        bstats.append((lab, m[1], len(rs)))
    if len(bstats) >= 2:
        vals = [b[1] for b in bstats if b[1] is not None]
        spread = round(max(vals) - min(vals), 3)
        # 單調性檢查：桶序是由「套牢」到「獲利」，若非單調（例如 U 型兩端皆高），
        # 代表「溢價越高越好」的線性讀法是錯的 —— 不可直接進線性權重。
        mono = (all(vals[k] <= vals[k + 1] for k in range(len(vals) - 1)) or
                all(vals[k] >= vals[k + 1] for k in range(len(vals) - 1)))
        md.append(f"\n- 桶間 10 日最大差距：**{spread}pp**｜單調性："
                  f"{'✅單調' if mono else '🔴非單調（U 型：兩端皆優於中段）'}")
        if spread >= 1.0 and mono:
            concl = "**有鑑別度，值得考慮進權重**"
        elif spread >= 1.0 and not mono:
            concl = ("差距雖大但**非單調**，線性權重會誤導 → **維持顯示層**"
                     "（可考慮改為『極端值旗標』而非連續權重，需另行驗證）")
        else:
            concl = "差距不足，**維持顯示層**"
        md.append(f"- **結論**：{concl}")
        md.append("- 註：溢價以收盤價近似成本計算，本身含近似誤差；"
                  "且分桶樣本不均（極端桶 n 明顯偏少），解讀需保守。")

    # 4) 總結
    md.append("\n## 4. 總結：四因子採納建議\n")
    md.append("| 因子 | 10日分位差 | 單調性 | 穩定ρ | 建議 |")
    md.append("|---|---|---|---|---|")
    for label, diff, flag, rho in ranking:
        rec = ('進權重候選' if (flag == '✅單調' and rho is not None and rho >= 0.5
                              and abs(diff) >= 1.0) else '維持顯示層')
        md.append(f"| {label} | {diff} | {flag} | {rho if rho is not None else '—'} | {rec} |")
    md.append("\n> 依 build_prompt_12 規定，本輪**不自動修改任何評分邏輯**；"
              "上述建議供人工決定是否進入下一輪 fix prompt。")

    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Research] 報告 → {OUT_MD}")


if __name__ == '__main__':
    main()
