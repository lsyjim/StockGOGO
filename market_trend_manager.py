"""
market_trend_manager.py - 市場熱點管理器 (Market Trend Manager)

================================================================================
版本: v1.0.0
用途: 封裝 trend_scanner.py，提供市場廣度分析的統一接口

================================================================================
設計理念 (Goldman Sachs Top-Down Approach):
================================================================================

1. 由上而下選股 (Top-Down Stock Selection)
   - 先找強勢族群 → 再從中挑選領頭羊
   - 順勢而為，不逆市場操作

2. 市場廣度 (Market Breadth)
   - 監控整體市場健康度
   - 識別資金流向

3. 動能延續 (Momentum Continuation)
   - 強者恆強，追蹤近期表現最佳的題材
   - 5日動能分數作為核心指標

================================================================================
"""

import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
import traceback

# ============================================================================
# 嘗試導入依賴模組
# ============================================================================
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from trend_scanner import SectorMomentumScanner, ScannerConfig, ThemePerformance
    SCANNER_AVAILABLE = True
except ImportError:
    SCANNER_AVAILABLE = False
    print("[MarketTrendManager] 警告：trend_scanner 模組未找到")

try:
    from data_fetcher import WukongAPI, DataSourceManager
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False


# ============================================================================
# 數據類別
# ============================================================================

@dataclass
class SectorInfo:
    """板塊資訊"""
    sector_id: str
    sector_name: str
    category: str  # '產業' 或 '概念股'
    momentum_5d: float = 0.0
    daily_change: float = 0.0
    up_count: int = 0
    down_count: int = 0
    leader_symbol: str = ''
    leader_name: str = ''
    leader_change: float = 0.0


@dataclass 
class StockInfo:
    """個股資訊"""
    symbol: str
    name: str
    price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    momentum_5d: float = 0.0


# ============================================================================
# MarketTrendManager 類別
# ============================================================================

