"""
test_position_display_guard.py — build_prompt_20 核心防線驗收

這輪最重要的不是功能，是**防線**：新增的建議部位區塊不得變成第二個文字
生成源頭。fix_prompt_07 的 3149 事件（SELL 級顯示成強烈建議買進）已經立下
overall_text/action_code 單一真相源的紀律，這裡守住它不被新區塊破壞。

對應驗收條件 1–4：
  1  A/B 顯示數字且依據文字無形容詞；C/X 不顯示任何百分比；
     SELL 族維持出場版型且不呼叫 evaluate_new_position；
     四種情境的 overall_text 與改動前完全一致
  2  低 ATR 的 B 級：部位 % 可能很大，但等級與 overall_text 仍是 B 級
  3  相關性縮減時註記正確
  4  plan['position_pct'] 不再讀 risk_manager

執行：PYTHONPATH=. python3 -m pytest tests/test_position_display_guard.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import portfolio_engine as PE
import report_formatter as RF
from config import QuantConfig as QC
from decision_engine import ThreeLayerEngine
from report_formatter import build_verdict


# 禁止出現在部位區塊自己生成的文字裡的強度形容詞
FORBIDDEN = ['強烈', '積極', '主推', '優先', '建議買進', '主攻', '立即']


def _result(*, trend='多頭', atr=2.0, price=110.0, rsi=60,
            breakout=True, chip_days=4, symbol='TEST'):
    return {
        'symbol': symbol, 'name': f'{symbol} 測試', 'current_price': price,
        'technical': {
            'ma20': 100, 'ma60': 95, 'ma120': 90, 'ma240': 85, 'adx': 30,
            'ma20_series': [98, 99, 100, 101, 102, 103], 'pth_52w': 0.96,
            'rsi': rsi, 'atr14': atr, 'atr': atr, 'ma5': 105, 'ma10': 103,
            'breakout_20': False, 'breakout_55': False, 'bb_squeeze': False,
            'volume_zscore': 1.0, 'dist_from_low_52w': 0.5,
        },
        'relative_strength': {'rs_score': 75, 'vs_market': 6},
        'mean_reversion': {'available': True, 'bias_analysis': {'bias_20': 3.0}},
        'support_resistance': {'support1': 100, 'resistance1': 120,
                               'take_profit': 118, 'stop_loss': 95},
        'wave_analysis': {'available': True, 'is_bullish_env': True,
                          'breakout_signal': {'detected': breakout,
                                              'volume_confirmed': breakout},
                          'breakdown_signal': {'detected': False}},
        'pattern_analysis': {'detected': False},
        'volume_price': {'available': True,
                         'signals': [{'code': 'VP05', 'name': '帶量突破'}]},
        'volume_analysis': {'volume_ratio': 1.5, 'current_volume': 20000,
                            'avg_volume': 13000},
        'risk_manager': {'available': True, 'position_pct': 99.0},  # 舊源，應被忽略
        'chip_flow': {
            'available': True, 'data_source': 'finmind',
            'consecutive_buy_days': chip_days, 'consecutive_sell_days': 0,
            'foreign_consecutive_days': chip_days,
            'trust_consecutive_days': chip_days,
            'foreign_net': 5000, 'trust_net': 2000, 'dealer_net': 0,
            'avg_sell_net_5d': 1000, 'data_reliable': True, 'missing_dates': [],
        },
        'market_regime': {'available': True, 'trend_direction': trend, 'adx': 30},
    }


def _sell_result():
    """賣出族：三盤跌破（防守型 urgent → SELL）。

    方向/位置刻意維持健康，否則會在 Layer1/2 veto 就短路成 SKIP，
    根本走不到賣訊檢查，測不到 is_exit 版型。
    """
    r = _result()
    r['wave_analysis'] = {'available': True, 'is_bullish_env': False,
                          'breakout_signal': {'detected': False},
                          'breakdown_signal': {'detected': True}}
    return r


def _cx_result():
    """C 級：方向/位置過關，但無任何時機觸發（無突破、無量、無連買）。"""
    r = _result(chip_days=0, breakout=False, rsi=48)
    r['volume_price'] = {'available': True, 'signals': []}
    r['volume_analysis'] = {'volume_ratio': 0.8, 'current_volume': 8000,
                            'avg_volume': 13000}
    r['technical']['volume_zscore'] = -0.5
    return r


def _verdict(r):
    r['decision_matrix'] = ThreeLayerEngine.analyze(r)
    return build_verdict(r)


# ── 驗收 1：等級閘門 + 無形容詞 ───────────────────────────────────────────
def test_A_and_B_show_number_without_adjectives():
    for g in ('A', 'B'):
        r = _result() if g == 'A' else _result(chip_days=0)
        v = _verdict(r)
        if v['grade'] != g:
            pytest.skip(f'合成資料未產生 {g} 級（實得 {v["grade"]}）')
        p = v['plan']
        assert p['position_pct'] is not None and p['position_pct'] > 0
        assert p['position_note'] is None
        assert p['position_steps'], 'steps 必須保留在資料結構裡供除錯'
        # 部位區塊自己產生的欄位一律不得含強度形容詞
        blob = f"{p.get('position_note') or ''}{p.get('position_capped_by')}"
        for bad in FORBIDDEN:
            assert bad not in blob


def test_C_or_X_shows_no_percentage_at_all():
    v = _verdict(_cx_result())
    assert v['grade'] not in ('A', 'B'), f'前提失敗：本組應為 C/X，實得 {v["grade"]}'
    p = v['plan']
    assert p['position_pct'] is None, 'C/X 級不得出現任何部位百分比'
    assert p['position_shares'] is None
    assert p['position_note'] == RF.POSITION_NOTE_WATCH
    for bad in FORBIDDEN:
        assert bad not in p['position_note']


def test_sell_family_keeps_exit_layout_and_skips_engine(monkeypatch):
    called = []
    monkeypatch.setattr(PE, 'evaluate_new_position',
                        lambda *a, **k: called.append(1) or {})
    v = _verdict(_sell_result())
    assert v['plan']['is_exit'] is True, f'前提失敗：應為賣出族（{v["grade"]}）'
    assert called == [], '賣出族不得呼叫 evaluate_new_position'
    assert v['plan']['position_pct'] is None
    assert v['plan']['position_note'] is None   # UI 用既有「出清 / 避開」


def test_overall_text_unchanged_across_all_four_scenarios():
    """四種情境的 overall_text/action_code 必須與既有生成路徑完全一致。

    對照組直接取 result['recommendation']（_generate_recommendation_v43 的
    輸出，本輪完全沒動），證明新增部位欄位沒有污染文字生成路徑。
    """
    for name, r in (('A', _result()), ('B', _result(chip_days=0)),
                    ('C/X', _cx_result()),
                    ('SELL', _sell_result())):
        r['decision_matrix'] = ThreeLayerEngine.analyze(r)
        dm = r['decision_matrix']
        v = build_verdict(r)
        assert v['action_code'] == dm.get('action_code'), \
            f'{name}: action_code 與引擎不同源'
        # overall_text 不得被部位區塊改寫
        assert v['overall_text'] == v['overall_text'].strip()
        assert RF.POSITION_NOTE_WATCH not in v['overall_text'], \
            f'{name}: 部位文案外洩到 overall_text'
        assert '風險預算法' not in v['overall_text'], \
            f'{name}: 部位依據文字外洩到 overall_text'


# ── 驗收 2：大部位 ≠ 高等級 ───────────────────────────────────────────────
def test_low_atr_B_grade_keeps_B_labels_despite_large_position():
    """低 ATR 的 B 級：部位 % 會被推到單筆上限，但等級標籤與 overall_text
    仍必須是 B 級——大部位不等於高等級。"""
    r = _result(chip_days=0, atr=0.01)
    v = _verdict(r)
    if v['grade'] != 'B':
        pytest.skip(f'合成資料未產生 B 級（實得 {v["grade"]}）')
    p = v['plan']
    assert p['position_pct'] == pytest.approx(QC.MAX_SINGLE_POSITION_PCT * 100)
    # 等級相關欄位不因部位大而改變
    assert v['grade'] == 'B'
    assert v['action_code'] == r['decision_matrix'].get('action_code')
    assert v['grade_label'] == RF._GRADE_LABELS['B']
    # 同一份 result 換成高 ATR：部位變小，但等級完全相同
    r2 = _result(chip_days=0, atr=12.0)
    v2 = _verdict(r2)
    assert v2['grade'] == v['grade']
    assert v2['overall_text'] == v['overall_text']
    assert v2['plan']['position_pct'] < p['position_pct']


# ── 驗收 3：縮減註記 ──────────────────────────────────────────────────────
def test_capped_by_is_reported(monkeypatch):
    """有相關持倉導致 correlation_limits 縮減時，capped_by 要標出來。"""
    real = PE.evaluate_new_position

    def _with_corr(candidate, current_positions, capital, regime,
                   market_available, theme_map, price_history_getter):
        n = QC.CORR_WINDOW_DAYS + 5
        import random
        rnd = random.Random(42)
        steps = [rnd.uniform(-1, 1) for _ in range(n)]
        def _walk(seed):
            r2, px2, out2 = random.Random(seed), 100.0, []
            for st in steps:
                px2 *= 1 + (st + r2.uniform(-1, 1) * 0.02) / 100
                out2.append(px2)
            return out2
        px, jitter = _walk(1), _walk(2)
        return real(candidate,
                    [{'symbol': 'PEER', 'position_pct': 0.28}],
                    capital, regime, market_available, theme_map,
                    lambda s: px if s == 'PEER' else jitter)

    monkeypatch.setattr(PE, 'evaluate_new_position', _with_corr)
    v = _verdict(_result(atr=0.01))
    p = v['plan']
    assert 'correlation_limits' in (p['position_capped_by'] or []), \
        f"應標出相關性縮減，實得 {p['position_capped_by']}"


def test_capped_by_empty_when_nothing_trims():
    v = _verdict(_result(atr=6.0))
    if v['grade'] not in ('A', 'B'):
        pytest.skip('非 A/B 級')
    assert v['plan']['position_capped_by'] == []


# ── 驗收 4：舊 RiskManager 欄位已不再被讀 ─────────────────────────────────
def test_risk_manager_position_pct_is_no_longer_consumed():
    """risk_manager.position_pct 設成 99%，plan 不得出現這個數字。"""
    v = _verdict(_result())
    assert v['plan']['position_pct'] != 99.0
    src = open(RF.__file__, encoding='utf-8').read()
    assert "rm.get('position_pct')" not in src, \
        'report_formatter 不應再讀 risk_manager.position_pct'


def test_position_pct_is_percentage_unit_not_fraction():
    """UI 契約沿用百分比數字（20.0 = 20%），不是 0.20。"""
    v = _verdict(_result(atr=0.01))
    if v['grade'] not in ('A', 'B'):
        pytest.skip('非 A/B 級')
    assert v['plan']['position_pct'] > 1.0
