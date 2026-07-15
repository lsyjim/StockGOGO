"""
tests/test_r_track.py - build_prompt_12 R 軌獨立評估單元測試

驗收重點：
- R_TRACK_ENABLED 預設關 → 全 None（動能管線零影響）。
- 盤整→R-TRADE；多頭/空頭→R-WATCH；未觸發→None。
- r_strength：strong 直通；moderate+1 reason→moderate；moderate+>=2 reasons→strong。
- _nth_trading_day_after：第 n 個未來交易日 / 不足→None。
- 紅線：不回傳、也不改動 grade/action_code，且不 mutate 傳入的 result。
"""
import pytest

from config import QuantConfig
import r_track
from r_track import evaluate_r_track, _nth_trading_day_after


def _res(triggered=True, trend='盤整', strength='moderate', reasons=None, available=True):
    return {'grade': 'SELL', 'action_code': 'SELL',
            'market_regime': {'available': available, 'trend_direction': trend},
            'mean_reversion': {'left_buy_signal': {'triggered': triggered, 'strength': strength,
                               'trigger_reasons': reasons if reasons is not None else ['負乖離', 'RSI超賣']}}}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(QuantConfig, 'R_TRACK_ENABLED', True, raising=False)


# ---------------------------------------------------------------- disabled default
def test_disabled_by_default_all_none_even_when_triggered(monkeypatch):
    monkeypatch.setattr(QuantConfig, 'R_TRACK_ENABLED', False, raising=False)
    out = evaluate_r_track(_res(triggered=True), '2026-07-15')
    assert out == {'r_signal': None, 'r_strength': None, 'r_exit_date': None}


# ---------------------------------------------------------------- regime routing
def test_enabled_triggered_range_regime_is_r_trade(enabled):
    out = evaluate_r_track(_res(trend='盤整'), '2026-07-15')
    assert out['r_signal'] == 'R-TRADE'


def test_enabled_triggered_bull_regime_is_r_watch(enabled):
    out = evaluate_r_track(_res(trend='多頭'), '2026-07-15')
    assert out['r_signal'] == 'R-WATCH'


def test_enabled_triggered_bear_regime_is_r_watch(enabled):
    out = evaluate_r_track(_res(trend='空頭'), '2026-07-15')
    assert out['r_signal'] == 'R-WATCH'


def test_enabled_not_triggered_is_none(enabled):
    out = evaluate_r_track(_res(triggered=False, trend='盤整'), '2026-07-15')
    assert out == {'r_signal': None, 'r_strength': None, 'r_exit_date': None}


def test_regime_unavailable_no_signal(enabled):
    out = evaluate_r_track(_res(trend='盤整', available=False), '2026-07-15')
    assert out['r_signal'] is None


# ---------------------------------------------------------------- strength
def test_strength_strong_passthrough(enabled):
    out = evaluate_r_track(_res(strength='strong', reasons=['僅一個']), '2026-07-15')
    assert out['r_strength'] == 'strong'


def test_strength_moderate_single_reason(enabled):
    out = evaluate_r_track(_res(strength='moderate', reasons=['負乖離']), '2026-07-15')
    assert out['r_strength'] == 'moderate'


def test_strength_moderate_two_reasons_promoted_to_strong(enabled):
    out = evaluate_r_track(_res(strength='moderate', reasons=['負乖離', 'RSI超賣']), '2026-07-15')
    assert out['r_strength'] == 'strong'


# ---------------------------------------------------------------- exit date helper
def _tdays():
    # 由舊到新，含未來日；as_of=2026-07-15
    return ['2026-07-13', '2026-07-14', '2026-07-15',
            '2026-07-16', '2026-07-17', '2026-07-20', '2026-07-21',
            '2026-07-22', '2026-07-23', '2026-07-24', '2026-07-27',
            '2026-07-28', '2026-07-29', '2026-07-30', '2026-07-31']


def test_nth_trading_day_after_10th():
    days = _tdays()
    # as_of 之後：16,17,20,21,22,23,24,27,28,29 → 第 10 個 = 2026-07-29
    assert _nth_trading_day_after('2026-07-15', days, 10) == '2026-07-29'


def test_nth_trading_day_after_insufficient_returns_none():
    days = ['2026-07-15', '2026-07-16', '2026-07-17']
    assert _nth_trading_day_after('2026-07-15', days, 10) is None


def test_nth_trading_day_after_empty_returns_none():
    assert _nth_trading_day_after('2026-07-15', [], 10) is None


def test_exit_date_wired_through_evaluate(enabled):
    out = evaluate_r_track(_res(trend='盤整'), '2026-07-15', trading_days=_tdays())
    assert out['r_signal'] == 'R-TRADE'
    assert out['r_exit_date'] == '2026-07-29'


def test_exit_date_none_when_no_trading_days(enabled):
    out = evaluate_r_track(_res(trend='盤整'), '2026-07-15')
    assert out['r_exit_date'] is None


# ---------------------------------------------------------------- RED LINE
def test_red_line_returns_no_momentum_fields_and_does_not_mutate(enabled):
    result = _res(trend='盤整')
    original = {'grade': result['grade'], 'action_code': result['action_code']}
    out = evaluate_r_track(result, '2026-07-15', trading_days=_tdays())
    # 回傳 dict 不得含任何動能欄位
    assert set(out.keys()) == {'r_signal', 'r_strength', 'r_exit_date'}
    assert 'grade' not in out and 'action_code' not in out
    # 傳入 result 的動能欄位不得被修改
    assert result['grade'] == original['grade']
    assert result['action_code'] == original['action_code']
    # 也不得偷偷寫入 R 欄位到 result
    assert 'r_signal' not in result
