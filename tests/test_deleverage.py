"""
test_deleverage.py — build_prompt_22 驗收

  1  select_position_to_trim()：超標／未超標、多持倉選最舊
  2  限速：嚴重超標時每天最多平倉一筆，不一次砍光
  4  Scenario A 必須與 build_prompt_21 基準逐位重現（唯一變數是減碼）
  6  只新增函式，未改既有四個函式與 config 既有常數

執行：PYTHONPATH=. python3 -m pytest tests/test_deleverage.py -q
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import portfolio_backtest as PB
import portfolio_engine as PE
from config import QuantConfig as QC


def _pos(sym, pct, date):
    return {'symbol': sym, 'position_pct': pct, 'entry_date': date}


# ── 驗收 1：select_position_to_trim ──────────────────────────────────────
def test_returns_none_when_under_cap():
    pos = [_pos('A', 0.10, '2024-01-02'), _pos('B', 0.15, '2024-01-03')]
    assert PE.select_position_to_trim(pos, '空頭') is None   # 25% < 40%


def test_returns_none_when_exactly_at_cap():
    pos = [_pos('A', 0.40, '2024-01-02')]
    assert PE.select_position_to_trim(pos, '空頭') is None   # 恰好 40%，不算超標


def test_returns_none_when_no_positions():
    assert PE.select_position_to_trim([], '空頭') is None
    assert PE.select_position_to_trim(None, '空頭') is None


def test_picks_oldest_when_over_cap():
    pos = [_pos('NEW', 0.20, '2024-03-01'),
           _pos('OLD', 0.20, '2024-01-15'),
           _pos('MID', 0.20, '2024-02-10')]
    out = PE.select_position_to_trim(pos, '空頭')     # 60% > 40%
    assert out is not None
    assert out['symbol'] == 'OLD'
    assert out['entry_date'] == '2024-01-15'
    assert out['reason'] == 'gross_exposure_deleverage'
    assert out['excess_pct'] == pytest.approx(0.60 - 0.40)
    assert out['cap'] == pytest.approx(0.40)


def test_same_date_tie_breaks_by_symbol():
    pos = [_pos('ZZZ', 0.30, '2024-01-15'), _pos('AAA', 0.30, '2024-01-15')]
    out = PE.select_position_to_trim(pos, '空頭')
    assert out['symbol'] == 'AAA', '同日應依代號決定，確保可重現'


def test_cap_follows_regime():
    """同一組持倉，上限隨 regime 變動而有不同判定。"""
    pos = [_pos('A', 0.30, '2024-01-02'), _pos('B', 0.30, '2024-01-03')]  # 60%
    assert PE.select_position_to_trim(pos, '多頭') is None   # 上限 100%，不超標
    assert PE.select_position_to_trim(pos, '盤整') is None   # 上限 70%，不超標
    out = PE.select_position_to_trim(pos, '空頭')            # 上限 40%，超標
    assert out is not None and out['cap'] == pytest.approx(0.40)

    heavy = pos + [_pos('C', 0.25, '2024-01-04')]            # 85%
    assert PE.select_position_to_trim(heavy, '多頭') is None       # 仍在 100% 內
    assert PE.select_position_to_trim(heavy, '盤整') is not None   # 超過 70%


def test_unknown_regime_uses_conservative_fallback():
    pos = [_pos('A', 0.40, '2024-01-02'), _pos('B', 0.35, '2024-01-03')]  # 75%
    out = PE.select_position_to_trim(pos, '未知')
    assert out is not None and out['cap'] == pytest.approx(0.70)
    assert PE.select_position_to_trim(pos, '多頭', market_available=False) is not None


def test_does_not_use_pnl_to_choose():
    """明確排除 P&L 規則：帶上 pnl 欄位也不得影響選擇。"""
    pos = [_pos('OLD', 0.30, '2024-01-01'), _pos('NEW', 0.30, '2024-06-01')]
    pos[0]['pnl'] = +9999
    pos[1]['pnl'] = -9999
    out = PE.select_position_to_trim(pos, '空頭')
    assert out['symbol'] == 'OLD', '應只看年齡，不看損益'


# ── 驗收 2：限速 ─────────────────────────────────────────────────────────
def test_throttle_one_per_day_in_principle():
    """嚴重超標時，單次呼叫只回一筆——一次砍光與否由呼叫端限速決定。"""
    pos = [_pos(f'S{i}', 0.20, f'2024-01-{i+1:02d}') for i in range(5)]  # 100%
    out = PE.select_position_to_trim(pos, '空頭')
    assert out['symbol'] == 'S0'
    # 砍掉最舊的一筆後仍超標（80% > 40%），下一次才會回下一筆
    rest = [p for p in pos if p['symbol'] != 'S0']
    out2 = PE.select_position_to_trim(rest, '空頭')
    assert out2['symbol'] == 'S1'


@pytest.fixture(scope='module')
def sims():
    if not os.path.exists(PB.BASE_TRADES):
        pytest.skip('缺 bp13_step0/trades.csv')
    return (PB.simulate(deleverage=False, verbose=False),
            PB.simulate(deleverage=True, verbose=False))


def test_at_most_one_deleverage_per_day(sims):
    _a, b = sims
    per_day = collections.Counter(
        t['exit_date'] for t in b['trades'] if t.get('exit_reason') == 'deleveraged')
    worst = max(per_day.values()) if per_day else 0
    assert worst <= PB.MAX_DELEVERAGE_PER_DAY, \
        f'某日減碼 {worst} 筆，超過限速 {PB.MAX_DELEVERAGE_PER_DAY}'


def test_deleveraging_actually_happened(sims):
    _a, b = sims
    assert b['stats'].get('deleveraged', 0) > 0


def test_deleveraged_exits_are_early(sims):
    """減碼出場必須早於固定持有期，且出場價是真實收盤價。"""
    _a, b = sims
    dl = [t for t in b['trades'] if t.get('exit_reason') == 'deleveraged']
    assert all(t['held_days'] < PB.HOLDING_DAYS for t in dl)
    assert all(t['exit_price'] > 0 for t in dl)
    book = b['book']
    for t in dl[:50]:
        assert t['exit_price'] == pytest.approx(
            book.close_on(t['symbol'], t['exit_date'])), '應以當日真實收盤價結算'


def test_expired_exits_still_fixed_period(sims):
    _a, b = sims
    ex = [t for t in b['trades'] if t.get('exit_reason') == 'expired']
    assert ex and all(t['held_days'] == PB.HOLDING_DAYS for t in ex)


# ── 驗收 4：唯一變數是減碼 ───────────────────────────────────────────────
def test_scenario_A_reproduces_build_prompt_21_baseline(sims):
    a, _b = sims
    perf = PB.perf_from_equity(a['equity_curve'], a['start_capital'])
    assert perf['cagr'] == 19.06 and perf['mdd'] == -45.8, \
        f"基準未重現：{perf['cagr']} / {perf['mdd']}"
    assert a['stats'].get('deleveraged', 0) == 0


def test_both_scenarios_conserve_money(sims):
    for s in sims:
        pnl = sum(t['pnl'] for t in s['trades'])
        delta = s['equity_curve'][-1]['equity'] - s['start_capital']
        assert abs(pnl - delta) < 1e-6
        assert not [c for c in s['equity_curve'] if c['cash'] < -1e-6]
        assert s['stats']['opened'] == len(s['trades'])


# ── 驗收 6：只新增，不改既有 ─────────────────────────────────────────────
def test_existing_engine_functions_unchanged():
    for name in ('position_sizing', 'gross_exposure_cap',
                 'concentration_limits', 'correlation_limits',
                 'evaluate_new_position', 'select_position_to_trim'):
        assert callable(getattr(PE, name))
    # 既有四函式的行為抽查（與 test_portfolio_engine 重疊，這裡只守回歸）
    assert PE.gross_exposure_cap('空頭') == 0.40
    out = PE.position_sizing('A', 1_000_000, 100, 0.01)
    assert out['position_pct'] == pytest.approx(QC.MAX_SINGLE_POSITION_PCT)


def test_no_new_config_constants_needed():
    """本輪沿用既有 GROSS_EXPOSURE_BY_REGIME，不新增 config 常數。"""
    src = open(PE.__file__, encoding='utf-8').read()
    i = src.index('def select_position_to_trim')
    body = src[i:src.index('\ndef ', i + 10)]
    assert 'GROSS_EXPOSURE_BY_REGIME' not in body or 'gross_exposure_cap' in body
    assert '_QC.' not in body, '減碼函式應透過 gross_exposure_cap() 取上限'
