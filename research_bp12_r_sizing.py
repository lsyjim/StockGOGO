#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_bp12_r_sizing.py  (report-only, standalone)

Empirical position-sizing analysis for the R-TRADE (超跌反彈, oversold-rebound)
track from build_prompt_12. Reads a completed backtest trades.csv, extracts the
R-TRADE per-trade net returns (10-trading-day time exit, NO stop-loss), and
computes empirical Kelly sizing via log-growth maximization.

Does NOT import config / decision_engine / signal_backtest / analyzers / r_track.
Makes NO network call. Pure os/sys/math/numpy/pandas.

Outputs:
  - r_track_trades.csv                              (auditable per-trade subset)
  - docs/superpowers/reports/r_track_sizing.md      (the sizing report)

Usage:
  python research_bp12_r_sizing.py [path/to/trades.csv]
"""
import os
import sys
import math
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TRADES_CSV = os.path.join(ROOT, 'backtest_results', 'bp12_r_on', 'trades.csv')
TRADES_OUT = os.path.join(ROOT, 'r_track_trades.csv')
REPORT_MD = os.path.join(ROOT, 'docs', 'superpowers', 'reports', 'r_track_sizing.md')

# Single-position cap for the R track. Mirrors config.Config.R_POSITION_CAP=0.15.
# Hardcoded here (with this comment) so the script stays standalone and does not
# import config; keep in sync if config changes.
R_POSITION_CAP = 0.15

# Log-growth guard: a fractional return of -1 or worse would make log(1+f*r)
# undefined/-inf. Real 10-day equity returns are > -1, so clipping 1+f*r to this
# small positive floor is only a numerical safety net (noted in the report).
LOG_FLOOR = 1e-9


# ---------------------------------------------------------------------------
# Kelly / left-tail math (fully auditable, no scipy dependency)
# ---------------------------------------------------------------------------
def empirical_kelly(returns, grid_step=0.001):
    """Empirical full/half Kelly via log-growth maximization on realized returns.

    Parameters
    ----------
    returns : 1D array-like of *fractional* per-trade returns (e.g. 0.05 = +5%).

    Method
    ------
    Growth(f) = mean_i( log(1 + f * r_i) ), maximized over f in [0, 1] by a fine
    grid scan (step `grid_step`) plus a local parabolic refine around the best
    grid point. 1 + f*r_i is clipped to LOG_FLOOR before the log as a guard.

    Returns
    -------
    dict with keys:
      full_kelly       : argmax_f Growth(f) over [0, 1]
      half_kelly       : full_kelly / 2
      growth_at_full   : Growth(full_kelly)
      n                : number of returns used
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n == 0:
        return {'full_kelly': 0.0, 'half_kelly': 0.0, 'growth_at_full': 0.0, 'n': 0}

    def growth(f):
        return float(np.mean(np.log(np.clip(1.0 + f * r, LOG_FLOOR, None))))

    grid = np.arange(0.0, 1.0 + grid_step / 2.0, grid_step)
    growths = np.array([growth(f) for f in grid])
    best_i = int(np.argmax(growths))
    best_f = float(grid[best_i])

    # Local parabolic refine using the two neighbouring grid points (only when
    # the optimum is interior, so we do not push the estimate outside [0, 1]).
    if 0 < best_i < len(grid) - 1:
        y0, y1, y2 = growths[best_i - 1], growths[best_i], growths[best_i + 1]
        denom = (y0 - 2.0 * y1 + y2)
        if denom < 0:  # concave: valid interior maximum
            offset = 0.5 * (y0 - y2) / denom
            cand = best_f + offset * grid_step
            cand = min(1.0, max(0.0, cand))
            if growth(cand) >= growths[best_i]:
                best_f = cand

    full_kelly = best_f
    return {
        'full_kelly': full_kelly,
        'half_kelly': full_kelly / 2.0,
        'growth_at_full': growth(full_kelly),
        'n': n,
    }


