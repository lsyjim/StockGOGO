"""
fubon_trading.py - 富邦證券 API 交易模組 (修正版)
=====================================
修正內容：
1. 登入後自動載入庫存明細
2. 量化分析摘要整合主視窗分析結果
3. 下單頁面選項全面中文化
4. 庫存明細新增刷新按鈕（使用富邦API）
5. 改善整體使用體驗

使用前請先：
1. 下載 SDK: https://www.fbs.com.tw/TradeAPI/docs/download/download-sdk
2. 安裝: pip install fubon_neo-x.x.x-cp37-abi3-xxxxx.whl
3. 申請憑證: https://www.fbs.com.tw/Certificate/Management
"""

import os
import json
import threading
import time
from datetime import datetime

# 嘗試導入富邦 SDK
try:
    from fubon_neo.sdk import FubonSDK, Order
    from fubon_neo.constant import (
        TimeInForce, OrderType, PriceType, 
        MarketType, BSAction
    )
    FUBON_SDK_AVAILABLE = True
except ImportError:
    FUBON_SDK_AVAILABLE = False
    print("警告：未安裝 fubon_neo SDK")
    print("請從 https://www.fbs.com.tw/TradeAPI/docs/download/download-sdk 下載安裝")


class FubonTrader:
    """
    富邦證券交易類別
    
    功能：
    - 登入/登出
    - 下單（買進/賣出）
    - 查詢委託單
    - 查詢庫存
    - 即時行情訂閱
    """
    
    def __init__(self):
        self.sdk = None
        self.accounts = None
        self.active_account = None
        self.is_logged_in = False
        self.realtime_data = {}
        self.ws_client = None
        self.rest_client = None
        self._callbacks = {}
        
    # ============================================================================
    # 登入/登出
    # ============================================================================
    
    def login(self, user_id, password, cert_path, cert_password):
        """
        登入富邦證券 API
        
        參數：
            user_id: 身分證字號
            password: 登入密碼
            cert_path: 憑證檔案路徑 (.pfx 或 .p12)
            cert_password: 憑證密碼
            
        返回：
            dict: {'success': bool, 'message': str, 'accounts': list}
        """
        if not FUBON_SDK_AVAILABLE:
            return {
                'success': False, 
                'message': '未安裝 fubon_neo SDK，請先安裝',
                'accounts': []
            }
        
        # Debug 輸出（資安：一律不印密碼明文，只印長度供排錯）
        print(f"[FubonTrader.login] 接收到的參數:")
        print(f"  user_id: {user_id}")
        print(f"  password: ***（長度 {len(password or '')}）")
        print(f"  cert_path: {cert_path}")
        print(f"  cert_password: ***（長度 {len(cert_password or '')}）")
        
        try:
            self.sdk = FubonSDK()
            
            print(f"[FubonTrader.login] 呼叫 sdk.login()...")
            result = self.sdk.login(user_id, password, cert_path, cert_password)
            
            print(f"[FubonTrader.login] SDK 返回: is_success={result.is_success}, message={result.message}")
            
            if result.is_success:
                self.accounts = result.data
                self.active_account = self.accounts[0] if self.accounts else None
                self.is_logged_in = True
                
                # 初始化行情連線
                self.sdk.init_realtime()
                self.rest_client = self.sdk.marketdata.rest_client.stock
                self.ws_client = self.sdk.marketdata.websocket_client.stock
                
                # v4.4.7 新增：初始化 DataSourceManager，讓全系統使用富邦 API
                try:
                    from data_fetcher import DataSourceManager
                    DataSourceManager.initialize(self.sdk)
                    print("[FubonTrader] DataSourceManager 已切換至富邦 API")
                except Exception as e:
                    print(f"[FubonTrader] DataSourceManager 初始化失敗: {e}")
                
                account_info = []
                for acc in self.accounts:
                    account_info.append({
                        'account': getattr(acc, 'account', str(acc)),
                        'account_type': getattr(acc, 'account_type', 'unknown')
                    })
                
                return {
                    'success': True,
                    'message': '登入成功',
                    'accounts': account_info
                }
            else:
                return {
                    'success': False,
                    'message': f'登入失敗: {result.message}',
                    'accounts': []
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'登入錯誤: {str(e)}',
                'accounts': []
            }
    
    def logout(self):
        """登出"""
        if self.sdk and self.is_logged_in:
            try:
                result = self.sdk.logout()
                self.is_logged_in = False
                self.accounts = None
                self.active_account = None
                return {'success': True, 'message': '已登出'}
            except Exception as e:
                return {'success': False, 'message': f'登出錯誤: {str(e)}'}
        return {'success': False, 'message': '尚未登入'}
    
    # ============================================================================
    # 下單功能
    # ============================================================================
    
    def place_order(self, symbol, action, price, quantity, 
                    price_type='limit', market_type='common',
                    time_in_force='ROD', user_def=''):
        """
        下單
        
        參數：
            symbol: 股票代號 (例如 '2330')
            action: 'buy' 或 'sell'
            price: 價格 (市價單時可為 None)
            quantity: 數量 (股數，1張=1000股)
            price_type: 'limit'(限價) / 'market'(市價) / 'reference'(平盤)
            market_type: 'common'(一般) / 'odd'(盤中零股) / 'fixing'(定盤)
            time_in_force: 'ROD' / 'IOC' / 'FOK'
            user_def: 自訂欄位
            
        返回：
            dict: 下單結果
        """
        if not self.is_logged_in:
            return {'success': False, 'message': '尚未登入'}
        
        if not self.active_account:
            return {'success': False, 'message': '無可用帳戶'}
        
        try:
            # 轉換參數
            bs_action = BSAction.Buy if action.lower() == 'buy' else BSAction.Sell
            
            # 價格類型（支援中英文）
            price_type_map = {
                'limit': PriceType.Limit,
                'market': PriceType.Market,
                'reference': PriceType.Reference,
                '限價': PriceType.Limit,
                '市價': PriceType.Market,
                '平盤價': PriceType.Reference
            }
            pt = price_type_map.get(price_type.lower() if isinstance(price_type, str) else price_type, PriceType.Limit)
            
            # 市場類型（支援中英文）
            market_type_map = {
                'common': MarketType.Common,
                'odd': MarketType.IntradayOdd,
                'fixing': MarketType.Fixing,
                '一般': MarketType.Common,
                '盤中零股': MarketType.IntradayOdd,
                '定盤': MarketType.Fixing
            }
            mt = market_type_map.get(market_type.lower() if isinstance(market_type, str) else market_type, MarketType.Common)
            
            # 委託時效（支援中英文）
            tif_map = {
                'ROD': TimeInForce.ROD,
                'IOC': TimeInForce.IOC,
                'FOK': TimeInForce.FOK,
                '當日有效': TimeInForce.ROD,
                '立即成交否則取消': TimeInForce.IOC,
                '全部成交否則取消': TimeInForce.FOK
            }
            tif = tif_map.get(time_in_force.upper() if isinstance(time_in_force, str) else time_in_force, TimeInForce.ROD)
            
            # 建立委託單
            order = Order(
                buy_sell=bs_action,
                symbol=symbol,
                price=str(price) if price else None,
                quantity=int(quantity),
                market_type=mt,
                price_type=pt,
                time_in_force=tif,
                order_type=OrderType.Stock,
                user_def=user_def
            )
            
            # 下單
            result = self.sdk.stock.place_order(self.active_account, order)
            
            if result.is_success:
                order_data = result.data
                return {
                    'success': True,
                    'message': '下單成功',
                    'order_no': getattr(order_data, 'order_no', ''),
                    'data': str(order_data)
                }
            else:
                return {
                    'success': False,
                    'message': f'下單失敗: {result.message}'
                }
                
        except Exception as e:
            return {'success': False, 'message': f'下單錯誤: {str(e)}'}
    
    def cancel_order(self, order_no):
        """
        取消委託單
        
        參數：
            order_no: 委託書號
        """
        if not self.is_logged_in:
            return {'success': False, 'message': '尚未登入'}
        
        try:
            # 先取得委託單
            orders = self.sdk.stock.get_order_results(self.active_account)
            target_order = None
            
            for order in orders.data:
                if order.order_no == order_no:
                    target_order = order
                    break
            
            if not target_order:
                return {'success': False, 'message': f'找不到委託單: {order_no}'}
            
            result = self.sdk.stock.cancel_order(self.active_account, target_order)
            
            if result.is_success:
                return {'success': True, 'message': '取消成功'}
            else:
                return {'success': False, 'message': f'取消失敗: {result.message}'}
                
        except Exception as e:
            return {'success': False, 'message': f'取消錯誤: {str(e)}'}
    
    # ============================================================================
    # 帳務查詢
    # ============================================================================
    
    def get_order_results(self):
        """取得今日委託單"""
        if not self.is_logged_in:
            return {'success': False, 'message': '尚未登入', 'data': []}
        
        try:
            result = self.sdk.stock.get_order_results(self.active_account)
            
            orders = []
            for order in result.data:
                orders.append({
                    'order_no': getattr(order, 'order_no', ''),
                    'symbol': getattr(order, 'stock_no', ''),
                    'buy_sell': str(getattr(order, 'buy_sell', '')),
                    'price': getattr(order, 'price', 0),
                    'quantity': getattr(order, 'quantity', 0),
                    'filled_qty': getattr(order, 'filled_qty', 0),
                    'status': getattr(order, 'status', 0),
                    'time': getattr(order, 'order_time', '')
                })
            
            return {'success': True, 'message': '', 'data': orders}
            
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': []}
    
    def get_inventories(self):
        """
        取得庫存 (v4.3.8 修正版)
        
        修正內容：
        1. 加入零股 (odd) 處理
        2. 從行情 API 取得股票名稱
        3. 確保股票代號為字串格式（保留前導0）
        
        API 路徑：sdk.accounting.inventories(account)
        官方文檔：https://www.fbs.com.tw/TradeAPI/docs/trading/library/python/accountManagement/Inventories
        """
        if not self.is_logged_in:
            return {'success': False, 'message': '尚未登入', 'data': []}
        
        try:
            # v4.3.7 修正：使用正確的 API 路徑
            result = self.sdk.accounting.inventories(self.active_account)
            
            print(f"[get_inventories] is_success={result.is_success}, message={result.message}")
            
            if not result.is_success:
                return {'success': False, 'message': result.message or '查詢失敗', 'data': []}
            
            inventories = []
            
            # 同時取得未實現損益來獲取成本和損益資訊
            unrealized_data = {}
            try:
                unrealized_result = self.sdk.accounting.unrealized_gains_and_loses(self.active_account)
                print(f"[get_inventories] unrealized: is_success={unrealized_result.is_success}")
                if unrealized_result.is_success and unrealized_result.data:
                    for item in unrealized_result.data:
                        stock_no = str(getattr(item, 'stock_no', ''))
                        if stock_no:
                            unrealized_data[stock_no] = {
                                'cost_price': getattr(item, 'cost_price', 0),
                                'profit': getattr(item, 'unrealized_profit', 0),
                                'loss': getattr(item, 'unrealized_loss', 0),
                                'today_qty': getattr(item, 'today_qty', 0)
                            }
            except Exception as e:
                print(f"[get_inventories] 取得未實現損益失敗: {e}")
            
            # 股票名稱快取
            stock_names = {}
            
            def get_stock_name(stock_no):
                """從行情 API 取得股票名稱"""
                if stock_no in stock_names:
                    return stock_names[stock_no]
                
                name = ''
                try:
                    if self.rest_client:
                        quote = self.rest_client.intraday.quote(symbol=stock_no)
                        if quote:
                            name = quote.get('name', '') or ''
                except Exception as e:
                    print(f"[get_stock_name] {stock_no} 失敗: {e}")
                
                stock_names[stock_no] = name
                return name
            
            # 處理庫存資料
            if result.data:
                for inv in result.data:
                    # 確保股票代號為字串（保留前導0）
                    stock_no = str(getattr(inv, 'stock_no', ''))
                    
                    # 整股數量
                    today_qty = getattr(inv, 'today_qty', 0) or 0
                    
                    # v4.3.8：處理零股
                    odd_data = getattr(inv, 'odd', None)
                    odd_qty = 0
                    if odd_data:
                        odd_qty = getattr(odd_data, 'today_qty', 0) or 0
                    
                    # 總數量 = 整股 + 零股
                    total_qty = today_qty + odd_qty
                    
                    # 跳過數量為 0 的項目
                    if total_qty == 0:
                        continue
                    
                    # 從未實現損益取得成本和損益
                    unrealized = unrealized_data.get(stock_no, {})
                    cost_price = unrealized.get('cost_price', 0) or 0
                    profit = unrealized.get('profit', 0) or 0
                    loss = unrealized.get('loss', 0) or 0
                    pnl = profit - loss
                    
                    # 嘗試取得現價和名稱
                    current_price = 0
                    stock_name = ''
                    try:
                        if self.rest_client:
                            quote = self.rest_client.intraday.quote(symbol=stock_no)
                            if quote:
                                current_price = quote.get('closePrice', 0) or quote.get('lastPrice', 0) or 0
                                stock_name = quote.get('name', '') or ''
                    except Exception as e:
                        print(f"[get_inventories] 取得 {stock_no} 報價失敗: {e}")
                    
                    # 如果無法取得現價，從成本和損益推算
                    if current_price == 0 and cost_price > 0 and total_qty > 0:
                        current_price = round(pnl / total_qty + cost_price, 2)
                    
                    # 計算報酬率
                    if cost_price > 0 and total_qty > 0:
                        total_cost = cost_price * total_qty
                        pnl_percent = (pnl / total_cost) * 100 if total_cost > 0 else 0
                    else:
                        pnl_percent = 0
                    
                    # 標記是否含零股
                    qty_display = total_qty
                    if odd_qty > 0 and today_qty > 0:
                        # 有整股也有零股
                        qty_note = f"({today_qty}+{odd_qty})"
                    elif odd_qty > 0:
                        # 只有零股
                        qty_note = "(零股)"
                    else:
                        qty_note = ""
                    
                    inventories.append({
                        'symbol': stock_no,  # 確保為字串
                        'name': stock_name,
                        'qty': total_qty,
                        'qty_note': qty_note,  # 零股標記
                        'regular_qty': today_qty,
                        'odd_qty': odd_qty,
                        'price_avg': cost_price,
                        'price_now': current_price,
                        'pnl': pnl,
                        'pnl_percent': round(pnl_percent, 2)
                    })
            
            return {'success': True, 'message': '', 'data': inventories}
            
        except AttributeError as e:
            print(f"[get_inventories] AttributeError: {e}")
            return self._get_inventories_fallback()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e), 'data': []}
    
    def _get_inventories_fallback(self):
        """庫存查詢的替代方案（SDK 版本相容）"""
        try:
            # 嘗試不同的 API 路徑
            possible_methods = [
                ('sdk.accounting.inventories', lambda: self.sdk.accounting.inventories(self.active_account)),
                ('sdk.stock.inventories', lambda: self.sdk.stock.inventories(self.active_account)),
            ]
            
            for name, method in possible_methods:
                try:
                    print(f"[_get_inventories_fallback] 嘗試 {name}")
                    result = method()
                    if hasattr(result, 'is_success') and result.is_success:
                        inventories = []
                        for inv in result.data:
                            # 嘗試多種可能的欄位名稱
                            stock_no = (getattr(inv, 'stock_no', None) or 
                                       getattr(inv, 'stk_no', None) or 
                                       getattr(inv, 'symbol', ''))
                            qty = (getattr(inv, 'today_qty', None) or 
                                  getattr(inv, 'qty', 0))
                            
                            if qty and qty > 0:
                                inventories.append({
                                    'symbol': stock_no,
                                    'name': getattr(inv, 'stock_name', '') or getattr(inv, 'stk_na', ''),
                                    'qty': qty,
                                    'price_avg': getattr(inv, 'cost_price', 0) or getattr(inv, 'price_avg', 0),
                                    'price_now': 0,
                                    'pnl': 0,
                                    'pnl_percent': 0
                                })
                        return {'success': True, 'message': '', 'data': inventories}
                except Exception as e:
                    print(f"[_get_inventories_fallback] {name} 失敗: {e}")
                    continue
            
            return {'success': False, 'message': 'SDK 版本不支援此 API', 'data': []}
            
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': []}
    
    # ============================================================================
    # 行情查詢
    # ============================================================================
    
    def get_quote(self, symbol):
        """
        取得即時報價快照
        
        參數：
            symbol: 股票代號
            
        返回：
            dict: 報價資訊
        """
        if not self.is_logged_in or not self.rest_client:
            return {'success': False, 'message': '尚未登入或行情未初始化'}
        
        try:
            result = self.rest_client.intraday.quote(symbol=symbol)
            
            return {
                'success': True,
                'data': {
                    'symbol': result.get('symbol', symbol),
                    'name': result.get('name', ''),
                    'open': result.get('openPrice', 0),
                    'high': result.get('highPrice', 0),
                    'low': result.get('lowPrice', 0),
                    'close': result.get('closePrice', 0),
                    'volume': result.get('tradeVolume', 0),
                    'change': result.get('change', 0),
                    'change_percent': result.get('changePercent', 0),
                    'bid_price': result.get('bidPrice', 0),
                    'ask_price': result.get('askPrice', 0),
                    'last_updated': result.get('lastUpdated', 0)
                }
            }
            
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def get_market_snapshot(self, market='TSE'):
        """
        取得市場快照
        
        參數：
            market: 'TSE'(上市) / 'OTC'(上櫃)
        """
        if not self.is_logged_in or not self.rest_client:
            return {'success': False, 'message': '尚未登入'}
        
        try:
            result = self.rest_client.snapshot.quotes(market=market)
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def subscribe_realtime(self, symbols, callback):
        """
        訂閱即時行情 (WebSocket)
        
        參數：
            symbols: 股票代號列表 ['2330', '2317']
            callback: 回調函數 callback(data)
        """
        if not self.is_logged_in or not self.ws_client:
            return {'success': False, 'message': '尚未登入'}
        
        try:
            def handle_message(message):
                data = json.loads(message)
                if data.get('event') == 'data':
                    callback(data.get('data', {}))
            
            self.ws_client.on('message', handle_message)
            self.ws_client.connect()
            
            # 訂閱
            for symbol in symbols:
                self.ws_client.subscribe({
                    'channel': ['trades', 'books'],
                    'symbol': symbol
                })
            
            return {'success': True, 'message': f'已訂閱 {len(symbols)} 檔股票'}
            
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def unsubscribe_realtime(self, symbols):
        """取消訂閱即時行情"""
        if not self.ws_client:
            return {'success': False, 'message': '尚未連線'}
        
        try:
            for symbol in symbols:
                self.ws_client.unsubscribe({
                    'channel': ['trades', 'books'],
                    'symbol': symbol
                })
            return {'success': True, 'message': '已取消訂閱'}
        except Exception as e:
            return {'success': False, 'message': str(e)}


