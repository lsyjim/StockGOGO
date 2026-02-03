"""
database.py - Database Management Module
"""

import datetime
import sqlite3
import json
import threading
import time
import hashlib
import warnings
import sys
import os

warnings.filterwarnings('ignore', category=FutureWarning)

import yfinance as yf
import mplfinance as mpf
import pandas as pd
import numpy as np
from scipy.stats import linregress, percentileofscore
import twstock

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.figure import Figure

from io import StringIO
import requests
from bs4 import BeautifulSoup

# ============================================================================
# v4.0 改進：增強版資料庫管理（含籌碼緩存）
# v4.4.7 改進：添加自選股排序功能
# ============================================================================

class WatchlistDatabase:
    """自選股資料庫管理 + 籌碼緩存"""
    
    def __init__(self, db_name="watchlist_v4.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """初始化資料庫（v4.0 新增籌碼緩存表, v4.4.7 新增排序欄位）"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 自選股表格
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                name TEXT,
                market TEXT DEFAULT '台股',
                added_date TEXT,
                notes TEXT,
                recommendation TEXT DEFAULT '待分析',
                sort_order INTEGER DEFAULT 0
            )
        ''')
        
        # v4.4.7: 檢查是否需要添加 sort_order 欄位（升級舊資料庫）
        cursor.execute("PRAGMA table_info(watchlist)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'sort_order' not in columns:
            cursor.execute('ALTER TABLE watchlist ADD COLUMN sort_order INTEGER DEFAULT 0')
            # 初始化排序順序
            cursor.execute('SELECT id FROM watchlist ORDER BY added_date DESC')
            rows = cursor.fetchall()
            for idx, (row_id,) in enumerate(rows):
                cursor.execute('UPDATE watchlist SET sort_order = ? WHERE id = ?', (idx, row_id))
            print("[Database] 已添加 sort_order 欄位並初始化排序")
        
        # 分析歷史表格
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                analysis_date TEXT,
                technical_signal TEXT,
                fundamental_signal TEXT,
                recommendation TEXT,
                analysis_data TEXT,
                FOREIGN KEY (symbol) REFERENCES watchlist(symbol)
            )
        ''')
        
        # v4.0 新增：籌碼面緩存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chip_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                data_date TEXT NOT NULL,
                cache_time TEXT NOT NULL,
                foreign_investor INTEGER,
                investment_trust INTEGER,
                dealer INTEGER,
                raw_data TEXT,
                UNIQUE(symbol, data_date)
            )
        ''')
        
        # v4.0 新增：大盤數據緩存表（用於 Beta 計算和市場環境判斷）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_code TEXT NOT NULL,
                cache_date TEXT NOT NULL,
                price_data TEXT,
                adx_value REAL,
                trend_direction TEXT,
                UNIQUE(index_code, cache_date)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_stock(self, symbol, name="", market="台股", notes=""):
        """新增自選股（v4.4.7 更新：自動設定排序順序）"""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            added_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 取得目前最大的 sort_order
            cursor.execute('SELECT COALESCE(MAX(sort_order), -1) + 1 FROM watchlist')
            next_order = cursor.fetchone()[0]
            
            cursor.execute('''
                INSERT INTO watchlist (symbol, name, market, added_date, notes, recommendation, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, name, market, added_date, notes, "待分析", next_order))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def remove_stock(self, symbol):
        """移除自選股"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM watchlist WHERE symbol = ?', (symbol,))
        cursor.execute('DELETE FROM analysis_history WHERE symbol = ?', (symbol,))
        conn.commit()
        conn.close()
        # 重新整理排序順序
        self._reorder_stocks()
    
    def _reorder_stocks(self):
        """重新整理排序順序（移除後調用）"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM watchlist ORDER BY sort_order ASC')
        rows = cursor.fetchall()
        for idx, (row_id,) in enumerate(rows):
            cursor.execute('UPDATE watchlist SET sort_order = ? WHERE id = ?', (idx, row_id))
        conn.commit()
        conn.close()
    
    def get_all_stocks(self, order_by='sort_order'):
        """
        取得所有自選股
        
        Args:
            order_by: 排序方式
                - 'sort_order': 自訂順序（預設）
                - 'symbol': 按代碼
                - 'name': 按名稱
                - 'added_date': 按加入日期
                - 'recommendation': 按建議
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 安全的排序欄位
        valid_orders = {
            'sort_order': 'sort_order ASC',
            'symbol': 'symbol ASC',
            'name': 'name ASC',
            'added_date': 'added_date DESC',
            'recommendation': 'recommendation ASC'
        }
        order_clause = valid_orders.get(order_by, 'sort_order ASC')
        
        cursor.execute(f'SELECT symbol, name, market, added_date, notes, recommendation FROM watchlist ORDER BY {order_clause}')
        stocks = cursor.fetchall()
        conn.close()
        return stocks
    
    def move_stock_up(self, symbol):
        """將股票上移一位"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 取得當前股票的排序順序
        cursor.execute('SELECT sort_order FROM watchlist WHERE symbol = ?', (symbol,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False
        
        current_order = result[0]
        if current_order == 0:
            # 已經在最上面
            conn.close()
            return False
        
        # 找到上一個股票
        cursor.execute('SELECT symbol FROM watchlist WHERE sort_order = ?', (current_order - 1,))
        prev_result = cursor.fetchone()
        if prev_result:
            prev_symbol = prev_result[0]
            # 交換順序
            cursor.execute('UPDATE watchlist SET sort_order = ? WHERE symbol = ?', (current_order, prev_symbol))
            cursor.execute('UPDATE watchlist SET sort_order = ? WHERE symbol = ?', (current_order - 1, symbol))
            conn.commit()
        
        conn.close()
        return True
    
    def move_stock_down(self, symbol):
        """將股票下移一位"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 取得當前股票的排序順序
        cursor.execute('SELECT sort_order FROM watchlist WHERE symbol = ?', (symbol,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False
        
        current_order = result[0]
        
        # 取得最大排序順序
        cursor.execute('SELECT MAX(sort_order) FROM watchlist')
        max_order = cursor.fetchone()[0]
        
        if current_order >= max_order:
            # 已經在最下面
            conn.close()
            return False
        
        # 找到下一個股票
        cursor.execute('SELECT symbol FROM watchlist WHERE sort_order = ?', (current_order + 1,))
        next_result = cursor.fetchone()
        if next_result:
            next_symbol = next_result[0]
            # 交換順序
            cursor.execute('UPDATE watchlist SET sort_order = ? WHERE symbol = ?', (current_order, next_symbol))
            cursor.execute('UPDATE watchlist SET sort_order = ? WHERE symbol = ?', (current_order + 1, symbol))
            conn.commit()
        
        conn.close()
        return True
    
    def move_stock_to_top(self, symbol):
        """將股票移到最上面"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 取得當前股票的排序順序
        cursor.execute('SELECT sort_order FROM watchlist WHERE symbol = ?', (symbol,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False
        
        current_order = result[0]
        if current_order == 0:
            conn.close()
            return True
        
        # 將所有排序 < current_order 的股票往下移一位
        cursor.execute('UPDATE watchlist SET sort_order = sort_order + 1 WHERE sort_order < ?', (current_order,))
        # 將當前股票移到最上面
        cursor.execute('UPDATE watchlist SET sort_order = 0 WHERE symbol = ?', (symbol,))
        conn.commit()
        conn.close()
        return True
    
    def move_stock_to_bottom(self, symbol):
        """將股票移到最下面"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 取得當前股票的排序順序和最大順序
        cursor.execute('SELECT sort_order FROM watchlist WHERE symbol = ?', (symbol,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False
        
        current_order = result[0]
        
        cursor.execute('SELECT MAX(sort_order) FROM watchlist')
        max_order = cursor.fetchone()[0]
        
        if current_order >= max_order:
            conn.close()
            return True
        
        # 將所有排序 > current_order 的股票往上移一位
        cursor.execute('UPDATE watchlist SET sort_order = sort_order - 1 WHERE sort_order > ?', (current_order,))
        # 將當前股票移到最下面
        cursor.execute('UPDATE watchlist SET sort_order = ? WHERE symbol = ?', (max_order, symbol))
        conn.commit()
        conn.close()
        return True
    
    def get_stock_count(self):
        """取得自選股數量"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM watchlist')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def update_recommendation(self, symbol, recommendation):
        """更新投資建議"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE watchlist SET recommendation = ? WHERE symbol = ?', 
                      (recommendation, symbol))
        conn.commit()
        conn.close()
    
    def save_analysis(self, symbol, tech_signal, fund_signal, recommendation, analysis_data):
        """儲存分析結果"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        analysis_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 安全處理 analysis_data
        if isinstance(analysis_data, dict):
            # 深拷貝並清理不可序列化的數據
            clean_data = {}
            for key, value in analysis_data.items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    clean_data[key] = value
                elif isinstance(value, dict):
                    clean_data[key] = {k: v for k, v in value.items() 
                                       if isinstance(v, (str, int, float, bool, type(None)))}
                else:
                    clean_data[key] = str(value)
            analysis_json = json.dumps(clean_data, ensure_ascii=False, default=str)
        else:
            analysis_json = str(analysis_data)
        
        cursor.execute('''
            INSERT INTO analysis_history 
            (symbol, analysis_date, technical_signal, fundamental_signal, recommendation, analysis_data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (symbol, analysis_date, tech_signal, fund_signal, recommendation, analysis_json))
        conn.commit()
        conn.close()
    
    # ==================== v4.0 新增：籌碼緩存方法 ====================
    
    def get_cached_chip_data(self, symbol, data_date):
        """取得緩存的籌碼數據"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT foreign_investor, investment_trust, dealer, raw_data, cache_time
            FROM chip_cache 
            WHERE symbol = ? AND data_date = ?
        ''', (symbol, data_date))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            cache_time = datetime.datetime.strptime(result[4], "%Y-%m-%d %H:%M:%S")
            # 檢查緩存是否過期
            if (datetime.datetime.now() - cache_time).total_seconds() < QuantConfig.CHIP_CACHE_HOURS * 3600:
                return {
                    'foreign_investor': result[0],
                    'investment_trust': result[1],
                    'dealer': result[2],
                    'raw_data': json.loads(result[3]) if result[3] else None
                }
        return None
    
    def save_chip_cache(self, symbol, data_date, foreign_inv, invest_trust, dealer=0, raw_data=None):
        """儲存籌碼數據到緩存"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cache_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        raw_json = json.dumps(raw_data, ensure_ascii=False) if raw_data else None
        
        cursor.execute('''
            INSERT OR REPLACE INTO chip_cache 
            (symbol, data_date, cache_time, foreign_investor, investment_trust, dealer, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, data_date, cache_time, foreign_inv, invest_trust, dealer, raw_json))
        
        conn.commit()
        conn.close()
    
    def clean_old_cache(self, days=7):
        """清理過期緩存"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        cursor.execute('DELETE FROM chip_cache WHERE data_date < ?', (cutoff_date,))
        cursor.execute('DELETE FROM market_cache WHERE cache_date < ?', (cutoff_date,))
        
        conn.commit()
        conn.close()


# ============================================================================
# v4.0 新增：市場環境分析器
# ============================================================================

