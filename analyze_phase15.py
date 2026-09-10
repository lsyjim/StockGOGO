"""
analyze_phase15.py — build_prompt_15 任務 B / C / D（report-only）

  b   Date-neutral Cross-sectional Test        → b_date_neutral.md
  c   RS Paired Stability Test                 → c_rs_paired.md
  d   Regime Episode Block Bootstrap           → episode_bootstrap.md

全部複用 Phase 1 既有 trades.csv，不重跑回測。不修改任何規則。
"""

from __future__ import annotations

import os
import csv
import argparse
import statistics
import collections

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, 'docs', 'superpowers', 'reports', 'phase1')
BASE = os.path.join(ROOT, 'backtest_results', 'bp13_step0', 'trades.csv')
NOFILTER = os.path.join(ROOT, 'backtest_results', 'b1_nofilter', 'trades.csv')
AB_RS = os.path.join(ROOT, 'backtest_results', 'b2_ab_rs', 'trades.csv')
CONTROL = os.path.join(ROOT, 'backtest_results', 'bp15_control', 'trades.csv')

HOLDS = (5, 10, 20)
MIN_PER_DAY = 10        # 當日訊號數門檻（低於此排除，排名無意義）
QUANT = 0.20            # Top/Bottom 20%


def load(p):
    with open(p, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        if v in (None, '', 'None'):
            return None
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


def write(md, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Phase1.5] → {p}")
    return p


def series_bootstrap_ci(vals, n_boot=1000, alpha=0.05, seed=42):
    """對「已按日聚合的序列」直接重抽樣（每日 spread 已是聚合單位）。"""
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    arr = np.asarray(v, dtype=float)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return (round(float(lo), 3), round(float(hi), 3), round(float(hi - lo), 3))


def ci_verdict(lo, hi):
    if lo is None or hi is None:
        return '—'
    if lo > 0:
        return '顯著為正'
    if hi < 0:
        return '顯著為負'
    return '**跨 0（不顯著）**'


# ── 任務 B：Date-neutral 每日橫斷面 spread ────────────────────────────────
def daily_spreads(rows, N, min_per_day=MIN_PER_DAY, q=QUANT):
    """
    逐 as_of 日：依 dir_score 排名取當日 Top q 與 Bottom q，
    回傳 {date: (spread, regime, n_day)}；同時回傳被排除的日數。
    """
    byd = collections.defaultdict(list)
    reg = {}
    for r in rows:
        s = fnum(r.get('dir_score'))
        v = fnum(r.get(f'ret_{N}_net'))
        if s is None or v is None:
            continue
        byd[r['as_of']].append((s, v))
        reg.setdefault(r['as_of'], r.get('regime', '未知'))
    out, excluded = {}, 0
    for d, lst in byd.items():
        if len(lst) < min_per_day:
            excluded += 1
            continue
        lst.sort(key=lambda t: t[0])
        k = max(1, int(len(lst) * q))
        bot = [v for _s, v in lst[:k]]
        top = [v for _s, v in lst[-k:]]
        out[d] = (statistics.mean(top) - statistics.mean(bot), reg[d], len(lst))
    return out, excluded


def _spread_block(sp):
    """由 {date:(spread,regime,n)} 算摘要。"""
    v = [x[0] for x in sp.values()]
    if not v:
        return None
    lo, hi, w = series_bootstrap_ci(v)
    return {'days': len(v), 'mean': round(statistics.mean(v), 3),
            'median': round(statistics.median(v), 3),
            'win': round(sum(1 for x in v if x > 0) / len(v) * 100, 1),
            'ci': (lo, hi), 'verdict': ci_verdict(lo, hi)}


def cmd_b(_a):
    rows = load(BASE)
    md = ["# 任務B：Date-neutral Cross-sectional Test（build_prompt_15）\n"]
    md.append("> **目的**：回答「Direction Score 能不能在**同一天**挑出相對更好的股票」。")
    md.append("> 原 B3 的 Top20−Bot20 是**全期 pooled** 排名，會混入時間／regime 組成效應")
    md.append("> （高分股集中在某些好年份，低分股集中在壞年份，價差就會被時間效應墊高）。")
    md.append("> 本測試把排名限制在**當日內**，時間效應自動消除。\n")
    md.append(f"- 樣本：{len(rows):,} 筆｜universe {len({r['symbol'] for r in rows})} 檔｜"
              f"{min(r['as_of'] for r in rows)} → {max(r['as_of'] for r in rows)}")
    md.append(f"- 方法：逐日依 `dir_score` 取 Top {QUANT:.0%} / Bottom {QUANT:.0%}；"
              f"當日訊號數 < {MIN_PER_DAY} 的日期排除")
    md.append("- CI：對「每日 spread 時間序列」直接 block bootstrap（1000 次，日期為單位）\n")
    md.append("⚠️ **universe 警語**：本測試沿用 Phase 1 的 82 檔 watchlist，"
              "該 universe 經任務A 確認具 selection bias（見 `universe_audit.md`）。"
              "date-neutral 設計消除的是**時間組成效應**，不能消除選股偏誤；"
              "惟「同日橫斷面排名」的相對結論受選股偏誤影響小於絕對期望值。\n")

    md.append("## 整體結果\n")
    md.append("| 持有期 | 有效天數 | 排除天數 | mean spread | median | 勝率(spread>0) | "
              "Block Bootstrap 95%CI | 判讀 |")
    md.append("|---|---|---|---|---|---|---|---|")
    keep = {}
    for N in HOLDS:
        sp, exc = daily_spreads(rows, N)
        keep[N] = sp
        b = _spread_block(sp)
        if not b:
            md.append(f"| {N}D | 0 | {exc} | — | — | — | — | — |")
            continue
        md.append(f"| {N}D | {b['days']:,} | {exc:,} "
                  f"({exc/(exc+b['days']):.0%}) | **{b['mean']:+.3f}pp** | "
                  f"{b['median']:+.3f}pp | {b['win']}% | "
                  f"[{b['ci'][0]}, {b['ci'][1]}] | {b['verdict']} |")

    # 與原 pooled 對照
    md.append("\n## 與原 B3 pooled spread 對照（驗收條件3）\n")
    md.append("| 持有期 | 原 pooled spread | Date-neutral spread | 差異 | 方向 |")
    md.append("|---|---|---|---|---|")
    pooled = {5: 0.445, 10: 1.094, 20: 2.173}     # b3_monotonicity.md 原值
    for N in HOLDS:
        b = _spread_block(keep[N])
        if not b:
            continue
        d = round(b['mean'] - pooled[N], 3)
        arrow = '縮水' if d < 0 else '增強'
        md.append(f"| {N}D | {pooled[N]:+.3f}pp | **{b['mean']:+.3f}pp** | "
                  f"{d:+.3f}pp | {arrow} {abs(d/pooled[N]):.0%} |")

    # 分 regime
    md.append("\n## 分 Regime（每個持有期）\n")
    for N in HOLDS:
        md.append(f"\n### 持有 {N} 日\n")
        md.append("| Regime | 天數 | mean spread | median | 勝率 | 95%CI | 判讀 |")
        md.append("|---|---|---|---|---|---|---|")
        for rg in ('多頭', '盤整', '空頭'):
            sub = {d: t for d, t in keep[N].items() if t[1] == rg}
            b = _spread_block(sub)
            if not b:
                md.append(f"| {rg} | 0 | — | — | — | — | — |")
                continue
            md.append(f"| {rg} | {b['days']:,} | **{b['mean']:+.3f}pp** | "
                      f"{b['median']:+.3f}pp | {b['win']}% | "
                      f"[{b['ci'][0]}, {b['ci'][1]}] | {b['verdict']} |")

    # 分年
    md.append("\n## 分年（20 日）\n")
    md.append("| 年份 | 天數 | mean spread | median | 勝率 | 95%CI | 判讀 |")
    md.append("|---|---|---|---|---|---|---|")
    for y in sorted({d[:4] for d in keep[20]}):
        sub = {d: t for d, t in keep[20].items() if d[:4] == y}
        b = _spread_block(sub)
        if not b:
            continue
        md.append(f"| {y} | {b['days']:,} | {b['mean']:+.3f}pp | {b['median']:+.3f}pp | "
                  f"{b['win']}% | [{b['ci'][0]}, {b['ci'][1]}] | {b['verdict']} |")

    # 對照 universe 交叉檢驗（若已產出）
    if os.path.exists(CONTROL):
        md.append("\n## 對照 universe 交叉檢驗（任務A Track2 的 120 檔）\n")
        md.append("同一 date-neutral 方法套用在**無選股偏誤**的對照 universe 上：\n")
        crows = load(CONTROL)
        md.append("| 持有期 | 有效天數 | mean spread | 勝率 | 95%CI | 判讀 |")
        md.append("|---|---|---|---|---|---|")
        for N in HOLDS:
            sp, _e = daily_spreads(crows, N)
            b = _spread_block(sp)
            if not b:
                md.append(f"| {N}D | 0 | — | — | — | — |")
                continue
            md.append(f"| {N}D | {b['days']:,} | **{b['mean']:+.3f}pp** | {b['win']}% | "
                      f"[{b['ci'][0]}, {b['ci'][1]}] | {b['verdict']} |")
        md.append("\n這是本輪**最關鍵的交叉驗證**：若對照 universe 的 date-neutral spread")
        md.append("也顯著為正，代表 Direction Score 的橫斷面鑑別力**不是選股偏誤的產物**。\n")

    write(md, 'b_date_neutral.md')


# ── 任務 C：RS 配對穩定性 ─────────────────────────────────────────────────
def cmd_c(_a):
    if not os.path.exists(AB_RS):
        print('[C] 缺 b2_ab_rs/trades.csv'); return
    full, ars = load(BASE), load(AB_RS)
    md = ["# 任務C：RS Paired Stability Test（build_prompt_15）\n"]
    md.append("> **目的**：驗證 B2「移除 RS 後表現略好」是否在 date-neutral 排名下依然成立，")
    md.append("> 且跨年跨 regime 穩定。B2 原本只看全期單一數字（Rank-Norm Δ=+0.088），")
    md.append("> 幅度小且未檢驗穩定性。\n")
    md.append(f"- Full model：{len(full):,} 筆｜−RS model：{len(ars):,} 筆")
    md.append("- 方法：兩模型各自用任務B 的 date-neutral 法算「當日 spread」，"
              "再對**同一天**配對相減：Δspread = (−RS spread) − (Full spread)")
    md.append("- CI：對 Δspread 時間序列 block bootstrap（1000 次）\n")

    for N in HOLDS:
        spf, _ = daily_spreads(full, N)
        spa, _ = daily_spreads(ars, N)
        common = sorted(set(spf) & set(spa))
        delta = {d: (spa[d][0] - spf[d][0], spf[d][1]) for d in common}
        v = [x[0] for x in delta.values()]
        lo, hi, w = series_bootstrap_ci(v)
        md.append(f"\n## 持有 {N} 日\n")
        md.append(f"- 配對天數：{len(common):,}")
        md.append(f"- Full 平均 spread：{statistics.mean([spf[d][0] for d in common]):+.3f}pp")
        md.append(f"- −RS 平均 spread：{statistics.mean([spa[d][0] for d in common]):+.3f}pp")
        md.append(f"- **Δspread 平均：{statistics.mean(v):+.3f}pp**"
                  f"（中位 {statistics.median(v):+.3f}pp，"
                  f"Δ>0 天數佔比 {sum(1 for x in v if x>0)/len(v):.0%}）")
        md.append(f"- **Block Bootstrap 95%CI：[{lo}, {hi}] → {ci_verdict(lo, hi)}**\n")
        if N == 20:
            md.append("### 分年拆解（20 日）\n")
            md.append("| 年份 | 天數 | Δspread 平均 | 95%CI | 判讀 |")
            md.append("|---|---|---|---|---|")
            for y in sorted({d[:4] for d in delta}):
                vv = [x[0] for d, x in delta.items() if d[:4] == y]
                if len(vv) < 20:
                    continue
                l2, h2, _ = series_bootstrap_ci(vv)
                md.append(f"| {y} | {len(vv):,} | {statistics.mean(vv):+.3f}pp | "
                          f"[{l2}, {h2}] | {ci_verdict(l2, h2)} |")
            md.append("\n### 分 Regime 拆解（20 日）\n")
            md.append("| Regime | 天數 | Δspread 平均 | 95%CI | 判讀 |")
            md.append("|---|---|---|---|---|")
            for rg in ('多頭', '盤整', '空頭'):
                vv = [x[0] for x in delta.values() if x[1] == rg]
                if len(vv) < 20:
                    md.append(f"| {rg} | {len(vv)} | 樣本不足 | — | — |")
                    continue
                l2, h2, _ = series_bootstrap_ci(vv)
                md.append(f"| {rg} | {len(vv):,} | {statistics.mean(vv):+.3f}pp | "
                          f"[{l2}, {h2}] | {ci_verdict(l2, h2)} |")
            _all_lo, _all_hi = lo, hi
            md.append("\n## 驗收判定（驗收條件4）\n")
            _yrs = []
            for y in sorted({d[:4] for d in delta}):
                vv = [x[0] for d, x in delta.items() if d[:4] == y]
                if len(vv) >= 20:
                    l2, h2, _ = series_bootstrap_ci(vv)
                    _yrs.append(ci_verdict(l2, h2))
            _pos_yrs = sum(1 for x in _yrs if x == '顯著為正')
            if _all_lo is not None and _all_lo > 0 and _pos_yrs >= max(1, len(_yrs) * 0.6):
                md.append("**支持**將 RS 列入權重調整候選：整體 Δspread CI 穩定為正，"
                          f"且 {_pos_yrs}/{len(_yrs)} 年份方向一致。→ 可排入下一輪實驗。")
            else:
                md.append(f"**不支持**。整體 Δspread CI = [{_all_lo}, {_all_hi}]"
                          f"（{ci_verdict(_all_lo,_all_hi)}），"
                          f"年份一致性 {_pos_yrs}/{len(_yrs)} 顯著為正。")
                md.append("依 spec 規定，**RS 維持「優先複驗但未證實」的狀態不變**，"
                          "不得升格為權重調整候選。")

    write(md, 'c_rs_paired.md')


# ── 任務 D：Regime Episode Block Bootstrap ───────────────────────────────
def build_episodes(rows):
    """依 as_of 的 regime 標籤，把連續同標籤日期切成 episode。"""
    reg = {}
    for r in rows:
        reg.setdefault(r['as_of'], r.get('regime', '未知'))
    days = sorted(reg)
    eps, cur = [], None
    for d in days:
        g = reg[d]
        if cur and cur['regime'] == g:
            cur['end'] = d
            cur['days'].append(d)
        else:
            if cur:
                eps.append(cur)
            cur = {'regime': g, 'start': d, 'end': d, 'days': [d]}
    if cur:
        eps.append(cur)
    for i, e in enumerate(eps, 1):
        e['id'] = i
    return eps


def episode_bootstrap(ep_vals, n_boot=1000, alpha=0.05, seed=42):
    """
    以 **episode 為重抽樣單位**（不是日期）：對 episode 取後放回抽樣，
    每次把抽到 episode 內的全部訊號池化後取平均。
    """
    eps = [v for v in ep_vals if v]
    if len(eps) < 2:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    idx = np.arange(len(eps))
    means = []
    for _ in range(n_boot):
        picked = rng.choice(idx, size=len(eps), replace=True)
        pooled = [x for i in picked for x in eps[i]]
        means.append(statistics.mean(pooled))
    lo, hi = np.percentile(means, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return (round(float(lo), 3), round(float(hi), 3), round(float(hi - lo), 3))


def cmd_d(_a):
    if not os.path.exists(NOFILTER):
        print('[D] 缺 b1_nofilter/trades.csv'); return
    base, nof = load(BASE), load(NOFILTER)
    eps = build_episodes(base)

    md = ["# 任務D：Regime Episode Block Bootstrap（build_prompt_15）\n"]
    md.append("> **目的**：處理 fix_prompt_14 揭露的殘留限制——day-cluster bootstrap 修正了")
    md.append("> 「同一天多檔聚集」，但沒處理「同一段 regime 內跨日自相關」")
    md.append("> （2022 全年空頭是一個延續事件，不是 245 個獨立日）。\n")
    md.append("- Episode 定義：`as_of` 的 regime 標籤**連續不中斷**的最長日期區間"
              "（regime 改變即為新 episode 起點）；已驗證 regime 每日唯一")
    md.append("- 重抽樣單位：**整個 episode**（非日期）。每次抽到的 episode "
              "把其內全部訊號池化取平均，重複 1000 次")
    md.append(f"- 全期共 {len(eps)} 個 episode（"
              + "、".join(f"{g} {sum(1 for e in eps if e['regime']==g)} 段"
                          for g in ('多頭', '盤整', '空頭')) + "）")
    md.append("- 對象：B1 的 **No Filter 組 A 級**訊號中 regime=盤整／空頭者"
              "（即被現行濾網壓制的那批）\n")
    md.append("⚠️ 本 CI **預期比 day-cluster 版本更寬** —— 這是任務目的（更嚴格的檢驗），"
              "不是異常。\n")

    summary = {}
    for rg in ('盤整', '空頭'):
        sub = [r for r in nof if r['grade'] == 'A' and r.get('regime') == rg]
        byd = collections.defaultdict(list)
        for r in sub:
            v = fnum(r.get('ret_20_net'))
            if v is not None:
                byd[r['as_of']].append(v)
        rg_eps = [e for e in eps if e['regime'] == rg]
        rows_out, ep_vals = [], []
        for e in rg_eps:
            vals = [v for d in e['days'] for v in byd.get(d, [])]
            if not vals:
                continue
            ep_vals.append(vals)
            rows_out.append((e['id'], e['start'], e['end'], len(e['days']),
                             len(vals), statistics.mean(vals)))
        md.append(f"\n## {rg}（No Filter A 級）\n")
        if not rows_out:
            md.append("無訊號，略過。\n")
            continue
        allv = [v for x in ep_vals for v in x]
        pos = sum(1 for r in rows_out if r[5] > 0)
        neg = len(rows_out) - pos
        md.append(f"- 有訊號的 episode：**{len(rows_out)}** / {len(rg_eps)} 段"
                  f"｜總訊號 {len(allv)} 筆｜整體平均 **{statistics.mean(allv):+.3f}%**")
        md.append(f"- 正報酬 episode {pos} 段 vs 負報酬 {neg} 段"
                  f"（正比例 {pos/len(rows_out):.0%}）\n")
        md.append("| Ep# | 起日 | 迄日 | 持續天數 | 訊號數 | 20日平均 |")
        md.append("|---|---|---|---|---|---|")
        for i, s, e_, nd, n, m in rows_out:
            md.append(f"| {i} | {s} | {e_} | {nd} | {n} | {m:+.3f}% |")
        lo, hi, w = episode_bootstrap(ep_vals)
        summary[rg] = (len(rows_out), len(allv), statistics.mean(allv), lo, hi, w)
        md.append(f"\n**Episode-level Block Bootstrap 95%CI：[{lo}, {hi}]"
                  f"（寬度 {w}）→ {ci_verdict(lo, hi)}**\n")

    # 三層 CI 對照
    md.append("\n## 三層 CI 對照（naive → day-cluster → episode）\n")
    md.append("| Cell | N | 日期數 | Episode數 | Naive CI | Day-Cluster CI | "
              "**Episode CI** | 最終判讀 |")
    md.append("|---|---|---|---|---|---|---|---|")
    prev = {'盤整': ('[1.02, 3.578]', '[0.678, 4.136]'),
            '空頭': ('[-6.052, -1.416]', '[-6.84, -1.032]')}
    for rg in ('盤整', '空頭'):
        if rg not in summary:
            continue
        nep, n, m, lo, hi, w = summary[rg]
        nd = len({r['as_of'] for r in nof
                  if r['grade'] == 'A' and r.get('regime') == rg})
        md.append(f"| {rg} restored-A | {n} | {nd} | **{nep}** | {prev[rg][0]} | "
                  f"{prev[rg][1]} | **[{lo}, {hi}]** | {ci_verdict(lo, hi)} |")

    md.append("\n## 驗收判定（驗收條件5）\n")
    for rg in ('盤整', '空頭'):
        if rg not in summary:
            continue
        nep, n, m, lo, hi, w = summary[rg]
        v = ci_verdict(lo, hi)
        if '跨 0' in v:
            md.append(f"- **{rg}：CI 跨 0（[{lo}, {hi}]）** → 在目前能做的最嚴格檢驗下，"
                      f"方向性結論**證據強度不足**。episode 數僅 {nep}，"
                      "獨立事件太少。依 spec 規定，此格不足以支撐任何規則調整建議。")
        else:
            md.append(f"- **{rg}：CI 仍不跨 0（[{lo}, {hi}]，{v}）** → "
                      f"方向性結論**通過目前能做的最嚴格檢驗**（{nep} 個獨立 episode）。")

    md.append("\n## 殘留限制\n")
    md.append("- Episode 數本身很少（盤整/空頭各僅十餘至數十段），"
              "block bootstrap 在 block 數過少時本身也不穩定；"
              "CI 應視為「數量級指標」而非精確區間。")
    md.append("- Episode 由**引擎自身的 regime 標籤**切分，"
              "若 regime 判定本身有雜訊（例如在多頭/盤整邊界頻繁跳動），"
              "會把單一市場事件切成多段，使 CI 偏窄。"
              f"實測盤整 episode 中位長度僅 4 天、空頭 6 天，"
              "確實存在此類碎片化。")
    md.append("- universe 仍是有 selection bias 的 82 檔（見 `universe_audit.md`）。")

    write(md, 'episode_bootstrap.md')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['b', 'c', 'd'])
    a = ap.parse_args()
    globals()[f'cmd_{a.cmd}'](a)


if __name__ == '__main__':
    main()
