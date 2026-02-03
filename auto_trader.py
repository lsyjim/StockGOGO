"""
auto_trader.py - 自動交易主程式 v1.0

功能：
1. 雙模式架構：模擬 (SIMULATION) / 實單 (LIVE)
2. 整合量化分析核心 (QuickAnalyzer)
3. 資金與庫存控管
4. 交易決策邏輯（含否決權機制）
5. 即時損益監控

作者：Stock Analysis System
日期：2026-01-19
"""

import json
import os
import datetime
import time
from typing import Dict, List, Optional, Tuple

# 本地模組
from config import QuantConfig
from database import WatchlistDatabase
from main import QuickAnalyzer
from data_fetcher import RealtimePriceFetcher

# 嘗試導入富邦交易模組
try:
    from fubon_trading import FubonTrader
    FUBON_AVAILABLE = True
except ImportError:
    FUBON_AVAILABLE = False
    print("[AutoTrader] 警告：無法導入 FubonTrader，僅支援模擬模式")


# ============================================================================
# 自動交易設定
# ============================================================================

class AutoTraderConfig:
    """自動交易專用設定"""
    
    # 模式設定
    MODE_SIMULATION = 'SIMULATION'  # 模擬模式
    MODE_LIVE = 'LIVE'              # 實單模式
    
    # 資金設定
    DEFAULT_INITIAL_CAPITAL = 1_000_000     # 預設初始資金（100萬）
    MAX_INVESTMENT_BUDGET = 500_000          # 最大可用預算（50萬）
    MAX_SINGLE_POSITION_PCT = 0.20           # 單一部位最大佔比（20%）
    
    # 交易設定
    MIN_ORDER_AMOUNT = 1000                  # 最小下單股數（1張）
    COMMISSION_RATE = 0.001425               # 手續費率（0.1425%）
    TAX_RATE = 0.003                          # 交易稅率（0.3%）
    
    # v4.4.5 新增：下單價格優化（提高成交率）
    BUY_PRICE_PREMIUM = 1.01                 # 買進讓利 1%（掛高確保成交）
    SELL_PRICE_DISCOUNT = 0.99               # 賣出讓利 1%（掛低確保成交）
    
    # v4.4.5 新增：停損設定
    STOP_LOSS_PCT = 0.08                     # 停損百分比（預設 8%）
    ENABLE_TRAILING_STOP = True              # 是否啟用移動停損（v4.4.7 更新：預設開啟）
    TRAILING_STOP_PCT = 0.05                 # 移動停損回撤百分比（5%）
    
    # v4.4.6 新增：零股交易設定
    ENABLE_ODD_LOT = True                    # 是否啟用零股交易
    MIN_ODD_LOT_AMOUNT = 1                   # 最小零股數量
    ODD_LOT_TIME_IN_FORCE = 'IOC'            # 零股預設委託條件（IOC 立即成交否則取消）
    
    # 決策設定
    MIN_RR_RATIO = 1.5                        # 最低盈虧比
    MIN_CONFIDENCE = 'Medium'                 # 最低信心度（修正：Medium 也可買進）
    REQUIRE_HIGH_CONFIDENCE = False           # 是否要求高信心度（False = Medium 也可買）
    
    # v4.4.7 新增：移動停利設定（Trailing Stop）
    TRAILING_PROFIT_ENABLED = True            # 啟用移動停利
    TRAILING_PROFIT_ACTIVATION = 0.10         # 啟動條件：獲利 10% 後開始追蹤
    TRAILING_PROFIT_DISTANCE = 0.05           # 從最高點回落 5% 出場
    TRAILING_USE_MA5_EXIT = True              # 跌破 5 日線出場
    
    # v4.4.7 新增：盤整盤過濾設定
    RANGE_MARKET_FILTER_ENABLED = True        # 啟用盤整盤過濾
    RANGE_MARKET_REDUCE_POSITION = 0.5        # 盤整盤部位縮減比例
    
    # v4.4.7 新增：數據源驗證
    REQUIRE_REALTIME_FOR_LIVE = True          # 實單模式要求即時數據
    MAX_DATA_DELAY_SECONDS = 900              # 最大數據延遲（15分鐘）
    
    # 檔案路徑
    SIMULATION_DATA_FILE = 'simulation_data.json'
    IGNORE_LIST_FILE = 'ignore_list.json'
    TRADE_LOG_FILE = 'trade_log.json'
    TRAILING_STOP_FILE = 'trailing_stop_data.json'  # v4.4.7 新增：移動停利追蹤檔案
    
    # 掃描間隔（秒）
    SCAN_INTERVAL = 300  # 5分鐘


# ============================================================================
# 自動交易主程式
# ============================================================================

