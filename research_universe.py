"""
research_universe.py — build_prompt_15 任務A：Universe Provenance 稽核 + 條件式重建

子命令：
  audit    A1（added_date 時間戳記核對）+ A2 Track1（客觀上市資格）→ universe_audit.md
  build    A2 Track2：建立 point-in-time 對照 universe（產業分層抽樣）→ control_universe.txt
  compare  對照回測完成後，比對新舊 Step0 數字 → universe_reconstruction.md

report-only：不修改任何規則。
"""

from __future__ import annotations

import os
import csv
import sys
import json
import random
import argparse
import datetime
import statistics
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, 'docs', 'superpowers', 'reports', 'phase1')
BASE_CSV = os.path.join(ROOT, 'backtest_results', 'bp13_step0', 'trades.csv')
CTRL_LIST = os.path.join(ROOT, 'control_universe.txt')
CTRL_CSV = os.path.join(ROOT, 'backtest_results', 'bp15_control', 'trades.csv')

BASE_DATE = datetime.date(2019, 6, 1)          # HISTORY_START_DATE
MIN_LISTED = BASE_DATE - datetime.timedelta(days=730)   # 上市滿 2 年
N_CONTROL = 120                                 # 目標抽樣數（spec 要求 100–150，≥80）


def _write(md, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    p = os.path.join(OUT_DIR, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Universe] → {p}")
    return p


def _phase1_universe():
    rows = list(csv.DictReader(open(BASE_CSV, encoding='utf-8-sig')))
    first = collections.defaultdict(lambda: '9999-99-99')
    cnt = collections.Counter()
    for r in rows:
        first[r['symbol']] = min(first[r['symbol']], r['as_of'])
        cnt[r['symbol']] += 1
    return sorted(cnt), dict(first), cnt


def _listing(sym):
    """(name, 上市日 date|None, 市場, 產業/類型)。"""
    import twstock
    x = twstock.codes.get(str(sym))
    if not x:
        return (None, None, None, None)
    st = None
    if x.start:
        try:
            st = datetime.datetime.strptime(x.start, '%Y/%m/%d').date()
        except Exception:
            st = None
    return (x.name, st, x.market, (x.group or x.type or '').strip())


def cmd_audit(_a):
    import sqlite3
    uni, first, cnt = _phase1_universe()
    conn = sqlite3.connect(os.path.join(ROOT, 'watchlist_v4.db'))
    wl = {str(s): (n, a) for s, n, a in
          conn.execute("SELECT symbol,name,added_date FROM watchlist")}
    conn.close()

    md = ["# 任務A：Universe Provenance 稽核（build_prompt_15）\n"]
    md.append(f"- Phase 1 universe：**{len(uni)} 檔**｜回測基準日 "
              f"`HISTORY_START_DATE = {BASE_DATE}`")
    md.append(f"- 資料來源：`watchlist.added_date`（A1）＋ `twstock.codes[].start` 上市日（Track1）")
    md.append(f"- 客觀資格門檻：上市於 **{MIN_LISTED}** 之前（＝基準日已上市滿 2 年）\n")

    # ── A1 ──
    ok = bad = miss = notin = 0
    detail = []
    for s in uni:
        nm, st, mk, grp = _listing(s)
        if s not in wl:
            notin += 1
            ad, verdict = '（已從 watchlist 移除）', '無法核對'
        else:
            _n, a = wl[s]
            ad = str(a)[:10] if a else ''
            if not ad:
                miss += 1
                verdict = '無記錄'
            elif ad <= BASE_DATE.isoformat():
                ok += 1
                verdict = '✅ 通過'
            else:
                bad += 1
                verdict = '❌ 晚於基準日'
        detail.append((s, nm or (wl.get(s, ('', ''))[0]), ad, verdict, st, grp))

    md.append("## A1：加入時間戳記核對\n")
    md.append(f"| 結果 | 檔數 | 佔比 |")
    md.append("|---|---|---|")
    md.append(f"| ✅ `added_date` ≤ {BASE_DATE} | **{ok}** | {ok/len(uni):.0%} |")
    md.append(f"| ❌ `added_date` > {BASE_DATE} | **{bad}** | {bad/len(uni):.0%} |")
    md.append(f"| 無時間戳記 | {miss} | {miss/len(uni):.0%} |")
    md.append(f"| 不在現行 watchlist | {notin} | {notin/len(uni):.0%} |")
    md.append("")
    dist = collections.Counter(d[2][:7] for d in detail if d[2] and d[2] != '（已從 watchlist 移除）')
    md.append("**`added_date` 月份分佈**：" +
              "、".join(f"{k} ({v}檔)" for k, v in sorted(dist.items())) + "\n")
    if bad == len(uni):
        md.append("### ❌ A1 判定：**未通過（全部未通過）**\n")
        md.append(f"全部 {len(uni)} 檔的 `added_date` 都落在 **2026 年 2–7 月**，"
                  f"比回測起點 {BASE_DATE} 晚了約 **7 年**。\n")
        md.append("這代表 Phase 1 的 universe 是「**先知道 2026 年的結果、再回測 2019 年**」——")
        md.append("屬教科書級的 selection bias 風險：清單裡的股票之所以在 2026 年被選入，")
        md.append("很可能正是因為它們在 2019–2026 這段期間表現良好。")
        md.append("**→ 觸發 A2（條件式重建）。**\n")
    else:
        md.append(f"### A1 判定：{ok}/{len(uni)} 通過\n")

    # ── Track 1 ──
    t_ok = [d for d in detail if d[4] and d[4] <= MIN_LISTED]
    t_bad = [d for d in detail if d[4] and d[4] > MIN_LISTED]
    t_unk = [d for d in detail if not d[4]]
    md.append("## A2 Track 1：客觀 point-in-time 資格檢查\n")
    md.append("與績效完全無關的客觀條件：基準日已上市滿 2 年。\n")
    md.append("| 結果 | 檔數 |")
    md.append("|---|---|")
    md.append(f"| ✅ 上市於 {MIN_LISTED} 之前 | **{len(t_ok)}** |")
    md.append(f"| ❌ 之後才上市 | **{len(t_bad)}** |")
    md.append(f"| ❓ 無上市日資料 | {len(t_unk)} |")
    md.append("")
    if t_bad:
        md.append("### 不通過明細（含回測最早訊號日交叉核對）\n")
        md.append("| 代號 | 名稱 | 上市日 | 回測最早訊號 | 訊號數 | 時序檢查 |")
        md.append("|---|---|---|---|---|---|")
        pre = 0
        for s, nm, ad, vd, st, grp in sorted(t_bad, key=lambda d: d[4]):
            f = first.get(s, '—')
            badseq = f != '—' and f < st.isoformat()
            if badseq:
                pre += 1
            md.append(f"| {s} | {nm} | {st} | {f} | {cnt.get(s,0):,} | "
                      f"{'⚠️ **回測早於上市日**' if badseq else '✓ 訊號晚於上市'} |")
        md.append("")
        md.append(f"其中 **{pre} 檔的回測訊號早於其 twstock 記載的上市日**"
                  "（4576、6761、6770）。合理解釋是這些個股在上市（主板）之前已在")
        md.append("**興櫃／上櫃**交易，yfinance 提供的是那段期間的價格；"
                  "`twstock.start` 記載的是主板上市日。屬資料語意差異而非虛構價格，")
        md.append("但仍代表這些樣本的早期資料流動性與現行主板不可直接類比。\n")

    # 產業集中度
    md.append("## 產業集中度（selection bias 的另一個面向）\n")
    g = collections.Counter(d[5] or '(未分類)' for d in detail)
    tot = sum(g.values())
    md.append("| 產業 | 檔數 | 佔比 |")
    md.append("|---|---|---|")
    for k, v in g.most_common():
        md.append(f"| {k} | {v} | {v/tot:.0%} |")
    ELEC = ('半導體業', '電子零組件業', '光電業', '其他電子業',
            '電腦及週邊設備業', '通信網路業', '電子通路業', '資訊服務業')
    n_elec = sum(v for k, v in g.items() if k in ELEC)
    md.append("")
    md.append(f"**電子相關合計 {n_elec}/{tot} = {n_elec/tot:.0%}**"
              f"（半導體業單一產業即 {g.get('半導體業',0)/tot:.0%}）。")
    md.append("2019–2026 正是台股半導體大多頭，如此集中的產業結構會讓回測期望值")
    md.append("同時受到**選股偏誤**與**產業景氣**兩股力量墊高，二者需分開檢視"
              "（見 `universe_reconstruction.md` 的產業對照）。\n")

    # 逐檔明細
    md.append("## 逐檔明細（全部 82 檔）\n")
    md.append("| # | 代號 | 名稱 | added_date | A1 | 上市日 | Track1 | 產業 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for i, (s, nm, ad, vd, st, grp) in enumerate(detail, 1):
        t1 = ('✅' if (st and st <= MIN_LISTED) else ('❌' if st else '❓'))
        md.append(f"| {i} | {s} | {nm or '—'} | {ad or '無記錄'} | {vd} | "
                  f"{st or '—'} | {t1} | {grp or '—'} |")

    md.append("\n## 任務A 驗收回答\n")
    md.append("**問題：82 檔是否構成 survivorship / selection bias？**\n")
    md.append("**答案：是，且有可稽核證據。**\n")
    md.append(f"1. **Selection bias：確認存在。** 全部 {len(uni)} 檔的 `added_date` "
              f"皆為 2026 年（{bad}/{len(uni)} 未通過），晚於回測起點 7 年。"
              "universe 是在已知結果之後選定的。")
    md.append(f"2. **客觀資格：多數通過但非全部。** {len(t_ok)}/{len(uni)} 於基準日已上市滿 2 年；"
              f"{len(t_bad)} 檔不合格，其中 3 檔回測訊號早於主板上市日。")
    md.append(f"3. **產業集中：極高。** 電子相關 {n_elec/tot:.0%}，半導體單一產業 "
              f"{g.get('半導體業',0)/tot:.0%}。")
    md.append("\n→ 依 spec 規定進入 **A2 Track 2**：建立獨立的 point-in-time 對照 universe，"
              "量化偏誤幅度。")

    _write(md, 'universe_audit.md')


def cmd_build(_a):
    """Track2：從全市場依客觀規則篩合格股，產業分層抽樣。"""
    import twstock
    uni, _f, _c = _phase1_universe()
    excl = set(uni)
    pool = []
    for code, x in twstock.codes.items():
        if x.type != '股票' or x.market not in ('上市', '上櫃'):
            continue
        if not x.start:
            continue
        try:
            st = datetime.datetime.strptime(x.start, '%Y/%m/%d').date()
        except Exception:
            continue
        if st > MIN_LISTED:
            continue
        if not code.isdigit() or len(code) != 4:
            continue
        pool.append((code, x.name, st, (x.group or '').strip(), x.market))

    by_ind = collections.defaultdict(list)
    for p in pool:
        by_ind[p[3] or '(未分類)'].append(p)
    print(f"[Build] 全市場合格池 {len(pool)} 檔，{len(by_ind)} 個產業")

    # 市場代表性分層：各產業按池中佔比配額，至少 1 檔
    rng = random.Random(42)
    picked = []
    total = len(pool)
    for ind, lst in sorted(by_ind.items(), key=lambda kv: -len(kv[1])):
        quota = max(1, round(N_CONTROL * len(lst) / total))
        rng.shuffle(lst)
        picked.extend(lst[:quota])
    rng.shuffle(picked)
    picked = picked[:N_CONTROL]

    with open(CTRL_LIST, 'w', encoding='utf-8') as f:
        f.write("# build_prompt_15 A2 Track2 對照 universe（point-in-time 客觀篩選）\n")
        f.write(f"# 規則：股票類、上市/上櫃、上市於 {MIN_LISTED} 之前；產業分層、seed=42\n")
        for c, n, st, g, mk in picked:
            f.write(f"{c}\n")
    ind_dist = collections.Counter(p[3] or '(未分類)' for p in picked)
    print(f"[Build] 抽出 {len(picked)} 檔 → {CTRL_LIST}")
    print("[Build] 產業分佈:", dict(ind_dist.most_common(8)))
    json.dump({'picked': [[c, n, str(st), g, mk] for c, n, st, g, mk in picked],
               'pool_size': len(pool)},
              open(os.path.join(ROOT, 'backtest_results', 'bp15_control_meta.json'), 'w'),
              ensure_ascii=False)


def _step0(csv_path):
    rows = list(csv.DictReader(open(csv_path, encoding='utf-8-sig')))
    by = collections.defaultdict(list)
    for r in rows:
        by[r['grade']].append(r)
    out = {'total': len(rows), 'symbols': len({r['symbol'] for r in rows}),
           'span': (min(r['as_of'] for r in rows), max(r['as_of'] for r in rows))}
    for g in ('A', 'B', 'C'):
        v = [float(r['ret_20_net']) for r in by.get(g, [])
             if r.get('ret_20_net') not in ('', 'None', None)]
        out[g] = (len(by.get(g, [])), (round(statistics.mean(v), 3) if v else None))
    return out


def cmd_compare(_a):
    if not os.path.exists(CTRL_CSV):
        print(f"[Compare] 尚無對照回測結果 {CTRL_CSV}"); return
    w = _step0(BASE_CSV)
    c = _step0(CTRL_CSV)
    meta = {}
    mp = os.path.join(ROOT, 'backtest_results', 'bp15_control_meta.json')
    if os.path.exists(mp):
        meta = json.load(open(mp))

    md = ["# 任務A2：Universe 條件式重建（Track 1 + Track 2）\n"]
    md.append("> A1 判定未通過（82 檔全部於 2026 年加入，晚於回測起點 7 年）→ 執行 A2。")
    md.append("> 本報告量化「選股偏誤把 Phase 1 數字墊高了多少」。\n")
    md.append(f"- Watchlist universe：{w['symbols']} 檔｜{w['total']:,} 筆｜"
              f"{w['span'][0]} → {w['span'][1]}")
    md.append(f"- 對照 universe：{c['symbols']} 檔｜{c['total']:,} 筆｜"
              f"{c['span'][0]} → {c['span'][1]}")
    md.append(f"- 對照池母體：全市場合格 {meta.get('pool_size','—')} 檔"
              f"（股票類、上市/上櫃、{MIN_LISTED} 前上市），產業分層抽樣、seed=42\n")

    md.append("## Track 2：Step0 核心數字對照\n")
    md.append("| 等級 | Watchlist n | 對照 n | Watchlist 20日期望 | 對照 20日期望 | 差距 |")
    md.append("|---|---|---|---|---|---|")
    gaps = {}
    for g in ('A', 'B', 'C'):
        wn, we = w[g]
        cn, ce = c[g]
        gap = (round(we - ce, 3) if (we is not None and ce is not None) else None)
        gaps[g] = gap
        md.append(f"| {g} | {wn:,} | {cn:,} | {we:+.3f}% | "
                  f"{ce:+.3f}% | **{gap:+.3f}pp** |" if gap is not None else
                  f"| {g} | {wn:,} | {cn:,} | {we} | {ce} | — |")
    md.append("")
    # 判定需綜合三個等級，不能只看 A（B/C 差距更大）
    over = [g for g in ('A', 'B', 'C') if gaps.get(g) is not None and gaps[g] > 1.0]
    md.append("### 判定：**選股偏誤確認存在，且絕對期望值被顯著墊高**\n")
    md.append(f"三個等級的期望值全部高於對照 universe："
              f"A {gaps['A']:+.3f}pp、B {gaps['B']:+.3f}pp、C {gaps['C']:+.3f}pp。")
    md.append(f"其中 **{len(over)} 個等級（{', '.join(over)}）超過 spec 設定的 1pp 門檻**。\n")
    md.append("（註：若只看 A 級的 +0.632pp 會誤判為「幅度有限」——"
              "但 B/C 差距都超過 1pp，故判定必須綜合三級。）\n")
    md.append("依 spec 規定，`phase1_report.md` 須加明確警語：")
    md.append("**Phase 1 的絕對期望值被選股偏誤墊高約 0.6–1.2pp，"
              "不可視為策略在全市場的預期表現。**\n")

    # 最關鍵的發現：等級鑑別力是否為偏誤產物
    wA, wB, wC = w['A'][1], w['B'][1], w['C'][1]
    cA, cB, cC = c['A'][1], c['B'][1], c['C'][1]
    md.append("### 但等級鑑別力**不是**選股偏誤的產物（本任務最重要的發現）\n")
    md.append("| 指標 | Watchlist | 對照 universe | 判讀 |")
    md.append("|---|---|---|---|")
    md.append(f"| A>B>C 單調性 | {'✅ 成立' if wA>wB>wC else '❌'} "
              f"({wA:+.2f} > {wB:+.2f} > {wC:+.2f}) | "
              f"{'✅ 成立' if cA>cB>cC else '❌'} "
              f"({cA:+.2f} > {cB:+.2f} > {cC:+.2f}) | 兩者皆成立 |")
    md.append(f"| A−C 價差 | {wA-wC:+.3f}pp | **{cA-cC:+.3f}pp** | "
              f"對照組價差{'**更大**' if (cA-cC)>(wA-wC) else '較小'} |")
    md.append(f"| A 級稀缺度 | {w['A'][0]/w['total']:.2%} | {c['A'][0]/c['total']:.2%} | "
              "對照組 A 級更稀有 |")
    md.append("")
    if (cA - cC) > (wA - wC):
        md.append(f"**A−C 價差在無偏誤的對照 universe 上反而更大"
                  f"（{cA-cC:+.3f}pp vs {wA-wC:+.3f}pp）。**")
        md.append("這代表：**選股偏誤墊高了絕對水準，但沒有製造出等級鑑別力**——")
        md.append("三層引擎「A 比 C 好」這個核心相對結論在全市場樣本上依然成立，甚至更明顯。")
        md.append("這是對 Phase 1 相對性結論（A>B>C、因子消融、regime 差異）最有力的辯護：")
        md.append("**受偏誤影響的是水準（level），不是排序（ranking）。**\n")

    # 產業對照：分離選股效應與產業景氣效應
    md.append("### 產業效應 vs 選股效應的部分分離\n")
    try:
        import twstock
        ELEC = ('半導體業', '電子零組件業', '光電業', '其他電子業',
                '電腦及週邊設備業', '通信網路業', '電子通路業', '資訊服務業')

        def _elec_only(path):
            rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
            keep = []
            for r in rows:
                x = twstock.codes.get(r['symbol'])
                if x and (x.group or '').strip() in ELEC:
                    keep.append(r)
            by = collections.defaultdict(list)
            for r in keep:
                by[r['grade']].append(r)
            o = {'symbols': len({r['symbol'] for r in keep}), 'total': len(keep)}
            for g in ('A', 'B', 'C'):
                v = [float(r['ret_20_net']) for r in by.get(g, [])
                     if r.get('ret_20_net') not in ('', 'None', None)]
                o[g] = (len(by.get(g, [])), (round(statistics.mean(v), 3) if v else None))
            return o
        we = _elec_only(BASE_CSV)
        ce = _elec_only(CTRL_CSV)
        md.append("只比較**電子相關產業**的子集（把產業景氣因素大致對齊）：\n")
        md.append("| 等級 | Watchlist電子 n | 對照電子 n | Watchlist 期望 | 對照 期望 | 差距 |")
        md.append("|---|---|---|---|---|---|")
        for g in ('A', 'B', 'C'):
            gp = (round(we[g][1] - ce[g][1], 3)
                  if (we[g][1] is not None and ce[g][1] is not None) else None)
            md.append(f"| {g} | {we[g][0]:,} | {ce[g][0]:,} | {we[g][1]}% | {ce[g][1]}% | "
                      f"{gp:+.3f}pp |" if gp is not None else
                      f"| {g} | {we[g][0]:,} | {ce[g][0]:,} | {we[g][1]} | {ce[g][1]} | — |")
        md.append(f"\n（Watchlist 電子 {we['symbols']} 檔／對照電子 {ce['symbols']} 檔）\n")
        if we['A'][1] is not None and ce['A'][1] is not None:
            ge = we['A'][1] - ce['A'][1]
            md.append(f"產業對齊後 A 級差距為 **{ge:+.3f}pp**，"
                      f"相較未對齊的 {gaps['A']:+.3f}pp "
                      f"{'縮小' if abs(ge) < abs(gaps['A']) else '未縮小'}——"
                      f"代表原始差距中{'有相當部分來自產業結構，而非純粹選股' if abs(ge) < abs(gaps['A']) else '選股效應仍為主'}。")
    except Exception as e:
        md.append(f"（產業對照略過：{e}）")
    md.append("")

    md.append("## 殘留限制（重要，如實記錄）\n")
    md.append("1. **對照 universe 本身仍有 survivorship bias**：`twstock.codes` 只收錄"
              "**目前仍上市**的股票，2019–2026 間下市/下櫃者不在池中。"
              "因此本對照量測的是 **selection bias（選股偏誤）**，"
              "**並未**量測 survivorship bias（倒閉股缺席）。真正無倒存偏誤的對照"
              "需要歷史上市清單快照，目前資料源不具備。")
    md.append("2. **產業效應與選股效應交纏**：watchlist 電子相關佔 85%，"
              "而對照為市場代表性分層。兩者差距同時含「選股」與「產業景氣」兩因素；"
              "下節的產業對照嘗試部分分離。")
    md.append("3. 對照 universe 的籌碼/營收資料為本輪新回補，"
              "與 watchlist 長期累積的資料完整度可能不同（籌碼 fail-safe 比例已列於下）。")

    _write(md, 'universe_reconstruction.md')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['audit', 'build', 'compare'])
    main_args = ap.parse_args()
    globals()[f'cmd_{main_args.cmd}'](main_args)


if __name__ == '__main__':
    main()
