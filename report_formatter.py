"""
report_formatter.py — 量化建議「單一真相源」（build_prompt_06 任務1a）

build_verdict(result) → dict：**只讀不重算**。所有等級/分數/建議一律取自
result['decision_matrix']（engine analyze 最終裁決）與 result['recommendation']
（_generate_recommendation_v43 輸出）。首頁量化建議、完整報告、左下摘要全部改接此函式，
杜絕「首頁 B 級、報告 A 級」的多鏈路不一致。

鐵律：本模組不得重算任何分數、目標價、停損、連買天數——只做欄位彙整與顯示格式化。
"""

from __future__ import annotations


def _num(x):
    if x is None or isinstance(x, str):
        return None
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


# action_code → 簡短動作標籤（首頁欄位用；與 decision_engine 裁決同源）
_ACTION_SHORT = {
    'STRONG_BUY': '主攻｜積極進場',
    'BUY':        '追蹤｜分批佈局',
    'HOLD':       '觀察｜續抱不加碼',
    'WAIT':       '等待｜拉回再進',
    'SKIP':       '跳過｜方向不利',
    'SELL':       '賣出｜出場',
    'TAKE_PROFIT': '停利｜分批了結',
}

_GRADE_LABELS = {
    'A': 'A 級主攻', 'B': 'B 級追蹤', 'C': 'C 級觀察',
    'SELL': '賣出訊號', 'WAIT': '等待拉回', 'SKIP': '方向不佳',
    'X': '無訊號',
}

# ── build_prompt_20：建議部位（接 portfolio_engine）─────────────────────
#
# 核心防線：這個區塊**只產生數字與客觀計算依據**，一個強度形容詞都不准出現。
# 「強烈建議買進」「積極進場」這類字眼的唯一來源仍是 overall_text
# （_generate_recommendation_v43），本輪完全沒動那條路徑。
#
# 等級閘門（fix_prompt_07 3149 事件的延伸紀律）：
#   A/B      → 顯示部位 % 與股數
#   C/X/其他 → position_pct=None，只給 POSITION_NOTE_WATCH，不給任何百分比，
#              避免「C 級也有 5%」被讀成「C 級也值得進場」
#   賣出族   → 完全不碰 portfolio_engine（那是買進情境的引擎），
#              UI 維持既有「出清 / 避開」
POSITION_NOTE_WATCH = '觀察中，暫無建議部位'
_SIZED_GRADES = ('A', 'B')

_THEME_MAP_CACHE = None


def _theme_map():
    """theme_map.json（讀一次快取）。讀不到就回空 dict，集中度限制自然不作用。"""
    global _THEME_MAP_CACHE
    if _THEME_MAP_CACHE is None:
        import json
        import os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theme_map.json')
        try:
            with open(p, encoding='utf-8') as f:
                _THEME_MAP_CACHE = json.load(f)
        except Exception:
            _THEME_MAP_CACHE = {}
    return _THEME_MAP_CACHE


def _no_price_history(_symbol):
    """本輪 current_positions 恆為空清單，相關性層不會被用到。

    多持倉整合時，這裡要換成真的「近 N 日收盤價」取數器。
    """
    return None


