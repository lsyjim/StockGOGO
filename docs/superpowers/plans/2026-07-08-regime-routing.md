# Regime Routing (build_prompt_11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add regime-aware signal routing — a config-gated "M-Lite" B-grade path for range (盤整) markets, a momentum-aware RSI safety-valve exemption, and a theme-strength grade contribution — validated by A/B walk-forward on price/chip history expanded back to 2020, plus two report-only research tracks (bear rev_mom, oversold-rebound R signal).

**Architecture:** All engine behaviour changes live behind `config.py` boolean flags defaulting to the current behaviour, so `baseline` (flags off) is a one-line revert from `variant` (flags on). Task 4 widens the data window first (price via `start_date=2020-01-01`, chip via a new per-symbol FinMind range backfill) because every downstream A/B matrix and research report must run on the expanded sample. Grade decisions stay inside `ThreeLayerEngine` (`decision_engine.py`); validation stays inside `signal_backtest.py`; both keep the `data_reliable` fail-safe (missing chip days ⇒ path silent, never 0-filled).

**Tech Stack:** Python 3.7+, pandas, yfinance, FinMind REST, SQLite (`watchlist_v4.db`), pytest, argparse-driven walk-forward harness.

---

## ⚠️ Spec Deviations & Open Decisions (read before Task 3)

**Task 3 premise is false as written.** The spec says "定位 theme_score 現行進分點（prompt 08 實作處），將其權重提高一檔". But theme momentum is **deliberately excluded from the grade today**:

- `main.py:1346` — `# build_prompt_08：族群動能（顯示/排序加成，不進 grade）`
- `main.py:1847` — `# ...加註（顯示/排序用，不進 grade；歷史模式跳過）`
- In `signal_backtest.py:236`, `theme_score` is a **factor snapshot** (`theme_rank_pct`), never a grade input.

So there is **no existing theme weight to raise**. "升權一檔" is therefore ambiguous:

- **Interpretation A (implemented in Task 3 below):** Promote theme into the grade as a *new, bounded, config-gated* input (`THEME_GRADE_ENABLED`, `THEME_WEIGHT`). This is what the acceptance criteria implicitly require — the A/B grade×hold matrices can only move if theme touches the grade. Justified by spec point 5 (theme_score is one of only 3 factors passing dual-half stability). Risk: it is arguably a *new variant*, which brushes against the "no new variants beyond pre-registered" discipline (防呆 line 119). We treat "theme→grade" as the pre-registered item since factor attribution nominated it.
- **Interpretation B:** Keep theme as ranking/sort weight only (literally "升權" the sort boost). Matches the words, but is **invisible to the grade×hold A/B matrices** — the validation in the acceptance criteria would show zero movement, making the round meaningless.

**Task 3 below implements Interpretation A behind a flag, and flags this for the user.** If the user prefers B (or wants Task 3 dropped this round to preserve multiple-comparison discipline), skip Task 3's steps — nothing else depends on them.

**Task 4 is a data operation, not classic TDD.** Live yfinance/FinMind calls can't be unit-tested against the network. Task 4 unit-tests the *pure* pieces (deep-backfill date-range construction, calendar lookback math) with mocked clients, then uses an explicit **verification checklist** (date coverage, fail-safe %) for the live run.

**Bear conclusions stay single-event-ish.** Expanding to 2020 adds COVID-2020-03 and the 2022 bear, but Task 4 step "V-pattern reproduction check" only *tests whether* they rhyme with 2025-04; it does not upgrade the deep-oversold "94% win" finding into the engine (防呆 line 120).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `config.py` | Modify (add flags) | All new tunables + on/off switches (single revert point) |
| `decision_engine.py` | Modify | M-Lite path (Task 1), RSI-valve exemption (Task 2), theme grade nudge (Task 3) — all flag-gated |
| `chip_data_manager.py` | Modify (add method) | `deep_backfill()` per-symbol FinMind range backfill to 2020 (Task 4) |
| `data_fetcher.py` | Modify | History fetch reachable back to 2020 (Task 4) |
| `signal_backtest.py` | Modify | History window + calendar lookback to 2020; research subcommands (Tasks 4/5/6) |
| `tests/test_mlite_range.py` | Create | M-Lite grant + **bear lockout** (data red line) |
| `tests/test_rsi_valve_mom.py` | Create | 85 vs 92 valve threshold selection |
| `tests/test_theme_grade.py` | Create | Theme nudge on/off + bounded |
| `tests/test_deep_backfill.py` | Create | Deep-backfill range/calendar math (mocked FinMind) |
| `docs/superpowers/reports/research_bear_revmom.md` | Create (Task 5 output) | Bear rev_mom report |
| `docs/superpowers/reports/research_r_signal.md` | Create (Task 6 output) | Oversold-rebound R report |

