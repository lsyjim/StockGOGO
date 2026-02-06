"""
ui_integration_guide.py - UI 整合指南與關鍵程式碼片段

================================================================================
版本: v4.5.17
用途: 提供 main.py 的 UI 修改指南，將左側面板改為分頁設計

================================================================================
修改概覽:
================================================================================

1. 將 _create_left_panel 改為 ttk.Notebook 分頁設計
   - 分頁 1：個股分析（保留原有功能）
   - 分頁 2：市場熱點（新功能）

2. 底部自選股面板改為可拉伸的 PanedWindow
   - 橫向貫穿底部
   - 支援產業分組顯示

3. 整合 MarketTrendManager

================================================================================
"""

# ============================================================================
# 需要在 main.py 頂部添加的 import
# ============================================================================

IMPORTS_TO_ADD = '''
# v4.5.17 新增：市場熱點模組
try:
    from market_trend_manager import MarketTrendManager, SectorInfo, StockInfo
    from advanced_analyzers import VCPScanner, RelativeStrengthCalculator, ATRStopLossCalculator, AdvancedAnalyzer
    TREND_MODULE_AVAILABLE = True
except ImportError:
    TREND_MODULE_AVAILABLE = False
    print("[Main] 警告：market_trend_manager 或 advanced_analyzers 模組未找到")

try:
    from database_upgrade import WatchlistDatabaseV2, upgrade_database
    # 自動執行資料庫升級
    upgrade_database()
    DATABASE_V2_AVAILABLE = True
except ImportError:
    DATABASE_V2_AVAILABLE = False
    print("[Main] 警告：database_upgrade 模組未找到")
'''


# ============================================================================
# 修改後的 _create_left_panel 方法（關鍵程式碼）
# ============================================================================

