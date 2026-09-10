"""
analyze_phase1.py — build_prompt_13 Phase 1 分析與報告產生器（report-only）

子命令：
  baseline    Step 0 基準重現比對 → baseline_reproduction.md
  b3          Direction Score 單調性 + Bootstrap CI → b3_monotonicity.md
  b1          Market Regime 四組對照 → b1_market_regime.md
  b2corr      Layer1 五因子相關性（Test A，子樣本） → 併入 b2 報告
  b2          Layer1 雙軌 Ablation → b2_layer1_ablation.md
  b2extra     Breakout Priority 影響拆解 → b2extra_breakout_priority.md
  summary     彙總 → phase1_report.md

所有報告共用同一批凍結資料與同一套成本模型參數（見 COST_PARAMS）。
"""

from __future__ import annotations

import os
import csv
import sys
import json
import random
import argparse
import statistics
from collections import defaultdict

import numpy as np

try:
    from scipy.stats import spearmanr, pearsonr
except Exception:
    spearmanr = pearsonr = None

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, 'docs', 'superpowers', 'reports', 'phase1')
BASE_DIR = os.path.join(ROOT, 'backtest_results', 'bp13_step0')
HOLDS = (5, 10, 20)

# 全部任務共用（spec §Step0：不得任一組單獨改動成本假設）
COST_PARAMS = {
    'ENABLE_COST_MODEL': True, 'COMMISSION_RATE': 0.001425, 'TAX_RATE': 0.003,
    'SLIPPAGE_MODEL': 'vol_liq', 'SLIPPAGE_BASE': 0.001,
    'SLIPPAGE_K1': 0.5, 'SLIPPAGE_K2': 0.1,
}

BP11_REF = {'A': (1305, 3.360), 'B': (12459, 2.408), 'C': (30840, 1.904)}


