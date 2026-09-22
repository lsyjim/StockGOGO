"""
portfolio_engine.py — build_prompt_19 任務1：Portfolio Engine 核心邏輯

定位
────
把「風險控制」從**訊號層**（原本大盤空頭就把 A 降成 B）搬到**曝險層**：
grade 只負責回答「這檔訊號多強」，這裡負責回答「這筆該下多大、整體該
持多少」。任務0 已移除 `decision_engine.analyze()` 的大盤濾網降級，
regime 風控改由 `gross_exposure_cap()` 表達。

四層核心（每層都只會**縮小**部位，不會放大）：

  1. position_sizing()      ATR 風險預算法 + 等級係數 + 單筆上限
  2. gross_exposure_cap()   regime 總曝險上限
  3. concentration_limits() 題材集中度（theme_map.json）
  4. correlation_limits()   高相關集群集中度

`evaluate_new_position()` 把四層串起來，取最嚴格者。

本模組是**純函式**：不讀 DB、不打網路、不碰 UI。價格歷史一律由呼叫端
以 `price_history_getter(symbol)` 注入，方便回測與實盤共用同一套邏輯。

所有門檻常數一律取自 `config.QuantConfig`，模組內不 hardcode。
"""

from __future__ import annotations

import math

from config import QuantConfig as _QC


__all__ = [
    'position_sizing', 'gross_exposure_cap', 'concentration_limits',
    'correlation_limits', 'evaluate_new_position',
]


# ── 小工具 ────────────────────────────────────────────────────────────────
def _num(x):
    """安全轉 float；None/空值/NaN 一律回 None。"""
    try:
        if x is None or x == '':
            return None
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _positive(x):
    v = _num(x)
    return v if (v is not None and v > 0) else None


def _sum_pct(positions):
    return sum(_num(p.get('position_pct')) or 0.0 for p in (positions or []))


def _default_risk_pct():
    """未知等級的保守預設：取 RISK_PCT_BY_GRADE 中最小者。"""
    return min(_QC.RISK_PCT_BY_GRADE.values())


# ── 1a. 部位大小：ATR 風險預算法 ───────────────────────────────────────────
def position_sizing(grade, capital, entry_price, atr, risk_pct_override=None):
    """依「每筆最多虧損 risk_pct 的資金」反推部位大小。

    risk_amount = capital × risk_pct（risk_pct 由 grade 決定，A>B>C）
    stop_distance_per_share = ATR_K_STOP × atr
    shares = risk_amount / stop_distance_per_share

    直覺：停損距離越寬（ATR 越大）→ 同樣的容忍虧損只能買越少股。

    atr 不可用（None/<=0）時 fallback 成固定金額法
    （shares = capital × risk_pct / entry_price），並標記 `fallback=True`。

    最後套 `MAX_SINGLE_POSITION_PCT` 單筆上限。**被封頂時 shares 與
    position_value 會一併按封頂後的 pct 重算**，確保回傳的三個數字自洽
    （否則呼叫端拿 shares 下單會超買）。
    """
    cap_pct = _QC.MAX_SINGLE_POSITION_PCT
    capital = _positive(capital)
    price = _positive(entry_price)
    risk_pct = _num(risk_pct_override)
    if risk_pct is None:
        risk_pct = _QC.RISK_PCT_BY_GRADE.get(grade, _default_risk_pct())

    out = {'shares': 0.0, 'position_value': 0.0, 'position_pct': 0.0,
           'risk_pct_used': risk_pct, 'stop_distance_per_share': None,
           'capped': False, 'fallback': False}
    if capital is None or price is None:
        return out

    risk_amount = capital * risk_pct
    atr_v = _positive(atr)
    stop_dist = (_QC.ATR_K_STOP * atr_v) if atr_v is not None else None
    if stop_dist is None or stop_dist <= 0:
        # fallback：無 ATR 可用 → 退化成固定金額法
        out['fallback'] = True
        shares = risk_amount / price
    else:
        out['stop_distance_per_share'] = stop_dist
        shares = risk_amount / stop_dist

    value = shares * price
    pct = value / capital
    if pct > cap_pct:
        out['capped'] = True
        pct = cap_pct
        value = cap_pct * capital
        shares = value / price

    out.update({'shares': shares, 'position_value': value, 'position_pct': pct})
    return out