**Reused knowledge (do not re-derive):**
- Grade decision entry: `ThreeLayerEngine.analyze()` `decision_engine.py:132`; timing grade in `score_timing()` `:676`; chip filter `apply_chip_filter()` `:1002`; sell hierarchy `check_sell_signal()` `:1075`; momentum test `_is_momentum()` `:97`.
- Field access (exact keys):
  - `rs_score` → `result['relative_strength']['rs_score']` (default 50)
  - `ma_bull` → `technical`: `current > ma20 and ma20 > ma60` (matches `signal_backtest.py:202`)
  - `chip_buy_days` → `_get_chip(result)['consecutive_buy_days']` (default 0)
  - `chip_reliable` → `_get_chip(result).get('data_reliable') is not False`
  - market regime → `result['market_regime']['trend_direction']` ∈ {多頭,空頭,盤整}
- RSI safety valve lives at `score_timing()` `decision_engine.py:936-972`; the literal `85` is line 949.
- Backtest history source: `signal_backtest.py:959` (index `period="3y"`), `:970` (per-symbol `period="3y"`), `:990` (0050), `:966` chip `backfill(trading_days=_chip_days=750)`, `:952` `sync_calendar(lookback_days=1200)`.
- Volume-price "healthy" (Task 2) per recall appendix `backtest_results/20260708_1005/recall_report.md:49`: **量增 (vol_ratio>1) OR 量能 zscore>0**.

---

## Task 4: Historical Data Expansion to 2020-01-01

**Goal:** Price + chip history reach 2020-01-01 (COVID-2020, 2022 bear, 2023-10 correction, 2025-04 tariff crash) so all later A/B and research runs have qualifying bear/range samples. Fail-safe semantics unchanged.

**Files:**
- Modify: `config.py` (add `HISTORY_START_DATE`, `CHIP_DEEP_START_DATE`)
- Modify: `chip_data_manager.py` (add `deep_backfill`)
- Modify: `signal_backtest.py:952,959,966,970,990`
- Test: `tests/test_deep_backfill.py`

- [ ] **Step 1: Add data-window config**

In `config.py`, inside `class QuantConfig`, after the FinMind block (around line 42):

```python
    # build_prompt_11：歷史資料窗口擴充至 2020（COVID/2022/2023-10/2025-04 四次空頭）
    HISTORY_START_DATE = "2020-01-01"   # 價格與回測起點
    CHIP_DEEP_START_DATE = "2020-01-01" # 籌碼深度回補起點（FinMind 法人可回溯至 2012）
```

- [ ] **Step 2: Write failing test for deep-backfill range construction**

Create `tests/test_deep_backfill.py`:

```python
import datetime
from unittest.mock import patch
from chip_data_manager import ChipDataManager

def test_deep_backfill_requests_full_range_once():
    mgr = ChipDataManager(db_name=":memory:")
    calls = []
    def fake_fetch(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return {}  # no rows; exercises range logic only
    with patch.object(mgr, "_fetch_finmind_chip", side_effect=fake_fetch):
        mgr.deep_backfill("2330", start_date="2020-01-01")
    assert len(calls) == 1, "deep_backfill must be ONE FinMind request per symbol"
    sym, s, e = calls[0]
    assert sym == "2330" and s == "2020-01-01"
    assert e >= datetime.date.today().isoformat()
```

- [ ] **Step 3: Run it, verify it fails**

Run: `python -m pytest tests/test_deep_backfill.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'deep_backfill'`

- [ ] **Step 4: Implement `deep_backfill`**

