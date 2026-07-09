"""
test_serve_from_batch.py — build_prompt_11 Task 4 批次快取切片守門單元測試

守門點：_serve_from_batch 不得把「只有 2y 覆蓋」的批次快取，當成「回溯到 2020」
的請求的合法結果回傳（靜默截斷陷阱）。當要求的 start_date 早於快取最早日期時，
應回 None（cache miss → 觸發真正的帶日期抓取）。

執行：python tests/test_serve_from_batch.py
"""
import os
import sys
import datetime
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import data_fetcher as D


def _make_2y_cache(symbol="2330", market="台股"):
    """灌一份合成的 2 年日線進 _batch_hist_cache（今天新鮮）。"""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=730)
    idx = pd.date_range(start=start, end=today, freq="D")
    df = pd.DataFrame({
        "Open": 100.0, "High": 101.0, "Low": 99.0,
        "Close": 100.0, "Volume": 1000,
    }, index=idx)
    D.DataSourceManager._batch_hist_cache[f"{symbol}|{market}"] = (
        today.isoformat(), df.copy())
    return df


def test_string_start_before_coverage_returns_none():
    """字串 start_date="2020-01-01" 早於 2y 快取覆蓋 → 回 None（強制真正抓取）。"""
    _make_2y_cache()
    out = D.DataSourceManager._serve_from_batch(
        "2330", "台股", "2020-01-01", None, None)
    assert out is None, f"應回 None（cache miss），實得 {type(out)} len={0 if out is None else len(out)}"
    print("[1] 字串 start_date 早於快取覆蓋 → 回 None，不靜默截斷")


def test_datetime_start_within_coverage_filters():
    """datetime start（覆蓋內，1 年前）→ 正常切片，僅回 start 之後的列。"""
    df = _make_2y_cache()
    start = datetime.datetime.combine(
        datetime.date.today() - datetime.timedelta(days=365),
        datetime.time.min)
    out = D.DataSourceManager._serve_from_batch(
        "2330", "台股", start, None, None)
    assert out is not None, "覆蓋內的 datetime start 不應回 None"
    assert len(out) < len(df), f"應被切片變短：{len(out)} vs {len(df)}"
    assert out.index.min() >= pd.Timestamp(start), \
        f"最早列 {out.index.min()} 不應早於 start {start}"
    print(f"[2] datetime start（覆蓋內）正常切片：{len(df)} → {len(out)} 列")


def test_string_start_within_coverage_filters():
    """字串 start_date（覆蓋內）也應被 coerce 成 datetime 並正確切片。"""
    df = _make_2y_cache()
    start_date = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()
    out = D.DataSourceManager._serve_from_batch(
        "2330", "台股", start_date, None, None)
    assert out is not None, "覆蓋內的字串 start 不應回 None"
    assert len(out) < len(df), f"應被切片變短：{len(out)} vs {len(df)}"
    assert out.index.min() >= pd.Timestamp(start_date), \
        f"最早列 {out.index.min()} 不應早於 start {start_date}"
    print(f"[3] 字串 start（覆蓋內）coerce 後正常切片：{len(df)} → {len(out)} 列")


if __name__ == "__main__":
    test_string_start_before_coverage_returns_none()
    test_datetime_start_within_coverage_filters()
    test_string_start_within_coverage_filters()
    print("\nALL SERVE-FROM-BATCH TESTS PASSED")