# ── 1b. regime 總曝險上限 ─────────────────────────────────────────────────
def gross_exposure_cap(regime, market_available=True):
    """回傳該 regime 下的總曝險上限（佔資金比例）。

    未知 regime 或 market_available=False 一律 fallback 到「盤整」那組
    （保守預設，**不是** 100%）。這是任務0 移除 grade 降級後，
    大盤空頭風控的唯一表達方式。
    """
    table = _QC.GROSS_EXPOSURE_BY_REGIME
    fallback = table[_QC.GROSS_EXPOSURE_FALLBACK_REGIME]
    if not market_available:
        return fallback
    return table.get(regime, fallback)


# ── 1c. 題材集中度 ────────────────────────────────────────────────────────
def _themes_of(theme_map, symbol):
    """回傳 symbol 所屬的全部題材名稱。

    theme_map 可以是 theme_map.json 整包（含 'themes' 鍵），
    也可以直接是內層 {題材: [代號, ...]}。
    """
    if not isinstance(theme_map, dict):
        return []
    inner = theme_map.get('themes') if isinstance(theme_map.get('themes'), dict) \
        else theme_map
    sym = str(symbol)
    return [t for t, members in inner.items()
            if isinstance(members, (list, tuple, set)) and sym in {str(m) for m in members}]


def concentration_limits(current_positions, candidate_symbol, candidate_pct,
                         theme_map, max_theme_pct=None):
    """單一題材總曝險上限。超過時**縮減到上限為止**，而非直接拒絕。

    candidate 不屬於任何題材 → 視為無集中度限制，原樣放行。
    candidate 同時屬於多個題材 → 取最嚴格（可承受空間最小）的那個。
    """
    cap = _num(max_theme_pct)
    if cap is None:
        cap = _QC.MAX_THEME_EXPOSURE_PCT
    want = _num(candidate_pct) or 0.0

    themes = _themes_of(theme_map, candidate_symbol)
    if not themes:
        return {'approved_pct': want, 'theme': None, 'theme_total_before': 0.0,
                'theme_total_after': want, 'capped': False}

    binding, before, allowed = None, 0.0, want
    for t in themes:
        members = {str(m) for m in (
            theme_map.get('themes', theme_map).get(t) or [])}
        tot = sum(_num(p.get('position_pct')) or 0.0
                  for p in (current_positions or [])
                  if str(p.get('symbol')) in members)
        room = max(0.0, cap - tot)
        if binding is None or room < allowed:
            binding, before, allowed = t, tot, min(want, room)

    return {'approved_pct': allowed, 'theme': binding,
            'theme_total_before': before, 'theme_total_after': before + allowed,
            'capped': allowed < want}


# ── 1d. 相關性集中度 ──────────────────────────────────────────────────────
def _returns(closes, window):
    """取最後 window 根收盤價算報酬率序列；資料不足回 None。"""
    if not closes:
        return None
    vals = [v for v in (_num(c) for c in closes) if v is not None and v > 0]
    if len(vals) < window:
        return None
    vals = vals[-window:]
    return [vals[i] / vals[i - 1] - 1.0 for i in range(1, len(vals))]


def _pearson(a, b):
    """Pearson 相關係數；零變異或長度不符回 None（視為無法判定）。"""
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    va = math.sqrt(sum(x * x for x in da))
    vb = math.sqrt(sum(x * x for x in db))
    if va <= 0 or vb <= 0:
        return None
    r = sum(x * y for x, y in zip(da, db)) / (va * vb)
    return None if r != r else r


