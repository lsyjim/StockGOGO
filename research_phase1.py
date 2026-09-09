"""
research_phase1.py — build_prompt_13 Phase 1 實驗執行器（不修改 production code）

以「原始碼手術」產生變體：取生產函式的原文，只注入必要的一兩行，其餘逐字不動。
比複製整個函式安全（不會抄錯），也比輸入中性化精確（不受 fallback 分支干擾）。

變體：
  --variant none            對照組（不打補丁）→ 必須重現 Step 0 基準（harness 自我驗證）
  --variant ablate --factor slope|adx|rs|vol|pth
                            Layer1 單因子消融：在 score 合成前注入 `<f>_mod = 0`
  --variant nofilter        B1 組別B：大盤濾網關閉（注入 _is_market_bear/_range = False）
  --variant priority_fixed  B2-extra：_vp_trigger 改為候選清單 + 顯式優先序

用法：python research_phase1.py --variant ablate --factor rs --out backtest_results/b2_rs
"""

from __future__ import annotations

import os
import re
import sys
import inspect
import argparse
import textwrap

import decision_engine as DE
from decision_engine import ThreeLayerEngine

FACTOR_VARS = {
    'slope': 'slope_mod', 'adx': 'adx_mod', 'rs': 'rs_mod',
    'vol': 'vol_mod', 'pth': 'pth_mod',
}


def _recompile(func, transform, name):
    """取 func 原始碼 → transform(list[str]) → 編譯回可呼叫物件（用原模組 globals）。"""
    src = textwrap.dedent(inspect.getsource(func))
    lines = src.split('\n')
    # 去掉裝飾器（@staticmethod 等）
    while lines and lines[0].lstrip().startswith('@'):
        lines.pop(0)
    lines = transform(lines)
    new_src = '\n'.join(lines)
    ns = dict(vars(DE))          # 用 decision_engine 的模組命名空間解析 _num 等
    exec(compile(new_src, f'<{name}>', 'exec'), ns)
    fn = ns[func.__name__]
    return fn


def _inject_before(lines, pattern, inject_line, once=True):
    """在符合 pattern 的行之前插入 inject_line（沿用該行縮排）。"""
    out, done = [], False
    for ln in lines:
        if (not done or not once) and re.search(pattern, ln):
            indent = ln[:len(ln) - len(ln.lstrip())]
            out.append(f"{indent}{inject_line}")
            done = True
        out.append(ln)
    if not done:
        raise RuntimeError(f"注入失敗：找不到 pattern {pattern!r}")
    return out


def patch_ablate(factor):
    """Layer1 消融：合成 score 前把該因子的 modifier 歸零。"""
    var = FACTOR_VARS[factor]
    fn = _recompile(
        ThreeLayerEngine.score_direction,
        lambda L: _inject_before(L, r'^\s*score = max\(0, min\(100', f'{var} = 0  # ABLATION'),
        f'ablate_{factor}')
    ThreeLayerEngine.score_direction = staticmethod(fn)
    print(f"[Patch] score_direction: {var} 強制歸零（消融 {factor}）")


def patch_nofilter():
    """B1 組別B：大盤濾網完全關閉（bear/range 判定強制 False）。"""
    def tf(L):
        L = _inject_before(L, r'^\s*_is_market_range = market_available and \(',
                           '_is_market_bear = False  # NOFILTER')
        # 找到 _is_market_range 賦值結束的下一行（該賦值跨行，用 ')' 收尾）
        out, hit, done = [], False, False
        for ln in L:
            out.append(ln)
            if '_is_market_range = market_available and (' in ln:
                hit = True
                continue
            if hit and not done and ln.strip() == ')':
                indent = ln[:len(ln) - len(ln.lstrip())]
                out.append(f"{indent}_is_market_range = False  # NOFILTER")
                done = True
        if not done:
            raise RuntimeError("注入失敗：_is_market_range 區塊結尾未找到")
        return out
    fn = _recompile(ThreeLayerEngine.analyze, tf, 'nofilter')
    ThreeLayerEngine.analyze = staticmethod(fn)
    print("[Patch] analyze: 大盤濾網關閉（_is_market_bear/_is_market_range = False）")