class AutoTrader:
    """
    自動交易主程式
    
    支援模擬模式與實單模式，整合量化分析進行自動交易決策。
    
    使用方式：
        # 模擬模式
        trader = AutoTrader(mode='SIMULATION', initial_capital=1000000)
        trader.run()
        
        # 實單模式
        trader = AutoTrader(mode='LIVE')
        trader.login(user_id, password, cert_path, cert_password)
        trader.run()
    """
    
    def __init__(self, mode: str = 'SIMULATION', initial_capital: float = None):
        """
        初始化自動交易器
        
        Args:
            mode: 'SIMULATION' 或 'LIVE'
            initial_capital: 初始資金（僅模擬模式使用）
        """
        # 驗證模式
        if mode not in [AutoTraderConfig.MODE_SIMULATION, AutoTraderConfig.MODE_LIVE]:
            raise ValueError(f"無效的模式: {mode}，請使用 'SIMULATION' 或 'LIVE'")
        
        self.mode = mode
        self.is_running = False
        self.last_scan_time = None
        
        # 初始化資料庫
        self.db = WatchlistDatabase()
        
        # 載入存股黑名單
        self.ignore_list = self._load_ignore_list()
        
        # 交易紀錄
        self.trade_log = []
        
        # v4.4.7 新增：移動停利追蹤數據
        self.trailing_stop_data = self._load_trailing_stop_data()
        
        # 根據模式初始化
        if self.mode == AutoTraderConfig.MODE_SIMULATION:
            # ============================================================
            # 模擬模式初始化
            # ============================================================
            self.trader = None  # 不需要真實交易器
            self.initial_capital = initial_capital or AutoTraderConfig.DEFAULT_INITIAL_CAPITAL
            
            # 載入或初始化模擬帳戶數據
            self.sim_data = self._load_simulation()
            if self.sim_data is None:
                # 首次執行，創建初始數據
                self.sim_data = {
                    'balance': self.initial_capital,
                    'inventory': {},  # {symbol: {'qty': 股數, 'cost': 成本價, 'buy_date': 日期}}
                    'initial_capital': self.initial_capital,
                    'created_at': datetime.datetime.now().isoformat(),
                    'last_updated': datetime.datetime.now().isoformat()
                }
                self._save_simulation()
            else:
                # 使用載入的初始資金
                self.initial_capital = self.sim_data.get('initial_capital', self.initial_capital)
            
            print(f"[AutoTrader] 模擬模式啟動")
            print(f"  初始資金：${self.initial_capital:,.0f}")
            print(f"  目前餘額：${self.sim_data['balance']:,.0f}")
            print(f"  持有部位：{len(self.sim_data['inventory'])} 檔")
            
        else:
            # ============================================================
            # 實單模式初始化
            # ============================================================
            if not FUBON_AVAILABLE:
                raise RuntimeError("實單模式需要安裝 fubon_neo SDK")
            
            self.trader = FubonTrader()
            self.sim_data = None
            self.initial_capital = None  # 將在登入後從 API 取得
            
            print(f"[AutoTrader] 實單模式初始化完成，請呼叫 login() 登入")
    
    # ========================================================================
    # 模擬帳戶數據管理
    # ========================================================================
    
    def _load_simulation(self) -> Optional[Dict]:
        """
        讀取模擬帳戶數據
        
        Returns:
            dict: 模擬帳戶數據，若檔案不存在則返回 None
        """
        try:
            if os.path.exists(AutoTraderConfig.SIMULATION_DATA_FILE):
                with open(AutoTraderConfig.SIMULATION_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"[AutoTrader] 已載入模擬帳戶數據")
                return data
        except Exception as e:
            print(f"[AutoTrader] 載入模擬數據失敗: {e}")
        return None
    
    def _save_simulation(self) -> bool:
        """
        儲存模擬帳戶數據
        
        Returns:
            bool: 是否儲存成功
        """
        if self.mode != AutoTraderConfig.MODE_SIMULATION:
            return False
        
        try:
            self.sim_data['last_updated'] = datetime.datetime.now().isoformat()
            with open(AutoTraderConfig.SIMULATION_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.sim_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[AutoTrader] 儲存模擬數據失敗: {e}")
            return False
    
    def _load_ignore_list(self) -> List[str]:
        """
        讀取存股黑名單（這些股票只看不動）
        
        Returns:
            list: 股票代碼列表
        """
        try:
            if os.path.exists(AutoTraderConfig.IGNORE_LIST_FILE):
                with open(AutoTraderConfig.IGNORE_LIST_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    ignore_list = data.get('symbols', [])
                    print(f"[AutoTrader] 已載入存股黑名單: {len(ignore_list)} 檔")
                    return ignore_list
        except Exception as e:
            print(f"[AutoTrader] 載入存股黑名單失敗: {e}")
        
        # 建立預設檔案
        default_data = {
            'description': '存股黑名單 - 這些股票只看不動，不會被自動交易',
            'symbols': [],
            'updated_at': datetime.datetime.now().isoformat()
        }
        try:
            with open(AutoTraderConfig.IGNORE_LIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
        except:
            pass
        
        return []
    
    def add_to_ignore_list(self, symbol: str) -> bool:
        """將股票加入存股黑名單"""
        if symbol not in self.ignore_list:
            self.ignore_list.append(symbol)
            try:
                data = {
                    'description': '存股黑名單 - 這些股票只看不動，不會被自動交易',
                    'symbols': self.ignore_list,
                    'updated_at': datetime.datetime.now().isoformat()
                }
                with open(AutoTraderConfig.IGNORE_LIST_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"[AutoTrader] 已將 {symbol} 加入存股黑名單")
                return True
            except Exception as e:
                print(f"[AutoTrader] 更新存股黑名單失敗: {e}")
        return False
    
    # ========================================================================
    # v4.4.7 新增：移動停利追蹤數據管理
    # ========================================================================
    
    def _load_trailing_stop_data(self) -> Dict:
        """
        讀取移動停利追蹤數據
        
        結構：{
            symbol: {
                'highest_price': 最高價,
                'trailing_stop_price': 移動停利價,
                'activated': 是否已啟動,
                'activation_price': 啟動時的價格,
                'updated_at': 更新時間
            }
        }
        """
        try:
            if os.path.exists(AutoTraderConfig.TRAILING_STOP_FILE):
                with open(AutoTraderConfig.TRAILING_STOP_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"[AutoTrader] 已載入移動停利追蹤數據: {len(data)} 檔")
                return data
        except Exception as e:
            print(f"[AutoTrader] 載入移動停利數據失敗: {e}")
        return {}
    
    def _save_trailing_stop_data(self) -> bool:
        """儲存移動停利追蹤數據"""
        try:
            with open(AutoTraderConfig.TRAILING_STOP_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.trailing_stop_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[AutoTrader] 儲存移動停利數據失敗: {e}")
            return False
    
    def update_trailing_stop(self, symbol: str, current_price: float, cost: float, ma5: float = None) -> Dict:
        """
        更新移動停利追蹤
        
        移動停利邏輯：
        1. 獲利 >= 10% 時啟動追蹤
        2. 追蹤最高價
        3. 當價格從最高點回落 5% 或跌破 5 日線時觸發停利
        
        Args:
            symbol: 股票代碼
            current_price: 當前價格
            cost: 成本價
            ma5: 5 日均線價格（可選）
        
        Returns:
            dict: {
                'activated': 是否已啟動移動停利,
                'highest_price': 追蹤的最高價,
                'trailing_stop_price': 移動停利價,
                'trigger_sell': 是否觸發賣出,
                'trigger_reason': 觸發原因
            }
        """
        if not AutoTraderConfig.TRAILING_PROFIT_ENABLED:
            return {'activated': False, 'trigger_sell': False}
        
        if cost <= 0 or current_price <= 0:
            return {'activated': False, 'trigger_sell': False}
        
        # 計算獲利百分比
        profit_pct = (current_price - cost) / cost
        
        # 取得或初始化追蹤數據
        if symbol not in self.trailing_stop_data:
            self.trailing_stop_data[symbol] = {
                'highest_price': current_price,
                'trailing_stop_price': 0,
                'activated': False,
                'activation_price': 0,
                'updated_at': datetime.datetime.now().isoformat()
            }
        
        ts = self.trailing_stop_data[symbol]
        
        # 檢查是否達到啟動條件（獲利 >= 10%）
        activation_threshold = AutoTraderConfig.TRAILING_PROFIT_ACTIVATION
        if not ts['activated'] and profit_pct >= activation_threshold:
            ts['activated'] = True
            ts['activation_price'] = current_price
            ts['highest_price'] = current_price
            # 設定初始移動停利價（從最高點回落 5%）
            distance_pct = AutoTraderConfig.TRAILING_PROFIT_DISTANCE
            ts['trailing_stop_price'] = current_price * (1 - distance_pct)
            ts['updated_at'] = datetime.datetime.now().isoformat()
            print(f"[TrailingStop] {symbol} 啟動移動停利：獲利 {profit_pct*100:.1f}%，停利價 ${ts['trailing_stop_price']:.2f}")
        
        # 如果已啟動，更新追蹤
        trigger_sell = False
        trigger_reason = ''
        
        if ts['activated']:
            # 更新最高價
            if current_price > ts['highest_price']:
                ts['highest_price'] = current_price
                # 更新移動停利價
                distance_pct = AutoTraderConfig.TRAILING_PROFIT_DISTANCE
                ts['trailing_stop_price'] = current_price * (1 - distance_pct)
                ts['updated_at'] = datetime.datetime.now().isoformat()
                print(f"[TrailingStop] {symbol} 創新高 ${current_price:.2f}，停利價上移至 ${ts['trailing_stop_price']:.2f}")
            
            # 檢查是否觸發停利
            # 條件 1：價格跌破移動停利價
            if current_price <= ts['trailing_stop_price']:
                trigger_sell = True
                drawdown_pct = (ts['highest_price'] - current_price) / ts['highest_price'] * 100
                trigger_reason = f"移動停利觸發（從最高${ts['highest_price']:.2f}回落{drawdown_pct:.1f}%）"
            
            # 條件 2：跌破 5 日線（如果有提供）
            if AutoTraderConfig.TRAILING_USE_MA5_EXIT and ma5 and ma5 > 0:
                if current_price < ma5 and ts['highest_price'] > ma5:
                    trigger_sell = True
                    trigger_reason = f"跌破5日線（MA5=${ma5:.2f}，現價${current_price:.2f}）"
        
        # 儲存更新
        self._save_trailing_stop_data()
        
        return {
            'activated': ts['activated'],
            'highest_price': ts['highest_price'],
            'trailing_stop_price': ts['trailing_stop_price'],
            'trigger_sell': trigger_sell,
            'trigger_reason': trigger_reason,
            'profit_pct': profit_pct * 100
        }
    
    def clear_trailing_stop(self, symbol: str):
        """清除股票的移動停利追蹤數據（賣出後呼叫）"""
        if symbol in self.trailing_stop_data:
            del self.trailing_stop_data[symbol]
            self._save_trailing_stop_data()
            print(f"[TrailingStop] 已清除 {symbol} 的移動停利追蹤")
    
    # ========================================================================
    # 登入功能（僅實單模式）
    # ========================================================================
    
    def login(self, user_id: str, password: str, cert_path: str, cert_password: str) -> Dict:
        """
        登入富邦證券（僅實單模式）
        
        Args:
            user_id: 身分證字號
            password: 登入密碼
            cert_path: 憑證檔案路徑
            cert_password: 憑證密碼
        
        Returns:
            dict: 登入結果
        """
        if self.mode != AutoTraderConfig.MODE_LIVE:
            return {'success': False, 'message': '模擬模式不需要登入'}
        
        result = self.trader.login(user_id, password, cert_path, cert_password)
        
        if result['success']:
            print(f"[AutoTrader] 實單模式登入成功")
            # 取得初始資金
            self._update_live_balance()
        
        return result
    
    def _update_live_balance(self):
        """更新實單模式的帳戶餘額"""
        if self.mode != AutoTraderConfig.MODE_LIVE or not self.trader:
            return
        
        # TODO: 從 API 取得帳戶餘額
        # 目前 FubonTrader 可能需要額外實作餘額查詢
        pass
    
    # ========================================================================
    # 資金與庫存查詢
    # ========================================================================
    
    def get_balance(self) -> float:
        """
        取得可用餘額
        
        Returns:
            float: 可用現金餘額
        """
        if self.mode == AutoTraderConfig.MODE_SIMULATION:
            return self.sim_data.get('balance', 0)
        else:
            # 實單模式：從 API 查詢
            # TODO: 實作真實餘額查詢
            return 0
    
    def get_inventory(self) -> Dict:
        """
        取得庫存（含現價、損益計算）
        
        v4.4.5 修復：富邦 API 僅回傳股數與成本，不含現價。
        需另外呼叫 RealtimePriceFetcher 取得現價並計算損益。
        
        Returns:
            dict: {symbol: {
                'qty': 股數, 
                'cost': 成本價, 
                'name': 名稱,
                'current_price': 現價,
                'market_value': 市值,
                'pnl': 損益,
                'pnl_pct': 損益百分比
            }}
        """
        if self.mode == AutoTraderConfig.MODE_SIMULATION:
            inventory = self.sim_data.get('inventory', {}).copy()
            
            # 為模擬帳戶補充現價資訊
            for symbol, pos in inventory.items():
                qty = pos.get('qty', 0)
                cost = pos.get('cost', 0)
                
                # 優先使用已緩存的現價
                current_price = pos.get('last_price', cost)
                
                # 嘗試取得最新現價
                try:
                    price_data = RealtimePriceFetcher.get_realtime_price(symbol, "台股")
                    if price_data and price_data.get('price'):
                        current_price = price_data['price']
                        # 更新緩存
                        inventory[symbol]['last_price'] = current_price
                        if not pos.get('name') and price_data.get('name'):
                            inventory[symbol]['name'] = price_data['name']
                except:
                    pass
                
                # 計算損益
                cost_basis = qty * cost
                market_value = qty * current_price
                pnl = market_value - cost_basis
                pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                inventory[symbol]['current_price'] = current_price
                inventory[symbol]['market_value'] = market_value
                inventory[symbol]['pnl'] = pnl
                inventory[symbol]['pnl_pct'] = pnl_pct
            
            return inventory
            
        else:
            # 實單模式：從 API 查詢
            result = self.trader.get_inventories()
            if not result.get('success'):
                print(f"[AutoTrader] 取得庫存失敗: {result.get('message', '')}")
                return {}
            
            inventory = {}
            for item in result.get('data', []):
                symbol = item.get('symbol', '')
                if not symbol:
                    continue
                
                # v4.4.5 修正：對應 fubon_trading.py 的欄位名稱
                qty = item.get('qty', 0)  # 股數
                cost = item.get('price_avg', 0)  # 成本均價
                current_price = item.get('price_now', 0)  # 現價
                name = item.get('name', '')
                pnl = item.get('pnl', 0)  # 損益（API 已計算）
                pnl_pct = item.get('pnl_percent', 0)  # 報酬率（API 已計算）
                
                # 如果 API 沒提供現價，嘗試從其他來源取得
                if current_price == 0 and cost > 0:
                    try:
                        price_data = RealtimePriceFetcher.get_realtime_price(symbol, "台股")
                        if price_data and price_data.get('price'):
                            current_price = price_data['price']
                            if not name and price_data.get('name'):
                                name = price_data['name']
                    except:
                        pass
                
                # 計算市值
                cost_basis = qty * cost
                market_value = qty * current_price if current_price > 0 else cost_basis
                
                # 如果 API 沒提供損益，自行計算
                if pnl == 0 and cost > 0 and current_price > 0:
                    pnl = market_value - cost_basis
                    pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                inventory[symbol] = {
                    'qty': qty,
                    'cost': cost,
                    'name': name,
                    'current_price': current_price,
                    'market_value': market_value,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                }
            
            return inventory
    
    def get_available_budget(self) -> float:
        """
        計算可用預算
        
        可用資金 = min(帳戶餘額, 預算上限 - 目前持倉成本)
        
        Returns:
            float: 可用預算
        """
        balance = self.get_balance()
        inventory = self.get_inventory()
        
        # 計算目前持倉成本
        total_cost = sum(
            pos.get('qty', 0) * pos.get('cost', 0)
            for pos in inventory.values()
        )
        
        # 計算可用預算
        budget_remaining = AutoTraderConfig.MAX_INVESTMENT_BUDGET - total_cost
        available = min(balance, max(0, budget_remaining))
        
        return available
    
    # ========================================================================
    # 掃描與分析核心
    # ========================================================================
    
    def scan_watchlist(self) -> List[Dict]:
        """
        掃描股票清單並進行分析
        
        v4.4.5 修正：
        1. 掃描範圍為「自選股」與「庫存股」的聯集（Union）
           避免庫存股被移出自選名單後成為孤兒單，無法執行停損
        2. 優先過濾存股黑名單，黑名單內的股票直接跳過分析
        
        Returns:
            list: 分析結果列表
        """
        results = []
        
        # ============================================================
        # 步驟 1：建立掃描目標（自選股 + 庫存股 聯集）
        # ============================================================
        
        # 取得自選股
        watchlist_stocks = self.db.get_all_stocks()
        watchlist_symbols = {stock[0]: {'name': stock[1], 'market': stock[2] or '台股'} 
                            for stock in watchlist_stocks}
        
        # 取得庫存股（確保持倉股票一定會被掃描）
        inventory = self.get_inventory()
        for symbol in inventory.keys():
            if symbol not in watchlist_symbols:
                # 庫存股不在自選，需要補充進掃描清單
                watchlist_symbols[symbol] = {
                    'name': inventory[symbol].get('name', symbol),
                    'market': '台股'  # 預設台股
                }
                print(f"[AutoTrader] 庫存股 {symbol} 不在自選名單，已加入掃描")
        
        if not watchlist_symbols:
            print("[AutoTrader] 無股票可掃描（自選股與庫存皆為空）")
            return results
        
        print(f"\n[AutoTrader] 開始掃描 {len(watchlist_symbols)} 檔股票...")
        print(f"  (自選股: {len(watchlist_stocks)}檔, 庫存股: {len(inventory)}檔)")
        print("=" * 60)
        
        # ============================================================
        # 步驟 2：逐一分析（優先過濾黑名單）
        # ============================================================
        
        for symbol, info in watchlist_symbols.items():
            name = info.get('name') or symbol
            market = info.get('market') or '台股'
            
            # ⚠️ 關鍵過濾：存股黑名單優先檢查
            # 黑名單內的股票不分析、不交易（包含庫存股）
            if symbol in self.ignore_list:
                print(f"  🔒 {symbol} {name}: 存股名單，跳過分析")
                continue
            
            # 標記是否為持倉股
            has_position = symbol in inventory
            position_marker = "📦持倉" if has_position else "📊分析"
            
            try:
                # 呼叫 QuickAnalyzer 進行分析
                result = QuickAnalyzer.analyze_stock(symbol, market)
                
                if result is None:
                    print(f"  ❌ {symbol} {name}: 分析失敗，跳過")
                    continue
                
                # 加入額外資訊
                result['is_ignored'] = False  # 能執行到這裡表示不在黑名單
                result['stock_name'] = name
                result['has_position'] = has_position
                
                # 若是持倉股，補充持倉資訊
                if has_position:
                    result['position'] = inventory[symbol]
                
                # 顯示簡要分析結果
                dm = result.get('decision_matrix', {})
                scenario = dm.get('scenario', 'X')
                recommendation = dm.get('recommendation', '待分析')
                confidence = dm.get('confidence', 'Medium')
                
                # 取得短線建議
                short_term = dm.get('short_term_action', '')
                
                print(f"  {position_marker} {symbol} {name}: 場景{scenario} | {recommendation}")
                if short_term:
                    print(f"       短線建議: {short_term} | 信心度:{confidence}")
                
                results.append(result)
                
            except Exception as e:
                print(f"  ❌ {symbol}: 分析錯誤 - {e}")
                continue
        
        print("=" * 60)
        print(f"[AutoTrader] 掃描完成，成功分析 {len(results)} 檔")
        
        self.last_scan_time = datetime.datetime.now()
        return results
    
    # ========================================================================
    # 交易決策邏輯
    # ========================================================================
    
    def _detect_chart_signals(self, result: Dict) -> Dict:
        """
        v4.4.4 新增：使用與主程式 K 線標記相同的訊號邏輯
        v4.4.5 修正：移除硬編碼參數，改用 QuantConfig
        
        偵測以下訊號：
        - 買進訊號：三盤突破、左側買訊（超跌反彈）、黃金買點條件
        - 賣出訊號：三盤跌破、左側賣訊（過熱回檔）、放量跌破
        
        Args:
            result: QuickAnalyzer.analyze_stock 的結果
        
        Returns:
            dict: {'buy_signal': bool, 'sell_signal': bool, 'buy_reason': str, 'sell_reason': str}
        """
        signals = {
            'buy_signal': False,
            'sell_signal': False,
            'buy_reason': '',
            'sell_reason': ''
        }
        
        try:
            # 取得技術指標
            tech = result.get('technical', {})
            rsi = tech.get('rsi', 50)
            ma5 = tech.get('ma5', 0)
            ma20 = tech.get('ma20', 0)
            ma55 = tech.get('ma55', 0)
            
            # 取得價格和成交量資訊
            current_price = result.get('current_price', 0)
            
            # 從 decision_matrix 取得乖離率和其他指標
            dm = result.get('decision_matrix', {})
            dv = dm.get('decision_vars', {})
            bias_20 = dv.get('bias_20', 0)
            
            # 取得量價分析
            vp = result.get('volume_price', {})
            vp_signals = vp.get('signals', []) if vp.get('available') else []
            
            # 取得均值回歸訊號
            mr = result.get('mean_reversion', {})
            left_buy_triggered = mr.get('left_buy_signal', {}).get('triggered', False) if mr.get('available') else False
            left_sell_triggered = mr.get('left_sell_signal', {}).get('triggered', False) if mr.get('available') else False
            
            # 取得成交量比率
            vol_analysis = result.get('volume_analysis', {})
            vol_ratio = vol_analysis.get('vol_ratio_20', 1.0) if vol_analysis else 1.0
            
            # ============================================================
            # 買進訊號檢測（使用 QuantConfig 參數）
            # ============================================================
            
            # 排除高檔爆量收黑（主力出貨跡象）
            is_distribution = False
            for sig in vp_signals:
                if sig.get('code') in ['VP07', 'VP08']:  # 放量不漲、放量跌破
                    is_distribution = True
                    break
            
            # 條件1：三盤突破（多頭趨勢確認）
            if ma5 > 0 and ma20 > 0 and ma55 > 0:
                if current_price > ma55 and ma5 > ma20 > ma55:
                    # 帶量突破
                    for sig in vp_signals:
                        if sig.get('code') == 'VP05':  # 帶量突破
                            if not is_distribution:
                                signals['buy_signal'] = True
                                signals['buy_reason'] = '三盤突破（多頭排列+帶量突破）'
            
            # 條件2：左側買訊（超跌反彈）- 使用 QuantConfig 閾值
            if not signals['buy_signal']:
                oversold_bias = QuantConfig.BIAS_OVERSOLD_THRESHOLD  # -10%
                oversold_rsi = QuantConfig.RSI_OVERSOLD_LEVEL  # 25
                if bias_20 < oversold_bias and rsi < oversold_rsi:
                    signals['buy_signal'] = True
                    signals['buy_reason'] = f'左側買訊（超跌反彈：乖離{bias_20:.1f}%，RSI={rsi:.0f}）'
            
            # 條件3：黃金買點 - 使用 QuantConfig 閾值
            if not signals['buy_signal']:
                is_bull = ma5 > ma20 > 0 and current_price > ma20
                golden_bias = QuantConfig.GOLDEN_BUY_BIAS_MIN <= bias_20 <= QuantConfig.GOLDEN_BUY_BIAS_MAX
                golden_rsi = rsi < QuantConfig.GOLDEN_BUY_RSI_MAX
                if is_bull and golden_bias and golden_rsi:
                    if not is_distribution:
                        signals['buy_signal'] = True
                        signals['buy_reason'] = f'黃金買點（乖離{bias_20:.1f}%，RSI={rsi:.0f}）'
            
            # ============================================================
            # 賣出訊號檢測（使用 QuantConfig 參數）
            # ============================================================
            
            # 條件1：三盤跌破（空頭趨勢確認）
            if ma5 > 0 and ma20 > 0 and ma55 > 0:
                if current_price < ma55 and ma5 < ma20 < ma55:
                    signals['sell_signal'] = True
                    signals['sell_reason'] = '三盤跌破（空頭排列）'
            
            # 條件2：左側賣訊（過熱回檔）- 使用 QuantConfig 閾值
            if not signals['sell_signal']:
                overbought_bias = QuantConfig.BIAS_OVERBOUGHT_THRESHOLD  # 15%
                overbought_rsi = QuantConfig.RSI_OVERBOUGHT_LEVEL  # 75
                if bias_20 > overbought_bias and rsi > overbought_rsi:
                    signals['sell_signal'] = True
                    signals['sell_reason'] = f'左側賣訊（過熱回檔：乖離{bias_20:.1f}%，RSI={rsi:.0f}）'
            
            # 條件3：放量跌破 - 使用 QuantConfig 閾值
            if not signals['sell_signal']:
                volume_spike = QuantConfig.VOLUME_SPIKE_THRESHOLD  # 2.0
                if current_price < ma20 and vol_ratio > volume_spike:
                    signals['sell_signal'] = True
                    signals['sell_reason'] = f'放量跌破MA20（量比={vol_ratio:.1f}）'
            
            # 條件4：VP 賣出訊號
            if not signals['sell_signal']:
                for sig in vp_signals:
                    if sig.get('code') in ['VP08', 'VP12']:  # 放量跌破、跳空下跌
                        signals['sell_signal'] = True
                        signals['sell_reason'] = f"量價賣訊：{sig.get('name', '')}"
                        break
            
        except Exception as e:
            print(f"[AutoTrader] 訊號檢測錯誤: {e}")
        
        return signals
    
    def evaluate_signals(self, analysis_results: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        評估分析結果，產出買進/賣出訊號
        
        決策優先級：
        1. 賣出檢查（優先）
        2. 買進檢查
        
        Args:
            analysis_results: QuickAnalyzer 分析結果列表
        
        Returns:
            tuple: (買進訊號列表, 賣出訊號列表)
        """
        buy_signals = []
        sell_signals = []
        
        inventory = self.get_inventory()
        
        for result in analysis_results:
            symbol = result.get('symbol', '')
            is_ignored = result.get('is_ignored', False)
            
            # 存股黑名單：只看不動
            if is_ignored:
                continue
            
            # 取得分析數據
            dm = result.get('decision_matrix', {})
            rm = result.get('risk_manager', {})
            current_price = result.get('current_price', 0)
            
            # 檢查是否持有
            has_position = symbol in inventory
            position = inventory.get(symbol, {})
            
            # ============================================================
            # 1. 賣出檢查（優先）
            # ============================================================
            if has_position:
                sell_signal = self._check_sell_signal(result, position, dm, rm)
                if sell_signal:
                    sell_signal['symbol'] = symbol
                    sell_signal['current_price'] = current_price
                    sell_signal['position'] = position
                    sell_signals.append(sell_signal)
                    continue  # 已決定賣出，不再檢查買進
            
            # ============================================================
            # 2. 買進檢查
            # ============================================================
            if not has_position:  # 目前空手才考慮買進
                buy_signal = self._check_buy_signal(result, dm, rm)
                if buy_signal:
                    buy_signal['symbol'] = symbol
                    buy_signal['current_price'] = current_price
                    buy_signal['result'] = result
                    buy_signals.append(buy_signal)
        
        return buy_signals, sell_signals
    
    def _check_sell_signal(self, result: Dict, position: Dict, dm: Dict, rm: Dict) -> Optional[Dict]:
        """
        檢查賣出訊號（v4.4.7 更新：整合移動停利）
        
        賣出條件（按優先級排序）：
        0. 形態分析：M頭/頭肩頂/島狀反轉確立（最高優先）
        1. 觸發設定停損百分比
        1.5 v4.4.7 新增：移動停利（獲利後追蹤最高點）
        2. 觸發 ATR 停損價
        3. 觸發停利價
        4. 短線建議為「賣出」或「減碼」
        5. K 線賣出訊號（三盤跌破/過熱回檔/放量跌破）
        6. 場景 D/E（空頭確認/順勢空頭）
        
        Args:
            result: 分析結果
            position: 持倉資訊
            dm: 決策矩陣
            rm: 風險管理
        
        Returns:
            dict: 賣出訊號，None 表示不賣
        """
        current_price = result.get('current_price', 0)
        cost = position.get('cost', 0)
        symbol = result.get('symbol', '')
        
        # 取得 MA5（用於移動停利）
        tech = result.get('technical', {})
        ma5 = tech.get('ma5', 0)
        
        # 取得各種建議
        short_term_action = dm.get('short_term_action', '')  # 短線建議
        recommendation = dm.get('recommendation', '')  # 綜合分析建議
        action_timing = dm.get('action_timing', '')  # 今日建議/進場時機
        scenario = dm.get('scenario', '')
        
        # ============================================================
        # 風險控制區塊（強制賣出，不需三重確認）
        # ============================================================
        
        # 0. v4.4.6 新增：形態分析優先判斷（頭部型態確立）
        pattern = result.get('pattern_analysis', {})
        if pattern.get('available') and pattern.get('detected'):
            pattern_status = pattern.get('status', '')
            pattern_signal = pattern.get('signal', 'neutral')
            pattern_name = pattern.get('pattern_name', '')
            volume_confirmed = pattern.get('volume_confirmed', False)
            
            # 頭部型態確立 -> 強制賣出訊號（風控）
            if 'CONFIRMED' in pattern_status and pattern_signal == 'sell':
                return {
                    'action': 'SELL',
                    'reason': f'【風控】形態確立：{pattern_name}' + ('（量能確認）' if volume_confirmed else ''),
                    'urgency': 'CRITICAL' if volume_confirmed else 'HIGH',
                    'pattern_target': pattern.get('target_price', 0)
                }
        
        # 1. 停損百分比檢查（最優先 - 風險控制）
        if cost > 0 and current_price > 0:
            loss_pct = (current_price - cost) / cost
            stop_loss_threshold = -AutoTraderConfig.STOP_LOSS_PCT  # 負值（如 -0.08 = -8%）
            
            if loss_pct <= stop_loss_threshold:
                return {
                    'action': 'SELL',
                    'reason': f'【風控】觸發停損百分比（虧損{loss_pct*100:.1f}%，停損線:{stop_loss_threshold*100:.0f}%）',
                    'urgency': 'CRITICAL'
                }
        
        # 1.5 v4.4.7 新增：移動停利檢查（Trailing Stop）
        if AutoTraderConfig.TRAILING_PROFIT_ENABLED and symbol and cost > 0:
            trailing_result = self.update_trailing_stop(symbol, current_price, cost, ma5)
            
            if trailing_result.get('trigger_sell'):
                return {
                    'action': 'SELL',
                    'reason': f"【風控】移動停利：{trailing_result.get('trigger_reason', '')}（獲利{trailing_result.get('profit_pct', 0):.1f}%）",
                    'urgency': 'MEDIUM',
                    'trailing_stop_info': trailing_result
                }
        
        # 2. ATR 停損檢查
        stop_loss = rm.get('stop_loss', 0) if rm.get('available') else 0
        if stop_loss > 0 and current_price <= stop_loss:
            return {
                'action': 'SELL',
                'reason': f'【風控】觸發ATR停損（停損價:{stop_loss:.2f}，現價:{current_price:.2f}）',
                'urgency': 'HIGH'
            }
        
        # 3. 停利檢查（固定目標價）
        take_profit = rm.get('take_profit', 0) if rm.get('available') else 0
        if take_profit > 0 and current_price >= take_profit:
            # v4.4.7：如果啟用移動停利，達到目標價時不立即賣出，改為啟動追蹤
            if AutoTraderConfig.TRAILING_PROFIT_ENABLED:
                # 目標價達標，讓移動停利接手
                print(f"[AutoTrader] {symbol} 達到目標價 ${take_profit:.2f}，移動停利接手追蹤")
                # 不返回賣出訊號，讓移動停利來決定
            else:
                return {
                    'action': 'SELL',
                    'reason': f'【風控】觸發停利（停利價:{take_profit:.2f}，現價:{current_price:.2f}）',
                    'urgency': 'MEDIUM'
                }
        
        # ============================================================
        # v4.4.7 更新：一般賣出需三重確認
        # 需同時滿足：短線建議賣出 + 今日建議賣出 + 綜合分析建議賣出
        # ============================================================
        
        # 定義賣出關鍵字
        sell_keywords = ['賣出', '出清', '停損', '減碼', '減持', '獲利了結', '清倉']
        
        # 檢查短線建議
        has_short_term_sell = any(keyword in short_term_action for keyword in sell_keywords)
        
        # 檢查今日建議/進場時機
        has_timing_sell = any(keyword in action_timing for keyword in sell_keywords) or \
                          '不宜' in action_timing or '觀望' in action_timing
        
        # 檢查綜合分析建議
        has_recommendation_sell = any(keyword in recommendation for keyword in sell_keywords) or \
                                   '空頭' in recommendation or '反轉' in recommendation
        
        # 檢查場景 D/E（空頭確認/順勢空頭）
        is_bearish_scenario = scenario in ['D', 'E']
        
        # v4.4.7：三重確認邏輯
        # 必須短線 + (今日建議 或 場景D/E) + 綜合分析 都建議賣出
        if has_short_term_sell and (has_timing_sell or is_bearish_scenario) and has_recommendation_sell:
            # 組合原因說明
            reasons = []
            reasons.append(f"短線:{short_term_action}")
            if has_timing_sell:
                reasons.append(f"時機:{action_timing}")
            if is_bearish_scenario:
                reasons.append(f"場景:{scenario}")
            reasons.append(f"建議:{recommendation}")
            
            return {
                'action': 'SELL',
                'reason': f'三重確認賣出（{" | ".join(reasons)}）',
                'urgency': 'HIGH' if is_bearish_scenario else 'MEDIUM'
            }
        
        # 若未達到三重確認，不賣出
        return None
    
    def _check_buy_signal(self, result: Dict, dm: Dict, rm: Dict) -> Optional[Dict]:
        """
        檢查買進訊號（v4.4.7 更新：短線建議優先判斷）
        
        v4.4.7 買進條件（必須同時滿足）：
        1. 短線建議為「買進」相關（優先判斷）
        2. 綜合分析建議為「買進」相關
        
        否決條件（任一觸發即放棄買進）：
        1. 形態分析：M頭/頭肩頂/島狀反轉確立（最優先否決）
        2. 信心度為 Low
        3. Downgraded == True
        4. RR < 1.5
        5. 場景 A（過熱）
        6. RSI > 80
        7. 短線建議為「觀望」或「減碼」或「賣出」
        8. v4.4.7 更新：盤整盤過濾（場景 F 或 ADX < 20）
        
        Args:
            result: 分析結果
            dm: 決策矩陣
            rm: 風險管理
        
        Returns:
            dict: 買進訊號，None 表示不買
        """
        scenario = dm.get('scenario', '')
        recommendation = dm.get('recommendation', '')
        confidence = dm.get('confidence', 'Medium')
        downgraded = dm.get('downgraded', False)
        short_term_action = dm.get('short_term_action', '')
        
        dv = dm.get('decision_vars', {})
        rr_ratio = dv.get('rr_ratio', 0)
        rsi = dv.get('rsi', 50)
        adx = dv.get('adx', 25)
        
        # ============================================================
        # v4.4.7 更新：短線建議優先判斷
        # 必須短線建議為買進相關，否則不買
        # ============================================================
        short_term_buy_keywords = ['買進', '加碼', '積極買進', '強力買進', '建立部位', '可買進']
        has_short_term_buy = any(keyword in short_term_action for keyword in short_term_buy_keywords)
        
        # 綜合分析建議為買進相關
        recommendation_buy_keywords = ['強力買進', '建議買進', '逢低布局', '積極進場', '買進']
        has_recommendation_buy = any(keyword in recommendation for keyword in recommendation_buy_keywords)
        
        # v4.4.7：必須短線+綜合分析都建議買進
        if not has_short_term_buy:
            # 短線建議不是買進，不買
            return None
        
        if not has_recommendation_buy:
            # 綜合分析不建議買進，不買
            return None
        
        # ============================================================
        # v4.4.6 新增：形態分析優先判斷
        # ============================================================
        pattern = result.get('pattern_analysis', {})
        if pattern.get('available') and pattern.get('detected'):
            pattern_status = pattern.get('status', '')
            pattern_signal = pattern.get('signal', 'neutral')
            pattern_name = pattern.get('pattern_name', '')
            volume_confirmed = pattern.get('volume_confirmed', False)
            
            # 形態否決：頭部型態確立
            if 'CONFIRMED' in pattern_status and pattern_signal == 'sell':
                # 有賣出形態確立，不買進
                return None
            
            # 形態買進訊號：底部型態確立（加分項，不是必要條件）
            if 'CONFIRMED' in pattern_status and pattern_signal == 'buy':
                return {
                    'action': 'BUY',
                    'reason': f'形態確立：{pattern_name}（短線:{short_term_action}）',
                    'strength': 'STRONG' if volume_confirmed else 'NORMAL',
                    'rr_ratio': rr_ratio,
                    'pattern_target': pattern.get('target_price', 0),
                    'pattern_stop': pattern.get('stop_loss', 0)
                }
        
        # ============================================================
        # 否決權檢查（優先）
        # ============================================================
        vetoes = []
        
        # 否決 1：場景 A 過熱
        if scenario == 'A':
            vetoes.append(f"場景A過熱（{dm.get('scenario_name', '')}）")
        
        # 否決 2：信心度不足（v4.4.6 修正：Medium 也可以買進）
        # 只有 Low 信心度才會被否決
        valid_confidence = ['High', 'Medium']
        if AutoTraderConfig.REQUIRE_HIGH_CONFIDENCE:
            valid_confidence = ['High']  # 嚴格模式只接受 High
        
        if confidence not in valid_confidence:
            vetoes.append(f"信心度不足（{confidence}，需要 {'/'.join(valid_confidence)}）")
        
        # 否決 3：被濾網降級
        if downgraded:
            vetoes.append("已被濾網降級")
        
        # 否決 4：盈虧比不佳
        if rr_ratio < AutoTraderConfig.MIN_RR_RATIO:
            vetoes.append(f"盈虧比不佳（RR={rr_ratio:.2f}，需≥{AutoTraderConfig.MIN_RR_RATIO}）")
        
        # 否決 5：RSI 嚴重超買
        if rsi > 80:
            vetoes.append(f"RSI嚴重超買（{rsi:.0f}）")
        
        # 否決 6：短線建議為觀望、減碼或賣出
        if any(keyword in short_term_action for keyword in ['觀望', '減碼', '減持', '賣出', '出清', '停損']):
            vetoes.append(f"短線建議不宜買進（{short_term_action}）")
        
        # ============================================================
        # v4.4.7 新增：盤整盤過濾（避免在震盪區被雙巴）
        # ============================================================
        if AutoTraderConfig.RANGE_MARKET_FILTER_ENABLED:
            # 場景 F 是盤整震盪
            if scenario == 'F':
                vetoes.append(f"場景F盤整震盪（ADX={adx:.0f}，趨勢不明）")
            # ADX < 20 也視為盤整
            elif adx < QuantConfig.RANGE_MARKET_ADX_THRESHOLD:
                vetoes.append(f"ADX過低（{adx:.0f} < {QuantConfig.RANGE_MARKET_ADX_THRESHOLD}），趨勢不明")
            # 場景 C 空頭反彈也要謹慎
            elif scenario == 'C':
                # 空頭反彈場景，允許買進但會標記為輕倉
                pass  # 不否決，但後續會縮減部位
        
        # 若有任何否決條件，放棄買進
        if vetoes:
            return None
        
        # ============================================================
        # 買進訊號確認（已通過短線+綜合分析雙重確認）
        # ============================================================
        
        # 檢查是否為空頭反彈場景（需要輕倉）
        is_light_position = scenario == 'C'
        
        # 返回買進訊號
        return {
            'action': 'BUY',
            'reason': f'短線建議:{short_term_action} + 綜合建議:{recommendation}',
            'strength': 'LIGHT' if is_light_position else 'STRONG',
            'rr_ratio': rr_ratio,
            'light_position': is_light_position,
            'light_reason': '空頭反彈場景，建議輕倉' if is_light_position else ''
        }
    
    # ========================================================================
    # 交易執行
    # ========================================================================
    
    def execute_trades(self, buy_signals: List[Dict], sell_signals: List[Dict]) -> Dict:
        """
        執行交易
        
        Args:
            buy_signals: 買進訊號列表
            sell_signals: 賣出訊號列表
        
        Returns:
            dict: 執行結果
        """
        results = {
            'executed_buys': [],
            'executed_sells': [],
            'skipped': [],
            'errors': []
        }
        
        # ============================================================
        # 1. 先執行賣出（釋放資金）
        # ============================================================
        for signal in sell_signals:
            try:
                result = self._execute_sell(signal)
                if result['success']:
                    results['executed_sells'].append(result)
                else:
                    results['errors'].append(result)
            except Exception as e:
                results['errors'].append({
                    'symbol': signal.get('symbol'),
                    'error': str(e)
                })
        
        # ============================================================
        # 2. 再執行買進
        # ============================================================
        for signal in buy_signals:
            try:
                result = self._execute_buy(signal)
                if result['success']:
                    results['executed_buys'].append(result)
                elif result.get('skipped'):
                    results['skipped'].append(result)
                else:
                    results['errors'].append(result)
            except Exception as e:
                results['errors'].append({
                    'symbol': signal.get('symbol'),
                    'error': str(e)
                })
        
        return results
    
    def _execute_sell(self, signal: Dict) -> Dict:
        """
        執行賣出
        
        v4.4.6 更新：使用智慧下單，自動拆分整張與零股
        
        Args:
            signal: 賣出訊號
        
        Returns:
            dict: 執行結果
        """
        symbol = signal.get('symbol')
        position = signal.get('position', {})
        current_price = signal.get('current_price', 0)
        qty = position.get('qty', 0)
        cost = position.get('cost', 0)
        
        if qty <= 0:
            return {'success': False, 'symbol': symbol, 'message': '無持倉可賣'}
        
        # v4.4.5：下單價格優化（讓利確保成交）
        order_price = round(current_price * AutoTraderConfig.SELL_PRICE_DISCOUNT, 2)
        
        # 計算損益（以下單價計算）
        proceeds = qty * order_price
        cost_basis = qty * cost
        gross_pnl = proceeds - cost_basis
        
        # 扣除手續費和交易稅
        commission = proceeds * AutoTraderConfig.COMMISSION_RATE
        tax = proceeds * AutoTraderConfig.TAX_RATE
        net_pnl = gross_pnl - commission - tax
        
        # 計算整張與零股
        round_lots = (qty // 1000) * 1000
        odd_lots = qty % 1000
        
        if self.mode == AutoTraderConfig.MODE_SIMULATION:
            # ============================================================
            # 模擬模式：更新模擬帳戶
            # ============================================================
            net_proceeds = proceeds - commission - tax
            self.sim_data['balance'] += net_proceeds
            
            # 移除持倉
            if symbol in self.sim_data['inventory']:
                del self.sim_data['inventory'][symbol]
            
            self._save_simulation()
            
            # 記錄交易
            trade_record = {
                'time': datetime.datetime.now().isoformat(),
                'action': 'SELL',
                'symbol': symbol,
                'qty': qty,
                'round_lots': round_lots,
                'odd_lots': odd_lots,
                'price': order_price,
                'proceeds': net_proceeds,
                'pnl': net_pnl,
                'reason': signal.get('reason', '')
            }
            self.trade_log.append(trade_record)
            self._save_trade_log()
            
            # 顯示下單資訊
            if odd_lots > 0:
                print(f"  💰 賣出 {symbol}: {qty}股 @ ${order_price:.2f}")
                print(f"     整張: {round_lots}股, 零股: {odd_lots}股")
            else:
                print(f"  💰 賣出 {symbol}: {qty}股 @ ${order_price:.2f}")
            print(f"     損益: ${net_pnl:+,.0f} | 原因: {signal.get('reason', '')}")
            
            return {
                'success': True,
                'symbol': symbol,
                'qty': qty,
                'price': order_price,
                'proceeds': net_proceeds,
                'pnl': net_pnl,
                'reason': signal.get('reason', '')
            }
            
        else:
            # ============================================================
            # 實單模式：使用智慧下單（自動拆分整張與零股）
            # ============================================================
            results = self._smart_place_order(
                symbol=symbol,
                action='sell',
                price=order_price,
                qty=qty
            )
            
            # 檢查是否全部成功
            all_success = all(r.get('success', False) for r in results)
            total_filled_qty = sum(r.get('qty', 0) for r in results if r.get('success'))
            
            if all_success and total_filled_qty > 0:
                print(f"  💰 賣出委託 {symbol}: {total_filled_qty}股 @ ${order_price:.2f}")
                return {
                    'success': True,
                    'symbol': symbol,
                    'qty': total_filled_qty,
                    'price': order_price,
                    'orders': results,
                    'pnl': net_pnl,
                    'reason': signal.get('reason', '')
                }
            else:
                # 部分成功或全部失敗
                failed_msgs = [r.get('message', '') for r in results if not r.get('success')]
                return {
                    'success': False,
                    'symbol': symbol,
                    'partial_success': total_filled_qty > 0,
                    'filled_qty': total_filled_qty,
                    'message': '; '.join(failed_msgs) or '下單失敗'
                }
    
    # ========================================================================
    # v4.4.6 新增：智慧下單（自動拆分整張與零股）
    # ========================================================================
    
    def _calculate_order_qty(self, price: float, target_amount: float = None) -> int:
        """
        計算可買股數
        
        v4.4.6 新增：根據資金和股價計算最佳買進股數
        
        Args:
            price: 股價
            target_amount: 目標金額（預設使用可用預算）
        
        Returns:
            int: 建議買進股數
        """
        if price <= 0:
            return 0
        
        # 計算可用預算
        available_budget = self.get_available_budget()
        
        # 單一部位上限
        max_position_value = AutoTraderConfig.MAX_INVESTMENT_BUDGET * AutoTraderConfig.MAX_SINGLE_POSITION_PCT
        
        # 實際可用金額
        if target_amount:
            budget = min(target_amount, available_budget, max_position_value)
        else:
            budget = min(available_budget, max_position_value)
        
        # 計算可買股數
        max_qty = int(budget / price)
        
        # 決定是否只買整張
        if AutoTraderConfig.ENABLE_ODD_LOT:
            # 啟用零股：直接返回可買股數
            return max_qty
        else:
            # 不啟用零股：向下取整到 1000 股
            return (max_qty // 1000) * 1000
    
    def _smart_place_order(self, symbol: str, action: str, price: float, qty: int) -> List[Dict]:
        """
        智慧下單：自動拆分整張與零股
        
        v4.4.6 新增：
        - 整張部分使用 ROD（當日有效）+ 一般交易
        - 零股部分使用 盤中零股交易
        
        Args:
            symbol: 股票代碼
            action: 'buy' 或 'sell'
            price: 下單價格
            qty: 總股數
        
        Returns:
            list: 下單結果列表
        """
        results = []
        
        # 計算整張與零股
        round_lots = (qty // 1000) * 1000  # 整張部分
        odd_lots = qty % 1000               # 零股部分
        
        action_name = "買進" if action == 'buy' else "賣出"
        
        # 1. 整張下單（一般交易 + ROD）
        if round_lots > 0:
            print(f"  📦 {action_name}整張: {symbol} {round_lots}股 (ROD)")
            
            if self.mode == AutoTraderConfig.MODE_SIMULATION:
                # 模擬模式：直接記錄
                results.append({
                    'success': True,
                    'type': 'round_lot',
                    'symbol': symbol,
                    'action': action,
                    'qty': round_lots,
                    'price': price
                })
            else:
                # 實單模式：呼叫 API
                res = self.trader.place_order(
                    symbol=symbol,
                    action=action,
                    price=price,
                    quantity=round_lots,
                    price_type='limit',
                    market_type='common',  # 一般交易
                    time_in_force='ROD'    # 整張用 ROD
                )
                res['type'] = 'round_lot'
                res['qty'] = round_lots
                results.append(res)
        
        # 2. 零股下單（盤中零股交易）
        if odd_lots > 0 and AutoTraderConfig.ENABLE_ODD_LOT:
            print(f"  🧩 {action_name}零股: {symbol} {odd_lots}股 (盤中零股)")
            
            if self.mode == AutoTraderConfig.MODE_SIMULATION:
                # 模擬模式：直接記錄
                results.append({
                    'success': True,
                    'type': 'odd_lot',
                    'symbol': symbol,
                    'action': action,
                    'qty': odd_lots,
                    'price': price
                })
            else:
                # 實單模式：呼叫 API（盤中零股）
                res = self.trader.place_order(
                    symbol=symbol,
                    action=action,
                    price=price,
                    quantity=odd_lots,
                    price_type='limit',
                    market_type='odd',  # 盤中零股
                    time_in_force=AutoTraderConfig.ODD_LOT_TIME_IN_FORCE
                )
                res['type'] = 'odd_lot'
                res['qty'] = odd_lots
                results.append(res)
        
        return results
    
    def _execute_buy(self, signal: Dict) -> Dict:
        """
        執行買進
        
        v4.4.6 更新：
        - 使用智慧下單，自動拆分整張與零股
        - 放寬最小下單門檻（啟用零股時可小於 1000 股）
        
        v4.4.7 更新：
        - 股價 1000 元以下，強制不零股交易（買整張）
        
        Args:
            signal: 買進訊號
        
        Returns:
            dict: 執行結果
        """
        symbol = signal.get('symbol')
        current_price = signal.get('current_price', 0)
        
        if current_price <= 0:
            return {'success': False, 'symbol': symbol, 'message': '無效價格'}
        
        # v4.4.5：下單價格優化（讓利確保成交）
        order_price = round(current_price * AutoTraderConfig.BUY_PRICE_PREMIUM, 2)
        
        # ============================================================
        # v4.4.7 新增：股價 1000 元以下，強制不零股交易
        # 原因：低價股零股交易成本較高，且流動性較差
        # ============================================================
        force_round_lot_only = order_price < 1000
        original_odd_lot_setting = AutoTraderConfig.ENABLE_ODD_LOT
        
        if force_round_lot_only and AutoTraderConfig.ENABLE_ODD_LOT:
            print(f"  ⚠️ 股價 ${order_price:.2f} < $1000，自動切換為整張交易")
            AutoTraderConfig.ENABLE_ODD_LOT = False
        
        try:
            # v4.4.6：使用智慧股數計算
            qty = self._calculate_order_qty(order_price)
            
            # 檢查最小下單數量
            if force_round_lot_only or not original_odd_lot_setting:
                # 強制整張或原本就不啟用零股：最小 1 張
                min_qty = AutoTraderConfig.MIN_ORDER_AMOUNT
            else:
                # 啟用零股：最小 1 股
                min_qty = AutoTraderConfig.MIN_ODD_LOT_AMOUNT
            
            if qty < min_qty:
                available_budget = self.get_available_budget()
                return {
                    'success': False,
                    'skipped': True,
                    'symbol': symbol,
                    'message': f'資金不足（可用預算:${available_budget:,.0f}，需要至少:${order_price * min_qty:,.0f}）'
                }
            
            # 計算成本（含手續費）
            order_value = qty * order_price
            commission = order_value * AutoTraderConfig.COMMISSION_RATE
            total_cost = order_value + commission
            
            if self.mode == AutoTraderConfig.MODE_SIMULATION:
                # ============================================================
                # 模擬模式：更新模擬帳戶
                # ============================================================
                if total_cost > self.sim_data['balance']:
                    return {
                        'success': False,
                        'skipped': True,
                        'symbol': symbol,
                        'message': f'餘額不足（餘額:${self.sim_data["balance"]:,.0f}，需要:${total_cost:,.0f}）'
                    }
                
                # 扣除餘額
                self.sim_data['balance'] -= total_cost
                
                # 新增持倉（成本價使用實際下單價格）
                self.sim_data['inventory'][symbol] = {
                    'qty': qty,
                    'cost': order_price,
                    'buy_date': datetime.datetime.now().isoformat(),
                    'reason': signal.get('reason', '')
                }
                
                self._save_simulation()
                
                # 記錄交易
                round_lots = (qty // 1000) * 1000
                odd_lots = qty % 1000
                
                trade_record = {
                    'time': datetime.datetime.now().isoformat(),
                    'action': 'BUY',
                    'symbol': symbol,
                    'qty': qty,
                    'round_lots': round_lots,
                    'odd_lots': odd_lots,
                    'price': order_price,
                    'cost': total_cost,
                    'reason': signal.get('reason', ''),
                    'force_round_lot': force_round_lot_only  # v4.4.7 記錄是否強制整張
                }
                self.trade_log.append(trade_record)
                self._save_trade_log()
                
                # 顯示下單資訊
                if odd_lots > 0:
                    print(f"  🛒 買進 {symbol}: {qty}股 @ ${order_price:.2f}")
                    print(f"     整張: {round_lots}股, 零股: {odd_lots}股")
                else:
                    print(f"  🛒 買進 {symbol}: {qty}股 @ ${order_price:.2f}")
                    if force_round_lot_only:
                        print(f"     （低價股強制整張交易）")
                print(f"     成本: ${total_cost:,.0f} | 原因: {signal.get('reason', '')}")
                
                return {
                    'success': True,
                    'symbol': symbol,
                    'qty': qty,
                    'price': order_price,
                    'cost': total_cost,
                    'reason': signal.get('reason', '')
                }
            
            else:
                # ============================================================
                # 實單模式：使用智慧下單（自動拆分整張與零股）
                # ============================================================
                results = self._smart_place_order(
                    symbol=symbol,
                    action='buy',
                    price=order_price,
                    qty=qty
                )
                
                # 檢查是否全部成功
                all_success = all(r.get('success', False) for r in results)
                total_filled_qty = sum(r.get('qty', 0) for r in results if r.get('success'))
                
                if all_success and total_filled_qty > 0:
                    print(f"  🛒 買進委託 {symbol}: {total_filled_qty}股 @ ${order_price:.2f}")
                    if force_round_lot_only:
                        print(f"     （低價股強制整張交易）")
                    return {
                        'success': True,
                        'symbol': symbol,
                        'qty': total_filled_qty,
                        'price': order_price,
                        'orders': results,
                        'reason': signal.get('reason', '')
                    }
                else:
                    # 部分成功或全部失敗
                    failed_msgs = [r.get('message', '') for r in results if not r.get('success')]
                    return {
                        'success': False,
                        'symbol': symbol,
                        'partial_success': total_filled_qty > 0,
                        'filled_qty': total_filled_qty,
                        'message': '; '.join(failed_msgs) or '下單失敗'
                    }
        
        finally:
            # v4.4.7：恢復原本的零股交易設定
            if force_round_lot_only:
                AutoTraderConfig.ENABLE_ODD_LOT = original_odd_lot_setting
    
    def _save_trade_log(self):
        """儲存交易紀錄"""
        try:
            # 載入現有紀錄
            existing = []
            if os.path.exists(AutoTraderConfig.TRADE_LOG_FILE):
                with open(AutoTraderConfig.TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            
            # 合併新紀錄
            all_records = existing + self.trade_log
            
            with open(AutoTraderConfig.TRADE_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_records, f, ensure_ascii=False, indent=2)
            
            self.trade_log = []  # 清空暫存
        except Exception as e:
            print(f"[AutoTrader] 儲存交易紀錄失敗: {e}")
    
    # ========================================================================
    # 即時損益監控
    # ========================================================================
    
    def _calculate_pnl(self, analysis_results: List[Dict] = None) -> Dict:
        """
        計算當前損益
        
        Args:
            analysis_results: 分析結果（用於取得現價），None 則使用快取
        
        Returns:
            dict: 損益資訊
        """
        inventory = self.get_inventory()
        balance = self.get_balance()
        
        # 建立現價對照表
        price_map = {}
        if analysis_results:
            for r in analysis_results:
                symbol = r.get('symbol', '')
                price_map[symbol] = r.get('current_price', 0)
        
        # 計算持倉市值與損益
        total_market_value = 0
        total_cost_basis = 0
        unrealized_pnl = 0
        positions = []
        
        for symbol, pos in inventory.items():
            qty = pos.get('qty', 0)
            cost = pos.get('cost', 0)
            
            # 取得現價（優先使用分析結果，否則使用成本價估算）
            current_price = price_map.get(symbol, cost)
            
            market_value = qty * current_price
            cost_basis = qty * cost
            pnl = market_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            total_market_value += market_value
            total_cost_basis += cost_basis
            unrealized_pnl += pnl
            
            positions.append({
                'symbol': symbol,
                'qty': qty,
                'cost': cost,
                'current_price': current_price,
                'market_value': market_value,
                'pnl': pnl,
                'pnl_pct': pnl_pct
            })
        
        # 計算總資產與報酬率
        total_assets = balance + total_market_value
        
        if self.mode == AutoTraderConfig.MODE_SIMULATION:
            initial_capital = self.sim_data.get('initial_capital', self.initial_capital)
        else:
            initial_capital = self.initial_capital or total_assets
        
        total_return = total_assets - initial_capital
        total_return_pct = (total_return / initial_capital * 100) if initial_capital > 0 else 0
        
        return {
            'balance': balance,
            'total_market_value': total_market_value,
            'total_cost_basis': total_cost_basis,
            'total_assets': total_assets,
            'initial_capital': initial_capital,
            'unrealized_pnl': unrealized_pnl,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'positions': positions
        }
    
    def report_status(self, analysis_results: List[Dict] = None):
        """
        顯示即時損益報告
        
        Args:
            analysis_results: 分析結果（用於取得現價）
        """
        pnl = self._calculate_pnl(analysis_results)
        
        print("\n" + "=" * 60)
        print("📊 帳戶狀態報告")
        print("=" * 60)
        
        # 模式標示
        mode_str = "🔬 模擬模式" if self.mode == AutoTraderConfig.MODE_SIMULATION else "💰 實單模式"
        print(f"模式：{mode_str}")
        print(f"時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        
        # 資產概況
        print(f"初始本金：${pnl['initial_capital']:>15,.0f}")
        print(f"現金餘額：${pnl['balance']:>15,.0f}")
        print(f"持倉市值：${pnl['total_market_value']:>15,.0f}")
        print(f"總資產　：${pnl['total_assets']:>15,.0f}")
        print("-" * 60)
        
        # 損益
        pnl_color = "🟢" if pnl['unrealized_pnl'] >= 0 else "🔴"
        return_color = "🟢" if pnl['total_return'] >= 0 else "🔴"
        
        print(f"未實現損益：{pnl_color} ${pnl['unrealized_pnl']:>+13,.0f}")
        print(f"總報酬　　：{return_color} ${pnl['total_return']:>+13,.0f} ({pnl['total_return_pct']:+.2f}%)")
        print("-" * 60)
        
        # 持倉明細
        if pnl['positions']:
            print("📋 持倉明細：")
            for pos in pnl['positions']:
                pos_color = "🟢" if pos['pnl'] >= 0 else "🔴"
                print(f"  {pos['symbol']}: {pos['qty']}股 @ ${pos['cost']:.2f}")
                print(f"    現價: ${pos['current_price']:.2f} | {pos_color} 損益: ${pos['pnl']:+,.0f} ({pos['pnl_pct']:+.1f}%)")
        else:
            print("📋 持倉明細：（空倉）")
        
        print("=" * 60)
        
        # 更新模擬數據中的市值（用於下次啟動時參考）
        if self.mode == AutoTraderConfig.MODE_SIMULATION and analysis_results:
            for pos in pnl['positions']:
                symbol = pos['symbol']
                if symbol in self.sim_data['inventory']:
                    self.sim_data['inventory'][symbol]['last_price'] = pos['current_price']
            self._save_simulation()
    
    # ========================================================================
    # 主執行迴圈
    # ========================================================================
    
    def run_once(self) -> Dict:
        """
        執行一次掃描與交易
        
        Returns:
            dict: 執行結果
        """
        print(f"\n{'='*60}")
        print(f"🚀 AutoTrader 執行掃描")
        print(f"   模式：{'模擬' if self.mode == AutoTraderConfig.MODE_SIMULATION else '實單'}")
        print(f"   時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        # 1. 掃描分析
        analysis_results = self.scan_watchlist()
        
        if not analysis_results:
            print("[AutoTrader] 無可分析的股票")
            return {'status': 'no_data'}
        
        # 2. 評估訊號
        buy_signals, sell_signals = self.evaluate_signals(analysis_results)
        
        print(f"\n📡 訊號摘要：")
        print(f"  買進訊號: {len(buy_signals)} 檔")
        print(f"  賣出訊號: {len(sell_signals)} 檔")
        
        # 3. 執行交易
        if buy_signals or sell_signals:
            print(f"\n💼 執行交易...")
            trade_results = self.execute_trades(buy_signals, sell_signals)
            
            print(f"\n📝 交易結果：")
            print(f"  成功買進: {len(trade_results['executed_buys'])} 筆")
            print(f"  成功賣出: {len(trade_results['executed_sells'])} 筆")
            print(f"  跳過: {len(trade_results['skipped'])} 筆")
            print(f"  錯誤: {len(trade_results['errors'])} 筆")
        else:
            trade_results = {'executed_buys': [], 'executed_sells': [], 'skipped': [], 'errors': []}
            print(f"\n⏸️ 無交易訊號，維持現狀")
        
        # 4. 報告狀態
        self.report_status(analysis_results)
        
        return {
            'status': 'success',
            'analysis_count': len(analysis_results),
            'buy_signals': len(buy_signals),
            'sell_signals': len(sell_signals),
            'trades': trade_results
        }
    
    def run(self, interval: int = None):
        """
        啟動自動交易迴圈
        
        Args:
            interval: 掃描間隔（秒），None 則使用預設值
        """
        interval = interval or AutoTraderConfig.SCAN_INTERVAL
        self.is_running = True
        
        print(f"\n{'='*60}")
        print(f"🤖 AutoTrader 啟動")
        print(f"   模式：{'模擬' if self.mode == AutoTraderConfig.MODE_SIMULATION else '實單'}")
        print(f"   掃描間隔：{interval} 秒")
        print(f"   按 Ctrl+C 停止")
        print(f"{'='*60}")
        
        try:
            while self.is_running:
                self.run_once()
                
                print(f"\n⏳ 等待 {interval} 秒後進行下一次掃描...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(f"\n\n🛑 AutoTrader 已停止")
            self.is_running = False
    
    def stop(self):
        """停止自動交易"""
        self.is_running = False
        print("[AutoTrader] 正在停止...")


# ============================================================================
# 主程式入口
# ============================================================================

def main():
    """主程式入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AutoTrader 自動交易程式')
    parser.add_argument('--mode', type=str, default='SIMULATION',
                        choices=['SIMULATION', 'LIVE'],
                        help='運作模式：SIMULATION(模擬) 或 LIVE(實單)')
    parser.add_argument('--capital', type=float, default=1000000,
                        help='初始資金（僅模擬模式）')
    parser.add_argument('--interval', type=int, default=300,
                        help='掃描間隔（秒）')
    parser.add_argument('--once', action='store_true',
                        help='只執行一次（不進入迴圈）')
    
    args = parser.parse_args()
    
    # 創建交易器
    trader = AutoTrader(mode=args.mode, initial_capital=args.capital)
    
    # 實單模式需要登入
    if args.mode == 'LIVE':
        print("實單模式需要登入，請提供認證資訊：")
        user_id = input("身分證字號: ")
        password = input("密碼: ")
        cert_path = input("憑證路徑: ")
        cert_password = input("憑證密碼: ")
        
        result = trader.login(user_id, password, cert_path, cert_password)
        if not result['success']:
            print(f"登入失敗: {result['message']}")
            return
    
    # 執行
    if args.once:
        trader.run_once()
    else:
        trader.run(interval=args.interval)


if __name__ == '__main__':
    main()