NEW_CREATE_LEFT_PANEL = '''
    def _create_left_panel(self, parent):
        """
        建立左側控制面板
        
        v4.5.17 重構：改為 ttk.Notebook 分頁設計
        - 分頁 1：個股分析
        - 分頁 2：市場熱點
        """
        # ========================================
        # 創建分頁控制項
        # ========================================
        self.left_notebook = ttk.Notebook(parent)
        self.left_notebook.pack(fill=tk.BOTH, expand=True)
        
        # ========================================
        # 分頁 1：個股分析
        # ========================================
        stock_tab = ttk.Frame(self.left_notebook)
        self.left_notebook.add(stock_tab, text="🔍 個股分析")
        self._create_stock_analysis_tab(stock_tab)
        
        # ========================================
        # 分頁 2：市場熱點
        # ========================================
        market_tab = ttk.Frame(self.left_notebook)
        self.left_notebook.add(market_tab, text="📊 市場熱點")
        self._create_market_trend_tab(market_tab)
    
    def _create_stock_analysis_tab(self, parent):
        """
        創建個股分析分頁（原有功能）
        
        包含：股票查詢、策略回測、自選股快捷
        """
        # --- 股票查詢區塊 ---
        query_frame = ttk.LabelFrame(parent, text="🔍 股票查詢", padding=10)
        query_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 標題列（包含按鈕）
        header_line = ttk.Frame(query_frame)
        header_line.pack(fill=tk.X)
        
        ttk.Label(header_line, text="股票代碼：").pack(side=tk.LEFT)
        
        # 功能按鈕
        ranking_btn = ttk.Button(header_line, text="📊 排行", 
                                 command=self._show_market_ranking, width=8)
        ranking_btn.pack(side=tk.RIGHT)
        
        order_btn = ttk.Button(header_line, text="💰 下單", 
                               command=self._show_order_dialog, width=8)
        order_btn.pack(side=tk.RIGHT, padx=(0, 5))
        
        auto_btn = ttk.Button(header_line, text="🤖 自動", 
                              command=self._show_auto_trader, width=8)
        auto_btn.pack(side=tk.RIGHT, padx=(0, 5))
        
        # 輸入框
        input_frame = ttk.Frame(query_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        self.symbol_entry = ttk.Entry(input_frame, font=("Arial", 12))
        self.symbol_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.symbol_entry.bind('<Return>', lambda e: self.plot_chart())
        
        search_btn = ttk.Button(input_frame, text="查詢", command=self.plot_chart, width=8)
        search_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # 市場選擇
        market_frame = ttk.Frame(query_frame)
        market_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(market_frame, text="市場：").pack(side=tk.LEFT)
        self.market_var = tk.StringVar(value="台股")
        ttk.Radiobutton(market_frame, text="台股", variable=self.market_var, value="台股").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(market_frame, text="美股", variable=self.market_var, value="美股").pack(side=tk.LEFT)
        
        # 週期選擇
        period_frame = ttk.Frame(query_frame)
        period_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(period_frame, text="週期：").pack(anchor=tk.W)
        self.period_var = tk.StringVar(value="6mo")
        periods = [("1個月", "1mo"), ("3個月", "3mo"), ("6個月", "6mo"), ("1年", "1y")]
        for text, value in periods:
            ttk.Radiobutton(period_frame, text=text, variable=self.period_var, 
                          value=value, command=self.plot_chart).pack(anchor=tk.W)
        
        # 初始化圖表選項變數
        self.indicator_var = tk.StringVar(value="KD")
        self.show_ma_var = tk.BooleanVar(value=True)
        self.show_vol_var = tk.BooleanVar(value=True)
        self.show_bb_var = tk.BooleanVar(value=False)
        
        # --- 策略回測區塊 ---
        strategy_frame = ttk.LabelFrame(parent, text="📈 策略回測", padding=10)
        strategy_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(strategy_frame, text="選擇策略：").pack(anchor=tk.W)
        self.strategy_var = tk.StringVar(value="趨勢策略")
        strategies = ["趨勢策略", "動能策略", "通道策略", "均值回歸策略"]
        strategy_combo = ttk.Combobox(strategy_frame, textvariable=self.strategy_var, 
                                     values=strategies, state="readonly", width=20)
        strategy_combo.pack(fill=tk.X, pady=5)
        
        # 滑價設定
        slippage_frame = ttk.Frame(strategy_frame)
        slippage_frame.pack(fill=tk.X, pady=5)
        ttk.Label(slippage_frame, text="滑價(%)：").pack(side=tk.LEFT)
        self.slippage_var = tk.DoubleVar(value=0.3)
        slippage_spin = ttk.Spinbox(slippage_frame, from_=0, to=5, increment=0.1,
                                   textvariable=self.slippage_var, width=8)
        slippage_spin.pack(side=tk.LEFT, padx=5)
        
        btn_frame = ttk.Frame(strategy_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="執行回測", command=self.run_backtest).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="完整分析", command=self.show_analysis_report).pack(side=tk.LEFT, padx=2)
        
        # --- 快捷自選股（簡化版，完整版在底部） ---
        quick_watchlist = ttk.LabelFrame(parent, text="⭐ 快速選股", padding=5)
        quick_watchlist.pack(fill=tk.BOTH, expand=True)
        
        # 簡化的自選股列表
        self.quick_watchlist_tree = ttk.Treeview(quick_watchlist, 
            columns=("score", "signal"), 
            show="tree headings", 
            height=8
        )
        self.quick_watchlist_tree.heading("#0", text="股票")
        self.quick_watchlist_tree.heading("score", text="評分")
        self.quick_watchlist_tree.heading("signal", text="訊號")
        self.quick_watchlist_tree.column("#0", width=100)
        self.quick_watchlist_tree.column("score", width=50)
        self.quick_watchlist_tree.column("signal", width=80)
        self.quick_watchlist_tree.pack(fill=tk.BOTH, expand=True)
        self.quick_watchlist_tree.bind('<Double-1>', self.on_watchlist_double_click)
    
    def _create_market_trend_tab(self, parent):
        """
        創建市場熱點分頁（新功能）
        
        顯示強勢族群排行與領頭羊股票
        """
        # --- 強勢族群區塊 ---
        sector_frame = ttk.LabelFrame(parent, text="🔥 強勢族群 (5日動能)", padding=5)
        sector_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # 族群列表
        self.sector_tree = ttk.Treeview(sector_frame,
            columns=("momentum", "category", "leader"),
            show="tree headings",
            height=8
        )
        self.sector_tree.heading("#0", text="族群")
        self.sector_tree.heading("momentum", text="5D動能")
        self.sector_tree.heading("category", text="類別")
        self.sector_tree.heading("leader", text="領頭羊")
        
        self.sector_tree.column("#0", width=100)
        self.sector_tree.column("momentum", width=70)
        self.sector_tree.column("category", width=60)
        self.sector_tree.column("leader", width=100)
        
        # 顏色標籤
        self.sector_tree.tag_configure("hot", foreground="#FF4444")
        self.sector_tree.tag_configure("warm", foreground="#FF8800")
        self.sector_tree.tag_configure("cool", foreground="#4488FF")
        
        self.sector_tree.pack(fill=tk.BOTH, expand=True)
        self.sector_tree.bind('<<TreeviewSelect>>', self._on_sector_select)
        
        # --- 領頭羊區塊 ---
        leader_frame = ttk.LabelFrame(parent, text="🏆 族群成分股", padding=5)
        leader_frame.pack(fill=tk.BOTH, expand=True)
        
        self.leader_tree = ttk.Treeview(leader_frame,
            columns=("price", "change", "volume"),
            show="tree headings",
            height=6
        )
        self.leader_tree.heading("#0", text="股票")
        self.leader_tree.heading("price", text="股價")
        self.leader_tree.heading("change", text="漲跌%")
        self.leader_tree.heading("volume", text="成交量")
        
        self.leader_tree.column("#0", width=100)
        self.leader_tree.column("price", width=70)
        self.leader_tree.column("change", width=60)
        self.leader_tree.column("volume", width=80)
        
        self.leader_tree.tag_configure("up", foreground="#00AA00")
        self.leader_tree.tag_configure("down", foreground="#FF0000")
        
        self.leader_tree.pack(fill=tk.BOTH, expand=True)
        self.leader_tree.bind('<Double-1>', self._on_leader_double_click)
        
        # --- 控制按鈕 ---
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="🔄 重新整理", 
                  command=self._refresh_market_trends).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📊 詳細報告",
                  command=self._show_sector_report).pack(side=tk.LEFT, padx=2)
        
        # 狀態標籤
        self.sector_status_label = ttk.Label(btn_frame, text="點擊「重新整理」載入數據")
        self.sector_status_label.pack(side=tk.RIGHT)
        
        # 初始化 MarketTrendManager
        if TREND_MODULE_AVAILABLE:
            self._market_manager = MarketTrendManager()
        else:
            self._market_manager = None
    
    def _on_sector_select(self, event):
        """
        當選擇族群時，載入成分股
        """
        selection = self.sector_tree.selection()
        if not selection:
            return
        
        sector_id = selection[0]
        
        def load_constituents():
            if self._market_manager:
                stocks = self._market_manager.get_sector_constituents(sector_id)
                self.after(0, lambda: self._update_leader_tree(stocks))
        
        # 在背景線程中載入
        threading.Thread(target=load_constituents, daemon=True).start()
    
    def _on_leader_double_click(self, event):
        """
        雙擊領頭羊股票，載入到主圖表
        """
        selection = self.leader_tree.selection()
        if not selection:
            return
        
        item = self.leader_tree.item(selection[0])
        stock_text = item['text']  # 格式: "2330 台積電"
        
        if stock_text:
            symbol = stock_text.split()[0]
            self.symbol_entry.delete(0, tk.END)
            self.symbol_entry.insert(0, symbol)
            self.plot_chart()
    
    def _refresh_market_trends(self):
        """
        重新整理市場熱點數據
        """
        if not self._market_manager:
            self.sector_status_label.config(text="模組未載入")
            return
        
        self.sector_status_label.config(text="載入中...")
        
        def load_sectors():
            try:
                sectors = self._market_manager.get_hot_sectors(limit=15, force_refresh=True)
                self.after(0, lambda: self._update_sector_tree(sectors))
                self.after(0, lambda: self.sector_status_label.config(
                    text=f"更新時間: {datetime.now().strftime('%H:%M:%S')}"
                ))
            except Exception as e:
                self.after(0, lambda: self.sector_status_label.config(text=f"錯誤: {str(e)[:20]}"))
        
        threading.Thread(target=load_sectors, daemon=True).start()
    
    def _update_sector_tree(self, sectors):
        """
        更新族群列表
        """
        # 清空現有項目
        for item in self.sector_tree.get_children():
            self.sector_tree.delete(item)
        
        # 新增項目
        for sector in sectors:
            momentum = sector.momentum_5d
            
            # 決定顏色標籤
            if momentum >= 5:
                tag = "hot"
            elif momentum >= 2:
                tag = "warm"
            else:
                tag = "cool"
            
            leader_text = f"{sector.leader_symbol} {sector.leader_name}" if sector.leader_symbol else "-"
            
            self.sector_tree.insert("", "end",
                iid=sector.sector_id,
                text=sector.sector_name,
                values=(
                    f"{momentum:+.1f}%",
                    sector.category,
                    leader_text
                ),
                tags=(tag,)
            )
    
    def _update_leader_tree(self, stocks):
        """
        更新領頭羊列表
        """
        # 清空現有項目
        for item in self.leader_tree.get_children():
            self.leader_tree.delete(item)
        
        # 新增項目
        for stock in stocks:
            tag = "up" if stock.change_pct > 0 else "down" if stock.change_pct < 0 else ""
            
            self.leader_tree.insert("", "end",
                text=f"{stock.symbol} {stock.name}",
                values=(
                    f"${stock.price:.2f}",
                    f"{stock.change_pct:+.2f}%",
                    f"{stock.volume:,}"
                ),
                tags=(tag,)
            )
    
    def _show_sector_report(self):
        """
        顯示詳細的族群報告
        """
        if not self._market_manager:
            messagebox.showinfo("提示", "模組未載入")
            return
        
        try:
            from trend_scanner import SectorMomentumScanner
            scanner = SectorMomentumScanner()
            report = scanner.generate_report(limit=10)
            
            # 顯示報告視窗
            dialog = tk.Toplevel(self)
            dialog.title("📊 市場熱點詳細報告")
            dialog.geometry("700x500")
            
            text = tk.Text(dialog, wrap=tk.WORD, font=("Courier", 10))
            text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text.insert("1.0", report)
            text.config(state=tk.DISABLED)
            
            ttk.Button(dialog, text="關閉", command=dialog.destroy).pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("錯誤", f"生成報告失敗: {e}")
'''


