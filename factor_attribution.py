"""
factor_attribution.py — 因子歸因分析（build_prompt_10 任務2）

讀 signal_backtest 產出的 trades.csv，輸出 factor_report.md：
  單因子分箱（quintile）→ 勝率/報酬/n、單調性標記、≤10 組雙因子交互、時間雙半 Spearman 穩定性、
  因子排行榜 + 權重調整候選清單（只列建議與依據，不自動改任何權重）。

方法論鐵律（多重比較陷阱）：對數十個指標組合暴力搜尋，最高勝率那格極可能是雜訊
（本專案實例：頭肩底 n=15 勝率 80%，另兩輪掉到 48%/36%）。採納門檻＝
「分位單調性 + 時間雙半穩定」，嚴禁以單格最高勝率為調整依據。

用法：python factor_attribution.py --trades backtest_results/xxx/trades.csv
向後相容：舊 csv 缺因子欄 → 該因子優雅跳過（不報錯）。
"""

import os
import csv
import argparse
import statistics

import numpy as np
try:
    from scipy.stats import spearmanr
except Exception:
    spearmanr = None

# 連續型因子（quintile 分箱）
CONT = ['rsi', 'kd_k', 'kd_d', 'macd_dif', 'macd_hist', 'bias_5', 'bias_20', 'bias_60',
        'adx', 'atr_pct', 'vol_ratio', 'pth_52w', 'rs_score', 'theme_score', 'rev_yoy']
# 類別型因子（直接分組）
CAT = ['kd_state', 'macd_state', 'macd_div', 'pv_state', 'bb_squeeze', 'ma_bull',
       'above_ma20', 'above_ma60', 'rev_mom', 'short_advice', 'mid_advice', 'long_advice']

MIN_N = 30   # 每格樣本門檻