In `chip_data_manager.py`, add a method to `ChipDataManager` next to `backfill` (near line 279). It issues **one** FinMind range request per symbol (budget-guarded via the existing `_fetch_finmind_chip` path), writes rows, and marks calendar-covered holes for official range backup — reusing `_upsert_chip` and `_backfill_official_range` exactly as `backfill` does:

```python
    def deep_backfill(self, symbol, start_date: str = None):
        """build_prompt_11：單檔 FinMind 日期區間深度回補（1 請求 / 檔）。
        缺洞語意不變：FinMind 限流/無資料 → 官方 per-date 備援補完整缺洞，
        仍缺的日子留白（data_reliable=False 由讀取端判定，嚴禁 0 填充）。"""
        import datetime
        start = start_date or getattr(__import__('config').QuantConfig,
                                      'CHIP_DEEP_START_DATE', '2020-01-01')
        end = datetime.date.today().isoformat()
        chip = self._fetch_finmind_chip(str(symbol), start, end)
        written = 0
        if chip and chip is not RATE_LIMITED:
            cal = set(self.get_trading_days_desc(limit=100000))
            for d, v in chip.items():
                if d in cal:
                    self._upsert_chip(symbol, d, v["f_net"], v["t_net"],
                                      v["d_net"], "finmind", commit=False)
                    written += 1
            self._commit()
        # 官方備援補缺洞（沿用 backfill 的缺洞判定路徑）
        miss = self._missing_chip_dates(symbol, start, end)
        if miss:
            self._backfill_official_range([symbol], {symbol: miss})
        return written
```

If `_missing_chip_dates` / `_commit` don't exist under these names, mirror whatever `backfill` (`:279`) uses — read `backfill`'s body first and reuse its exact helpers rather than inventing names.

- [ ] **Step 5: Run test, verify pass**

Run: `python -m pytest tests/test_deep_backfill.py -v`
Expected: PASS

- [ ] **Step 6: Widen backtest history window + calendar lookback**

In `signal_backtest.py`:
- `:952` `sync_calendar(lookback_days=1200)` → `sync_calendar(lookback_days=2600)` (2020-01→2026-07 ≈ 2380 days + margin)
- `:959` index `period="3y"` → fetch from `QuantConfig.HISTORY_START_DATE`: replace with
  `QuickAnalyzer._get_index_history_cached(QuantConfig.MARKET_INDEX_TW, period="max")` (index needs full span; `max` is safe for `^TWII`)
- `:970` `DataSourceManager.get_history(sym, '台股', period="3y")` →
  `DataSourceManager.get_history(sym, '台股', start_date=QuantConfig.HISTORY_START_DATE)`
- `:990` 0050 fallback `period="3y"` → same `start_date=QuantConfig.HISTORY_START_DATE`
- `:966` `_chip_days = 750 if args.days <= 0` → when `args.days <= 0`, call the new deep path instead of the 750-day `backfill`:

```python
        # build_prompt_11：全歷史模式走深度回補（1 FinMind 請求/檔，回溯 2020）
        try:
            if args.days <= 0:
                chip_mgr.deep_backfill(sym, start_date=QuantConfig.CHIP_DEEP_START_DATE)
            else:
                chip_mgr.backfill(sym, trading_days=_chip_days)
        except Exception:
            pass
```

Confirm `DataSourceManager.get_history` honours `start_date` (it does — `data_fetcher.py:1151` signature `start_date=..., period=...` mutually exclusive). No `data_fetcher.py` change is needed if `start_date` already flows through `_serve_from_batch`/`_get_history_yfinance` (`:1256`). Verify by reading `_serve_from_batch` (`:1083`); if it only honours `period`, add a `start_date` branch there.

- [ ] **Step 7: Live expansion run + verification checklist (NOT a unit test)**

Run: `python signal_backtest.py --days 0 --hold 5,10,20 --out backtest_results/bp11_expanded`
Then verify (record actual numbers in the round report):
- [ ] Earliest `as_of` in `backtest_results/bp11_expanded/trades.csv` ≤ 2020-06 (price coverage reached 2020).
- [ ] All four bear windows present: rows with `regime==空頭` exist in 2020-03, 2022-H1/H2, 2023-10, 2025-04.
- [ ] Chip fail-safe %: fraction of signals with chip `data_reliable is False` reported; unchanged semantics (holes blank, not 0).
- [ ] `deep_backfill` issued ≤ 98 FinMind requests total (well under 550/hr).