# ============================================================================
# 下單對話框 (GUI) - 修正版
# ============================================================================

def create_order_dialog(parent, symbol='', trader=None):
    """
    建立下單對話框（修正版）
    
    修正內容：
    1. 登入後自動載入庫存明細
    2. 量化分析摘要整合主視窗分析結果
    3. 下單頁面選項全面中文化
    4. 庫存明細新增刷新按鈕
    
    參數：
        parent: 父視窗
        symbol: 預設股票代號
        trader: FubonTrader 實例
    """
    import tkinter as tk
    from tkinter import ttk, messagebox
    from tkinter import filedialog
    
    dialog = tk.Toplevel(parent)
    dialog.title("📈 富邦證券下單")
    dialog.geometry("1150x800")
    dialog.resizable(True, True)
    dialog.minsize(950, 650)
    
    # 使對話框置中
    dialog.transient(parent)
    
    # 儲存最後一次的分析結果（用於量化分析摘要）
    last_analysis_result = {'data': None}
    
    # 主框架 - 左右分欄
    main_frame = ttk.Frame(dialog, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # 左側面板 (登入 + 下單)
    left_panel = ttk.Frame(main_frame, width=480)
    left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
    left_panel.pack_propagate(False)
    
    # 右側面板 (庫存 + 分析)
    right_panel = ttk.Frame(main_frame)
    right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    # ============================================================================
    # 左側：登入區域
    # ============================================================================
    login_frame = ttk.LabelFrame(left_panel, text="🔐 帳號登入", padding="10")
    login_frame.pack(fill=tk.X, pady=(0, 10))
    
    # 身分證字號
    id_row = ttk.Frame(login_frame)
    id_row.pack(fill=tk.X, pady=3)
    ttk.Label(id_row, text="身分證字號：", width=12).pack(side=tk.LEFT)
    user_id_var = tk.StringVar()
    user_id_entry = ttk.Entry(id_row, textvariable=user_id_var, width=25)
    user_id_entry.pack(side=tk.LEFT, padx=5)
    
    # 登入密碼
    pwd_row = ttk.Frame(login_frame)
    pwd_row.pack(fill=tk.X, pady=3)
    ttk.Label(pwd_row, text="登入密碼：", width=12).pack(side=tk.LEFT)
    password_var = tk.StringVar()
    password_entry = ttk.Entry(pwd_row, textvariable=password_var, width=25, show="*")
    password_entry.pack(side=tk.LEFT, padx=5)
    
    # 憑證路徑
    cert_row = ttk.Frame(login_frame)
    cert_row.pack(fill=tk.X, pady=3)
    ttk.Label(cert_row, text="憑證路徑：", width=12).pack(side=tk.LEFT)
    cert_path_var = tk.StringVar()
    cert_path_entry = ttk.Entry(cert_row, textvariable=cert_path_var, width=18)
    cert_path_entry.pack(side=tk.LEFT, padx=5)
    
    def browse_cert():
        path = filedialog.askopenfilename(
            title="選擇憑證檔案",
            filetypes=[("憑證檔案", "*.pfx *.p12"), ("所有檔案", "*.*")]
        )
        if path:
            cert_path_var.set(path)
    
    browse_btn = ttk.Button(cert_row, text="瀏覽", command=browse_cert, width=6)
    browse_btn.pack(side=tk.LEFT, padx=2)
    
    # 憑證密碼
    cert_pwd_row = ttk.Frame(login_frame)
    cert_pwd_row.pack(fill=tk.X, pady=3)
    ttk.Label(cert_pwd_row, text="憑證密碼：", width=12).pack(side=tk.LEFT)
    cert_password_var = tk.StringVar()
    cert_password_entry = ttk.Entry(cert_pwd_row, textvariable=cert_password_var, width=25, show="*")
    cert_password_entry.pack(side=tk.LEFT, padx=5)
    
    # 登入狀態
    status_var = tk.StringVar(value="⚪ 未登入")
    status_label = ttk.Label(login_frame, textvariable=status_var, 
                            font=('Microsoft JhengHei', 11, 'bold'))
    status_label.pack(pady=5)
    
    # 登入/登出按鈕
    login_btn_frame = ttk.Frame(login_frame)
    login_btn_frame.pack(fill=tk.X, pady=5)
    
    # 庫存明細相關元件（先宣告）
    inventory_tree = None
    total_pnl_label = None
    
    def refresh_inventory():
        """刷新庫存顯示（使用富邦API）"""
        nonlocal inventory_tree, total_pnl_label
        
        if inventory_tree is None:
            return
            
        if trader and trader.is_logged_in:
            # 顯示載入中
            for item in inventory_tree.get_children():
                inventory_tree.delete(item)
            inventory_tree.insert('', 'end', values=('載入中...', '', '', '', '', '', ''))
            dialog.update()
            
            result = trader.get_inventories()
            
            # 清空現有項目
            for item in inventory_tree.get_children():
                inventory_tree.delete(item)
            
            if result['success']:
                total_pnl = 0
                if not result['data']:
                    inventory_tree.insert('', 'end', values=('無庫存', '', '', '', '', '', ''))
                else:
                    for idx, inv in enumerate(result['data']):
                        pnl = float(inv.get('pnl', 0))
                        total_pnl += pnl
                        pnl_str = f"+{pnl:,.0f}" if pnl >= 0 else f"{pnl:,.0f}"
                        pnl_pct = inv.get('pnl_percent', 0)
                        pnl_pct_str = f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"
                        
                        # v4.4.1：使用 iid 保存原始股票代號（保留前導0）
                        symbol_str = str(inv.get('symbol', ''))
                        
                        # v4.3.8：顯示零股標記
                        qty = inv.get('qty', 0)
                        qty_note = inv.get('qty_note', '')
                        qty_str = f"{qty:,}{qty_note}" if qty_note else f"{qty:,}"
                        
                        # 股票名稱（若無則顯示 -）
                        name = inv.get('name', '') or '-'
                        
                        # 使用 iid 存儲原始股票代號，確保前導0不丟失
                        # iid 格式：inv_{index}_{symbol}
                        iid = f"inv_{idx}_{symbol_str}"
                        
                        inventory_tree.insert('', 'end', iid=iid, values=(
                            symbol_str,  # 顯示用
                            name,
                            qty_str,
                            f"{inv.get('price_avg', 0):.2f}",
                            f"{inv.get('price_now', 0):.2f}",
                            pnl_str,
                            pnl_pct_str
                        ))
                
                # 更新總損益
                if total_pnl_label:
                    pnl_color = 'green' if total_pnl >= 0 else 'red'
                    pnl_text = f"+{total_pnl:,.0f}" if total_pnl >= 0 else f"{total_pnl:,.0f}"
                    total_pnl_label.config(text=f"總損益：{pnl_text}", foreground=pnl_color)
            else:
                inventory_tree.insert('', 'end', values=(f'錯誤: {result["message"]}', '', '', '', '', '', ''))
                if total_pnl_label:
                    total_pnl_label.config(text="總損益：--", foreground='black')
        else:
            if inventory_tree:
                for item in inventory_tree.get_children():
                    inventory_tree.delete(item)
                inventory_tree.insert('', 'end', values=('請先登入', '', '', '', '', '', ''))
    
    def do_login():
        if not trader:
            messagebox.showerror("錯誤", "交易模組未初始化")
            return
        
        user_id = user_id_var.get().strip()
        password = password_var.get()
        cert_path = cert_path_var.get().strip()
        cert_pwd = cert_password_var.get()
        
        if not all([user_id, password, cert_path, cert_pwd]):
            messagebox.showerror("錯誤", "請填寫所有登入資訊")
            return
        
        # Debug（資安：不印密碼明文，只印長度）
        print(f"[DEBUG] ====== 登入參數 ======")
        print(f"[DEBUG] 身分證: {user_id}")
        print(f"[DEBUG] 密碼: *** (長度:{len(password)})")
        print(f"[DEBUG] 憑證路徑: {cert_path}")
        print(f"[DEBUG] 憑證密碼: *** (長度:{len(cert_pwd)})")
        print(f"[DEBUG] ====================")
        
        status_var.set("🔄 登入中...")
        dialog.update()
        
        result = trader.login(user_id, password, cert_path, cert_pwd)
        
        print(f"[DEBUG] 登入結果: {result}")
        
        if result['success']:
            status_var.set("🟢 已登入")
            messagebox.showinfo("成功", f"登入成功！\n帳戶數量: {len(result['accounts'])}")
            # 修正：確保登入後立即刷新庫存
            dialog.after(500, refresh_inventory)  # 延遲 500ms 確保 UI 已完成初始化
        else:
            status_var.set("🔴 登入失敗")
            messagebox.showerror("失敗", result['message'])
    
    def do_logout():
        if trader and trader.is_logged_in:
            result = trader.logout()
            if result['success']:
                status_var.set("⚪ 未登入")
                # 清空庫存
                if inventory_tree:
                    for item in inventory_tree.get_children():
                        inventory_tree.delete(item)
                if total_pnl_label:
                    total_pnl_label.config(text="總損益：--", foreground='black')
                messagebox.showinfo("成功", "已登出")
            else:
                messagebox.showerror("失敗", result['message'])
    
    login_btn = ttk.Button(login_btn_frame, text="登入", command=do_login, width=12)
    login_btn.pack(side=tk.LEFT, padx=5)
    logout_btn = ttk.Button(login_btn_frame, text="登出", command=do_logout, width=12)
    logout_btn.pack(side=tk.LEFT, padx=5)
    
    # ============================================================================
    # 左側：下單區域
    # ============================================================================
    order_frame = ttk.LabelFrame(left_panel, text="📝 委託下單", padding="10")
    order_frame.pack(fill=tk.X, pady=(0, 10))
    
    # 股票代號
    row1 = ttk.Frame(order_frame)
    row1.pack(fill=tk.X, pady=5)
    ttk.Label(row1, text="股票代號：", width=12).pack(side=tk.LEFT)
    symbol_var = tk.StringVar(value=symbol)
    symbol_entry = ttk.Entry(row1, textvariable=symbol_var, width=15)
    symbol_entry.pack(side=tk.LEFT, padx=5)
    
    # 查詢報價按鈕
    def query_quote():
        if not trader or not trader.is_logged_in:
            messagebox.showinfo("提示", "請先登入以取得即時報價")
            return
        
        sym = symbol_var.get().strip()
        if not sym:
            messagebox.showerror("錯誤", "請輸入股票代號")
            return
        
        result = trader.get_quote(sym)
        if result['success']:
            data = result['data']
            info = f"股票: {data['symbol']} {data['name']}\n"
            info += f"現價: {data['close']}\n"
            info += f"漲跌: {data['change']} ({data['change_percent']}%)\n"
            info += f"開: {data['open']} 高: {data['high']} 低: {data['low']}\n"
            info += f"量: {data['volume']}"
            messagebox.showinfo("即時報價", info)
            
            if data['close']:
                price_var.set(str(data['close']))
        else:
            messagebox.showerror("錯誤", result['message'])
    
    quote_btn = ttk.Button(row1, text="查詢報價", command=query_quote, width=10)
    quote_btn.pack(side=tk.LEFT, padx=5)
    
    # 買賣別
    row2 = ttk.Frame(order_frame)
    row2.pack(fill=tk.X, pady=5)
    ttk.Label(row2, text="買賣別：", width=12).pack(side=tk.LEFT)
    action_var = tk.StringVar(value='buy')
    buy_radio = ttk.Radiobutton(row2, text="買進", variable=action_var, value='buy')
    sell_radio = ttk.Radiobutton(row2, text="賣出", variable=action_var, value='sell')
    buy_radio.pack(side=tk.LEFT, padx=5)
    sell_radio.pack(side=tk.LEFT, padx=5)
    
    # 價格類型（中文化）
    row3 = ttk.Frame(order_frame)
    row3.pack(fill=tk.X, pady=5)
    ttk.Label(row3, text="價格類型：", width=12).pack(side=tk.LEFT)
    price_type_var = tk.StringVar(value='限價')
    price_type_combo = ttk.Combobox(row3, textvariable=price_type_var, 
                                    values=['限價', '市價', '平盤價'],
                                    state='readonly', width=12)
    price_type_combo.pack(side=tk.LEFT, padx=5)
    
    # 價格
    row4 = ttk.Frame(order_frame)
    row4.pack(fill=tk.X, pady=5)
    ttk.Label(row4, text="委託價格：", width=12).pack(side=tk.LEFT)
    price_var = tk.StringVar()
    price_entry = ttk.Entry(row4, textvariable=price_var, width=15)
    price_entry.pack(side=tk.LEFT, padx=5)
    
    # 數量
    row5 = ttk.Frame(order_frame)
    row5.pack(fill=tk.X, pady=5)
    ttk.Label(row5, text="委託股數：", width=12).pack(side=tk.LEFT)
    qty_var = tk.StringVar(value='1000')
    qty_entry = ttk.Entry(row5, textvariable=qty_var, width=15)
    qty_entry.pack(side=tk.LEFT, padx=5)
    ttk.Label(row5, text="(1張=1000股)").pack(side=tk.LEFT)
    
    # 委託時效（中文化）
    row6 = ttk.Frame(order_frame)
    row6.pack(fill=tk.X, pady=5)
    ttk.Label(row6, text="委託時效：", width=12).pack(side=tk.LEFT)
    tif_var = tk.StringVar(value='當日有效')
    tif_combo = ttk.Combobox(row6, textvariable=tif_var,
                            values=['當日有效', '立即成交否則取消', '全部成交否則取消'],
                            state='readonly', width=18)
    tif_combo.pack(side=tk.LEFT, padx=5)
    
    # 市場類型（中文化）
    row7 = ttk.Frame(order_frame)
    row7.pack(fill=tk.X, pady=5)
    ttk.Label(row7, text="市場類型：", width=12).pack(side=tk.LEFT)
    market_var = tk.StringVar(value='一般')
    market_combo = ttk.Combobox(row7, textvariable=market_var,
                               values=['一般', '盤中零股', '定盤'],
                               state='readonly', width=12)
    market_combo.pack(side=tk.LEFT, padx=5)
    
    # 下單按鈕
    def submit_order():
        if not trader or not trader.is_logged_in:
            messagebox.showerror("錯誤", "請先登入")
            return
        
        sym = symbol_var.get().strip()
        if not sym:
            messagebox.showerror("錯誤", "請輸入股票代號")
            return
        
        try:
            price = float(price_var.get()) if price_var.get() else None
            quantity = int(qty_var.get())
        except ValueError:
            messagebox.showerror("錯誤", "價格或數量格式錯誤")
            return
        
        action_text = "買進" if action_var.get() == 'buy' else "賣出"
        confirm = messagebox.askyesno(
            "確認下單",
            f"確定要{action_text} {sym}\n"
            f"價格: {price if price else '市價'}\n"
            f"數量: {quantity} 股？"
        )
        
        if confirm:
            result = trader.place_order(
                symbol=sym,
                action=action_var.get(),
                price=price,
                quantity=quantity,
                price_type=price_type_var.get(),
                market_type=market_var.get(),
                time_in_force=tif_var.get()
            )
            
            if result['success']:
                messagebox.showinfo("成功", f"下單成功！\n委託書號: {result.get('order_no', '')}")
                refresh_inventory()
            else:
                messagebox.showerror("失敗", result['message'])
    
    btn_frame = ttk.Frame(order_frame)
    btn_frame.pack(fill=tk.X, pady=10)
    submit_btn = ttk.Button(btn_frame, text="📤 送出委託", command=submit_order, width=15)
    submit_btn.pack(side=tk.LEFT, padx=5)
    
    # ============================================================================
    # 右側：庫存區域
    # ============================================================================
    inventory_frame = ttk.LabelFrame(right_panel, text="💰 庫存明細", padding="10")
    inventory_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    
    # 庫存標題列（含刷新按鈕）
    inv_title_row = ttk.Frame(inventory_frame)
    inv_title_row.pack(fill=tk.X, pady=(0, 5))
    
    # 總損益標籤
    total_pnl_label = ttk.Label(inv_title_row, text="總損益：--", 
                                font=('Microsoft JhengHei', 12, 'bold'))
    total_pnl_label.pack(side=tk.LEFT)
    
    # 刷新按鈕（使用富邦API）
    refresh_inv_btn = ttk.Button(inv_title_row, text="🔄 刷新庫存", 
                                  command=refresh_inventory, width=12)
    refresh_inv_btn.pack(side=tk.RIGHT, padx=5)
    
    # 更新時間標籤
    update_time_label = ttk.Label(inv_title_row, text="", font=('Microsoft JhengHei', 9), foreground='gray')
    update_time_label.pack(side=tk.RIGHT, padx=5)
    
    def refresh_inventory_with_time():
        """刷新庫存並更新時間"""
        refresh_inventory()
        from datetime import datetime
        update_time_label.config(text=f"更新: {datetime.now().strftime('%H:%M:%S')}")
    
    refresh_inv_btn.config(command=refresh_inventory_with_time)
    
    # 庫存表格
    inv_columns = ('symbol', 'name', 'qty', 'avg_price', 'now_price', 'pnl', 'pnl_pct')
    inventory_tree = ttk.Treeview(inventory_frame, columns=inv_columns, show='headings', height=8)
    
    inventory_tree.heading('symbol', text='代號')
    inventory_tree.heading('name', text='名稱')
    inventory_tree.heading('qty', text='股數')
    inventory_tree.heading('avg_price', text='成本')
    inventory_tree.heading('now_price', text='現價')
    inventory_tree.heading('pnl', text='損益')
    inventory_tree.heading('pnl_pct', text='報酬率')
    
    inventory_tree.column('symbol', width=60, anchor='center')
    inventory_tree.column('name', width=80, anchor='center')
    inventory_tree.column('qty', width=70, anchor='e')
    inventory_tree.column('avg_price', width=70, anchor='e')
    inventory_tree.column('now_price', width=70, anchor='e')
    inventory_tree.column('pnl', width=80, anchor='e')
    inventory_tree.column('pnl_pct', width=70, anchor='e')
    
    inv_scrollbar = ttk.Scrollbar(inventory_frame, orient=tk.VERTICAL, command=inventory_tree.yview)
    inventory_tree.configure(yscrollcommand=inv_scrollbar.set)
    
    inventory_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    inv_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # 點擊庫存項目填入股票代號
    def on_inventory_select(event):
        selected = inventory_tree.selection()
        if selected:
            iid = selected[0]
            # v4.4.1：從 iid 中提取股票代號（格式：inv_{index}_{symbol}）
            # 這樣可以保留前導0（如 0056）
            if iid.startswith('inv_'):
                parts = iid.split('_')
                if len(parts) >= 3:
                    sym_str = '_'.join(parts[2:])  # 處理可能包含底線的代號
                    if sym_str and sym_str not in ['載入中...', '無庫存', '請先登入']:
                        symbol_var.set(sym_str)
                        return
            
            # 備用方案：從 values 取得（可能丟失前導0）
            item = inventory_tree.item(iid)
            sym = item['values'][0]
            sym_str = str(sym) if sym else ''
            if sym_str and sym_str not in ['載入中...', '無庫存', '請先登入'] and not sym_str.startswith('錯誤'):
                symbol_var.set(sym_str)
    
    inventory_tree.bind('<Double-1>', on_inventory_select)
    
    # ============================================================================
    # 右側：量化分析摘要（v4.3.7 修正版：字體放大 + 股價顯示）
    # ============================================================================
    analysis_frame = ttk.LabelFrame(right_panel, text="📊 量化分析摘要", padding="10")
    analysis_frame.pack(fill=tk.BOTH, expand=True)
    
    # 分析內容文字框（v4.3.7：字體從 10 放大到 13）
    analysis_text = tk.Text(analysis_frame, height=14, width=55, wrap=tk.WORD,
                           font=('Microsoft JhengHei', 13))
    analysis_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
    
    analysis_scrollbar = ttk.Scrollbar(analysis_text, orient=tk.VERTICAL, command=analysis_text.yview)
    analysis_text.configure(yscrollcommand=analysis_scrollbar.set)
    
    # 定義標籤樣式（v4.3.7：字體放大）
    analysis_text.tag_config("title", font=("Microsoft JhengHei", 14, "bold"), foreground="#F39C12")
    analysis_text.tag_config("price_header", font=("Microsoft JhengHei", 18, "bold"), foreground="#3498DB")
    analysis_text.tag_config("price_up", font=("Microsoft JhengHei", 14, "bold"), foreground="#E74C3C")
    analysis_text.tag_config("price_down", font=("Microsoft JhengHei", 14, "bold"), foreground="#2ECC71")
    analysis_text.tag_config("positive", foreground="#2ECC71", font=("Microsoft JhengHei", 13, "bold"))
    analysis_text.tag_config("negative", foreground="#E74C3C", font=("Microsoft JhengHei", 13, "bold"))
    analysis_text.tag_config("warning", foreground="#E67E22", font=("Microsoft JhengHei", 13))
    analysis_text.tag_config("normal", font=("Microsoft JhengHei", 13))
    analysis_text.tag_config("info", foreground="#3498DB", font=("Microsoft JhengHei", 12))
    
    # 預設提示
    analysis_text.insert('1.0', "💡 點擊「分析股票」按鈕取得量化分析報告\n\n", "title")
    analysis_text.insert(tk.END, "分析內容包含：\n", "normal")
    analysis_text.insert(tk.END, "• 目前股價與漲跌幅\n", "normal")
    analysis_text.insert(tk.END, "• 決策矩陣場景判斷\n", "normal")
    analysis_text.insert(tk.END, "• 趨勢方向與乖離狀態\n", "normal")
    analysis_text.insert(tk.END, "• 風險回報比評估\n", "normal")
    analysis_text.insert(tk.END, "• 短線/中線操作建議\n", "normal")
    analysis_text.insert(tk.END, "• 進場時機判斷\n\n", "normal")
    analysis_text.insert(tk.END, "📌 提示：若在主視窗已分析，會自動載入結果", "info")
    analysis_text.config(state='disabled')
    
    def analyze_stock():
        """執行量化分析（整合主視窗分析結果）"""
        sym = symbol_var.get().strip()
        if not sym:
            messagebox.showerror("錯誤", "請輸入股票代號")
            return
        
        analysis_text.config(state='normal')
        analysis_text.delete('1.0', tk.END)
        analysis_text.insert('1.0', f"正在分析 {sym}...\n", "title")
        analysis_text.config(state='disabled')
        dialog.update()
        
        try:
            result = None
            
            # 嘗試從主視窗取得已分析的結果
            if hasattr(parent, 'last_analysis_result') and parent.last_analysis_result:
                if parent.last_analysis_result.get('symbol') == sym:
                    result = parent.last_analysis_result
                    print(f"[DEBUG] 使用主視窗已有的分析結果: {sym}")
            
            # 如果沒有現成結果，呼叫 QuickAnalyzer
            if result is None:
                try:
                    # 動態導入（避免循環導入）
                    import sys
                    if 'main' in sys.modules:
                        main_module = sys.modules['main']
                        if hasattr(main_module, 'QuickAnalyzer'):
                            market = "台股"  # 預設台股
                            result = main_module.QuickAnalyzer.analyze_stock(sym, market)
                            print(f"[DEBUG] 新執行分析: {sym}")
                except Exception as e:
                    print(f"[DEBUG] 呼叫 QuickAnalyzer 失敗: {e}")
            
            # 顯示分析結果
            analysis_text.config(state='normal')
            analysis_text.delete('1.0', tk.END)
            
            if result:
                _display_analysis_summary(analysis_text, sym, result)
                last_analysis_result['data'] = result
            else:
                analysis_text.insert('1.0', f"📈 {sym} 量化分析報告\n", "title")
                analysis_text.insert(tk.END, "=" * 45 + "\n\n", "normal")
                analysis_text.insert(tk.END, "⚠️ 無法取得分析資料\n\n", "warning")
                analysis_text.insert(tk.END, "請先在主視窗查詢此股票，\n", "normal")
                analysis_text.insert(tk.END, "點擊「查詢」按鈕後再回來下單。\n\n", "normal")
                analysis_text.insert(tk.END, "【快速步驟】\n", "info")
                analysis_text.insert(tk.END, f"1. 在主視窗輸入 {sym}\n", "info")
                analysis_text.insert(tk.END, "2. 點擊「查詢」按鈕\n", "info")
                analysis_text.insert(tk.END, "3. 點擊「完整分析」按鈕\n", "info")
                analysis_text.insert(tk.END, "4. 回到下單視窗，再次點擊「分析股票」\n", "info")
            
            analysis_text.config(state='disabled')
            
        except Exception as e:
            analysis_text.config(state='normal')
            analysis_text.delete('1.0', tk.END)
            analysis_text.insert('1.0', f"分析錯誤: {e}", "negative")
            analysis_text.config(state='disabled')
            import traceback
            traceback.print_exc()
    
    def _display_analysis_summary(text_widget, symbol, result):
        """顯示分析摘要（v4.3.7：加入股價顯示）"""
        
        # v4.3.7：第一行顯示目前股價和漲幅
        current_price = result.get('current_price', 0)
        price_change = result.get('price_change', 0)
        price_change_pct = result.get('price_change_pct', 0)
        
        text_widget.insert(tk.END, f"📈 {symbol} ", "title")
        
        # 股價顯示
        if current_price > 0:
            text_widget.insert(tk.END, f"${current_price:.2f} ", "price_header")
            
            # 漲跌幅顯示
            if price_change > 0:
                text_widget.insert(tk.END, f"▲{price_change:.2f} (+{price_change_pct:.2f}%)\n", "price_up")
            elif price_change < 0:
                text_widget.insert(tk.END, f"▼{abs(price_change):.2f} ({price_change_pct:.2f}%)\n", "price_down")
            else:
                text_widget.insert(tk.END, f"- 平盤\n", "normal")
        else:
            text_widget.insert(tk.END, "量化分析摘要\n", "title")
        
        text_widget.insert(tk.END, "=" * 40 + "\n\n", "normal")
        
        # 核心建議
        rec = result.get('recommendation', {})
        if isinstance(rec, dict):
            overall = rec.get('overall', '待分析')
            scenario = rec.get('scenario', '')
            scenario_name = rec.get('scenario_name', '')
            action_timing = rec.get('action_timing', '')
            warning_msg = rec.get('warning_message', '')
            rr_ratio = rec.get('rr_ratio', 0)
            bias_20 = rec.get('bias_20', 0)
            
            # 場景
            if scenario and scenario_name:
                text_widget.insert(tk.END, "【觸發場景】", "normal")
                tag = "positive" if scenario in ['B', 'B2'] else "negative" if scenario == 'D' else "warning"
                text_widget.insert(tk.END, f" {scenario} - {scenario_name}\n", tag)
            
            # 投資建議
            text_widget.insert(tk.END, "【投資建議】", "normal")
            if any(x in overall for x in ["買進", "進場", "看好"]):
                text_widget.insert(tk.END, f" {overall}\n", "positive")
            elif any(x in overall for x in ["賣出", "減碼", "出場"]):
                text_widget.insert(tk.END, f" {overall}\n", "negative")
            else:
                text_widget.insert(tk.END, f" {overall}\n", "warning")
            
            # 進場時機
            if action_timing:
                text_widget.insert(tk.END, "【進場時機】", "normal")
                text_widget.insert(tk.END, f" {action_timing}\n", "info")
            
            # 關鍵指標
            if rr_ratio > 0:
                text_widget.insert(tk.END, f"【盈虧比】 {rr_ratio:.2f}\n", "normal")
            if bias_20 != 0:
                text_widget.insert(tk.END, f"【20MA乖離】 {bias_20:+.1f}%\n", "normal")
            
            # 警示訊息
            if warning_msg:
                text_widget.insert(tk.END, f"\n📝 {warning_msg}\n", "warning")
            
            # 區間操作資訊（修正：顯示箱頂箱底）
            if scenario == 'E':
                range_info = rec.get('range_info', {})
                if range_info:
                    text_widget.insert(tk.END, "\n【區間操作資訊】\n", "title")
                    box_top = range_info.get('box_top', 'N/A')
                    box_bottom = range_info.get('box_bottom', 'N/A')
                    position = range_info.get('position', '')
                    suggestion = range_info.get('suggestion', '')
                    
                    text_widget.insert(tk.END, f"  箱頂價格：${box_top}\n", "normal")
                    text_widget.insert(tk.END, f"  箱底價格：${box_bottom}\n", "normal")
                    text_widget.insert(tk.END, f"  目前位置：{position}\n", "info")
                    text_widget.insert(tk.END, f"  操作建議：{suggestion}\n", "positive" if "買" in suggestion else "negative" if "賣" in suggestion else "warning")
            
            text_widget.insert(tk.END, "\n" + "-" * 45 + "\n", "normal")
            
            # 分段建議
            text_widget.insert(tk.END, "【分段操作建議】\n", "title")
            for period, name in [('short_term', '短線'), ('mid_term', '中線'), ('long_term', '長線')]:
                data = rec.get(period, {})
                if isinstance(data, dict):
                    action = data.get('action', 'N/A')
                    reason = data.get('reason', '')
                    
                    text_widget.insert(tk.END, f"  {name}：", "normal")
                    if any(x in action for x in ["買進", "進場", "持有", "偏多"]):
                        text_widget.insert(tk.END, f"{action}\n", "positive")
                    elif any(x in action for x in ["賣出", "減碼", "偏空"]):
                        text_widget.insert(tk.END, f"{action}\n", "negative")
                    else:
                        text_widget.insert(tk.END, f"{action}\n", "warning")
                    
                    if reason:
                        text_widget.insert(tk.END, f"        ({reason})\n", "info")
        
        # v4.4.1 新增：量價分析摘要
        vp = result.get('volume_price', {})
        if vp.get('available'):
            text_widget.insert(tk.END, "\n" + "-" * 40 + "\n", "normal")
            text_widget.insert(tk.END, "【量價分析】\n", "title")
            
            vp_score = vp.get('vp_score', 0)
            summary = vp.get('summary', '')
            
            # 分數顯示
            if vp_score > 20:
                text_widget.insert(tk.END, f"  量價評分：{vp_score:+d} ", "positive")
                text_widget.insert(tk.END, "(偏多)\n", "positive")
            elif vp_score < -20:
                text_widget.insert(tk.END, f"  量價評分：{vp_score:+d} ", "negative")
                text_widget.insert(tk.END, "(偏空)\n", "negative")
            else:
                text_widget.insert(tk.END, f"  量價評分：{vp_score:+d} ", "normal")
                text_widget.insert(tk.END, "(中性)\n", "normal")
            
            # 顯示主要訊號（最多2個）
            signals = vp.get('signals', [])
            if signals:
                for sig in signals[:2]:
                    direction = sig.get('direction', 'neutral')
                    name = sig.get('name', '')
                    hint = sig.get('decision_hint', '')
                    
                    if direction == 'bullish':
                        icon = "🟢"
                        tag = "positive"
                    elif direction == 'bearish':
                        icon = "🔴"
                        tag = "negative"
                    else:
                        icon = "🟡"
                        tag = "warning"
                    
                    text_widget.insert(tk.END, f"  {icon} {name}\n", tag)
                    if hint:
                        text_widget.insert(tk.END, f"     → {hint}\n", "info")
        
        # v4.4.2 新增：籌碼面摘要（數值驅動）
        chip = result.get('chip_flow', {})
        if chip.get('available'):
            text_widget.insert(tk.END, "\n" + "-" * 40 + "\n", "normal")
            text_widget.insert(tk.END, "【籌碼面分析】\n", "title")
            
            # 外資
            foreign_net = chip.get('foreign_net', 0)
            foreign_days = chip.get('foreign_consecutive_days', 0)
            foreign_text = chip.get('foreign', 'N/A')
            
            if foreign_net > 0:
                icon = "🔴"
                tag = "positive"
            elif foreign_net < 0:
                icon = "🟢"
                tag = "negative"
            else:
                icon = "⚪"
                tag = "normal"
            
            text_widget.insert(tk.END, f"  {icon} 外資：{foreign_text}", tag)
            if abs(foreign_days) >= 2:
                text_widget.insert(tk.END, f" (連{abs(foreign_days)}日)\n", tag)
            else:
                text_widget.insert(tk.END, "\n", tag)
            
            # 投信
            trust_net = chip.get('trust_net', 0)
            trust_days = chip.get('trust_consecutive_days', 0)
            trust_text = chip.get('trust', 'N/A')
            
            if trust_net > 0:
                icon = "🔴"
                tag = "positive"
            elif trust_net < 0:
                icon = "🟢"
                tag = "negative"
            else:
                icon = "⚪"
                tag = "normal"
            
            text_widget.insert(tk.END, f"  {icon} 投信：{trust_text}", tag)
            if abs(trust_days) >= 2:
                text_widget.insert(tk.END, f" (連{abs(trust_days)}日)\n", tag)
            else:
                text_widget.insert(tk.END, "\n", tag)
            
            # 同步信號判斷
            is_sync_buy = (foreign_net > 0 and trust_net > 0 and 
                          abs(foreign_days) >= 2 and abs(trust_days) >= 2)
            is_sync_sell = (foreign_net < 0 and trust_net < 0 and 
                           abs(foreign_days) >= 2 and abs(trust_days) >= 2)
            
            if is_sync_buy:
                text_widget.insert(tk.END, f"  ⭐ 同步連續買超，籌碼面強勢\n", "positive")
            elif is_sync_sell:
                text_widget.insert(tk.END, f"  ⚠️ 同步連續賣超，籌碼面轉弱\n", "negative")
            
            # 籌碼結論
            chip_signal = chip.get('signal', '')
            if chip_signal:
                if "集中" in chip_signal or "偏多" in chip_signal:
                    text_widget.insert(tk.END, f"  結論：{chip_signal}\n", "positive")
                elif "分散" in chip_signal or "偏空" in chip_signal:
                    text_widget.insert(tk.END, f"  結論：{chip_signal}\n", "negative")
                else:
                    text_widget.insert(tk.END, f"  結論：{chip_signal}\n", "normal")
        
        # 支撐壓力
        sr = result.get('support_resistance', {})
        if sr:
            text_widget.insert(tk.END, "\n" + "-" * 45 + "\n", "normal")
            text_widget.insert(tk.END, "【支撐壓力位】\n", "title")
            text_widget.insert(tk.END, f"  建議停利：${sr.get('take_profit', 'N/A')}\n", "positive")
            text_widget.insert(tk.END, f"  建議停損：${sr.get('stop_loss', 'N/A')}\n", "negative")
            text_widget.insert(tk.END, f"  第一壓力：${sr.get('resistance1', 'N/A')}\n", "normal")
            text_widget.insert(tk.END, f"  第一支撐：${sr.get('support1', 'N/A')}\n", "normal")
    
    analysis_btn_frame = ttk.Frame(analysis_frame)
    analysis_btn_frame.pack(fill=tk.X)
    
    analyze_btn = ttk.Button(analysis_btn_frame, text="📊 分析股票", command=analyze_stock, width=15)
    analyze_btn.pack(side=tk.LEFT, padx=5)
    
    # 更新登入狀態（如果已經登入）
    if trader and trader.is_logged_in:
        status_var.set("🟢 已登入")
        # 延遲載入庫存，確保 UI 元件已完成初始化
        dialog.after(300, refresh_inventory)
    
    return dialog


# 全域 trader 實例
_global_trader = None

def get_trader():
    """取得全域 trader 實例"""
    global _global_trader
    if _global_trader is None:
        _global_trader = FubonTrader()
    return _global_trader


# ============================================================================
# 啟動登入（單一登入點：登入一次，行情與下單共用同一個 SDK）
# ============================================================================
# 偏好設定只存「帳號 / 憑證路徑 / 是否不再詢問」——
# **密碼與憑證密碼一律不落地**，每次啟動手動輸入。
LOGIN_PREFS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'fubon_login_prefs.json')


