"""
test_deep_backfill_batch.py — fix_prompt_16 驗收條件 1 與 2

驗收1（正確性等價）：混合情境（部分已有資料、部分全空）下，
  「逐檔 deep_backfill」與「一次 deep_backfill_batch」跑完後
  chip_daily 全欄位逐列相同。
驗收2（效能改善量化）：新版官方備援請求數 == 不重複交易日數，
  而非 symbol數 × 平均缺洞數。

以 mock 取代真實 HTTP（不打外網），故可在 CI 重複執行。
執行：python tests/test_deep_backfill_batch.py
"""
import os
import sys
import time
import sqlite3
import datetime
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chip_data_manager as C

SYMS = ['1101', '1102', '2201', '2301', '2302', '2303', '2311', '2312']
DAYS = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08']
START = '2024-01-01'

# 前 3 檔 FinMind 有資料；後 5 檔完全空白 → 混合情境
FINMIND_OK = set(SYMS[:3])


def _mgr(db):
    m = C.ChipDataManager(db_name=db)
    conn = sqlite3.connect(db)
    conn.executemany("INSERT OR REPLACE INTO trading_calendar (date, source) VALUES (?,?)",
                     [(d, 'test') for d in DAYS])
    conn.commit()
    conn.close()
    return m


def _install_mocks(m, gov_counter):
    """FinMind：前 3 檔回 2 天資料；官方 T86/TPEx：回全部 symbol，並計數請求。"""
    def fake_finmind(symbol, start_date, end_date):
        if str(symbol) not in FINMIND_OK:
            return None
        return {DAYS[0]: dict(f_net=10, t_net=1, d_net=0, f_buy=100, f_sell=90,
                              t_buy=5, t_sell=4, d_buy=0, d_sell=0),
                DAYS[1]: dict(f_net=-5, t_net=2, d_net=1, f_buy=50, f_sell=55,
                              t_buy=6, t_sell=4, d_buy=2, d_sell=1)}

    def fake_t86(date_str):
        gov_counter.append(('t86', date_str))
        # 回全部測試 symbol，值由 (symbol,date) 決定 → 可比對等價性
        return {s: tuple(((hash((s, date_str)) % 7) - 3) * k for k in range(1, 10))
                for s in SYMS}

    def fake_tpex(date_str):
        gov_counter.append(('tpex', date_str))
        return {}

    m._fetch_finmind_chip = fake_finmind
    m._fetch_twse_t86 = fake_t86
    m._fetch_tpex_hist = fake_tpex
    m._gov_get = lambda *a, **k: None       # 保險：不得有真實 HTTP
    return m


def _dump(db):
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT symbol,date,foreign_net,trust_net,dealer_net,foreign_buy,foreign_sell,"
        "trust_buy,trust_sell,dealer_buy,dealer_sell FROM chip_daily "
        "ORDER BY symbol,date").fetchall()
    conn.close()
    return rows


def test_1_equivalence_and_2_efficiency():
    d = tempfile.mkdtemp()
    db_old, db_new = os.path.join(d, 'old.db'), os.path.join(d, 'new.db')

    # 舊版：逐檔 deep_backfill
    m_old = _mgr(db_old)
    gov_old = []
    _install_mocks(m_old, gov_old)
    t0 = time.time()
    for s in SYMS:
        m_old.deep_backfill(s, start_date=START)
    t_old = time.time() - t0

    # 新版：一次 deep_backfill_batch
    m_new = _mgr(db_new)
    gov_new = []
    _install_mocks(m_new, gov_new)
    t1 = time.time()
    m_new.deep_backfill_batch(SYMS, start_date=START)
    t_new = time.time() - t1

    old_rows, new_rows = _dump(db_old), _dump(db_new)
    print(f"[1] 正確性等價：舊版 {len(old_rows)} 列 / 新版 {len(new_rows)} 列")
    assert len(old_rows) == len(new_rows), "列數不同"
    diff = [(a, b) for a, b in zip(old_rows, new_rows) if a != b]
    assert not diff, f"內容不同，前3筆差異：{diff[:3]}"
    print(f"    ✓ chip_daily 全欄位逐列相同（{len(new_rows)} 列）")

    n_days = len({d for _t, d in gov_new})
    print(f"[2] 效能量化：")
    print(f"    舊版官方備援請求 {len(gov_old)} 次（symbol數 × 缺洞數 的量級）")
    print(f"    新版官方備援請求 {len(gov_new)} 次")
    print(f"    不重複交易日數 {n_days}")
    print(f"    wall-clock：舊 {t_old*1000:.1f}ms → 新 {t_new*1000:.1f}ms")
    # 新版：每個有缺洞的日期最多 t86 + tpex 各一次
    assert len(gov_new) <= n_days * 2, \
        f"新版請求數 {len(gov_new)} 超過不重複日數×2 ({n_days*2})"
    assert len(gov_new) < len(gov_old), \
        f"新版請求數未減少（{len(gov_new)} vs {len(gov_old)}）"
    print(f"    ✓ 請求數由 {len(gov_old)} 降為 {len(gov_new)}"
          f"（減少 {(1-len(gov_new)/len(gov_old)):.0%}），與 symbol 數解耦")


def test_3_single_symbol_behaviour_unchanged():
    """單檔 deep_backfill 的回傳語意未變（FinMind 寫入筆數）。"""
    d = tempfile.mkdtemp()
    db = os.path.join(d, 's.db')
    m = _mgr(db)
    _install_mocks(m, [])
    w = m.deep_backfill(SYMS[0], start_date=START)
    assert w == 2, f"FinMind 有資料的檔應回 2，實得 {w}"
    w0 = m.deep_backfill(SYMS[5], start_date=START)
    assert w0 == 0, f"FinMind 無資料的檔應回 0，實得 {w0}"
    print("[3] 單檔 deep_backfill 回傳語意未變（2 / 0）")


def test_4_batch_return_shape():
    """批次版回傳 {symbol: FinMind寫入筆數}，涵蓋全部傳入 symbol。"""
    d = tempfile.mkdtemp()
    db = os.path.join(d, 'b.db')
    m = _mgr(db)
    _install_mocks(m, [])
    out = m.deep_backfill_batch(SYMS, start_date=START)
    assert set(out) == set(SYMS), "回傳未涵蓋全部 symbol"
    assert all(out[s] == 2 for s in FINMIND_OK), "FinMind 有資料的檔應為 2"
    assert all(out[s] == 0 for s in SYMS if s not in FINMIND_OK), "無資料的檔應為 0"
    print(f"[4] 批次回傳形狀正確：{ {k: out[k] for k in SYMS[:4]} } …")


if __name__ == '__main__':
    test_1_equivalence_and_2_efficiency()
    test_3_single_symbol_behaviour_unchanged()
    test_4_batch_return_shape()
    print("\nALL DEEP-BACKFILL-BATCH TESTS PASSED")
