"""
auto_trader_gui.py - AutoTrader 視覺化介面 v1.0

功能：
1. 模擬/實單雙模式切換
2. 資金設定調整
3. 交易LOG顯示
4. 庫存與損益監控
5. 手動/自動分析控制
6. 存股名單管理

作者：Stock Analysis System
日期：2026-01-19
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import datetime
import threading
import time
from typing import Dict, List, Optional

# 本地模組
from config import QuantConfig
from database import WatchlistDatabase

# 嘗試導入 QuickAnalyzer
try:
    from main import QuickAnalyzer
    ANALYZER_AVAILABLE = True
except ImportError:
    ANALYZER_AVAILABLE = False

# 嘗試導入 AutoTrader
try:
    from auto_trader import AutoTrader, AutoTraderConfig
    AUTO_TRADER_AVAILABLE = True
except ImportError as e:
    print(f"[AutoTraderGUI] 警告：無法導入 AutoTrader: {e}")
    AUTO_TRADER_AVAILABLE = False

# 嘗試導入 FubonTrader
try:
    from fubon_trading import FubonTrader
    FUBON_AVAILABLE = True
except ImportError:
    FUBON_AVAILABLE = False


# ============================================================================
# AutoTrader 視覺化介面
# ============================================================================

class AutoTraderGUI:
    """
    AutoTrader 視覺化介面
    
    可單獨執行或從主程式開啟
    """
    
    def __init__(self, parent=None, standalone=True, fubon_trader=None):
        """
        初始化 GUI
        
        Args:
            parent: 父視窗（從主程式開啟時傳入）
            standalone: 是否為獨立執行模式
            fubon_trader: 已登入的 FubonTrader 實例（可選）
        """
        self.standalone = standalone
        self.parent = parent
        self.fubon_trader = fubon_trader  # v4.4.5：保存 FubonTrader 實例
        
        # 創建視窗
        if standalone:
            self.root = tk.Tk()
            self.root.title("🤖 AutoTrader 自動交易系統 v1.0")
            self.root.geometry("1400x900")
            self.root.minsize(1200, 700)
        else:
            self.root = tk.Toplevel(parent)
            self.root.title("🤖 AutoTrader 自動交易系統")
            self.root.geometry("1400x900")
            self.root.transient(parent)
        
        # 設定關閉事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 狀態變數
        self.trader = None
        self.is_running = False
        self.auto_thread = None
        self._closed = False
        
        # 資料庫
        self.db = WatchlistDatabase()
        
        # 載入存股名單
        self.ignore_list = self._load_ignore_list()
        
        # 建立 GUI
        self._create_gui()
        
        # v4.4.7 新增：載入儲存的設定（在 GUI 建立後）
        self._load_settings()
        
        # 初始化顯示
        self._refresh_ignore_list_display()
        self._load_trade_log()
        
        # 嘗試載入模擬數據
        self._load_simulation_preview()
        
        # v4.4.5：如果有傳入 FubonTrader，自動顯示連線狀態
        if self.fubon_trader and self.fubon_trader.is_logged_in:
            self._log_message("已連接實單帳戶（從主程式繼承）", "info")
    
    def _create_gui(self):
        """建立 GUI 介面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ============================================================
        # 頂部：模式選擇與登入區
        # ============================================================
        self._create_top_section(main_frame)
        
        # ============================================================
        # 中間區域（三欄佈局）
        # ============================================================
        middle_frame = ttk.Frame(main_frame)
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 左欄：資金設定 + 庫存
        self._create_left_panel(middle_frame)
        
        # 中欄：交易LOG + 分析結果
        self._create_center_panel(middle_frame)
        
        # 右欄：存股名單管理
        self._create_right_panel(middle_frame)
        
        # ============================================================
        # 底部：操作按鈕
        # ============================================================
        self._create_bottom_section(main_frame)
    
    def _create_top_section(self, parent):
        """建立頂部區域：模式選擇與登入"""
        top_frame = ttk.LabelFrame(parent, text="🔐 模式與連線", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 左側：模式選擇
        mode_frame = ttk.Frame(top_frame)
        mode_frame.pack(side=tk.LEFT, fill=tk.X)
        
        ttk.Label(mode_frame, text="運作模式：", font=("", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        
        self.mode_var = tk.StringVar(value="SIMULATION")
        
        sim_radio = ttk.Radiobutton(mode_frame, text="🔬 模擬模式", 
                                    variable=self.mode_var, value="SIMULATION",
                                    command=self._on_mode_change)
        sim_radio.pack(side=tk.LEFT, padx=5)
        
        live_radio = ttk.Radiobutton(mode_frame, text="💰 實單模式", 
                                     variable=self.mode_var, value="LIVE",
                                     command=self._on_mode_change)
        live_radio.pack(side=tk.LEFT, padx=5)
        
        # 分隔線
        ttk.Separator(top_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=15)
        
        # 中間：登入資訊（實單模式用）
        self.login_frame = ttk.Frame(top_frame)
        self.login_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(self.login_frame, text="身分證：").pack(side=tk.LEFT)
        self.user_id_var = tk.StringVar()
        self.user_id_entry = ttk.Entry(self.login_frame, textvariable=self.user_id_var, width=12)
        self.user_id_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(self.login_frame, text="密碼：").pack(side=tk.LEFT, padx=(10, 0))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(self.login_frame, textvariable=self.password_var, 
                                        width=12, show="*")
        self.password_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(self.login_frame, text="憑證路徑：").pack(side=tk.LEFT, padx=(10, 0))
        self.cert_path_var = tk.StringVar()
        self.cert_path_entry = ttk.Entry(self.login_frame, textvariable=self.cert_path_var, width=20)
        self.cert_path_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(self.login_frame, text="📂", width=3,
                   command=self._browse_cert).pack(side=tk.LEFT)
        
        ttk.Label(self.login_frame, text="憑證密碼：").pack(side=tk.LEFT, padx=(10, 0))
        self.cert_password_var = tk.StringVar()
        self.cert_password_entry = ttk.Entry(self.login_frame, textvariable=self.cert_password_var, 
                                             width=10, show="*")
        self.cert_password_entry.pack(side=tk.LEFT, padx=2)
        
        # 初始隱藏登入框（模擬模式不需要）
        self._toggle_login_frame()
        
        # 右側：狀態與連線按鈕
        status_frame = ttk.Frame(top_frame)
        status_frame.pack(side=tk.RIGHT)
        
        self.status_label = ttk.Label(status_frame, text="⚪ 未連線", 
                                      font=("", 10, "bold"), foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.connect_btn = ttk.Button(status_frame, text="🔌 連線/初始化", 
                                      command=self._connect)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
    
    def _create_left_panel(self, parent):
        """建立左欄：資金設定 + 庫存顯示"""
        left_frame = ttk.Frame(parent, width=450)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 5))
        left_frame.pack_propagate(False)
        
        # ============================================================
        # 資金設定區
        # ============================================================
        capital_frame = ttk.LabelFrame(left_frame, text="💰 資金設定", padding="10")
        capital_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 模擬帳戶資金
        sim_frame = ttk.LabelFrame(capital_frame, text="模擬帳戶", padding="5")
        sim_frame.pack(fill=tk.X, pady=(0, 5))
        
        row1 = ttk.Frame(sim_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="初始資金：$").pack(side=tk.LEFT)
        self.sim_capital_var = tk.StringVar(value="1000000")
        self.sim_capital_entry = ttk.Entry(row1, textvariable=self.sim_capital_var, width=12)
        self.sim_capital_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="重置帳戶", command=self._reset_simulation,
                   width=10).pack(side=tk.RIGHT)
        
        row2 = ttk.Frame(sim_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="可用餘額：").pack(side=tk.LEFT)
        self.sim_balance_label = ttk.Label(row2, text="$0", font=("", 10, "bold"),
                                           foreground="blue")
        self.sim_balance_label.pack(side=tk.LEFT)
        
        # 實單帳戶資金
        live_frame = ttk.LabelFrame(capital_frame, text="實單帳戶", padding="5")
        live_frame.pack(fill=tk.X, pady=(0, 5))
        
        row3 = ttk.Frame(live_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="可交易金額上限：$").pack(side=tk.LEFT)
        self.live_budget_var = tk.StringVar(value="500000")
        self.live_budget_entry = ttk.Entry(row3, textvariable=self.live_budget_var, width=12)
        self.live_budget_entry.pack(side=tk.LEFT, padx=2)
        
        row4 = ttk.Frame(live_frame)
        row4.pack(fill=tk.X, pady=2)
        ttk.Label(row4, text="帳戶餘額：").pack(side=tk.LEFT)
        self.live_balance_label = ttk.Label(row4, text="$0（需登入）", 
                                            font=("", 10), foreground="gray")
        self.live_balance_label.pack(side=tk.LEFT)
        
        # 共用設定
        common_frame = ttk.LabelFrame(capital_frame, text="交易參數", padding="5")
        common_frame.pack(fill=tk.X)
        
        row5 = ttk.Frame(common_frame)
        row5.pack(fill=tk.X, pady=2)
        ttk.Label(row5, text="單一部位上限：").pack(side=tk.LEFT)
        self.position_pct_var = tk.StringVar(value="20")
        ttk.Entry(row5, textvariable=self.position_pct_var, width=5).pack(side=tk.LEFT)
        ttk.Label(row5, text="%").pack(side=tk.LEFT)
        
        row6 = ttk.Frame(common_frame)
        row6.pack(fill=tk.X, pady=2)
        ttk.Label(row6, text="最低盈虧比：").pack(side=tk.LEFT)
        self.min_rr_var = tk.StringVar(value="1.5")
        ttk.Entry(row6, textvariable=self.min_rr_var, width=5).pack(side=tk.LEFT)
        
        # v4.4.5 新增：停損百分比設定
        row7 = ttk.Frame(common_frame)
        row7.pack(fill=tk.X, pady=2)
        ttk.Label(row7, text="停損百分比：").pack(side=tk.LEFT)
        self.stop_loss_pct_var = tk.StringVar(value="8")
        ttk.Entry(row7, textvariable=self.stop_loss_pct_var, width=5).pack(side=tk.LEFT)
        ttk.Label(row7, text="% (虧損達此即賣)", foreground="gray").pack(side=tk.LEFT)
        
        # v4.4.6 新增：交易選項
        row8 = ttk.Frame(common_frame)
        row8.pack(fill=tk.X, pady=2)
        self.enable_odd_lot_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row8, text="啟用零股交易", 
                        variable=self.enable_odd_lot_var).pack(side=tk.LEFT)
        
        row9 = ttk.Frame(common_frame)
        row9.pack(fill=tk.X, pady=2)
        self.require_high_confidence_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row9, text="只買高信心度 (High)", 
                        variable=self.require_high_confidence_var).pack(side=tk.LEFT)
        
        ttk.Button(common_frame, text="💾 儲存設定", 
                   command=self._save_settings).pack(pady=5)
        
        # ============================================================
        # 庫存與損益顯示區
        # ============================================================
        inventory_frame = ttk.LabelFrame(left_frame, text="📊 庫存與損益", padding="5")
        inventory_frame.pack(fill=tk.BOTH, expand=True)
        
        # 帳戶切換
        acc_frame = ttk.Frame(inventory_frame)
        acc_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.inv_account_var = tk.StringVar(value="SIM")
        ttk.Radiobutton(acc_frame, text="模擬帳戶", variable=self.inv_account_var,
                        value="SIM", command=self._refresh_inventory).pack(side=tk.LEFT)
        ttk.Radiobutton(acc_frame, text="實單帳戶", variable=self.inv_account_var,
                        value="LIVE", command=self._refresh_inventory).pack(side=tk.LEFT)
        ttk.Button(acc_frame, text="🔄", width=3,
                   command=self._refresh_inventory).pack(side=tk.RIGHT)
        
        # 損益摘要（更詳細）
        summary_frame = ttk.Frame(inventory_frame)
        summary_frame.pack(fill=tk.X, pady=5)
        
        # 第一行：總資產與淨值
        row1 = ttk.Frame(summary_frame)
        row1.pack(fill=tk.X)
        self.total_assets_label = ttk.Label(row1, text="總資產：$0", 
                                            font=("", 10, "bold"))
        self.total_assets_label.pack(side=tk.LEFT)
        
        # 第二行：付出成本
        row2 = ttk.Frame(summary_frame)
        row2.pack(fill=tk.X)
        self.total_cost_label = ttk.Label(row2, text="付出成本：$0", font=("", 9))
        self.total_cost_label.pack(side=tk.LEFT)
        
        # 第三行：資產市值
        row3 = ttk.Frame(summary_frame)
        row3.pack(fill=tk.X)
        self.market_value_label = ttk.Label(row3, text="資產市值：$0", font=("", 9))
        self.market_value_label.pack(side=tk.LEFT)
        
        # 第四行：未實現損益
        row4 = ttk.Frame(summary_frame)
        row4.pack(fill=tk.X)
        self.unrealized_pnl_label = ttk.Label(row4, text="未實現損益：$0", font=("", 10))
        self.unrealized_pnl_label.pack(side=tk.LEFT)
        
        # 第五行：報酬率
        row5 = ttk.Frame(summary_frame)
        row5.pack(fill=tk.X)
        self.return_label = ttk.Label(row5, text="報酬率：0.00%", font=("", 10))
        self.return_label.pack(side=tk.LEFT)
        
        # 第六行：現金餘額
        row6 = ttk.Frame(summary_frame)
        row6.pack(fill=tk.X)
        self.cash_label = ttk.Label(row6, text="現金餘額：$0", font=("", 9), foreground="gray")
        self.cash_label.pack(side=tk.LEFT)
        
        # 庫存列表（增加欄位）
        columns = ('symbol', 'name', 'qty', 'avg_cost', 'price', 'cost_total', 'market_val', 'pnl', 'pnl_pct')
        self.inventory_tree = ttk.Treeview(inventory_frame, columns=columns, 
                                           show='headings', height=6)
        
        self.inventory_tree.heading('symbol', text='代碼')
        self.inventory_tree.heading('name', text='名稱')
        self.inventory_tree.heading('qty', text='股數')
        self.inventory_tree.heading('avg_cost', text='成本均價')
        self.inventory_tree.heading('price', text='現價')
        self.inventory_tree.heading('cost_total', text='付出成本')
        self.inventory_tree.heading('market_val', text='市值')
        self.inventory_tree.heading('pnl', text='損益')
        self.inventory_tree.heading('pnl_pct', text='%')
        
        self.inventory_tree.column('symbol', width=50)
        self.inventory_tree.column('name', width=55)
        self.inventory_tree.column('qty', width=45)
        self.inventory_tree.column('avg_cost', width=55)
        self.inventory_tree.column('price', width=50)
        self.inventory_tree.column('cost_total', width=60)
        self.inventory_tree.column('market_val', width=60)
        self.inventory_tree.column('pnl', width=55)
        self.inventory_tree.column('pnl_pct', width=45)
        
        # 設定顏色標籤
        self.inventory_tree.tag_configure('profit', foreground='red')
        self.inventory_tree.tag_configure('loss', foreground='green')
        
        inv_scroll = ttk.Scrollbar(inventory_frame, orient=tk.VERTICAL, 
                                   command=self.inventory_tree.yview)
        self.inventory_tree.configure(yscrollcommand=inv_scroll.set)
        
        self.inventory_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inv_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _create_center_panel(self, parent):
        """建立中欄：交易LOG + 分析結果"""
        center_frame = ttk.Frame(parent)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # ============================================================
        # 分析結果區
        # ============================================================
        analysis_frame = ttk.LabelFrame(center_frame, text="📡 分析結果", padding="5")
        analysis_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # 工具列
        tool_frame = ttk.Frame(analysis_frame)
        tool_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.manual_btn = ttk.Button(tool_frame, text="🔍 手動分析", 
                                     command=self._manual_analyze)
        self.manual_btn.pack(side=tk.LEFT, padx=2)
        
        self.auto_btn = ttk.Button(tool_frame, text="▶️ 開始自動", 
                                   command=self._toggle_auto)
        self.auto_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(tool_frame, text="間隔：").pack(side=tk.LEFT, padx=(10, 2))
        self.interval_var = tk.StringVar(value="300")
        ttk.Entry(tool_frame, textvariable=self.interval_var, width=5).pack(side=tk.LEFT)
        ttk.Label(tool_frame, text="秒").pack(side=tk.LEFT)
        
        self.auto_status_label = ttk.Label(tool_frame, text="", foreground="gray")
        self.auto_status_label.pack(side=tk.RIGHT, padx=5)
        
        # 分析結果顯示
        self.analysis_text = scrolledtext.ScrolledText(analysis_frame, height=15, 
                                                       font=("Consolas", 9),
                                                       wrap=tk.WORD)
        self.analysis_text.pack(fill=tk.BOTH, expand=True)
        
        # 設定標籤樣式
        self.analysis_text.tag_configure('title', font=("", 10, "bold"), foreground="blue")
        self.analysis_text.tag_configure('buy', foreground="red")
        self.analysis_text.tag_configure('sell', foreground="green")
        self.analysis_text.tag_configure('warning', foreground="orange")
        self.analysis_text.tag_configure('info', foreground="gray")
        
        # ============================================================
        # 交易LOG區
        # ============================================================
        log_frame = ttk.LabelFrame(center_frame, text="📝 交易紀錄", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # 工具列
        log_tool_frame = ttk.Frame(log_frame)
        log_tool_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(log_tool_frame, text="🔄 重新載入", 
                   command=self._load_trade_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_tool_frame, text="🗑️ 清除LOG", 
                   command=self._clear_trade_log).pack(side=tk.LEFT, padx=2)
        ttk.Button(log_tool_frame, text="💾 匯出CSV", 
                   command=self._export_log_csv).pack(side=tk.LEFT, padx=2)
        
        # LOG 列表
        log_columns = ('time', 'action', 'symbol', 'qty', 'price', 'amount', 'reason')
        self.log_tree = ttk.Treeview(log_frame, columns=log_columns, 
                                     show='headings', height=8)
        
        self.log_tree.heading('time', text='時間')
        self.log_tree.heading('action', text='動作')
        self.log_tree.heading('symbol', text='股票')
        self.log_tree.heading('qty', text='股數')
        self.log_tree.heading('price', text='價格')
        self.log_tree.heading('amount', text='金額')
        self.log_tree.heading('reason', text='原因')
        
        self.log_tree.column('time', width=130)
        self.log_tree.column('action', width=50)
        self.log_tree.column('symbol', width=60)
        self.log_tree.column('qty', width=50)
        self.log_tree.column('price', width=60)
        self.log_tree.column('amount', width=80)
        self.log_tree.column('reason', width=150)
        
        # v4.4.7 修改：字體改為黑色，背景保持區分
        self.log_tree.tag_configure('buy', background='#ffe6e6', foreground='black')
        self.log_tree.tag_configure('sell', background='#e6ffe6', foreground='black')
        
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, 
                                   command=self.log_tree.yview)
        self.log_tree.configure(yscrollcommand=log_scroll.set)
        
        self.log_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _create_right_panel(self, parent):
        """建立右欄：存股名單管理"""
        right_frame = ttk.Frame(parent, width=320)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right_frame.pack_propagate(False)
        
        # ============================================================
        # 存股名單管理
        # ============================================================
        ignore_frame = ttk.LabelFrame(right_frame, text="🔒 存股名單（只看不動）", padding="5")
        ignore_frame.pack(fill=tk.BOTH, expand=True)
        
        # 說明
        ttk.Label(ignore_frame, text="在此名單中的股票不會被自動交易", 
                  foreground="gray", font=("", 9)).pack(anchor=tk.W)
        
        # 新增區 - 第一行：股票代碼
        add_frame = ttk.Frame(ignore_frame)
        add_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(add_frame, text="股票代碼：").pack(side=tk.LEFT)
        self.ignore_symbol_var = tk.StringVar()
        self.ignore_symbol_entry = ttk.Entry(add_frame, textvariable=self.ignore_symbol_var, 
                                             width=10)
        self.ignore_symbol_entry.pack(side=tk.LEFT, padx=2)
        
        # 備註區 - 第二行
        note_frame = ttk.Frame(ignore_frame)
        note_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(note_frame, text="備　　註：").pack(side=tk.LEFT)
        self.ignore_note_var = tk.StringVar()
        self.ignore_note_entry = ttk.Entry(note_frame, textvariable=self.ignore_note_var, 
                                           width=20)
        self.ignore_note_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        # 按鈕區 - 第三行
        btn_frame = ttk.Frame(ignore_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="➕ 新增", command=self._add_to_ignore,
                   width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="➖ 移除", command=self._remove_from_ignore,
                   width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📝 更新備註", command=self._update_ignore_note,
                   width=10).pack(side=tk.LEFT, padx=2)
        
        # 存股名單列表
        list_frame = ttk.Frame(ignore_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        columns = ('symbol', 'name', 'note')
        self.ignore_tree = ttk.Treeview(list_frame, columns=columns, 
                                        show='headings', height=10)
        
        self.ignore_tree.heading('symbol', text='代碼')
        self.ignore_tree.heading('name', text='名稱')
        self.ignore_tree.heading('note', text='備註')
        
        self.ignore_tree.column('symbol', width=60)
        self.ignore_tree.column('name', width=80)
        self.ignore_tree.column('note', width=130)
        
        self.ignore_tree.bind('<<TreeviewSelect>>', self._on_ignore_select)
        
        ignore_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, 
                                      command=self.ignore_tree.yview)
        self.ignore_tree.configure(yscrollcommand=ignore_scroll.set)
        
        self.ignore_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ignore_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 快速操作
        quick_frame = ttk.Frame(ignore_frame)
        quick_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(quick_frame, text="從自選股匯入", 
                   command=self._import_from_watchlist).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="💾 儲存", 
                   command=self._save_ignore_list).pack(side=tk.RIGHT, padx=2)
        
        # ============================================================
        # 自選股快速檢視
        # ============================================================
        watchlist_frame = ttk.LabelFrame(right_frame, text="📋 自選股清單", padding="5")
        watchlist_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # 自選股數量
        self.watchlist_count_label = ttk.Label(watchlist_frame, 
                                               text=f"共 {self.db.get_stock_count()} 檔自選股")
        self.watchlist_count_label.pack(anchor=tk.W)
        
        # 自選股列表
        wl_columns = ('symbol', 'name', 'status')
        self.watchlist_tree = ttk.Treeview(watchlist_frame, columns=wl_columns, 
                                           show='headings', height=8)
        
        self.watchlist_tree.heading('symbol', text='代碼')
        self.watchlist_tree.heading('name', text='名稱')
        self.watchlist_tree.heading('status', text='狀態')
        
        self.watchlist_tree.column('symbol', width=60)
        self.watchlist_tree.column('name', width=100)
        self.watchlist_tree.column('status', width=80)
        
        self.watchlist_tree.tag_configure('ignored', foreground='gray')
        
        wl_scroll = ttk.Scrollbar(watchlist_frame, orient=tk.VERTICAL, 
                                  command=self.watchlist_tree.yview)
        self.watchlist_tree.configure(yscrollcommand=wl_scroll.set)
        
        self.watchlist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        wl_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Button(watchlist_frame, text="🔄 重新載入", 
                   command=self._refresh_watchlist).pack(pady=5)
        
        # 初始載入
        self._refresh_watchlist()
    
    def _create_bottom_section(self, parent):
        """建立底部區域：狀態列"""
        bottom_frame = ttk.Frame(parent)
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 狀態訊息
        self.bottom_status = ttk.Label(bottom_frame, text="就緒", foreground="gray")
        self.bottom_status.pack(side=tk.LEFT)
        
        # 時間顯示
        self.time_label = ttk.Label(bottom_frame, text="")
        self.time_label.pack(side=tk.RIGHT)
        
        self._update_time()
    
    # ========================================================================
    # 事件處理
    # ========================================================================
    
    def _on_mode_change(self):
        """模式切換事件"""
        self._toggle_login_frame()
        self._update_status("模式已切換")
    
    def _toggle_login_frame(self):
        """切換登入框顯示"""
        if self.mode_var.get() == "LIVE":
            for child in self.login_frame.winfo_children():
                child.configure(state='normal')
        else:
            for child in self.login_frame.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Button)):
                    child.configure(state='disabled')
    
    def _browse_cert(self):
        """瀏覽憑證檔案"""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            title="選擇憑證檔案",
            filetypes=[("憑證檔案", "*.pfx *.p12"), ("所有檔案", "*.*")]
        )
        if filename:
            self.cert_path_var.set(filename)
    
    def _connect(self):
        """連線/初始化"""
        mode = self.mode_var.get()
        
        if mode == "SIMULATION":
            # 模擬模式：初始化 AutoTrader
            try:
                capital = float(self.sim_capital_var.get())
                self.trader = AutoTrader(mode='SIMULATION', initial_capital=capital)
                
                # 更新顯示
                self._refresh_inventory()
                
                self.status_label.config(text="🟢 模擬模式已連線", foreground="green")
                self._update_status("模擬模式初始化完成")
                self._log_message("系統初始化完成（模擬模式）", "info")
                
            except Exception as e:
                messagebox.showerror("錯誤", f"初始化失敗：{e}")
                self.status_label.config(text="🔴 初始化失敗", foreground="red")
        
        else:
            # 實單模式：需要登入
            if not FUBON_AVAILABLE:
                messagebox.showerror("錯誤", "未安裝 fubon_neo SDK，無法使用實單模式")
                return
            
            user_id = self.user_id_var.get().strip()
            password = self.password_var.get()
            cert_path = self.cert_path_var.get().strip()
            cert_password = self.cert_password_var.get()
            
            if not all([user_id, password, cert_path, cert_password]):
                messagebox.showwarning("警告", "請填寫完整的登入資訊")
                return
            
            try:
                self.trader = AutoTrader(mode='LIVE')
                result = self.trader.login(user_id, password, cert_path, cert_password)
                
                if result['success']:
                    self.status_label.config(text="🟢 實單模式已連線", foreground="green")
                    self._update_status("實單模式登入成功")
                    self._log_message("系統登入成功（實單模式）", "info")
                    self._refresh_inventory()
                else:
                    messagebox.showerror("登入失敗", result.get('message', '未知錯誤'))
                    self.status_label.config(text="🔴 登入失敗", foreground="red")
                    
            except Exception as e:
                messagebox.showerror("錯誤", f"連線失敗：{e}")
                self.status_label.config(text="🔴 連線失敗", foreground="red")
    
    def _manual_analyze(self):
        """手動執行分析"""
        if self.trader is None:
            messagebox.showwarning("警告", "請先連線/初始化")
            return
        
        self._update_status("正在執行分析...")
        self.manual_btn.config(state='disabled')
        
        def analyze_thread():
            try:
                result = self.trader.run_once()
                
                # 更新 UI（需要在主執行緒）
                self.root.after(0, lambda: self._on_analyze_complete(result))
                
            except Exception as e:
                self.root.after(0, lambda: self._on_analyze_error(str(e)))
        
        thread = threading.Thread(target=analyze_thread, daemon=True)
        thread.start()
    
    def _on_analyze_complete(self, result):
        """分析完成回調"""
        self.manual_btn.config(state='normal')
        self._update_status("分析完成")
        
        # 更新分析結果顯示
        self._display_analysis_result(result)
        
        # 更新庫存
        self._refresh_inventory()
        
        # 重新載入 LOG
        self._load_trade_log()
    
    def _on_analyze_error(self, error):
        """分析錯誤回調"""
        self.manual_btn.config(state='normal')
        self._update_status(f"分析錯誤：{error}")
        self._log_message(f"分析錯誤：{error}", "warning")
    
    def _display_analysis_result(self, result):
        """顯示分析結果"""
        self.analysis_text.delete(1.0, tk.END)
        
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.analysis_text.insert(tk.END, f"═══ 分析報告 {now} ═══\n\n", "title")
        
        if result.get('status') == 'no_data':
            self.analysis_text.insert(tk.END, "無可分析的股票\n", "warning")
            return
        
        # 摘要
        self.analysis_text.insert(tk.END, f"📊 分析股票數：{result.get('analysis_count', 0)}\n")
        self.analysis_text.insert(tk.END, f"🟢 買進訊號：{result.get('buy_signals', 0)} 檔\n", "buy")
        self.analysis_text.insert(tk.END, f"🔴 賣出訊號：{result.get('sell_signals', 0)} 檔\n", "sell")
        
        # 交易結果
        trades = result.get('trades', {})
        if trades:
            self.analysis_text.insert(tk.END, "\n═══ 交易執行結果 ═══\n", "title")
            
            for buy in trades.get('executed_buys', []):
                self.analysis_text.insert(tk.END, 
                    f"  🛒 買進 {buy['symbol']}: {buy['qty']}股 @ ${buy['price']:.2f}\n", "buy")
                self.analysis_text.insert(tk.END, 
                    f"     原因: {buy.get('reason', '')}\n", "info")
            
            for sell in trades.get('executed_sells', []):
                self.analysis_text.insert(tk.END, 
                    f"  💰 賣出 {sell['symbol']}: {sell['qty']}股 @ ${sell['price']:.2f}\n", "sell")
                pnl = sell.get('pnl', 0)
                pnl_tag = "buy" if pnl >= 0 else "sell"
                self.analysis_text.insert(tk.END, 
                    f"     損益: ${pnl:+,.0f} | 原因: {sell.get('reason', '')}\n", pnl_tag)
            
            for skip in trades.get('skipped', []):
                self.analysis_text.insert(tk.END, 
                    f"  ⏸️ 跳過 {skip['symbol']}: {skip.get('message', '')}\n", "warning")
            
            for err in trades.get('errors', []):
                self.analysis_text.insert(tk.END, 
                    f"  ❌ 錯誤 {err.get('symbol', '')}: {err.get('error', err.get('message', ''))}\n", "warning")
    
    def _toggle_auto(self):
        """切換自動執行"""
        if self.trader is None:
            messagebox.showwarning("警告", "請先連線/初始化")
            return
        
        if self.is_running:
            # 停止自動執行
            self.is_running = False
            self.auto_btn.config(text="▶️ 開始自動")
            self.auto_status_label.config(text="已停止", foreground="gray")
            self._update_status("自動執行已停止")
        else:
            # 開始自動執行
            self.is_running = True
            self.auto_btn.config(text="⏹️ 停止自動")
            self.auto_status_label.config(text="執行中...", foreground="green")
            self._update_status("自動執行已啟動")
            
            # 啟動背景執行緒
            self.auto_thread = threading.Thread(target=self._auto_run_loop, daemon=True)
            self.auto_thread.start()
    
    def _auto_run_loop(self):
        """自動執行迴圈"""
        while self.is_running and not self._closed:
            try:
                # 執行分析
                result = self.trader.run_once()
                
                # 更新 UI
                self.root.after(0, lambda r=result: self._on_analyze_complete(r))
                
                # 等待
                interval = int(self.interval_var.get())
                for _ in range(interval):
                    if not self.is_running or self._closed:
                        break
                    time.sleep(1)
                    
                    # 更新倒數
                    remaining = interval - _
                    self.root.after(0, lambda r=remaining: 
                        self.auto_status_label.config(text=f"下次掃描：{r}秒"))
                    
            except Exception as e:
                self.root.after(0, lambda: self._log_message(f"自動執行錯誤：{e}", "warning"))
                time.sleep(60)  # 錯誤後等待 1 分鐘
    
    # ========================================================================
    # 庫存與損益
    # ========================================================================
    
    def _refresh_inventory(self):
        """
        刷新庫存顯示
        
        根據選擇的帳戶類型（模擬/實單）顯示對應的庫存數據
        """
        # 清空列表
        for item in self.inventory_tree.get_children():
            self.inventory_tree.delete(item)
        
        account_type = self.inv_account_var.get()
        
        # ============================================================
        # 模擬帳戶
        # ============================================================
        if account_type == "SIM":
            self._refresh_simulation_inventory()
        
        # ============================================================
        # 實單帳戶
        # ============================================================
        else:
            self._refresh_live_inventory()
    
    def _refresh_simulation_inventory(self):
        """刷新模擬帳戶庫存"""
        try:
            # 讀取模擬數據檔案
            if not os.path.exists(AutoTraderConfig.SIMULATION_DATA_FILE):
                self._reset_inventory_display()
                self._update_status("模擬帳戶尚未建立")
                return
            
            with open(AutoTraderConfig.SIMULATION_DATA_FILE, 'r', encoding='utf-8') as f:
                sim_data = json.load(f)
            
            balance = sim_data.get('balance', 0)
            inventory = sim_data.get('inventory', {})
            initial_capital = sim_data.get('initial_capital', 1000000)
            
            # 計算損益
            total_cost = 0
            total_market_value = 0
            positions = []
            
            for symbol, pos in inventory.items():
                qty = pos.get('qty', 0)
                cost = pos.get('cost', 0)
                
                if qty <= 0:
                    continue
                
                # 使用最後更新的價格，若沒有則使用成本價
                current_price = pos.get('last_price', cost)
                
                cost_total = qty * cost
                market_value = qty * current_price
                pnl = market_value - cost_total
                pnl_pct = (pnl / cost_total * 100) if cost_total > 0 else 0
                
                total_cost += cost_total
                total_market_value += market_value
                
                # 取得股票名稱
                name = self._get_stock_name(symbol)
                
                positions.append({
                    'symbol': symbol,
                    'name': name,
                    'qty': qty,
                    'avg_cost': cost,
                    'current_price': current_price,
                    'cost_total': cost_total,
                    'market_value': market_value,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                })
            
            # 計算總資產和報酬
            total_assets = balance + total_market_value
            unrealized_pnl = total_market_value - total_cost
            total_return = total_assets - initial_capital
            total_return_pct = (total_return / initial_capital * 100) if initial_capital > 0 else 0
            
            # 更新摘要顯示
            self.total_assets_label.config(text=f"總資產：${total_assets:,.0f}")
            self.total_cost_label.config(text=f"付出成本：${total_cost:,.0f}")
            self.market_value_label.config(text=f"資產市值：${total_market_value:,.0f}")
            self.cash_label.config(text=f"現金餘額：${balance:,.0f}")
            
            pnl_color = "red" if unrealized_pnl >= 0 else "green"
            self.unrealized_pnl_label.config(
                text=f"未實現損益：${unrealized_pnl:+,.0f}",
                foreground=pnl_color
            )
            
            ret_color = "red" if total_return_pct >= 0 else "green"
            self.return_label.config(
                text=f"報酬率：{total_return_pct:+.2f}%",
                foreground=ret_color
            )
            
            # 填充庫存列表
            for pos in positions:
                tag = 'profit' if pos['pnl'] >= 0 else 'loss'
                self.inventory_tree.insert('', 'end', values=(
                    pos['symbol'],
                    pos['name'][:4] if pos['name'] else '',  # 名稱截短
                    f"{pos['qty']:,}",
                    f"{pos['avg_cost']:.2f}",
                    f"{pos['current_price']:.2f}",
                    f"{pos['cost_total']:,.0f}",
                    f"{pos['market_value']:,.0f}",
                    f"{pos['pnl']:+,.0f}",
                    f"{pos['pnl_pct']:+.1f}%"
                ), tags=(tag,))
            
            if not positions:
                self._update_status("模擬帳戶目前無持倉")
            else:
                self._update_status(f"模擬帳戶：{len(positions)} 檔持倉")
                
        except Exception as e:
            self._log_message(f"刷新模擬庫存錯誤：{e}", "warning")
            self._reset_inventory_display()
    
    def _refresh_live_inventory(self):
        """刷新實單帳戶庫存"""
        # v4.4.5 修正：優先使用傳入的 FubonTrader 實例
        fubon_trader = None
        
        # 1. 優先使用初始化時傳入的 FubonTrader
        if self.fubon_trader is not None:
            fubon_trader = self.fubon_trader
        
        # 2. 從 self.trader.trader 取得（如果 self.trader 是 AutoTrader）
        if fubon_trader is None and self.trader is not None:
            if hasattr(self.trader, 'trader') and self.trader.trader is not None:
                fubon_trader = self.trader.trader
        
        # 沒有可用的 FubonTrader
        if fubon_trader is None:
            self._reset_inventory_display()
            self._update_status("實單帳戶未連線，請從下單頁面登入")
            self._log_message("無法取得 FubonTrader 連線", "warning")
            return
        
        # 檢查是否已登入
        if not fubon_trader.is_logged_in:
            self._reset_inventory_display()
            self._update_status("實單帳戶未登入，請從下單頁面登入")
            return
        
        try:
            self._update_status("正在載入實單庫存...")
            
            # 從富邦 API 取得庫存
            result = fubon_trader.get_inventories()
            
            print(f"[GUI] get_inventories result: success={result.get('success')}, data_count={len(result.get('data', []))}")
            
            if not result.get('success'):
                self._reset_inventory_display()
                self._update_status(f"取得庫存失敗：{result.get('message', '')}")
                return
            
            inventory_data = result.get('data', [])
            
            total_cost = 0
            total_market_value = 0
            total_pnl = 0
            positions = []
            
            for item in inventory_data:
                # v4.4.5 修正：對應 fubon_trading.py 的欄位名稱
                symbol = item.get('symbol', '')
                name = item.get('name', '') or self._get_stock_name(symbol)
                qty = item.get('qty', 0)  # 修正：qty 而非 quantity
                cost = item.get('price_avg', 0)  # 修正：price_avg 而非 cost_price
                current_price = item.get('price_now', 0)  # 修正：price_now 而非 current_price
                pnl = item.get('pnl', 0)  # API 已計算的損益
                pnl_pct = item.get('pnl_percent', 0)  # API 已計算的報酬率
                
                print(f"[GUI] 庫存項目: {symbol} {name} qty={qty} cost={cost} price={current_price} pnl={pnl}")
                
                if qty <= 0:
                    continue
                
                cost_total = qty * cost
                market_value = qty * current_price if current_price > 0 else cost_total
                
                # 如果 API 沒有提供損益，自行計算
                if pnl == 0 and cost > 0 and current_price > 0:
                    pnl = market_value - cost_total
                    pnl_pct = (pnl / cost_total * 100) if cost_total > 0 else 0
                
                total_cost += cost_total
                total_market_value += market_value
                total_pnl += pnl
                
                positions.append({
                    'symbol': symbol,
                    'name': name,
                    'qty': qty,
                    'avg_cost': cost,
                    'current_price': current_price,
                    'cost_total': cost_total,
                    'market_value': market_value,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                })
            
            # 更新摘要
            self.total_assets_label.config(text=f"總資產：${total_market_value:,.0f}")
            self.total_cost_label.config(text=f"付出成本：${total_cost:,.0f}")
            self.market_value_label.config(text=f"資產市值：${total_market_value:,.0f}")
            self.cash_label.config(text=f"現金餘額：（需查詢）")
            
            pnl_color = "red" if total_pnl >= 0 else "green"
            self.unrealized_pnl_label.config(
                text=f"未實現損益：${total_pnl:+,.0f}",
                foreground=pnl_color
            )
            
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            ret_color = "red" if total_pnl_pct >= 0 else "green"
            self.return_label.config(
                text=f"報酬率：{total_pnl_pct:+.2f}%",
                foreground=ret_color
            )
            
            # 填充庫存列表
            for pos in positions:
                tag = 'profit' if pos['pnl'] >= 0 else 'loss'
                self.inventory_tree.insert('', 'end', values=(
                    pos['symbol'],
                    pos['name'][:4] if pos['name'] else '',
                    f"{pos['qty']:,}",
                    f"{pos['avg_cost']:.2f}",
                    f"{pos['current_price']:.2f}",
                    f"{pos['cost_total']:,.0f}",
                    f"{pos['market_value']:,.0f}",
                    f"{pos['pnl']:+,.0f}",
                    f"{pos['pnl_pct']:+.1f}%"
                ), tags=(tag,))
            
            if not positions:
                self._update_status("實單帳戶目前無持倉")
            else:
                self._update_status(f"已載入 {len(positions)} 筆庫存")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log_message(f"刷新實單庫存錯誤：{e}", "warning")
            self._reset_inventory_display()
    
    def _reset_inventory_display(self):
        """重置庫存顯示為空"""
        self.total_assets_label.config(text="總資產：$0")
        self.total_cost_label.config(text="付出成本：$0")
        self.market_value_label.config(text="資產市值：$0")
        self.unrealized_pnl_label.config(text="未實現損益：$0", foreground="gray")
        self.return_label.config(text="報酬率：0.00%", foreground="gray")
        self.cash_label.config(text="現金餘額：$0")
    
    def _get_stock_name(self, symbol: str) -> str:
        """取得股票名稱"""
        try:
            import twstock
            symbol = str(symbol)
            if symbol in twstock.codes:
                return twstock.codes[symbol].name
        except:
            pass
        return ""
    
    def _load_simulation_preview(self):
        """載入模擬數據預覽"""
        try:
            if os.path.exists(AutoTraderConfig.SIMULATION_DATA_FILE):
                with open(AutoTraderConfig.SIMULATION_DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.sim_capital_var.set(str(int(data.get('initial_capital', 1000000))))
                self.sim_balance_label.config(text=f"${data.get('balance', 0):,.0f}")
        except:
            pass
    
    # ========================================================================
    # 交易 LOG
    # ========================================================================
    
    def _load_trade_log(self):
        """載入交易紀錄"""
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)
        
        try:
            if os.path.exists(AutoTraderConfig.TRADE_LOG_FILE):
                with open(AutoTraderConfig.TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                
                # 倒序顯示（最新在前）
                for log in reversed(logs[-100:]):  # 只顯示最近 100 筆
                    action = log.get('action', '')
                    tag = 'buy' if action == 'BUY' else 'sell'
                    
                    # 計算金額
                    if action == 'BUY':
                        amount = log.get('cost', 0)
                    else:
                        amount = log.get('proceeds', 0)
                    
                    # 格式化時間
                    time_str = log.get('time', '')
                    if time_str:
                        try:
                            dt = datetime.datetime.fromisoformat(time_str)
                            time_str = dt.strftime('%m/%d %H:%M:%S')
                        except:
                            pass
                    
                    self.log_tree.insert('', 'end', values=(
                        time_str,
                        action,
                        log.get('symbol', ''),
                        log.get('qty', 0),
                        f"{log.get('price', 0):.2f}",
                        f"${amount:,.0f}",
                        log.get('reason', '')[:20]
                    ), tags=(tag,))
                    
        except Exception as e:
            self._log_message(f"載入交易紀錄錯誤：{e}", "warning")
    
    def _clear_trade_log(self):
        """清除交易紀錄"""
        if messagebox.askyesno("確認", "確定要清除所有交易紀錄嗎？"):
            try:
                if os.path.exists(AutoTraderConfig.TRADE_LOG_FILE):
                    os.remove(AutoTraderConfig.TRADE_LOG_FILE)
                self._load_trade_log()
                self._update_status("交易紀錄已清除")
            except Exception as e:
                messagebox.showerror("錯誤", f"清除失敗：{e}")
    
    def _export_log_csv(self):
        """匯出交易紀錄為 CSV"""
        from tkinter import filedialog
        
        filename = filedialog.asksaveasfilename(
            title="匯出交易紀錄",
            defaultextension=".csv",
            filetypes=[("CSV 檔案", "*.csv")]
        )
        
        if filename:
            try:
                import csv
                
                with open(AutoTraderConfig.TRADE_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
                
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['時間', '動作', '股票', '股數', '價格', '金額', '損益', '原因'])
                    
                    for log in logs:
                        writer.writerow([
                            log.get('time', ''),
                            log.get('action', ''),
                            log.get('symbol', ''),
                            log.get('qty', 0),
                            log.get('price', 0),
                            log.get('cost', 0) or log.get('proceeds', 0),
                            log.get('pnl', ''),
                            log.get('reason', '')
                        ])
                
                self._update_status(f"已匯出至 {filename}")
                
            except Exception as e:
                messagebox.showerror("錯誤", f"匯出失敗：{e}")
    
    # ========================================================================
    # 存股名單管理
    # ========================================================================
    
    def _load_ignore_list(self) -> Dict:
        """載入存股名單"""
        try:
            if os.path.exists(AutoTraderConfig.IGNORE_LIST_FILE):
                with open(AutoTraderConfig.IGNORE_LIST_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        
        return {
            'description': '存股黑名單',
            'symbols': [],
            'notes': {},
            'updated_at': datetime.datetime.now().isoformat()
        }
    
    def _save_ignore_list(self):
        """儲存存股名單"""
        try:
            self.ignore_list['updated_at'] = datetime.datetime.now().isoformat()
            with open(AutoTraderConfig.IGNORE_LIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.ignore_list, f, ensure_ascii=False, indent=2)
            self._update_status("存股名單已儲存")
            
            # 同步到 trader
            if self.trader:
                self.trader.ignore_list = self.ignore_list.get('symbols', [])
                
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存失敗：{e}")
    
    def _refresh_ignore_list_display(self):
        """刷新存股名單顯示"""
        for item in self.ignore_tree.get_children():
            self.ignore_tree.delete(item)
        
        symbols = self.ignore_list.get('symbols', [])
        notes = self.ignore_list.get('notes', {})
        
        for symbol in symbols:
            # 確保 symbol 是字串
            symbol = str(symbol)
            
            # 嘗試取得股票名稱
            name = ""
            try:
                import twstock
                if symbol in twstock.codes:
                    name = twstock.codes[symbol].name
            except:
                pass
            
            note = notes.get(symbol, '') or notes.get(str(symbol), '')
            self.ignore_tree.insert('', 'end', values=(symbol, name, note))
    
    def _add_to_ignore(self):
        """新增存股"""
        symbol = self.ignore_symbol_var.get().strip()
        note = self.ignore_note_var.get().strip()
        
        if not symbol:
            messagebox.showwarning("警告", "請輸入股票代碼")
            return
        
        # 確保 symbol 是字串
        symbol = str(symbol)
        
        symbols = self.ignore_list.get('symbols', [])
        symbols_str = [str(s) for s in symbols]
        
        if symbol in symbols_str:
            messagebox.showinfo("提示", f"{symbol} 已在存股名單中")
            return
        
        symbols.append(symbol)
        self.ignore_list['symbols'] = symbols
        
        if note:
            if 'notes' not in self.ignore_list:
                self.ignore_list['notes'] = {}
            self.ignore_list['notes'][symbol] = note
        
        self._save_ignore_list()
        self._refresh_ignore_list_display()
        self._refresh_watchlist()
        
        # 清空輸入
        self.ignore_symbol_var.set('')
        self.ignore_note_var.set('')
        
        self._update_status(f"已將 {symbol} 加入存股名單")
    
    def _remove_from_ignore(self):
        """移除存股 - 修復前導零問題"""
        selection = self.ignore_tree.selection()
        if not selection:
            # 嘗試使用輸入框的值
            symbol = self.ignore_symbol_var.get().strip()
            if not symbol:
                messagebox.showwarning("警告", "請選擇或輸入要移除的股票")
                return
        else:
            item = selection[0]
            display_symbol = str(self.ignore_tree.item(item)['values'][0])
            
            # 從原始 symbols 列表中找到正確的 symbol
            symbols = self.ignore_list.get('symbols', [])
            symbol = display_symbol
            
            for s in symbols:
                s_str = str(s)
                if s_str == display_symbol or s_str.lstrip('0') == display_symbol or s_str == display_symbol.zfill(4):
                    symbol = s_str
                    break
        
        symbols = self.ignore_list.get('symbols', [])
        
        # 尋找並移除
        found = False
        for i, s in enumerate(symbols):
            s_str = str(s)
            if s_str == symbol or s_str.lstrip('0') == symbol.lstrip('0'):
                symbols.pop(i)
                found = True
                break
        
        if found:
            self.ignore_list['symbols'] = symbols
            
            # 移除備註
            notes = self.ignore_list.get('notes', {})
            if symbol in notes:
                del notes[symbol]
            
            self._save_ignore_list()
            self._refresh_ignore_list_display()
            self._refresh_watchlist()
            
            self._update_status(f"已將 {symbol} 從存股名單移除")
        else:
            messagebox.showinfo("提示", f"{symbol} 不在存股名單中")
    
    def _update_ignore_note(self):
        """更新存股備註 - 修復前導零問題"""
        selection = self.ignore_tree.selection()
        symbol = self.ignore_symbol_var.get().strip()
        note = self.ignore_note_var.get().strip()
        
        if not symbol:
            if selection:
                item = selection[0]
                display_symbol = str(self.ignore_tree.item(item)['values'][0])
                
                # 從原始 symbols 列表中找到正確的 symbol
                symbols = self.ignore_list.get('symbols', [])
                symbol = display_symbol
                for s in symbols:
                    s_str = str(s)
                    if s_str == display_symbol or s_str.lstrip('0') == display_symbol or s_str == display_symbol.zfill(4):
                        symbol = s_str
                        break
            else:
                messagebox.showwarning("警告", "請選擇或輸入股票代碼")
                return
        
        symbols = self.ignore_list.get('symbols', [])
        
        # 尋找正確的 symbol
        actual_symbol = None
        for s in symbols:
            s_str = str(s)
            if s_str == symbol or s_str.lstrip('0') == symbol.lstrip('0'):
                actual_symbol = s_str
                break
        
        if not actual_symbol:
            messagebox.showwarning("警告", f"{symbol} 不在存股名單中，請先新增")
            return
        
        # 更新備註
        if 'notes' not in self.ignore_list:
            self.ignore_list['notes'] = {}
        
        if note:
            self.ignore_list['notes'][actual_symbol] = note
        elif actual_symbol in self.ignore_list['notes']:
            del self.ignore_list['notes'][actual_symbol]
        
        self._save_ignore_list()
        self._refresh_ignore_list_display()
        
        self._update_status(f"已更新 {actual_symbol} 的備註")
    
    def _on_ignore_select(self, event):
        """選擇存股項目 - 修復前導零問題"""
        selection = self.ignore_tree.selection()
        if selection:
            item = selection[0]
            values = self.ignore_tree.item(item)['values']
            
            # Treeview 可能會將 '0050' 轉為 50，需要從原始數據中找回正確的 symbol
            display_symbol = str(values[0]) if values else ''
            
            # 從原始 symbols 列表中找到匹配的 symbol
            symbols = self.ignore_list.get('symbols', [])
            actual_symbol = display_symbol
            
            for s in symbols:
                s_str = str(s)
                # 檢查是否匹配（考慮前導零被移除的情況）
                if s_str == display_symbol or s_str.lstrip('0') == display_symbol or s_str == display_symbol.zfill(4):
                    actual_symbol = s_str
                    break
            
            # 取得備註
            notes = self.ignore_list.get('notes', {})
            note = notes.get(actual_symbol, '')
            
            self.ignore_symbol_var.set(actual_symbol)
            self.ignore_note_var.set(note)
    
    def _import_from_watchlist(self):
        """從自選股匯入存股名單"""
        # 建立選擇對話框
        dialog = tk.Toplevel(self.root)
        dialog.title("選擇要加入存股名單的股票")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        
        ttk.Label(dialog, text="勾選要加入存股名單的股票：").pack(pady=10)
        
        # 列表框
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        stocks = self.db.get_all_stocks()
        check_vars = {}
        
        canvas = tk.Canvas(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        existing = self.ignore_list.get('symbols', [])
        
        for stock in stocks:
            symbol = stock[0]
            name = stock[1] or symbol
            
            var = tk.BooleanVar(value=symbol in existing)
            check_vars[symbol] = var
            
            cb = ttk.Checkbutton(scrollable_frame, text=f"{symbol} {name}", variable=var)
            cb.pack(anchor=tk.W, pady=2)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def apply():
            selected = [s for s, v in check_vars.items() if v.get()]
            self.ignore_list['symbols'] = selected
            self._save_ignore_list()
            self._refresh_ignore_list_display()
            self._refresh_watchlist()
            dialog.destroy()
            self._update_status(f"已更新存股名單（{len(selected)} 檔）")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="確定", command=apply).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    # ========================================================================
    # 自選股顯示
    # ========================================================================
    
    def _refresh_watchlist(self):
        """刷新自選股顯示"""
        for item in self.watchlist_tree.get_children():
            self.watchlist_tree.delete(item)
        
        stocks = self.db.get_all_stocks()
        ignore_symbols = self.ignore_list.get('symbols', [])
        
        self.watchlist_count_label.config(text=f"共 {len(stocks)} 檔自選股")
        
        for stock in stocks:
            symbol = stock[0]
            name = stock[1] or symbol
            
            if symbol in ignore_symbols:
                status = "🔒 存股"
                tag = 'ignored'
            else:
                status = "📊 交易"
                tag = ''
            
            self.watchlist_tree.insert('', 'end', values=(symbol, name, status), tags=(tag,))
    
    # ========================================================================
    # 設定管理
    # ========================================================================
    
    def _save_settings(self):
        """
        儲存設定（v4.4.7 更新：儲存至檔案並立即生效）
        
        設定會同時：
        1. 更新到 AutoTraderConfig（記憶體中立即生效）
        2. 儲存到 auto_trader_settings.json（持久化）
        """
        try:
            # 更新 AutoTraderConfig
            live_budget = float(self.live_budget_var.get())
            position_pct = float(self.position_pct_var.get()) / 100
            min_rr = float(self.min_rr_var.get())
            
            AutoTraderConfig.MAX_INVESTMENT_BUDGET = live_budget
            AutoTraderConfig.MAX_SINGLE_POSITION_PCT = position_pct
            AutoTraderConfig.MIN_RR_RATIO = min_rr
            
            # v4.4.5 新增：停損百分比
            stop_loss_pct = float(self.stop_loss_pct_var.get()) / 100
            if stop_loss_pct <= 0 or stop_loss_pct > 0.5:
                messagebox.showwarning("警告", "停損百分比應在 1% ~ 50% 之間")
                return
            AutoTraderConfig.STOP_LOSS_PCT = stop_loss_pct
            
            # v4.4.6 新增：零股與信心度設定
            AutoTraderConfig.ENABLE_ODD_LOT = self.enable_odd_lot_var.get()
            AutoTraderConfig.REQUIRE_HIGH_CONFIDENCE = self.require_high_confidence_var.get()
            
            # v4.4.7 新增：儲存到檔案（持久化）
            settings = {
                'live_budget': live_budget,
                'position_pct': position_pct * 100,  # 存百分比
                'min_rr': min_rr,
                'stop_loss_pct': stop_loss_pct * 100,  # 存百分比
                'enable_odd_lot': AutoTraderConfig.ENABLE_ODD_LOT,
                'require_high_confidence': AutoTraderConfig.REQUIRE_HIGH_CONFIDENCE,
                'saved_at': datetime.datetime.now().isoformat()
            }
            
            settings_file = 'auto_trader_settings.json'
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            
            # 組合狀態訊息
            status_parts = [
                f"可交易金額: ${live_budget:,.0f}",
                f"停損線: {stop_loss_pct*100:.0f}%"
            ]
            if AutoTraderConfig.ENABLE_ODD_LOT:
                status_parts.append("零股:開")
            else:
                status_parts.append("零股:關")
            if AutoTraderConfig.REQUIRE_HIGH_CONFIDENCE:
                status_parts.append("信心度:High")
            else:
                status_parts.append("信心度:Medium+")
            
            self._update_status(f"設定已儲存並立即生效（{', '.join(status_parts)}）")
            self._log_message(f"設定已儲存: 可交易金額=${live_budget:,.0f}", "info")
            messagebox.showinfo("成功", f"設定已儲存並立即生效\n\n可交易金額上限: ${live_budget:,.0f}")
            
        except ValueError as e:
            messagebox.showerror("錯誤", f"設定值格式錯誤：{e}")
    
    def _load_settings(self):
        """
        v4.4.7 新增：載入設定檔
        
        從 auto_trader_settings.json 讀取並套用設定
        """
        settings_file = 'auto_trader_settings.json'
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 套用到 GUI
                if 'live_budget' in settings:
                    self.live_budget_var.set(str(int(settings['live_budget'])))
                    AutoTraderConfig.MAX_INVESTMENT_BUDGET = settings['live_budget']
                
                if 'position_pct' in settings:
                    self.position_pct_var.set(str(settings['position_pct']))
                    AutoTraderConfig.MAX_SINGLE_POSITION_PCT = settings['position_pct'] / 100
                
                if 'min_rr' in settings:
                    self.min_rr_var.set(str(settings['min_rr']))
                    AutoTraderConfig.MIN_RR_RATIO = settings['min_rr']
                
                if 'stop_loss_pct' in settings:
                    self.stop_loss_pct_var.set(str(settings['stop_loss_pct']))
                    AutoTraderConfig.STOP_LOSS_PCT = settings['stop_loss_pct'] / 100
                
                if 'enable_odd_lot' in settings:
                    self.enable_odd_lot_var.set(settings['enable_odd_lot'])
                    AutoTraderConfig.ENABLE_ODD_LOT = settings['enable_odd_lot']
                
                if 'require_high_confidence' in settings:
                    self.require_high_confidence_var.set(settings['require_high_confidence'])
                    AutoTraderConfig.REQUIRE_HIGH_CONFIDENCE = settings['require_high_confidence']
                
                print(f"[AutoTraderGUI] 已載入設定: 可交易金額=${settings.get('live_budget', 0):,.0f}")
                return True
        except Exception as e:
            print(f"[AutoTraderGUI] 載入設定失敗: {e}")
        return False
    
    def _reset_simulation(self):
        """重置模擬帳戶"""
        if not messagebox.askyesno("確認", "確定要重置模擬帳戶嗎？\n所有模擬交易紀錄將被清除。"):
            return
        
        try:
            # 刪除模擬數據檔案
            if os.path.exists(AutoTraderConfig.SIMULATION_DATA_FILE):
                os.remove(AutoTraderConfig.SIMULATION_DATA_FILE)
            
            # 重新初始化
            if self.trader and self.mode_var.get() == "SIMULATION":
                capital = float(self.sim_capital_var.get())
                self.trader = AutoTrader(mode='SIMULATION', initial_capital=capital)
            
            self._refresh_inventory()
            self._update_status("模擬帳戶已重置")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"重置失敗：{e}")
    
    # ========================================================================
    # 輔助函數
    # ========================================================================
    
    def _update_status(self, message):
        """更新狀態訊息"""
        self.bottom_status.config(text=message)
    
    def _log_message(self, message, tag="info"):
        """在分析結果區寫入訊息"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        self.analysis_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.analysis_text.see(tk.END)
    
    def _update_time(self):
        """更新時間顯示"""
        if self._closed:
            return
        
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.time_label.config(text=now)
        self.root.after(1000, self._update_time)
    
    def _on_close(self):
        """關閉視窗"""
        if self.is_running:
            if not messagebox.askyesno("確認", "自動交易正在執行中，確定要關閉嗎？"):
                return
            self.is_running = False
        
        self._closed = True
        
        if self.standalone:
            self.root.quit()
        else:
            self.root.destroy()
    
    def run(self):
        """啟動 GUI（獨立模式用）"""
        if self.standalone:
            self.root.mainloop()


# ============================================================================
# 從主程式開啟的入口函數
# ============================================================================

def open_auto_trader_gui(parent=None, fubon_trader=None):
    """
    從主程式開啟 AutoTrader GUI
    
    Args:
        parent: 父視窗
        fubon_trader: 已登入的 FubonTrader 實例（可選）
    
    Returns:
        AutoTraderGUI: GUI 實例
    """
    gui = AutoTraderGUI(parent=parent, standalone=False, fubon_trader=fubon_trader)
    return gui


# ============================================================================
# 主程式入口
# ============================================================================

if __name__ == '__main__':
    # 獨立執行
    app = AutoTraderGUI(standalone=True)
    app.run()