def _position_block(grade, is_exit, result, current_price):
    """回傳要併進 plan 的部位欄位。只回資料，不回任何描述性文案。"""
    blank = {'position_pct': None, 'position_note': None, 'position_shares': None,
             'position_steps': None, 'position_risk_pct': None,
             'position_capped_by': [], 'position_rejected': False}

    if is_exit:
        # 賣出族：UI 既有「出清 / 避開」照舊，不接 portfolio_engine
        return blank
    if grade not in _SIZED_GRADES:
        return {**blank, 'position_note': POSITION_NOTE_WATCH}

    try:
        import portfolio_engine as _PE
        from config import QuantConfig as _QC
    except Exception:
        return {**blank, 'position_note': POSITION_NOTE_WATCH}

    tech = result.get('technical', {}) or {}
    atr = _num(tech.get('atr14'))
    if atr is None:
        atr = _num(tech.get('atr'))
    mreg = result.get('market_regime', {}) or {}

    try:
        out = _PE.evaluate_new_position(
            {'symbol': result.get('symbol'), 'grade': grade,
             'entry_price': current_price, 'atr': atr},
            current_positions=[],          # 本輪單檔視角；多持倉整合是下一輪
            capital=_QC.SIMULATED_CAPITAL,
            regime=mreg.get('trend_direction'),
            market_available=bool(mreg.get('available')),
            theme_map=_theme_map(),
            price_history_getter=_no_price_history,
        )
    except Exception:
        return {**blank, 'position_note': POSITION_NOTE_WATCH}

    if out.get('rejected'):
        return {**blank, 'position_note': POSITION_NOTE_WATCH,
                'position_steps': out.get('steps'), 'position_rejected': True}

    sizing = (out['steps'][0].get('detail') or {}) if out.get('steps') else {}
    # 哪幾層真的縮減了（供 UI 加註「受限縮減」）。position_sizing 的單筆上限
    # 不算集中度限制，故從第二層起算。
    capped_by = [s['step'] for s in (out.get('steps') or [])[1:] if s.get('capped')]

    return {
        # 單位沿用既有 UI 契約：百分比數字（20.0 = 20%），不是小數
        'position_pct':      round(out['final_pct'] * 100, 1),
        'position_shares':   out['final_shares'],
        'position_steps':    out['steps'],
        'position_risk_pct': round((sizing.get('risk_pct_used') or 0) * 100, 2),
        'position_capped_by': capped_by,
        'position_rejected': False,
        'position_note':     None,
    }


