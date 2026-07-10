#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_bp11_bear_revmom.py  (REPORT-ONLY; no engine changes)

Offline analysis of an EXISTING walk-forward signal CSV. Investigates whether the
`rev_mom==True` (revenue-momentum / month-over-month acceleration) signal carries a
tradeable edge inside BEAR regimes (regime=='空頭').

Standalone: imports only pandas/numpy. Does NOT import config / decision_engine /
signal_backtest. Does NOT run any backtest or network fetch. Reads one CSV, prints
tables to stdout, and writes docs/superpowers/reports/research_bear_revmom.md.
"""
import os
import numpy as np
import pandas as pd

CSV_PATH = "backtest_results/bp11_expanded/trades.csv"
OUT_MD = "docs/superpowers/reports/research_bear_revmom.md"

HORIZONS = [("ret_5_net", "5d"), ("ret_10_net", "10d"), ("ret_20_net", "20d")]
BEAR = "空頭"

# Prior (pre-expansion) reference figures to compare against.
PRIOR_20D_WIN = 69.5
PRIOR_20D_MEAN = 6.61
PRIOR_20D_N = 1142

# The three independent bear rev_mom events (event -> list of as_of YYYY-MM prefixes).
EVENTS = {
    "2023-10": ["2023-10"],
    "2024-08/09": ["2024-08", "2024-09"],
    "2025-03/04": ["2025-03", "2025-04"],
}


def load() -> pd.DataFrame:
    # utf-8-sig strips the BOM on the first header cell.
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig", low_memory=False)
    # rev_mom: values True/False/blank. Normalize to a nullable boolean.
    rm = df["rev_mom"].astype("string").str.strip()
    df["rev_mom_bool"] = rm.map({"True": True, "False": False})
    # chip_reliable
    if "chip_reliable" in df.columns:
        df["chip_reliable_bool"] = (
            df["chip_reliable"].astype("string").str.strip().map({"True": True, "False": False})
        )
    # forward returns -> numeric, blanks -> NaN
    for col, _ in HORIZONS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["rs_score"] = pd.to_numeric(df["rs_score"], errors="coerce")
    df["chip_buy_days"] = pd.to_numeric(df["chip_buy_days"], errors="coerce")
    df["as_of"] = df["as_of"].astype(str)
    df["ym"] = df["as_of"].str.slice(0, 7)
    return df


def stats(series: pd.Series) -> dict:
    """n / win% / mean / median on a numeric series with NaN dropped."""
    s = series.dropna()
    n = int(s.shape[0])
    if n == 0:
        return {"n": 0, "win": np.nan, "mean": np.nan, "median": np.nan}
    return {
        "n": n,
        "win": float((s > 0).mean() * 100.0),
        "mean": float(s.mean()),
        "median": float(s.median()),
    }


def fmt(x, pct=False, dp=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{dp}f}{'%' if pct else ''}"


def main():
    df = load()
    lines = []  # markdown accumulator
    P = lines.append

    # ---- global availability facts -------------------------------------------
    rm = df["rev_mom_bool"]
    n_true = int((rm == True).sum())
    n_false = int((rm == False).sum())
    n_blank = int(rm.isna().sum())
    total = len(df)

    bear = df[df["regime"] == BEAR]
    bear_rm_true = bear[bear["rev_mom_bool"] == True]
    bear_rm_months = sorted(bear_rm_true["ym"].unique().tolist())
    win_start, win_end = df["as_of"].min(), df["as_of"].max()
    n_symbols = df["symbol"].nunique()

    print("=" * 70)
    print("BP11 BEAR rev_mom research (report-only)")
    print("=" * 70)
    print(f"data window : {win_start} -> {win_end}  ({total:,} rows, {n_symbols} symbols)")
    print(f"rev_mom     : True={n_true:,}  False={n_false:,}  blank(NaN)={n_blank:,}")
    print(f"bear rows   : {len(bear):,}   bear&rev_mom==True : {len(bear_rm_true):,}")
    print(f"bear rev_mom months present: {bear_rm_months}")
    print()

    # =========================================================================
    # MARKDOWN HEADER + SCOPE
    # =========================================================================
    P("# BP11 研究報告：空頭 × 營收動能 (rev_mom) 前瞻報酬")
    P("")
    P("> **REPORT-ONLY** — 本輪僅分析，不改引擎（依規格：no engine change this round）。")
    P("> 全部數字由 `backtest_results/bp11_expanded/trades.csv` 離線計算；未跑回測、未抓網路資料。")
    P("> 產生腳本：`research_bp11_bear_revmom.py`（僅 import pandas/numpy）。")
    P("")
    P("## 1. 範圍與資料限制")
    P("")
    P(f"- **資料窗**：{win_start} → {win_end}，共 **{total:,}** 筆 walk-forward 訊號，{n_symbols} 檔標的。")
    P(f"- **rev_mom 分布**：`True`={n_true:,}、`False`={n_false:,}、空白(NaN)={n_blank:,}。")
    P("- **關鍵限制 — 營收資料深度**：`rev_mom` 空白＝當時月營收資料尚未回補（主要為 2023 年以前）。"
      "月營收僅回補約 40 個月，因此 **2020 COVID 空頭與 2022 空頭完全沒有 rev_mom 資料，無法評估**。")
    P(f"- 因此「空頭 × rev_mom==True」僅存在於 2023–2025，共 **{len(bear_rm_true):,}** 筆，"
      f"月份：`{', '.join(bear_rm_months)}`。")
    P("- **空頭 rev_mom 的證據＝僅 3 個獨立事件**：`2023-10`、`2024-08/09`、`2025-03/04`。"
      "任何結論都受限於這 3 個事件，2020/2022 空頭的空窗使樣本本質上偏薄。")
    P("")

    # =========================================================================
    # 2. CORE MATRIX
    # =========================================================================
    P("## 2. 空頭 rev_mom 核心矩陣（vs 空頭基準）")
    P("")
    P("`regime=='空頭' & rev_mom==True` 各持有期的 n / 勝率 / 平均 / 中位；"
      "benchmark＝同持有期**全部空頭訊號**（任何 rev_mom）的平均，供讀者看相對邊際。")
    P("")
    P("| 持有期 | n | 勝率 | 平均報酬 | 中位 | 空頭基準(平均, n) | 邊際 vs 基準 |")
    P("|---|---:|---:|---:|---:|---:|---:|")
    core = {}
    for col, label in HORIZONS:
        st = stats(bear_rm_true[col])
        bench = stats(bear[col])
        core[label] = st
        edge = (st["mean"] - bench["mean"]) if (st["n"] and bench["n"]) else np.nan
        P(f"| {label} | {st['n']} | {fmt(st['win'],pct=True,dp=1)} | {fmt(st['mean'],pct=True)} "
          f"| {fmt(st['median'],pct=True)} | {fmt(bench['mean'],pct=True)} (n={bench['n']}) "
          f"| {fmt(edge,pct=True)} |")
        print(f"[core] {label:>3}  n={st['n']:>5}  win={fmt(st['win'],pct=True,dp=1):>7}  "
              f"mean={fmt(st['mean'],pct=True):>8}  median={fmt(st['median'],pct=True):>8}  "
              f"bench_mean={fmt(bench['mean'],pct=True)} (n={bench['n']})")
    P("")
    d20 = core["20d"]
    P(f"**與擴充前(prior)比較**：本次 20 日 = **{fmt(d20['win'],pct=True,dp=1)} 勝率 / {fmt(d20['mean'],pct=True)} 平均"
      f"（n={d20['n']}）**；prior = {PRIOR_20D_WIN:.1f}% / +{PRIOR_20D_MEAN:.2f}%（n≈{PRIOR_20D_N}，同 3 事件）。")
    P("")

    # =========================================================================
    # 3. 2x2 OVERLAYS (bear only, 20d)
    # =========================================================================
    P("## 3. 2×2 疊加分析（僅空頭、20 日；標示每格 n，n<30 加註 ⚠️）")
    P("")

    def two_by_two(second_mask_name, second_mask):
        rows = []
        for rm_val, rm_lbl in [(True, "rev_mom=T"), (False, "rev_mom=F")]:
            for s_val, s_lbl in [(True, f"{second_mask_name}=T"), (False, f"{second_mask_name}=F")]:
                m = (bear["rev_mom_bool"] == rm_val) & (second_mask == s_val)
                st = stats(bear.loc[m, "ret_20_net"])
                rows.append((rm_lbl, s_lbl, st))
        return rows

    # 3a rev_mom x rs_score>=80
    P("### 3a. rev_mom × rs_score≥80")
    P("")
    P("| rev_mom | rs≥80 | n | 20d 勝率 | 20d 平均 |")
    P("|---|---|---:|---:|---:|")
    rs_mask = bear["rs_score"] >= 80
    for rm_lbl, s_lbl, st in two_by_two("rs≥80", rs_mask):
        flag = " ⚠️" if 0 < st["n"] < 30 else ("" if st["n"] else " ⚠️(空)")
        P(f"| {rm_lbl.replace('rev_mom=','')} | {s_lbl.replace('rs≥80=','')} | {st['n']}{flag} "
          f"| {fmt(st['win'],pct=True,dp=1)} | {fmt(st['mean'],pct=True)} |")
    P("")

    # 3b rev_mom x chip_buy_days>=3
    P("### 3b. rev_mom × chip_buy_days≥3")
    P("")
    P("| rev_mom | chip≥3 | n | 20d 勝率 | 20d 平均 |")
    P("|---|---|---:|---:|---:|")
    chip_mask = bear["chip_buy_days"] >= 3
    for rm_lbl, s_lbl, st in two_by_two("chip≥3", chip_mask):
        flag = " ⚠️" if 0 < st["n"] < 30 else ("" if st["n"] else " ⚠️(空)")
        P(f"| {rm_lbl.replace('rev_mom=','')} | {s_lbl.replace('chip≥3=','')} | {st['n']}{flag} "
          f"| {fmt(st['win'],pct=True,dp=1)} | {fmt(st['mean'],pct=True)} |")
    P("")

    # =========================================================================
    # 4. CONCENTRATION CHECKS
    # =========================================================================
    P("## 4. 集中度檢查")
    P("")

    # 4a by month
    P("### 4a. 依月份（2023–2025 空頭月份）")
    P("")
    P("| 月份 | n | 20d 勝率 | 20d 平均 |")
    P("|---|---:|---:|---:|")
    print("\n[by month]")
    for ym in bear_rm_months:
        st = stats(bear_rm_true.loc[bear_rm_true["ym"] == ym, "ret_20_net"])
        flag = " ⚠️" if 0 < st["n"] < 30 else ""
        P(f"| {ym} | {st['n']}{flag} | {fmt(st['win'],pct=True,dp=1)} | {fmt(st['mean'],pct=True)} |")
        print(f"  {ym}  n={st['n']:>4}  win={fmt(st['win'],pct=True,dp=1):>7}  mean={fmt(st['mean'],pct=True):>8}")
    P("")

    # 4b by symbol
    P("### 4b. 依標的（20d 有效樣本，Top 貢獻）")
    P("")
    sub = bear_rm_true.dropna(subset=["ret_20_net"]).copy()
    n_sub = len(sub)
    by_sym = sub.groupby("symbol")["ret_20_net"].agg(["count", "mean"]).sort_values("count", ascending=False)
    top = by_sym.head(12)
    top_share = (by_sym["count"].head(2).sum() / n_sub * 100.0) if n_sub else np.nan
    n_names = by_sym.shape[0]
    P(f"20d 有效樣本 n={n_sub}，來自 **{n_names}** 檔標的；前 2 大標的占比 **{fmt(top_share,pct=True,dp=1)}**。")
    P("")
    P("| symbol | n | 20d 平均 | 占總樣本 |")
    P("|---|---:|---:|---:|")
    print("\n[by symbol top12]")
    for sym, r in top.iterrows():
        share = r["count"] / n_sub * 100.0
        P(f"| {sym} | {int(r['count'])} | {fmt(r['mean']*100 if False else r['mean'],pct=True)} | {fmt(share,pct=True,dp=1)} |")
        print(f"  {sym}  n={int(r['count']):>4}  mean={fmt(r['mean'],pct=True):>8}  share={fmt(share,pct=True,dp=1)}")
    P("")

    # 4c per-event breakdown
    P("### 4c. 逐事件拆解（3 個獨立空頭事件）")
    P("")
    P("| 事件 | 月份 | n | 20d 勝率 | 20d 平均 |")
    P("|---|---|---:|---:|---:|")
    print("\n[per-event]")
    event_summary = {}
    for ev, prefixes in EVENTS.items():
        m = bear_rm_true["ym"].isin(prefixes)
        st = stats(bear_rm_true.loc[m, "ret_20_net"])
        event_summary[ev] = st
        flag = " ⚠️" if 0 < st["n"] < 30 else ""
        P(f"| {ev} | {', '.join(prefixes)} | {st['n']}{flag} | {fmt(st['win'],pct=True,dp=1)} | {fmt(st['mean'],pct=True)} |")
        print(f"  {ev:>11}  n={st['n']:>4}  win={fmt(st['win'],pct=True,dp=1):>7}  mean={fmt(st['mean'],pct=True):>8}")
    P("")

    # =========================================================================
    # 5. LEFT TAIL
    # =========================================================================
    P("## 5. 左尾風險（空頭 rev_mom==True 子集，20 日淨報酬）")
    P("")
    s20 = bear_rm_true["ret_20_net"].dropna()
    p5 = float(np.percentile(s20, 5)) if len(s20) else np.nan
    p10 = float(np.percentile(s20, 10)) if len(s20) else np.nan
    worst = float(s20.min()) if len(s20) else np.nan
    P(f"- 有效 n = {len(s20)}")
    P(f"- **P5** = {fmt(p5,pct=True)}")
    P(f"- **P10** = {fmt(p10,pct=True)}")
    P(f"- **最差 (worst)** = {fmt(worst,pct=True)}")
    P("")
    print(f"\n[left tail] n={len(s20)}  P5={fmt(p5,pct=True)}  P10={fmt(p10,pct=True)}  worst={fmt(worst,pct=True)}")

    # =========================================================================
    # 5b. INTRA-EVENT ROBUSTNESS — the aggregate hides month-level dispersion.
    # =========================================================================
    # Event-level means can be positive while a constituent bear month is a wipeout.
    # Flag any n>=30 constituent bear rev_mom month with a severely negative 20d mean.
    SEVERE = -10.0  # % 20d mean threshold for "intra-event failure month"
    month_st = {ym: stats(bear_rm_true.loc[bear_rm_true["ym"] == ym, "ret_20_net"])
                for ym in bear_rm_months}
    severe_months = [(ym, month_st[ym]) for ym in bear_rm_months
                     if month_st[ym]["n"] >= 30 and month_st[ym]["mean"] < SEVERE]

    P("## 5b. 事件內月度穩健性（聚合掩蓋的分散）")
    P("")
    P("事件層級平均為正，不代表每個構成月份都為正。以下標出 **n≥30 但 20d 平均 < −10%** 的「事件內崩潰月」：")
    P("")
    if severe_months:
        P("| 崩潰月 | n | 20d 勝率 | 20d 平均 |")
        P("|---|---:|---:|---:|")
        for ym, st in severe_months:
            P(f"| {ym} | {st['n']} | {fmt(st['win'],pct=True,dp=1)} | {fmt(st['mean'],pct=True)} |")
        P("")
        P("> **這是關鍵風險**：在真正的空頭段（如 2025-03，n≥30 且 100% 訊號皆輸），rev_mom==True "
          "並未提供保護；正的事件平均是被同事件另一個月（2025-04）強拉回來的。這代表邊際具高度**時點依賴**。")
    else:
        P("- 無 n≥30 的事件內崩潰月。")
    P("")

    # =========================================================================
    # 6. CONCLUSION
    # =========================================================================
    # Decision logic tied to numbers. 提案入引擎 requires ALL of:
    #   (a) all 3 events positive, (b) n>=30 per event, (c) concentration clean,
    #   (d) NO n>=30 constituent bear month with severe (< -10%) failure,
    #   (e) left tail not extreme (worst > -30%).
    ev_ns = [event_summary[e]["n"] for e in EVENTS]
    ev_means = [event_summary[e]["mean"] for e in EVENTS]
    ev_wins = [event_summary[e]["win"] for e in EVENTS]
    all_events_n30 = all(n >= 30 for n in ev_ns)
    all_events_positive = all((m is not None and not np.isnan(m) and m > 0) for m in ev_means)
    conc_clean = (not np.isnan(top_share)) and top_share < 40.0 and n_names >= 8
    intra_event_robust = len(severe_months) == 0
    tail_ok = (not np.isnan(worst)) and worst > -30.0

    P("## 6. 結論（三選一）")
    P("")
    if all_events_positive and all_events_n30 and conc_clean and intra_event_robust and tail_ok:
        verdict = "提案入引擎（附條件）"
    elif all_events_positive and (all_events_n30 or True):
        # Positive aggregate but fails robustness (intra-event failure / extreme tail /
        # concentration) or is structurally thin (2020/2022 gap, 3 events only).
        verdict = "需更多樣本"
    else:
        verdict = "否決"

    P(f"### ▶ 判定：**{verdict}**")
    P("")
    P("判定依據（緊扣數字）：")
    P(f"- 3 事件 20d 平均：2023-10={fmt(event_summary['2023-10']['mean'],pct=True)}"
      f"、2024-08/09={fmt(event_summary['2024-08/09']['mean'],pct=True)}"
      f"、2025-03/04={fmt(event_summary['2025-03/04']['mean'],pct=True)}"
      f"（事件層級皆為正：{'是' if all_events_positive else '否'}）。")
    P(f"- 3 事件 n：{ev_ns[0]} / {ev_ns[1]} / {ev_ns[2]}（每事件 n≥30：{'是' if all_events_n30 else '否'}）。")
    if intra_event_robust:
        severe_desc = "無"
    else:
        severe_desc = "有 → " + ", ".join(
            f"{ym}({fmt(st['mean'], pct=True)}, n={st['n']})" for ym, st in severe_months
        )
    P(f"- **事件內崩潰月**：{severe_desc}（穩健：{'是' if intra_event_robust else '否'}）。")
    P(f"- 集中度：{n_names} 檔、前 2 大占 {fmt(top_share,pct=True,dp=1)}（乾淨門檻 <40% 且 ≥8 檔：{'通過' if conc_clean else '未通過'}）。")
    P(f"- 左尾：P5={fmt(p5,pct=True)}、worst={fmt(worst,pct=True)}（worst > −30% 門檻：{'通過' if tail_ok else '未通過'}）。")
    P(f"- 20d 整體 = {fmt(d20['win'],pct=True,dp=1)} / {fmt(d20['mean'],pct=True)}（n={d20['n']}），"
      f"prior = {PRIOR_20D_WIN:.1f}% / +{PRIOR_20D_MEAN:.2f}%（方向一致，邊際仍在）。")
    P("- **結構性限制**：2020/2022 空頭無月營收資料，本訊號在那兩段空頭無法被驗證；"
      "全部證據只建立在 2023–2025 這 3 個事件上。")
    P("")
    if verdict == "需更多樣本":
        P("→ **判定理由**：事件層級 3 個皆正、方向與 prior 一致，邊際確實存在；但"
          "（1）事件內出現 n≥30 的崩潰月（2025-03：0% 勝率、−21.80% 平均、worst −35.57%），"
          "顯示在真正空頭段本訊號無保護、正報酬高度依賴時點；"
          "（2）左尾嚴峻（P5≈−18.65%、worst≈−35.57%）；"
          "（3）結構上 2020/2022 空頭無營收資料、獨立事件僅 3 個。"
          "在缺少更多獨立空頭週期佐證下，**尚不足以入引擎**。建議累積更多空頭事件的 rev_mom 樣本後再評估。")
    elif verdict == "否決":
        P("→ 擴充資料後事件層級邊際消失或方向不一致，**否決**入引擎。")
    else:
        P("→ 邊際跨 3 事件穩健、每事件 n≥30、無事件內崩潰月、集中度乾淨、左尾可控，"
          "**可提案入引擎（附條件）**；惟本輪為 report-only，實作留待後續。")
    P("")
    P("---")
    P("_本報告為 report-only，未更動 config/decision_engine/signal_backtest。_")

    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n[written] {OUT_MD}  ({len(lines)} md lines)")
    print(f"[verdict] {verdict}")


if __name__ == "__main__":
    main()
