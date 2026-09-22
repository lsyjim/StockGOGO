"""
test_portfolio_engine.py — build_prompt_19 任務1 驗收

對應驗收條件 4–9：
  4  position_sizing：低ATR > 高ATR 部位；MAX_SINGLE_POSITION_PCT 封頂
  5  gross_exposure_cap：三 regime 各自值、market_available=False fallback
  6  concentration_limits：同題材 25% + 15% → 縮到剛好 30%
  7  correlation_limits：高相關集群受限；資料不足不誤判
  8  evaluate_new_position：全通過／被縮減／被縮到 rejected 三種案例
  9  所有常數都取自 config.QuantConfig，不 hardcode 在 portfolio_engine

執行：PYTHONPATH=. python3 -m pytest tests/test_portfolio_engine.py -q
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import portfolio_engine as PE
from config import QuantConfig as QC


# ── 驗收 4：position_sizing ───────────────────────────────────────────────
def test_low_atr_gets_bigger_position_than_high_atr():
    """同 A 級、同資金、同價格：低 ATR → 部位較大，高 ATR → 部位較小。"""
    low = PE.position_sizing('A', capital=1_000_000, entry_price=100, atr=1.0)
    high = PE.position_sizing('A', capital=1_000_000, entry_price=100, atr=8.0)
    assert low['position_pct'] > high['position_pct']
    assert low['shares'] > high['shares']
    # 高 ATR 這檔不該被封頂（用來確認比較的是風險預算而非上限）
    assert high['capped'] is False


def test_risk_pct_follows_grade():
    """A > B > C 的風險預算，且數值取自 config。"""
    kw = dict(capital=1_000_000, entry_price=100, atr=5.0)
    a = PE.position_sizing('A', **kw)
    b = PE.position_sizing('B', **kw)
    c = PE.position_sizing('C', **kw)
    assert a['risk_pct_used'] == QC.RISK_PCT_BY_GRADE['A']
    assert b['risk_pct_used'] == QC.RISK_PCT_BY_GRADE['B']
    assert c['risk_pct_used'] == QC.RISK_PCT_BY_GRADE['C']
    assert a['position_pct'] > b['position_pct'] > c['position_pct']


def test_unknown_grade_falls_back_to_most_conservative():
    out = PE.position_sizing('X', capital=1_000_000, entry_price=100, atr=5.0)
    assert out['risk_pct_used'] == 0.005


def test_max_single_position_cap_is_enforced():
    """ATR 極低 → 風險預算法會算出超大部位 → 必須被 MAX_SINGLE_POSITION_PCT 封頂。"""
    out = PE.position_sizing('A', capital=1_000_000, entry_price=100, atr=0.01)
    assert out['capped'] is True
    assert out['position_pct'] == pytest.approx(QC.MAX_SINGLE_POSITION_PCT)
    # 封頂後 shares / position_value 必須與封頂後的 pct 自洽
    assert out['position_value'] == pytest.approx(
        QC.MAX_SINGLE_POSITION_PCT * 1_000_000)
    assert out['shares'] == pytest.approx(out['position_value'] / 100)


def test_atr_missing_falls_back_to_fixed_amount():
    """atr 為 None / <=0 → fallback 成固定金額法（capital*risk_pct/entry_price）。"""
    for bad in (None, 0, -1.0):
        out = PE.position_sizing('B', capital=1_000_000, entry_price=100, atr=bad)
        assert out['stop_distance_per_share'] is None
        assert out['shares'] == pytest.approx(1_000_000 * QC.RISK_PCT_BY_GRADE['B'] / 100)
        assert out['fallback'] is True


def test_stop_distance_uses_config_atr_k_stop():
    out = PE.position_sizing('B', capital=1_000_000, entry_price=100, atr=3.0)
    assert out['stop_distance_per_share'] == pytest.approx(QC.ATR_K_STOP * 3.0)


def test_risk_pct_override_wins():
    out = PE.position_sizing('C', capital=1_000_000, entry_price=100, atr=5.0,
                             risk_pct_override=0.02)
    assert out['risk_pct_used'] == 0.02


def test_invalid_entry_price_returns_zero_position():
    out = PE.position_sizing('A', capital=1_000_000, entry_price=0, atr=2.0)
    assert out['position_pct'] == 0
    assert out['shares'] == 0


# ── 驗收 5：gross_exposure_cap ────────────────────────────────────────────
def test_gross_exposure_by_regime():
    assert PE.gross_exposure_cap('多頭') == 1.00
    assert PE.gross_exposure_cap('盤整') == 0.70
    assert PE.gross_exposure_cap('空頭') == 0.40


def test_gross_exposure_unavailable_falls_back_to_range():
    assert PE.gross_exposure_cap('多頭', market_available=False) == 0.70
    assert PE.gross_exposure_cap('未知') == 0.70
    assert PE.gross_exposure_cap(None) == 0.70


# ── 驗收 6：concentration_limits ──────────────────────────────────────────
THEME_MAP = {'themes': {'AI': ['1111', '2222', '3333'], '航運': ['9001', '9002']}}


def test_theme_concentration_trims_to_cap():
    """同題材已有 25%，candidate 再 15% 會超過 30% → 縮到剛好 30%。"""
    pos = [{'symbol': '1111', 'position_pct': 0.15},
           {'symbol': '2222', 'position_pct': 0.10}]
    out = PE.concentration_limits(pos, '3333', 0.15, THEME_MAP)
    assert out['capped'] is True
    assert out['theme'] == 'AI'
    assert out['theme_total_before'] == pytest.approx(0.25)
    assert out['approved_pct'] == pytest.approx(0.05)
    assert out['theme_total_after'] == pytest.approx(QC.MAX_THEME_EXPOSURE_PCT)


def test_theme_under_cap_passes_through():
    pos = [{'symbol': '1111', 'position_pct': 0.05}]
    out = PE.concentration_limits(pos, '3333', 0.10, THEME_MAP)
    assert out['capped'] is False
    assert out['approved_pct'] == pytest.approx(0.10)


def test_symbol_without_theme_is_unconstrained():
    pos = [{'symbol': '1111', 'position_pct': 0.28}]
    out = PE.concentration_limits(pos, '8888', 0.15, THEME_MAP)
    assert out['theme'] is None
    assert out['capped'] is False
    assert out['approved_pct'] == pytest.approx(0.15)


def test_theme_already_full_gives_zero():
    pos = [{'symbol': '1111', 'position_pct': 0.30}]
    out = PE.concentration_limits(pos, '3333', 0.10, THEME_MAP)
    assert out['approved_pct'] == pytest.approx(0.0)
    assert out['capped'] is True


def test_accepts_flat_theme_map_too():
    """theme_map 可直接傳內層 {題材: [代號]}，不必一定包 'themes'。"""
    out = PE.concentration_limits([], '3333', 0.10, THEME_MAP['themes'])
    assert out['theme'] == 'AI'


# ── 驗收 7：correlation_limits ────────────────────────────────────────────
def _steps(n, seed):
    """n 個日報酬步長（%）。注意 Random 只能建一次——建在 comprehension
    裡會每圈重播同一個 seed，做出常數序列。"""
    import random
    rnd = random.Random(seed)
    return [rnd.uniform(-1, 1) for _ in range(n)]


def _series(n, seed, noise=0.0, base=None):
    """合成收盤價序列。共用同一組 base（noise 很小）→ 兩檔近乎同步（高相關）。"""
    import random
    rnd = random.Random(seed)
    steps = base if base is not None else _steps(n, seed)
    px, out = 100.0, []
    for s in steps:
        px *= 1 + (s + (rnd.uniform(-1, 1) * noise)) / 100
        out.append(px)
    return out


def _getter_factory(mapping):
    def g(sym):
        return mapping.get(sym)
    return g


def test_correlated_cluster_is_capped():
    """兩檔高度相關（同一組 base 走勢）→ 集群總曝險受 MAX_CORRELATED_EXPOSURE_PCT 限制。"""
    n = QC.CORR_WINDOW_DAYS + 5
    base = _steps(n, 7)
    mapping = {'AAA': _series(n, 1, noise=0.02, base=base),
               'BBB': _series(n, 2, noise=0.02, base=base)}
    pos = [{'symbol': 'AAA', 'position_pct': 0.25}]
    out = PE.correlation_limits(pos, 'BBB', 0.15, _getter_factory(mapping))
    assert 'AAA' in out['correlated_with']
    assert out['capped'] is True
    assert out['approved_pct'] == pytest.approx(0.05)
    assert out['cluster_total_after'] == pytest.approx(QC.MAX_CORRELATED_EXPOSURE_PCT)


def test_uncorrelated_pair_is_not_capped():
    n = QC.CORR_WINDOW_DAYS + 5
    mapping = {'AAA': _series(n, 11), 'BBB': _series(n, 99)}
    pos = [{'symbol': 'AAA', 'position_pct': 0.25}]
    out = PE.correlation_limits(pos, 'BBB', 0.15, _getter_factory(mapping))
    assert out['correlated_with'] == []
    assert out['capped'] is False
    assert out['approved_pct'] == pytest.approx(0.15)


def test_insufficient_history_is_treated_as_uncorrelated():
    """任一方資料 < CORR_WINDOW_DAYS → 視為不相關，不得誤判成集群。"""
    n = QC.CORR_WINDOW_DAYS + 5
    base = _steps(n, 21)
    short = QC.CORR_WINDOW_DAYS - 1
    mapping = {'AAA': _series(n, 1, base=base),
               'BBB': _series(short, 2, base=base[:short])}   # candidate 資料不足
    pos = [{'symbol': 'AAA', 'position_pct': 0.25}]
    out = PE.correlation_limits(pos, 'BBB', 0.15, _getter_factory(mapping))
    assert out['correlated_with'] == []
    assert out['capped'] is False
    assert out['approved_pct'] == pytest.approx(0.15)


def test_missing_history_getter_result_is_safe():
    mapping = {'AAA': None, 'BBB': None}
    pos = [{'symbol': 'AAA', 'position_pct': 0.25}]
    out = PE.correlation_limits(pos, 'BBB', 0.15, _getter_factory(mapping))
    assert out['capped'] is False
    assert out['approved_pct'] == pytest.approx(0.15)


def test_flat_series_does_not_blow_up():
    """零變異序列 → 相關係數未定義，應視為不相關而非丟例外。"""
    n = QC.CORR_WINDOW_DAYS + 5
    mapping = {'AAA': [100.0] * n, 'BBB': [100.0] * n}
    pos = [{'symbol': 'AAA', 'position_pct': 0.25}]
    out = PE.correlation_limits(pos, 'BBB', 0.15, _getter_factory(mapping))
    assert out['capped'] is False


# ── 驗收 8：evaluate_new_position 整合 ────────────────────────────────────
def _cand(symbol='8888', grade='B', entry=100.0, atr=4.0):
    return {'symbol': symbol, 'grade': grade, 'entry_price': entry, 'atr': atr}


def _no_history(_sym):
    return None


def test_evaluate_all_layers_pass():
    """四層都不觸發：空持倉、多頭 regime、無題材、無歷史價。"""
    out = PE.evaluate_new_position(_cand(), [], capital=1_000_000,
                                   regime='多頭', market_available=True,
                                   theme_map=THEME_MAP,
                                   price_history_getter=_no_history)
    sized = PE.position_sizing('B', 1_000_000, 100.0, 4.0)['position_pct']
    assert out['rejected'] is False
    assert out['final_pct'] == pytest.approx(sized)
    assert [s['step'] for s in out['steps']] == [
        'position_sizing', 'gross_exposure_cap', 'concentration_limits',
        'correlation_limits']
    assert all(s['capped'] is False for s in out['steps'][1:])
    assert out['final_shares'] == pytest.approx(out['final_pct'] * 1_000_000 / 100.0)


def test_evaluate_trimmed_by_gross_exposure():
    """空頭 regime 上限 40%，已持 38% → candidate 只剩 2% 空間。"""
    pos = [{'symbol': '5555', 'position_pct': 0.38}]
    out = PE.evaluate_new_position(_cand(atr=1.0), pos, capital=1_000_000,
                                   regime='空頭', market_available=True,
                                   theme_map=THEME_MAP,
                                   price_history_getter=_no_history)
    gross = next(s for s in out['steps'] if s['step'] == 'gross_exposure_cap')
    assert gross['capped'] is True
    assert gross['cap'] == pytest.approx(0.40)
    assert out['final_pct'] == pytest.approx(0.02)
    assert out['rejected'] is False


def test_evaluate_trimmed_by_theme():
    pos = [{'symbol': '1111', 'position_pct': 0.25}]
    out = PE.evaluate_new_position(_cand(symbol='3333', atr=1.0), pos,
                                   capital=1_000_000, regime='多頭',
                                   market_available=True, theme_map=THEME_MAP,
                                   price_history_getter=_no_history)
    theme = next(s for s in out['steps'] if s['step'] == 'concentration_limits')
    assert theme['capped'] is True
    assert out['final_pct'] == pytest.approx(0.05)


def test_evaluate_rejected_when_no_headroom():
    """空頭上限 40%，已持滿 40% → 無空間，rejected=True。"""
    pos = [{'symbol': '5555', 'position_pct': 0.40}]
    out = PE.evaluate_new_position(_cand(), pos, capital=1_000_000,
                                   regime='空頭', market_available=True,
                                   theme_map=THEME_MAP,
                                   price_history_getter=_no_history)
    assert out['rejected'] is True
    assert out['final_pct'] == pytest.approx(0.0)
    assert out['final_shares'] == 0


def test_evaluate_takes_the_strictest_layer():
    """多層同時觸發時，最終 pct 必須等於各層核准值的最小者。"""
    n = QC.CORR_WINDOW_DAYS + 5
    base = _steps(n, 3)
    mapping = {'1111': _series(n, 1, noise=0.02, base=base),
               '3333': _series(n, 2, noise=0.02, base=base)}
    pos = [{'symbol': '1111', 'position_pct': 0.26}]
    out = PE.evaluate_new_position(_cand(symbol='3333', atr=1.0), pos,
                                   capital=1_000_000, regime='多頭',
                                   market_available=True, theme_map=THEME_MAP,
                                   price_history_getter=_getter_factory(mapping))
    # 題材上限 30% - 26% = 4%；相關集群上限 30% - 26% = 4%；取最嚴格
    assert out['final_pct'] == pytest.approx(0.04)
    approved = [s['approved_pct'] for s in out['steps']]
    assert out['final_pct'] == pytest.approx(min(approved))


def test_evaluate_regime_unavailable_uses_range_cap():
    pos = [{'symbol': '5555', 'position_pct': 0.68}]
    out = PE.evaluate_new_position(_cand(atr=1.0), pos, capital=1_000_000,
                                   regime='多頭', market_available=False,
                                   theme_map=THEME_MAP,
                                   price_history_getter=_no_history)
    gross = next(s for s in out['steps'] if s['step'] == 'gross_exposure_cap')
    assert gross['cap'] == pytest.approx(0.70)
    assert out['final_pct'] == pytest.approx(0.02)


# ── 驗收 9：常數全部來自 config，不 hardcode ──────────────────────────────
def test_constants_come_from_config(monkeypatch):
    """改動 config 的值，portfolio_engine 行為必須跟著變（證明沒有 hardcode）。"""
    monkeypatch.setattr(QC, 'MAX_SINGLE_POSITION_PCT', 0.05)
    out = PE.position_sizing('A', capital=1_000_000, entry_price=100, atr=0.01)
    assert out['position_pct'] == pytest.approx(0.05)

    monkeypatch.setattr(QC, 'GROSS_EXPOSURE_BY_REGIME',
                        {'多頭': 0.9, '盤整': 0.5, '空頭': 0.2})
    assert PE.gross_exposure_cap('空頭') == 0.2
    assert PE.gross_exposure_cap('未知') == 0.5

    monkeypatch.setattr(QC, 'MAX_THEME_EXPOSURE_PCT', 0.10)
    o2 = PE.concentration_limits([{'symbol': '1111', 'position_pct': 0.08}],
                                 '3333', 0.10, THEME_MAP)
    assert o2['approved_pct'] == pytest.approx(0.02)

    monkeypatch.setattr(QC, 'MAX_CORRELATED_EXPOSURE_PCT', 0.10)
    n = QC.CORR_WINDOW_DAYS + 5
    base = _steps(n, 5)
    mapping = {'AAA': _series(n, 1, noise=0.02, base=base),
               'BBB': _series(n, 2, noise=0.02, base=base)}
    o3 = PE.correlation_limits([{'symbol': 'AAA', 'position_pct': 0.08}],
                               'BBB', 0.10, _getter_factory(mapping))
    assert o3['approved_pct'] == pytest.approx(0.02)


def test_no_hardcoded_magic_numbers_in_source():
    """原始碼層級檢查：關鍵數值不得以字面量出現在 portfolio_engine.py。"""
    src = open(PE.__file__, encoding='utf-8').read()
    code = "\n".join(l.split('#')[0] for l in src.splitlines())
    for lit in ('0.015', '0.20', '0.30', '0.70', '0.40', '1.00', '0.7', '60'):
        assert lit not in code, f"portfolio_engine.py 不應 hardcode {lit}"