def build_verdict(result: dict) -> dict:
    """單一真相源。回傳完整 verdict dict（見 build_prompt_06 任務1a 規格）。"""
    dm  = result.get('decision_matrix', {}) or {}
    rec = result.get('recommendation', {})
    if not isinstance(rec, dict):
        rec = {}
    tl  = dm.get('three_layer', {}) or {}
    direction = tl.get('direction') or {}
    position  = tl.get('position') or {}
    timing    = tl.get('timing') or {}
    tech      = result.get('technical', {}) or {}
    symbol    = result.get('symbol', '')

    grade = dm.get('scenario', 'X')
    action_code = dm.get('action_code', '')

    # ── 分期建議（同源：v43 依 action_code 產生的 short/mid/long）──
    def _term(key):
        d = rec.get(key) or {}
        if isinstance(d, dict):
            return {'action': d.get('action', '—'), 'reason': d.get('reason', '')}
        return {'action': str(d), 'reason': ''}
    term_advice = {'short': _term('short_term'), 'mid': _term('mid_term'), 'long': _term('long_term')}

    # ── 三層分數與各層一行摘要 ──
    scores = {
        'direction': direction.get('score'),
        'position':  position.get('score'),
        'timing':    timing.get('grade', grade),
    }
    def _first_detail(layer):
        ds = layer.get('details') or layer.get('triggers') or []
        return ds[0] if ds else '—'
    score_notes = {
        'direction': _first_detail(direction),
        'position':  _first_detail(position),
        'timing':    _first_detail(timing),
    }

    # ── 交易計畫（全部取自引擎 price_targets / risk_manager，不重算）──
    pt = dm.get('price_targets', {}) or {}
    rm = result.get('risk_manager', {}) or {}
    sr = result.get('support_resistance', {}) or {}
    current = _num(result.get('current_price'))
    _sup1 = _num(sr.get('support1'))
    entry_zone = None
    if current is not None:
        if _sup1 is not None and 0 < _sup1 < current:
            entry_zone = (round(_sup1, 2), round(current, 2))
        else:
            entry_zone = (round(current, 2), round(current, 2))
    try:
        from config import QuantConfig as _QC
        _atr_mult = _QC.ATR_K_STOP
    except Exception:
        _atr_mult = 2.0
    # fix_07 任務4：賣出族 → 出場計畫版型（is_exit）。壓力位作持有者停損。
    _ac_u = str(action_code).upper()
    _is_exit = _ac_u.startswith('SELL') or _ac_u in ('EXIT', 'TAKE_PROFIT')
    _res1 = _num(sr.get('resistance1'))
    plan = {
        'is_exit':      _is_exit,
        'entry_zone':   entry_zone,
        'stop_loss':    pt.get('stop_loss'),
        'stop_atr_mult': _atr_mult,
        'target':       pt.get('target_price'),
        'target2':      None,
        'rr':           pt.get('rr_ratio'),
        # build_prompt_20：建議部位改由 portfolio_engine 決定（見下方 _position_block）
        'position_pct': None,
        # 出場版型專用：現價（出場參考）、上方壓力（持有者停損）、下檔目標
        'exit_ref':     current,
        'holder_stop':  (_res1 if (_res1 is not None and current is not None and _res1 > current) else None),
        'downside_ref': pt.get('target_price'),
    }
    plan.update(_position_block(grade, _is_exit, result, current))

    # ── 量價分析（05 區）──
    va = result.get('volume_analysis', {}) or {}
    vp = result.get('volume_price', {}) or {}
    vp_signals = [s.get('name') or s.get('code') for s in (vp.get('signals') or [])] if vp.get('available') else []

    # fix_07 任務5：hist Volume 單位為「股」，統一 // 1000 轉「張」再輸出
    def _to_lots(x):
        v = _num(x)
        return int(v // 1000) if v is not None else None
    volume_profile = {
        'today_volume': _to_lots(va.get('current_volume')),   # 張
        'avg_volume':   _to_lots(va.get('avg_volume')),       # 張（20日）
        'vol_ratio':    va.get('volume_ratio'),
        'volume_zscore': tech.get('volume_zscore'),
        'volume_trend': va.get('volume_trend'),
        'spike_signal': va.get('spike_signal'),
        'vp_signals':   vp_signals,
        'vp_score':     vp.get('vp_score') if vp.get('available') else None,
    }

    # ── 籌碼近10日明細 + 摘要（只讀 DB，不重算連買）──
    chip_flow = result.get('chip_flow', {}) or {}
    chip_detail = []
    try:
        from chip_data_manager import get_chip_manager
        _as_of = result.get('analysis_date') if result.get('is_historical') else None
        mgr = get_chip_manager()
        chip_detail = mgr.get_daily_detail(symbol, days=10, as_of=_as_of)
    except Exception:
        chip_detail = []
    chip_summary = {
        'foreign_days':  chip_flow.get('foreign_consecutive_days'),
        'trust_days':    chip_flow.get('trust_consecutive_days'),
        'reliable':      chip_flow.get('data_reliable'),
        'missing_dates': chip_flow.get('missing_dates', []),
        'available':     chip_flow.get('available', False),
    }

    # ── 證據明細（07 區）──
    rev = result.get('revenue_momentum', {}) or {}
    tf  = result.get('timeframe_profile', {}) or {}
    evidence = {
        'pth':          tech.get('pth_52w'),
        'dist_from_high': (round((tech['pth_52w'] - 1) * 100, 1)
                           if _num(tech.get('pth_52w')) is not None else None),
        'dist_from_low': tech.get('dist_from_low_52w'),
        'rs_rank':      result.get('rs_rank_60d'),
        'rs_score':     (result.get('relative_strength', {}) or {}).get('rs_score'),
        'triggers':     list(timing.get('triggers') or []),
        'timeframe':    {'short_swing': tf.get('short_swing_ready'),
                         'position_trend': tf.get('position_trend_ready')},
        'revenue_yoy':  rev.get('revenue_yoy'),
        'rev_12m_high': rev.get('is_12m_high'),
        'combo_tag':    rev.get('combo_label') or '',
        # build_prompt_08：所屬題材（顯示用）
        'theme':        result.get('theme_info', {}) or {},
    }

    # ── 警示彙整 ──
    warnings = []
    for w in (dm.get('warning_message'), rec.get('warning_message')):
        if w and w not in warnings:
            warnings.append(w)
    if chip_summary['reliable'] is False:
        _md = chip_summary.get('missing_dates') or []
        warnings.append(f'籌碼資料不完整（缺 {len(_md)} 日），已排除於連買計算')
    if result.get('price_anomaly'):
        warnings.append('資料異常：漲跌幅超過±10%漲跌停，即時價與昨收可能未對齊')

    # ── fix_07 任務2：情緒一致 fail-safe（防回歸最後保險，正常永不觸發）──
    overall_text = rec.get('overall', dm.get('recommendation', '')) or ''
    _ac = str(action_code).upper()
    _ac_sell = _ac.startswith('SELL') or _ac in ('EXIT', 'TAKE_PROFIT')
    _ac_buy  = _ac in ('STRONG_BUY', 'BUY')
    _buy_kw  = ('買進', '進場', '佈局', '加碼')
    _sell_kw = ('賣出', '出場', '減碼', '避開')
    _txt_buy  = any(k in overall_text for k in _buy_kw)
    _txt_sell = any(k in overall_text for k in _sell_kw)
    if (_ac_sell and _txt_buy) or (_ac_buy and _txt_sell):
        _canon = _ACTION_SHORT.get(action_code, '')
        _fixed = f"{_GRADE_LABELS.get(grade, grade)}：{_canon}" if _canon else _GRADE_LABELS.get(grade, grade)
        import logging
        logging.getLogger(__name__).warning(
            "verdict text/action mismatch: symbol=%s action_code=%s overall=%r -> corrected=%r",
            symbol, action_code, overall_text, _fixed)
        overall_text = _fixed
        warnings.insert(0, '文字與裁決不一致已自動校正（以引擎 action_code 為準）')

    return {
        'symbol':       symbol,
        'name':         result.get('name', symbol),
        'grade':        grade,
        'grade_label':  _GRADE_LABELS.get(grade, dm.get('scenario_name', grade)),
        'action_code':  action_code,
        'action_short': _ACTION_SHORT.get(action_code, ''),
        'overall_text': overall_text,
        'score':        dm.get('score'),
        'confidence':   dm.get('confidence', rec.get('confidence', '')),
        'data_date':    result.get('data_time', result.get('analysis_date', '')),
        'scores':       scores,
        'score_notes':  score_notes,
        'term_advice':  term_advice,
        'adjustments':  dm.get('adjustment_trail', []),
        'plan':         plan,
        'volume_profile': volume_profile,
        'chip_detail':  chip_detail,
        'chip_summary': chip_summary,
        # build_prompt_12：籌碼強度四因子（只讀 result，不重算；純顯示不影響裁決）
        'chip_strength': result.get('chip_strength') or {'available': False},
        'evidence':     evidence,
        'warnings':     warnings,
    }


def chip_strength_line(verdict: dict) -> str:
    """
    build_prompt_12：籌碼強度摘要列（報告 06 區上方）。
    缺資料一律顯示 '—'，不報錯、不以 0 充數。
    法人均價明確標註為近似值（當日收盤價，非逐筆成交均價）。
    """
    cs = (verdict or {}).get('chip_strength') or {}
    if not cs.get('available'):
        return "籌碼強度：—（資料不足）"

    st = cs.get('strength') or {}
    co = cs.get('consistency') or {}
    mg = cs.get('margin') or {}
    ac = cs.get('avg_cost') or {}

    z = st.get('combined_z') if st.get('available') else None
    z_txt = f"{z:+.1f}" if isinstance(z, (int, float)) else "—"

    r = co.get('consistency_ratio') if co.get('available') else None
    r_txt = f"{r:.0%}（{co.get('dominant_direction', '')}）" if isinstance(r, (int, float)) else "—"

    d_txt = mg.get('divergence_type') if mg.get('available') else "—"

    cost = ac.get('avg_cost_proxy') if ac.get('available') else None
    prem = ac.get('premium_pct') if ac.get('available') else None
    if isinstance(cost, (int, float)):
        c_txt = f"{cost:.2f}≈"       # ≈ 標示近似值
        p_txt = f"{prem:+.1f}%" if isinstance(prem, (int, float)) else "—"
        cost_txt = f"{c_txt} vs 現價 {p_txt}"
    else:
        cost_txt = "—"

    return (f"強度 Z={z_txt} · 一致性 {r_txt} · 融資背離：{d_txt} · 法人均價 {cost_txt}")


def watchlist_cell(verdict: dict) -> str:
    """首頁 watchlist「量化建議」欄字串：{等級} {簡短action}。"""
    g = verdict.get('grade', '')
    act = verdict.get('action_short', '') or verdict.get('overall_text', '')
    return f"{g} {act}".strip()