class MarketTrendManager:
    """
    市場熱點管理器
    
    功能：
    1. 取得當日強勢族群 (get_hot_sectors)
    2. 取得族群成分股 (get_sector_constituents)
    3. 快取管理與自動更新
    
    =====================================================
    使用範例:
    =====================================================
    
    ```python
    manager = MarketTrendManager()
    
    # 取得熱門族群
    hot_sectors = manager.get_hot_sectors(limit=10)
    
    # 取得成分股
    stocks = manager.get_sector_constituents(sector_id='ind_01')
    
    # 註冊更新回調
    manager.register_update_callback(my_callback)
    manager.start_auto_refresh(interval=300)
    ```
    """
    
    # 單例模式
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 初始化掃描器
        if SCANNER_AVAILABLE:
            config = ScannerConfig(
                pre_filter_limit=20,
                leader_count=5,
                max_workers=10,
                cache_ttl_seconds=300
            )
            self._scanner = SectorMomentumScanner(config)
        else:
            self._scanner = None
        
        # 快取
        self._sectors_cache: List[SectorInfo] = []
        self._constituents_cache: Dict[str, List[StockInfo]] = {}
        self._last_update: Optional[datetime] = None
        
        # 回調函數
        self._update_callbacks: List[Callable] = []
        
        # 自動更新
        self._auto_refresh_thread: Optional[threading.Thread] = None
        self._auto_refresh_running = False
        self._refresh_interval = 300  # 預設 5 分鐘
        
        # 統計
        self._stats = {
            'refresh_count': 0,
            'api_calls': 0,
            'errors': 0
        }
    
    # ========================================================================
    # 公開方法
    # ========================================================================
    
    def get_hot_sectors(self, limit: int = 10, force_refresh: bool = False) -> List[SectorInfo]:
        """
        取得當日強勢族群
        
        Args:
            limit: 回傳的族群數量
            force_refresh: 是否強制重新整理
        
        Returns:
            List[SectorInfo]: 強勢族群列表，按 5日動能 降序排列
        """
        # 檢查是否需要更新
        if force_refresh or self._should_refresh():
            self._refresh_sectors()
        
        return self._sectors_cache[:limit]
    
    def get_sector_constituents(self, sector_id: str, limit: int = 20) -> List[StockInfo]:
        """
        取得族群成分股
        
        Args:
            sector_id: 族群 ID
            limit: 回傳的股票數量
        
        Returns:
            List[StockInfo]: 成分股列表，按成交量降序排列
        """
        # 檢查快取
        if sector_id in self._constituents_cache:
            return self._constituents_cache[sector_id][:limit]
        
        # 從 API 取得
        stocks = self._fetch_constituents(sector_id)
        
        if stocks:
            self._constituents_cache[sector_id] = stocks
        
        return stocks[:limit]
    
    def get_sector_by_id(self, sector_id: str) -> Optional[SectorInfo]:
        """
        根據 ID 取得族群資訊
        """
        for sector in self._sectors_cache:
            if sector.sector_id == sector_id:
                return sector
        return None
    
    def register_update_callback(self, callback: Callable):
        """
        註冊更新回調函數
        
        當數據更新時會呼叫所有已註冊的回調
        """
        if callback not in self._update_callbacks:
            self._update_callbacks.append(callback)
    
    def unregister_update_callback(self, callback: Callable):
        """
        取消註冊回調函數
        """
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)
    
    def start_auto_refresh(self, interval: int = 300):
        """
        啟動自動更新
        
        Args:
            interval: 更新間隔（秒）
        """
        if self._auto_refresh_running:
            return
        
        self._refresh_interval = interval
        self._auto_refresh_running = True
        
        def refresh_loop():
            while self._auto_refresh_running:
                try:
                    self._refresh_sectors()
                    self._notify_callbacks()
                except Exception as e:
                    print(f"[MarketTrendManager] 自動更新錯誤: {e}")
                    self._stats['errors'] += 1
                
                # 等待下次更新
                time.sleep(self._refresh_interval)
        
        self._auto_refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self._auto_refresh_thread.start()
        print(f"[MarketTrendManager] 自動更新已啟動（間隔 {interval} 秒）")
    
    def stop_auto_refresh(self):
        """
        停止自動更新
        """
        self._auto_refresh_running = False
        print("[MarketTrendManager] 自動更新已停止")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        取得統計資訊
        """
        return {
            **self._stats,
            'last_update': self._last_update,
            'sectors_count': len(self._sectors_cache),
            'cached_constituents': len(self._constituents_cache)
        }
    
    def clear_cache(self):
        """
        清除所有快取
        """
        self._sectors_cache.clear()
        self._constituents_cache.clear()
        self._last_update = None
        print("[MarketTrendManager] 快取已清除")
    
    # ========================================================================
    # 私有方法
    # ========================================================================
    
    def _should_refresh(self) -> bool:
        """
        檢查是否應該重新整理
        """
        if self._last_update is None:
            return True
        
        elapsed = (datetime.now() - self._last_update).total_seconds()
        return elapsed >= self._refresh_interval
    
    def _refresh_sectors(self):
        """
        重新整理族群數據
        """
        print(f"[MarketTrendManager] 重新整理族群數據... ({datetime.now().strftime('%H:%M:%S')})")
        
        try:
            if self._scanner:
                # 使用 TrendScanner 取得數據
                themes = self._scanner.get_top_themes(limit=20, force_refresh=True)
                
                # 轉換格式
                self._sectors_cache = self._convert_themes_to_sectors(themes)
            else:
                # 直接使用 WukongAPI
                self._sectors_cache = self._fetch_sectors_from_api()
            
            self._last_update = datetime.now()
            self._stats['refresh_count'] += 1
            
            print(f"[MarketTrendManager] 已載入 {len(self._sectors_cache)} 個族群")
            
        except Exception as e:
            print(f"[MarketTrendManager] 重新整理失敗: {e}")
            traceback.print_exc()
            self._stats['errors'] += 1
    
    def _convert_themes_to_sectors(self, themes: Any) -> List[SectorInfo]:
        """
        將 TrendScanner 的輸出轉換為 SectorInfo 列表
        """
        sectors = []
        
        if PANDAS_AVAILABLE and hasattr(themes, 'iterrows'):
            # DataFrame 格式
            for _, row in themes.iterrows():
                sector = SectorInfo(
                    sector_id=str(row.get('Rank', '')),
                    sector_name=row.get('Theme_Name', ''),
                    category=row.get('Category', ''),
                    momentum_5d=row.get('5D_Momentum_%', 0),
                    daily_change=row.get('Daily_Change_%', 0),
                    up_count=row.get('Up_Count', 0),
                    down_count=row.get('Down_Count', 0),
                    leader_symbol=row.get('Top_Stock', '').split()[0] if row.get('Top_Stock') else '',
                    leader_name=' '.join(row.get('Top_Stock', '').split()[1:]) if row.get('Top_Stock') else '',
                    leader_change=row.get('Top_Stock_Chg%', 0)
                )
                sectors.append(sector)
        elif isinstance(themes, list):
            # List 格式
            for item in themes:
                if isinstance(item, dict):
                    top_stock = item.get('Top_Stock', '')
                    sector = SectorInfo(
                        sector_id=str(item.get('Rank', '')),
                        sector_name=item.get('Theme_Name', ''),
                        category=item.get('Category', ''),
                        momentum_5d=item.get('5D_Momentum_%', 0),
                        daily_change=item.get('Daily_Change_%', 0),
                        up_count=item.get('Up_Count', 0),
                        down_count=item.get('Down_Count', 0),
                        leader_symbol=top_stock.split()[0] if top_stock else '',
                        leader_name=' '.join(top_stock.split()[1:]) if top_stock else '',
                        leader_change=item.get('Top_Stock_Chg%', 0)
                    )
                    sectors.append(sector)
        
        return sectors
    
    def _fetch_sectors_from_api(self) -> List[SectorInfo]:
        """
        直接從 WukongAPI 取得族群數據
        """
        sectors = []
        
        if not API_AVAILABLE:
            return self._get_mock_sectors()
        
        try:
            # 取得產業
            industries = WukongAPI.get_industry_list() or []
            for ind in industries:
                if isinstance(ind, dict):
                    sectors.append(SectorInfo(
                        sector_id=ind.get('id', ''),
                        sector_name=ind.get('name', ''),
                        category='產業',
                        daily_change=ind.get('change_pct', 0),
                        up_count=ind.get('up_count', 0),
                        down_count=ind.get('down_count', 0)
                    ))
            
            # 取得概念股
            concepts = WukongAPI.get_concept_list() or []
            for con in concepts:
                if isinstance(con, dict):
                    sectors.append(SectorInfo(
                        sector_id=con.get('id', ''),
                        sector_name=con.get('name', ''),
                        category='概念股',
                        daily_change=con.get('change_pct', 0),
                        up_count=con.get('up_count', 0),
                        down_count=con.get('down_count', 0)
                    ))
            
            # 按漲跌幅排序
            sectors.sort(key=lambda x: x.daily_change, reverse=True)
            
            self._stats['api_calls'] += 1
            
        except Exception as e:
            print(f"[MarketTrendManager] API 呼叫失敗: {e}")
            self._stats['errors'] += 1
        
        return sectors
    
    def _fetch_constituents(self, sector_id: str) -> List[StockInfo]:
        """
        從 API 取得成分股
        """
        stocks = []
        
        if not API_AVAILABLE:
            return self._get_mock_stocks()
        
        try:
            # 根據 sector_id 判斷是產業還是概念股
            sector = self.get_sector_by_id(sector_id)
            
            if sector and sector.category == '產業':
                raw_stocks = WukongAPI.get_industry_stocks(sector_id, 50)
            else:
                raw_stocks = WukongAPI.get_concept_stocks(sector_id, 50)
            
            if raw_stocks:
                for s in raw_stocks:
                    if isinstance(s, dict):
                        stocks.append(StockInfo(
                            symbol=s.get('symbol', ''),
                            name=s.get('name', ''),
                            price=s.get('price', 0),
                            change=s.get('change', 0),
                            change_pct=s.get('change_pct', 0),
                            volume=s.get('volume', 0)
                        ))
            
            # 按成交量排序
            stocks.sort(key=lambda x: x.volume, reverse=True)
            
            self._stats['api_calls'] += 1
            
        except Exception as e:
            print(f"[MarketTrendManager] 取得成分股失敗: {e}")
            self._stats['errors'] += 1
        
        return stocks
    
    def _notify_callbacks(self):
        """
        通知所有回調函數
        """
        for callback in self._update_callbacks:
            try:
                callback(self._sectors_cache)
            except Exception as e:
                print(f"[MarketTrendManager] 回調執行失敗: {e}")
    
    def _get_mock_sectors(self) -> List[SectorInfo]:
        """
        模擬數據（用於測試）
        """
        return [
            SectorInfo('1', 'AI人工智慧', '概念股', 12.5, 3.2, 25, 3, '2330', '台積電', 5.8),
            SectorInfo('2', '半導體', '產業', 8.3, 2.1, 20, 5, '2454', '聯發科', 4.2),
            SectorInfo('3', '電動車', '概念股', 6.7, 1.8, 18, 7, '2317', '鴻海', 3.1),
            SectorInfo('4', '5G通訊', '概念股', 5.2, 1.5, 15, 8, '2412', '中華電', 2.5),
            SectorInfo('5', '雲端運算', '概念股', 4.8, 1.2, 12, 6, '3008', '大立光', 2.0),
        ]
    
    def _get_mock_stocks(self) -> List[StockInfo]:
        """
        模擬成分股數據
        """
        return [
            StockInfo('2330', '台積電', 580.0, 15.0, 2.65, 25000000),
            StockInfo('2454', '聯發科', 850.0, 25.0, 3.03, 8000000),
            StockInfo('2379', '瑞昱', 420.0, 10.0, 2.44, 3000000),
            StockInfo('3034', '聯詠', 380.0, 8.0, 2.15, 2500000),
            StockInfo('2408', '南亞科', 75.0, 2.0, 2.74, 15000000),
        ]


# ============================================================================
# 便捷函數
# ============================================================================

def get_market_trend_manager() -> MarketTrendManager:
    """
    取得 MarketTrendManager 單例實例
    """
    return MarketTrendManager()


def get_hot_sectors(limit: int = 10) -> List[SectorInfo]:
    """
    快速取得熱門族群
    """
    return get_market_trend_manager().get_hot_sectors(limit)


def get_sector_stocks(sector_id: str, limit: int = 20) -> List[StockInfo]:
    """
    快速取得族群成分股
    """
    return get_market_trend_manager().get_sector_constituents(sector_id, limit)


# ============================================================================
# 測試
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  MarketTrendManager 測試")
    print("=" * 60)
    
    manager = MarketTrendManager()
    
    # 取得熱門族群
    print("\n取得熱門族群...")
    sectors = manager.get_hot_sectors(limit=5)
    
    for sector in sectors:
        print(f"  {sector.sector_name} [{sector.category}]: 5D動能 {sector.momentum_5d:+.1f}%")
    
    # 取得成分股
    if sectors:
        print(f"\n取得 {sectors[0].sector_name} 成分股...")
        stocks = manager.get_sector_constituents(sectors[0].sector_id, limit=5)
        
        for stock in stocks:
            print(f"  {stock.symbol} {stock.name}: ${stock.price:.2f} ({stock.change_pct:+.2f}%)")
    
    print("\n" + "=" * 60)
    print("  統計資訊")
    print("=" * 60)
    for key, value in manager.get_stats().items():
        print(f"  {key}: {value}")
