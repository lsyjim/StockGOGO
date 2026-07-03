"""
trend_scanner.py - 近五日熱門題材掃描器 (5-Day Hot Theme Scanner)

================================================================================
版本: v1.0.0
作者: 量化投資分析系統
用途: 掃描市場中近五日表現最強的產業/概念股題材

================================================================================
核心邏輯:
================================================================================

1. 初篩 (Pre-filter)
   - 從 WukongAPI 取得所有產業與概念股
   - 根據當日漲跌家數比排序，選取前 20 名板塊

2. 鑽取 (Drill-down)
   - 針對這 20 個板塊，取得成分股清單

3. 領頭羊選取 (Leader Selection)
   - 在每個板塊中，選取成交量最大的前 5 檔股票作為代表

4. 五日績效計算 (5-Day Performance)
   - 抓取這 5 檔股票的歷史數據
   - 計算 (最新收盤價 - 5天前收盤價) / 5天前收盤價

5. 板塊評分 (Sector Scoring)
   - 將 5 檔股票的漲幅取平均值，作為「5日動能分數」

================================================================================
效能優化:
================================================================================
- 使用 ThreadPoolExecutor 並發抓取歷史數據
- 使用快取減少重複 API 請求
- 初篩機制減少需要分析的板塊數量

================================================================================
使用範例:
================================================================================

```python
from trend_scanner import SectorMomentumScanner

# 創建掃描器
scanner = SectorMomentumScanner()

# 取得熱門題材（預設前 5 名）
hot_themes = scanner.get_top_themes(limit=5)

# 顯示結果
print(hot_themes)

# 取得詳細報告
report = scanner.generate_report()
print(report)
```

================================================================================
"""

import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

# ============================================================================
# 嘗試導入必要模組
# ============================================================================
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("[TrendScanner] 警告：pandas 未安裝，將使用簡易輸出格式")

try:
    from data_fetcher import WukongAPI, DataSourceManager
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    print("[TrendScanner] 警告：data_fetcher 模組未找到，將使用模擬數據")


# ============================================================================
# 數據類別定義
# ============================================================================

@dataclass
class StockPerformance:
    """個股績效數據"""
    symbol: str                          # 股票代碼
    name: str                            # 股票名稱
    current_price: float = 0.0           # 最新收盤價
    price_5d_ago: float = 0.0            # 5天前收盤價
    change_5d_pct: float = 0.0           # 5日漲跌幅 (%)
    volume: int = 0                      # 成交量
    daily_change_pct: float = 0.0        # 當日漲跌幅 (%)
    data_valid: bool = False             # 數據是否有效


@dataclass
class ThemePerformance:
    """題材/板塊績效數據"""
    theme_id: str                        # 板塊 ID
    theme_name: str                      # 板塊名稱
    category: str                        # 類別 (產業/概念股)
    momentum_5d_pct: float = 0.0         # 5日動能分數 (%)
    up_count: int = 0                    # 上漲家數
    down_count: int = 0                  # 下跌家數
    daily_change_pct: float = 0.0        # 當日漲跌幅 (%)
    leader_stocks: List[StockPerformance] = field(default_factory=list)  # 領頭羊股票
    top_stock: Optional[StockPerformance] = None  # 漲幅最大的股票
    scan_time: datetime = field(default_factory=datetime.now)  # 掃描時間


@dataclass
class ScannerConfig:
    """掃描器配置"""
    pre_filter_limit: int = 20           # 初篩板塊數量上限
    leader_count: int = 5                # 每個板塊選取的領頭羊數量
    max_workers: int = 10                # 並發線程數
    history_period: str = '10d'          # 歷史數據期間（多抓幾天以確保有足夠數據）
    calculation_days: int = 5            # 計算績效的天數
    cache_ttl_seconds: int = 300         # 快取有效期（秒）
    timeout_seconds: int = 30            # API 請求超時（秒）
    retry_count: int = 2                 # 重試次數