def load_login_prefs():
    """讀取登入偏好（無密碼）。"""
    try:
        with open(LOGIN_PREFS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return {
            'user_id': d.get('user_id', ''),
            'cert_path': d.get('cert_path', ''),
            'skip_startup_login': bool(d.get('skip_startup_login', False)),
        }
    except Exception:
        return {'user_id': '', 'cert_path': '', 'skip_startup_login': False}


def save_login_prefs(user_id='', cert_path='', skip_startup_login=False):
    """儲存登入偏好。嚴禁寫入任何密碼欄位。"""
    try:
        with open(LOGIN_PREFS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'user_id': user_id, 'cert_path': cert_path,
                       'skip_startup_login': bool(skip_startup_login)},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[富邦登入] 偏好儲存失敗: {e}")


def startup_login_dialog(parent, force=False):
    """
    啟動時的富邦登入對話框。

    Args:
        parent: 父視窗
        force:  True＝忽略「不再詢問」偏好（供選單手動登入用）

    Returns:
        FubonTrader: 已登入的全域 trader；使用者選擇跳過或失敗則回 None
    """
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    if not FUBON_SDK_AVAILABLE:
        if force:
            messagebox.showerror("無法登入", "未安裝 fubon_neo SDK")
        return None

    prefs = load_login_prefs()
    if prefs['skip_startup_login'] and not force:
        print("[富邦登入] 依偏好設定跳過啟動登入（可從選單手動登入）")
        return None

    trader = get_trader()
    if trader.is_logged_in:
        return trader   # 已登入就不重複問

    dlg = tk.Toplevel(parent)
    dlg.title("富邦證券登入")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)

    frm = ttk.Frame(dlg, padding=16)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="登入後行情改用富邦即時報價，下單功能亦無需再次登入。",
              foreground="#666").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    user_id_var = tk.StringVar(value=prefs['user_id'])
    pwd_var = tk.StringVar()
    cert_var = tk.StringVar(value=prefs['cert_path'])
    cert_pwd_var = tk.StringVar()
    remember_var = tk.BooleanVar(value=bool(prefs['user_id'] or prefs['cert_path']))
    dont_ask_var = tk.BooleanVar(value=False)

    rows = [("身分證字號：", user_id_var, False),
            ("登入密碼：", pwd_var, True),
            ("憑證路徑：", cert_var, False),
            ("憑證密碼：", cert_pwd_var, True)]
    entries = {}
    for i, (label, var, secret) in enumerate(rows, start=1):
        ttk.Label(frm, text=label, width=12).grid(row=i, column=0, sticky="w", pady=3)
        e = ttk.Entry(frm, textvariable=var, width=30, show="*" if secret else "")
        e.grid(row=i, column=1, sticky="we", pady=3)
        entries[label] = e

    def browse():
        p = filedialog.askopenfilename(
            title="選擇憑證檔",
            filetypes=[("憑證檔", "*.pfx *.p12"), ("所有檔案", "*.*")])
        if p:
            cert_var.set(p)
    ttk.Button(frm, text="瀏覽", width=6, command=browse).grid(row=3, column=2, padx=(6, 0))

    ttk.Checkbutton(frm, text="記住身分證字號與憑證路徑（不含密碼）",
                    variable=remember_var).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Checkbutton(frm, text="下次啟動不再詢問（仍可從『交易』選單手動登入）",
                    variable=dont_ask_var).grid(row=6, column=0, columnspan=3, sticky="w")

    status_var = tk.StringVar(value="")
    ttk.Label(frm, textvariable=status_var, foreground="#c77").grid(
        row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))

    result = {'trader': None}

    def do_skip():
        # 「不再詢問」即使跳過也要記住
        save_login_prefs(user_id_var.get().strip() if remember_var.get() else '',
                         cert_var.get().strip() if remember_var.get() else '',
                         dont_ask_var.get())
        dlg.destroy()

    def do_login_click():
        uid = user_id_var.get().strip()
        pwd = pwd_var.get()
        cert = cert_var.get().strip()
        cpwd = cert_pwd_var.get()
        if not all([uid, pwd, cert, cpwd]):
            status_var.set("請填寫所有欄位")
            return
        if not os.path.exists(cert):
            status_var.set("憑證檔不存在，請確認路徑")
            return
        status_var.set("登入中…")
        dlg.update()
        res = trader.login(uid, pwd, cert, cpwd)
        if res.get('success'):
            save_login_prefs(uid if remember_var.get() else '',
                             cert if remember_var.get() else '',
                             dont_ask_var.get())
            result['trader'] = trader
            dlg.destroy()
        else:
            status_var.set(f"登入失敗：{res.get('message', '未知錯誤')}")

    btns = ttk.Frame(frm)
    btns.grid(row=8, column=0, columnspan=3, pady=(14, 0), sticky="e")
    ttk.Button(btns, text="這次跳過", command=do_skip).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="登入", command=do_login_click).pack(side=tk.LEFT)

    # 焦點放在第一個空欄位
    (entries["登入密碼："] if prefs['user_id'] else entries["身分證字號："]).focus_set()
    dlg.bind('<Return>', lambda e: do_login_click())
    dlg.protocol("WM_DELETE_WINDOW", do_skip)

    dlg.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_width()) // 2
    y = parent.winfo_rooty() + 120
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

    parent.wait_window(dlg)
    return result['trader']