- [ ] **Step 8: Re-run existing validation on expanded data (regression + V-pattern check)**

Run recall + sell/wait so downstream reports use expanded sample and stay backward-compatible:
`python signal_backtest.py --days 0 --recall --out backtest_results/bp11_expanded`
Confirm `recall_report.md` and `sell_wait_regime.md` regenerate without error. Add to the round report: do 2020-03 and 2022 deep-oversold events show a 2025-04-style V-rebound, or not? (Report only — no engine change.)

- [ ] **Step 9: Commit**

```bash
git add config.py chip_data_manager.py signal_backtest.py tests/test_deep_backfill.py
git commit -m "feat(data): expand price+chip history to 2020 via per-symbol FinMind deep backfill

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 1: M-Lite Range Path (highest-priority engine change)

**Goal:** In range (盤整) markets, grant B-grade to `ma_bull ∧ rs_score≥80 ∧ chip_buy_days≥3 ∧ chip_reliable` with label `M-Lite盤整`. **Locked out of bear** (data red line: 3% win / −19.2%). Not enabled in bull (avoid A/B attribution pollution). Sell precedence + overheat valve + bias ceiling still apply.

**Files:**
- Modify: `config.py`
- Modify: `decision_engine.py` `analyze()` (insert after chip filter `:227`, before sell check `:229`)
- Test: `tests/test_mlite_range.py`

- [ ] **Step 1: Add config flags**

In `config.py`, `class QuantConfig`, after the Task-4 block:

```python
    # build_prompt_11 任務1：盤整 M-Lite 路徑（預設關閉）
    MLITE_RANGE_ENABLED = False   # 僅盤整授予 B 級；空頭嚴禁、多頭不啟用
    MLITE_RS_MIN = 80             # rs_score 門檻
    MLITE_CHIP_MIN = 3            # chip_buy_days 門檻
```

- [ ] **Step 2: Write failing tests (grant + BEAR LOCKOUT)**

Create `tests/test_mlite_range.py`. The bear-lockout test is the data red line (防呆 line 116) and must never regress:

```python
from decision_engine import ThreeLayerEngine
import config

def _mlite_result(regime_trend):
    # ma_bull: 100 > 95 > 90 ; rs_score 85 ; chip 連買4 reliable
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

def test_mlite_grants_B_in_range_when_enabled(monkeypatch):
    monkeypatch.setattr(config.QuantConfig, 'MLITE_RANGE_ENABLED', True)
    out = ThreeLayerEngine.analyze(_mlite_result('盤整'))
    trail = ' '.join(str(t) for t in out.get('adjustment_trail', []))
    assert out.get('grade') in ('B',) or 'M-Lite盤整' in trail

def test_mlite_LOCKED_in_bear_even_when_enabled(monkeypatch):
    # DATA RED LINE: 3% win / -19.2% in bear. Must stay silent.
    monkeypatch.setattr(config.QuantConfig, 'MLITE_RANGE_ENABLED', True)
    out = ThreeLayerEngine.analyze(_mlite_result('空頭'))
    trail = ' '.join(str(t) for t in out.get('adjustment_trail', []))
    assert 'M-Lite盤整' not in trail, "M-Lite must NEVER fire in bear regime"

def test_mlite_off_by_default(monkeypatch):
    out = ThreeLayerEngine.analyze(_mlite_result('盤整'))
    trail = ' '.join(str(t) for t in out.get('adjustment_trail', []))
    assert 'M-Lite盤整' not in trail
