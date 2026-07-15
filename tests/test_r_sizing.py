#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for research_bp12_r_sizing (empirical Kelly + left tail).

Synthetic data only — does NOT depend on any real backtest / bp12_r_on/trades.csv.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import research_bp12_r_sizing as rs  # noqa: E402


# ---------------------------------------------------------------------------
# empirical_kelly
# ---------------------------------------------------------------------------
def test_positive_edge_interior_optimum():
    """A positive-edge coin-flip-like series → 0 < full_kelly <= 1.

    Win +50% / lose -40% with equal odds. Classic Kelly for a symmetric-count
    two-outcome bet is f* = mean/var-style; here f* is comfortably interior.
    """
    returns = np.array([0.50, -0.40] * 200)  # p=0.5 each, positive expectation
    out = rs.empirical_kelly(returns)
    assert 0.0 < out['full_kelly'] <= 1.0
    # half is exactly full/2
    assert out['half_kelly'] == pytest.approx(out['full_kelly'] / 2.0)
    # analytic optimum: maximize .5*log(1+.5f)+.5*log(1-.4f)
    # g'(f)=0 -> .25/(1+.5f)=.2/(1-.4f) -> .25(1-.4f)=.2(1+.5f) -> .05=.2f -> f*=0.25
    assert out['full_kelly'] == pytest.approx(0.25, abs=0.01)


def test_zero_edge_gives_zero():
    """A symmetric zero-edge series → full_kelly ≈ 0 (no allocation)."""
    returns = np.array([0.30, -0.30] * 500)  # mean 0, symmetric
    out = rs.empirical_kelly(returns)
    assert out['full_kelly'] == pytest.approx(0.0, abs=1e-3)
    assert out['half_kelly'] == pytest.approx(0.0, abs=1e-3)


def test_negative_edge_gives_zero():
    """A negative-edge series → full_kelly == 0 (no allocation, clamped at 0)."""
    returns = np.array([0.30, -0.40] * 300)  # negative expectation
    out = rs.empirical_kelly(returns)
    assert out['full_kelly'] == 0.0
    assert out['half_kelly'] == 0.0


def test_empty_returns_safe():
    out = rs.empirical_kelly(np.array([]))
    assert out['full_kelly'] == 0.0
    assert out['n'] == 0


def test_nan_dropped():
    a = rs.empirical_kelly(np.array([0.5, -0.4, np.nan, 0.5, -0.4]))
    b = rs.empirical_kelly(np.array([0.5, -0.4, 0.5, -0.4]))
    assert a['n'] == 4
    assert a['full_kelly'] == pytest.approx(b['full_kelly'])


# ---------------------------------------------------------------------------
# left_tail
# ---------------------------------------------------------------------------
def test_left_tail_known_array():
    arr = list(range(1, 101))  # 1..100
    lt = rs.left_tail(arr)
    assert lt['worst'] == 1.0
    assert lt['n'] == 100
    # numpy linear-interp percentiles of 1..100
    assert lt['p5'] == pytest.approx(np.percentile(arr, 5))
    assert lt['p10'] == pytest.approx(np.percentile(arr, 10))
    assert lt['p5'] == pytest.approx(5.95)
    assert lt['p10'] == pytest.approx(10.9)


def test_left_tail_empty():
    lt = rs.left_tail([])
    assert lt['n'] == 0
    assert np.isnan(lt['worst'])


# ---------------------------------------------------------------------------
# main() smoke test on a tiny synthetic trades.csv (writes to tmp only)
# ---------------------------------------------------------------------------
def test_main_smoke(tmp_path, monkeypatch):
    df = pd.DataFrame({
        'symbol': ['1101', '2330', '2317', '9999'],
        'as_of': ['2026-01-02'] * 4,
        'regime': ['盤整'] * 4,
        'r_signal': ['R-TRADE', 'R-TRADE', 'R-WATCH', 'R-TRADE'],
        'r_strength': [3, 2, 1, 4],
        'ret_10_net': [8.5, -3.2, 1.0, ''],  # last blank -> dropped from stats
    })
    src = tmp_path / 'trades.csv'
    df.to_csv(src, index=False)

    out_csv = tmp_path / 'r_track_trades.csv'
    out_md = tmp_path / 'r_track_sizing.md'
    monkeypatch.setattr(rs, 'TRADES_OUT', str(out_csv))
    monkeypatch.setattr(rs, 'REPORT_MD', str(out_md))

    res = rs.main(str(src))

    # 3 R-TRADE rows written; 2 have numeric returns
    written = pd.read_csv(out_csv, dtype={'symbol': str})
    assert len(written) == 3
    assert res['n'] == 2
    assert out_md.exists()
    text = out_md.read_text(encoding='utf-8')
    assert 'Full Kelly' in text
    assert 'R_POSITION_CAP' in text
    assert '10 trading-day time exit' in text
    # recommended never exceeds the cap
    assert res['recommended'] <= rs.R_POSITION_CAP + 1e-12
