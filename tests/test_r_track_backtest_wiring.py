"""build_prompt_12 任務3：R 軌回測接線的輕量單元測試。

只測 write_r_track_summary 對合成 trades 的彙總輸出，
不跑完整回測（signal_backtest.main）。
"""
import os
import statistics

import signal_backtest as sb


def _read_summary(tmp_path):
    with open(os.path.join(tmp_path, 'summary.md'), encoding='utf-8') as f:
        return f.read()


def test_r_track_summary_trade_and_watch(tmp_path):
    out_dir = str(tmp_path)
    holds = [5, 10, 20]
    # R-TRADE ×3（盤整），R-WATCH 多頭 ×2、空頭 ×1，加一筆非 R 訊號（應被忽略）。
    trades = [
        {'r_signal': 'R-TRADE', 'regime': '盤整', 'ret_10_net': 2.0},
        {'r_signal': 'R-TRADE', 'regime': '盤整', 'ret_10_net': -1.0},
        {'r_signal': 'R-TRADE', 'regime': '盤整', 'ret_10_net': 4.0},
        {'r_signal': 'R-WATCH', 'regime': '多頭', 'ret_10_net': 1.0},
        {'r_signal': 'R-WATCH', 'regime': '多頭', 'ret_10_net': 3.0},
        {'r_signal': 'R-WATCH', 'regime': '空頭', 'ret_10_net': -2.0},
        {'r_signal': None, 'regime': '盤整', 'ret_10_net': 9.0},
    ]

    sb.write_r_track_summary(trades, holds, out_dir)
    txt = _read_summary(tmp_path)

    # 標題
    assert "## R 軌矩陣（build_prompt_12）" in txt
    # R-TRADE n=3、平均 = mean(2,-1,4)
    mean_trade = statistics.mean([2.0, -1.0, 4.0])
    assert f"| R-TRADE | 3 |" in txt
    assert f"{mean_trade:.3f}%" in txt
    # R-WATCH 多頭 n=2、平均 mean(1,3)=2.0
    assert "| 多頭 | 2 |" in txt
    assert f"{statistics.mean([1.0, 3.0]):.3f}%" in txt
    # R-WATCH 空頭 n=1
    assert "| 空頭 | 1 |" in txt
    # 非 R 訊號的 9.0 不得混入任何統計
    assert "9.000%" not in txt


def test_r_track_summary_disabled_empty(tmp_path):
    out_dir = str(tmp_path)
    # 全部無 R 訊號 → 視同 R_TRACK 未啟用
    trades = [
        {'r_signal': None, 'regime': '多頭', 'ret_10_net': 1.0},
        {'r_signal': None, 'regime': '盤整', 'ret_10_net': -2.0},
    ]
    sb.write_r_track_summary(trades, [5, 10, 20], out_dir)
    txt = _read_summary(tmp_path)
    assert "R_TRACK 未啟用（本輪無 R 訊號）" in txt


def test_r_track_summary_no_ten_hold_uses_closest(tmp_path):
    out_dir = str(tmp_path)
    # holds 不含 10 → 用最接近（此處 8），並讀 ret_8_net
    holds = [5, 8, 20]
    trades = [
        {'r_signal': 'R-TRADE', 'regime': '盤整', 'ret_8_net': 2.0},
        {'r_signal': 'R-TRADE', 'regime': '盤整', 'ret_8_net': 6.0},
    ]
    sb.write_r_track_summary(trades, holds, out_dir)
    txt = _read_summary(tmp_path)
    assert "holds 不含 10，改用最接近的 8 日" in txt
    assert "| R-TRADE | 2 |" in txt
    assert f"{statistics.mean([2.0, 6.0]):.3f}%" in txt