# ============================================================================
# 底部自選股面板（PanedWindow 設計）
# ============================================================================

BOTTOM_WATCHLIST_PANEL = '''
    def _create_bottom_watchlist_panel(self, parent):
        """
        創建底部自選股面板
        
        v4.5.17 新增：使用 PanedWindow 可拉伸設計
        支援產業分組顯示
        """
        # 創建 PanedWindow（垂直分割）
        self.main_paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
        
        # 上方：主圖表區域
        chart_container = ttk.Frame(self.main_paned)
        self.main_paned.add(chart_container, weight=3)
        
        # 下方：自選股面板
        watchlist_container = ttk.Frame(self.main_paned)
        self.main_paned.add(watchlist_container, weight=1)
        
        self._create_enhanced_watchlist(watchlist_container)
        
        return chart_container  # 返回圖表容器供後續使用
    
    def _create_enhanced_watchlist(self, parent):
        """
        創建增強版自選股面板
        
        特點：
        1. 橫向完整寬度
        2. 產業分組顯示
        3. 完整量化欄位
        """
        # 標題列
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(header_frame, text="⭐ 自選股清單", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        
        # 控制按鈕
        ttk.Button(header_frame, text="🔄 刷新", command=self.refresh_all_watchlist).pack(side=tk.RIGHT, padx=2)
        ttk.Button(header_frame, text="➕ 新增", command=self._add_to_watchlist_dialog).pack(side=tk.RIGHT, padx=2)
        ttk.Button(header_frame, text="📊 相關性", command=self._show_correlation_analysis).pack(side=tk.RIGHT, padx=2)
        
        # 顯示模式
        self.watchlist_view_mode = tk.StringVar(value="grouped")
        ttk.Radiobutton(header_frame, text="分組", variable=self.watchlist_view_mode, 
                       value="grouped", command=self.refresh_watchlist).pack(side=tk.RIGHT, padx=5)
        ttk.Radiobutton(header_frame, text="列表", variable=self.watchlist_view_mode, 
                       value="list", command=self.refresh_watchlist).pack(side=tk.RIGHT)
        
        # Treeview（完整欄位）
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = (
            "score",      # 量化評分
            "trend",      # 趨勢狀態
            "chip",       # 籌碼訊號
            "bias",       # 乖離率
            "scenario",   # 場景
            "signal",     # 訊號
            "timing"      # 時機
        )
        
        self.watchlist_tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings", height=6)
        
        # 設定欄位標題
        self.watchlist_tree.heading("#0", text="股票")
        self.watchlist_tree.heading("score", text="評分")
        self.watchlist_tree.heading("trend", text="趨勢")
        self.watchlist_tree.heading("chip", text="籌碼")
        self.watchlist_tree.heading("bias", text="乖離%")
        self.watchlist_tree.heading("scenario", text="場景")
        self.watchlist_tree.heading("signal", text="訊號")
        self.watchlist_tree.heading("timing", text="時機")
        
        # 設定欄位寬度
        self.watchlist_tree.column("#0", width=120, minwidth=100)
        self.watchlist_tree.column("score", width=50, minwidth=40)
        self.watchlist_tree.column("trend", width=60, minwidth=50)
        self.watchlist_tree.column("chip", width=100, minwidth=80)
        self.watchlist_tree.column("bias", width=60, minwidth=50)
        self.watchlist_tree.column("scenario", width=100, minwidth=80)
        self.watchlist_tree.column("signal", width=100, minwidth=80)
        self.watchlist_tree.column("timing", width=100, minwidth=80)
        
        # 顏色標籤
        self.watchlist_tree.tag_configure("buy", foreground="#00AA00", font=("Arial", 10, "bold"))
        self.watchlist_tree.tag_configure("sell", foreground="#FF0000", font=("Arial", 10, "bold"))
        self.watchlist_tree.tag_configure("hold", foreground="#FF8800")
        self.watchlist_tree.tag_configure("wait", foreground="#888888")
        self.watchlist_tree.tag_configure("group", background="#E8E8E8", font=("Arial", 10, "bold"))
        self.watchlist_tree.tag_configure("overbought", background="#FFCCCC")  # 過熱
        self.watchlist_tree.tag_configure("oversold", background="#CCFFCC")    # 超跌
        
        # 滾動條
        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.watchlist_tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.watchlist_tree.xview)
        self.watchlist_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        # 佈局
        self.watchlist_tree.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # 事件綁定
        self.watchlist_tree.bind('<Double-1>', self.on_watchlist_double_click)
        self.watchlist_tree.bind('<Button-3>', self._show_watchlist_context_menu)
        
        # 狀態列
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X)
        self.watchlist_count_label = ttk.Label(status_frame, text="目前 0/100 檔")
        self.watchlist_count_label.pack(side=tk.LEFT)
        self.watchlist_update_label = ttk.Label(status_frame, text="")
        self.watchlist_update_label.pack(side=tk.RIGHT)
    
    def refresh_watchlist_grouped(self):
        """
        刷新自選股清單（分組模式）
        """
        # 清空現有項目
        for item in self.watchlist_tree.get_children():
            self.watchlist_tree.delete(item)
        
        # 取得分組數據
        if DATABASE_V2_AVAILABLE:
            db = WatchlistDatabaseV2()
            grouped = db.get_stocks_grouped_by_industry()
            summary = db.get_industry_summary()
        else:
            grouped = {'未分類': self.db.get_all_stocks()}
            summary = []
        
        total_count = 0
        
        # 創建產業彙總字典
        summary_dict = {s['industry']: s for s in summary}
        
        for industry, stocks in grouped.items():
            # 產業節點
            info = summary_dict.get(industry, {})
            avg_score = info.get('avg_score', 0)
            up_count = info.get('up_count', 0)
            down_count = info.get('down_count', 0)
            
            industry_text = f"{industry} [{len(stocks)}檔]"
            if avg_score > 0:
                industry_text += f" 平均{avg_score:.0f}分"
            
            industry_id = self.watchlist_tree.insert("", "end",
                text=industry_text,
                values=("", f"↑{up_count}/↓{down_count}", "", "", "", "", ""),
                tags=("group",),
                open=True
            )
            
            # 個股節點
            for stock in stocks:
                symbol = stock.get('symbol', '')
                name = stock.get('name', '')
                
                # 量化數據
                score = stock.get('quant_score', 0)
                trend = stock.get('trend_status', '待分析')
                chip = stock.get('chip_signal', '')
                bias = stock.get('bias_20', 0)
                
                # 建議解析
                rec_str = stock.get('recommendation', '')
                parts = rec_str.split('|') if rec_str else []
                scenario = parts[1] if len(parts) > 1 else ''
                signal = parts[2] if len(parts) > 2 else parts[0] if parts else ''
                timing = parts[3] if len(parts) > 3 else ''
                
                # 決定標籤
                tags = []
                if '買進' in signal or '積極' in signal:
                    tags.append("buy")
                elif '賣出' in signal or '減碼' in signal:
                    tags.append("sell")
                elif '觀望' in signal or '持有' in signal:
                    tags.append("hold")
                else:
                    tags.append("wait")
                
                # 乖離率標籤
                if bias > 10:
                    tags.append("overbought")
                elif bias < -10:
                    tags.append("oversold")
                
                self.watchlist_tree.insert(industry_id, "end",
                    text=f"{symbol} {name}",
                    values=(
                        f"{score:.0f}" if score else "-",
                        trend,
                        chip,
                        f"{bias:+.1f}%" if bias else "-",
                        scenario,
                        signal,
                        timing
                    ),
                    tags=tuple(tags)
                )
                total_count += 1
        
        self.watchlist_count_label.config(text=f"目前 {total_count}/100 檔")
        self.watchlist_update_label.config(text=f"更新: {datetime.now().strftime('%H:%M')}")
'''


