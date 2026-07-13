from decision_engine import ThreeLayerEngine
import config


def _mlite_result(regime_trend):
    return {
        'symbol': 'T', 'current_price': 100.0,
        'technical': {'ma5': 99, 'ma20': 95, 'ma60': 90, 'rsi': 55,
                      'atr': 2.0, 'pth_52w': 0.95},
        'relative_strength': {'rs_score': 85, 'vs_market': 4},
        'market_regime': {'available': True, 'trend_direction': regime_trend, 'adx': 15},
        'chip_flow': {'available': True, 'data_reliable': True,
                      'consecutive_buy_days': 4},
        'mean_reversion': {'available': True, 'bias_analysis': {'bias_20': 1.0}},
        'wave_analysis': {}, 'pattern_analysis': {}, 'volume_price': {},
    }


def _mlite_fired(out):
    return any(isinstance(t, dict) and t.get('stage') == 'M-Lite盤整' and t.get('to') == 'B'
               for t in out.get('adjustment_trail', []))


def test_mlite_grants_B_in_range_when_enabled(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'MLITE_RANGE_ENABLED', True)
    out = ThreeLayerEngine.analyze(_mlite_result('盤整'))
    # 買訊輸出無頂層 'grade' 鍵；grade 反映在 scenario 與 three_layer.timing.grade
    assert _mlite_fired(out)
    assert out.get('scenario') == 'B'
    assert out.get('three_layer', {}).get('timing', {}).get('grade') == 'B'


def test_mlite_LOCKED_in_bear_even_when_enabled(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'MLITE_RANGE_ENABLED', True)
    out = ThreeLayerEngine.analyze(_mlite_result('空頭'))
    assert not _mlite_fired(out), "M-Lite must NEVER fire in bear regime"


def test_mlite_off_by_default():
    out = ThreeLayerEngine.analyze(_mlite_result('盤整'))
    assert not _mlite_fired(out)