PRIORITY_FIXED_SRC = '''
        candidates = []
        if _bo_55:
            candidates.append((1, 'D55突破（帶量中期突破）', True))
        if wave.get('available') and wave.get('breakout_signal', {}).get('detected') \\
                and wave.get('breakout_signal', {}).get('volume_confirmed'):
            candidates.append((2, '三盤突破（帶量）', True))
        if vp.get('available') and any(s.get('code') == 'VP05' for s in vp.get('signals', [])):
            candidates.append((2, '帶量突破 VP05', True))
        if _bo_20:
            candidates.append((3, 'D20突破（帶量）', False))
        if wave.get('available') and wave.get('breakout_signal', {}).get('detected') \\
                and not wave.get('breakout_signal', {}).get('volume_confirmed'):
            candidates.append((4, '三盤突破（量能待確認）', False))
        if candidates:
            candidates.sort(key=lambda c: c[0])
            _vp_trigger, _vp_strong = candidates[0][1], candidates[0][2]
        else:
            _vp_trigger, _vp_strong = '', False
'''


def patch_priority_fixed():
    """B2-extra：把 _vp_trigger 互斥鏈改為候選清單 + 顯式優先序（spec 提供的實作）。"""
    src = textwrap.dedent(inspect.getsource(ThreeLayerEngine.score_timing))
    lines = src.split('\n')
    while lines and lines[0].lstrip().startswith('@'):
        lines.pop(0)
    # 定位既有 _vp_trigger 判定鏈：從第一個賦值/判定起，到最後一個 _vp_trigger 賦值止
    # 判定區塊 = 從 `_vp_trigger = ''` 起，到 `_vp_strong = bool(...)` 止。
    # （其後所有 _vp_trigger 出現處都只是「使用」，不可動。）
    try:
        start = next(i for i, ln in enumerate(lines)
                     if ln.strip().startswith("_vp_trigger = ''"))
        end = next(i for i, ln in enumerate(lines)
                   if i > start and ln.strip().startswith('_vp_strong = bool('))
    except StopIteration:
        raise RuntimeError("找不到 _vp_trigger/_vp_strong 判定區塊邊界")
    # 依目標行的實際縮排重新對齊（dedent 後函式主體為 4 空格，來源片段為 8 空格）
    anchor = lines[start]
    indent = anchor[:len(anchor) - len(anchor.lstrip())]
    block = [(indent + ln[8:] if ln.strip() else ln)
             for ln in PRIORITY_FIXED_SRC.strip('\n').split('\n')]
    new = lines[:start] + block + lines[end + 1:]
    ns = dict(vars(DE))
    exec(compile('\n'.join(new), '<priority_fixed>', 'exec'), ns)
    ThreeLayerEngine.score_timing = staticmethod(ns['score_timing'])
    print(f"[Patch] score_timing: _vp_trigger 改為顯式優先序（取代原第 {start}–{end} 行區塊）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', required=True,
                    choices=['none', 'ablate', 'nofilter', 'priority_fixed'])
    ap.add_argument('--factor', default='', choices=['', *FACTOR_VARS])
    ap.add_argument('--out', required=True)
    ap.add_argument('--days', default='0')
    ap.add_argument('--hold', default='5,10,20')
    ap.add_argument('--workers', default='8')
    args = ap.parse_args()

    if args.variant == 'ablate':
        if not args.factor:
            ap.error('--variant ablate 需要 --factor')
        patch_ablate(args.factor)
    elif args.variant == 'nofilter':
        patch_nofilter()
    elif args.variant == 'priority_fixed':
        patch_priority_fixed()
    else:
        print("[Patch] none：不打補丁（對照組，應重現基準）")

    sys.argv = ['signal_backtest.py', '--days', args.days, '--hold', args.hold,
                '--reuse-data', '--workers', args.workers, '--out', args.out]
    import signal_backtest
    signal_backtest.main()


if __name__ == '__main__':
    main()
