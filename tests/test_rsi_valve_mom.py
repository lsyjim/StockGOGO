from decision_engine import ThreeLayerEngine
import config


def _hot_momentum_result(rsi, vol_ratio=1.5, volume_zscore=1.0):
    # momentum: rs 90 + stacked MAs; strong breakout gives A; hot RSI + positive bias
    return {
        'symbol': 'H', 'current_price': 120.0,
        'technical': {'ma5': 118, 'ma20': 110, 'ma60': 100, 'rsi': rsi,
                      'atr': 4.8, 'pth_52w': 0.99, 'breakout_55': True,
                      'vol_ratio': vol_ratio, 'volume_zscore': volume_zscore},
        'relative_strength': {'rs_score': 90, 'vs_market': 8},
        'market_regime': {'available': True, 'trend_direction': '多頭', 'adx': 30},
        'chip_flow': {'available': True, 'data_reliable': True, 'consecutive_buy_days': 4},
        'mean_reversion': {'available': True, 'bias_analysis': {'bias_20': 22.0}},
        'wave_analysis': {'available': True,
                          'breakout_signal': {'detected': True, 'volume_confirmed': True}},
        'pattern_analysis': {}, 'volume_price': {},
    }


# 註：任務2 豁免經 A/B 否決，預設 SAFETY_VALVE_RSI_MOM 已還原為 85（機制預設關）。
# 下列測試以 monkeypatch 顯式啟用（=92）驗證「機制本身正確」，與預設無關。
def test_valve_holds_A_for_healthy_momentum_between_85_and_92(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'SAFETY_VALVE_RSI_MOM', 92)
    t = ThreeLayerEngine.score_timing(_hot_momentum_result(rsi=88))
    assert t['grade'] == 'A', "RSI 88 healthy momentum should stay A under 92 valve"


def test_valve_downgrades_above_92(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'SAFETY_VALVE_RSI_MOM', 92)
    t = ThreeLayerEngine.score_timing(_hot_momentum_result(rsi=95))
    assert t['grade'] == 'B', "RSI 95 exceeds even the momentum valve"


def test_valve_default_off_downgrades_healthy_momentum_at_88():
    # 預設還原後（RSI_MOM=85）：健康動能股 RSI88 仍降 B（機制預設關 = pre-bp11 行為）
    t = ThreeLayerEngine.score_timing(_hot_momentum_result(rsi=88))
    assert t['grade'] == 'B', "default (reverted) 85 valve downgrades RSI 88"


def test_valve_downgrades_unhealthy_volume_at_88():
    # not healthy (vol_ratio<1 AND zscore<=0) → threshold stays 85 → 88 downgrades
    t = ThreeLayerEngine.score_timing(_hot_momentum_result(rsi=88, vol_ratio=0.8, volume_zscore=-0.5))
    assert t['grade'] == 'B', "unhealthy volume keeps the 85 valve → 88 downgrades"