```

- [ ] **Step 3: Run tests, verify grant/lockout tests fail (default test passes)**

Run: `python -m pytest tests/test_mlite_range.py -v`
Expected: `test_mlite_grants_B_in_range_when_enabled` FAIL, `test_mlite_LOCKED_in_bear...` currently PASS (label absent), `test_mlite_off_by_default` PASS. Grant test failing confirms the path is genuinely missing.

- [ ] **Step 4: Implement M-Lite in `analyze()`**

In `decision_engine.py`, inside `analyze()`, insert between the chip-filter trail block (ends `:227`) and the sell check (`:229`). Uses only already-fetched `market_regime`/`chip`/`result`; grants B only when the current grade is weaker than B; **hard-locks bear** with an explicit condition (spec line 51):

```python
            # ── build_prompt_11 任務1：盤整 M-Lite 路徑（flag-gated）──────
            from config import QuantConfig as _QC11
            if getattr(_QC11, 'MLITE_RANGE_ENABLED', False):
                _g_before_ml = timing['grade']
                _regime_ml = market_trend  # '多頭'/'空頭'/'盤整'（analyze 頂部已取）
                _tech_ml = result.get('technical', {}) or {}
                _cur_ml = result.get('current_price', 0) or 0
                _ma20_ml = _tech_ml.get('ma20', _cur_ml) or _cur_ml
                _ma60_ml = _tech_ml.get('ma60', _cur_ml) or _cur_ml
                _ma_bull = (_cur_ml > _ma20_ml) and (_ma20_ml > _ma60_ml)
                _rs_ml = (result.get('relative_strength', {}) or {}).get('rs_score', 50) or 50
                _buy_days_ml = chip.get('consecutive_buy_days', 0) or 0 if isinstance(chip, dict) else 0
                _chip_reliable_ml = _get_chip(result).get('data_reliable') is not False
                # 位階鎖：僅盤整；空頭嚴禁（數據紅線）；多頭不啟用
                assert _regime_ml != '空頭' or True  # documented invariant; enforced by condition below
                if (_regime_ml == '盤整' and _ma_bull and _rs_ml >= _QC11.MLITE_RS_MIN
                        and _buy_days_ml >= _QC11.MLITE_CHIP_MIN and _chip_reliable_ml
                        and market_available
                        and timing['grade'] in ('X', 'C')):
                    timing['grade'] = 'B'
                    _ml_reason = (f'M-Lite盤整：盤整+均線多頭+RS{_rs_ml:.0f}'
                                  f'+法人連買{_buy_days_ml}天 → B')
                    timing['label'] = '追蹤（M-Lite盤整）'
                    timing['triggers'].append('🟡 ' + _ml_reason)
                    trail.append({'stage': 'M-Lite盤整', 'from': _g_before_ml,
                                  'to': 'B', 'reason': _ml_reason})
                else:
                    trail.append({'stage': 'M-Lite盤整', 'from': None,
                                  'to': None, 'reason': '—'})
```

Note: because the `if` requires `_regime_ml == '盤整'`, bear/bull can never enter — the bear lockout is structural, not just an assert. Sell check (`:229`) runs *after* this, so sell precedence (fix_07) is preserved automatically.

- [ ] **Step 5: Run tests, verify all pass**

Run: `python -m pytest tests/test_mlite_range.py -v`
Expected: all 3 PASS (grant in range, lockout in bear, off by default).

- [ ] **Step 6: Commit**

```bash
git add config.py decision_engine.py tests/test_mlite_range.py
git commit -m "feat(engine): flag-gated M-Lite range B-grade path, bear-locked

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7: A/B round 1 (defer full run to combined validation section)** — see "A/B Validation Discipline" below. Round 1 = M-Lite only.

---

## Task 2: RSI Safety-Valve Momentum Exemption (pre-registered)

**Goal:** Parametrize the overheat valve (`85`→`SAFETY_VALVE_RSI`); when `_is_momentum` and volume-price healthy, raise the threshold to `SAFETY_VALVE_RSI_MOM=92` (lets healthy momentum names keep A). Quantify the fatter left tail.

**Files:**
- Modify: `config.py`
- Modify: `decision_engine.py:936-972` (valve block in `score_timing`)
- Test: `tests/test_rsi_valve_mom.py`

- [ ] **Step 1: Add config flags**

```python
    # build_prompt_11 任務2：RSI 安全閥動能豁免
    SAFETY_VALVE_RSI = 85       # 非動能 / 一般情況
    SAFETY_VALVE_RSI_MOM = 92   # _is_momentum 且量價健康時放寬
```

- [ ] **Step 2: Write failing test**

Create `tests/test_rsi_valve_mom.py`. Build a momentum result with healthy volume and RSI between 85 and 92 that would currently be A→B'd but should now stay A:

