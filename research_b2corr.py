"""
research_b2corr.py — build_prompt_13 B2 Test A：Layer1 五因子修正量相關性矩陣

spec 定位：Test A「僅供參考，不作為判斷依據」，真正判斷依據是 Test B（增量價值）。

作法：對凍結資料集抽樣重放，以原始碼手術在 score_direction 的合成前注入一行
追蹤器，取出每次呼叫的 (slope_mod, adx_mod, rs_mod, vol_mod, pth_mod)，
再算 Pearson / Spearman 兩兩相關。

為何抽樣：完整 130,993 筆需重跑整條 as-of 管線（約 50 分鐘）；相關係數在
n=5,000 已充分收斂，且 Test A 本非判斷依據。抽樣數與種子皆記錄於報告。

用法：python research_b2corr.py [--n 5000] [--seed 42]
"""

from __future__ import annotations

import os
import re
import sys
import json
import random
import inspect
import argparse
import textwrap
import warnings
import statistics

warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'backtest_results', 'b2_corr_mods.json')

FACTORS = ['slope', 'adx', 'rs', 'vol', 'pth']
LABELS = {'slope': 'MA斜率', 'adx': 'ADX', 'rs': 'RS', 'vol': '量能', 'pth': 'PTH'}


def install_tracer():
    """回傳 (trace_list, 已安裝的 score_direction)。"""
    import decision_engine as DE
    src = textwrap.dedent(inspect.getsource(DE.ThreeLayerEngine.score_direction))
    lines = src.split('\n')
    while lines and lines[0].lstrip().startswith('@'):
        lines.pop(0)
    out, done = [], False
    for ln in lines:
        if not done and re.search(r'^\s*score = max\(0, min\(100', ln):
            indent = ln[:len(ln) - len(ln.lstrip())]
            out.append(f"{indent}_MOD_TRACE.append((base_score, slope_mod, adx_mod, "
                       f"rs_mod, vol_mod, pth_mod))")
            done = True
        out.append(ln)
    if not done:
        raise RuntimeError('注入點未找到')
    ns = dict(vars(DE))
    trace = []
    ns['_MOD_TRACE'] = trace
    exec(compile('\n'.join(out), '<modtrace>', 'exec'), ns)
    DE.ThreeLayerEngine.score_direction = staticmethod(ns['score_direction'])
    return trace


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=5000)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    trace = install_tracer()

    import signal_backtest as SB
    from config import QuantConfig
    from main import QuickAnalyzer
    from chip_data_manager import get_chip_manager
    from revenue_data_manager import get_revenue_manager
    import datetime

    hists = SB._load_hist_cache(QuantConfig.HISTORY_START_DATE)
    if not hists:
        print('[B2corr] 無凍結價格快取，中止'); return
    chip = get_chip_manager()
    rev = get_revenue_manager()
    idx = hists.get('0050')

    rng = random.Random(args.seed)
    syms = sorted(hists)
    picks = []
    while len(picks) < args.n:
        s = rng.choice(syms)
        h = hists[s]
        if len(h) < 300:
            continue
        i = rng.randrange(250, len(h) - 25)
        picks.append((s, i))

    ok = 0
    for s, i in picks:
        h = hists[s]
        try:
            as_of_date = h.index[i].date()
            as_of_str = as_of_date.isoformat()
            ha = h.iloc[:i + 1]
            ia = idx[idx.index <= h.index[i]] if idx is not None else None
            before = len(trace)
            # build_asof_result 本身不呼叫 engine；需另行呼叫 score_direction 取修正量
            res = SB.build_asof_result(s, ha, ia, chip, rev, as_of_str, as_of_date, QuickAnalyzer)
            import decision_engine as DE
            DE.ThreeLayerEngine.score_direction(res)
            if len(trace) > before:
                ok += 1
        except Exception:
            continue
        if ok % 500 == 0 and ok:
            print(f'[B2corr] {ok}/{args.n}')

    print(f'[B2corr] 有效樣本 {len(trace)}')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(trace, f)
    print(f'[B2corr] 修正量已存 → {OUT}')


if __name__ == '__main__':
    main()
