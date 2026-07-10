import os, tempfile
import pandas as pd
import signal_backtest as sb


def test_hist_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    os.makedirs('backtest_results', exist_ok=True)
    data = {'2330': pd.DataFrame({'Close': [1.0, 2.0]}),
            '2317': pd.DataFrame({'Close': [3.0, 4.0]})}
    assert sb._load_hist_cache('2019-06-01') is None      # no cache yet
    sb._save_hist_cache(data, '2019-06-01')
    loaded = sb._load_hist_cache('2019-06-01')
    assert loaded is not None and set(loaded.keys()) == {'2330', '2317'}
    assert sb._load_hist_cache('2020-01-01') is None       # different window key → miss


def test_cache_path_keyed_by_window():
    assert sb._hist_cache_path('2019-06-01') != sb._hist_cache_path('2020-01-01')
