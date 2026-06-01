"""
diagnose_strong_stocks.py
診斷「強勢股被系統性壓制」的實際卡點。

用法：
    python diagnose_strong_stocks.py [代碼1 代碼2 ...]

    若不傳代碼，使用預設的近期強勢台股清單。

輸出：
    每檔股票的三層引擎明細 — direction_score / position_score / bias_z / RS / grade
    並標示出「卡在哪一層」。
"""

import sys
import os
import warnings
warnings.filterwarnings('ignore')

# ── 讓 import 能找到專案模組 ─────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from decision_engine import ThreeLayerEngine

# ── Monkey-patch：在三層引擎各層加上 log ──────────────────────────────

_orig_direction = ThreeLayerEngine.score_direction.__func__
_orig_position  = ThreeLayerEngine.score_position.__func__
_orig_timing    = ThreeLayerEngine.score_timing.__func__

def _patched_direction(result):
    out = _orig_direction(result)
    rs = result.get('relative_strength', {})
    print(f"  [L1-方向] score={out['score']:3d}  bull={out['bull_count']}/4  "
          f"slope_mod={out.get('slope_mod',0):+d}  rs_mod={out.get('rs_mod',0):+d}  "
          f"RS={rs.get('rs_score','-'):.1f}  label={out['label']}")
    return out

def _patched_position(result):
    out = _orig_position(result)
    print(f"  [L2-位置] score={out['score']:3d}  bias_20={out.get('bias_20',0):+.1f}%  "
          f"bias_z={out.get('bias_z',0):+.2f}σ  rsi={out.get('rsi',0):.0f}  "
          f"chip_relax={out.get('chip_relax',0):+d}  label={out['label']}")
    return out

def _patched_timing(result):
    out = _orig_timing(result)
    print(f"  [L3-時機] grade={out['grade']}  triggers={out['triggers'][:2]}")
    return out

ThreeLayerEngine.score_direction = staticmethod(_patched_direction)
ThreeLayerEngine.score_position  = staticmethod(_patched_position)
ThreeLayerEngine.score_timing    = staticmethod(_patched_timing)

# ── 主流程 ────────────────────────────────────────────────────────────

def diagnose(symbols):
    # import 放這裡，避免 patch 前就被呼叫
    try:
        from main import QuickAnalyzer
    except Exception as e:
        print(f"import QuickAnalyzer 失敗: {e}")
        return

    summary = []

    for sym in symbols:
        print(f"\n{'='*60}")
        print(f"  股票: {sym}")
        print(f"{'='*60}")
        try:
            result = QuickAnalyzer.analyze_stock(sym, market="台股")
            if result is None:
                print("  ✗ 分析失敗（data None）")
                continue

            dm = result.get('decision_matrix', {})
            rec = result.get('recommendation', {})
            tl  = dm.get('three_layer', {})

            direction = tl.get('direction') or {}
            position  = tl.get('position')  or {}
            timing    = tl.get('timing')    or {}

            action_code = dm.get('action_code', '?')
            scenario    = dm.get('scenario',    '?')
            overall     = rec.get('overall',    '?') if isinstance(rec, dict) else str(rec)

            # ADX 盤整濾網
            mr_obj = result.get('market_regime', {})
            adx_market = mr_obj.get('adx', 'N/A')
            trend_dir  = mr_obj.get('trend_direction', 'N/A')

            print(f"\n  大盤: trend={trend_dir}  ADX={adx_market}")
            print(f"\n  最終: action_code={action_code}  scenario={scenario}")
            print(f"  overall: {overall}")

            # 判斷卡點
            d_score = direction.get('score', 0)
            p_score = position.get('score', 0) if position else -1
            grade   = timing.get('grade', 'N/A') if timing else 'N/A'

            if action_code == 'SKIP':
                stuck = 'L1-方向否決'
            elif action_code == 'WAIT':
                stuck = 'L2-位置否決'
            elif grade in ('C', 'X'):
                stuck = f'L3-時機弱({grade})'
            else:
                stuck = '通過三層'

            summary.append({
                'sym':        sym,
                'stuck':      stuck,
                'dir':        d_score,
                'pos':        p_score,
                'bias_z':     position.get('bias_z', 'N/A') if position else 'N/A',
                'grade':      grade,
                'action':     action_code,
                'overall':    overall[:30],
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ✗ 例外: {e}")

    # 摘要表格
    print(f"\n\n{'='*80}")
    print(f"  診斷摘要")
    print(f"{'='*80}")
    print(f"  {'代碼':6s}  {'卡點':18s}  {'L1':4s}  {'L2':4s}  {'bias_z':8s}  {'L3':4s}  {'action':12s}")
    print(f"  {'-'*6}  {'-'*18}  {'-'*4}  {'-'*4}  {'-'*8}  {'-'*4}  {'-'*12}")
    for r in summary:
        print(f"  {r['sym']:6s}  {r['stuck']:18s}  {r['dir']:4}  {r['pos']:4}  {str(r['bias_z']):8s}  {r['grade']:4s}  {r['action']:12s}")
    print()


DEFAULT_SYMBOLS = [
    "2330",  # 台積電（大型強勢）
    "2379",  # 瑞昱（近期強勢）
    "3293",  # 鈊象（題材股）
    "6669",  # 緯穎（AI 伺服器）
    "2454",  # 聯發科
]

if __name__ == "__main__":
    syms = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SYMBOLS
    print(f"診斷標的: {syms}")
    diagnose(syms)
