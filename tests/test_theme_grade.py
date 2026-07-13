from decision_engine import ThreeLayerEngine
import config


def _theme_c_result(is_top=True, is_leader=False):
    # A signal that lands at grade C (bullish env + healthy RSI/bias, no stronger trigger)
    return {
        'symbol': 'C', 'current_price': 100.0,
        'technical': {'ma5': 99, 'ma20': 98, 'ma60': 96, 'rsi': 55, 'atr': 2.0,
                      'bb_squeeze': False},
        'relative_strength': {'rs_score': 60, 'vs_market': 1},
        'market_regime': {'available': True, 'trend_direction': '多頭', 'adx': 30},
        'chip_flow': {'available': True, 'data_reliable': True, 'consecutive_buy_days': 0},
        'mean_reversion': {'available': True, 'bias_analysis': {'bias_20': 1.0}},
        'wave_analysis': {'available': True, 'is_bullish_env': True},
        'pattern_analysis': {}, 'volume_price': {},
        'theme_momentum': {'is_top_theme': is_top, 'is_theme_leader': is_leader,
                           'theme_rank_pct': 95},
    }


def test_theme_nudges_C_to_B_when_enabled(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'THEME_GRADE_ENABLED', True)
    t = ThreeLayerEngine.score_timing(_theme_c_result(is_top=True))
    assert t['grade'] == 'B'


def test_theme_no_effect_when_disabled():
    t = ThreeLayerEngine.score_timing(_theme_c_result(is_top=True))
    assert t['grade'] == 'C'


def test_theme_no_nudge_when_not_top_or_leader(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'THEME_GRADE_ENABLED', True)
    t = ThreeLayerEngine.score_timing(_theme_c_result(is_top=False, is_leader=False))
    assert t['grade'] == 'C'