def correlation_limits(current_positions, candidate_symbol, candidate_pct,
                       price_history_getter, corr_threshold=None, max_pct=None):
    """高相關集群總曝險上限。

    與 candidate 報酬相關係數 > threshold 的持倉歸為同一集群；
    集群（含 candidate）總曝險超過上限時，把 candidate 縮到剛好不超過。

    任一方歷史不足 `CORR_WINDOW_DAYS` 天、取不到資料、或序列零變異
    → 該對股票**視為不相關**（寧可漏判也不誤判），不納入集群。
    """
    thr = _num(corr_threshold)
    if thr is None:
        thr = _QC.CORR_THRESHOLD
    cap = _num(max_pct)
    if cap is None:
        cap = _QC.MAX_CORRELATED_EXPOSURE_PCT
    window = _QC.CORR_WINDOW_DAYS
    want = _num(candidate_pct) or 0.0

    def _hist(sym):
        try:
            return price_history_getter(sym)
        except Exception:
            return None

    base = _returns(_hist(candidate_symbol), window)
    if base is None:
        return {'approved_pct': want, 'correlated_with': [],
                'cluster_total_after': want, 'capped': False}

    cluster, cluster_pct = [], 0.0
    for p in (current_positions or []):
        sym = p.get('symbol')
        other = _returns(_hist(sym), window)
        if other is None:
            continue
        r = _pearson(base, other)
        if r is not None and r > thr:
            cluster.append(sym)
            cluster_pct += _num(p.get('position_pct')) or 0.0

    if not cluster:
        return {'approved_pct': want, 'correlated_with': [],
                'cluster_total_after': want, 'capped': False}

    allowed = min(want, max(0.0, cap - cluster_pct))
    return {'approved_pct': allowed, 'correlated_with': cluster,
            'cluster_total_after': cluster_pct + allowed,
            'capped': allowed < want}


# ── 1e. 整合 ──────────────────────────────────────────────────────────────
def evaluate_new_position(candidate, current_positions, capital, regime,
                          market_available, theme_map, price_history_getter):
    """四層依序過濾，取最嚴格（最小）的 pct。

    candidate: {'symbol', 'grade', 'entry_price', 'atr'}

    每一層都只會縮小部位，所以最終值等於各層核准值的最小者；
    `steps` 保留每層的中間結果，供報告/回測追溯是哪一層卡住的。

    final_pct 低於 `MIN_EFFECTIVE_POSITION_PCT` 時 `rejected=True`，
    代表這筆實質上不該進場（例如曝險已滿、題材已塞爆）。
    """
    candidate = candidate or {}
    symbol = candidate.get('symbol')
    price = _positive(candidate.get('entry_price'))
    cap_total = _positive(capital)

    steps = []

    # 1. 部位大小
    sizing = position_sizing(candidate.get('grade'), capital, price,
                             candidate.get('atr'))
    pct = sizing['position_pct']
    steps.append({'step': 'position_sizing', 'approved_pct': pct,
                  'capped': sizing['capped'], 'detail': sizing})

    # 2. regime 總曝險上限（現有總曝險 + candidate 不得超過）
    gcap = gross_exposure_cap(regime, market_available)
    gross_now = _sum_pct(current_positions)
    room = max(0.0, gcap - gross_now)
    g_pct = min(pct, room)
    steps.append({'step': 'gross_exposure_cap', 'approved_pct': g_pct,
                  'capped': g_pct < pct, 'cap': gcap,
                  'gross_before': gross_now, 'gross_after': gross_now + g_pct})
    pct = g_pct

    # 3. 題材集中度
    conc = concentration_limits(current_positions, symbol, pct, theme_map)
    steps.append({'step': 'concentration_limits',
                  'approved_pct': conc['approved_pct'],
                  'capped': conc['capped'], 'detail': conc})
    pct = min(pct, conc['approved_pct'])

    # 4. 相關性集中度
    corr = correlation_limits(current_positions, symbol, pct,
                              price_history_getter)
    steps.append({'step': 'correlation_limits',
                  'approved_pct': corr['approved_pct'],
                  'capped': corr['capped'], 'detail': corr})
    pct = min(pct, corr['approved_pct'])

    rejected = pct < _QC.MIN_EFFECTIVE_POSITION_PCT
    if rejected:
        pct = 0.0
    shares = (pct * cap_total / price) if (cap_total and price) else 0.0

    return {'final_pct': pct, 'final_shares': shares, 'steps': steps,
            'rejected': rejected}