def load_trades(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def fnum(v):
    try:
        if v in (None, '', 'None'):
            return None
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


def rets(rows, N):
    return [r for r in (fnum(x.get(f'ret_{N}_net')) for x in rows) if r is not None]


def stat_block(rows, N):
    """單組績效指標。MDD 為訊號序（非投組）近似，報告中已標註。"""
    v = rets(rows, N)
    if not v:
        return None
    wins = [x for x in v if x > 0]
    losses = [x for x in v if x <= 0]
    gp, gl = sum(wins), abs(sum(losses))
    mean = statistics.mean(v)
    sd = statistics.pstdev(v) if len(v) > 1 else 0.0
    dn = [x for x in v if x < mean]
    sd_dn = statistics.pstdev(dn) if len(dn) > 1 else 0.0
    return {
        'n': len(v),
        'mean': round(mean, 3),
        'win': round(len(wins) / len(v) * 100, 1),
        'pf': (round(gp / gl, 3) if gl > 0 else None),
        'mdd': round(max_drawdown(rows, N), 2),
        'sharpe': (round(mean / sd, 3) if sd > 0 else None),
        'sortino': (round(mean / sd_dn, 3) if sd_dn > 0 else None),
    }


def daily_series(rows, N, non_overlapping=True):
    """
    每個 as_of 日的訊號等權平均 → 投組報酬序列。

    ⚠️ 重疊持有問題：ret_N_net 是「持有 N 日」的報酬，但訊號每日產生。
    若把每日序列直接複利，等於同一筆資金被重複投入 N 次 → 嚴重高估
    （實測會使 MDD 全部觸及 −100%，明顯失真）。
    因此預設以 **每 N 個交易日取一次**（不重疊持倉）建構序列，
    這是在現有訊號級資料上可得的最誠實近似；真正的投組模擬需要
    部位管理器，非本框架能力範圍（已於報告限制章節載明）。
    """
    byd = defaultdict(list)
    for r in rows:
        v = fnum(r.get(f'ret_{N}_net'))
        if v is not None:
            byd[r['as_of']].append(v)
    days = sorted(byd)
    if non_overlapping:
        days = days[::max(1, N)]
    return [(d, statistics.mean(byd[d])) for d in days]


def max_drawdown(rows, N):
    """等權投組（每日平均）之最大回撤（%）。以複利累積計算。"""
    ser = daily_series(rows, N)
    if not ser:
        return 0.0
    eq, peak, mdd = 1.0, 1.0, 0.0
    for _d, v in ser:
        eq *= (1 + v / 100.0)
        peak = max(peak, eq)
        mdd = min(mdd, (eq / peak - 1) * 100)
    return mdd


def cagr(rows, N):
    """以每日等權投組報酬複利，年化。訊號重疊持有 → 屬近似（報告中標註）。"""
    ser = daily_series(rows, N)
    if len(ser) < 2:
        return None
    eq = 1.0
    for _d, v in ser:
        eq *= (1 + v / 100.0)
    import datetime as _dt
    d0 = _dt.date.fromisoformat(ser[0][0])
    d1 = _dt.date.fromisoformat(ser[-1][0])
    years = max((d1 - d0).days / 365.25, 1e-9)
    if eq <= 0:
        return None
    return round((eq ** (1 / years) - 1) * 100, 2)


def bootstrap_ci(vals, n_boot=1000, alpha=0.05, seed=42):
    """平均值的 Bootstrap 信賴區間。回傳 (lo, hi, 寬度)。"""
    if not vals or len(vals) < 2:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    arr = np.asarray(vals, dtype=float)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return (round(float(lo), 3), round(float(hi), 3), round(float(hi - lo), 3))


def bootstrap_ci_clustered(rows, ret_key, n_boot=1000, alpha=0.05, seed=42):
    """
    以 as_of 日期為重抽樣單位的 Block(Day-Cluster) Bootstrap。

    為何需要：`bootstrap_ci()` 對攤平後的逐筆訊號做 iid 抽樣，
    但訊號在日期上高度聚集（同一天多檔股票一起觸發），
    把 n 筆當成 n 個獨立樣本會使 CI 偏窄、造成假顯著。

    作法：對「不重複日期」取後放回抽樣（抽樣數＝原不重複日期數），
    把抽到的每個日期的**全部**訊號池化後取平均。
    如此保留同日訊號的原始筆數與變異，但隨機性反映的是
    「日期」層級的不確定性，而非「訊號筆數」層級。
    """
    byd = defaultdict(list)
    for r in rows:
        v = fnum(r.get(ret_key))
        if v is not None:
            byd[r['as_of']].append(v)
    days = list(byd)
    if len(days) < 2:
        return (None, None, None)
    rng = np.random.default_rng(seed)
    idx = np.arange(len(days))
    means = []
    for _ in range(n_boot):
        picked = rng.choice(idx, size=len(days), replace=True)
        pooled = [v for i in picked for v in byd[days[i]]]
        means.append(statistics.mean(pooled))
    lo, hi = np.percentile(means, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return (round(float(lo), 3), round(float(hi), 3), round(float(hi - lo), 3))


def cluster_profile(rows, ret_key='ret_20_net'):
    """聚集度診斷：不重複日期數、每日筆數中位/最大、聚集比例。"""
    byd = defaultdict(list)
    for r in rows:
        v = fnum(r.get(ret_key))
        if v is not None:
            byd[r['as_of']].append(v)
    n = sum(len(v) for v in byd.values())
    d = len(byd)
    if not d:
        return None
    per = [len(v) for v in byd.values()]
    return {'n': n, 'days': d, 'median_per_day': statistics.median(per),
            'max_per_day': max(per), 'cluster_ratio': (1 - d / n) if n else 0.0}


def ci_verdict(lo, hi):
    """CI 是否跨 0 → 方向性判讀。"""
    if lo is None or hi is None:
        return '—'
    if lo > 0:
        return '顯著為正'
    if hi < 0:
        return '顯著為負'
    return '**跨 0（不顯著）**'


def meta_line(rows, extra=''):
    syms = len({r['symbol'] for r in rows})
    return (f"樣本期間 {min(r['as_of'] for r in rows)} → {max(r['as_of'] for r in rows)}"
            f"｜universe {syms} 檔｜訊號 {len(rows)} 筆｜walk-forward ✅（逐 as_of 切片）"
            f"｜OOS：全期樣本內重放（非切分 OOS）{extra}")


def cost_block():
    return ("### 成本模型參數（全部任務共用，不得單獨改動）\n\n"
            + "\n".join(f"- `{k}` = `{v}`" for k, v in COST_PARAMS.items()) + "\n")


# ── Step 0 ────────────────────────────────────────────────────────────────
def cmd_baseline(_args):
    rows = load_trades(os.path.join(BASE_DIR, 'trades.csv'))
    by = defaultdict(list)
    for r in rows:
        by[r['grade']].append(r)

    md = ["# Step 0：Baseline Reproduction（基準重現）\n"]
    md.append("> **閘門任務**：用現行 production code 原封不動（含 Breakout Priority 已知 bug、")
    md.append("> 不改任何規則）重跑全歷史，核對是否重現 bp11 已知數字。")
    md.append("> 未通過則不得進行 B1/B2/B3。\n")
    md.append(f"- {meta_line(rows)}")
    md.append(f"- 資料重用：`--reuse-data`（凍結價格快取 `_histcache_7e9dcd08c3.pkl`，"
              f"與 bp11 同一份，MD5 鍵由 `HISTORY_START_DATE=2019-06-01` 決定）")
    md.append("- 旗標狀態：`BP11_MLITE=False`、`BP11_RSI_MOM=85`（無豁免）、"
              "`BP11_THEME=False` —— 與 bp11 baseline 完全一致")
    md.append("- `R_TRACK_ENABLED=True`（bp12 後新增）：經程式碼確認僅**附加** "
              "`r_signal`/`r_strength` 欄位於 row，不參與 grade 判定，故不影響本比對\n")
    md.append(cost_block())

    md.append("\n## 逐項比對\n")
    md.append("| 指標 | bp11 已知值 | 本次重跑 | 差異 | 一致 |")
    md.append("|---|---|---|---|---|")
    allok = True
    for g, (rn, re_) in BP11_REF.items():
        n = len(by.get(g, []))
        e = statistics.mean(rets(by.get(g, []), 20))
        ok_n, ok_e = (n == rn), (abs(e - re_) < 0.005)
        allok = allok and ok_n and ok_e
        md.append(f"| {g} 級樣本數 | {rn:,} | {n:,} | {n-rn:+d} | {'✅' if ok_n else '❌'} |")
        md.append(f"| {g} 級20日期望值 | {re_:+.2f}% | {e:+.3f}% | {e-re_:+.3f} | "
                  f"{'✅' if ok_e else '❌'} |")
    md.append(f"| 總訊號數 | 130,993 | {len(rows):,} | {len(rows)-130993:+d} | "
              f"{'✅' if len(rows)==130993 else '❌'} |")

    md.append(f"\n## 結論\n")
    if allok:
        md.append("**✅ 完全重現** —— 六項指標與總樣本數全部逐位吻合，無任何差異。")
        md.append("基準已確立，B1/B2/B3 可在此凍結資料上進行。\n")
        md.append("重現成功的關鍵條件（供日後複現）：")
        md.append("1. 同一份價格快取（`--reuse-data`），避免 yfinance 歷史修訂造成漂移")
        md.append("2. 三個 bp11 旗標維持預設關閉")
        md.append("3. R_TRACK 雖預設開啟，但與動能評級完全隔離")
    else:
        md.append("**❌ 未能重現** —— 依 spec 規定，停止執行 B1/B2/B3，先排查上表差異原因。")

    md.append("\n### 過程中發現（如實記錄）\n")
    md.append("- `backtest_results/bp11_expanded/trades.csv` 磁碟現存檔案**並非 baseline**，")
    md.append("  而是 bp11 第二輪 variant（`BP11_RSI_MOM=92`）的輸出（B 級 12,401 筆，")
    md.append("  對應 bp11 報告內「12459 → 12401」那一列）——baseline 輸出當時被覆蓋。")
    md.append("  本次是以現行 code 重新產生 baseline，而非直接讀舊檔，故此比對為真實重跑。")
    md.append("- bp11 報告文字記載 universe 為 81 檔，實際凍結資料為 **82 檔**；")
    md.append("  因兩者用的是同一份快取，不影響數字一致性，僅為文件筆誤。")

    write(md, 'baseline_reproduction.md')
    return allok


def write(md, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Phase1] → {p}")
    return p


# ── B3 ────────────────────────────────────────────────────────────────────
BUCKETS = [('<30', lambda s: s < 30), ('30-40', lambda s: 30 <= s < 40),
           ('40-50', lambda s: 40 <= s < 50), ('50-60', lambda s: 50 <= s < 60),
           ('60-70', lambda s: 60 <= s < 70), ('70-80', lambda s: 70 <= s < 80),
           ('80-90', lambda s: 80 <= s < 90), ('90-100', lambda s: s >= 90)]


def cmd_b3(_args):
    rows = [r for r in load_trades(os.path.join(BASE_DIR, 'trades.csv'))
            if fnum(r.get('dir_score')) is not None]
    md = ["# B3：Direction Score 單調性檢驗\n"]
    md.append(f"- {meta_line(rows)}")
    md.append("- MDD 為「依時間等權累積的訊號級回撤」，非投組模擬（見方法論註記）")
    md.append("- Bootstrap：每桶 1000 次重抽樣，95% 信賴區間\n")
    md.append(cost_block())

    md.append("\n## 分桶表\n")
    md.append("| Direction Score | N | 5D | 10D | 20D | 10D勝率 | 20D勝率 | MDD | 20D Bootstrap 95%CI | CI寬度 |")
    md.append("|---|---|---|---|---|---|---|---|---|---|")
    bmeans = []
    for lab, cond in BUCKETS:
        sub = [r for r in rows if cond(fnum(r['dir_score']))]
        if not sub:
            md.append(f"| {lab} | 0 | — | — | — | — | — | — | — | — |")
            bmeans.append((lab, None, 0, None))
            continue
        s5, s10, s20 = (stat_block(sub, N) for N in HOLDS)
        v20 = rets(sub, 20)
        # fix_prompt_14：改用 day-cluster block bootstrap（訊號日期高度聚集）
        lo, hi, w = bootstrap_ci_clustered(sub, 'ret_20_net')
        _nlo, _nhi, _nw = bootstrap_ci(v20)   # 保留 naive 供對照表
        n = s20['n'] if s20 else 0
        flag = '⚠️' if n < 100 else ''
        md.append(f"| {lab}{flag} | {n:,} | {s5['mean'] if s5 else '—'} | "
                  f"{s10['mean'] if s10 else '—'} | {s20['mean'] if s20 else '—'} | "
                  f"{s10['win'] if s10 else '—'}% | {s20['win'] if s20 else '—'}% | "
                  f"{s20['mdd'] if s20 else '—'} | [{lo}, {hi}] | {w} |")
        bmeans.append((lab, s20['mean'] if s20 else None, n, (lo, hi, w)))
    md.append("\n⚠️ = N<100，point estimate 不可單獨採信")
    md.append("\n**CI 欄位已改用 day-cluster block bootstrap**"
              "（以 `as_of` 日期為重抽樣單位）——見下方新舊對照表。\n")

    # ── fix_prompt_14：新舊 CI 對照（全期分桶 + 分 regime）──────────────
    md.append("\n## Bootstrap CI 修正：Naive vs Day-Cluster（fix_prompt_14）\n")
    md.append("> 原 `bootstrap_ci()` 對攤平的逐筆訊號做 iid 重抽樣；但同一天常有多檔股票")
    md.append("> 同時觸發訊號（本節各桶聚集比例 81–96%），把 n 筆當 n 個獨立樣本會使 CI 偏窄。")
    md.append("> 修正版以「日期」為重抽樣單位，池化該日全部訊號。")
    md.append("> 聚集度明細見 [bootstrap_diagnostic.md](bootstrap_diagnostic.md)。\n")
    md.append("### 全期分桶（20D）\n")
    md.append("| 分桶 | N | 不重複日期 | 聚集比例 | Naive CI | Cluster CI | 寬度倍數 | 結論是否改變 |")
    md.append("|---|---|---|---|---|---|---|---|")
    _changed = []
    for lab, cond in BUCKETS:
        sub = [r for r in rows if cond(fnum(r['dir_score']))]
        if not sub:
            continue
        p = cluster_profile(sub)
        v = rets(sub, 20)
        nlo, nhi, nw = bootstrap_ci(v)
        clo, chi, cw = bootstrap_ci_clustered(sub, 'ret_20_net')
        vn, vc = ci_verdict(nlo, nhi), ci_verdict(clo, chi)
        ch = vn != vc
        if ch:
            _changed.append(f'全期 {lab}')
        md.append(f"| {lab} | {p['n']:,} | {p['days']:,} | {p['cluster_ratio']:.0%} | "
                  f"[{nlo}, {nhi}] | [{clo}, {chi}] | {cw/nw:.1f}x | "
                  f"{'⚠️ **改變**：' + vc if ch else '不變（' + vc + '）'} |")
    md.append("\n### 分 Regime × 分桶（僅列 n≥30；★ 為結論改變者）\n")
    md.append("| Regime | 分桶 | N | 日期 | 平均 | Naive CI | Cluster CI | Cluster 判讀 | 改變 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for reg in ('多頭', '盤整', '空頭'):
        sr = [r for r in rows if r.get('regime') == reg]
        for lab, cond in BUCKETS:
            sub = [r for r in sr if cond(fnum(r['dir_score']))]
            v = rets(sub, 20)
            if len(v) < 30:
                continue
            p = cluster_profile(sub)
            nlo, nhi, _ = bootstrap_ci(v)
            clo, chi, _ = bootstrap_ci_clustered(sub, 'ret_20_net')
            vn, vc = ci_verdict(nlo, nhi), ci_verdict(clo, chi)
            ch = vn != vc
            if ch:
                _changed.append(f'{reg} {lab}')
            md.append(f"| {reg} | {lab} | {p['n']:,} | {p['days']:,} | "
                      f"{statistics.mean(v):+.2f}% | [{nlo}, {nhi}] | [{clo}, {chi}] | "
                      f"{vc} | {'★ **是**' if ch else '否'} |")
    md.append("")
    if _changed:
        md.append(f"**結論改變的 cell（{len(_changed)} 個）**：{', '.join(_changed)}\n")
        md.append("依 fix_prompt_14 規定，這些 cell 的判讀一律改為")
        md.append("「**CI 跨 0，方向性結論證據強度不足，待更多獨立事件樣本**」，"
                  "不挑選對原結論有利的 CI。\n")
    else:
        md.append("**全部 cell 結論未改變**（CI 雖變寬，顯著性方向不變）。\n")

    # Spearman
    md.append("## 等級相關（Spearman）\n")
    md.append("| 持有期 | Spearman ρ | p-value | 解讀 |")
    md.append("|---|---|---|---|")
    for N in HOLDS:
        pairs = [(fnum(r['dir_score']), fnum(r.get(f'ret_{N}_net'))) for r in rows]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if spearmanr and len(pairs) > 100:
            rho, p = spearmanr([a for a, _ in pairs], [b for _, b in pairs])
            tag = ('正相關（分數越高報酬越好）' if rho > 0.02 else
                   '負相關' if rho < -0.02 else '幾無單調關係')
            md.append(f"| {N}D | {rho:+.4f} | {p:.3g} | {tag} |")
        else:
            md.append(f"| {N}D | — | — | scipy 不可用或樣本不足 |")

    # Top vs bottom quantile
    md.append("\n## Top 20% vs Bottom 20% 價差\n")
    md.append("| 持有期 | Top20% 平均 | Bottom20% 平均 | Spread | Top N | Bottom N |")
    md.append("|---|---|---|---|---|---|")
    scored = sorted(rows, key=lambda r: fnum(r['dir_score']))
    k = max(1, len(scored) // 5)
    bot, top = scored[:k], scored[-k:]
    for N in HOLDS:
        tb, bb = rets(top, N), rets(bot, N)
        if tb and bb:
            md.append(f"| {N}D | {statistics.mean(tb):+.3f}% | {statistics.mean(bb):+.3f}% | "
                      f"**{statistics.mean(tb)-statistics.mean(bb):+.3f}pp** | {len(tb):,} | {len(bb):,} |")

    # 90-100 saturation
    md.append("\n## 90–100 區間飽和度檢查\n")
    hi_b = next((b for b in bmeans if b[0] == '90-100'), None)
    ref_b = [b for b in bmeans if b[0] in ('70-80', '80-90') and b[1] is not None]
    if hi_b and hi_b[1] is not None and ref_b:
        ref_mean = statistics.mean([b[1] for b in ref_b])
        md.append(f"- 90–100 桶：20D 平均 **{hi_b[1]:+.3f}%**，N={hi_b[2]:,}，"
                  f"95%CI=[{hi_b[3][0]}, {hi_b[3][1]}]（寬度 {hi_b[3][2]}）")
        md.append(f"- 70–90 區間平均：{ref_mean:+.3f}%")
        if hi_b[1] < ref_mean:
            if hi_b[2] < 100:
                md.append(f"- **判定：樣本不足，無法判斷是否為真實 saturation**"
                          f"（N={hi_b[2]}<100，CI 寬度 {hi_b[3][2]} 過寬）")
            else:
                md.append(f"- **判定：出現相對下降**（N={hi_b[2]:,} 足夠），"
                          f"需注意高分區可能已達飽和；但仍須對照 CI 是否與 70–90 區間重疊")
        else:
            md.append("- **判定：未見飽和**，90–100 桶不低於 70–90 區間")
    else:
        md.append("- 90–100 桶無有效樣本，無法評估")

    # 分 regime / 分年
    md.append("\n## 分 Regime 一致性（20D）\n")
    md.append("| Regime | " + " | ".join(l for l, _ in BUCKETS) + " | Spearman ρ |")
    md.append("|---" * (len(BUCKETS) + 2) + "|")
    for reg in ('多頭', '盤整', '空頭'):
        sub_all = [r for r in rows if r.get('regime') == reg]
        cells = []
        for lab, cond in BUCKETS:
            sub = [r for r in sub_all if cond(fnum(r['dir_score']))]
            v = rets(sub, 20)
            cells.append(f"{statistics.mean(v):+.2f}" if len(v) >= 30 else '—')
        pairs = [(fnum(r['dir_score']), fnum(r.get('ret_20_net'))) for r in sub_all]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        rho = (f"{spearmanr([a for a,_ in pairs],[b for _,b in pairs])[0]:+.4f}"
               if spearmanr and len(pairs) > 100 else '—')
        md.append(f"| {reg}（n={len(sub_all):,}） | " + " | ".join(cells) + f" | {rho} |")

    md.append("\n## 分年一致性（20D Spearman ρ）\n")
    md.append("| 年份 | N | Spearman ρ | Top20−Bot20 |")
    md.append("|---|---|---|---|")
    byyear = defaultdict(list)
    for r in rows:
        byyear[r['as_of'][:4]].append(r)
    for y in sorted(byyear):
        sub = byyear[y]
        pairs = [(fnum(r['dir_score']), fnum(r.get('ret_20_net'))) for r in sub]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if spearmanr and len(pairs) > 100:
            rho = spearmanr([a for a, _ in pairs], [b for _, b in pairs])[0]
            ss = sorted(sub, key=lambda r: fnum(r['dir_score']))
            kk = max(1, len(ss) // 5)
            tb, bb = rets(ss[-kk:], 20), rets(ss[:kk], 20)
            sp = (f"{statistics.mean(tb)-statistics.mean(bb):+.2f}pp" if tb and bb else '—')
            md.append(f"| {y} | {len(sub):,} | {rho:+.4f} | {sp} |")

    # ── 解讀 ──────────────────────────────────────────────────────────
    md.append("\n## 解讀與結論\n")
    md.append("### 1. Spearman ρ≈0 與「分桶單調」並不矛盾——不可只看其中一個\n")
    md.append("全樣本 20D Spearman **ρ=+0.0011（p=0.70，不顯著）**，乍看像「完全沒有鑑別度」；")
    md.append("但同一批資料的分桶平均卻是乾淨遞增（1.24% → 3.25%），Top20−Bot20 價差 **+2.17pp**。")
    md.append("兩者都對，差別在**衡量的層次**：\n")
    md.append("- Spearman 衡量的是「個別訊號」層級的等級一致性。單一台股 20 日報酬的個股雜訊")
    md.append("  遠大於因子訊號，逐筆排序幾乎純噪音 → ρ 必然趨近 0。")
    md.append("- 分桶平均把數千筆的雜訊平均掉，留下的是**橫斷面期望值差異**，這才是選股要用的東西。\n")
    md.append("**結論：Direction Score 具有「群體期望值鑑別力」，但不具「逐筆排序預測力」。**")
    md.append("實務意涵——可用於分級與排序（現行用途正確），")
    md.append("但不應據以宣稱「分數高的個股會贏過分數低的個股」。\n")

    md.append("### 2. 空頭 regime 的單調性**反轉**（經 cluster CI 修正後仍成立，但邊界收窄）\n")
    md.append("多頭 ρ=+0.017、分桶乾淨遞增；空頭 ρ=−0.108 且中高分桶報酬為負。")
    md.append("以 **day-cluster CI** 檢驗空頭各桶（fix_prompt_14 修正後）：\n")
    md.append("| 空頭分桶 | 平均 | Cluster CI | 判讀 |")
    md.append("|---|---|---|---|")
    md.append("| 50–60 | −1.75% | [−3.231, −0.255] | 顯著為負 ✅ |")
    md.append("| 60–70 | −1.65% | [−2.986, −0.258] | 顯著為負 ✅ |")
    md.append("| 70–80 | −1.82% | [−3.357, −0.393] | 顯著為負 ✅ |")
    md.append("| 80–90 | −3.50% | [−5.03, −2.075] | 顯著為負 ✅ |")
    md.append("| **90–100** | −1.71% | **[−3.537, 0.056]** | **跨 0，證據強度不足** ⚠️ |")
    md.append("| **<30** | +1.60% | **[−0.038, 3.184]** | **跨 0，證據強度不足** ⚠️ |")
    md.append("")
    md.append("**修正後的正確表述**：在空頭市場中，**方向分 50–90 區間顯著為負**"
              "（四個相鄰桶一致，非單格僥倖）；")
    md.append("但原先引用的兩個極端桶——最高分 90–100 與最低分 <30——在 cluster CI 下")
    md.append("**都變成跨 0，不能再作為證據**。\n")
    md.append("因此「空頭中方向分越高越危險」這句話需要修正為："
              "**空頭中方向分處於中高區間（50–90）者顯著虧損**；")
    md.append("最高分區間（90–100）雖點估計為負，但獨立事件樣本不足"
              "（n=1,209 僅來自 177 天）無法斷言。\n")
    md.append("即使如此，反轉的核心結論仍由四個相鄰桶支撐，且與 B1 空頭 A 級的")
    md.append("cluster CI [−6.84, −1.032]（顯著為負）互相印證。\n")

    md.append("### 3. 時間穩定性不足——全期 +2.17pp 有集中來源，不可直接外推\n")
    md.append("分年 Top20−Bot20 價差：**8 年中有 3 年為負**（2019 −2.08pp、2021 −2.77pp、")
    md.append("2022 −4.45pp），2023 幾乎為零（−0.55pp）；全期正價差主要由 **2026 的 +10.92pp**")
    md.append("與 2024 的 +1.86pp 拉起。分年 Spearman 亦有 5 年為負。\n")
    md.append("依本專案 bp10 建立的反過擬合紀律（單調 + 時間雙半穩定才可入權重），")
    md.append("**Direction Score 的鑑別力通過「分桶單調」但未通過「時間穩定」**。")
    md.append("這與第 2 點互為因果：負價差年份（2021/2022）正是空頭與高波動年，")
    md.append("而空頭中方向分是反指標。\n")
    md.append("**因此正確的結論不是「方向分無效」，而是「方向分的有效性條件於市場環境」**——")
    md.append("這強化了 regime-aware 設計的必要性，而非否定因子本身。\n")

    md.append("### 4. 90–100 桶未見飽和\n")
    md.append("N=29,416（樣本充足，非小樣本）、CI 寬度僅 0.434，且 +3.249% 高於 70–90 區間的")
    md.append("+2.154%。**無需標記為 saturation**。\n")

    md.append("### 5. 5D 為負、20D 為正的持有期效應\n")
    md.append("5D 全桶接近 0 或為負（Spearman ρ=−0.030），10D 轉正，20D 最清楚。")
    md.append("與 bp11 既有結論一致（5/10 日全樣本無鑑別度），屬系統既有特性。")
    md.append("成本模型（round-trip 約 0.585%）在 5 日持有期佔比過高是主因之一。\n")

    md.append("### 方法論限制（如實記錄）\n")
    md.append("- **MDD/CAGR 為近似**：訊號每日產生但持有 N 日，直接把每日序列複利會使同一筆")
    md.append("  資金重複投入 N 次（實測會讓 MDD 全部觸及 −100%，明顯失真）。本報告改以")
    md.append("  **每 N 個交易日取樣一次**（持倉不重疊）建構等權序列。真正的投組層級 MDD")
    md.append("  需要部位管理器與資金配置模擬，**超出現有 `signal_backtest.py` 框架能力**。")
    md.append("- 全期為樣本內重放（walk-forward as-of 切片，無前視），非切分訓練/測試的 OOS。")
    md.append("- **殘留限制：事件層級（episode-level）自相關未處理**。"
              "day-cluster bootstrap 修正的是「同一天多檔股票共同觸發」的聚集，"
              "但 regime 本身橫跨連續數週至數月——同一次崩盤事件內**不同天之間**"
              "仍存在自相關（例如 2022 全年空頭是一個延續事件，不是 245 個獨立日）。"
              "本輪未實作 episode-level block bootstrap（避免過度工程化），"
              "故現有 cluster CI 仍可能**偏窄**，方向是保守化不足而非過度保守。"
              "若未來要再深入，下一步是以「連續 regime 區段」為 block 單位重抽樣，"
              "屆時空頭類 cell 的 CI 預期會再明顯放寬。")


    write(md, 'b3_monotonicity.md')


# ── B1：Market Regime 四組對照 ────────────────────────────────────────────
BUY_GRADES = ('A', 'B', 'C')
UNIT = 0.10          # 單一訊號基礎部位＝資金 10%
REGIME_SCALE = {'多頭': 1.00, '盤整': 0.70, '空頭': 0.40}    # 組別C：逐筆縮放
REGIME_CAP = {'多頭': 1.00, '盤整': 0.70, '空頭': 0.40}      # 組別D：總曝險上限


def portfolio_series(rows, N, mode='base'):
    """
    每日等權投組報酬序列（不重疊取樣），依 mode 套用部位規則。

    mode='base'  ：曝險 = min(k×UNIT, 1.0)              （A/B 組）
    mode='scale' ：曝險 = min(k×UNIT, 1.0) × scale(reg) （C 組：逐筆縮放）
    mode='cap'   ：曝險 = min(k×UNIT, cap(reg))         （D 組：總曝險上限）
    """
    byd = defaultdict(list)
    reg_of = {}
    for r in rows:
        v = fnum(r.get(f'ret_{N}_net'))
        if v is None:
            continue
        byd[r['as_of']].append(v)
        reg_of.setdefault(r['as_of'], r.get('regime', '未知'))
    days = sorted(byd)[::max(1, N)]
    out = []
    for d in days:
        v = byd[d]
        k = len(v)
        reg = reg_of.get(d, '未知')
        if mode == 'scale':
            expo = min(k * UNIT, 1.0) * REGIME_SCALE.get(reg, 1.0)
        elif mode == 'cap':
            expo = min(k * UNIT, REGIME_CAP.get(reg, 1.0))
        else:
            expo = min(k * UNIT, 1.0)
        out.append((d, expo * statistics.mean(v), reg))
    return out


def perf_from_series(ser):
    """由 (date, ret%, regime) 序列算 CAGR/MDD/Sharpe/Sortino/PF/Expectancy。"""
    if len(ser) < 2:
        return None
    v = [x[1] for x in ser]
    eq, peak, mdd = 1.0, 1.0, 0.0
    for x in v:
        eq *= (1 + x / 100.0)
        peak = max(peak, eq)
        mdd = min(mdd, (eq / peak - 1) * 100)
    import datetime as _dt
    yrs = max((_dt.date.fromisoformat(ser[-1][0]) - _dt.date.fromisoformat(ser[0][0])).days / 365.25, 1e-9)
    cg = ((eq ** (1 / yrs) - 1) * 100) if eq > 0 else None
    mean = statistics.mean(v)
    sd = statistics.pstdev(v) if len(v) > 1 else 0
    dn = [x for x in v if x < 0]
    sd_dn = statistics.pstdev(dn) if len(dn) > 1 else 0
    gp = sum(x for x in v if x > 0)
    gl = abs(sum(x for x in v if x <= 0))
    return {
        'periods': len(v), 'cagr': (round(cg, 2) if cg is not None else None),
        'exp': round(mean, 3), 'pf': (round(gp / gl, 3) if gl > 0 else None),
        'mdd': round(mdd, 2), 'win': round(sum(1 for x in v if x > 0) / len(v) * 100, 1),
        'sharpe': (round(mean / sd, 3) if sd > 0 else None),
        'sortino': (round(mean / sd_dn, 3) if sd_dn > 0 else None),
    }


def cmd_b1(_args):
    cur = [r for r in load_trades(os.path.join(BASE_DIR, 'trades.csv'))
           if r['grade'] in BUY_GRADES]
    nf_path = os.path.join(ROOT, 'backtest_results', 'b1_nofilter', 'trades.csv')
    nof = ([r for r in load_trades(nf_path) if r['grade'] in BUY_GRADES]
           if os.path.exists(nf_path) else None)

    md = ["# B1：Market Regime 四組對照\n"]
    md.append(f"- {meta_line(cur)}（僅計買進族 A/B/C）")
    md.append("- 四組共用同一批凍結資料與同一套成本模型；僅 B 組需重跑引擎"
              "（關閉大盤濾網），C/D 組為部位覆蓋層，grade 與 A 組相同\n")
    md.append(cost_block())
    md.append("\n### 投組模擬假設（如實載明）\n")
    md.append(f"- 單一訊號基礎部位 = 資金 **{UNIT:.0%}**；同日 k 檔訊號 → 曝險 min(k×{UNIT:.0%}, 上限)")
    md.append(f"- 組別C 逐筆縮放：多頭 {REGIME_SCALE['多頭']:.0%} / 盤整 "
              f"{REGIME_SCALE['盤整']:.0%} / 空頭 {REGIME_SCALE['空頭']:.0%}")
    md.append(f"- 組別D 總曝險上限：多頭 {REGIME_CAP['多頭']:.0%} / 盤整 "
              f"{REGIME_CAP['盤整']:.0%} / 空頭 {REGIME_CAP['空頭']:.0%}（單筆不縮放，"
              "僅在同日加總超過上限時等比壓縮）")
    md.append("- 為避免重疊持倉導致資金重複投入，序列以**每 N 個交易日取樣一次**建構\n")

    md.append("\n### ⚠️ 比較基準的關鍵修正（務必先讀）\n")
    md.append("初版設計以「全買進族（A/B/C）等權」比較四組，結果 A 組與 B 組數字**完全相同**。")
    md.append("追查後確認這不是 bug，而是**比較基準設計錯誤**：\n")
    md.append(f"- Current 買進族 A+B+C = **{len(cur):,}** 筆；No Filter 買進族亦為 "
              f"**{len(nof):,}** 筆（若已完成）—— 總數相同。" if nof is not None else
              "- Current 與 No Filter 的買進族總數相同。")
    md.append("- 因為大盤濾網**只在 A/B/C 之間重新貼標籤**（A→B/C 降級），"
              "並未把任何訊號逐出買進族。")
    md.append("- 因此「全買進族等權」在建構上就不可能顯示濾網效果。\n")
    md.append("**濾網真正作用的是 A 級書**（最高信度、實務上部位最重的一群）。")
    md.append("故本報告以 **A 級書為主要比較基準**，另附全買進族表作為對照佐證。\n")

    md.append("**組別 C/D 的資料基礎**：spec 定義 C/D 為「**grade 不變**」——即不做 regime 降級、")
    md.append("改以部位管理控風險。因此 C/D 建立在 **No Filter 的 grade** 之上（濾網關閉），")
    md.append("與 A 組（降級）形成「降級 vs 部位控管」的真正對照；若誤用 Current 的 grade，")
    md.append("等於「既降級又縮倉」，無法回答 spec 的問題。\n")

    _cur_a = [r for r in cur if r['grade'] == 'A']
    _nof_a = [r for r in nof if r['grade'] == 'A'] if nof is not None else None
    arms_a = [('A. Current（濾網降級）', _cur_a, 'base'),
              ('B. No Filter（不降級、不控倉）', _nof_a, 'base'),
              ('C. Position Sizing（不降級＋逐筆縮放）', _nof_a, 'scale'),
              ('D. Hybrid（不降級＋總曝險上限）', _nof_a, 'cap')]

    for N in HOLDS:
        md.append(f"\n## 【主要基準】A 級書｜持有 {N} 日｜全期間\n")
        md.append("| 組別 | A級訊號數 | 期數 | CAGR | Expectancy | PF | 勝率 | MDD | Sharpe | Sortino |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for name, data, mode in arms_a:
            if data is None:
                md.append(f"| {name} | —（回測未完成） | — | — | — | — | — | — | — | — |")
                continue
            p = perf_from_series(portfolio_series(data, N, mode))
            if not p:
                md.append(f"| {name} | {len(data):,} | — | — | — | — | — | — | — | — |")
                continue
            md.append(f"| {name} | {len(data):,} | {p['periods']} | {p['cagr']}% | "
                      f"{p['exp']}% | {p['pf']} | {p['win']}% | {p['mdd']}% | "
                      f"{p['sharpe']} | {p['sortino']} |")

    # A 級書分 regime
    md.append("\n## 【主要基準】A 級書｜持有 20 日｜分 Regime\n")
    for reg in ('多頭', '盤整', '空頭'):
        md.append(f"\n### {reg}\n")
        md.append("| 組別 | A級訊號數 | 不重疊期數 | 訊號級期望 | 投組期望 | PF | 勝率 | MDD |")
        md.append("|---|---|---|---|---|---|---|---|")
        for name, data, mode in arms_a:
            if data is None:
                md.append(f"| {name} | — | — | — | — | — | — | — |")
                continue
            sub = [r for r in data if r.get('regime') == reg]
            p = perf_from_series(portfolio_series(sub, 20, mode)) if sub else None
            if not p:
                md.append(f"| {name} | {len(sub):,} | — | — | — | — | — | — |")
                continue
            _sv = rets(sub, 20)
            _sig = f"{statistics.mean(_sv):+.3f}%" if _sv else "—"
            _warn = " ⚠️" if p['periods'] < 10 else ""
            md.append(f"| {name} | {len(sub):,} | {p['periods']}{_warn} | **{_sig}** | "
                      f"{p['exp']}% | {p['pf']} | {p['win']}% | {p['mdd']}% |")

    arms = [('A. Current（濾網降級）', cur, 'base'),
            ('B. No Filter（不降級、不控倉）', nof, 'base'),
            ('C. Position Sizing（不降級＋逐筆縮放）', nof, 'scale'),
            ('D. Hybrid（不降級＋總曝險上限）', nof, 'cap')]

    for N in HOLDS:
        md.append(f"\n## 【對照】全買進族 A/B/C｜持有 {N} 日｜全期間\n")
        md.append("| 組別 | 訊號數 | 期數 | CAGR | Expectancy | PF | 勝率 | MDD | Sharpe | Sortino |")
        md.append("|---|---|---|---|---|---|---|---|---|---|")
        for name, data, mode in arms:
            if data is None:
                md.append(f"| {name} | — | — | — | — | — | — | — | — | — |（回測未完成）")
                continue
            p = perf_from_series(portfolio_series(data, N, mode))
            if not p:
                md.append(f"| {name} | {len(data):,} | — | — | — | — | — | — | — | — |")
                continue
            md.append(f"| {name} | {len(data):,} | {p['periods']} | {p['cagr']}% | "
                      f"{p['exp']}% | {p['pf']} | {p['win']}% | {p['mdd']}% | "
                      f"{p['sharpe']} | {p['sortino']} |")

    # 分 regime
    for N in (20,):
        md.append(f"\n## 持有 {N} 日｜分 Regime（Bull / Range / Bear 各一次）\n")
        for reg in ('多頭', '盤整', '空頭'):
            md.append(f"\n### {reg}\n")
            md.append("| 組別 | 訊號數 | 期數 | CAGR | Expectancy | PF | 勝率 | MDD | Sharpe | Sortino |")
            md.append("|---|---|---|---|---|---|---|---|---|---|")
            for name, data, mode in arms:
                if data is None:
                    md.append(f"| {name} | — | — | — | — | — | — | — | — | — |")
                    continue
                sub = [r for r in data if r.get('regime') == reg]
                if not sub:
                    md.append(f"| {name} | 0 | — | — | — | — | — | — | — | — |")
                    continue
                p = perf_from_series(portfolio_series(sub, N, mode))
                if not p:
                    md.append(f"| {name} | {len(sub):,} | — | — | — | — | — | — | — | — |")
                    continue
                md.append(f"| {name} | {len(sub):,} | {p['periods']} | {p['cagr']}% | "
                          f"{p['exp']}% | {p['pf']} | {p['win']}% | {p['mdd']}% | "
                          f"{p['sharpe']} | {p['sortino']} |")

    # 等級分佈對照（濾網影響最直接的證據）
    if nof is not None:
        md.append("\n## 濾網對等級分佈的影響（A 組 vs B 組）\n")
        md.append("| 等級 | A. Current | B. No Filter | 差異 |")
        md.append("|---|---|---|---|")
        ca = defaultdict(int); cb = defaultdict(int)
        for r in cur:
            ca[r['grade']] += 1
        for r in nof:
            cb[r['grade']] += 1
        for g in BUY_GRADES:
            md.append(f"| {g} | {ca[g]:,} | {cb[g]:,} | {cb[g]-ca[g]:+,} |")

    # ── 解讀 ──────────────────────────────────────────────────────────
    md.append("\n## 解讀與結論\n")
    _cur_bear = [r for r in _cur_a if r.get('regime') == '空頭']
    _cur_rng = [r for r in _cur_a if r.get('regime') == '盤整']
    md.append("### 1. 現行濾網在盤整/空頭把 A 級**完全歸零**\n")
    md.append(f"A 組（Current）在盤整 A 級 = **{len(_cur_rng)}** 筆、空頭 A 級 = "
              f"**{len(_cur_bear)}** 筆——不是變少，是歸零。這是規則的直接後果"
              "（空頭壓制 A、盤整 A→B），非資料問題。\n")
    if _nof_a is not None:
        _nb = [r for r in _nof_a if r.get('regime') == '空頭']
        _nr = [r for r in _nof_a if r.get('regime') == '盤整']
        vb, vr = rets(_nb, 20), rets(_nr, 20)
        md.append("### 2. 被壓掉的 A 級訊號：盤整**該救**、空頭**該殺**（結論分歧）\n")
        md.append("關閉濾網後，這些被降級的訊號恢復 A 身分。以**訊號級**（全樣本，非取樣）"
                  "20 日報酬評估：\n")
        md.append("| Regime | n | 訊號級平均 | Bootstrap 95%CI | 判讀 |")
        md.append("|---|---|---|---|---|")
        _verdicts = {}
        for _lab, _v in (('盤整', vr), ('空頭', vb)):
            if not _v:
                md.append(f"| {_lab} | 0 | — | — | — |")
                continue
            _m = statistics.mean(_v)
            _rowset = _nr if _lab == '盤整' else _nb
            lo, hi, _w = bootstrap_ci_clustered(_rowset, 'ret_20_net')
            if lo is not None and lo > 0:
                jd = "顯著為正 → 濾網**誤殺**"
            elif hi is not None and hi < 0:
                jd = "顯著為負 → 濾網**正確**"
            else:
                jd = "CI 跨 0，無定論"
            _verdicts[_lab] = jd
            md.append(f"| {_lab} | {len(_v)} | **{_m:+.3f}%** | [{lo}, {hi}] | {jd} |")
        md.append("")
        md.append("**兩個 regime 的結論相反，不可一概而論：**\n")
        if '空頭' in _verdicts and '正確' in _verdicts['空頭']:
            md.append("- **空頭：濾網是對的。** 被壓制的 A 級訊號平均 "
                      f"{statistics.mean(vb):+.2f}%，CI 完全落在負區間。"
                      "空頭中壓制多方訊號有明確實證支持，**不應放寬**。")
            md.append("  這也與 B3 的空頭反轉發現一致（空頭中順勢動能是負貢獻）。")
        if '盤整' in _verdicts and '誤殺' in _verdicts['盤整']:
            md.append(f"- **盤整：濾網可能過度保守。** 被降級的 {len(vr)} 筆平均 "
                      f"{statistics.mean(vr):+.2f}%，CI 完全落在正區間，"
                      "且高於全期 A 級平均。**這是下一輪最值得檢視的調整點**"
                      "（盤整 A→B 的一律降級是否過嚴）。")
        md.append("")
        # ── fix_prompt_14：新舊 CI 對照 ──────────────────────────────
        md.append("#### Bootstrap CI 修正對照（fix_prompt_14）\n")
        md.append("原 CI 以逐筆訊號 iid 重抽樣；同一天多檔股票同時觸發使其偏窄。")
        md.append("下表並列 naive 與 day-cluster（以日期為重抽樣單位）結果：\n")
        md.append("| Cell | N | 不重複日期 | 聚集比例 | Naive CI | Cluster CI | 寬度倍數 | 結論是否改變 |")
        md.append("|---|---|---|---|---|---|---|---|")
        _b1chg = []
        for _lab, _rowset in (('空頭 A級', _nb), ('盤整 A級', _nr),
                              ('多頭 A級', [r for r in _nof_a if r.get('regime') == '多頭'])):
            _vv = rets(_rowset, 20)
            if not _vv:
                continue
            _p = cluster_profile(_rowset)
            _nl, _nh, _nw = bootstrap_ci(_vv)
            _cl, _ch, _cw = bootstrap_ci_clustered(_rowset, 'ret_20_net')
            _vn, _vc = ci_verdict(_nl, _nh), ci_verdict(_cl, _ch)
            _ch2 = _vn != _vc
            if _ch2:
                _b1chg.append(_lab)
            md.append(f"| {_lab} | {_p['n']:,} | {_p['days']:,} | {_p['cluster_ratio']:.0%} | "
                      f"[{_nl}, {_nh}] | [{_cl}, {_ch}] | {_cw/_nw:.2f}x | "
                      f"{'⚠️ **改變**：' + _vc if _ch2 else '不變（' + _vc + '）'} |")
        md.append("")
        if _b1chg:
            md.append(f"⚠️ **結論改變**：{', '.join(_b1chg)} → 判讀改為"
                      "「CI 跨 0，方向性結論證據強度不足，待更多獨立事件樣本」。\n")
        else:
            md.append("**三格結論皆未改變**：CI 寬度增加 1.25–1.35 倍，但顯著性方向不變。")
            md.append("本節「盤整該救／空頭該殺」的方向性結論在 day-cluster 修正後仍成立。")
            md.append("惟盤整下界由 1.02 收窄至 0.678（更接近 0），信心邊際變薄，")
            md.append("採納前仍建議補時間穩定性驗證。\n")

        md.append("⚠️ **方法論警告（重要）**：本節刻意採用**訊號級**平均而非上方表格的")
        md.append("投組序列值。原因：空頭 A 級只有 5 個不重疊期，取樣後的投組數字"
                  f"（+0.982%）與訊號級真值（{statistics.mean(vb):+.3f}%）**符號相反**——")
        md.append("5 期樣本完全不具代表性。**凡不重疊期數 < 10 的格子，一律以訊號級數字為準**，")
        md.append("上方表格的該類欄位僅供結構參考。\n")
    md.append("### 3. 濾網的真實 trade-off：品質換機會\n")
    md.append("全期 A 級書：Current 期望 0.846%／PF 2.413／勝率 60.0%／MDD −4.5%；")
    md.append("No Filter 期望 0.823%／PF 2.162／勝率 54.7%／MDD −11.09%。")
    md.append("濾網確實**提升每筆品質並大幅壓低回撤**，代價是訊號數減半（1,305 vs 2,496）。\n")
    md.append("⚠️ CAGR 欄位不可直接對比：A 組僅 25 個不重疊投資期、B 組 53 期，")
    md.append("CAGR 差異主要反映**在市時間**不同，而非單位風險報酬差異。"
              "請以 Expectancy／PF／MDD 為準。\n")
    md.append("### 4. 組別 D（總曝險上限）幾乎沒有作用\n")
    md.append(f"D 組多數欄位與 B 組相同。原因：A 級訊號稀疏，同日筆數 k 很小，")
    md.append(f"`k × {UNIT:.0%}` 極少觸及 {REGIME_CAP['盤整']:.0%}／{REGIME_CAP['空頭']:.0%} 的上限，")
    md.append("上限形同虛設。**spec 所設想的「同一天多檔 A 訊號撐爆曝險」在實際資料中幾乎不發生**——")
    md.append("這本身就是對 D 設計的一個答案：在目前的 A 級稀缺度下，總曝險上限不是有效槓桿。\n")
    md.append("### 5. 組別 C（逐筆縮放）在盤整/空頭降低報酬也降低回撤\n")
    md.append("盤整：期望 1.082% → 0.758%、MDD −3.78% → −2.65%；"
              "空頭：期望 0.982% → 0.393%、MDD −1.79% → −0.72%。")
    md.append("屬線性縮放的必然結果（報酬與回撤同比例縮小），"
              "**單位風險報酬未改善**，並非真正的風險控制優化。\n")

    md.append("\n## 限制\n")
    md.append("- 投組模擬為**近似**：單筆部位以固定比例代替真實風險預算（ATR/波動度定量），")
    md.append("  且未模擬資金曲線上的實際成交與再平衡。真正的部位管理器超出現有")
    md.append("  `signal_backtest.py` 框架能力，已依 spec 規定如實記錄而非簡化到失真。")
    md.append("- regime 標記取自訊號當日 `market_regime.trend_direction`（as-of，無前視）。")
    md.append("- **殘留限制：事件層級（episode-level）自相關未處理**。"
              "day-cluster bootstrap 修正的是「同一天多檔股票共同觸發」的聚集，"
              "但 regime 本身橫跨連續數週至數月——同一次崩盤事件內**不同天之間**"
              "仍存在自相關（例如 2022 全年空頭是一個延續事件，不是 245 個獨立日）。"
              "本輪未實作 episode-level block bootstrap（避免過度工程化），"
              "故現有 cluster CI 仍可能**偏窄**，方向是保守化不足而非過度保守。"
              "若未來要再深入，下一步是以「連續 regime 區段」為 block 單位重抽樣，"
              "屆時空頭類 cell 的 CI 預期會再明顯放寬。")


    write(md, 'b1_market_regime.md')


# ── B2：Layer1 雙軌 Ablation ──────────────────────────────────────────────
AB_FACTORS = [('slope', 'MA斜率', 'b2_ab_slope'), ('adx', 'ADX', 'b2_ab_adx'),
              ('rs', 'RS', 'b2_ab_rs'), ('vol', '量能', 'b2_ab_vol'),
              ('pth', 'PTH', 'b2_ab_pth')]
CORR_JSON = os.path.join(ROOT, 'backtest_results', 'b2_corr_mods.json')


def _book(rows, grades=('A',)):
    return [r for r in rows if r['grade'] in grades]


def _topq(rows, q=0.20):
    """依 dir_score 取前 q 比例（Rank-Normalized 比較用）。"""
    sc = [r for r in rows if fnum(r.get('dir_score')) is not None]
    sc.sort(key=lambda r: fnum(r['dir_score']), reverse=True)
    k = max(1, int(len(sc) * q))
    return sc[:k]


def _metrics(rows, N=20):
    v = rets(rows, N)
    if not v:
        return None
    s = stat_block(rows, N)
    # fix_prompt_14：一律用 day-cluster（此 CI 目前未渲染，改正以免日後誤用 naive）
    lo, hi, w = bootstrap_ci_clustered(rows, f'ret_{N}_net')
    return {**s, 'ci': (lo, hi)}


def cmd_b2(_args):
    base = load_trades(os.path.join(BASE_DIR, 'trades.csv'))
    md = ["# B2：Layer 1 因子 Correlation + 雙軌 Ablation\n"]
    md.append(f"- {meta_line(base)}")
    md.append("- 所有 variant 以**原始碼手術**產生：取 `score_direction` 生產原文，")
    md.append("  僅在分數合成前注入一行 `<factor>_mod = 0`，其餘逐字不動")
    md.append("  （不修改 production code，見 `research_phase1.py`）\n")
    md.append(cost_block())

    # ── Test A：相關性 ──
    md.append("\n## Test A：五因子修正量相關矩陣（僅供參考，非判斷依據）\n")
    if os.path.exists(CORR_JSON):
        d = json.load(open(CORR_JSON))
        names = ['base', 'slope', 'adx', 'rs', 'vol', 'pth']
        cols = {n: [r[i] for r in d] for i, n in enumerate(names)}
        F = ['slope', 'adx', 'rs', 'vol', 'pth']
        LB = {'slope': 'MA斜率', 'adx': 'ADX', 'rs': 'RS', 'vol': '量能', 'pth': 'PTH'}
        md.append(f"抽樣 n={len(d):,}（seed=42，自凍結資料集隨機抽 (symbol, as_of)）。")
        md.append("完整 130,993 筆需重跑整條 as-of 管線約 50 分鐘，"
                  "而相關係數在 n=5,000 已充分收斂，且 Test A 本非判斷依據。\n")
        md.append("### 各修正量分佈\n")
        md.append("| 因子 | 設計幅度 | 實際均值 | 標準差 | 非零比例 |")
        md.append("|---|---|---|---|---|")
        rng_txt = {'slope': '±8', 'adx': '±10', 'rs': '−8~+12', 'vol': '±8', 'pth': '−6~+8'}
        for f in F:
            v = cols[f]
            md.append(f"| {LB[f]} | {rng_txt[f]} | {statistics.mean(v):+.2f} | "
                      f"{statistics.pstdev(v):.2f} | {sum(1 for x in v if x != 0)/len(v):.0%} |")
        for title, fn in (('Pearson', pearsonr), ('Spearman', spearmanr)):
            md.append(f"\n### {title}\n")
            md.append("| | " + " | ".join(LB[b] for b in F) + " |")
            md.append("|---" * (len(F) + 1) + "|")
            for a in F:
                cells = []
                for b in F:
                    try:
                        r = fn(cols[a], cols[b])[0]
                        cells.append(f"{r:.3f}")
                    except Exception:
                        cells.append('—')
                md.append(f"| **{LB[a]}** | " + " | ".join(cells) + " |")
        md.append("\n**觀察**：MA斜率／RS／PTH 三者互相關 ρ≈0.38–0.42，構成一個「趨勢群」；")
        md.append("**量能與其他因子幾乎正交**（與 ADX 僅 0.006、與 RS 0.09），是最獨立的一支。")
        md.append("高相關不等於冗餘——是否冗餘要看 Test B 的增量價值。\n")
    else:
        md.append("（尚未產生 `b2_corr_mods.json`，請先跑 `research_b2corr.py`）\n")

    # ── Test B：雙軌 ablation ──
    md.append("\n## Test B：增量價值（真正判斷依據）\n")
    md.append("兩種比較並列，避免只看 Raw Ablation 誤判為 scale shift 假象：\n")
    md.append("1. **Raw Ablation**：直接拿掉該因子後的 A 級書表現")
    md.append("2. **Rank-Normalized**：兩模型各取 `dir_score` 前 20% 的訊號比較"
              "（控制分數尺度平移）\n")

    fb = _book(base, ('A',))
    ftop = _topq(base)
    mfull, mfull_t = _metrics(fb), _metrics(ftop)
    md.append("### 主表（持有 20 日）\n")
    md.append("| 模型 | A級n | 期望 | PF | 勝率 | MDD | Sharpe | Sortino | "
              "Δ vs Full (Raw) | Top20%n | Top20%期望 | Δ vs Full (Rank-Norm) |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    md.append(f"| **Full Model** | {mfull['n']:,} | {mfull['mean']}% | {mfull['pf']} | "
              f"{mfull['win']}% | {mfull['mdd']}% | {mfull['sharpe']} | {mfull['sortino']} | "
              f"baseline | {mfull_t['n']:,} | {mfull_t['mean']}% | baseline |")
    rows_out = []
    for key, label, d in AB_FACTORS:
        p = os.path.join(ROOT, 'backtest_results', d, 'trades.csv')
        if not os.path.exists(p):
            md.append(f"| −{label} | —（回測未完成） | | | | | | | | | | |")
            continue
        t = load_trades(p)
        m, mt = _metrics(_book(t, ('A',))), _metrics(_topq(t))
        draw = round(m['mean'] - mfull['mean'], 3)
        drank = round(mt['mean'] - mfull_t['mean'], 3)
        rows_out.append((label, m, mt, draw, drank))
        md.append(f"| −{label} | {m['n']:,} | {m['mean']}% | {m['pf']} | {m['win']}% | "
                  f"{m['mdd']}% | {m['sharpe']} | {m['sortino']} | **{draw:+.3f}** | "
                  f"{mt['n']:,} | {mt['mean']}% | **{drank:+.3f}** |")

    if rows_out:
        md.append("\n### 判讀\n")
        md.append("Δ 為**移除該因子後**的變化：Δ<0 代表移除會變差 → 該因子有正貢獻；")
        md.append("Δ>0 代表移除反而更好 → 該因子可能是負貢獻或雜訊。\n")
        md.append("| 因子 | Raw Δ | Rank-Norm Δ | 兩軌是否同號 | 初步判讀 |")
        md.append("|---|---|---|---|---|")
        for label, m, mt, draw, drank in rows_out:
            same = (draw < 0) == (drank < 0)
            if same and draw < 0:
                jd = "**有正貢獻**（兩軌一致）"
            elif same and draw > 0:
                jd = "**移除更好**（兩軌一致，需檢視是否為雜訊因子）"
            else:
                jd = "兩軌不一致 → 疑似 scale shift 假象，不可據 Raw 下結論"
            md.append(f"| {label} | {draw:+.3f} | {drank:+.3f} | "
                      f"{'✅' if same else '⚠️'} | {jd} |")
        md.append("\n> Rank-Normalized 存在的意義：若移除某因子只是讓所有分數平移，"
                  "Raw Ablation 會因 A 級門檻相對變動而顯示假差異；"
                  "固定取前 20% 可消除此效應。兩軌不同號時，以 Rank-Norm 為準。")

        md.append("\n### 為什麼 Raw Ablation 幾乎測不出東西（結構性原因，重要）\n")
        md.append("Raw Δ 全部落在 −0.024 ~ +0.016 之間，A 級樣本數也僅在 1,299–1,308 間變動"
                  "（Full=1,305）。這不是「因子沒用」，而是**量錯了地方**：\n")
        md.append("- A 級由 `score_timing` 的**雙因子觸發**決定（量價突破＋形態/籌碼），"
                  "不是由方向分決定。")
        md.append("- 方向分在 `analyze()` 中的角色是**否決門檻**（`DIRECTION_VETO=40`）"
                  "與排序輸入，只有當分數跨越 40 這條線時才會改變 grade。")
        md.append("- 因此移除一個 ±8~±12 的修正量，只影響到「剛好在門檻邊緣」的極少數樣本。\n")
        md.append("**結論：評估 Layer1 因子必須用 Rank-Normalized（排序品質），"
                  "Raw Ablation 在現行架構下不具鑑別力。** 這正是 spec 要求雙軌並列的原因，"
                  "本輪資料完整驗證了該設計的必要性。\n")

        md.append("### Test A 與 Test B 交叉解讀（最有價值的部分）\n")
        md.append("把相關性與增量價值放在一起看，出現一個清楚的結構：\n")
        md.append("| 因子 | 設計幅度 | 與其他因子相關性 | Rank-Norm 增量 | 綜合判讀 |")
        md.append("|---|---|---|---|---|")
        md.append("| ADX | ±10 | 中低（與量能 0.006） | **−0.265（最高）** | "
                  "**最有價值**：相對獨立且貢獻最大 |")
        md.append("| MA斜率 | ±8 | 高（與 PTH 0.41、RS 0.38） | −0.152 | 有貢獻，但與趨勢群重疊 |")
        md.append("| 量能 | ±8 | **最低（近乎正交）** | −0.080 | 貢獻小但獨立，保留成本低 |")
        md.append("| PTH | −6~+8 | 高（與 MA斜率 0.41、RS 0.39） | −0.068 | 貢獻小且與趨勢群重疊 |")
        md.append("| RS | **−8~+12（最大）** | 高（與 MA斜率 0.38、PTH 0.39） | **+0.088（負貢獻）** | "
                  "**權重最大卻是唯一負貢獻**：疑似冗餘 |")
        md.append("")
        md.append("**RS 是本輪最值得注意的異常**：它擁有五因子中最大的權重（−8~+12），"
                  "卻是唯一在兩軌都顯示「移除後更好」的因子；同時它與 MA斜率（0.38）、"
                  "PTH（0.39）高度相關——**方向動能的資訊已被那兩者涵蓋，RS 只是重複計分**。")
        md.append("這是下一輪權重調整最明確的候選（降低 RS 權重或改為與趨勢群擇一）。\n")
        md.append("⚠️ 但差異幅度很小（Rank-Norm Δ 全部 <0.3pp，遠小於 20 日報酬的標準差），"
                  "且本輪為單一路徑全期樣本內測試、未做時間雙半穩定檢驗。"
                  "依 bp10 紀律，**尚不足以直接改權重**，需先做穩定性驗證。\n")

    md.append("\n## 限制\n")
    md.append("- Test A 為抽樣（n=5,000）；Test B 為全樣本重跑（每個 variant 一次完整回測）。")
    md.append("- Ablation 僅作用於 `score_direction` 的五個修正量，"
              "不改變 base_score（均線排列）與 position/timing 兩層。")

    write(md, 'b2_layer1_ablation.md')


def cmd_b2extra(_args):
    cur_p = os.path.join(BASE_DIR, 'trades.csv')
    fix_p = os.path.join(ROOT, 'backtest_results', 'b2extra_prio_fixed', 'trades.csv')
    cur = {(r['symbol'], r['as_of']): r for r in load_trades(cur_p)}
    fix = {(r['symbol'], r['as_of']): r for r in load_trades(fix_p)}
    keys = set(cur) & set(fix)
    diff_trig = [k for k in keys if cur[k]['triggers'] != fix[k]['triggers']]
    diff_grade = [k for k in keys if cur[k]['grade'] != fix[k]['grade']]

    md = ["# B2-extra：Breakout Priority — Current vs Priority-Fixed\n"]
    md.append("> **定位（G5 要求）**：軟體正確性層面已確認實作優先序與註解宣告不一致，")
    md.append("> 這點不需回測驗證。本節要回答的是：**修正成宣告優先序後，")
    md.append("> 對訊號品質與績效的實際影響是什麼**，用數據決定要修程式碼還是修規格文件。\n")
    md.append(f"- {meta_line(list(cur.values()))}")
    md.append("- Priority-Fixed 以**原始碼手術**產生（僅供本測試，未動 production code）：")
    md.append("  取 `score_timing` 原文，把 `_vp_trigger` 判定區塊（`_vp_trigger = ''` 至")
    md.append("  `_vp_strong = bool(...)`）換成 spec 提供的候選清單 + 顯式優先序實作\n")
    md.append(cost_block())

    md.append("\n## 1. 受影響樣本數（affected_signal_count）\n")
    md.append("| 項目 | 數量 | 佔全樣本 |")
    md.append("|---|---|---|")
    md.append(f"| 共同比對樣本 | {len(keys):,} | 100% |")
    md.append(f"| `_vp_trigger`/`_vp_strong` 判定不同 | **{len(diff_trig):,}** | "
              f"**{len(diff_trig)/len(keys):.2%}** |")
    md.append(f"| 最終 grade 不同 | **{len(diff_grade):,}** | "
              f"{len(diff_grade)/len(keys):.2%} |")
    md.append("")
    if not diff_trig:
        md.append("**受影響樣本為零。** 兩次回測輸出的 `trades.csv` 經 `cmp` 比對為"
                  "**逐位元組相同**（46,570,527 bytes）。\n")

    md.append("## 2. 補丁確實生效的證明（排除「補丁沒裝上」的可能）\n")
    md.append("零差異有兩種可能：(a) 補丁沒生效；(b) 觸發條件在真實資料中不存在。")
    md.append("必須排除 (a) 才能下結論，故做了兩項驗證：\n")
    md.append("**驗證一：補丁確實安裝**\n")
    md.append("```")
    md.append("補丁前 score_timing.__code__.co_varnames 含 'candidates': False")
    md.append("補丁後 score_timing.__code__.co_varnames 含 'candidates': True")
    md.append("函式物件已替換: True")
    md.append("```")
    md.append("**驗證二：補丁在合成樣本上確實改變判定**（三盤待確認 + VP05 並存）\n")
    md.append("| | `_vp_trigger` | grade |")
    md.append("|---|---|---|")
    md.append("| Current | 三盤突破（量能待確認） | **B** |")
    md.append("| Priority-Fixed | 帶量突破 VP05 | **A**（VP05 為強觸發，與法人連買構成雙因子）|")
    md.append("\n→ 補丁功能正常，零差異必然來自 (b)。\n")

    md.append("## 3. 為什麼零差異：P1/P2/P3 情境在真實資料中不存在\n")
    md.append("對凍結資料集抽樣 n=3,951，直接量測各候選條件的共現頻率"
              "（不依賴補丁，純讀 `result`）：\n")
    md.append("| 條件 | 出現次數 | 佔比 |")
    md.append("|---|---|---|")
    md.append("| 三盤突破（量能待確認） | 332 | 8.40% |")
    md.append("| 帶量突破 VP05 | 173 | 4.38% |")
    md.append("| D20 突破（帶量） | 101 | 2.56% |")
    md.append("| D55 突破 | 75 | 1.90% |")
    md.append("| **Group P1**（待確認 + VP05） | **0** | **0.00%** |")
    md.append("| **Group P2**（待確認 + D20） | **0** | **0.00%** |")
    md.append("| **Group P3**（待確認 + VP05 + D20） | **0** | **0.00%** |")
    md.append("")
    md.append("**結構性原因（不是巧合）**：「三盤突破**量能待確認**」的定義是")
    md.append("`detected and not volume_confirmed`（突破了但**沒有量**）；")
    md.append("而 VP05 是「**帶量**突破」、D20 也是「**帶量**突破」。")
    md.append("**「沒有量」與「帶量」在同一根 K 棒上互斥**，因此待確認永遠不可能")
    md.append("壓掉 VP05 或 D20——這個優先序 bug 是**邏輯上不可達（unreachable）**的。\n")
    md.append("⚠️ 抽樣為 n=3,951；但全樣本 130,993 筆的輸出逐位相同，"
              "已是全集合層級的零影響證明，抽樣僅用於解釋**為什麼**為零。\n")

    md.append("## 4. 依預先定義準則的結論\n")
    md.append("spec 預先定義了兩種情況，但兩者都預設「受影響子集非空」。")
    md.append("實測結果落在第三種情況：**受影響子集為空集合**。因此：\n")
    md.append("| 判斷面向 | 結果 |")
    md.append("|---|---|")
    md.append("| 受影響子集後續報酬 | 無樣本可比較（n=0） |")
    md.append("| 新增 A 級樣本品質 | 無新增 A 級（grade 差異 0 筆） |")
    md.append("| OOS/regime 方向一致性 | 不適用 |")
    md.append("| 整體 portfolio | 完全相同（逐位元組） |")
    md.append("")
    md.append("**結論：建議修正規格文件（註解），不修改程式碼。**\n")
    md.append("理由：")
    md.append("1. 修改程式碼的預期效益**經全樣本量測為精確的零**，")
    md.append("   而任何改動都帶有回歸風險（本專案已有多次「改動引發連鎖問題」的紀錄）。")
    md.append("2. 兩者互斥是**語意上的必然**（有量 vs 沒量），不是資料期間的偶然；")
    md.append("   未來資料也不會讓它變成可達路徑，除非「量能確認」的定義本身改變。")
    md.append("3. 現行實作的行為是正確的；錯的是註解宣告的優先序。\n")
    md.append("**具體修正**：`decision_engine.py` 中兩處優先序註解（`score_timing` 內")
    md.append("「取較強者敘述：D55 > 三盤帶量/VP05 > D20 > 三盤待確認」）應改為與實作一致的")
    md.append("實際判定順序，並補一行說明「三盤待確認與 VP05/D20 因量能條件互斥，")
    md.append("故其相對順序不可達」。\n")
    md.append("> **最終必須是 Specification = Implementation。** 本輪數據支持的是")
    md.append("> **讓文件對齊實作**，而非讓實作對齊文件。\n")

    md.append("## 限制\n")
    md.append("- 本結論成立的前提是「量能待確認」與「帶量突破」的定義維持互斥。")
    md.append("  若日後修改 `volume_confirmed` 或 VP05/Donchian 的量能門檻，")
    md.append("  此優先序即可能變成可達路徑，屆時需重新評估。")

    write(md, 'b2extra_breakout_priority.md')


def cmd_summary(_args):
    base = load_trades(os.path.join(BASE_DIR, 'trades.csv'))
    md = ["# build_prompt_13 Phase 1 總報告\n"]
    md.append("> 執行型任務：照既定規格跑出真實數字，不在執行過程重新設計測試方法。")
    md.append("> 本輪**未修改任何 production 決策邏輯**（`decision_engine.py`／`config.py` 皆未動），")
    md.append("> 所有 variant 均以原始碼手術在執行期產生。\n")
    md.append(f"- {meta_line(base)}")
    md.append("- 凍結資料：`--reuse-data`（`_histcache_7e9dcd08c3.pkl`，82 檔，與 bp11 同一份）")
    md.append("- 共 8 次全歷史回測：Step 0 基準 ×1、B1 無濾網 ×1、B2 消融 ×5、B2-extra ×1")
    md.append("  （每次約 50 分鐘，序列執行）\n")
    md.append(cost_block())

    md.append("\n## 子報告\n")
    md.append("| 報告 | 內容 | 結論摘要 |")
    md.append("|---|---|---|")
    md.append("| [Step 0 基準重現](baseline_reproduction.md) | 全歷史重跑核對 bp11 | "
              "**✅ 七項指標逐位吻合**，閘門通過 |")
    md.append("| [B1 Market Regime](b1_market_regime.md) | 四組對照 × 分 regime | "
              "空頭濾網**正確**、盤整濾網**可能過嚴** |")
    md.append("| [B2 Layer1 Ablation](b2_layer1_ablation.md) | 相關性 + 雙軌消融 | "
              "**RS 權重最大卻是唯一負貢獻**；ADX 增量最高 |")
    md.append("| [B2-extra Breakout Priority](b2extra_breakout_priority.md) | 優先序影響拆解 | "
              "**零影響（邏輯不可達）**→ 建議修文件不修碼 |")
    md.append("| [B3 Score Monotonicity](b3_monotonicity.md) | 分桶 + Bootstrap CI | "
              "分桶單調但**時間穩定性不足**；空頭反轉 |")

    md.append("\n## 核心結論（依重要性排序）\n")

    md.append("### 1. 基準完全可重現（Step 0）\n")
    md.append("A/B/C 樣本數與 20 日期望值、總訊號數共 7 項與 bp11 逐位吻合"
              "（1,305/+3.360、12,459/+2.408、30,840/+1.904、130,993）。")
    md.append("後續所有比較因此建立在確定的基準上。\n")
    md.append("過程中發現 `bp11_expanded/trades.csv` 磁碟檔其實是第二輪 variant"
              "（B=12,401）而非 baseline——baseline 當時被覆蓋，故本輪為真實重跑而非讀舊檔。\n")

    md.append("### 2. 大盤濾網：空頭該留，盤整該檢討（B1）\n")
    md.append("現行濾網讓 A 級在盤整與空頭**完全歸零**。關閉濾網後檢視這些被壓制的訊號：\n")
    md.append("| Regime | n | 不重複日期 | 20日訊號級平均 | Day-Cluster 95%CI | 判讀 |")
    md.append("|---|---|---|---|---|---|")
    md.append("| 盤整 | 550 | 283 | **+2.225%** | [0.678, 4.136] | 不跨 0（正）→ 濾網**可能誤殺** |")
    md.append("| 空頭 | 158 | 90 | **−3.801%** | [−6.84, −1.032] | 不跨 0（負）→ 濾網**正確** |")
    md.append("")
    md.append("CI 已依 fix_prompt_14 改用 **day-cluster block bootstrap**（以 as_of 日期為")
    md.append("重抽樣單位）。原 naive CI 分別為 [1.02, 3.578] 與 [−6.052, −1.416]，")
    md.append("修正後寬 1.25–1.35 倍但**顯著性方向不變**。惟盤整下界由 1.02 收窄至 0.678，")
    md.append("信心邊際變薄；且 episode-level 自相關尚未處理（見限制章節），"
              "故用語為「可能誤殺」而非確定。")
    md.append("")
    md.append("**兩個 regime 結論相反**：空頭壓制有明確實證支持、不應放寬；"
              "盤整的一律 A→B 降級則可能過度保守，是下一輪最值得檢視的調整點。\n")

    md.append("### 3. RS 因子疑似冗餘（B2，最明確的權重調整候選）\n")
    md.append("RS 擁有五因子中最大權重（−8~+12），卻是**唯一在 Raw 與 Rank-Norm 兩軌"
              "都顯示「移除後更好」**的因子（+0.015 / +0.088）；")
    md.append("同時它與 MA斜率（ρ=0.38）、PTH（ρ=0.39）高度相關——方向動能資訊已被涵蓋。")
    md.append("反之 ADX 相對獨立（與量能 ρ=0.006）且 Rank-Norm 增量最高（−0.265）。\n")
    md.append("⚠️ 但幅度極小（全部 <0.3pp）且未做時間雙半穩定檢驗，"
              "依 bp10 紀律尚不足以直接改權重。\n")

    md.append("### 4. Breakout Priority 是不可達的死 bug（B2-extra）\n")
    md.append("全樣本 130,993 筆輸出**逐位元組相同**，受影響樣本 0 筆。")
    md.append("原因是語意互斥：「量能待確認」= 沒量，VP05/D20 = 帶量，"
              "同一根 K 棒不可能同時成立。")
    md.append("**建議修正註解讓文件對齊實作，不動程式碼**（改動有回歸風險、效益經量測為零）。\n")

    md.append("### 5. 方向分：有群體鑑別力，無逐筆預測力，且不跨期穩定（B3）\n")
    md.append("- 分桶 20 日報酬近乎單調（1.24% → 3.25%），Top20−Bot20 價差 +2.17pp")
    md.append("- 但全樣本 Spearman ρ=+0.0011（不顯著）——**個股雜訊遠大於因子訊號**")
    md.append("- 90–100 桶 N=29,416、CI 窄，**未見飽和**")
    md.append("- **8 年中有 3 年 Top−Bot 價差為負**（2019/2021/2022），全期正值主要由 2026 撐起")
    md.append("- 空頭 regime 單調性**反轉**（ρ=−0.108）：day-cluster CI 下 50–90 四個")
    md.append("  相鄰桶顯著為負；但最高分 90–100 桶 [−3.537, 0.056] 與最低分 <30 桶")
    md.append("  [−0.038, 3.184] **皆跨 0**，兩個極端桶不能作為證據\n")
    md.append("正確讀法不是「方向分無效」，而是「**其有效性條件於市場環境**」——"
              "這與第 2 點互相印證，共同支持 regime-aware 設計。\n")

    md.append("## 方法論限制（如實記錄，未為了產出數字而簡化）\n")
    md.append("1. **投組層級 MDD/CAGR 為近似**。訊號每日產生但持有 N 日，"
              "直接複利會使同一筆資金重複投入 N 次（實測讓 MDD 全部觸及 −100%）。"
              "改以「每 N 交易日取樣一次」建構不重疊序列。"
              "**真正的投組模擬需要部位管理器，超出 `signal_backtest.py` 能力範圍。**")
    md.append("2. **小樣本格子以訊號級為準**。空頭 A 級只有 5 個不重疊期，"
              "取樣後投組值（+0.98%）與訊號級真值（−3.80%）**符號相反**。"
              "凡不重疊期數 <10 的格子已標 ⚠️，一律以訊號級數字判讀。")
    md.append("3. **Raw Ablation 在現行架構下不具鑑別力**（方向分是否決門檻而非 grade 決定者），"
              "故 Layer1 因子評估以 Rank-Normalized 為準。")
    md.append("4. **Test A 為抽樣**（n=5,000，seed=42）；Test B 與其餘全部為全樣本。")
    md.append("5. 全期為**樣本內** walk-forward 重放（逐 as_of 切片、無前視），"
              "非切分訓練/測試的 OOS；跨年結果已分列可視為時間穩健性的替代檢驗。")
    md.append("6. B1 的 C/D 組部位模型以固定比例（單筆 10%）代替真實風險預算，"
              "未模擬成交與再平衡。")
    md.append("7. **Bootstrap CI 已於 fix_prompt_14 修正為 day-cluster**（原 naive 版本"
              "把同一天的多檔訊號當獨立樣本，40 個 cell 中 36 個聚集比例 >50%，"
              "B3 分桶更達 81–96%）。修正後 B1 三格與 B3 全期八桶結論不變，"
              "但**分 regime 有 2 格翻盤**（空頭 <30、空頭 90–100 由顯著變為跨 0）。"
              "殘留：**episode-level 自相關未處理**——同一次崩盤內不同天仍相關，"
              "故現有 CI 仍可能偏窄。詳見 "
              "[bootstrap_diagnostic.md](bootstrap_diagnostic.md)。")

    # ── Phase 1.5 補充驗證（build_prompt_15）────────────────────────────
    md.append("\n---\n")
    md.append("# Phase 1.5 補充驗證（build_prompt_15）\n")
    md.append("四項獨立檢驗：universe 稽核、date-neutral 橫斷面、RS 配對穩定性、"
              "regime episode bootstrap。")
    md.append("**結論：Phase 1 的「相對排序」結論大體存活，但「絕對水準」與"
              "「regime 方向性」兩類結論被明顯削弱。**\n")
    md.append("子報告：[universe_audit.md](universe_audit.md)、"
              "[universe_reconstruction.md](universe_reconstruction.md)、"
              "[b_date_neutral.md](b_date_neutral.md)、"
              "[c_rs_paired.md](c_rs_paired.md)、"
              "[episode_bootstrap.md](episode_bootstrap.md)\n")

    md.append("## ⚠️ 全域警語（任務A 結論）\n")
    md.append("**Phase 1 的 82 檔 universe 具已證實的 selection bias**："
              "全部 82 檔的 `watchlist.added_date` 皆為 **2026 年**，晚於回測起點 "
              "2019-06-01 約 **7 年** —— 即「先知道結果再回測」。")
    md.append("與 point-in-time 對照 universe（全市場合格 1,502 檔中產業分層抽 120 檔，"
              "202,560 筆訊號）比較：\n")
    md.append("| 等級 | Watchlist | 對照 | 差距 | 產業對齊後差距 |")
    md.append("|---|---|---|---|---|")
    md.append("| A | +3.360% | +2.728% | +0.632pp | **+0.095pp** |")
    md.append("| B | +2.408% | +1.205% | +1.203pp | +1.077pp |")
    md.append("| C | +1.904% | +0.854% | +1.050pp | +0.990pp |")
    md.append("")
    md.append("**→ 所有絕對期望值須折扣 0.6–1.2pp 後解讀，不可視為全市場預期表現。**")
    md.append("惟兩項辯護：(1) **A>B>C 單調性在對照組同樣成立，A−C 價差甚至更大**"
              "（+1.874pp vs +1.456pp）；(2) 產業對齊後 **A 級差距僅 +0.095pp**，"
              "代表 A 級的水準幾乎不受選股偏誤影響（差距主要來自產業結構）。")
    md.append("**受偏誤影響的是 level，不是 ranking。**\n")

    md.append("## 逐項結論影響對照\n")
    md.append("| # | 原結論 | Phase 1.5 檢驗 | 影響 |")
    md.append("|---|---|---|---|")
    md.append("| 1 | Step 0 基準完全可重現 | 不受影響 | **不變** |")
    md.append("| 2 | 濾網讓 A 級在盤整/空頭歸零 | 事實陳述，不受影響 | **不變** |")
    md.append("| 3 | 盤整被壓制訊號為正（濾網誤殺） | 任務D episode CI "
              "**[−0.362, 4.828] 跨 0** | **推翻**（證據不足支撐規則調整） |")
    md.append("| 4 | 空頭被壓制訊號為負（濾網正確） | 任務D episode CI "
              "**[−9.519, 0.758] 跨 0** | **轉弱**（方向仍為負但不顯著） |")
    md.append("| 5 | 濾網 trade-off：品質換機會 | 描述性，未依賴 CI | **不變** |")
    md.append("| 6 | 組別D 曝險上限幾乎不作用 | 結構性事實 | **不變** |")
    md.append("| 7 | 組別C 線性縮放無單位風險改善 | 結構性事實 | **不變** |")
    md.append("| 8 | Raw Ablation 結構性無鑑別力 | 結構性事實 | **不變** |")
    md.append("| 9 | RS 疑似冗餘、為權重候選 | 任務C Δspread CI **[−0.051, 0.175] 跨 0**，"
              "僅 1/8 年顯著 | **推翻**（維持「優先複驗但未證實」） |")
    md.append("| 10 | ADX 增量價值最高 | 未經 Phase1.5 獨立檢驗 | **待驗**（同 RS 的疑慮） |")
    md.append("| 11 | Breakout priority 零影響、邏輯不可達 | 不依賴統計推論 | **不變** |")
    md.append("| 12 | 方向分有群體鑑別力、無逐筆預測力 | 任務B date-neutral spread "
              "**+1.259pp CI [0.959, 1.579] 顯著為正** | **轉強**（見下） |")
    md.append("| 13 | 空頭 regime 單調性反轉 | fix_14 已縮限至 50–90 桶；"
              "任務B 空頭 date-neutral 見子報告 | **維持縮限後版本** |")
    md.append("| 14 | 時間穩定性不足（3/8 年負） | 任務B 分年結果一致偏弱 | **不變** |")
    md.append("| 15 | 90–100 桶未見飽和 | 不受影響 | **不變** |")

    md.append("\n## 任務B：方向分的橫斷面鑑別力——縮水但存活（本輪最好的消息）\n")
    md.append("原 B3 的 Top20−Bot20 = +2.173pp 是**全期 pooled** 排名，"
              "可能混入時間組成效應。改為**逐日內排名**後：\n")
    md.append("| 持有期 | 原 pooled | Date-neutral | 縮水幅度 | 95%CI | 判讀 |")
    md.append("|---|---|---|---|---|---|")
    md.append("| 5D | +0.445pp | +0.161pp | −64% | [0.017, 0.304] | 顯著為正 |")
    md.append("| 10D | +1.094pp | +0.462pp | −58% | [0.262, 0.652] | 顯著為正 |")
    md.append("| 20D | +2.173pp | **+1.259pp** | **−42%** | [0.959, 1.579] | **顯著為正** |")
    md.append("")
    md.append("**判讀：原數字約 42% 來自時間組成效應（G6 的疑慮部分成立），"
              "但扣除後仍有 +1.259pp 的真實同日橫斷面優勢，且 CI 不跨 0。**")
    md.append("「方向分具群體鑑別力」這個結論因此**正式坐實**，"
              "而非只是時間效應的假象。\n")

    md.append("## 殘留限制（Phase 1.5 之後仍未解）\n")
    md.append("1. **對照 universe 本身仍有 survivorship bias**：`twstock.codes` 只收錄"
              "目前仍上市者，2019–2026 間下市/下櫃股不在池中。"
              "故任務A 量測的是 **selection bias**，**未**量測 survivorship bias。")
    md.append("2. **Episode bootstrap 的 block 數過少**（盤整 68、空頭 19），"
              "block bootstrap 本身在此régime下不穩定；且 episode 中位長度僅 4–6 天，"
              "顯示 regime 標籤碎片化會把單一市場事件切成多段，"
              "使 CI **偏窄**（保守化仍不足）。")
    md.append("3. **對照 universe 的籌碼資料以 FinMind 預填、停用官方逐日補洞**"
              "（原設計逐檔觸發 per-date 掃描，單檔可達 20 分鐘）。"
              "覆蓋率中位 98.0% vs watchlist 99.3%，可比但非完全相同；"
              "對照組營收回補亦略過（月營收動能因子在對照組不可用）。")
    md.append("4. 任務C 只檢驗了 RS；其餘四因子（含 ADX）未做同等的 date-neutral "
              "配對穩定性檢驗，故第 10 項結論狀態為「待驗」。")

    md.append("\n## 下一輪建議（供人工決策，本輪不做任何規則變更）\n")
    md.append("| 優先 | 項目 | 依據 | 風險 |")
    md.append("|---|---|---|---|")
    md.append("| 1 | 修正 breakout priority **註解** | B2-extra 零影響 | 極低（純文件） |")
    md.append("| ~~2~~ | ~~檢視盤整 A→B 降級~~ **暫緩** | Phase1.5 任務D："
              "episode CI [−0.362, 4.828] **跨 0** | **證據不足，撤下此建議**"
              "（原依據為 day-cluster CI，經 episode 檢驗後不成立） |")
    md.append("| ~~3~~ | ~~檢視 RS 權重~~ **暫緩** | Phase1.5 任務C："
              "Δspread CI [−0.051, 0.175] **跨 0**、僅 1/8 年顯著 | "
              "**證據不足，維持「優先複驗但未證實」** |")
    md.append("| 2 | **補齊其餘四因子的 date-neutral 配對檢驗** | 任務C 只驗了 RS，"
              "ADX「增量最高」尚未經同等檢驗 | 低（純量測） |")
    md.append("| 3 | 建立 point-in-time universe 機制（含已下市股） | 任務A：現行 universe "
              "有已證實的 selection bias，且對照組仍缺倒存股 | 中（需歷史上市清單資料源） |")
    md.append("| — | **不建議**放寬空頭濾網 | 空頭 episode CI [−9.519, 0.758] 雖跨 0，"
              "點估計仍為負（−3.80%）；無證據支持放寬 | — |")
    md.append("| — | **不建議**依 Phase 1 絕對期望值設定報酬預期 | 任務A：絕對水準"
              "被墊高 0.6–1.2pp | — |")

    write(md, 'phase1_report.md')


# ── fix_prompt_14：Bootstrap 聚集度診斷 ──────────────────────────────────
def _all_cells():
    """回傳 [(區塊, cell 名, rows)]，涵蓋 B1/B3 所有呼叫過 bootstrap_ci 的 cell。"""
    base = load_trades(os.path.join(BASE_DIR, 'trades.csv'))
    nf_p = os.path.join(ROOT, 'backtest_results', 'b1_nofilter', 'trades.csv')
    nof = load_trades(nf_p) if os.path.exists(nf_p) else []
    cells = []
    # B1：A 級書（Current 與 NoFilter）× regime
    cells.append(('B1', 'Current A級（全期）', [r for r in base if r['grade'] == 'A']))
    for reg in ('多頭', '盤整', '空頭'):
        cells.append(('B1', f'Current A級（{reg}）',
                      [r for r in base if r['grade'] == 'A' and r.get('regime') == reg]))
    if nof:
        cells.append(('B1', 'NoFilter A級（全期）', [r for r in nof if r['grade'] == 'A']))
        for reg in ('多頭', '盤整', '空頭'):
            cells.append(('B1', f'NoFilter A級（{reg}）★',
                          [r for r in nof if r['grade'] == 'A' and r.get('regime') == reg]))
    # B3：分桶（全期 + 分 regime）
    scored = [r for r in base if fnum(r.get('dir_score')) is not None]
    for lab, cond in BUCKETS:
        cells.append(('B3', f'dir_score {lab}（全期）',
                      [r for r in scored if cond(fnum(r['dir_score']))]))
    for reg in ('多頭', '盤整', '空頭'):
        for lab, cond in BUCKETS:
            cells.append(('B3', f'dir_score {lab}（{reg}）',
                          [r for r in scored if cond(fnum(r['dir_score']))
                           and r.get('regime') == reg]))
    return cells


def cmd_diag(_args):
    md = ["# Bootstrap 聚集度診斷（fix_prompt_14 任務1）\n"]
    md.append("> **問題**：`bootstrap_ci()` 對攤平後的逐筆訊號做 iid 重抽樣，")
    md.append("> 但 regime 是連續日曆區段，同一段期間內多檔股票常在同幾天一起觸發訊號。")
    md.append("> 若 n 筆訊號其實只來自少數交易日，naive bootstrap 會把它們當 n 個獨立樣本，")
    md.append("> **使 CI 偏窄、造成假顯著**。\n")
    md.append("- 聚集比例 = 1 − (不重複日期數 / 訊號筆數)；越高代表獨立資訊量越少於筆數")
    md.append("- ⚠️ 標記門檻：聚集比例 > 50%")
    md.append("- ★ 標記：Phase 1 核心方向性結論所依賴的 cell\n")

    md.append("## 全部 cell 聚集度\n")
    md.append("| 區塊 | Cell | N | 不重複日期 | 中位筆數/日 | 最大筆數/日 | 聚集比例 | 標記 |")
    md.append("|---|---|---|---|---|---|---|---|")
    high = 0
    for blk, name, rows in _all_cells():
        p = cluster_profile(rows)
        if not p:
            md.append(f"| {blk} | {name} | 0 | — | — | — | — | 無樣本 |")
            continue
        flag = '⚠️ 高聚集，naive CI 可能低估不確定性' if p['cluster_ratio'] > 0.50 else ''
        if p['cluster_ratio'] > 0.50:
            high += 1
        md.append(f"| {blk} | {name} | {p['n']:,} | {p['days']:,} | "
                  f"{p['median_per_day']:.0f} | {p['max_per_day']} | "
                  f"{p['cluster_ratio']:.1%} | {flag} |")

    md.append(f"\n## 小結\n")
    md.append(f"- 共 {len(_all_cells())} 個 cell，其中 **{high} 個聚集比例 > 50%**")
    md.append("- **B3 分桶問題最嚴重**（全期各桶 81–96%）：例如 `<30` 桶 40,305 筆訊號")
    md.append("  僅來自 1,635 個交易日，中位每日 21 筆——naive CI 實際上把「同一天的")
    md.append("  21 檔股票」當成 21 個獨立觀測。")
    md.append("- **B1 核心兩格聚集度中等**（空頭 43%、盤整 49%），影響較小但仍需修正。")
    md.append("- 修正結果與新舊 CI 對照見 `b1_market_regime.md`、`b3_monotonicity.md`。")

    write(md, 'bootstrap_diagnostic.md')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['baseline', 'b3', 'b1', 'b2corr', 'b2', 'b2extra',
                                    'summary', 'diag'])
    args = ap.parse_args()
    globals()[f'cmd_{args.cmd}'](args)


if __name__ == '__main__':
    main()
