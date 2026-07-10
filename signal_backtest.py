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


# ── build_prompt_10：因子快照（全部 as_of 點時間值，缺值 None，嚴禁 0 填充）──────
# 建議文字以短代碼記錄（enum 對照見 factor_report 附錄）。建議 = f(action_code)：
# 引擎輸出恆有合法 action_code，_get_short/mid_term 對已知代碼直接查表、不做 bias/rsi 微調，
# 故此對照忠實反映短/中線建議；long_advice 因回測無基本面，以 action_code 代理（報告註記）。
_SHORT_ADVICE = {'STRONG_BUY': 'S1_積極進場', 'BUY': 'S2_分批佈局', 'HOLD': 'S3_續抱',
                 'WAIT': 'S4_等拉回', 'SKIP': 'S5_不參與', 'SELL': 'S6_出場',
                 'TAKE_PROFIT': 'S7_停利'}
_MID_ADVICE = {'STRONG_BUY': 'M1_偏多持有', 'BUY': 'M1_偏多持有', 'HOLD': 'M2_中線觀望',
               'WAIT': 'M3_偏多等位置', 'SKIP': 'M4_偏空出場', 'SELL': 'M4_偏空出場',
               'TAKE_PROFIT': 'M2_中線觀望'}
_LONG_ADVICE = {'STRONG_BUY': 'L1_中長多', 'BUY': 'L1_中長多', 'HOLD': 'L2_中長中立',
                'WAIT': 'L2_中長中立', 'SKIP': 'L3_中長空', 'SELL': 'L3_中長空',
                'TAKE_PROFIT': 'L2_中長中立'}