# ============================================================================
# 產業自動標註邏輯
# ============================================================================

INDUSTRY_AUTO_TAG_LOGIC = '''
def auto_tag_stock_industry(symbol: str) -> str:
    """
    自動取得股票的產業資訊
    
    優先順序：
    1. WukongAPI - 從產業列表中查找
    2. twstock 模組 - 從本地資料查找
    3. 返回空字串
    
    Args:
        symbol: 股票代碼
    
    Returns:
        str: 產業名稱
    """
    industry = ''
    
    # 方法 1: 使用 WukongAPI
    try:
        from data_fetcher import WukongAPI
        
        # 取得所有產業
        industries = WukongAPI.get_industry_list() or []
        
        for ind in industries:
            ind_id = ind.get('id', '')
            ind_name = ind.get('name', '')
            
            # 取得該產業的成分股
            stocks = WukongAPI.get_industry_stocks(ind_id, 100) or []
            
            # 檢查是否包含目標股票
            for s in stocks:
                if s.get('symbol') == symbol:
                    industry = ind_name
                    break
            
            if industry:
                break
                
    except Exception as e:
        print(f"[AutoTag] WukongAPI 查詢失敗: {e}")
    
    # 方法 2: 使用 twstock
    if not industry:
        try:
            import twstock
            if symbol in twstock.codes:
                stock_info = twstock.codes[symbol]
                industry = stock_info.group or ''
        except Exception as e:
            print(f"[AutoTag] twstock 查詢失敗: {e}")
    
    return industry


def add_stock_with_auto_industry(db, symbol: str, name: str, market: str = 'TW') -> bool:
    """
    新增股票並自動標註產業
    
    Args:
        db: 資料庫實例（WatchlistDatabaseV2）
        symbol: 股票代碼
        name: 股票名稱
        market: 市場
    
    Returns:
        bool: 是否成功
    """
    # 取得產業資訊
    industry = auto_tag_stock_industry(symbol)
    
    if industry:
        print(f"[AutoTag] {symbol} 自動標註產業: {industry}")
    else:
        print(f"[AutoTag] {symbol} 無法自動判斷產業")
    
    # 新增到資料庫
    return db.add_stock(symbol, name, market, industry=industry)
'''


# ============================================================================
# 主程式（測試用）
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("  UI 整合指南")
    print("=" * 70)
    print()
    print("本文件包含以下程式碼片段：")
    print()
    print("1. IMPORTS_TO_ADD - 需要在 main.py 頂部添加的 import")
    print("2. NEW_CREATE_LEFT_PANEL - 修改後的 _create_left_panel 方法")
    print("3. BOTTOM_WATCHLIST_PANEL - 底部自選股面板程式碼")
    print("4. INDUSTRY_AUTO_TAG_LOGIC - 產業自動標註邏輯")
    print()
    print("請將這些程式碼整合到 main.py 中")
    print()
    print("=" * 70)
