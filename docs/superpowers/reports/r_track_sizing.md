# R-TRADE Position Sizing (build_prompt_12 Task 4)

Source trades.csv: `backtest_results/bp12_r_on/trades.csv`
Auditable subset: `r_track_trades.csv` (1010 R-TRADE rows, 1010 with numeric `ret_10_net`)

Exit rule: **10 trading-day time exit, NO stop-loss.** All returns below are `ret_10_net` (net %, costs included).

## Sample

- n (R-TRADE with return): **1010**
- Win %: **70.10%**
- Mean ret_10_net: **4.98%**
- Median ret_10_net: **4.36%**

## Left tail (ret_10_net %)

- P5: **-11.51%**
- P10: **-7.95%**
- Worst: **-20.86%**

## Empirical Kelly (log-growth maximization)

`Growth(f) = mean_i( log(1 + f * r_i) )`, `r_i = ret_10_net_i / 100`, maximized over `f in [0, 1]` by a 0.001-step grid scan + local refine.
(Guard: `1 + f*r` clipped to a 1e-09 floor before log; real 10-day returns are > -1 so this never binds in practice.)

- Full Kelly f*: **1.0000**
- Half Kelly (f*/2): **0.5000**
- Growth at f*: **0.043895**

## Recommendation vs cap

- R_POSITION_CAP: **0.15** (per-position cap)
- Half Kelly: **0.5000**
- **Recommended size = min(half-Kelly, cap) = 0.1500**
- Rationale: half-Kelly exceeds the 15% cap, so the cap binds — size at the cap to bound single-name risk on this no-stop time-exit track.

All numbers above are reproducible from `r_track_trades.csv` via `empirical_kelly` / `left_tail` in `research_bp12_r_sizing.py`.
