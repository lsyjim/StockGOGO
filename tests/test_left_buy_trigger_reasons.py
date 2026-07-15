import numpy as np, pandas as pd
from analyzers import MeanReversionAnalyzer


def _oversold_df():
    # long slow decline then a sharp deep drop → bias_20 very negative, RSI very low, low pierces lower band
    n = 60
    close = np.linspace(200, 150, n).tolist()
    # force the last few bars sharply down to deepen bias & RSI oversold and pierce lower band
    close[-5:] = [140, 132, 124, 116, 108]
    close = np.array(close, dtype=float)
    high = close * 1.01
    low = close * 0.97
    low[-1] = close[-1] * 0.90   # deep low to pierce lower band
    openp = close * 1.005
    vol = np.full(n, 1000.0); vol[-1] = 3000.0
    idx = pd.date_range('2024-01-01', periods=n, freq='B')
    return pd.DataFrame({'Open': openp, 'High': high, 'Low': low, 'Close': close, 'Volume': vol}, index=idx)


def test_left_buy_emits_trigger_reasons_multi():
    df = _oversold_df()
    # analyze() computes bias_analysis then calls _detect_left_buy_signal
    res = MeanReversionAnalyzer.analyze(df)
    lbs = res.get('left_buy_signal', {})
    assert lbs.get('triggered') is True, f"expected oversold trigger, got {lbs}"
    assert 'trigger_reasons' in lbs, "trigger_reasons key must now exist (the bug fix)"
    assert lbs['trigger_reasons'] == lbs.get('conditions_met'), "trigger_reasons mirrors conditions_met"
    assert len(lbs['trigger_reasons']) >= 2, f"double-confirm should yield >=2 reasons: {lbs['trigger_reasons']}"


def test_conditions_met_still_present_backward_comp():
    df = _oversold_df()
    lbs = MeanReversionAnalyzer.analyze(df).get('left_buy_signal', {})
    assert 'conditions_met' in lbs  # unchanged key preserved
