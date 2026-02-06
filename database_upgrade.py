"""
database_upgrade.py - 資料庫 Schema 升級腳本

================================================================================
版本: v4.5.17
用途: 為 watchlist 資料表新增產業分類與標籤欄位

================================================================================
Schema 變更:
================================================================================

新增欄位：
1. industry (TEXT)     - 產業/族群分類
2. tags (TEXT)         - 自定義標籤（JSON 格式）
3. quant_score (REAL)  - 量化評分
4. trend_status (TEXT) - 趨勢狀態 (多頭/空頭/盤整)
5. chip_signal (TEXT)  - 籌碼訊號
6. bias_20 (REAL)      - 20日乖離率
7. last_analyzed (TEXT)- 最後分析時間

================================================================================
使用方式:
================================================================================

```python
from database_upgrade import upgrade_database, WatchlistDatabaseV2

# 執行升級
upgrade_database()

# 使用新版資料庫
db = WatchlistDatabaseV2()
db.add_stock('2330', '台積電', 'TW', industry='半導體')
```

================================================================================
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import traceback

# ============================================================================
# 升級腳本
# ============================================================================

def upgrade_database(db_name: str = 'watchlist.db') -> bool:
    """
    執行資料庫 Schema 升級
    
    Args:
        db_name: 資料庫檔案名稱
    
    Returns:
        bool: 升級是否成功
    """
    print(f"[DatabaseUpgrade] 開始升級資料庫: {db_name}")
    
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # 檢查現有欄位
        cursor.execute("PRAGMA table_info(watchlist)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # 需要新增的欄位
        new_columns = [
            ('industry', 'TEXT DEFAULT ""'),
            ('tags', 'TEXT DEFAULT "[]"'),
            ('quant_score', 'REAL DEFAULT 0'),
            ('trend_status', 'TEXT DEFAULT "待分析"'),
            ('chip_signal', 'TEXT DEFAULT ""'),
            ('bias_20', 'REAL DEFAULT 0'),
            ('last_analyzed', 'TEXT DEFAULT ""'),
        ]
        
        # 新增缺少的欄位
        added_count = 0
        for column_name, column_def in new_columns:
            if column_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE watchlist ADD COLUMN {column_name} {column_def}')
                    print(f"[DatabaseUpgrade] 新增欄位: {column_name}")
                    added_count += 1
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' not in str(e).lower():
                        raise
        
        conn.commit()
        conn.close()
        
        print(f"[DatabaseUpgrade] 升級完成！共新增 {added_count} 個欄位")
        return True
        
    except Exception as e:
        print(f"[DatabaseUpgrade] 升級失敗: {e}")
        traceback.print_exc()
        return False


def check_database_version(db_name: str = 'watchlist.db') -> Dict[str, Any]:
    """
    檢查資料庫版本與欄位
    
    Returns:
        dict: 包含版本資訊與欄位列表
    """
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(watchlist)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # 判斷版本
        has_industry = 'industry' in columns
        has_quant = 'quant_score' in columns
        
        if has_quant:
            version = 'v2.0 (Full)'
        elif has_industry:
            version = 'v1.5 (Partial)'
        else:
            version = 'v1.0 (Original)'
        
        conn.close()
        
        return {
            'version': version,
            'columns': columns,
            'needs_upgrade': not has_quant
        }
        
    except Exception as e:
        return {
            'version': 'Unknown',
            'columns': [],
            'needs_upgrade': True,
            'error': str(e)
        }


# ============================================================================
# WatchlistDatabaseV2 - 升級版資料庫類別
# ============================================================================

class WatchlistDatabaseV2:
    """
    升級版自選股資料庫
    
    新增功能：
    1. 產業自動標註
    2. 量化評分存儲
    3. 籌碼訊號追蹤
    4. 批次更新支援
    5. 分組查詢
    """
    
    def __init__(self, db_name: str = 'watchlist.db'):
        self.db_name = db_name
        self._ensure_schema()
    
    def _ensure_schema(self):
        """確保資料庫結構正確"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # 創建主表（如果不存在）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                market TEXT DEFAULT 'TW',
                added_date TEXT,
                recommendation TEXT DEFAULT '待分析',
                sort_order INTEGER DEFAULT 0,
                industry TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                quant_score REAL DEFAULT 0,
                trend_status TEXT DEFAULT '待分析',
                chip_signal TEXT DEFAULT '',
                bias_20 REAL DEFAULT 0,
                last_analyzed TEXT DEFAULT ''
            )
        ''')
        
        # 確保所有新欄位存在
        upgrade_database(self.db_name)
        
        conn.commit()
        conn.close()
    
    # ========================================================================
    # 基本 CRUD 操作
    # ========================================================================
    
    def add_stock(
        self, 
        symbol: str, 
        name: str, 
        market: str = 'TW',
        industry: str = '',
        tags: List[str] = None
    ) -> bool:
        """
        新增股票到自選股
        
        Args:
            symbol: 股票代碼
            name: 股票名稱
            market: 市場 ('TW' 或 'US')
            industry: 產業分類（可選，若未提供會自動查詢）
            tags: 標籤列表
        
        Returns:
            bool: 是否成功
        """
        try:
            # 自動取得產業資訊
            if not industry:
                industry = self._fetch_industry(symbol)
            
            # 標籤轉 JSON
            tags_json = json.dumps(tags or [], ensure_ascii=False)
            
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # 取得目前最大排序值
                cursor.execute('SELECT MAX(sort_order) FROM watchlist')
                max_order = cursor.fetchone()[0] or 0
                
                cursor.execute('''
                    INSERT INTO watchlist 
                    (symbol, name, market, added_date, sort_order, industry, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol, 
                    name, 
                    market, 
                    datetime.now().strftime('%Y-%m-%d'),
                    max_order + 1,
                    industry,
                    tags_json
                ))
                conn.commit()
            
            print(f"[WatchlistDB] 已新增: {symbol} {name} ({industry})")
            return True
            
        except sqlite3.IntegrityError:
            print(f"[WatchlistDB] 股票已存在: {symbol}")
            return False
        except Exception as e:
            print(f"[WatchlistDB] 新增失敗: {e}")
            return False
    
    def update_quant_data(
        self,
        symbol: str,
        quant_score: float = None,
        trend_status: str = None,
        chip_signal: str = None,
        bias_20: float = None,
        recommendation: str = None
    ) -> bool:
        """
        更新量化數據
        
        Args:
            symbol: 股票代碼
            quant_score: 量化評分
            trend_status: 趨勢狀態
            chip_signal: 籌碼訊號
            bias_20: 20日乖離率
            recommendation: 建議
        
        Returns:
            bool: 是否成功
        """
        try:
            updates = []
            values = []
            
            if quant_score is not None:
                updates.append('quant_score = ?')
                values.append(quant_score)
            
            if trend_status is not None:
                updates.append('trend_status = ?')
                values.append(trend_status)
            
            if chip_signal is not None:
                updates.append('chip_signal = ?')
                values.append(chip_signal)
            
            if bias_20 is not None:
                updates.append('bias_20 = ?')
                values.append(bias_20)
            
            if recommendation is not None:
                updates.append('recommendation = ?')
                values.append(recommendation)
            
            # 更新分析時間
            updates.append('last_analyzed = ?')
            values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            values.append(symbol)
            
            if updates:
                with sqlite3.connect(self.db_name) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        f'UPDATE watchlist SET {", ".join(updates)} WHERE symbol = ?',
                        values
                    )
                    conn.commit()
                return True
            
            return False
            
        except Exception as e:
            print(f"[WatchlistDB] 更新量化數據失敗: {e}")
            return False
    
    def update_batch_quant_data(self, updates: List[Dict]) -> int:
        """
        批次更新量化數據
        
        Args:
            updates: 更新列表，每個元素包含 symbol 和要更新的欄位
                    例如: [{'symbol': '2330', 'quant_score': 85, 'trend_status': '多頭'}, ...]
        
        Returns:
            int: 成功更新的數量
        """
        success_count = 0
        
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                for update in updates:
                    symbol = update.get('symbol')
                    if not symbol:
                        continue
                    
                    set_clauses = []
                    values = []
                    
                    for key, value in update.items():
                        if key != 'symbol' and value is not None:
                            set_clauses.append(f'{key} = ?')
                            values.append(value)
                    
                    if set_clauses:
                        set_clauses.append('last_analyzed = ?')
                        values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        values.append(symbol)
                        
                        cursor.execute(
                            f'UPDATE watchlist SET {", ".join(set_clauses)} WHERE symbol = ?',
                            values
                        )
                        success_count += 1
                
                conn.commit()
            
            print(f"[WatchlistDB] 批次更新完成: {success_count}/{len(updates)}")
            
        except Exception as e:
            print(f"[WatchlistDB] 批次更新失敗: {e}")
        
        return success_count
    
    def get_all_stocks(self, order_by: str = 'sort_order') -> List[Dict]:
        """
        取得所有自選股
        
        Args:
            order_by: 排序欄位
        
        Returns:
            List[Dict]: 股票列表
        """
        try:
            with sqlite3.connect(self.db_name) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(f'SELECT * FROM watchlist ORDER BY {order_by}')
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            print(f"[WatchlistDB] 查詢失敗: {e}")
            return []
    
    def get_stocks_grouped_by_industry(self) -> Dict[str, List[Dict]]:
        """
        按產業分組取得股票
        
        Returns:
            Dict[str, List[Dict]]: {產業名稱: [股票列表]}
        """
        stocks = self.get_all_stocks()
        
        grouped = {}
        for stock in stocks:
            industry = stock.get('industry', '未分類') or '未分類'
            if industry not in grouped:
                grouped[industry] = []
            grouped[industry].append(stock)
        
        return grouped
    
    def get_industry_summary(self) -> List[Dict]:
        """
        取得產業彙總資訊
        
        Returns:
            List[Dict]: [{industry, count, avg_score, up_count, down_count}, ...]
        """
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        COALESCE(industry, '未分類') as industry,
                        COUNT(*) as count,
                        AVG(quant_score) as avg_score,
                        SUM(CASE WHEN bias_20 > 0 THEN 1 ELSE 0 END) as up_count,
                        SUM(CASE WHEN bias_20 < 0 THEN 1 ELSE 0 END) as down_count
                    FROM watchlist
                    GROUP BY industry
                    ORDER BY avg_score DESC
                ''')
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'industry': row[0],
                        'count': row[1],
                        'avg_score': row[2] or 0,
                        'up_count': row[3],
                        'down_count': row[4]
                    })
                
                return results
                
        except Exception as e:
            print(f"[WatchlistDB] 產業彙總查詢失敗: {e}")
            return []
    
    def update_industry(self, symbol: str, industry: str) -> bool:
        """
        更新股票的產業分類
        """
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE watchlist SET industry = ? WHERE symbol = ?',
                    (industry, symbol)
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"[WatchlistDB] 更新產業失敗: {e}")
            return False
    
    def add_tag(self, symbol: str, tag: str) -> bool:
        """
        為股票新增標籤
        """
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT tags FROM watchlist WHERE symbol = ?', (symbol,))
                row = cursor.fetchone()
                
                if row:
                    tags = json.loads(row[0] or '[]')
                    if tag not in tags:
                        tags.append(tag)
                        cursor.execute(
                            'UPDATE watchlist SET tags = ? WHERE symbol = ?',
                            (json.dumps(tags, ensure_ascii=False), symbol)
                        )
                        conn.commit()
                return True
        except Exception as e:
            print(f"[WatchlistDB] 新增標籤失敗: {e}")
            return False
    
    def remove_tag(self, symbol: str, tag: str) -> bool:
        """
        移除股票標籤
        """
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT tags FROM watchlist WHERE symbol = ?', (symbol,))
                row = cursor.fetchone()
                
                if row:
                    tags = json.loads(row[0] or '[]')
                    if tag in tags:
                        tags.remove(tag)
                        cursor.execute(
                            'UPDATE watchlist SET tags = ? WHERE symbol = ?',
                            (json.dumps(tags, ensure_ascii=False), symbol)
                        )
                        conn.commit()
                return True
        except Exception as e:
            print(f"[WatchlistDB] 移除標籤失敗: {e}")
            return False
    
    def get_stocks_by_tag(self, tag: str) -> List[Dict]:
        """
        按標籤查詢股票
        """
        all_stocks = self.get_all_stocks()
        return [
            s for s in all_stocks 
            if tag in json.loads(s.get('tags', '[]'))
        ]
    
    # ========================================================================
    # 自動標註
    # ========================================================================
    
    def _fetch_industry(self, symbol: str) -> str:
        """
        自動取得股票的產業資訊
        
        優先順序：
        1. WukongAPI.get_stock_info
        2. twstock 模組
        3. 預設為空
        """
        industry = ''
        
        # 嘗試使用 WukongAPI
        try:
            from data_fetcher import WukongAPI
            
            # 嘗試從產業列表中找
            industries = WukongAPI.get_industry_list() or []
            for ind in industries:
                stocks = WukongAPI.get_industry_stocks(ind.get('id', ''), 100) or []
                for s in stocks:
                    if s.get('symbol') == symbol:
                        industry = ind.get('name', '')
                        break
                if industry:
                    break
                    
        except Exception:
            pass
        
        # 嘗試使用 twstock
        if not industry:
            try:
                import twstock
                if symbol in twstock.codes:
                    industry = twstock.codes[symbol].group or ''
            except Exception:
                pass
        
        return industry
    
    def auto_tag_all_stocks(self) -> int:
        """
        自動為所有股票標註產業
        
        Returns:
            int: 成功標註的數量
        """
        stocks = self.get_all_stocks()
        tagged_count = 0
        
        for stock in stocks:
            if not stock.get('industry'):
                industry = self._fetch_industry(stock['symbol'])
                if industry:
                    self.update_industry(stock['symbol'], industry)
                    tagged_count += 1
        
        print(f"[WatchlistDB] 自動標註完成: {tagged_count} 檔")
        return tagged_count
    
    # ========================================================================
    # 相容性方法（保持與舊版 API 相容）
    # ========================================================================
    
    def remove_stock(self, symbol: str) -> bool:
        """移除股票"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM watchlist WHERE symbol = ?', (symbol,))
                conn.commit()
            return True
        except Exception as e:
            print(f"[WatchlistDB] 移除失敗: {e}")
            return False
    
    def get_stock_count(self) -> int:
        """取得股票數量"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM watchlist')
                return cursor.fetchone()[0]
        except:
            return 0
    
    def update_recommendation(self, symbol: str, recommendation: str) -> bool:
        """更新建議（相容舊版 API）"""
        return self.update_quant_data(symbol, recommendation=recommendation)


# ============================================================================
# 主程式（測試用）
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  資料庫升級工具")
    print("=" * 60)
    
    # 檢查版本
    print("\n檢查資料庫版本...")
    version_info = check_database_version()
    print(f"  版本: {version_info['version']}")
    print(f"  欄位: {version_info['columns']}")
    print(f"  需要升級: {version_info['needs_upgrade']}")
    
    # 執行升級
    if version_info['needs_upgrade']:
        print("\n執行升級...")
        success = upgrade_database()
        print(f"  升級結果: {'成功' if success else '失敗'}")
    
    # 測試新功能
    print("\n測試新功能...")
    db = WatchlistDatabaseV2()
    
    # 取得分組資料
    grouped = db.get_stocks_grouped_by_industry()
    print(f"  產業分組數: {len(grouped)}")
    
    for industry, stocks in list(grouped.items())[:3]:
        print(f"    {industry}: {len(stocks)} 檔")
    
    # 取得產業彙總
    summary = db.get_industry_summary()
    print(f"\n  產業彙總:")
    for s in summary[:3]:
        print(f"    {s['industry']}: {s['count']}檔, 平均分數 {s['avg_score']:.1f}")