# ============================================================================
# 主類別: SectorMomentumScanner
# ============================================================================

class SectorMomentumScanner:
    """
    板塊動能掃描器
    
    功能：
    1. 掃描市場中所有產業與概念股
    2. 計算每個板塊的 5 日動能分數
    3. 找出近期最熱門的題材
    
    =====================================================
    使用方式:
    =====================================================
    
    ```python
    # 基本使用
    scanner = SectorMomentumScanner()
    top_themes = scanner.get_top_themes(limit=5)
    
    # 自定義配置
    config = ScannerConfig(
        pre_filter_limit=30,
        leader_count=10,
        max_workers=20
    )
    scanner = SectorMomentumScanner(config)
    top_themes = scanner.get_top_themes()
    ```
    """
    
    def __init__(self, config: ScannerConfig = None):
        """
        初始化掃描器
        
        Args:
            config: 掃描器配置，若為 None 則使用預設值
        """
        self.config = config or ScannerConfig()
        
        # 快取
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._lock = threading.Lock()
        
        # 掃描結果
        self._last_scan_result: List[ThemePerformance] = []
        self._last_scan_time: Optional[datetime] = None
        
        # 統計
        self._stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'errors': 0,
            'total_stocks_analyzed': 0
        }
    
    # ========================================================================
    # 公開方法
    # ========================================================================
    
    def get_top_themes(self, limit: int = 5, force_refresh: bool = False) -> Any:
        """
        取得熱門題材排行
        
        Args:
            limit: 回傳的題材數量
            force_refresh: 是否強制重新掃描（忽略快取）
        
        Returns:
            DataFrame 或 List[Dict]，包含欄位：
            - Rank: 排名
            - Theme_Name: 題材名稱
            - Category: 類別（產業/概念股）
            - 5D_Momentum_%: 5日動能分數
            - Top_Stock: 領漲股票
            - Top_Stock_Chg%: 領漲股票漲幅
        """
        # 檢查快取
        cache_key = 'top_themes'
        if not force_refresh and self._is_cache_valid(cache_key):
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                self._stats['cache_hits'] += 1
                return self._format_output(cached_result[:limit])
        
        # 執行掃描
        print(f"[TrendScanner] 開始掃描熱門題材... ({datetime.now().strftime('%H:%M:%S')})")
        start_time = time.time()
        
        try:
            # Step 1-5: 執行完整掃描流程
            all_themes = self.calculate_sector_momentum()
            
            # 排序（按 5日動能分數 降序）
            all_themes.sort(key=lambda x: x.momentum_5d_pct, reverse=True)
            
            # 更新快取
            self._cache[cache_key] = all_themes
            self._cache_time[cache_key] = datetime.now()
            self._last_scan_result = all_themes
            self._last_scan_time = datetime.now()
            
            elapsed = time.time() - start_time
            print(f"[TrendScanner] 掃描完成！耗時 {elapsed:.1f} 秒，共分析 {len(all_themes)} 個板塊")
            
            return self._format_output(all_themes[:limit])
            
        except Exception as e:
            self._stats['errors'] += 1
            print(f"[TrendScanner] 掃描失敗: {e}")
            traceback.print_exc()
            return self._format_output([])
    
    def calculate_sector_momentum(self) -> List[ThemePerformance]:
        """
        計算所有板塊的動能分數
        
        這是核心計算方法，執行以下步驟：
        1. 初篩：取得並篩選板塊
        2. 鑽取：取得成分股
        3. 領頭羊選取：選出高成交量股票
        4. 績效計算：計算 5 日漲幅
        5. 評分：計算板塊動能分數
        
        Returns:
            List[ThemePerformance]: 所有板塊的績效數據
        """
        all_themes: List[ThemePerformance] = []
        
        # ========================================
        # Step 1: 初篩 - 取得並排序板塊
        # ========================================
        print("[TrendScanner] Step 1: 初篩板塊...")
        
        industries = self._get_industry_list()
        concepts = self._get_concept_list()
        
        # 合併所有板塊
        all_sectors = []
        
        for ind in industries:
            all_sectors.append({
                'id': ind.get('id', ''),
                'name': ind.get('name', ''),
                'category': '產業',
                'up_count': ind.get('up_count', 0),
                'down_count': ind.get('down_count', 0),
                'change_pct': ind.get('change_pct', 0),
                # 計算漲跌家數比作為初篩指標
                'up_ratio': ind.get('up_count', 0) / max(1, ind.get('up_count', 0) + ind.get('down_count', 0))
            })
        
        for con in concepts:
            all_sectors.append({
                'id': con.get('id', ''),
                'name': con.get('name', ''),
                'category': '概念股',
                'up_count': con.get('up_count', 0),
                'down_count': con.get('down_count', 0),
                'change_pct': con.get('change_pct', 0),
                'up_ratio': con.get('up_count', 0) / max(1, con.get('up_count', 0) + con.get('down_count', 0))
            })
        
        # 按漲跌家數比排序，取前 N 名
        all_sectors.sort(key=lambda x: (x['up_ratio'], x['change_pct']), reverse=True)
        top_sectors = all_sectors[:self.config.pre_filter_limit]
        
        print(f"[TrendScanner] 初篩完成：{len(all_sectors)} 個板塊 → 選取前 {len(top_sectors)} 名")
        
        # ========================================
        # Step 2-5: 並發處理每個板塊
        # ========================================
        print("[TrendScanner] Step 2-5: 分析領頭羊績效...")
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_sector = {
                executor.submit(self._analyze_sector, sector): sector
                for sector in top_sectors
            }
            
            completed = 0
            for future in as_completed(future_to_sector):
                sector = future_to_sector[future]
                completed += 1
                
                try:
                    theme_perf = future.result(timeout=self.config.timeout_seconds)
                    if theme_perf is not None:
                        all_themes.append(theme_perf)
                        print(f"[TrendScanner] ({completed}/{len(top_sectors)}) {sector['name']}: 5D動能 {theme_perf.momentum_5d_pct:+.2f}%")
                except Exception as e:
                    print(f"[TrendScanner] 分析 {sector['name']} 失敗: {e}")
                    self._stats['errors'] += 1
        
        return all_themes
    
    def generate_report(self, limit: int = 10) -> str:
        """
        生成詳細的文字報告
        
        Args:
            limit: 報告的題材數量
        
        Returns:
            str: 格式化的報告文字
        """
        top_themes = self.get_top_themes(limit=limit)
        
        if PANDAS_AVAILABLE and isinstance(top_themes, pd.DataFrame):
            themes_list = top_themes.to_dict('records')
        else:
            themes_list = top_themes if isinstance(top_themes, list) else []
        
        report_lines = [
            "=" * 70,
            f"  📊 近五日熱門題材報告",
            f"  生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
            ""
        ]
        
        for i, theme in enumerate(themes_list, 1):
            if isinstance(theme, dict):
                report_lines.extend([
                    f"  #{i} {theme.get('Theme_Name', 'N/A')} [{theme.get('Category', 'N/A')}]",
                    f"      5日動能: {theme.get('5D_Momentum_%', 0):+.2f}%",
                    f"      領漲股: {theme.get('Top_Stock', 'N/A')} ({theme.get('Top_Stock_Chg%', 0):+.2f}%)",
                    ""
                ])
        
        report_lines.extend([
            "=" * 70,
            f"  統計: API 呼叫 {self._stats['api_calls']} 次, "
            f"快取命中 {self._stats['cache_hits']} 次, "
            f"錯誤 {self._stats['errors']} 次",
            "=" * 70
        ])
        
        return "\n".join(report_lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊"""
        return {
            **self._stats,
            'last_scan_time': self._last_scan_time,
            'themes_count': len(self._last_scan_result)
        }
    
    def clear_cache(self):
        """清除快取"""
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        print("[TrendScanner] 快取已清除")
    
    # ========================================================================
    # 私有方法
    # ========================================================================
    
    def _analyze_sector(self, sector: Dict) -> Optional[ThemePerformance]:
        """
        分析單一板塊
        
        執行 Step 2-5：
        2. 鑽取成分股
        3. 選取領頭羊
        4. 計算績效
        5. 評分
        
        Args:
            sector: 板塊資訊
        
        Returns:
            ThemePerformance 或 None
        """
        try:
            sector_id = sector['id']
            sector_name = sector['name']
            category = sector['category']
            
            # ========================================
            # Step 2: 鑽取 - 取得成分股
            # ========================================
            if category == '產業':
                stocks = self._get_industry_stocks(sector_id)
            else:
                stocks = self._get_concept_stocks(sector_id)
            
            if not stocks:
                return None
            
            # ========================================
            # Step 3: 領頭羊選取 - 按成交量排序
            # ========================================
            # 過濾有效數據並按成交量排序
            valid_stocks = [s for s in stocks if isinstance(s, dict) and s.get('volume', 0) > 0]
            valid_stocks.sort(key=lambda x: x.get('volume', 0), reverse=True)
            
            # 選取前 N 檔
            leader_stocks = valid_stocks[:self.config.leader_count]
            
            if not leader_stocks:
                return None
            
            # ========================================
            # Step 4: 五日績效計算
            # ========================================
            stock_performances: List[StockPerformance] = []
            
            for stock in leader_stocks:
                symbol = stock.get('symbol', '')
                name = stock.get('name', '')
                volume = stock.get('volume', 0)
                daily_change = stock.get('change_pct', 0)
                current_price = stock.get('price', 0)
                
                # 取得歷史數據計算 5 日績效
                perf = self._calculate_stock_5d_performance(
                    symbol=symbol,
                    name=name,
                    volume=volume,
                    daily_change_pct=daily_change,
                    current_price=current_price
                )
                
                if perf.data_valid:
                    stock_performances.append(perf)
            
            if not stock_performances:
                return None
            
            # ========================================
            # Step 5: 板塊評分 - 平均 5 日漲幅
            # ========================================
            valid_changes = [sp.change_5d_pct for sp in stock_performances if sp.data_valid]
            
            if not valid_changes:
                return None
            
            momentum_5d = sum(valid_changes) / len(valid_changes)
            
            # 找出漲幅最大的股票
            top_stock = max(stock_performances, key=lambda x: x.change_5d_pct)
            
            # 更新統計
            self._stats['total_stocks_analyzed'] += len(stock_performances)
            
            return ThemePerformance(
                theme_id=sector_id,
                theme_name=sector_name,
                category=category,
                momentum_5d_pct=momentum_5d,
                up_count=sector.get('up_count', 0),
                down_count=sector.get('down_count', 0),
                daily_change_pct=sector.get('change_pct', 0),
                leader_stocks=stock_performances,
                top_stock=top_stock,
                scan_time=datetime.now()
            )
            
        except Exception as e:
            print(f"[TrendScanner] _analyze_sector 錯誤: {e}")
            return None
    
    def _calculate_stock_5d_performance(
        self,
        symbol: str,
        name: str,
        volume: int,
        daily_change_pct: float,
        current_price: float
    ) -> StockPerformance:
        """
        計算個股 5 日績效
        
        Args:
            symbol: 股票代碼
            name: 股票名稱
            volume: 成交量
            daily_change_pct: 當日漲跌幅
            current_price: 當前價格
        
        Returns:
            StockPerformance: 績效數據
        """
        perf = StockPerformance(
            symbol=symbol,
            name=name,
            volume=volume,
            daily_change_pct=daily_change_pct,
            current_price=current_price
        )
        
        try:
            # 取得歷史數據
            hist = self._get_stock_history(symbol)
            
            if hist is None or len(hist) < self.config.calculation_days:
                # 數據不足，使用當日漲幅作為估算
                perf.change_5d_pct = daily_change_pct
                perf.data_valid = True  # 標記為有效（使用估算值）
                return perf
            
            # 計算 5 日績效
            if PANDAS_AVAILABLE and isinstance(hist, pd.DataFrame):
                # 使用 pandas DataFrame
                if 'Close' in hist.columns and len(hist) >= self.config.calculation_days:
                    current = hist['Close'].iloc[-1]
                    past = hist['Close'].iloc[-self.config.calculation_days]
                    
                    if past > 0:
                        perf.current_price = current
                        perf.price_5d_ago = past
                        perf.change_5d_pct = (current - past) / past * 100
                        perf.data_valid = True
            else:
                # 使用 list 格式
                if len(hist) >= self.config.calculation_days:
                    current = hist[-1].get('close', 0) if isinstance(hist[-1], dict) else 0
                    past = hist[-self.config.calculation_days].get('close', 0) if isinstance(hist[-self.config.calculation_days], dict) else 0
                    
                    if past > 0:
                        perf.current_price = current
                        perf.price_5d_ago = past
                        perf.change_5d_pct = (current - past) / past * 100
                        perf.data_valid = True
            
        except Exception as e:
            # 發生錯誤時使用當日漲幅
            perf.change_5d_pct = daily_change_pct
            perf.data_valid = True
        
        return perf
    
    # ========================================================================
    # API 封裝方法（支援快取）
    # ========================================================================
    
    def _get_industry_list(self) -> List[Dict]:
        """取得產業清單（帶快取）"""
        cache_key = 'industry_list'
        
        if self._is_cache_valid(cache_key):
            self._stats['cache_hits'] += 1
            return self._cache.get(cache_key, [])
        
        self._stats['api_calls'] += 1
        
        if API_AVAILABLE:
            try:
                result = WukongAPI.get_industry_list()
                if result:
                    self._cache[cache_key] = result
                    self._cache_time[cache_key] = datetime.now()
                    return result
            except Exception as e:
                print(f"[TrendScanner] 取得產業清單失敗: {e}")
        
        return self._get_mock_industry_list()
    
    def _get_concept_list(self) -> List[Dict]:
        """取得概念股清單（帶快取）"""
        cache_key = 'concept_list'
        
        if self._is_cache_valid(cache_key):
            self._stats['cache_hits'] += 1
            return self._cache.get(cache_key, [])
        
        self._stats['api_calls'] += 1
        
        if API_AVAILABLE:
            try:
                result = WukongAPI.get_concept_list()
                if result:
                    self._cache[cache_key] = result
                    self._cache_time[cache_key] = datetime.now()
                    return result
            except Exception as e:
                print(f"[TrendScanner] 取得概念股清單失敗: {e}")
        
        return self._get_mock_concept_list()
    
    def _get_industry_stocks(self, industry_id: str) -> List[Dict]:
        """取得產業成分股（帶快取）"""
        cache_key = f'industry_stocks_{industry_id}'
        
        if self._is_cache_valid(cache_key):
            self._stats['cache_hits'] += 1
            return self._cache.get(cache_key, [])
        
        self._stats['api_calls'] += 1
        
        if API_AVAILABLE:
            try:
                result = WukongAPI.get_industry_stocks(industry_id, 50)
                if result:
                    self._cache[cache_key] = result
                    self._cache_time[cache_key] = datetime.now()
                    return result
            except Exception as e:
                print(f"[TrendScanner] 取得產業成分股失敗: {e}")
        
        return []
    
    def _get_concept_stocks(self, concept_id: str) -> List[Dict]:
        """取得概念股成分股（帶快取）"""
        cache_key = f'concept_stocks_{concept_id}'
        
        if self._is_cache_valid(cache_key):
            self._stats['cache_hits'] += 1
            return self._cache.get(cache_key, [])
        
        self._stats['api_calls'] += 1
        
        if API_AVAILABLE:
            try:
                result = WukongAPI.get_concept_stocks(concept_id, 50)
                if result:
                    self._cache[cache_key] = result
                    self._cache_time[cache_key] = datetime.now()
                    return result
            except Exception as e:
                print(f"[TrendScanner] 取得概念股成分股失敗: {e}")
        
        return []
    
    def _get_stock_history(self, symbol: str) -> Optional[Any]:
        """取得個股歷史數據（帶快取）"""
        cache_key = f'history_{symbol}'
        
        if self._is_cache_valid(cache_key):
            self._stats['cache_hits'] += 1
            return self._cache.get(cache_key)
        
        self._stats['api_calls'] += 1
        
        if API_AVAILABLE:
            try:
                # 使用 DataSourceManager 取得歷史數據
                result = DataSourceManager.get_history(
                    symbol=symbol,
                    market='TW',
                    period=self.config.history_period
                )
                if result is not None and len(result) > 0:
                    self._cache[cache_key] = result
                    self._cache_time[cache_key] = datetime.now()
                    return result
            except Exception as e:
                # 靜默失敗，返回 None
                pass
        
        return None
    
    # ========================================================================
    # 輔助方法
    # ========================================================================
    
    def _is_cache_valid(self, key: str) -> bool:
        """檢查快取是否有效"""
        if key not in self._cache_time:
            return False
        
        elapsed = (datetime.now() - self._cache_time[key]).total_seconds()
        return elapsed < self.config.cache_ttl_seconds
    
    def _format_output(self, themes: List[ThemePerformance]) -> Any:
        """
        格式化輸出
        
        Args:
            themes: 題材績效列表
        
        Returns:
            DataFrame 或 List[Dict]
        """
        result_list = []
        
        for i, theme in enumerate(themes, 1):
            top_stock_str = "N/A"
            top_stock_chg = 0.0
            
            if theme.top_stock:
                top_stock_str = f"{theme.top_stock.symbol} {theme.top_stock.name}"
                top_stock_chg = theme.top_stock.change_5d_pct
            
            result_list.append({
                'Rank': i,
                'Theme_Name': theme.theme_name,
                'Category': theme.category,
                '5D_Momentum_%': round(theme.momentum_5d_pct, 2),
                'Top_Stock': top_stock_str,
                'Top_Stock_Chg%': round(top_stock_chg, 2),
                'Up_Count': theme.up_count,
                'Down_Count': theme.down_count,
                'Daily_Change_%': round(theme.daily_change_pct, 2)
            })
        
        if PANDAS_AVAILABLE:
            return pd.DataFrame(result_list)
        else:
            return result_list
    
    # ========================================================================
    # 模擬數據（當 API 不可用時使用）
    # ========================================================================
    
    def _get_mock_industry_list(self) -> List[Dict]:
        """模擬產業清單"""
        return [
            {'id': 'ind_01', 'name': '半導體', 'up_count': 25, 'down_count': 5, 'change_pct': 2.5},
            {'id': 'ind_02', 'name': '電子零組件', 'up_count': 20, 'down_count': 10, 'change_pct': 1.8},
            {'id': 'ind_03', 'name': '光電', 'up_count': 15, 'down_count': 8, 'change_pct': 1.2},
            {'id': 'ind_04', 'name': '通信網路', 'up_count': 12, 'down_count': 6, 'change_pct': 0.9},
            {'id': 'ind_05', 'name': '電腦及週邊', 'up_count': 18, 'down_count': 7, 'change_pct': 1.5},
        ]
    
    def _get_mock_concept_list(self) -> List[Dict]:
        """模擬概念股清單"""
        return [
            {'id': 'con_01', 'name': 'AI人工智慧', 'up_count': 30, 'down_count': 3, 'change_pct': 3.5},
            {'id': 'con_02', 'name': '高股息', 'up_count': 22, 'down_count': 8, 'change_pct': 1.2},
            {'id': 'con_03', 'name': '電動車', 'up_count': 18, 'down_count': 5, 'change_pct': 2.0},
            {'id': 'con_04', 'name': '5G', 'up_count': 15, 'down_count': 10, 'change_pct': 0.8},
            {'id': 'con_05', 'name': '雲端運算', 'up_count': 20, 'down_count': 6, 'change_pct': 1.5},
        ]


# ============================================================================
# 便捷函數
# ============================================================================

def scan_hot_themes(limit: int = 5) -> Any:
    """
    快速掃描熱門題材的便捷函數
    
    Args:
        limit: 回傳的題材數量
    
    Returns:
        DataFrame 或 List[Dict]
    
    Example:
        >>> hot_themes = scan_hot_themes(5)
        >>> print(hot_themes)
    """
    scanner = SectorMomentumScanner()
    return scanner.get_top_themes(limit=limit)


def compute_cross_sectional_rs_rank(results):
    """
    build_prompt_04 任務2：橫斷面相對強度百分位（掃描層彙整）。

    對本次掃描全樣本的 60 日報酬（result['technical']['ret_60d'] 或 result['ret_60d']）
    計算 rank(pct=True)*100 → rs_rank_60d（0–100），寫回每檔 result。
    與 fix_02 的 normalized_rs（對大盤）並存：一個是對指數、一個是對同儕排名。

    回傳 {symbol: rs_rank_60d}。ret_60d 缺者 rs_rank_60d=None。
    """
    def _ret(d):
        t = d.get('technical') if isinstance(d.get('technical'), dict) else None
        v = (t or d).get('ret_60d')
        try:
            v = float(v)
            return None if v != v else v
        except (TypeError, ValueError):
            return None

    scored = [(d, _ret(d)) for d in results]
    valid = [(d, v) for d, v in scored if v is not None]

    out = {}
    if not valid:
        for d in results:
            d['rs_rank_60d'] = None
        return out

    n = len(valid)
    if n == 1:
        # 單一樣本無從排名，給中性 50
        valid[0][0]['rs_rank_60d'] = 50.0
        out[valid[0][0].get('symbol')] = 50.0
    else:
        # 百分位排名（average 法，與 pandas rank(pct=True) 等價）：0–100
        vals = sorted(v for _, v in valid)
        import bisect
        for d, v in valid:
            lo = bisect.bisect_left(vals, v)
            hi = bisect.bisect_right(vals, v)
            avg_rank = (lo + hi + 1) / 2.0     # 1-based 平均名次
            rk = round(avg_rank / n * 100, 1)
            d['rs_rank_60d'] = rk
            out[d.get('symbol')] = rk

    for d, v in scored:
        if v is None:
            d['rs_rank_60d'] = None
    return out


def get_sector_report(limit: int = 10) -> str:
    """
    生成板塊報告的便捷函數
    
    Args:
        limit: 報告的題材數量
    
    Returns:
        str: 格式化的報告
    
    Example:
        >>> print(get_sector_report(10))
    """
    scanner = SectorMomentumScanner()
    return scanner.generate_report(limit=limit)


# ============================================================================
# 主程式（測試用）
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("  近五日熱門題材掃描器 - 測試模式")
    print("=" * 70)
    print()
    
    # 創建掃描器
    scanner = SectorMomentumScanner()
    
    # 掃描熱門題材
    print("正在掃描熱門題材...")
    top_themes = scanner.get_top_themes(limit=10)
    
    print()
    print("=" * 70)
    print("  掃描結果")
    print("=" * 70)
    
    if PANDAS_AVAILABLE and isinstance(top_themes, pd.DataFrame):
        print(top_themes.to_string(index=False))
    else:
        for theme in top_themes:
            print(f"  {theme}")
    
    print()
    print("=" * 70)
    print("  統計資訊")
    print("=" * 70)
    stats = scanner.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print()
    print("=" * 70)
    print("  詳細報告")
    print("=" * 70)
    print(scanner.generate_report(limit=5))