```python
from decision_engine import ThreeLayerEngine
import config

def _hot_momentum_result(rsi, vol_ratio=1.5):
    # momentum (rs 90, ma stacked), bias_z ~1.6σ (over 1.5), atr→sigma 4%
    return {
        'symbol': 'H', 'current_price': 120.0,
        'technical': {'ma5': 118, 'ma20': 110, 'ma60': 100, 'rsi': rsi,
                      'atr': 4.8, 'pth_52w': 0.99, 'breakout_55': True,
                      'vol_ratio': vol_ratio, 'volume_zscore': 1.0},
        'relative_strength': {'rs_score': 90, 'vs_market': 8},
        'market_regime': {'available': True, 'trend_direction': '多頭', 'adx': 30},
        'chip_flow': {'available': True, 'data_reliable': True, 'consecutive_buy_days': 4},
        'mean_reversion': {'available': True, 'bias_analysis': {'bias_20': 13.0}},
        'wave_analysis': {'available': True,
                          'breakout_signal': {'detected': True, 'volume_confirmed': True}},
        'pattern_analysis': {}, 'volume_price': {},
    }

def test_valve_holds_A_for_healthy_momentum_between_85_and_92():
    t = ThreeLayerEngine.score_timing(_hot_momentum_result(rsi=88))
    assert t['grade'] == 'A', "RSI 88 healthy momentum should stay A under 92 valve"

def test_valve_still_downgrades_above_92():
    t = ThreeLayerEngine.score_timing(_hot_momentum_result(rsi=95))
    assert t['grade'] == 'B', "RSI 95 exceeds even the momentum valve"
```

- [ ] **Step 3: Run, verify first test fails**

Run: `python -m pytest tests/test_rsi_valve_mom.py -v`
Expected: `test_valve_holds_A...` FAIL (current code downgrades at 85 for non-`_bias_z>2.5`? no — momentum ≤2.5σ already only warns; verify the exact current behaviour and adjust bias so the test genuinely exercises the 85→92 change). Adjust `bias_20` so `1.5 < bias_z ≤ 2.5` path is hit and RSI is the deciding factor.

- [ ] **Step 4: Implement parametrized valve**

In `decision_engine.py`, replace the hard-coded threshold logic at `:949`. Compute the volume-price health and pick the threshold:

```python
            from config import QuantConfig as _QC11v
            _vr = tech.get('vol_ratio', None); _vz = tech.get('volume_zscore', None)
            _vp_healthy = ((_vr is not None and _vr > 1.0) or (_vz is not None and _vz > 0))
            _is_mom_v = ThreeLayerEngine._is_momentum(result)
            _rsi_thresh = (getattr(_QC11v, 'SAFETY_VALVE_RSI_MOM', 92)
                           if (_is_mom_v and _vp_healthy)
                           else getattr(_QC11v, 'SAFETY_VALVE_RSI', 85))

            if _rsi_ov > _rsi_thresh and _bias_z_ov > 1.5:
                # ...existing two-branch momentum/non-momentum body unchanged...
```

Keep the existing inner `_is_momentum` two-branch body (`:955-972`) intact — only the *gate* threshold changes from literal `85` to `_rsi_thresh`.

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/test_rsi_valve_mom.py -v`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add config.py decision_engine.py tests/test_rsi_valve_mom.py
git commit -m "feat(engine): momentum+healthy-volume RSI safety-valve exemption (85->92)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Theme Grade Contribution (⚠️ see Spec Deviations — Interpretation A)

**Goal (revised):** Because theme does not currently enter the grade, add a *new, bounded, flag-gated* theme nudge so it can influence B/C discrimination — the only way the A/B grade matrices can register the change. If the user chooses Interpretation B or drops Task 3, skip this task entirely.

**Files:**
- Modify: `config.py`
- Modify: `decision_engine.py` `score_timing()` C-grade block (`:908-928`)
- Test: `tests/test_theme_grade.py`

- [ ] **Step 1: Confirm interpretation with user** (blocking gate — do not code until confirmed). Present the two interpretations from the Spec Deviations section.

- [ ] **Step 2: Add config flags**

```python
    # build_prompt_11 任務3：題材強度進 grade（新輸入，預設關閉）— 見計畫 Spec Deviations
    THEME_GRADE_ENABLED = False
    THEME_WEIGHT = 1            # C→B 升級所需的題材強度檔位（0=舊行為/不進grade）