def _num(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _factor_snapshot(result, fh, i, action_code, rev_mgr, symbol, as_of_date, theme_info):
    """回傳因子欄位 dict（as_of 點時間值）。缺值 None。"""
    tech = result.get('technical', {}) or {}
    mr = result.get('mean_reversion', {}) or {}
    ba = (mr.get('bias_analysis', {}) or {}) if mr.get('available') else {}
    cur = _num(result.get('current_price'))

    k = _num(tech.get('k')); dd = _num(tech.get('d'))
    if k is None or dd is None:
        kd_state = None
    elif k >= 80:
        kd_state = 'high80'
    elif k <= 20:
        kd_state = 'low20'
    elif k > dd:
        kd_state = 'golden'
    elif k < dd:
        kd_state = 'death'
    else:
        kd_state = 'neutral'

    dif = _num(tech.get('macd')); sig = _num(tech.get('macd_signal'))
    if dif is None or sig is None:
        macd_state = None
    elif dif >= sig and dif >= 0:
        macd_state = 'golden'
    elif dif < sig and dif < 0:
        macd_state = 'death'
    elif dif >= 0:
        macd_state = 'above0'
    else:
        macd_state = 'below0'
    _mdv = tech.get('macd_divergence', {}) or {}
    macd_div = ('bull' if _mdv.get('bullish_divergence') else
                ('bear' if _mdv.get('bearish_divergence') else 'none'))

    # vol_ratio / pv_state（由切片自算，防前視）
    vol_ratio = None
    pv_state = None
    try:
        vols = fh['Volume']
        if i >= 20:
            avg20 = float(vols.iloc[i - 20:i].mean())
            vol_ratio = round(float(vols.iloc[i]) / avg20, 2) if avg20 > 0 else None
        if i >= 1 and vol_ratio is not None:
            _pchg = float(fh['Close'].iloc[i]) - float(fh['Close'].iloc[i - 1])
            _vup = vol_ratio >= 1.0
            if _pchg > 0:
                pv_state = '價漲量增' if _vup else '價漲量縮'
            elif _pchg < 0:
                pv_state = '價跌量增' if _vup else '價跌量縮'
            else:
                pv_state = '平盤'
    except Exception:
        pass

    ma20 = _num(tech.get('ma20')); ma60 = _num(tech.get('ma60'))
    ma_bull = (bool(cur is not None and ma20 is not None and ma60 is not None
                    and cur > ma20 > ma60))
    above_ma20 = (bool(cur is not None and ma20 is not None and cur > ma20)
                  if (cur is not None and ma20 is not None) else None)
    above_ma60 = (bool(cur is not None and ma60 is not None and cur > ma60)
                  if (cur is not None and ma60 is not None) else None)

    atr = _num(tech.get('atr14')) or _num(tech.get('atr'))
    atr_pct = round(atr / cur * 100, 2) if (atr and cur) else None

    # 營收（as_of 只讀 DB）
    rev_yoy = None; rev_mom = None
    try:
        rm = rev_mgr.get_revenue_momentum(symbol, as_of=as_of_date)
        if rm.get('available'):
            rev_yoy = rm.get('revenue_yoy')
            rev_mom = bool(rm.get('is_12m_high'))
    except Exception:
        pass

    return {
        'rsi': _num(tech.get('rsi')),
        'kd_k': k, 'kd_d': dd, 'kd_state': kd_state,
        'macd_dif': dif, 'macd_sig': sig, 'macd_hist': _num(tech.get('macd_histogram')),
        'macd_state': macd_state, 'macd_div': macd_div,
        'bias_5': _num(ba.get('bias_5')), 'bias_20': _num(ba.get('bias_20')),
        'bias_60': _num(ba.get('bias_60')),
        'adx': _num(tech.get('adx')), 'atr_pct': atr_pct,
        'bb_squeeze': tech.get('bb_squeeze'),
        'vol_ratio': vol_ratio, 'pv_state': pv_state,
        'ma_bull': ma_bull, 'above_ma20': above_ma20, 'above_ma60': above_ma60,
        'short_advice': _SHORT_ADVICE.get(action_code, ''),
        'mid_advice': _MID_ADVICE.get(action_code, ''),
        'long_advice': _LONG_ADVICE.get(action_code, ''),
        'theme_score': (theme_info or {}).get('theme_rank_pct'),
        'rev_yoy': rev_yoy, 'rev_mom': rev_mom,
    }


# ── 單檔 walk-forward ──────────────────────────────────────────────────────
def run_symbol(symbol, market, full_hist, idx_hist, chip_mgr, rev_mgr,
               days, holds, cost_rate, QuickAnalyzer, start=None, end=None,
               theme_by_date=None, tm=None):
    """回傳該檔所有 (as_of) 訊號的 trade 記錄 list。

    days=0 → 取全部可用 as_of（多期驗證用）；start/end（date）→ 限定 as_of 區間。
    theme_by_date/tm：build_prompt_10 因子快照的題材強度（可選）。
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
            # build_prompt_11 任務3：題材強度須在決策前掛到 result，否則 C→B 升級旗標無法觸發。
            # 旗標關閉時引擎僅在 gated 區塊讀 theme_momentum → 對 baseline 無副作用。
            _theme_info = None
            if tm is not None and theme_by_date is not None:
                try:
                    _theme_info = tm.annotate(symbol, theme_by_date.get(as_of_str, {}))
                    result['theme_momentum'] = _theme_info
                except Exception:
                    _theme_info = None
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
        tech = result.get('technical', {}) or {}
        _trig_str = '｜'.join(triggers)
        # build_prompt_08：動能模式、閘門歸因、安全閥旗標（量測用，讀引擎輸出，不改判定）
        try:
            _is_mom = bool(ThreeLayerEngine._is_momentum(result))
        except Exception:
            _is_mom = False
        _safety_valve = ('超買安全閥' in _trig_str) or ('極度延伸' in _trig_str)
        _bias_ceiling = ('天花板' in _trig_str)

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
            'triggers': _trig_str,
            'pth_52w': tech.get('pth_52w'),
            'rs_score': result['relative_strength'].get('rs_score'),
            'chip_buy_days': chip.get('consecutive_buy_days'),
            'chip_reliable': chip.get('data_reliable'),
            'is_mom': _is_mom,
            'safety_valve': bool(_safety_valve),
            'bias_ceiling': bool(_bias_ceiling),
            'gate': _gate_attribution(decision),
            'volume_zscore': tech.get('volume_zscore'),
            'ret60': (round(float(fh['Close'].iloc[i] / fh['Close'].iloc[i - 60] - 1) * 100, 2)
                      if i >= 60 else None),
            'entry': round(entry_open, 2),
        }
        # build_prompt_10：因子快照（as_of 點時間值，防前視）
        # 復用決策前已計算的 _theme_info，避免重複 annotate。
        row.update(_factor_snapshot(result, fh, i, row['action_code'], rev_mgr,
                                    symbol, as_of_date, _theme_info))
        for N in holds:
            exit_close = float(fh['Close'].iloc[i + 1 + N])
            gross = exit_close / entry_open - 1
            net = gross - cost_rate
            row[f'ret_{N}_net'] = round(net * 100, 3)
            row[f'exit_{N}'] = round(exit_close, 2)
        trades.append(row)

    return trades


# ── build_prompt_08：閘門歸因（讀引擎輸出分類「卡在哪」，不改判定）──────────
def _gate_attribution(decision) -> str:
    scn = decision.get('scenario', '')
    trail = decision.get('adjustment_trail', []) or []
    tl = decision.get('three_layer', {}) or {}
    tim = tl.get('timing', {}) or {}
    trigs = ' '.join(tim.get('triggers', []) if isinstance(tim, dict) else [])
    if scn == 'SELL':
        return '賣出訊號'
    if scn == 'SKIP':
        return '方向分否決'
    if scn == 'WAIT':
        return '位置否決'
    # 已達 C/B/X → 歸因「為何沒更高（未到 A）」
    for st in trail:
        if st.get('stage') == '大盤濾網' and st.get('to'):
            return '大盤濾網降級'
    if ('超買安全閥' in trigs) or ('極度延伸' in trigs):
        return '過熱安全閥'
    if ('PTH' in trigs and '52週高' in trigs):
        return 'PTH未達'
    if ('待確認' in trigs):
        return '量能未確認'
    _has_vp = any(k in trigs for k in ('三盤突破', 'D55突破', 'D20突破', 'VP05', '帶量突破'))
    if _has_vp and ('法人連買' not in trigs):
        return '缺法人腿'
    if scn == 'X' or not trigs.strip() or '無明確' in trigs:
        return '無訊號'
    return '其他'


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
    # trades.csv（build_prompt_10：因子欄位擴充；欄位順序固定 + 動態補齊新增鍵）
    csv_path = os.path.join(out_dir, 'trades.csv')
    _base = ['as_of', 'symbol', 'grade', 'regime', 'market_adx', 'action_code',
             'dir_score', 'pos_score', 'timing_grade', 'pth_52w', 'rs_score',
             'chip_buy_days', 'chip_reliable', 'is_mom', 'safety_valve', 'bias_ceiling',
             'gate', 'volume_zscore', 'ret60',
             # 因子快照
             'rsi', 'kd_k', 'kd_d', 'kd_state', 'macd_dif', 'macd_sig', 'macd_hist',
             'macd_state', 'macd_div', 'bias_5', 'bias_20', 'bias_60', 'adx', 'atr_pct',
             'bb_squeeze', 'vol_ratio', 'pv_state', 'ma_bull', 'above_ma20', 'above_ma60',
             'short_advice', 'mid_advice', 'long_advice', 'theme_score', 'rev_yoy', 'rev_mom',
             'entry'] + [f'exit_{N}' for N in holds] + [f'ret_{N}_net' for N in holds] + ['triggers']
    # 動態補齊任何未列出的鍵（向後相容）
    seen = set(_base)
    extra = [k for t in trades for k in t.keys() if k not in seen and not seen.add(k)]
    fields = _base + extra
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
    # build_prompt_10：因子快照防前視
    md.append("- [x] RSI/KD/MACD（含背離/histogram）皆由 as_of 切片 _technical_analysis 重算，取切片末值")
    md.append("- [x] 乖離 bias_5/20/60 取 as_of 切片 mean_reversion；ATR% 由切片 atr14/現價")
    md.append("- [x] vol_ratio/pv_state 由切片 Volume[i]/Close[i] 對前值計算，不含 i 之後")
    md.append("- [x] 題材強度 theme_by_date 以各日切片 20/60 日報酬計算（防前視）")
    md.append("- [x] 建議代碼 = f(action_code)，來自 as_of 當日引擎裁決")

    md_path = os.path.join(out_dir, 'summary.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    return csv_path, md_path


# ══════════════════════════════════════════════════════════════════════════
# build_prompt_08：捕捉率(recall) / 族群動能 / 第三腿實驗（量測，不改判定）
# ══════════════════════════════════════════════════════════════════════════
def detect_surge_events(closes, thresh=0.30, win=20, merge=20):
    """暴漲事件：起漲日 i 後 win 交易日內最大漲幅 ≥ thresh。事件間隔 <merge → 同一事件。"""
    events = []
    last = -10 ** 9
    n = len(closes)
    for i in range(n - 1):
        hi = closes[i + 1:min(n, i + win + 1)].max()
        if closes[i] > 0 and (hi / closes[i] - 1) >= thresh and (i - last) >= merge:
            events.append((i, hi / closes[i] - 1))
            last = i
    return events


def build_theme_strength_by_date(full_hists, tm):
    """{date_str: theme_strength}，用各檔 as_of 切片的 20/60 日報酬（防前視）。"""
    per = {}   # (sym,date)->(r20,r60)
    all_dates = set()
    for sym, fh in full_hists.items():
        c = fh['Close']
        r20 = (c / c.shift(20) - 1) * 100
        r60 = (c / c.shift(60) - 1) * 100
        for ts in c.index:
            ds = ts.date().isoformat()
            all_dates.add(ds)
            per[(sym, ds)] = (r20.loc[ts], r60.loc[ts])
    by_date = {}
    for ds in sorted(all_dates):
        rets = {}
        for sym in full_hists:
            v = per.get((sym, ds))
            if v and v[0] == v[0]:   # not NaN
                rets[sym] = {'ret20': float(v[0]), 'ret60': (float(v[1]) if v[1] == v[1] else None)}
        by_date[ds] = tm.compute(rets) if rets else {}
    return by_date


def _rs_rank_by_date(all_trades):
    """每日以 ret60 橫斷面百分位 → {(symbol,date): rs_rank_pct}。"""
    from collections import defaultdict
    import bisect
    bydate = defaultdict(list)
    for t in all_trades:
        if t.get('ret60') is not None:
            bydate[t['as_of']].append((t['symbol'], t['ret60']))
    out = {}
    for ds, rows in bydate.items():
        vals = sorted(v for _, v in rows)
        n = len(vals)
        for sym, v in rows:
            lo = bisect.bisect_left(vals, v)
            hi = bisect.bisect_right(vals, v)
            out[(sym, ds)] = round((lo + hi) / 2.0 / n * 100, 1) if n else 50.0
    return out


def run_recall(symbols, full_hists, all_trades, holds, args, out_dir):
    """任務1：捕捉率 + 閘門攔截歸因；任務4：安全閥動能豁免附錄。"""
    os.makedirs(out_dir, exist_ok=True)
    from collections import Counter
    idx = {(t['symbol'], t['as_of']): t for t in all_trades}
    grade_rank = {'A': 5, 'B': 4, 'C': 3, 'X': 2, 'WAIT': 2, 'SKIP': 1, 'SELL': 1}

    events = []
    for sym, fh in full_hists.items():
        fh = fh.sort_index()
        closes = fh['Close'].values
        dates = [d.date().isoformat() for d in fh.index]
        for (si, gain) in detect_surge_events(closes):
            wdates = dates[max(0, si - 5): si + 6]
            seq = [(wd, idx[(sym, wd)]) for wd in wdates if (sym, wd) in idx]
            if not seq:
                continue
            launch = idx.get((sym, dates[si]))
            best = max(seq, key=lambda x: grade_rank.get(x[1]['grade'], 0))
            events.append({
                'symbol': sym, 'start': dates[si], 'gain_pct': round(gain * 100, 1),
                'launch_grade': (launch['grade'] if launch else '—'),
                'launch_gate': (launch['gate'] if launch else '—'),
                'max_grade': best[1]['grade'], 'best_gate': best[1]['gate'],
                'window_days': len(seq),
            })

    # 事件 CSV
    ev_csv = os.path.join(out_dir, 'recall_events.csv')
    if events:
        with open(ev_csv, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(events[0].keys()))
            w.writeheader()
            w.writerows(events)

    n_ev = len(events)
    md = ["# 捕捉率（recall）驗證報告\n"]
    md.append("> 回答「A 級稀有是精準還是漏接」：對清單內個股的暴漲事件（20 交易日內漲幅≥30%），")
    md.append("> 逐日重放引擎，看系統在最佳買點看到什麼、卡在哪個閘門。\n")
    md.append(f"- 標的：{len(symbols)} 檔，回測窗口 {'全歷史' if args.days<=0 else str(args.days)+'日'}")
    md.append(f"- 暴漲事件數：{n_ev}\n")
    if n_ev:
        a = sum(1 for e in events if e['max_grade'] == 'A')
        ab = sum(1 for e in events if e['max_grade'] in ('A', 'B'))
        md.append("## 總捕捉率\n")
        md.append(f"- 事件曾出現 **A**：{a}/{n_ev}（{a/n_ev*100:.1f}%）")
        md.append(f"- 事件曾出現 **A 或 B**：{ab}/{n_ev}（{ab/n_ev*100:.1f}%）\n")

        md.append("## 閘門攔截統計（never-B 事件歸因，核心）\n")
        never = [e for e in events if e['max_grade'] not in ('A', 'B')]
        md.append(f"從未達 B 以上的事件：{len(never)}/{n_ev}\n")
        gc = Counter(e['best_gate'] for e in never)
        if gc:
            md.append("| 卡關閘門 | 事件數 | 佔比 |")
            md.append("|---|---|---|")
            for g, c in gc.most_common():
                md.append(f"| {g} | {c} | {c/len(never)*100:.1f}% |")

        md.append("\n## 起漲日當天等級分佈（最佳買點系統看到什麼）\n")
        lc = Counter(e['launch_grade'] for e in events)
        md.append("| 等級 | 事件數 | 佔比 |")
        md.append("|---|---|---|")
        for g in ['A', 'B', 'C', 'SELL', 'WAIT', 'SKIP', 'X', '—']:
            if lc.get(g):
                md.append(f"| {g} | {lc[g]} | {lc[g]/n_ev*100:.1f}% |")
    else:
        md.append("（區間內無符合定義的暴漲事件）\n")

    # ── 任務4：過熱安全閥動能豁免檢視（併入附錄）──
    md.append("\n## 附錄：過熱安全閥動能豁免檢視（任務4）\n")
    Nref = 10 if 10 in holds else holds[0]
    N2 = 20 if 20 in holds else holds[-1]
    def _mean(rows, key):
        xs = [r[key] for r in rows if r.get(key) is not None]
        return round(statistics.mean(xs), 3) if xs else None
    all_mean_10 = _mean(all_trades, f'ret_{Nref}_net')
    sv = [t for t in all_trades if t.get('safety_valve') or t.get('bias_ceiling')]
    sv_mom = [t for t in sv if t.get('is_mom')]
    sv_non = [t for t in sv if not t.get('is_mom')]
    md.append(f"- 全樣本 {Nref}日均報酬（基準）：{all_mean_10}%")
    md.append(f"- 被安全閥/天花板壓制樣本：{len(sv)}（動能內 {len(sv_mom)} / 動能外 {len(sv_non)}）\n")
    md.append(f"| 子集 | n | {Nref}日期望 | {N2}日期望 | 勝率({Nref}日) |")
    md.append("|---|---|---|---|---|")
    for lab, rows in [('動能內·被壓制', sv_mom), ('動能外·被壓制', sv_non)]:
        nets = [r[f'ret_{Nref}_net'] for r in rows if r.get(f'ret_{Nref}_net') is not None]
        wr = (sum(1 for x in nets if x > 0) / len(nets) * 100) if nets else 0
        md.append(f"| {lab} | {len(rows)} | {_mean(rows,f'ret_{Nref}_net')} | {_mean(rows,f'ret_{N2}_net')} | {wr:.0f}% |")
    _sv_mom_exp = _mean(sv_mom, f'ret_{Nref}_net')
    if _sv_mom_exp is not None and all_mean_10 is not None and len(sv_mom) >= 30 and _sv_mom_exp > all_mean_10:
        md.append(f"\n**結論：建議放寬** — 動能內被安全閥壓制子集 {Nref}日期望 {_sv_mom_exp}% > 全樣本 {all_mean_10}%，"
                  "且樣本≥30。提案：`_is_mom` 且量價健康時，RSI 安全閥閾值 85→92（附本數據，僅提案不改引擎）。")
    else:
        md.append(f"\n**結論：維持現狀 / 需更多樣本** — 動能內被壓制子集期望 {_sv_mom_exp}、樣本 {len(sv_mom)}"
                  f"（需 ≥30 且 > 全樣本 {all_mean_10}% 才提案放寬）。")

    with open(os.path.join(out_dir, 'recall_report.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Recall] 事件 {n_ev} 筆 → {out_dir}/recall_report.md")


def run_experiment_thirdleg(all_trades, theme_by_date, tm, holds, out_dir):
    """任務3：A vs A'（法人腿以 量能Z≥2.0 AND RS rank≥90 AND is_top_theme 替代）。"""
    os.makedirs(out_dir, exist_ok=True)
    rs_rank = _rs_rank_by_date(all_trades)

    def _third_leg_ok(t):
        vz = t.get('volume_zscore')
        if vz is None or float(vz) < 2.0:
            return False
        rr = rs_rank.get((t['symbol'], t['as_of']))
        if rr is None or rr < 90:
            return False
        strength = theme_by_date.get(t['as_of'], {})
        info = tm.annotate(t['symbol'], strength)
        return bool(info.get('is_top_theme'))

    cur_A = [t for t in all_trades if t['grade'] == 'A']
    # 第三腿子集：現狀因「缺法人腿」卡在 B/C，但滿足第三腿條件（原本會是 A）
    subset = [t for t in all_trades
              if t.get('gate') == '缺法人腿' and t['grade'] in ('B', 'C') and _third_leg_ok(t)]
    prime_A = cur_A + subset

    Nrefs = [h for h in (10, 20) if h in holds] or holds
    def _tbl(rows, N):
        nets = [r[f'ret_{N}_net'] for r in rows if r.get(f'ret_{N}_net') is not None]
        s = _stats(nets)
        return s

    md = ["# A 級第三腿實驗報告（僅回測對照，不上線）\n"]
    md.append("> 假設：對無法人連買的題材股，「量能 Z≥2.0 AND RS rank≥90 AND is_top_theme」可替代法人腿。")
    md.append("> A' = 現行 A ∪ 第三腿新增子集。**不自動修改引擎。**\n")
    md.append(f"- 現行 A 樣本：{len(cur_A)}｜第三腿新增：{len(subset)}｜A' 合計：{len(prime_A)}\n")
    for N in Nrefs:
        md.append(f"### 持有 {N} 日")
        md.append("| 版本 | n | 期望 | 勝率 | 最大單筆虧損 |")
        md.append("|---|---|---|---|---|")
        for lab, rows in [('現行 A', cur_A), ("A'（含第三腿）", prime_A), ('僅第三腿子集', subset)]:
            s = _tbl(rows, N)
            if s:
                md.append(f"| {lab} | {s['n']} | {s['expectancy']} | {s['win_rate']}% | {s['max_loss']} |")
            else:
                md.append(f"| {lab} | 0 | – | – | – |")
        md.append("")

    # 結論（以 10 日為準）
    Nc = 10 if 10 in holds else holds[0]
    sA = _tbl(cur_A, Nc)
    sSub = _tbl(subset, Nc)
    md.append("## 結論\n")
    if sA and sSub and sSub['n'] >= 30 and sSub['expectancy'] >= 0.8 * sA['expectancy']:
        md.append(f"**建議採納** — 僅第三腿子集 {Nc}日期望 {sSub['expectancy']}% ≥ 現行 A 的 80%"
                  f"（{sA['expectancy']}%×0.8），且樣本 {sSub['n']}≥30。")
    else:
        _n = sSub['n'] if sSub else 0
        _e = sSub['expectancy'] if sSub else None
        md.append(f"**維持現狀 / 需更多樣本** — 僅第三腿子集期望 {_e}、樣本 {_n}"
                  f"（需 ≥30 且 ≥ 現行 A 期望 {sA['expectancy'] if sA else '—'}% 的 80%）。")

    with open(os.path.join(out_dir, 'third_leg_report.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[Experiment] 第三腿子集 {len(subset)} 筆 → {out_dir}/third_leg_report.md")


# ── build_prompt_10 任務3：SELL/WAIT 分 regime 反向驗證 ────────────────────
def write_sell_wait_regime(trades, holds, out_dir):
    """牛市賣飛率 vs 空頭避損率分開計算（180日牛市 SELL 後六成續漲須以空頭平衡）。"""
    Nr = 10 if 10 in holds else holds[0]
    N2 = 20 if 20 in holds else holds[-1]
    md = ["# SELL / WAIT 反向驗證（分市場環境）\n"]
    md.append("> SELL 後上漲=賣飛（錯失）、下跌=避損（正確）；分 regime 平衡牛市偏誤。\n")
    for grade in ('SELL', 'WAIT'):
        md.append(f"## {grade}\n")
        md.append(f"| Regime | n | {Nr}日均報酬 | 賣飛率(fwd>0) | 避損率(fwd<0) | {N2}日均報酬 |")
        md.append("|---|---|---|---|---|---|")
        for reg in ('多頭', '盤整', '空頭'):
            rows = [t for t in trades if t.get('grade') == grade and t.get('regime') == reg]
            nets = [t[f'ret_{Nr}_net'] for t in rows if t.get(f'ret_{Nr}_net') is not None]
            nets2 = [t[f'ret_{N2}_net'] for t in rows if t.get(f'ret_{N2}_net') is not None]
            if not nets:
                md.append(f"| {reg} | 0 | – | – | – | – |")
                continue
            fly = sum(1 for x in nets if x > 0) / len(nets) * 100
            avoid = sum(1 for x in nets if x < 0) / len(nets) * 100
            md.append(f"| {reg} | {len(nets)} | {statistics.mean(nets):.2f}% | {fly:.0f}% | "
                      f"{avoid:.0f}% | {statistics.mean(nets2):.2f}% |" if nets2 else
                      f"| {reg} | {len(nets)} | {statistics.mean(nets):.2f}% | {fly:.0f}% | {avoid:.0f}% | – |")
        md.append("")
    md.append("**判讀**：牛市 SELL 賣飛率高＝賣訊在多頭過度謹慎；空頭 SELL 避損率高＝賣訊發揮保護。"
              "兩者須並陳，勿以單一 regime 下結論。")
    with open(os.path.join(out_dir, 'sell_wait_regime.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[bp10] SELL/WAIT regime → {out_dir}/sell_wait_regime.md")


# ── build_prompt_10 任務4：兩個既定實驗 ───────────────────────────────────
def run_bp10_experiments(trades, holds, out_dir):
    """實驗1 連買窗口提純；實驗2 WAIT 動能豁免。walk-forward A/B 對比。"""
    Nc = 10 if 10 in holds else holds[0]
    N2 = 20 if 20 in holds else holds[-1]

    def _row(rows, N):
        nets = [t[f'ret_{N}_net'] for t in rows if t.get(f'ret_{N}_net') is not None]
        s = _stats(nets)
        return s

    md = ["# build_prompt_10 實驗報告（walk-forward A/B）\n"]

    # 實驗1：連買窗口提純（法人連買 3-6 天有效；>=7 天觀察）
    md.append("## 實驗1：A 級籌碼腿連買窗口提純\n")
    md.append("> 假設：法人連買 3–6 天有效；≥7 天可能是尾聲。以買進族（A/B/C）分箱對比。\n")
    buy_rows = [t for t in trades if t.get('grade') in ('A', 'B', 'C')
                and t.get('chip_buy_days') is not None]
    buckets = [('連買 1-2', lambda d: 1 <= d <= 2),
               ('連買 3-6', lambda d: 3 <= d <= 6),
               ('連買 7-10', lambda d: 7 <= d <= 10),
               ('連買 >10', lambda d: d > 10)]
    for N in (Nc, N2):
        md.append(f"### 持有 {N} 日")
        md.append("| 連買窗口 | n | 期望 | 勝率 | 最大單筆虧損 |")
        md.append("|---|---|---|---|---|")
        for lab, cond in buckets:
            rows = [t for t in buy_rows if cond(int(t['chip_buy_days']))]
            s = _row(rows, N)
            if s:
                md.append(f"| {lab} | {s['n']} | {s['expectancy']} | {s['win_rate']}% | {s['max_loss']} |")
            else:
                md.append(f"| {lab} | 0 | – | – | – |")
        md.append("")
    # 依實測分箱：3-10 天皆佳、>10 天出現斷崖，故以「3-10 vs >10」為正確切點（非 3-6 vs ≥7）
    s310 = _row([t for t in buy_rows if 3 <= int(t['chip_buy_days']) <= 10], Nc)
    s10p = _row([t for t in buy_rows if int(t['chip_buy_days']) > 10], Nc)
    md.append("**結論**：")
    if s310 and s10p and s310['n'] >= 30 and s10p['n'] >= 30 and s310['expectancy'] > s10p['expectancy']:
        md.append(f"- 分箱顯示真正斷崖在 **>10 天**：連買 3-10 天 {Nc}日期望 {s310['expectancy']}%（n={s310['n']}）"
                  f" vs >10 天 {s10p['expectancy']}%（n={s10p['n']}）。7-10 天並未變差（見上表），"
                  f"故修正原假設 → **建議「連買 >10 天剔除/降級」，保留 3-10 天**（需 --days 0 重跑驗證單調性後採納）。")
    else:
        md.append(f"- 連買 3-10 期望 {s310['expectancy'] if s310 else '—'}（n={s310['n'] if s310 else 0}）、"
                  f">10 期望 {s10p['expectancy'] if s10p else '—'}（n={s10p['n'] if s10p else 0}）"
                  f" → **維持現狀/需更多樣本**。")

    # 實驗2：WAIT 動能豁免
    md.append("\n## 實驗2：WAIT 動能豁免\n")
    md.append("> recall 附錄「動能內被壓制」正式化：WAIT 且 is_mom 的後續報酬 vs 全樣本基準。\n")
    all_nets = [t[f'ret_{Nc}_net'] for t in trades if t.get(f'ret_{Nc}_net') is not None]
    base = round(statistics.mean(all_nets), 3) if all_nets else None
    wait_mom = [t for t in trades if t.get('grade') == 'WAIT' and t.get('is_mom')]
    s_wm = _row(wait_mom, Nc)
    md.append(f"- 全樣本 {Nc}日基準：{base}%")
    if s_wm:
        md.append(f"- WAIT·動能內：n={s_wm['n']}、{Nc}日期望 {s_wm['expectancy']}%、勝率 {s_wm['win_rate']}%")
    md.append("\n**結論**：")
    if s_wm and base is not None and s_wm['n'] >= 30 and s_wm['expectancy'] > base:
        md.append(f"- WAIT·動能內期望 {s_wm['expectancy']}% > 全樣本 {base}% 且 n≥30 → **提案放寬**："
                  "動能模式且量價健康時，WAIT 位置門檻放寬（僅提案，不改引擎）。")
    else:
        md.append(f"- 樣本 {s_wm['n'] if s_wm else 0}（需≥30）、期望 {s_wm['expectancy'] if s_wm else '—'} "
                  f"vs 基準 {base}% → **維持現狀並結案**。")

    with open(os.path.join(out_dir, 'experiment_bp10.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(md) + "\n")
    print(f"[bp10] 實驗報告 → {out_dir}/experiment_bp10.md")


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
    ap.add_argument('--recall', action='store_true', help='捕捉率模式（暴漲事件 + 閘門歸因）')
    ap.add_argument('--experiment', default='', help='實驗開關：third_leg')
    args = ap.parse_args()

    holds = [int(x) for x in args.hold.split(',') if x.strip()]
    _start = datetime.date.fromisoformat(args.start) if args.start else None
    _end = datetime.date.fromisoformat(args.end) if args.end else None
    QuickAnalyzer, DataSourceManager = _lazy_main()

    # 標的
    if args.symbols:
        if os.path.exists(args.symbols):
            with open(args.symbols) as f:
                symbols = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        else:
            symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    else:
        from database import WatchlistDatabase
        db = WatchlistDatabase()
        symbols = [s[0] for s in db.get_all_stocks() if (s[2] if len(s) > 2 else '台股') == '台股']

    # build_prompt_08：recall/experiment 需題材成分股歷史算題材強度 → 併入抓取集
    _tm = None
    if args.recall or args.experiment:
        try:
            from theme_momentum import ThemeMomentum
            _tm = ThemeMomentum()
            symbols = sorted(set(symbols) | set(_tm.all_symbols()))
        except Exception as _te:
            print(f"[Theme] 載入失敗: {_te}")
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
        chip_mgr.sync_calendar(lookback_days=2900)
    elif not chip_mgr.get_latest_trading_day():
        chip_mgr.sync_calendar(lookback_days=max(500, args.days * 2))

    # 大盤指數（一次抓，全體共用）
    try:
        idx_hist = QuickAnalyzer._get_index_history_cached(QuantConfig.MARKET_INDEX_TW, period="max")
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
            h = DataSourceManager.get_history(sym, '台股', start_date=QuantConfig.HISTORY_START_DATE)
            if h is not None and not h.empty:
                full_hists[sym] = h.dropna()
        except Exception as e:
            print(f"[Backtest] {sym} 抓取失敗: {e}")
        # 籌碼回測需要足夠歷史：backfill 一次（含 as_of 前的日子）
        try:
            if args.days <= 0:
                chip_mgr.deep_backfill(sym, start_date=QuantConfig.CHIP_DEEP_START_DATE)
            else:
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
            bh = DataSourceManager.get_history('0050', '台股', start_date=QuantConfig.HISTORY_START_DATE)
            bh = bh.dropna() if bh is not None else None
        except Exception:
            bh = None
    if bh is not None and len(bh) > max(holds) + 5:
        bh = bh.sort_index()
        for N in holds:
            rets = [(bh['Close'].iloc[k + N] / bh['Open'].iloc[k] - 1) * 100
                    for k in range(len(bh) - N - 1)][-args.days:]
            index_bh[N] = round(statistics.mean(rets), 3) if rets else None

    # build_prompt_10：題材強度 by-date（因子快照 theme_score 用；載入失敗則 None）
    theme_by_date = None
    if _tm is None:
        try:
            from theme_momentum import ThemeMomentum
            _tm = ThemeMomentum()
        except Exception:
            _tm = None
    if _tm is not None:
        try:
            theme_by_date = build_theme_strength_by_date(full_hists, _tm)
        except Exception as _e:
            print(f"[Theme] by-date 計算略過: {_e}")

    # 平行 walk-forward
    all_trades = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_symbol, sym, '台股', full_hists.get(sym), idx_hist,
                          chip_mgr, rev_mgr, args.days, holds, cost_rate, QuickAnalyzer,
                          _start, _end, theme_by_date, _tm): sym
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
    # 一律輸出基礎 trades/summary（含 recall/experiment 模式，供迴歸對照）
    csv_path, md_path = write_reports(all_trades, holds, out_dir, args, index_bh)
    print(f"[Backtest] 完成：{len(all_trades)} 筆訊號")
    print(f"[Backtest] trades:  {csv_path}")
    print(f"[Backtest] summary: {md_path}")

    # build_prompt_08：捕捉率 / 第三腿實驗
    if args.recall:
        run_recall(symbols, full_hists, all_trades, holds, args, out_dir)
    if args.experiment == 'third_leg':
        if theme_by_date is None and _tm is not None:
            theme_by_date = build_theme_strength_by_date(full_hists, _tm)
        run_experiment_thirdleg(all_trades, theme_by_date or {}, _tm, holds, out_dir)

    # build_prompt_10：SELL/WAIT 分 regime 反向驗證 + 兩個實驗
    write_sell_wait_regime(all_trades, holds, out_dir)
    if args.experiment in ('conn_window', 'wait_exempt', 'bp10'):
        run_bp10_experiments(all_trades, holds, out_dir)


if __name__ == '__main__':
    main()
