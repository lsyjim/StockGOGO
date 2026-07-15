"""build_prompt_12 Task5：R 軌 watchlist DB 遷移單元測試。

驗收目標（不啟動 GUI）：
  1. 對「沒有 r_signal 欄位」的 watchlist 表執行遷移 → 欄位出現。
  2. 再次執行 → 不報錯、欄位仍在（冪等）。
  3. 既有列/資料在遷移後完整保留（無資料遺失）。
  4. persist_r_signal / load_r_signal_map 讀寫獨立欄位，且不動其他欄位。
"""
import os
import sqlite3
import tempfile

import main


def _make_legacy_watchlist_db(path):
    """建立一個「舊版」watchlist 表（刻意不含 r_signal 欄位）並塞入一列資料。"""
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            name TEXT,
            market TEXT DEFAULT '台股',
            recommendation TEXT DEFAULT '待分析'
        )
    ''')
    cur.execute("INSERT INTO watchlist (symbol, name, market, recommendation) VALUES (?,?,?,?)",
                ('2330', '台積電', '台股', 'A 主攻|突破|買進|即刻'))
    conn.commit()
    conn.close()


def _columns(path):
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(watchlist)")
        return [c[1] for c in cur.fetchall()]
    finally:
        conn.close()


def test_migration_adds_column_then_idempotent_and_preserves_data():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'wl_test.db')
        _make_legacy_watchlist_db(path)

        # 前置：確認舊表沒有 r_signal
        assert 'r_signal' not in _columns(path)

        # 1) 首次遷移 → 欄位出現
        assert main.migrate_watchlist_r_signal(path) is True
        assert 'r_signal' in _columns(path)

        # 3) 既有資料完整保留
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT symbol, name, market, recommendation FROM watchlist WHERE symbol='2330'"
        ).fetchone()
        conn.close()
        assert row == ('2330', '台積電', '台股', 'A 主攻|突破|買進|即刻')

        # 2) 再次遷移 → 不報錯、欄位仍在（冪等），資料仍在
        assert main.migrate_watchlist_r_signal(path) is True
        assert 'r_signal' in _columns(path)
        conn = sqlite3.connect(path)
        cnt = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        conn.close()
        assert cnt == 1

        # 4) persist / load 獨立欄位往返
        main.persist_r_signal(path, '2330', 'R-TRADE')
        rmap = main.load_r_signal_map(path)
        assert rmap.get('2330') == 'R-TRADE'

        # 確認未破壞既有欄位
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT name, recommendation FROM watchlist WHERE symbol='2330'"
        ).fetchone()
        conn.close()
        assert row == ('台積電', 'A 主攻|突破|買進|即刻')


def test_migration_on_missing_table_returns_false():
    """watchlist 表不存在時遷移不應拋例外，回傳 False。"""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'empty.db')
        # 建一個空 DB（無 watchlist 表）
        sqlite3.connect(path).close()
        assert main.migrate_watchlist_r_signal(path) is False


def test_load_r_signal_map_empty_when_no_column():
    """欄位不存在時 load_r_signal_map 回傳空 dict，不拋例外。"""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'wl_nocol.db')
        _make_legacy_watchlist_db(path)
        assert main.load_r_signal_map(path) == {}