def _fnum(x):
    try:
        if x is None or x == '':
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _load(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def _binstats(nets):
    if not nets:
        return None
    return {'n': len(nets),
            'win': round(sum(1 for x in nets if x > 0) / len(nets) * 100, 1),
            'mean': round(statistics.mean(nets), 3)}


def _quintile(rows, factor, N):
    """連續因子五分位 → (list[5] of net-lists, edges) 或 None。"""
    pairs = [(_fnum(r.get(factor)), _fnum(r.get(f'ret_{N}_net'))) for r in rows]
    pairs = [(v, ret) for v, ret in pairs if v is not None and ret is not None]
    if len(pairs) < 50:
        return None
    xs = [v for v, _ in pairs]
    edges = [float(np.percentile(xs, p)) for p in (20, 40, 60, 80)]
    bins = [[] for _ in range(5)]
    for v, ret in pairs:
        b = 0
        while b < 4 and v > edges[b]:
            b += 1
        bins[b].append(ret)
    return bins, edges


def _monotonic_flag(means):
    """✅單調 / ⚠️閾值型 / 🔴雜訊。"""
    m = [x for x in means if x is not None]
    if len(m) < 3:
        return '樣本不足'
    up = all(m[i] <= m[i + 1] for i in range(len(m) - 1))
    down = all(m[i] >= m[i + 1] for i in range(len(m) - 1))
    if up or down:
        return '✅單調'
    # 閾值型：僅頭或尾一格明顯偏離、其餘接近
    mid = statistics.median(m[1:-1]) if len(m) > 2 else m[0]
    spread_mid = (max(m[1:-1]) - min(m[1:-1])) if len(m) > 2 else 0
    if abs(m[0] - mid) > 2 * max(0.5, spread_mid) or abs(m[-1] - mid) > 2 * max(0.5, spread_mid):
        return '⚠️閾值型'
    return '🔴雜訊'


def _stability_rho(rows, factor, N):
    """時間對半切，前後半段五分位平均報酬的 Spearman。|ρ|<0.5 → 疑似過擬合。"""
    if spearmanr is None:
        return None
    dated = sorted([r for r in rows if r.get('as_of')], key=lambda r: r['as_of'])
    if len(dated) < 100:
        return None
    mid = len(dated) // 2
    h1, h2 = dated[:mid], dated[mid:]
    q1 = _quintile(h1, factor, N)
    q2 = _quintile(h2, factor, N)
    if not q1 or not q2:
        return None
    m1 = [(_binstats(b) or {}).get('mean') for b in q1[0]]
    m2 = [(_binstats(b) or {}).get('mean') for b in q2[0]]
    if any(x is None for x in m1 + m2):
        return None
    try:
        rho, _ = spearmanr(m1, m2)
        return round(float(rho), 2) if rho == rho else None
    except Exception:
        return None


def _cat_groups(rows, factor, N):
    """類別因子分組 → {value: net-list}。"""
    out = {}
    for r in rows:
        v = r.get(factor)
        ret = _fnum(r.get(f'ret_{N}_net'))
        if v in (None, '') or ret is None:
            continue
        out.setdefault(str(v), []).append(ret)
    return out


def analyze(trades_path, out_dir=None):
    rows = _load(trades_path)
    out_dir = out_dir or os.path.dirname(trades_path)
    cols = set(rows[0].keys()) if rows else set()
    Nref = 10 if any('ret_10_net' in r for r in rows[:1]) else None
    holds = sorted({int(c.split('_')[1]) for c in cols if c.startswith('ret_') and c.endswith('_net')})
    Nref = 10 if 10 in holds else (holds[0] if holds else 10)

    md = ["# 因子歸因分析報告\n"]
    md.append("> **方法論鐵律（多重比較陷阱）**：對數十個指標組合暴力搜尋，最高勝率那格極可能是雜訊")
    md.append("> （實例：頭肩底 n=15 勝率 80%，另兩輪掉到 48%/36%）。採納門檻＝**分位單調性 + 時間雙半穩定**，")
    md.append("> **嚴禁以單格最高勝率為調整依據**。每格 n≥30 才列正文，n<30 進灰字附錄。\n")
    md.append(f"- 樣本：{len(rows)} 筆訊號｜主要持有期：{Nref} 日｜持有期：{holds}\n")

    ranking = []   # (factor, 10日分位差, flag, rho, kind)
    low_n = []     # n<30 附錄

    # ── 單因子：連續型 quintile ──
    md.append("## 單因子分箱（連續型五分位）\n")
    for fac in CONT:
        if fac not in cols:
            continue
        q = _quintile(rows, fac, Nref)
        if not q:
            continue
        bins, edges = q
        stats5 = [_binstats(b) for b in bins]
        if any(s is None for s in stats5):
            continue
        means = [s['mean'] for s in stats5]
        flag = _monotonic_flag(means)
        rho = _stability_rho(rows, fac, Nref)
        diff = round(means[-1] - means[0], 3)
        enough = all(s['n'] >= MIN_N for s in stats5)
        edge_txt = "、".join(f"{e:.1f}" for e in edges)
        md.append(f"### {fac}　（分位邊界 {edge_txt}）　{flag}"
                  f"{'　穩定性ρ='+str(rho) if rho is not None else ''}")
        md.append("| 分位 | n | 勝率 | 平均淨報酬 |")
        md.append("|---|---|---|---|")
        for qi, s in enumerate(stats5):
            md.append(f"| Q{qi+1} | {s['n']} | {s['win']}% | {s['mean']} |")
        # 穩定＝ρ≥0.5（正相關，前後半段同向）；ρ<0.5（含負值＝效果反轉）皆視為不穩定
        _unstable = (rho is None) or (rho < 0.5)
        md.append(f"- 10日分位差（Q5−Q1）：**{diff}**"
                  + ("　🔴 疑似過擬合（ρ<0.5，前後半段不穩/反轉）" if _unstable else "")
                  + ("" if enough else "　（部分格 n<30，僅參考）") + "\n")
        if enough:
            ranking.append((fac, diff, flag, rho, 'cont'))
        else:
            low_n.append((fac, diff, flag, min(s['n'] for s in stats5)))

    # ── 單因子：類別型分組 ──
    md.append("## 單因子分組（類別型）\n")
    for fac in CAT:
        if fac not in cols:
            continue
        groups = _cat_groups(rows, fac, Nref)
        if not groups:
            continue
        md.append(f"### {fac}")
        md.append("| 分組 | n | 勝率 | 平均淨報酬 |")
        md.append("|---|---|---|---|")
        gmeans = {}
        for val, nets in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            s = _binstats(nets)
            tag = "" if s['n'] >= MIN_N else "（n<30）"
            md.append(f"| {val}{tag} | {s['n']} | {s['win']}% | {s['mean']} |")
            if s['n'] >= MIN_N:
                gmeans[val] = s['mean']
        if len(gmeans) >= 2:
            diff = round(max(gmeans.values()) - min(gmeans.values()), 3)
            ranking.append((fac, diff, '（類別）', None, 'cat'))
            md.append(f"- 最大組間差：**{diff}**\n")
        else:
            md.append("")

    # ── 因子排行榜（依 10 日分位差絕對值）──
    md.append("## 因子排行榜（依 10 日分位差；n≥30）\n")
    ranking.sort(key=lambda x: -abs(x[1]))
    md.append("| 排名 | 因子 | 10日分位差 | 單調性 | 穩定ρ |")
    md.append("|---|---|---|---|---|")
    for i, (fac, diff, flag, rho, kind) in enumerate(ranking, 1):
        md.append(f"| {i} | {fac} | {diff} | {flag} | {rho if rho is not None else '—'} |")

    # ── 雙因子交互：只取單因子 10 日分位差前 5 名兩兩組合（≤10 組）──
    md.append("\n## 雙因子交互（僅前 5 名兩兩組合，≤10 組；嚴禁全排列暴搜）\n")
    top5 = [r for r in ranking if r[4] == 'cont'][:5]
    import itertools
    pair_count = 0
    for (fa, _, _, _, _), (fb, _, _, _, _) in itertools.combinations(top5, 2):
        if pair_count >= 10:
            break
        pair_count += 1
        qa = _quintile(rows, fa, Nref)
        qb = _quintile(rows, fb, Nref)
        if not qa or not qb:
            continue
        ea, eb = qa[1], qb[1]

        def _b(v, edges):
            b = 0
            while b < 4 and v > edges[b]:
                b += 1
            return b
        # 2×2（低/高 × 低/高，用中位邊界 edges[1]/edges[2] 之間的簡化）
        cells = {}
        for r in rows:
            va, vb = _fnum(r.get(fa)), _fnum(r.get(fb))
            ret = _fnum(r.get(f'ret_{Nref}_net'))
            if va is None or vb is None or ret is None:
                continue
            la = '高' if va > ea[1] else '低'   # 以 40 百分位為界
            lb = '高' if vb > eb[1] else '低'
            cells.setdefault((la, lb), []).append(ret)
        md.append(f"### {fa} × {fb}（{Nref}日平均淨報酬）")
        md.append(f"| {fa}＼{fb} | 低 | 高 |")
        md.append("|---|---|---|")
        for la in ('低', '高'):
            cvals = []
            for lb in ('低', '高'):
                nets = cells.get((la, lb), [])
                if len(nets) >= MIN_N:
                    cvals.append(f"{statistics.mean(nets):.2f}%(n={len(nets)})")
                else:
                    cvals.append(f"—(n={len(nets)})")
            md.append(f"| {la} | {cvals[0]} | {cvals[1]} |")
        md.append("")

    # ── 權重調整候選清單 ──
    md.append("## 權重調整候選清單（只列建議與依據，不自動改權重）\n")
    # 候選門檻：單調 + 正向雙半穩定（ρ≥0.5，負 ρ＝效果反轉不採納）+ 分位差≥1.0
    cands = [r for r in ranking if r[2] == '✅單調' and (r[3] is not None and r[3] >= 0.5)
             and abs(r[1]) >= 1.0]
    if cands:
        for fac, diff, flag, rho, kind in cands[:8]:
            md.append(f"- **{fac}**：10日分位差 {diff}、{flag}、穩定ρ={rho if rho is not None else 'n/a'}"
                      f" → 建議納入權重評估（單調且雙半穩定）。")
    else:
        md.append("- （無因子同時滿足「單調 + 正向穩定 ρ≥0.5 + 分位差≥1.0」；本輪不建議調整任何權重）")
    md.append("\n> 採納流程見 README「權重調整循環規範」：一次只改一組 → 重跑 walk-forward → 期望值矩陣對比。")

    # ── 灰字附錄：n<30 ──
    if low_n:
        md.append("\n## 附錄：樣本不足（n<30，僅參考勿採納）\n")
        md.append("| 因子 | 10日分位差 | 單調性 | 最小格 n |")
        md.append("|---|---|---|---|")
        for fac, diff, flag, mn in low_n:
            md.append(f"| {fac} | {diff} | {flag} | {mn} |")

    # 建議代碼 enum 對照
    md.append("\n## 附錄：建議代碼對照\n")
    md.append("- 短線 short_advice：S1 積極進場 / S2 分批佈局 / S3 續抱 / S4 等拉回 / S5 不參與 / S6 出場 / S7 停利")
    md.append("- 中線 mid_advice：M1 偏多持有 / M2 中線觀望 / M3 偏多等位置 / M4 偏空出場")
    md.append("- 長線 long_advice：L1 中長多 / L2 中長中立 / L3 中長空（回測無基本面，以 action_code 代理）")

    path = os.path.join(out_dir, 'factor_report.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[factor_attribution] {len(rows)} 筆 → {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description="因子歸因分析（讀 trades.csv）")
    ap.add_argument('--trades', required=True, help='trades.csv 路徑')
    ap.add_argument('--out', default='', help='輸出目錄（預設同 trades.csv）')
    args = ap.parse_args()
    analyze(args.trades, args.out or None)


if __name__ == '__main__':
    main()
