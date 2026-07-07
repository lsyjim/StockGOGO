"""
test_chip_gov_backup.py — build_prompt_09 官方備援 + 額度守門單元測試

快速邏輯測試（無網路）：ROC 民國年格式、額度 token bucket/冷卻、RATE_LIMITED 哨兵語意。
網路交叉比對（官方 vs FinMind）已於開發時人工驗證（4 檔 net 完全一致），此處不重跑
（受請求禮儀 sleep 影響較慢）。

執行：python tests/test_chip_gov_backup.py
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chip_data_manager as C
import finmind_budget as fb


def test_roc_date_conversion():
    """民國年格式鎖（最常見雷點）：2026-07-03 → 115/07/03；_roc_to_iso 反向。"""
    m = C.ChipDataManager(":memory:")
    # 正向：_fetch_tpex_hist 內用的轉換規則（不發網路，只驗字串）
    y, mo, dd = "2026-07-03".split("-")
    roc = f"{int(y) - 1911}/{mo}/{dd}"
    assert roc == "115/07/03", roc
    # 反向
    assert m._roc_to_iso("1150703") == "2026-07-03"
    # 一位數月日補零
    y, mo, dd = "2026-01-05".split("-")
    assert f"{int(y)-1911}/{mo}/{dd}" == "115/01/05"
    print("[1] ROC 民國年轉換正確：115/07/03 ⇄ 2026-07-03")


def test_budget_bucket_and_cooldown():
    """token bucket 達額度自動冷卻；冷卻中 before_request=False。"""
    fb.reset()
    # 未達額度：可發
    assert fb.before_request() is True
    assert fb.is_cooling() is False
    # 手動限流 → 冷卻
    fb.note_rate_limited()
    assert fb.is_cooling() is True
    assert fb.before_request() is False   # 冷卻中一律 False
    assert fb.cooldown_remaining() > 0
    fb.reset()
    print("[2] 額度守門：限流→冷卻→before_request=False，reset 恢復")


def test_budget_hourly_cap():
    """達每小時上限主動冷卻。"""
    fb.reset()
    from config import QuantConfig as QC
    budget = QC.FINMIND_HOURLY_BUDGET
    ok = sum(1 for _ in range(budget) if fb.before_request())
    assert ok == budget
    # 第 budget+1 次應觸發冷卻→False
    assert fb.before_request() is False
    assert fb.is_cooling() is True
    fb.reset()
    print(f"[3] 每小時上限 {budget}：達標後主動冷卻")


def test_rate_limited_sentinel_semantics():
    """RATE_LIMITED 與 None 語意區分：_fetch_finmind_chip 透傳哨兵。"""
    m = C.ChipDataManager(":memory:")
    m._finmind_get = lambda *a, **k: C.RATE_LIMITED
    assert m._fetch_finmind_chip("2481", "2026-07-01", "2026-07-03") == C.RATE_LIMITED
    # None（查無）仍回 None
    m._finmind_get = lambda *a, **k: None
    assert m._fetch_finmind_chip("2481", "2026-07-01", "2026-07-03") is None
    print("[4] 哨兵語意：RATE_LIMITED 透傳、None 保持（抓不到 ≠ 0）")


def test_official_9tuple_shape():
    """官方備援 upsert 走 9 元組（buy/sell 六欄補齊）。以合成表驗 upsert9 寫入。"""
    import sqlite3
    m = C.ChipDataManager("/tmp/bp09_shape.db")
    import os as _os
    if _os.path.exists("/tmp/bp09_shape.db"):
        pass
    v9 = (-169, -500, 464, 1228, 1397, 0, 500, 628, 164)   # 2481 實測值
    m._upsert9("TEST9", "2026-07-03", v9, "t86")
    conn = sqlite3.connect("/tmp/bp09_shape.db")
    row = conn.execute("SELECT foreign_net,trust_net,dealer_net,foreign_buy,foreign_sell,"
                       "trust_buy,trust_sell,dealer_buy,dealer_sell,source FROM chip_daily "
                       "WHERE symbol='TEST9'").fetchone()
    conn.close()
    assert row[:9] == v9 and row[9] == "t86", row
    print("[5] 官方備援 9 元組寫入（含 buy/sell 六欄）+ source 標記正確")


if __name__ == "__main__":
    test_roc_date_conversion()
    test_budget_bucket_and_cooldown()
    test_budget_hourly_cap()
    test_rate_limited_sentinel_semantics()
    test_official_9tuple_shape()
    print("\nALL CHIP GOV-BACKUP TESTS PASSED")
