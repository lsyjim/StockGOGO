"""
test_portfolio_backtest.py — build_prompt_21 驗收

對應驗收條件 1–3、6–7：
  1  資金守恆：現金流獨立重建、equity == cash + invested、Σ損益 == 期末−期初
  2  曝險上限在**進場時點**確實生效（逐日觀察值另有 MTM 漂移，報告已載明）
  3  相關性層接的是真實價格，確實觸發過
  6/7 不改 portfolio_engine / decision_engine / config / signal_backtest

全期模擬約 3 秒，直接跑真實資料，不用合成 fixture——這輪要驗的就是
「真實資金曲線有沒有憑空生錢」，用假資料驗沒有意義。

執行：PYTHONPATH=. python3 -m pytest tests/test_portfolio_backtest.py -q
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import portfolio_backtest as PB
from config import QuantConfig as QC


@pytest.fixture(scope='module')
def sim():
    if not os.path.exists(PB.BASE_TRADES):
        pytest.skip('缺 bp13_step0/trades.csv')
    return PB.simulate(verbose=False)


# ── 驗收 1：資金守恆 ──────────────────────────────────────────────────────
def test_equity_equals_cash_plus_invested(sim):
    bad = [c for c in sim['equity_curve']
           if abs(c['equity'] - (c['cash'] + c['invested'])) > 1e-6]
    assert not bad, f'{len(bad)} 天 equity != cash+invested，例：{bad[:2]}'


def test_cash_reconciles_with_independent_ledger(sim):
    """用交易紀錄獨立重建現金流，逐日核對——抓「錢憑空增減」。"""
    buys = collections.defaultdict(float)
    sells = collections.defaultdict(float)
    for t in sim['trades']:
        buys[t['entry_date']] += t['notional']
        sells[t['exit_date']] += t['shares'] * t['exit_price'] - PB.COST_RATE * t['notional']
    cash = sim['start_capital']
    worst = 0.0
    for c in sim['equity_curve']:
        cash += sells[c['date']] - buys[c['date']]
        worst = max(worst, abs(c['cash'] - cash))
    assert worst < 1e-6, f'現金流對帳最大差異 {worst}'


def test_pnl_sums_to_equity_change(sim):
    pnl = sum(t['pnl'] for t in sim['trades'])
    delta = sim['equity_curve'][-1]['equity'] - sim['start_capital']
    assert abs(pnl - delta) < 1e-6, f'Σ損益 {pnl} != 期末−期初 {delta}'


def test_cash_never_negative(sim):
    neg = [c for c in sim['equity_curve'] if c['cash'] < -1e-6]
    assert not neg, f'出現負現金（等同無授權融資）：{neg[:2]}'


def test_every_open_is_closed(sim):
    st = sim['stats']
    assert st['opened'] == st['closed'] + st.get('forced_close_at_end', 0)
    assert len(sim['trades']) == st['opened']


# ── 驗收 2：曝險上限（進場時點）───────────────────────────────────────────
def test_gross_exposure_cap_holds_at_entry(sim):
    """每次開倉後的總曝險不得超過當日 regime 上限。

    註：逐日觀察值可能超過上限，那是 MTM 漂移 + 上限只是進場閘門所致，
    是 production 邏輯的真實樣貌，報告已專節說明，不在此斷言。
    """
    viol = [e for e in sim['entry_audit'] if e['gross_after'] > e['cap'] + 1e-9]
    assert not viol, f'{len(viol)} 次開倉後超過上限，例：{viol[:3]}'


def test_entry_audit_covers_every_open(sim):
    assert len(sim['entry_audit']) == sim['stats']['opened']


def test_multi_signal_day_respects_cap(sim):
    """抽查同日多筆開倉的日子，確認最後一筆開完仍在上限內。"""
    byday = collections.defaultdict(list)
    for e in sim['entry_audit']:
        byday[e['date']].append(e)
    multi = [v for v in byday.values() if len(v) >= 3]
    assert multi, '找不到同日 3 筆以上開倉的日子'
    for v in multi:
        last = v[-1]
        assert last['gross_after'] <= last['cap'] + 1e-9


# ── 驗收 3：相關性層接真實價格且確實生效 ──────────────────────────────────
def test_correlation_limit_actually_fires(sim):
    n = sim['stats'].get('capped_correlation_limits', 0)
    assert n > 0, '相關性限制從未觸發——代表沒接到真實價格'
    assert sim['capped_examples'], '應留下觸發樣例供報告佐證'
    e = sim['capped_examples'][0]
    assert e['with'], '樣例必須指出與哪些持倉高相關'
    assert e['to_pct'] < e['from_pct']


def test_price_history_getter_returns_real_series(sim):
    """PriceBook 由 trades.csv 重建，抽查長度與正值。"""
    book = sim['book']
    sym = sorted(book.dates)[0]
    date = book.dates[sym][300]
    h = book.history_upto(sym, date, QC.CORR_WINDOW_DAYS)
    assert h is not None and len(h) == QC.CORR_WINDOW_DAYS
    assert all(x > 0 for x in h)


def test_reconstructed_closes_agree_across_horizons():
    """exit_5 / exit_10 / exit_20 反推的同一日收盤價必須一致（重建無損）。"""
    rows = collections.defaultdict(list)
    for r in PB.load_rows(PB.BASE_TRADES):
        rows[r['symbol']].append(r)
    sym = sorted(rows)[0]
    rs = sorted(rows[sym], key=lambda r: r['as_of'])
    checked = 0
    for i in range(20, min(len(rs), 400)):
        a = PB._f(rs[i]['exit_5'])
        b = PB._f(rs[i - 5]['exit_10'])
        c = PB._f(rs[i - 15]['exit_20'])
        if None in (a, b, c):
            continue
        assert abs(a - b) < 0.011 and abs(b - c) < 0.011, \
            f'{sym} {rs[i]["as_of"]}: {a} / {b} / {c}'
        checked += 1
    assert checked > 100


# ── 驗收 6/7：未動核心模組 ────────────────────────────────────────────────
def test_core_modules_untouched_by_this_module():
    src = open(PB.__file__, encoding='utf-8').read()
    assert 'import signal_backtest' not in src, '本模組不得依賴 signal_backtest'
    for forbidden in ('QC.RISK_PCT_BY_GRADE =', 'QC.GROSS_EXPOSURE_BY_REGIME =',
                      'QC.MAX_SINGLE_POSITION_PCT ='):
        assert forbidden not in src, f'不得在回測裡改寫 config：{forbidden}'


def test_holding_period_is_fixed(sim):
    """出場一律固定持有期，不得出現訊號驅動出場。"""
    book = sim['book']
    off = collections.Counter()
    for t in sim['trades'][:500]:
        ds = book.dates[t['symbol']]
        i = book.idx[t['symbol']].get(t['entry_date'])
        j = book.idx[t['symbol']].get(t['exit_date'])
        if i is None or j is None:
            continue
        off[j - i] += 1
    assert set(off) == {PB.HOLDING_DAYS + 1}, f'持有期不一致：{dict(off)}'