```

- [ ] **Step 3: Write failing test**

Create `tests/test_theme_grade.py`:

```python
from decision_engine import ThreeLayerEngine
import config

def _theme_c_result(is_top=True, is_leader=False):
    return {
        'symbol': 'C', 'current_price': 100.0,
        'technical': {'ma5': 99, 'ma20': 98, 'ma60': 96, 'rsi': 55, 'atr': 2.0},
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
```

- [ ] **Step 4: Run, verify first fails**

Run: `python -m pytest tests/test_theme_grade.py -v`
Expected: `test_theme_nudges_C_to_B...` FAIL, `test_theme_no_effect...` PASS.

- [ ] **Step 5: Implement bounded theme nudge**

In `score_timing()`, after the C-grade assignment block (`:924-926`), before the overheat valve (`:932`). Only promotes a *qualified C* to B when theme is top/leader — bounded, no unbounded score inflation:

```python
        # ── build_prompt_11 任務3：題材強度進 grade（flag-gated, bounded）──
        from config import QuantConfig as _QC11t
        if getattr(_QC11t, 'THEME_GRADE_ENABLED', False) and getattr(_QC11t, 'THEME_WEIGHT', 0) >= 1:
            _tm = result.get('theme_momentum', {}) or {}
            if grade == 'C' and (_tm.get('is_theme_leader') or _tm.get('is_top_theme')):
                grade = 'B'
                _tt = '題材領導股' if _tm.get('is_theme_leader') else '主流題材'
                triggers.append(f'⬆️ {_tt}（強度{_tm.get("theme_rank_pct")}）C→B 升級')
```

Also confirm the engine `result` actually carries `theme_momentum` at analyze time in the backtest path. If `signal_backtest.build_asof_result` does not attach it, add `result['theme_momentum'] = theme_info` there (guarded by as_of visibility) so the A/B run can see it. Read `build_asof_result` (`signal_backtest.py:86`) first.

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/test_theme_grade.py -v`
Expected: both PASS.

- [ ] **Step 7: Commit**

```bash
git add config.py decision_engine.py tests/test_theme_grade.py
git commit -m "feat(engine): flag-gated theme-strength C->B grade nudge (new grade input)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## A/B Validation Discipline (Tasks 1–3 + combined)

**Rule (spec §任務1–3 共同紀律):** one variable at a time; four rounds total, same baseline each round; adopt variant only if **20-day expectancy improves AND 20-day monotonicity not broken AND affected-bucket n≥30**; else revert and record. Log baseline commit hash + param snapshot per round.

- [ ] **Step 1: Record baseline**

Run: `git rev-parse HEAD` → record as baseline hash.
Run baseline (all flags False): `python signal_backtest.py --days 0 --hold 5,10,20 --out backtest_results/bp11_baseline`

- [ ] **Step 2: Round 1 — M-Lite only**

Set `MLITE_RANGE_ENABLED=True` (others False). Run `--out backtest_results/bp11_r1_mlite`. Compare vs baseline: new `M-Lite盤整` label 5/10/20 matrix; existing A/B/C matrices must not degrade; range-regime B expectancy delta; **前後半段 time-stability of the M-Lite bucket** (the 233-signal finding was in-sample — must reproduce on expanded data + dual-half). Adopt/revert per rule. Reset flag.

- [ ] **Step 3: Round 2 — RSI valve only**

Set `SAFETY_VALVE_RSI_MOM=92` active (M-Lite off). Run `--out backtest_results/bp11_r2_rsi`. Focus: A-grade 10/20-day expectancy and **max single-trade loss** (exemption admits high names → fatter left tail — quantify the cost). Adopt/revert. Reset.

- [ ] **Step 4: Round 3 — theme only** (only if user confirmed Task 3)

Set `THEME_GRADE_ENABLED=True`. Run `--out backtest_results/bp11_r3_theme`. Focus: B/C discrimination and 20-day monotonicity improvement. Adopt/revert. Reset.

- [ ] **Step 5: Round 4 — best combination**

Enable only the flags that passed their round. Run `--out backtest_results/bp11_r4_combo`. Confirm no interaction degrades the 20-day matrices.

- [ ] **Step 6: Write the four-round A/B report**

Create `docs/superpowers/reports/bp11_ab_rounds.md`: per round — baseline hash, param snapshot, expectancy-matrix diff table, adopt/revert conclusion. This is a spec acceptance deliverable.

---

## Task 5: Bear rev_mom Research Report (report only — no engine change)

**Files:** Create `docs/superpowers/reports/research_bear_revmom.md`; may add a `--experiment bear_revmom` branch in `signal_backtest.py` mirroring the existing `run_experiment_thirdleg` (`:736`) / `run_bp10_experiments` (`:831`) pattern.

- [ ] **Step 1:** On expanded data, slice `regime==空頭 ∧ rev_mom==True`. Produce 5/10/20-day matrix; 2×2 overlays with `rs_score` and chip conditions; month & per-symbol concentration; **four bear events listed separately** (2020-03, 2022, 2023-10, 2025-04). Reuse `_stats`/matrix helpers already in `signal_backtest.py`.
- [ ] **Step 2:** Run the slice (extend the harness or a one-off script reading `trades.csv` + factor snapshot columns `rev_mom`, `regime`, `rs_score`).
- [ ] **Step 3:** Write `research_bear_revmom.md` with concentration checks and a **three-way conclusion**: propose-into-engine (with conditions) / need-more-sample / reject.
- [ ] **Step 4:** Commit report.

---

## Task 6: Oversold-Rebound R Signal Research Report (report only)

**Files:** Create `docs/superpowers/reports/research_r_signal.md`.

- [ ] **Step 1:** From current code, inventory the "超跌反彈" trigger (currently SELL-graded; see `score_timing` `_mr_trigger` logic `:770-792` and `mean_reversion.left_buy_signal`). Formalize as a candidate **R-signal spec**.
- [ ] **Step 2:** Independent-track backtest: **10-day hold** (edge concentrates in first 10 days); **hard stop-loss** −6% vs −8% vs no-stop (20-day worst −45.1% justifies stops); regime filter all-regime vs range-only.
- [ ] **Step 3:** Month/per-symbol concentration; full left tail (P5/P10/worst).
- [ ] **Step 4:** Write `research_r_signal.md`, three-way conclusion. **If proposed into engine, MUST be an independent track (R-grade label) — never merged into A/B momentum grades** (spec line 102). Note the deep-oversold "94% win" is a single 2025-04 event and stays rejected (防呆 line 120).
- [ ] **Step 5:** Commit report.

---

## Final Deliverables (spec 驗收 §)

- [ ] Expanded data covers 2020-01+; four bear events queryable; chip/price aligned; fail-safe % reported.
- [ ] Four-round A/B report (`bp11_ab_rounds.md`) with expectancy diffs + adopt/revert per round.
- [ ] Two research reports with concentration checks and explicit conclusions.
- [ ] All changes behind config flags; baseline = all flags False (one-line revert).
- [ ] Regression: `python -m pytest tests/ -v` green (existing `test_override_hierarchy`, `test_verdict_consistency`, `test_chip_gov_backup` + new tests); recall / sell_wait_regime / factor snapshot flows still run.
- [ ] Final summary: change list, four-round conclusion table, links to both reports, regression results.

---

## Self-Review notes

- **Spec coverage:** Tasks 1–6 + execution-order-first (Task 4) all mapped. Discipline (one-var, four rounds, n≥30, baseline hash) in the A/B Validation section. 防呆 items covered: bear lockout (Task 1 test), chip_reliable no-0-fill (deep_backfill), deep-oversold stays rejected (Task 6), no new variants beyond pre-registered (Task 3 flagged).
- **Known deviation:** Task 3 premise (theme has no current grade weight) surfaced up top and gated on user confirmation — the one genuine blocking decision.
- **Type consistency:** field keys (`consecutive_buy_days`, `relative_strength.rs_score`, `market_regime.trend_direction`, `data_reliable`) used identically across Tasks 1–3 and match the engine source lines cited.
