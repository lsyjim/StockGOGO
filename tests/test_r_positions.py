"""fix_13b P1-4：r_positions.json 讀寫容錯 + 出場日推算測試。

驗收（fix_prompt 驗收標準 4）：登記 群創(3481, 2026-07-16)，以 07-17 為當日 →
「第 2/10 天」，出場日以 trading_calendar 推第 10 交易日。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


# ── 載入容錯 ───────────────────────────────────────────────────────────
def test_missing_file_is_no_registration(tmp_path):
    p = str(tmp_path / 'nope.json')
    positions, err = main.load_r_positions(p)
    assert positions == []
    assert err is None


def test_malformed_json_is_ignored_with_message(tmp_path):
    p = tmp_path / 'r_positions.json'
    p.write_text('{ this is not valid json', encoding='utf-8')
    positions, err = main.load_r_positions(str(p))
    assert positions == []
    assert err is not None and 'r_positions.json' in err


def test_non_list_root_is_ignored(tmp_path):
    p = tmp_path / 'r_positions.json'
    p.write_text('{"symbol": "3481"}', encoding='utf-8')
    positions, err = main.load_r_positions(str(p))
    assert positions == []
    assert err is not None


def test_bad_items_skipped_good_kept(tmp_path):
    p = tmp_path / 'r_positions.json'
    data = [
        {'symbol': '3481', 'entry_date': '2026-07-16'},   # ok
        {'symbol': '', 'entry_date': '2026-07-16'},        # 缺代碼 → skip
        {'symbol': '2330'},                                # 缺日期 → skip
        {'symbol': '6285', 'entry_date': 'not-a-date'},    # 日期壞 → skip
        'garbage',                                         # 非 dict → skip
    ]
    p.write_text(json.dumps(data), encoding='utf-8')
    positions, err = main.load_r_positions(str(p))
    assert err is None
    assert positions == [{'symbol': '3481', 'entry_date': '2026-07-16'}]


# ── round-trip ─────────────────────────────────────────────────────────
def test_save_load_roundtrip(tmp_path):
    p = str(tmp_path / 'r_positions.json')
    positions = [{'symbol': '3481', 'entry_date': '2026-07-16'},
                 {'symbol': '2330', 'entry_date': '2026-07-10'}]
    err = main.save_r_positions(positions, p)
    assert err is None
    loaded, lerr = main.load_r_positions(p)
    assert lerr is None
    assert loaded == positions


def test_save_drops_incomplete_rows(tmp_path):
    p = str(tmp_path / 'r_positions.json')
    main.save_r_positions([{'symbol': '3481', 'entry_date': '2026-07-16'},
                           {'symbol': '', 'entry_date': 'x'}], p)
    loaded, _ = main.load_r_positions(p)
    assert loaded == [{'symbol': '3481', 'entry_date': '2026-07-16'}]


# ── 出場日 / 第 N 天推算 ───────────────────────────────────────────────
def _cal(*dates):
    return list(dates)


def test_progress_with_full_calendar():
    """驗收標準 4：3481 進場 07-16，當日 07-17 → 第 2/10 天，出場日＝第 10 交易日。"""
    # 07-16 起連續 10 個交易日（略過週末 07-18/19、07-25/26）
    cal = _cal('2026-07-16', '2026-07-17', '2026-07-20', '2026-07-21', '2026-07-22',
               '2026-07-23', '2026-07-24', '2026-07-27', '2026-07-28', '2026-07-29',
               '2026-07-30')
    day_n, hold, exit_d, est = main.r_position_progress(
        '2026-07-16', trading_days=cal, today='2026-07-17', hold_days=10)
    assert day_n == 2
    assert hold == 10
    assert est is False
    # 進場日之後第 10 個交易日
    assert exit_d == '2026-07-30'


def test_progress_exit_estimated_when_calendar_short():
    """日曆未涵蓋足夠未來日 → 以週間日外推，estimated=True。"""
    cal = _cal('2026-07-16', '2026-07-17')   # 未來只有 1 天
    day_n, hold, exit_d, est = main.r_position_progress(
        '2026-07-16', trading_days=cal, today='2026-07-17', hold_days=10)
    assert est is True
    assert exit_d > '2026-07-17'
    # 出場日必為週間日
    import datetime
    assert datetime.datetime.strptime(exit_d, '%Y-%m-%d').weekday() < 5


def test_progress_no_calendar_falls_back_to_weekdays():
    day_n, hold, exit_d, est = main.r_position_progress(
        '2026-07-16', trading_days=[], today='2026-07-16', hold_days=10)
    assert day_n == 1
    assert est is True
    assert exit_d > '2026-07-16'
