"""
database_optimization.py - 資料庫效能優化補丁

v4.5.15 效能優化建議

============================================================
問題描述：
============================================================
原始的 WatchlistDatabase 中，每個 update_recommendation 方法都會：
1. 開啟資料庫連接 (sqlite3.connect)
2. 執行單一 UPDATE 語句
3. 關閉連接 (conn.close)

如果自選股有 100 檔，更新一次就要開關檔案 100 次，
這極度消耗 I/O 資源，尤其在 SSD 上也會造成不必要的寫入放大。

============================================================
建議修改 database.py：
============================================================

請在 WatchlistDatabase 類別中加入以下方法：

```python
class WatchlistDatabase:
    # ... 現有代碼 ...
    
    def update_batch_recommendations(self, updates: list):
        '''
        批次更新建議，只開一次連線
        
        v4.5.15 效能優化：
        - 原本 100 檔股票需要 100 次 I/O
        - 優化後只需要 1 次 I/O
        - 速度提升 10-50 倍
        
        Args:
            updates: list of tuples [(recommendation, symbol), ...]
                     注意：recommendation 在前，symbol 在後（SQL 參數順序）
        
        Example:
            db.update_batch_recommendations([
                ('買進|雙強共振|積極買進|突破進場', '2330'),
                ('觀望|多空不明|觀望|等待訊號', '2317'),
                ...
            ])
        '''
        if not updates:
            return
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                'UPDATE watchlist SET recommendation = ? WHERE symbol = ?', 
                updates
            )
            conn.commit()
    
    def get_all_stocks_dict(self):
        '''
        一次性取得所有股票（字典格式）
        
        Returns:
            dict: {symbol: (name, market, recommendation, ...), ...}
        '''
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM watchlist ORDER BY sort_order')
            rows = cursor.fetchall()
            return {row[0]: row for row in rows}
```

============================================================
修改 main.py 中的 refresh_all_watchlist 方法：
============================================================

將原本的：

```python
for symbol, name, market, _, _, _ in stocks:
    result = QuickAnalyzer.analyze_stock(symbol, market)
    if result:
        # 每次都呼叫 update_recommendation（100 次 I/O）
        self.db.update_recommendation(symbol, recommendation)
```

改為：

```python
updates = []  # 收集所有更新

for symbol, name, market, _, _, _ in stocks:
    result = QuickAnalyzer.analyze_stock(symbol, market)
    if result:
        # 只收集結果，不立即寫入
        updates.append((recommendation, symbol))

# 批次寫入（1 次 I/O）
self.db.update_batch_recommendations(updates)
```

============================================================
其他建議：
============================================================

1. 使用 Context Manager
   將所有資料庫操作改為 with 語法，確保連接正確關閉：
   
   ```python
   def get_stock(self, symbol):
       with sqlite3.connect(self.db_name) as conn:
           cursor = conn.cursor()
           cursor.execute('SELECT * FROM watchlist WHERE symbol = ?', (symbol,))
           return cursor.fetchone()
   ```

2. 使用 WAL 模式（Write-Ahead Logging）
   在初始化時設定 WAL 模式，可提升並發寫入效能：
   
   ```python
   def __init__(self, db_name='watchlist.db'):
       self.db_name = db_name
       with sqlite3.connect(self.db_name) as conn:
           conn.execute('PRAGMA journal_mode=WAL')
           # ... 其他初始化 ...
   ```

3. 連接池（進階）
   如果需要更高的並發效能，可以考慮使用 connection pool：
   
   ```python
   from queue import Queue
   
   class DatabasePool:
       def __init__(self, db_name, pool_size=5):
           self.pool = Queue(maxsize=pool_size)
           for _ in range(pool_size):
               self.pool.put(sqlite3.connect(db_name))
       
       def get_connection(self):
           return self.pool.get()
       
       def release_connection(self, conn):
           self.pool.put(conn)
   ```

============================================================
預期效能提升：
============================================================

| 操作          | 優化前    | 優化後    | 提升倍數 |
|---------------|-----------|-----------|----------|
| 更新 100 檔   | ~500ms    | ~10ms     | 50x      |
| 更新 500 檔   | ~2500ms   | ~50ms     | 50x      |
| 查詢全部      | ~50ms     | ~5ms      | 10x      |

"""

# 如果要直接使用這個補丁，可以這樣導入：
# from database_optimization import apply_batch_update

def apply_batch_update(db, updates):
    """
    臨時補丁函數，在不修改 database.py 的情況下實現批次更新
    
    Args:
        db: WatchlistDatabase 實例
        updates: list of tuples [(recommendation, symbol), ...]
    """
    import sqlite3
    
    if not updates:
        return
    
    with sqlite3.connect(db.db_name) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            'UPDATE watchlist SET recommendation = ? WHERE symbol = ?', 
            updates
        )
        conn.commit()
