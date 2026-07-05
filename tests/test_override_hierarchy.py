"""
test_override_hierarchy.py — fix_prompt_07 驗收

裁決層級：賣出訊號 ＞ 大盤/籌碼濾網 ＞ 形態覆蓋。
驗證買進形態覆蓋防線、build_verdict 情緒 fail-safe、分數單一化。

執行：python tests/test_override_hierarchy.py
（合成資料，無需網路；build_verdict 的 chip_detail 走 DB，缺資料時回空 list 不影響。）
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_engine import ThreeLayerEngine
from report_formatter import build_verdict

_BUY_WORDS = ("買進", "進場", "佈局", "加碼")


def _base(pattern=None, market="多頭", wave=None, rsi=60, chip=None):
    r = {
        "symbol": "TEST", "name": "TEST 測試", "current_price": 100.0,
        "technical": {
            "signal": "中性", "rsi": rsi, "ma5": 101, "ma20": 100, "ma60": 98,
            "ma120": 96, "ma240": 94, "adx": 28, "ma20_series": [98, 99, 100, 101, 102, 103],
            "pth_52w": 0.90, "atr14": 2.0, "atr": 2.0, "volume_zscore": 0.5,
            "dist_from_low_52w": 0.4,
        },
        "fundamental": {"signal": "中性"},
        "relative_strength": {"rs_score": 55, "vs_market": 1},
        "mean_reversion": {"available": True, "bias_analysis": {"bias_20": 2.0}},
        "support_resistance": {"support1": 95, "resistance1": 108,
                               "take_profit": 106, "stop_loss": 93},
        "wave_analysis": wave if wave is not None else {
            "available": True, "is_bullish_env": True,
            "breakout_signal": {"detected": False}, "breakdown_signal": {"detected": False}},
        "pattern_analysis": pattern or {"detected": False},
        "volume_price": {"available": True, "signals": []},
        "volume_analysis": {"volume_ratio": 1.1, "current_volume": 17000000, "avg_volume": 15000000},
        "risk_manager": {"available": True, "position_pct": 15.0},
        "chip_flow": chip or {"available": True, "data_source": "finmind", "signal": "籌碼中性",
                              "consecutive_buy_days": 0, "consecutive_sell_days": 0,
                              "foreign_consecutive_days": 0, "trust_consecutive_days": 0,
                              "foreign_net": 0, "trust_net": 0, "dealer_net": 0,
                              "avg_sell_net_5d": 0, "data_reliable": True, "missing_dates": []},
        "market_regime": {"available": True, "trend_direction": market, "adx": 28},
    }
    return r


def _run(result):
    from main import QuickAnalyzer
    dm = ThreeLayerEngine.analyze(result)
    result["decision_matrix"] = dm
    result["recommendation"] = QuickAnalyzer._generate_recommendation_v43(result, dm)
    return build_verdict(result)


def test_1_sell_beats_vshape_buy_override():
    """賣訊觸發 + V型 CONFIRMED buy → 裁決屬賣出族、無買進字樣、trail 有賣訊與形態註記。"""
    pat = {"available": True, "detected": True, "pattern_type": "bottom", "signal": "buy", "status": "CONFIRMED",
           "pattern_name": "V型反轉", "volume_confirmed": True, "target_price": 120,
           "description": "V型急拉反彈"}
    # 三盤跌破 → DEFENSIVE urgent sell → scenario SELL
    wave = {"available": True, "is_bullish_env": False,
            "breakout_signal": {"detected": False},
            "breakdown_signal": {"detected": True}}
    v = _run(_base(pattern=pat, wave=wave))
    assert v["grade"] in ("SELL",), f"應為賣出裁決，實得 {v['grade']}"
    assert not any(w in v["overall_text"] for w in _BUY_WORDS), \
        f"overall 不應含買進字樣：{v['overall_text']}"
    stages = {a["stage"]: a for a in v["adjustments"]}
    assert "賣出訊號" in stages and stages["賣出訊號"]["to"] == "SELL", "trail 應含賣出訊號階段"
    pat_step = stages.get("形態覆蓋", {})
    assert pat_step.get("to") is None and "不改變裁決" in (pat_step.get("reason") or ""), \
        f"形態覆蓋應被擋（to=None）：{pat_step}"
    print(f"[1] 賣訊優先：grade={v['grade']} overall={v['overall_text'][:20]} "
          f"| 形態註記={pat_step.get('reason')}")


def test_2_head_shoulder_override_applies():
    """頭肩底 CONFIRMED + 引擎非賣非否決 + 防線全過 → 覆蓋生效（強烈建議買進）。"""
    pat = {"available": True, "detected": True, "pattern_type": "bottom", "signal": "buy", "status": "CONFIRMED",
           "pattern_name": "頭肩底", "volume_confirmed": True, "target_price": 115,
           "description": "頭肩底頸線突破"}
    v = _run(_base(pattern=pat))
    assert "買進" in v["overall_text"], f"頭肩底防線全過應覆蓋為買進：{v['overall_text']}"
    stages = {a["stage"]: a for a in v["adjustments"]}
    pat_step = stages.get("形態覆蓋", {})
    assert pat_step.get("to") and pat_step.get("from") != pat_step.get("to"), \
        f"覆蓋成功應記錄文字層 from/to：{pat_step}"
    print(f"[2] 頭肩底覆蓋生效：overall={v['overall_text'][:24]} | trail to={pat_step.get('to')[:16]}")


def test_3_pending_volume_no_override():
    """形態量能待確認 → 不覆蓋。"""
    pat = {"available": True, "detected": True, "pattern_type": "bottom", "signal": "buy",
           "status": "CONFIRMED（量能待確認）", "pattern_name": "頭肩底",
           "volume_confirmed": False, "target_price": 115, "description": "頸線突破但量能待確認"}
    v = _run(_base(pattern=pat))
    assert "強烈建議買進" not in v["overall_text"], f"待確認不應覆蓋：{v['overall_text']}"
    stages = {a["stage"]: a for a in v["adjustments"]}
    assert "量能待確認" in (stages.get("形態覆蓋", {}).get("reason") or ""), "應記錄量能待確認"
    print(f"[3] 量能待確認不覆蓋：overall={v['overall_text'][:20]}")


def test_4_failsafe_text_action_mismatch():
    """fail-safe：text/action 矛盾 → 自動校正 + warning。"""
    result = {
        "symbol": "X", "name": "X",
        "decision_matrix": {"available": True, "scenario": "SELL", "action_code": "SELL",
                            "score": 25, "scenario_name": "賣出訊號",
                            "three_layer": {"sell_signal": {"triggered": True}},
                            "adjustment_trail": []},
        "recommendation": {"overall": "強烈建議買進（測試矛盾）", "short_term": {}, "mid_term": {}, "long_term": {}},
    }
    v = build_verdict(result)
    assert not any(w in v["overall_text"] for w in _BUY_WORDS), \
        f"fail-safe 應移除買進字樣：{v['overall_text']}"
    assert any("自動校正" in w for w in v["warnings"]), f"應有校正警示：{v['warnings']}"
    print(f"[4] fail-safe：overall 校正為 {v['overall_text']} | warn={[w for w in v['warnings'] if '校正' in w]}")


if __name__ == "__main__":
    test_1_sell_beats_vshape_buy_override()
    test_2_head_shoulder_override_applies()
    test_3_pending_volume_no_override()
    test_4_failsafe_text_action_mismatch()
    print("\nALL OVERRIDE HIERARCHY TESTS PASSED")
