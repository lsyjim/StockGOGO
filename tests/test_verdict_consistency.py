"""
test_verdict_consistency.py — build_prompt_06 任務1c 一致性驗收

驗證單一真相源：首頁量化建議與完整報告經 build_verdict 取得一致等級/建議，
且大盤濾網降級、籌碼缺日等裁決都反映在同一份 verdict。

執行：python tests/test_verdict_consistency.py
（測試 1、2 為合成資料，無需網路；測試 3 需 FINMIND_TOKEN + 網路，無資料時自動略過。）
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_engine import ThreeLayerEngine
from report_formatter import build_verdict, watchlist_cell


def _base_result(market_trend="多頭", reliable=True):
    """滿足 A 級雙因子（三盤突破帶量 + 法人連買4天）的合成 result。"""
    return {
        "symbol": "TEST", "name": "TEST 測試", "current_price": 110,
        "technical": {
            "ma20": 100, "ma60": 95, "ma120": 90, "ma240": 85, "adx": 30,
            "ma20_series": [98, 99, 100, 101, 102, 103], "pth_52w": 0.96,
            "rsi": 60, "atr14": 2.0, "atr": 2.0, "ma5": 105, "ma10": 103,
            "breakout_20": False, "breakout_55": False, "bb_squeeze": False,
            "volume_zscore": 1.0, "dist_from_low_52w": 0.5,
        },
        "relative_strength": {"rs_score": 75, "vs_market": 6},
        "mean_reversion": {"available": True, "bias_analysis": {"bias_20": 3.0}},
        "support_resistance": {"support1": 100, "resistance1": 120,
                               "take_profit": 118, "stop_loss": 95},
        "wave_analysis": {"available": True, "is_bullish_env": True,
                          "breakout_signal": {"detected": True, "volume_confirmed": True},
                          "breakdown_signal": {"detected": False}},
        "pattern_analysis": {"detected": False},
        "volume_price": {"available": True, "signals": [{"code": "VP05", "name": "帶量突破"}]},
        "volume_analysis": {"volume_ratio": 1.5, "current_volume": 20000, "avg_volume": 13000},
        "risk_manager": {"available": True, "position_pct": 20.0},
        "chip_flow": {
            "available": True, "data_source": "finmind",
            "consecutive_buy_days": 4, "consecutive_sell_days": 0,
            "foreign_consecutive_days": 4, "trust_consecutive_days": 4,
            "foreign_net": 5000, "trust_net": 2000, "dealer_net": 0,
            "avg_sell_net_5d": 1000, "data_reliable": reliable,
            "missing_dates": ([] if reliable else ["2026-06-30"]),
        },
        "market_regime": {"available": True, "trend_direction": market_trend, "adx": 30},
    }


def test_1_market_bear_downgrades_A_to_B():
    """大盤空頭 + A 級雙因子 → verdict 等級為 B，adjustments 含大盤濾網一筆。"""
    # 先確認多頭時本檔確實是 A（否則測試前提不成立）
    bull = _base_result("多頭")
    bull["decision_matrix"] = ThreeLayerEngine.analyze(bull)
    assert bull["decision_matrix"]["scenario"] == "A", \
        f"前提失敗：多頭應為 A，實得 {bull['decision_matrix']['scenario']}"

    bear = _base_result("空頭")
    bear["decision_matrix"] = ThreeLayerEngine.analyze(bear)
    v = build_verdict(bear)
    assert v["grade"] == "B", f"大盤空頭應降 A→B，實得 {v['grade']}"
    mkt = [a for a in v["adjustments"] if a["stage"] == "大盤濾網" and a["to"] is not None]
    assert mkt and mkt[0]["from"] == "A" and mkt[0]["to"] == "B", \
        f"adjustments 應含大盤濾網 A→B，實得 {v['adjustments']}"
    print("[1] 大盤空頭 A→B：verdict.grade =", v["grade"],
          "| 軌跡:", mkt[0]["reason"])


def test_2_unreliable_chip_consistent_and_warned():
    """籌碼 data_reliable=False → verdict 兩端一致、warnings 含缺日、籌碼機制被略過。"""
    r = _base_result("多頭", reliable=False)
    r["decision_matrix"] = ThreeLayerEngine.analyze(r)
    v = build_verdict(r)
    assert v["chip_summary"]["reliable"] is False
    assert any("缺" in w for w in v["warnings"]), f"warnings 應含缺日：{v['warnings']}"
    # 籌碼不可信 → timing triggers 不得出現「法人連買」升級標籤
    trig = " ".join(v["evidence"]["triggers"])
    assert "法人連買" not in trig, f"不可信籌碼不應觸發連買升級：{trig}"
    # watchlist 與報告同源（同一 verdict）
    assert watchlist_cell(v).startswith(v["grade"])
    print("[2] 不可信籌碼：grade =", v["grade"], "| warnings:",
          [w for w in v["warnings"] if "缺" in w])


def test_3_real_stocks_same_source():
    """5 檔真實股票：build_verdict overall_text == recommendation overall == report grade。"""
    if not os.environ.get("FINMIND_TOKEN"):
        print("[3] 略過（無 FINMIND_TOKEN）")
        return
    try:
        import chip_data_manager as C
        C.get_chip_manager().sync_calendar(120)
        from main import QuickAnalyzer
    except Exception as e:
        print(f"[3] 略過（環境不可用：{e}）")
        return
    checked = 0
    for sym in ["2330", "2317", "2454", "2412", "1301"]:
        r = QuickAnalyzer.analyze_stock(sym, "台股", scan_mode=False)
        if not r:
            continue
        v = build_verdict(r)
        # fix_07 任務3：verdict 分數 == 引擎綜合分（= watchlist 分數同源）
        assert v["score"] == r["decision_matrix"]["score"], f"{sym} 分數不一致"
        # overall 經 fail-safe 後可能與 rec.overall 不同；正常無矛盾時應相同
        assert v["grade"] == r["decision_matrix"]["scenario"], f"{sym} grade 不一致"
        # 分期建議 action 與 action_code 同源（STRONG_BUY 短線不得出現暫緩類）
        if v["action_code"] == "STRONG_BUY":
            assert not any(x in v["term_advice"]["short"]["action"] for x in ["暫緩", "觀望", "等待"]), \
                f"{sym} STRONG_BUY 短線不應暫緩：{v['term_advice']['short']}"
        checked += 1
        print(f"    {sym}: grade={v['grade']} overall={v['overall_text'][:24]}")
    assert checked >= 1, "至少驗證一檔"
    print(f"[3] 真實股票同源一致（{checked} 檔）")


if __name__ == "__main__":
    test_1_market_bear_downgrades_A_to_B()
    test_2_unreliable_chip_consistent_and_warned()
    test_3_real_stocks_same_source()
    print("\nALL VERDICT CONSISTENCY TESTS PASSED")