def left_tail(returns_pct):
    """Left-tail stats on *percentage* returns. Returns dict {p5, p10, worst, n}."""
    r = np.asarray(returns_pct, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return {'p5': float('nan'), 'p10': float('nan'), 'worst': float('nan'), 'n': 0}
    return {
        'p5': float(np.percentile(r, 5)),
        'p10': float(np.percentile(r, 10)),
        'worst': float(np.min(r)),
        'n': int(r.size),
    }


# ---------------------------------------------------------------------------
# Report driver
# ---------------------------------------------------------------------------
def _fmt(x, nd=2):
    return 'n/a' if (x is None or (isinstance(x, float) and not math.isfinite(x))) else f'{x:.{nd}f}'


def main(trades_csv=DEFAULT_TRADES_CSV):
    df = pd.read_csv(trades_csv, dtype={'symbol': str}, low_memory=False)
    df.columns = [c.strip().lstrip('﻿') for c in df.columns]

    if 'r_signal' not in df.columns:
        raise KeyError("trades.csv has no 'r_signal' column — cannot extract R-TRADE subset")

    R = df[df['r_signal'].astype(str).str.strip() == 'R-TRADE'].copy()

    keep = ['symbol', 'as_of', 'regime', 'r_strength', 'ret_10_net']
    for c in keep:
        if c not in R.columns:
            R[c] = ''
    R = R[keep]
    R['symbol'] = R['symbol'].astype(str).str.strip()

    # r_track_trades.csv: the exact auditable subset the report numbers derive from.
    R.to_csv(TRADES_OUT, index=False)

    ret_pct = pd.to_numeric(R['ret_10_net'], errors='coerce').to_numpy()
    valid = ret_pct[np.isfinite(ret_pct)]
    n = int(valid.size)

    if n == 0:
        win_pct = mean_pct = median_pct = float('nan')
        lt = left_tail(valid)
        kelly = empirical_kelly(np.array([]))
    else:
        win_pct = 100.0 * float(np.mean(valid > 0))
        mean_pct = float(np.mean(valid))
        median_pct = float(np.median(valid))
        lt = left_tail(valid)
        kelly = empirical_kelly(valid / 100.0)

    recommended = min(kelly['half_kelly'], R_POSITION_CAP)
    cap_binds = kelly['half_kelly'] > R_POSITION_CAP

    os.makedirs(os.path.dirname(REPORT_MD), exist_ok=True)
    lines = []
    lines.append('# R-TRADE Position Sizing (build_prompt_12 Task 4)')
    lines.append('')
    lines.append(f'Source trades.csv: `{trades_csv}`')
    lines.append(f'Auditable subset: `r_track_trades.csv` ({len(R)} R-TRADE rows, {n} with numeric `ret_10_net`)')
    lines.append('')
    lines.append('Exit rule: **10 trading-day time exit, NO stop-loss.** All returns below '
                 'are `ret_10_net` (net %, costs included).')
    lines.append('')
    lines.append('## Sample')
    lines.append('')
    lines.append(f'- n (R-TRADE with return): **{n}**')
    lines.append(f'- Win %: **{_fmt(win_pct)}%**')
    lines.append(f'- Mean ret_10_net: **{_fmt(mean_pct)}%**')
    lines.append(f'- Median ret_10_net: **{_fmt(median_pct)}%**')
    lines.append('')
    lines.append('## Left tail (ret_10_net %)')
    lines.append('')
    lines.append(f'- P5: **{_fmt(lt["p5"])}%**')
    lines.append(f'- P10: **{_fmt(lt["p10"])}%**')
    lines.append(f'- Worst: **{_fmt(lt["worst"])}%**')
    lines.append('')
    lines.append('## Empirical Kelly (log-growth maximization)')
    lines.append('')
    lines.append('`Growth(f) = mean_i( log(1 + f * r_i) )`, `r_i = ret_10_net_i / 100`, '
                 'maximized over `f in [0, 1]` by a 0.001-step grid scan + local refine.')
    lines.append(f'(Guard: `1 + f*r` clipped to a {LOG_FLOOR:.0e} floor before log; real '
                 '10-day returns are > -1 so this never binds in practice.)')
    lines.append('')
    lines.append(f'- Full Kelly f*: **{_fmt(kelly["full_kelly"], 4)}**')
    lines.append(f'- Half Kelly (f*/2): **{_fmt(kelly["half_kelly"], 4)}**')
    lines.append(f'- Growth at f*: **{_fmt(kelly["growth_at_full"], 6)}**')
    lines.append('')
    lines.append('## Recommendation vs cap')
    lines.append('')
    lines.append(f'- R_POSITION_CAP: **{R_POSITION_CAP:.2f}** (per-position cap)')
    lines.append(f'- Half Kelly: **{_fmt(kelly["half_kelly"], 4)}**')
    lines.append(f'- **Recommended size = min(half-Kelly, cap) = {_fmt(recommended, 4)}**')
    if cap_binds:
        rationale = ('half-Kelly exceeds the 15% cap, so the cap binds — size at the cap to '
                     'bound single-name risk on this no-stop time-exit track.')
    else:
        rationale = ('half-Kelly is below the 15% cap, so half-Kelly binds — the fractional '
                     'Kelly already sizes below the risk cap.')
    lines.append(f'- Rationale: {rationale}')
    lines.append('')
    lines.append('All numbers above are reproducible from `r_track_trades.csv` via '
                 '`empirical_kelly` / `left_tail` in `research_bp12_r_sizing.py`.')
    lines.append('')

    with open(REPORT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'Wrote {TRADES_OUT} ({len(R)} rows) and {REPORT_MD}')
    print(f'n={n} full_kelly={kelly["full_kelly"]:.4f} half_kelly={kelly["half_kelly"]:.4f} '
          f'recommended={recommended:.4f}')
    return {
        'n': n, 'win_pct': win_pct, 'mean_pct': mean_pct, 'median_pct': median_pct,
        'left_tail': lt, 'kelly': kelly, 'recommended': recommended,
    }


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TRADES_CSV)
