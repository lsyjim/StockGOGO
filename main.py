"""
量化投資分析系統 v4.5.17 - 專業量化開發版本
=====================================
v4.5.17 高盛級量化系統整合與升級：
- 新增 MarketTrendManager 市場熱點管理器
- 新增 VCP Scanner 波動率壓縮偵測
- 新增 Relative Strength (RS) 相對強度計算
- 新增 ATR 動態停損計算器
- 資料庫 Schema 升級：新增 industry, tags, quant_score 等欄位
- UI 整合指南：分頁設計、底部自選股面板
- 邏輯審計報告：確認所有評分上限、時間跨度檢查正確

v4.5.16 形態失效檢查 (Pattern Invalidation)：
- W底：若收盤價跌破雙腳最低點，形態失效（趨勢向下）
- M頭：若收盤價漲破雙峰最高點，形態失效（趨勢向上）
- 頭肩底：若收盤價跌破頭部最低點，形態失效
- 頭肩頂：若收盤價漲破頭部最高點，形態失效
- 新增形成超時檢查：關鍵點形成超過 30 天未突破頸線，視為無效
- 解決「形態仍顯示 FORMING 但實際已被破壞」的漏洞

v4.5.15 效能優化：
- _detect_signals_for_chart 向量化重寫，速度提升 50-100 倍
- PatternAnalyzer._find_significant_points 使用 scipy.signal.argrelextrema
- 極值點尋找從 O(N*W) 降低為 O(N)，速度提升 10-50 倍

v4.5.14 重大修正（PatternAnalyzer 陳舊突破檢查）：
- 新增「陳舊突破檢查」(Stale Breakout Check)
- 檢查形態關鍵點（V2/P2）之後到昨天的最高/最低價
- 如果曾經突破頸線超過 5%，判定為「回測」而非「新鮮突破」
- 新增 PULLBACK_TEST 狀態，訊號降級為 hold
- 加入關鍵點資訊：左腳/右腳/左峰/右峰的日期和價格
- 解決「漲多拉回」被誤判為「起漲點」的問題

v4.5.13 修正：
- 修復 Python 3.13 Tkinter 多線程垃圾回收崩潰問題
- 新增 ThreadSafeGC 類別管理背景線程的垃圾回收
- 修復 dividend_yield 類型轉換錯誤（字串 vs 數字）

v4.5.12 重大架構變更（換腦手術）：
- 完全重構 DecisionMatrix.analyze，廢除舊的 determine_scenario_and_advice
- 統一使用雙軌評分系統（DualTrackScorer）作為唯一決策核心
- 解決「雙頭馬車」問題：自選股列表和報告現在使用相同邏輯
- 場景、建議、評分全部來自同一來源，確保資訊一致

v4.5.11 修正：
- 場景統一顯示簡短名稱（雙強共振、拉回佈局等）
- PatternAnalyzer 加入時效性濾網，過濾已漲完一波的過期形態
- 新增 max_distance_from_neckline 參數（預設 8%）

v4.5.10 修正：
- 統一報告和自選股清單的數據來源（使用 recommendation['overall']）
- 調整分數區間：High ≥65, Mid 45-65, Low ≤45（縮窄中性區間）
- 場景 I 改名：「蓄勢待發」→「動能交易」

v4.5.9 修正：
- 進場時機：使用 recommendation['action_timing']
- 場景：使用 DecisionMatrix 的 scenario_code

v4.5.8 更新：
- 增加各項指標的詳細說明
- 雙軌評分增加「基礎分+加減分=最終分數」欄位
- 籌碼面數據改為張數（原本是股數，已除以1000）
- 關閉按鈕改為深色背景（Mac相容）
- 基本面增加本益比計算過程（含EPS、股價、公式驗證）
- 技術指標增加說明文字

v4.5.7 修復：
- 修復 "bad screen distance '0 10'" 錯誤
- 原因：tk.Label 構造函數中 pady 只接受整數，不接受元組
- 元組 pady=(0, 10) 只能用在 .pack() 方法中

v4.5.6 修復：
- 完整修復滾輪綁定問題（加入 winfo_exists 檢查）
- 所有 Canvas 操作都加入 try-except 保護
- 視窗關閉時正確解綁全域事件

v4.5.5 修復：
- 完全重寫滾動框架，使用更簡單穩定的實現
- 簡化滾輪事件處理邏輯

v4.5.4 修復：
- 修復 "bad screen distance" 錯誤
- 修復 Canvas bbox 可能返回 None 的問題
- 修復 create_window 座標格式

v4.5.3 重大更新：
- 修復滾輪綁定問題（視窗關閉後不再報錯）
- 套用「現代暗黑金融風」配色方案
- 滑鼠進入/離開時自動綁定/解綁滾輪

v4.5.2 重大更新：
- 全新 Frame 區塊化報告設計（不再用文字畫線）
- 重點置頂：綜合評價、操作建議放最上方
- 使用 LabelFrame 組件，不會跑版

v4.5.1 修復：
- 修復 slice (None, 8, None) 錯誤
- 修復 components/breakdown 字段混淆問題
- 加強 None 值防護

v4.5.0 新增功能：

【雙軌評分系統 + 九大投資場景 v4.5.1】
31. 雙軌評分系統：
    - 短線波段評分：技術面為主（RSI/KD/MACD/趨勢/形態/量能）
    - 長線投資評分：基本面+籌碼面為主（PE/營收/外資/投信）
32. 九大投資場景矩陣：
    - A: 雙強共振（強力進攻型）
    - B: 拉回佈局（價值投資型）
    - C: 投機反彈（短線價差型）
    - D: 高檔震盪（獲利守成型）
    - E: 多空不明（雞肋觀望型）
    - F: 弱勢盤整（陰跌抵抗型）
    - G: 頭部確立（獲利了結型）
    - H: 空頭確認（逃命避險型）
    - I: 蓄勢待發（轉強觀察型）
33. 專業報告排版：區塊化呈現，重要結論前置

v4.3 新增功能：

【多因子決策矩陣 (Multi-Factor Decision Matrix)】
23. 核心決策變數：趨勢狀態、乖離位置、風險回報比、量能異常
24. 五大場景決策矩陣：
    - 場景 A：多頭過熱 → 持股續抱/暫停加碼
    - 場景 B：黃金買點 → 強烈建議買進
    - 場景 C：空頭超賣 → 不建議殺低/搶反彈
    - 場景 D：空頭確認 → 建議賣出
    - 場景 E：盤整震盪 → 區間操作
25. 強制濾網條件：
    - 濾網 1：風險回報比 < 1.5 → 降級
    - 濾網 2：創高量縮（假突破）→ 降級
26. 一致性建議輸出：消除「多頭叫追高、空頭叫殺低」的邏輯衝突

【歷史分析模式 (Historical Analysis Mode)】
27. 歷史日期選擇：可選擇任意過去日期進行分析
28. 策略驗證功能：自動計算分析日期之後的實際走勢
29. 未來驗證區塊：顯示 5天/10天/20天後的漲跌幅
30. 驗證結論：自動判斷買進/賣出建議是否正確

v4.2 新增功能：

【均值回歸與乖離模組 (Mean Reversion & Bias Module)】
18. 乖離率分析：20MA/60MA 乖離百分比，自動警示過熱/超跌
19. 左側買進訊號：負乖離 + RSI超賣 + 止跌跡象 → 超跌反彈偵測
20. 左側賣出訊號：正乖離 + RSI背離 + 高檔爆量不漲 → 漲多預判拉回
21. 雙軌出場策略：
    - 🛡️ 防守型出場（趨勢賣點）：三盤跌破 / 跌破 20MA
    - 💰 積極型停利（目標賣點）：左側賣訊 / 達風險回報比
22. 操作建議總結：結合趨勢方向 + 乖離狀態的綜合判斷

v4.1 新增功能：

【波段分析模組】
11. 波段環境篩選：K線 > 55MA 且 55MA 上揚
12. 三盤突破偵測：收盤價 > 前兩日最高價（進場訊號）
13. 三盤跌破偵測：收盤價 < 前兩日最低價（出場訊號）
14. 爆量K線守則：爆量K線低點不可被收破
15. 量價共振判斷：量、價、均線同時翻揚

【UI改進】
16. K線圖顯示當前股價、昨日收盤、漲跌幅、更新時間
17. 量化報告新增波段分析區塊

v4.0 重大改進清單：

【數據層面改進】
1. 基本面評估：改用 PE Band（歷史百分位）+ forwardPE（預估本益比）
2. 風險指標：獨立抓取 2 年數據計算 VaR、Beta、波動率
3. 籌碼面緩存：SQLite 本地緩存機制，同日數據只抓一次

【分析邏輯改進】
4. 市場環境過濾器：加入大盤趨勢判斷 + ADX 指標判斷趨勢盤/震盪盤
5. 策略穩定性評分：引入 Sharpe Ratio 權重，避免過度擬合

【回測引擎改進】
6. 夏普比率修正：扣除無風險利率（預設使用 10 年期美債收益率）
7. Equity Curve 視覺化：回測彈窗增加淨值曲線折線圖

【新增功能】
8. Beta 係數計算：個股相對於大盤的波動倍數
9. 成交量異常偵測：Volume Spike 判斷（2 倍於 20 日均量）
10. 相關性矩陣：自選股組合相關性分析
"""
import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import threading
import time
import warnings
import gc

# 抑制 yfinance 的警告訊息
warnings.filterwarnings('ignore', category=FutureWarning)

# ============================================================
# v4.5.13 修正：Python 3.13 Tkinter 多線程垃圾回收問題
# ============================================================
# 問題：背景線程中的對象被垃圾回收時，如果引用了 Tkinter 變數，
#       會觸發 "RuntimeError: main thread is not in main loop"
# 解決：在背景線程執行期間禁用自動垃圾回收
# ============================================================

class ThreadSafeGC:
    """
    線程安全的垃圾回收管理器
    
    用於解決 Python 3.13 中 Tkinter 多線程垃圾回收問題
    """
    _lock = threading.Lock()
    _background_threads = 0
    _gc_was_enabled = True
    
    @classmethod
    def enter_background_thread(cls):
        """進入背景線程時調用"""
        with cls._lock:
            cls._background_threads += 1
            if cls._background_threads == 1 and gc.isenabled():
                cls._gc_was_enabled = True
                gc.disable()
    
    @classmethod
    def exit_background_thread(cls):
        """離開背景線程時調用"""
        with cls._lock:
            cls._background_threads = max(0, cls._background_threads - 1)
            if cls._background_threads == 0 and cls._gc_was_enabled:
                gc.enable()
    
    @classmethod
    def collect_in_main_thread(cls, root):
        """在主線程中安全執行垃圾回收"""
        def do_collect():
            if cls._background_threads == 0:
                gc.collect()
        try:
            root.after(0, do_collect)
        except:
            pass

import yfinance as yf
import mplfinance as mpf
import pandas as pd
import numpy as np
from scipy.stats import percentileofscore
import twstock

# ============================================================================
# YFinance 速率限制輔助類（v4.4.7 增強：熔斷機制）
# ============================================================================
class YFinanceRateLimiter:
    """
    YFinance 速率限制器（帶熔斷機制）
    
    解決 "Too Many Requests" 錯誤：
    1. 請求間隔控制
    2. 指數退避重試（最多 2 次）
    3. 簡易快取
    4. ★ 熔斷機制：連續失敗 3 次後暫停所有請求 5 分鐘
    """
    
    _last_request_time = 0
    _min_interval = 1.0  # 最小請求間隔（秒）- 加大到 1 秒
    _cache = {}  # 簡易快取 {ticker: {'data': df, 'timestamp': time}}
    _cache_ttl = 600  # 快取有效期（秒）- 加長到 10 分鐘

    # B2 #3：基本面 .info 跨日磁碟快取（.info 盤中幾乎不變，每日抓一次即可）
    _info_disk_cache = None          # 延遲載入的當日磁碟快取 {ticker: data}
    _info_disk_cache_date = None     # 磁碟快取的日期字串
    _info_disk_dirty = False         # 是否有新資料待寫回
    
    # 熔斷機制
    _consecutive_failures = 0  # 連續失敗次數
    _circuit_breaker_triggered = False  # 熔斷是否觸發
    _circuit_breaker_until = 0  # 熔斷解除時間
    _max_failures = 3  # 觸發熔斷的連續失敗次數
    _cooldown_duration = 300  # 熔斷冷卻時間（5 分鐘）
    
    # 請求計數（用於診斷）
    _total_requests = 0
    _total_cache_hits = 0
    _total_failures = 0
    
    @classmethod
    def is_circuit_breaker_active(cls) -> bool:
        """檢查熔斷是否生效中"""
        if cls._circuit_breaker_triggered:
            if time.time() < cls._circuit_breaker_until:
                return True
            else:
                # 熔斷時間已過，重置
                cls._circuit_breaker_triggered = False
                cls._consecutive_failures = 0
                print(f"[YFinance] 熔斷已解除，恢復請求")
                return False
        return False
    
    @classmethod
    def get_circuit_breaker_remaining(cls) -> int:
        """取得熔斷剩餘秒數"""
        if cls._circuit_breaker_triggered:
            remaining = int(cls._circuit_breaker_until - time.time())
            return max(0, remaining)
        return 0
    
    @classmethod
    def trigger_circuit_breaker(cls, reason: str = ""):
        """觸發熔斷"""
        cls._circuit_breaker_triggered = True
        cls._circuit_breaker_until = time.time() + cls._cooldown_duration
        print(f"⛔ [YFinance] 熔斷觸發！原因：{reason}")
        print(f"⛔ [YFinance] 所有 API 請求暫停 {cls._cooldown_duration} 秒")
        print(f"⛔ [YFinance] 統計：總請求 {cls._total_requests}，快取命中 {cls._total_cache_hits}，失敗 {cls._total_failures}")
    
    @classmethod
    def get_history(cls, ticker_obj, **kwargs):
        """
        帶速率限制和熔斷機制的 history() 調用
        
        Args:
            ticker_obj: yf.Ticker 物件
            **kwargs: 傳遞給 history() 的參數
        
        Returns:
            DataFrame or None
        """
        # 檢查熔斷
        if cls.is_circuit_breaker_active():
            remaining = cls.get_circuit_breaker_remaining()
            print(f"⚠️ [YFinance] 熔斷中，剩餘 {remaining} 秒，返回快取或 None")
            # 嘗試返回快取
            ticker_symbol = ticker_obj.ticker if hasattr(ticker_obj, 'ticker') else str(ticker_obj)
            cache_key = f"{ticker_symbol}_{hash(frozenset(kwargs.items()))}"
            if cache_key in cls._cache:
                cls._total_cache_hits += 1
                return cls._cache[cache_key]['data'].copy()
            return None
        
        # 生成快取鍵
        ticker_symbol = ticker_obj.ticker if hasattr(ticker_obj, 'ticker') else str(ticker_obj)
        cache_key = f"{ticker_symbol}_{hash(frozenset(kwargs.items()))}"
        
        # 檢查快取
        if cache_key in cls._cache:
            cached = cls._cache[cache_key]
            if time.time() - cached['timestamp'] < cls._cache_ttl:
                cls._total_cache_hits += 1
                return cached['data'].copy()
        
        # 速率限制：確保請求間隔
        current_time = time.time()
        time_since_last = current_time - cls._last_request_time
        if time_since_last < cls._min_interval:
            sleep_time = cls._min_interval - time_since_last
            time.sleep(sleep_time)
        
        # 指數退避重試（最多 2 次，避免無限循環）
        max_retries = 2
        base_delay = 3
        
        for attempt in range(max_retries):
            try:
                cls._last_request_time = time.time()
                cls._total_requests += 1
                
                result = ticker_obj.history(**kwargs)
                
                # 成功，重置失敗計數
                cls._consecutive_failures = 0
                
                # 存入快取
                if result is not None and not result.empty:
                    cls._cache[cache_key] = {
                        'data': result.copy(),
                        'timestamp': time.time()
                    }
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                cls._total_failures += 1
                
                # 檢查是否為速率限制錯誤
                if 'rate' in error_str or 'limit' in error_str or 'too many' in error_str:
                    cls._consecutive_failures += 1
                    
                    # 檢查是否需要觸發熔斷
                    if cls._consecutive_failures >= cls._max_failures:
                        cls.trigger_circuit_breaker(f"連續 {cls._consecutive_failures} 次速率限制錯誤")
                        return None
                    
                    # 重試
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        print(f"⚠️ [YFinance] 速率限制，等待 {delay} 秒... (嘗試 {attempt + 1}/{max_retries})")
                        time.sleep(delay)
                    else:
                        print(f"⚠️ [YFinance] 重試失敗，連續失敗 {cls._consecutive_failures} 次")
                        return None
                else:
                    # 其他錯誤，不重試
                    print(f"⚠️ [YFinance] 非速率限制錯誤: {e}")
                    return None
        
        return None
    
    @classmethod
    def get_ticker_safe(cls, symbol):
        """
        安全取得 Ticker 物件
        
        Returns:
            Ticker 物件（不會觸發 API 請求）
        """
        # 檢查熔斷
        if cls.is_circuit_breaker_active():
            remaining = cls.get_circuit_breaker_remaining()
            print(f"⚠️ [YFinance] 熔斷中（剩餘 {remaining} 秒），但仍返回 Ticker 物件")
        
        # 建立 Ticker 物件不會觸發 API 請求
        return yf.Ticker(symbol)
    
    @classmethod
    def get_info_safe(cls, ticker_obj, timeout: int = 10):
        """
        安全取得 stock.info（帶快取和熔斷）
        
        Args:
            ticker_obj: yf.Ticker 物件
            timeout: 超時秒數
        
        Returns:
            dict: info 字典，失敗返回空字典
        """
        # 檢查熔斷
        if cls.is_circuit_breaker_active():
            return {}
        
        ticker_symbol = ticker_obj.ticker if hasattr(ticker_obj, 'ticker') else str(ticker_obj)
        cache_key = f"{ticker_symbol}_info"
        
        # 檢查記憶體快取
        if cache_key in cls._cache:
            cached = cls._cache[cache_key]
            if time.time() - cached['timestamp'] < cls._cache_ttl:
                cls._total_cache_hits += 1
                return cached['data'].copy()

        # B2 #3：檢查當日磁碟快取（.info 盤中幾乎不變，跨執行/重啟仍有效）
        _disk = cls._info_disk_get(ticker_symbol)
        if _disk is not None:
            cls._total_cache_hits += 1
            cls._cache[cache_key] = {'data': _disk, 'timestamp': time.time()}
            return _disk.copy()

        # 速率限制
        current_time = time.time()
        time_since_last = current_time - cls._last_request_time
        if time_since_last < cls._min_interval:
            time.sleep(cls._min_interval - time_since_last)

        try:
            cls._last_request_time = time.time()
            cls._total_requests += 1

            info = ticker_obj.info

            # 成功，重置失敗計數並存入快取
            cls._consecutive_failures = 0
            cls._cache[cache_key] = {
                'data': info.copy() if info else {},
                'timestamp': time.time()
            }
            # B2 #3：寫入當日磁碟快取
            if info:
                cls._info_disk_put(ticker_symbol, info)

            return info if info else {}
            
        except Exception as e:
            error_str = str(e).lower()
            cls._total_failures += 1
            
            if 'rate' in error_str or 'limit' in error_str or 'too many' in error_str:
                cls._consecutive_failures += 1
                if cls._consecutive_failures >= cls._max_failures:
                    cls.trigger_circuit_breaker(f"info 請求連續 {cls._consecutive_failures} 次失敗")
            
            print(f"⚠️ [YFinance] 取得 info 失敗: {e}")
            return {}
    
    # ── B2 #3：基本面 .info 跨日磁碟快取 ──────────────────────────────
    @classmethod
    def _info_disk_path(cls):
        import os as _os
        return _os.path.join(
            _os.path.dirname(_os.path.abspath(__file__)), 'info_cache.json'
        )

    @classmethod
    def _load_info_disk_cache(cls):
        """載入當日磁碟快取（檔案含日期，跨日自動失效）。"""
        import os as _os, json as _json, datetime as _dt
        today = _dt.date.today().isoformat()
        if cls._info_disk_cache is not None and cls._info_disk_cache_date == today:
            return
        cls._info_disk_cache = {}
        cls._info_disk_cache_date = today
        try:
            p = cls._info_disk_path()
            if _os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    raw = _json.load(f)
                if raw.get('date') == today:
                    cls._info_disk_cache = raw.get('data', {}) or {}
        except Exception:
            cls._info_disk_cache = {}

    @classmethod
    def _info_disk_get(cls, ticker_symbol):
        cls._load_info_disk_cache()
        return cls._info_disk_cache.get(ticker_symbol)

    @classmethod
    def _info_disk_put(cls, ticker_symbol, info):
        import json as _json
        cls._load_info_disk_cache()
        try:
            # 僅保留可 JSON 序列化的純量欄位，避免寫入失敗
            slim = {k: v for k, v in (info or {}).items()
                    if isinstance(v, (str, int, float, bool, type(None)))}
            cls._info_disk_cache[ticker_symbol] = slim
            with open(cls._info_disk_path(), 'w', encoding='utf-8') as f:
                _json.dump({'date': cls._info_disk_cache_date,
                            'data': cls._info_disk_cache}, f, ensure_ascii=False)
        except Exception:
            pass  # 磁碟快取寫入失敗不影響主流程

    @classmethod
    def clear_cache(cls):
        """清除快取"""
        cls._cache.clear()
        cls._info_disk_cache = None
        cls._info_disk_cache_date = None
        print(f"[YFinance] 快取已清除")
    
    @classmethod
    def reset_circuit_breaker(cls):
        """手動重置熔斷"""
        cls._circuit_breaker_triggered = False
        cls._consecutive_failures = 0
        cls._circuit_breaker_until = 0
        print(f"[YFinance] 熔斷已手動重置")
    
    @classmethod
    def get_stats(cls) -> dict:
        """取得統計資訊"""
        return {
            'total_requests': cls._total_requests,
            'cache_hits': cls._total_cache_hits,
            'failures': cls._total_failures,
            'consecutive_failures': cls._consecutive_failures,
            'circuit_breaker_active': cls.is_circuit_breaker_active(),
            'circuit_breaker_remaining': cls.get_circuit_breaker_remaining(),
            'cache_size': len(cls._cache)
        }

# Matplotlib相關
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.figure import Figure

import requests

# 設定中文字體
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft JhengHei", "PingFang SC", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False

import sys
import os

# ============================================================================
# 字體設定
# ============================================================================

zh_font = None

if sys.platform == "win32":
    font_paths = [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msyh.ttc"
    ]
elif sys.platform == "darwin":
    font_paths = [
        "/Library/Fonts/SimHei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc"
    ]
else:
    font_paths = [
        "/usr/share/fonts/truetype/SimHei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    ]

for font_path in font_paths:
    font_path = os.path.expanduser(font_path)
    if os.path.exists(font_path):
        try:
            zh_font = fm.FontProperties(fname=font_path)
            print(f"使用字體：{font_path}")
            break
        except:
            continue

if zh_font is None:
    zh_font = fm.FontProperties()
    print("警告：無法找到中文字體，使用系統預設字體")

# ============================================================================
# Import Modules
# ============================================================================
from config import QuantConfig
from data_fetcher import RealtimePriceFetcher, WukongAPI, DataSourceManager, FubonMarketData
from analyzers import (DecisionMatrix, WaveAnalyzer, MeanReversionAnalyzer, 
                       MarketRegimeAnalyzer, CorrelationAnalyzer,
                       calculate_sma, calculate_bollinger_bands, calculate_macd,
                       calculate_rsi, calculate_kd, analyze_volume_price_relation)
from backtesting import BacktestEngine
from database import WatchlistDatabase

# ============================================================================
# v4.5.17 新增：熱門題材掃描模組
# ============================================================================
try:
    from trend_scanner import SectorMomentumScanner
    from market_trend_manager import MarketTrendManager, SectorInfo, StockInfo
    TREND_SCANNER_AVAILABLE = True
except ImportError:
    TREND_SCANNER_AVAILABLE = False
    print("[Main] 提示：未找到 trend_scanner.py，熱門題材功能將停用")

try:
    from advanced_analyzers import VCPScanner, RelativeStrengthCalculator, ATRStopLossCalculator
    ADVANCED_ANALYZERS_AVAILABLE = True
except ImportError:
    ADVANCED_ANALYZERS_AVAILABLE = False
    print("[Main] 提示：未找到 advanced_analyzers.py，進階分析功能將停用")

# ============================================================================
# v4.3.5 新增：富邦證券交易模組
# ============================================================================
try:
    from fubon_trading import FubonTrader, create_order_dialog, get_trader, FUBON_SDK_AVAILABLE
except ImportError:
    FUBON_SDK_AVAILABLE = False
    def get_trader(): return None
    def create_order_dialog(parent, symbol='', trader=None):
        messagebox.showinfo("提示", "fubon_trading 模組未安裝\n請確認 fubon_trading.py 在同一目錄")
    print("提示：fubon_trading 模組未找到")

# ============================================================================
# v4.3 新增：市場排行彈跳視窗
# ============================================================================

class MarketRankingDialog:
    """
    市場排行彈跳視窗
    
    開啟程式時顯示：
    1. 三大法人買賣超排行（外資/投信/自營商）
    2. 產業分類排行
    3. 概念股分類排行
    
    v4.4.1 修正：加入視窗關閉保護，防止 TclError
    """
    
    def __init__(self, parent, on_stock_select=None):
        """
        Args:
            parent: 父視窗
            on_stock_select: 點擊股票時的回調函數 callback(symbol)
        """
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("📊 今日市場排行")
        self.dialog.geometry("1250x780")
        self.dialog.transient(parent)
        
        self.on_stock_select = on_stock_select
        self.parent = parent
        self.loading = False
        
        # v4.4.1 新增：視窗關閉保護
        self._closed = False
        self._after_ids = []
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 標題
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(title_frame, text="📊 今日市場排行 (悟空 API)", 
                 font=("SimHei", 18, "bold")).pack(side=tk.LEFT)
        
        date_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        self.status_label = ttk.Label(title_frame, text=f"更新時間：{date_str}", 
                                      font=("SimHei", 10), foreground="gray")
        self.status_label.pack(side=tk.RIGHT)
        
        # 頁籤
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 建立頁籤
        self._create_institutional_tab()
        self._create_industry_tab()
        self._create_concept_tab()
        
        # 按鈕區
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="🔄 重新整理", 
                  command=self._refresh_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="關閉", 
                  command=self._on_close).pack(side=tk.RIGHT, padx=5)
        
        # 載入數據
        self._load_data()
    
    def _on_close(self):
        """v4.4.1 新增：安全關閉視窗"""
        self._closed = True
        # 取消所有待執行的 after callback
        for after_id in self._after_ids:
            try:
                self.dialog.after_cancel(after_id)
            except:
                pass
        self._after_ids.clear()
        try:
            self.dialog.destroy()
        except:
            pass
    
    def _safe_after(self, ms, func):
        """v4.4.1 新增：安全的 after 調用，防止視窗關閉後執行"""
        if self._closed:
            return None
        try:
            if self.dialog.winfo_exists():
                after_id = self.dialog.after(ms, func)
                self._after_ids.append(after_id)
                return after_id
        except tk.TclError:
            pass
        return None
    
    def _safe_ui_update(self, func):
        """v4.4.1 新增：安全的 UI 更新包裝器"""
        def wrapper():
            if self._closed:
                return
            try:
                if self.dialog.winfo_exists():
                    func()
            except tk.TclError as e:
                print(f"[MarketRankingDialog] UI 更新跳過（視窗已關閉）: {e}")
        return wrapper
    
    def _create_institutional_tab(self):
        """建立三大法人頁籤"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="📈 三大法人買賣超")
        
        # 子頁籤：外資、投信、自營商
        sub_notebook = ttk.Notebook(tab)
        sub_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 外資頁籤
        foreign_frame = ttk.Frame(sub_notebook)
        sub_notebook.add(foreign_frame, text="🌍 外資")
        self._create_buysell_panel(foreign_frame, "foreign")
        
        # 投信頁籤
        trust_frame = ttk.Frame(sub_notebook)
        sub_notebook.add(trust_frame, text="🏦 投信")
        self._create_buysell_panel(trust_frame, "trust")
        
        # 自營商頁籤
        dealer_frame = ttk.Frame(sub_notebook)
        sub_notebook.add(dealer_frame, text="🏢 自營商")
        self._create_buysell_panel(dealer_frame, "dealer")
    
    def _create_buysell_panel(self, parent, inst_type):
        """建立買超/賣超雙欄面板"""
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左側：買超
        left_frame = ttk.LabelFrame(container, text="🔴 買超前50名", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        buy_tree = ttk.Treeview(left_frame, columns=("symbol", "name", "price","total_vol","volume"), 
                                show="headings", height=22)
        buy_tree.heading("symbol", text="代碼")
        buy_tree.heading("name", text="名稱")
        buy_tree.heading("price", text="價格(漲跌%)")
        buy_tree.heading("total_vol", text="成交量")
        buy_tree.heading("volume", text="買超(張)")
        buy_tree.column("symbol", width=60)
        buy_tree.column("name", width=70)
        buy_tree.column("price", width=110)
        buy_tree.column("total_vol", width=80)
        buy_tree.column("volume", width=80)
        
        buy_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=buy_tree.yview)
        buy_tree.configure(yscrollcommand=buy_scroll.set)
        buy_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        buy_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        buy_tree.bind('<Double-1>', lambda e: self._on_tree_double_click(e, buy_tree))
        buy_tree.tag_configure("up", foreground="red")
        buy_tree.tag_configure("down", foreground="green")
        setattr(self, f"{inst_type}_buy_tree", buy_tree)
        
        # 右側：賣超
        right_frame = ttk.LabelFrame(container, text="🟢 賣超前50名", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        sell_tree = ttk.Treeview(right_frame, columns=("symbol", "name", "price", "total_vol", "volume"), 
                                 show="headings", height=22)
        sell_tree.heading("symbol", text="代碼")
        sell_tree.heading("name", text="名稱")
        sell_tree.heading("price", text="價格(漲跌%)")
        sell_tree.heading("total_vol", text="成交量")
        sell_tree.heading("volume", text="賣超(張)")
        sell_tree.column("symbol", width=60)
        sell_tree.column("name", width=70)
        sell_tree.column("price", width=110)
        sell_tree.column("total_vol", width=80)
        sell_tree.column("volume", width=80)
        
        sell_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=sell_tree.yview)
        sell_tree.configure(yscrollcommand=sell_scroll.set)
        sell_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sell_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        sell_tree.bind('<Double-1>', lambda e: self._on_tree_double_click(e, sell_tree))
        sell_tree.tag_configure("up", foreground="red")
        sell_tree.tag_configure("down", foreground="green")
        setattr(self, f"{inst_type}_sell_tree", sell_tree)
    
    def _create_industry_tab(self):
        """建立產業分類頁籤"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🏭 產業分類")
        
        container = ttk.Frame(tab)
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左側：產業列表
        left_frame = ttk.LabelFrame(container, text="產業排行（點擊查看個股）", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        left_frame.configure(width=320)
        
        self.industry_tree = ttk.Treeview(left_frame, columns=("name", "up", "down", "trend"), 
                                          show="headings", height=25)
        self.industry_tree.heading("name", text="產業名稱")
        self.industry_tree.heading("up", text="漲↑")
        self.industry_tree.heading("down", text="跌↓")
        self.industry_tree.heading("trend", text="趨勢")
        self.industry_tree.column("name", width=120)
        self.industry_tree.column("up", width=50)
        self.industry_tree.column("down", width=50)
        self.industry_tree.column("trend", width=60)
        
        ind_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.industry_tree.yview)
        self.industry_tree.configure(yscrollcommand=ind_scroll.set)
        self.industry_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ind_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.industry_tree.bind('<<TreeviewSelect>>', self._on_industry_select)
        self.industry_tree.tag_configure("up", foreground="red")
        self.industry_tree.tag_configure("down", foreground="green")
        
        # 右側：產業個股
        right_frame = ttk.LabelFrame(container, text="產業個股（雙擊查詢K線）", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.industry_stocks_tree = ttk.Treeview(
            right_frame, 
            columns=("symbol", "name", "price", "change", "change_pct", "volume"), 
            show="headings", 
            height=25
        )
        self.industry_stocks_tree.heading("symbol", text="代碼")
        self.industry_stocks_tree.heading("name", text="名稱")
        self.industry_stocks_tree.heading("price", text="收盤價")
        self.industry_stocks_tree.heading("change", text="漲跌")
        self.industry_stocks_tree.heading("change_pct", text="漲跌%")
        self.industry_stocks_tree.heading("volume", text="成交量(張)")
        self.industry_stocks_tree.column("symbol", width=70)
        self.industry_stocks_tree.column("name", width=80)
        self.industry_stocks_tree.column("price", width=80)
        self.industry_stocks_tree.column("change", width=70)
        self.industry_stocks_tree.column("change_pct", width=70)
        self.industry_stocks_tree.column("volume", width=90)
        
        stocks_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, 
                                      command=self.industry_stocks_tree.yview)
        self.industry_stocks_tree.configure(yscrollcommand=stocks_scroll.set)
        self.industry_stocks_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        stocks_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.industry_stocks_tree.bind('<Double-1>', 
                                       lambda e: self._on_tree_double_click(e, self.industry_stocks_tree))
        self.industry_stocks_tree.tag_configure("up", foreground="red")
        self.industry_stocks_tree.tag_configure("down", foreground="green")
    
    def _create_concept_tab(self):
        """建立概念股頁籤"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="💡 概念股")
        
        container = ttk.Frame(tab)
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左側：概念股列表
        left_frame = ttk.LabelFrame(container, text="概念股分類（點擊查看個股）", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        left_frame.configure(width=320)
        
        self.concept_tree = ttk.Treeview(left_frame, columns=("name", "up", "down", "trend"), 
                                         show="headings", height=25)
        self.concept_tree.heading("name", text="概念股名稱")
        self.concept_tree.heading("up", text="漲↑")
        self.concept_tree.heading("down", text="跌↓")
        self.concept_tree.heading("trend", text="趨勢")
        self.concept_tree.column("name", width=120)
        self.concept_tree.column("up", width=50)
        self.concept_tree.column("down", width=50)
        self.concept_tree.column("trend", width=60)
        
        concept_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.concept_tree.yview)
        self.concept_tree.configure(yscrollcommand=concept_scroll.set)
        self.concept_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        concept_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.concept_tree.bind('<<TreeviewSelect>>', self._on_concept_select)
        self.concept_tree.tag_configure("up", foreground="red")
        self.concept_tree.tag_configure("down", foreground="green")
        
        # 右側：概念股個股
        right_frame = ttk.LabelFrame(container, text="概念股個股（雙擊查詢K線）", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.concept_stocks_tree = ttk.Treeview(
            right_frame, 
            columns=("symbol", "name", "price", "change", "change_pct", "volume"), 
            show="headings", 
            height=25
        )
        self.concept_stocks_tree.heading("symbol", text="代碼")
        self.concept_stocks_tree.heading("name", text="名稱")
        self.concept_stocks_tree.heading("price", text="收盤價")
        self.concept_stocks_tree.heading("change", text="漲跌")
        self.concept_stocks_tree.heading("change_pct", text="漲跌%")
        self.concept_stocks_tree.heading("volume", text="成交量(張)")
        self.concept_stocks_tree.column("symbol", width=70)
        self.concept_stocks_tree.column("name", width=80)
        self.concept_stocks_tree.column("price", width=80)
        self.concept_stocks_tree.column("change", width=70)
        self.concept_stocks_tree.column("change_pct", width=70)
        self.concept_stocks_tree.column("volume", width=90)
        
        concept_stocks_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, 
                                              command=self.concept_stocks_tree.yview)
        self.concept_stocks_tree.configure(yscrollcommand=concept_stocks_scroll.set)
        self.concept_stocks_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        concept_stocks_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.concept_stocks_tree.bind('<Double-1>', 
                                      lambda e: self._on_tree_double_click(e, self.concept_stocks_tree))
        self.concept_stocks_tree.tag_configure("up", foreground="red")
        self.concept_stocks_tree.tag_configure("down", foreground="green")
    
    def _load_data(self):
        """載入數據（v4.4.4 強化：加入 API 回傳 None 的防護）"""
        if self.loading or self._closed:
            return
        self.loading = True
        
        try:
            self.status_label.config(text="載入中...")
        except tk.TclError:
            return
        
        def load_in_thread():
            try:
                # 載入三大法人數據
                inst_data = WukongAPI.get_institutional_ranking(50)
                # v4.4.4 Fix: 加強 None 檢查
                if inst_data is not None and not self._closed:
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self._update_institutional_data(inst_data)
                    ))
                elif inst_data is None and not self._closed:
                    # v4.4.4 Fix: API 回傳 None 時顯示錯誤
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self.status_label.config(text="⚠️ 三大法人數據載入失敗")
                    ))
                
                # 載入產業數據
                industry_data = WukongAPI.get_industry_list()
                # v4.4.4 Fix: 加強 None 檢查
                if industry_data is not None and not self._closed:
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self._update_category_data(industry_data, self.industry_tree)
                    ))
                elif industry_data is None and not self._closed:
                    print("[MarketRankingDialog] 產業數據載入失敗（API 回傳 None）")
                
                # 載入概念股數據
                concept_data = WukongAPI.get_concept_list()
                # v4.4.4 Fix: 加強 None 檢查
                if concept_data is not None and not self._closed:
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self._update_category_data(concept_data, self.concept_tree)
                    ))
                elif concept_data is None and not self._closed:
                    print("[MarketRankingDialog] 概念股數據載入失敗（API 回傳 None）")
                
                # 更新狀態
                date_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if not self._closed:
                    # v4.4.4 Fix: 檢查是否有任何數據載入成功
                    if inst_data is not None or industry_data is not None or concept_data is not None:
                        self._safe_after(0, self._safe_ui_update(
                            lambda: self.status_label.config(text=f"更新時間：{date_str}")
                        ))
                    else:
                        self._safe_after(0, self._safe_ui_update(
                            lambda: self.status_label.config(text=f"⚠️ 數據載入失敗，請稍後重試")
                        ))
            except Exception as e:
                print(f"[MarketRankingDialog] 載入數據錯誤: {e}")
                # v4.4.4 Fix: 錯誤時更新 UI 顯示
                # 修正：先把訊息字串抽出，避免 lambda 延遲執行時 except 變數 e 已被刪除
                _err_text = f"⚠️ 載入錯誤：{str(e)[:30]}"
                if not self._closed:
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self.status_label.config(text=_err_text)
                    ))
            finally:
                self.loading = False
        
        thread = threading.Thread(target=load_in_thread, daemon=True)
        thread.start()
    
    def _update_institutional_data(self, data):
        """更新三大法人數據到 UI（v4.4.4 強化：加入 None 防護）"""
        if self._closed:
            return
        
        # v4.4.4 Fix: 加強 data 有效性檢查
        if data is None:
            print("[MarketRankingDialog] _update_institutional_data: data is None")
            return
        
        try:
            # 更新外資（加入預設空列表防護）
            self._fill_inst_tree(self.foreign_buy_tree, data.get('foreign_buy', []) or [])
            self._fill_inst_tree(self.foreign_sell_tree, data.get('foreign_sell', []) or [])
            
            # 更新投信
            self._fill_inst_tree(self.trust_buy_tree, data.get('trust_buy', []) or [])
            self._fill_inst_tree(self.trust_sell_tree, data.get('trust_sell', []) or [])
            
            # 更新自營商
            self._fill_inst_tree(self.dealer_buy_tree, data.get('dealer_buy', []) or [])
            self._fill_inst_tree(self.dealer_sell_tree, data.get('dealer_sell', []) or [])
        except tk.TclError as e:
            print(f"[MarketRankingDialog] _update_institutional_data 跳過: {e}")
        except Exception as e:
            print(f"[MarketRankingDialog] _update_institutional_data 錯誤: {e}")
    
    def _fill_inst_tree(self, tree, data_list):
        """填充法人 Treeview（v4.4.1 修正：加入防護）"""
        if self._closed:
            return
        
        try:
            if not tree.winfo_exists():
                return
            
            for item in tree.get_children():
                tree.delete(item)
            
            for item in data_list:
                if isinstance(item, dict):
                    symbol = item.get('symbol', '')
                    name = item.get('name', '')
                    volume = item.get('volume', 0)
                    price = item.get('price', 0)
                    change_pct = item.get('change_pct', 0)
                    total_vol = item.get('total_vol', 0)
                    
                    # 格式化顯示
                    vol_str = f"{int(volume):,}" if volume else "0"
                    total_vol_str = f"{int(total_vol):,}" if total_vol else "0"
                    
                    # 價格顯示：包含漲跌幅
                    if price:
                        if change_pct:
                            # 計算漲跌幅百分比
                            prev_price = price - change_pct
                            if prev_price > 0:
                                pct = (change_pct / prev_price) * 100
                                price_str = f"{price:.2f}({pct:+.1f}%)"
                            else:
                                price_str = f"{price:.2f}"
                        else:
                            price_str = f"{price:.2f}"
                    else:
                        price_str = "-"
                    
                    # 根據漲跌設定顏色標籤
                    tag = ""
                    if change_pct > 0:
                        tag = "up"
                    elif change_pct < 0:
                        tag = "down"
                    
                    tree.insert("", "end", values=(symbol, name, price_str, total_vol_str, vol_str), tags=(tag,))
        except tk.TclError as e:
            print(f"[MarketRankingDialog] _fill_inst_tree 跳過: {e}")
    
    def _update_category_data(self, data, tree):
        """更新分類數據到 UI（產業/概念股）（v4.4.4 強化：加入 None 防護）"""
        if self._closed:
            return
        
        # v4.4.4 Fix: 加強 data 有效性檢查
        if data is None:
            print("[MarketRankingDialog] _update_category_data: data is None")
            return
        
        try:
            if not tree.winfo_exists():
                return
            
            for item in tree.get_children():
                tree.delete(item)
            
            # v4.4.4 Fix: 確保 data 是可迭代的
            if not isinstance(data, (list, tuple)):
                print(f"[MarketRankingDialog] _update_category_data: 無效的數據類型 {type(data)}")
                return
            
            for ind in data:
                if isinstance(ind, dict):
                    cat_id = ind.get('id', '')
                    name = ind.get('name', '')
                    up = ind.get('up_count', 0)
                    down = ind.get('down_count', 0)
                    change_pct = ind.get('change_pct', 0)
                    
                    tag = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
                    trend_str = f"{change_pct:+.1f}%" if change_pct else "0.0%"
                    
                    # 存儲 id 在 iid 中
                    tree.insert("", "end", iid=cat_id, values=(name, up, down, trend_str), tags=(tag,))
        except tk.TclError as e:
            print(f"[MarketRankingDialog] _update_category_data 跳過: {e}")
        except Exception as e:
            print(f"[MarketRankingDialog] _update_category_data 錯誤: {e}")
    
    def _on_industry_select(self, event):
        """選擇產業時載入個股（v4.4.1 修正：加入防護）"""
        if self._closed:
            return
        
        try:
            selection = self.industry_tree.selection()
            if not selection:
                return
            
            industry_id = selection[0]  # iid 就是 category_id
            
            def load_stocks():
                if self._closed:
                    return
                stocks = WukongAPI.get_industry_stocks(industry_id, 50)
                if not self._closed:
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self._update_stocks_tree(stocks, self.industry_stocks_tree)
                    ))
            
            thread = threading.Thread(target=load_stocks, daemon=True)
            thread.start()
        except tk.TclError:
            pass
    
    def _on_concept_select(self, event):
        """選擇概念股時載入個股（v4.4.1 修正：加入防護）"""
        if self._closed:
            return
        
        try:
            selection = self.concept_tree.selection()
            if not selection:
                return
            
            concept_id = selection[0]
            
            def load_stocks():
                if self._closed:
                    return
                stocks = WukongAPI.get_concept_stocks(concept_id, 50)
                if not self._closed:
                    self._safe_after(0, self._safe_ui_update(
                        lambda: self._update_stocks_tree(stocks, self.concept_stocks_tree)
                    ))
            
            thread = threading.Thread(target=load_stocks, daemon=True)
            thread.start()
        except tk.TclError:
            pass
    
    def _update_stocks_tree(self, stocks, tree):
        """更新個股列表到 Treeview（v4.4.1 修正：加入防護）"""
        if self._closed:
            return
        
        try:
            if not tree.winfo_exists():
                return
            
            for item in tree.get_children():
                tree.delete(item)
            
            for stock in stocks:
                if isinstance(stock, dict):
                    symbol = stock.get('symbol', '')
                    name = stock.get('name', '')
                    price = stock.get('price', 0)
                    change = stock.get('change', 0)
                    change_pct = stock.get('change_pct', 0)
                    volume = stock.get('volume', 0)
                    
                    price_str = f"{price:.2f}" if price else "0.00"
                    change_str = f"{change:+.2f}" if change else "0.00"
                    change_pct_str = f"{change_pct:+.2f}%" if change_pct else "0.00%"
                    vol_str = f"{int(volume):,}" if volume else "0"
                    
                    tag = "up" if change > 0 else "down" if change < 0 else ""
                    tree.insert("", "end", values=(symbol, name, price_str, change_str, change_pct_str, vol_str), tags=(tag,))
        except tk.TclError as e:
            print(f"[MarketRankingDialog] _update_stocks_tree 跳過: {e}")
    
    def _on_tree_double_click(self, event, tree):
        """雙擊 Treeview 時的處理（v4.4.1 修正：加入防護）"""
        if self._closed:
            return
        
        try:
            selection = tree.selection()
            if not selection:
                return
            
            item = tree.item(selection[0])
            values = item.get('values', [])
            
            if values:
                # 第一欄是代碼
                symbol = str(values[0])
                
                if symbol and self.on_stock_select:
                    self.on_stock_select(symbol)
                    self._on_close()
        except tk.TclError:
            pass
    
    def _refresh_data(self):
        """重新整理數據（v4.4.1 修正：加入防護）"""
        if self._closed:
            return
        WukongAPI.clear_cache()
        self._load_data()



# ============================================================================
# v4.0 改進：增強版量化分析模組
# ============================================================================

class QuickAnalyzer:
    """快速量化分析器 v4.0"""
    
    # 籌碼緩存資料庫實例（類別層級）
    _db = None

    # A2/B：大盤指數歷史快取（避免每檔重抓，RS 計算共用）
    # 結構：{ index_symbol: (date_str, DataFrame) }，同一天內有效
    _index_hist_cache = {}

    @classmethod
    def get_db(cls):
        if cls._db is None:
            cls._db = WatchlistDatabase()
        return cls._db

    # 上櫃（OTC）判定快取：twstock market=='上櫃' → yfinance 需 .TWO 後綴
    _otc_cache = {}

    @classmethod
    def _is_otc(cls, symbol):
        """判斷台股代號是否為上櫃（OTC）。未知（ETF/新股）回 False。"""
        s = str(symbol)
        if s in cls._otc_cache:
            return cls._otc_cache[s]
        is_otc = False
        try:
            info = twstock.codes.get(s)
            is_otc = bool(info and getattr(info, 'market', '') == '上櫃')
        except Exception:
            is_otc = False
        cls._otc_cache[s] = is_otc
        return is_otc

    @classmethod
    def _yf_symbol(cls, symbol, market="台股"):
        """組出 yfinance ticker：台股上市 .TW、上櫃 .TWO、其他市場原樣。"""
        if market != "台股":
            return symbol
        return f"{symbol}.TWO" if cls._is_otc(symbol) else f"{symbol}.TW"

    # build_prompt_08：族群動能（顯示/排序加成，不進 grade）。題材強度當日快取。
    _theme_mgr = None
    _theme_strength_cache = None   # (date_str, strength_dict)

    @classmethod
    def _get_theme_strength(cls):
        """計算/取當日各題材強度（等權 20 日報酬橫斷面排名）。當日快取。"""
        import datetime as _dt
        today = _dt.date.today().isoformat()
        if cls._theme_strength_cache and cls._theme_strength_cache[0] == today:
            return cls._theme_strength_cache[1]
        try:
            if cls._theme_mgr is None:
                from theme_momentum import ThemeMomentum
                cls._theme_mgr = ThemeMomentum()
            tm = cls._theme_mgr
            rets = {}
            for sym in tm.all_symbols():
                try:
                    h = DataSourceManager.get_history(sym, '台股', period='6mo')
                    if h is None or len(h) < 21:
                        continue
                    c = h['Close']
                    r20 = float(c.iloc[-1] / c.iloc[-21] - 1) * 100
                    r60 = float(c.iloc[-1] / c.iloc[-61] - 1) * 100 if len(c) >= 61 else None
                    rets[sym] = {'ret20': r20, 'ret60': r60}
                except Exception:
                    continue
            strength = tm.compute(rets)
            cls._theme_strength_cache = (today, strength)
            return strength
        except Exception as e:
            print(f"[Theme] 強度計算略過: {e}")
            return {}

    @classmethod
    def _get_theme_info(cls, symbol):
        """個股題材加註（theme_name/theme_rank_pct/is_top_theme/is_theme_leader）。"""
        try:
            if cls._theme_mgr is None:
                from theme_momentum import ThemeMomentum
                cls._theme_mgr = ThemeMomentum()
            if not cls._theme_mgr.sym2theme.get(str(symbol)):
                return {'theme_name': None, 'theme_rank_pct': None,
                        'is_top_theme': False, 'is_theme_leader': False}
            return cls._theme_mgr.annotate(str(symbol), cls._get_theme_strength())
        except Exception:
            return {'theme_name': None, 'theme_rank_pct': None,
                    'is_top_theme': False, 'is_theme_leader': False}

    @staticmethod
    def aligned_prev_close(df):
        """
        日期對齊的昨收價（主程式與分析報告共用，確保漲跌幅一致）。

        即時報價的「現價」是今日盤中價；昨收應為「前一交易日的收盤」。
        - 若 df 最後一根 K 棒的日期 >= 今天（df 已含今日盤中/收盤），昨收 = 倒數第二根。
        - 否則（df 最後一根是前一交易日），昨收 = 最後一根。
        這樣不論資料源是否已更新今日 K 棒，都能取到正確的昨收，
        避免用 iloc[-2] 在「df 未含今日」時誤差一天。
        """
        import datetime as _dt
        try:
            if df is None or 'Close' not in df:
                return None
            # NaN-safe：先濾掉空值收盤（避免今日空 K 棒/資料缺漏導致回傳 nan）
            closes = df['Close'].dropna()
            if len(closes) < 1:
                return None
            last_idx = closes.index[-1]
            last_date = last_idx.date() if hasattr(last_idx, 'date') else None
            today = _dt.date.today()
            if last_date is not None and last_date >= today and len(closes) > 1:
                return round(float(closes.iloc[-2]), 2)
            return round(float(closes.iloc[-1]), 2)
        except Exception:
            try:
                closes = df['Close'].dropna()
                return round(float(closes.iloc[-2]), 2) if len(closes) > 1 else round(float(closes.iloc[-1]), 2)
            except Exception:
                return None

    @staticmethod
    def _get_index_history_cached(index_symbol, period=None):
        """
        取得大盤指數歷史（含當日快取）。

        用 yf.Ticker(index_symbol).history()，與 beta 計算相同的可運作路徑。
        index_symbol 應為 yfinance 格式（例如 "^TWII" / "^GSPC"）。
        回傳 DataFrame（含 'Close'）或 None。
        """
        import datetime as _dt
        period = period or f"{QuantConfig.RISK_DATA_YEARS}y"
        today = _dt.date.today().isoformat()
        cache_key = f"{index_symbol}|{period}"
        cached = QuickAnalyzer._index_hist_cache.get(cache_key)
        if cached and cached[0] == today:
            return cached[1]
        try:
            idx = yf.Ticker(index_symbol)
            hist = idx.history(period=period)
            if hist is None or hist.empty:
                return None
            QuickAnalyzer._index_hist_cache[cache_key] = (today, hist)
            return hist
        except Exception as e:
            print(f"[RS] 大盤指數 {index_symbol} 取得失敗: {e}")
            return None

    @staticmethod
    def analyze_stock(symbol, market="台股", analysis_date=None, scan_mode=False):
        """
        快速分析股票 - v4.3 增強版（整合即時與歷史分析）

        v4.4.7 更新：加入 YFinance 速率限制處理

        scan_mode=True（watchlist / 題材掃描的熱路徑）：
          只抓 1 年歷史，跳過 yfinance .info 基本面、5y PE Band、多年風險/beta、
          4 個策略回測（analyze_strategies_v4）——這些都不進三層引擎評級。
          保留評級需要的：technical / RS / volume / mean_reversion(bias) /
          support_resistance / market_regime / 法人 / DecisionMatrix /
          _generate_recommendation_v43 → A/B/C 真實評級與完整模式一致。
          缺的欄位用中性預設值，引擎不會因缺欄位報錯。
        scan_mode=False（完整版，含基本面/PE/風險/策略）給單檔 Query / Report 用。

        Args:
            symbol: 股票代碼
            market: 市場（台股/美股）
            analysis_date: 分析日期 (datetime 物件)，None 表示今天
            scan_mode: 掃描旁路，跳過不進評級的昂貴計算

        Returns:
            dict: 分析結果
        """
        try:
            # ============================================================
            # v4.4.7 重構：統一數據源管理
            # 優先使用富邦 API，失敗才 fallback 到 yfinance
            # ============================================================
            
            # 檢查 yfinance 熔斷（作為最後防線）
            if not DataSourceManager.is_fubon_available() and YFinanceRateLimiter.is_circuit_breaker_active():
                remaining = YFinanceRateLimiter.get_circuit_breaker_remaining()
                print(f"⛔ [DataSource] 所有數據源不可用，{symbol} 分析跳過（yfinance 熔斷剩餘 {remaining} 秒）")
                return None
            
            # 取得股票名稱（優先使用 twstock）
            stock_name = symbol
            if market == "台股" and symbol.isdigit():
                try:
                    stock_name = f"{symbol} {twstock.codes[symbol].name}"
                except:
                    stock_name = symbol
            
            # 用於後續基本面分析的 yfinance ticker（可選）
            # build_prompt: 上櫃股需 .TWO 後綴，否則 yfinance .info 查無資料
            # （基本面 available=None、PE/PB="N/A"、beta 退回近似值）。
            ticker_symbol = None
            stock = None
            ticker_symbol = QuickAnalyzer._yf_symbol(symbol, market)
            
            # 只有在需要時才創建 yfinance ticker（延遲初始化）
            def get_yf_ticker():
                nonlocal stock
                if stock is None:
                    stock = YFinanceRateLimiter.get_ticker_safe(ticker_symbol)
                return stock
            
            is_historical = analysis_date is not None
            
            # ============================================================
            # 數據獲取（v4.4.7 重構：優先使用富邦 API）
            # 優先順序：富邦 API → yfinance
            # ============================================================
            if is_historical:
                # 歷史模式：取得截至指定日期的數據
                end_date = analysis_date
                start_date = end_date - datetime.timedelta(days=250)
                
                # 優先使用 DataSourceManager（富邦 API → yfinance）
                hist = DataSourceManager.get_history(
                    symbol, market,
                    start_date=start_date,
                    end_date=end_date + datetime.timedelta(days=1)
                )
                
                if hist is None or hist.empty:
                    print(f"{symbol}: 無法獲取 {analysis_date.strftime('%Y-%m-%d')} 的歷史數據")
                    return None
                
                hist = hist.dropna()
                
                # 截取到分析日期（使用日期比較避免時區問題）
                target_date = analysis_date.date()
                mask = hist.index.date <= target_date
                hist = hist[mask]
                
                if hist.empty or len(hist) < 60:
                    print(f"{symbol}: 歷史數據不足（少於60天）")
                    return None
                
                actual_date = hist.index[-1].strftime('%Y-%m-%d')
                
                # 長期數據（截至分析日期）
                try:
                    long_start = end_date - datetime.timedelta(days=QuantConfig.RISK_DATA_YEARS * 365)
                    hist_long = DataSourceManager.get_history(
                        symbol, market,
                        start_date=long_start,
                        end_date=end_date + datetime.timedelta(days=1)
                    )
                    if hist_long is not None and not hist_long.empty:
                        hist_long = hist_long[hist_long.index.date <= target_date]
                    else:
                        hist_long = hist
                except:
                    hist_long = hist
            else:
                # 即時模式：取得最新數據
                # 優先使用 DataSourceManager（富邦 API → yfinance）
                # scan_mode：只抓 1 年（富邦只給 1 年，抓多年只會逼 fallback yfinance 拖慢）
                _periods = ["1y"] if scan_mode else ["6mo", "3mo", "1y"]
                hist = None
                for attempt, period in enumerate(_periods):
                    try:
                        hist = DataSourceManager.get_history(symbol, market, period=period)
                        if hist is not None and not hist.empty:
                            data_source = DataSourceManager.get_current_source()
                            print(f"[{symbol}] 數據來源：{data_source}，取得 {len(hist)} 筆")
                            break
                    except Exception as e:
                        print(f"{symbol}: 嘗試 {period} 失敗 - {e}")
                        continue

                if hist is None or hist.empty:
                    print(f"{symbol}: 無法獲取數據（請檢查網絡連接或稍後再試）")
                    return None

                hist = hist.dropna()
                if len(hist) < 60:
                    print(f"{symbol}: 數據不足（少於60天，僅有 {len(hist)} 天）")
                    return None

                actual_date = None
                if scan_mode:
                    hist_long = hist  # 掃描模式：不抓多年資料（風險指標不進三層評級）
                else:
                    try:
                        hist_long = DataSourceManager.get_history(symbol, market, period=f"{QuantConfig.RISK_DATA_YEARS}y")
                    except:
                        hist_long = hist  # 如果長期數據獲取失敗，使用短期數據
            
            # 確保 hist_long 有效
            if hist_long is None or hist_long.empty:
                hist_long = hist
            
            # ============================================================
            # v4.4.7 更新：即時模式優先使用 DataSourceManager 取得即時股價
            # ============================================================
            realtime_price = None
            realtime_change = None
            realtime_change_pct = None
            realtime_prev_close = None
            price_source = 'unknown'

            if not is_historical and market == "台股":
                # 優先使用 DataSourceManager（會嘗試富邦 API）
                realtime_data = DataSourceManager.get_realtime_price(symbol, market)
                if realtime_data and realtime_data.get('price'):
                    realtime_price = realtime_data['price']
                    realtime_change = realtime_data.get('change', 0)
                    realtime_change_pct = realtime_data.get('change_pct', 0)
                    realtime_prev_close = realtime_data.get('prev_close')  # 同源昨收
                    price_source = realtime_data.get('source', 'unknown')
            
            # ============================================================
            # 分析計算（共用邏輯）
            # ============================================================
            
            # 技術指標
            technical = QuickAnalyzer._technical_analysis(hist)

            # 基本面分析（scan_mode 跳過 yfinance .info / 5y PE，用中性預設；評級不依賴基本面）
            if scan_mode:
                fundamental = QuickAnalyzer._get_default_fundamental()
            else:
                # 使用延遲初始化的 yfinance ticker
                fundamental = QuickAnalyzer._fundamental_analysis_v4(get_yf_ticker(), ticker_symbol, hist, is_historical)

            # 風險指標（scan_mode 跳過多年風險/beta(.info)，用中性預設；評級不依賴風險指標）
            if scan_mode:
                risk_metrics = QuickAnalyzer._get_default_risk_metrics()
            else:
                risk_metrics = QuickAnalyzer._calculate_risk_metrics_v4(hist_long, ticker_symbol, market)
            
            # 支撐壓力
            support_resistance = QuickAnalyzer._calculate_support_resistance(hist, technical)
            
            # 籌碼面分析（根據模式走不同分支）
            if is_historical:
                chip_flow = QuickAnalyzer._analyze_chip_flow_historical(symbol, market, analysis_date)
            else:
                chip_flow = QuickAnalyzer._analyze_chip_flow_cached(symbol, market, scan_mode=scan_mode)
            
            # 成交量分析
            volume_analysis = QuickAnalyzer._analyze_volume_spike(hist)
            
            # v4.4.1 新增：量價分析情境庫
            from analyzers import VolumePriceAnalyzer, RiskManager
            volume_price = VolumePriceAnalyzer.analyze(hist)
            
            # v4.4.1 新增：風險管理分析
            risk_manager = RiskManager.analyze(hist)
            
            # 市場環境（根據模式走不同分支）
            if is_historical:
                market_regime = MarketRegimeAnalyzer.get_market_regime_historical(market, analysis_date)
            else:
                market_regime = MarketRegimeAnalyzer.get_market_regime(market)
            
            # 波段分析
            wave_analysis = WaveAnalyzer.analyze_wave(hist)
            
            # 均值回歸分析
            mean_reversion = MeanReversionAnalyzer.analyze(hist)
            
            # ============================================================
            # 組裝結果（使用即時股價如果有的話）
            # ============================================================
            # 先取得昨收價（日期對齊；與主程式 K 線視窗共用同一邏輯確保一致）
            prev_close_hist = QuickAnalyzer.aligned_prev_close(hist)
            if prev_close_hist is None:
                prev_close_hist = round(hist['Close'].iloc[-1], 2)
            
            if realtime_price is not None:
                current_price = realtime_price
                # 修正錯位 bug：優先用即時報價「同源」的昨收（current 與 prev 來自
                # 同一來源同一時刻，數學上不可能超過漲跌停）。原本改用 hist 的
                # iloc[-2]，若 hist 最後一根不是今天就會差兩天，算出 +11.6% 假漲幅。
                if realtime_prev_close and realtime_prev_close > 0:
                    prev_close = realtime_prev_close
                    price_change = round(current_price - prev_close, 2)
                    price_change_pct = round((current_price / prev_close - 1) * 100, 2)
                else:
                    # 爬蟲未提供昨收 → 退回 hist 昨收（可能錯位，由 price_anomaly 防護）
                    prev_close = prev_close_hist
                    price_change = round(current_price - prev_close, 2)
                    price_change_pct = round((current_price / prev_close - 1) * 100, 2) if prev_close > 0 else 0
            else:
                current_price = round(hist['Close'].iloc[-1], 2)
                prev_close = prev_close_hist
                price_change = round(current_price - prev_close, 2)
                price_change_pct = round((current_price / prev_close - 1) * 100, 2) if prev_close > 0 else 0

            # 資料異常防護：台股有 ±10% 漲跌停限制，單日漲跌幅不可能超過約 10%。
            # 若超過，多半是即時報價與 hist 昨收來自不同日期/來源（資料未對齊），
            # 標記為可疑，避免使用者誤信（例如鴻海顯示 +11.6%）。
            price_anomaly = bool(market == "台股" and abs(price_change_pct) > 10.5)
            if price_anomaly:
                print(f"⚠️ [{symbol}] 漲跌幅異常 {price_change_pct:+.1f}%（超過±10%漲跌停），"
                      f"即時價 {current_price} 與昨收 {prev_close} 可能未對齊")

            result = {
                "symbol": symbol,
                "name": stock_name,  # v4.3 新增：股票名稱
                "current_price": current_price,
                "prev_close": prev_close,
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "price_anomaly": price_anomaly,  # 漲跌幅超過±10%漲跌停 → 資料可疑
                "price_source": price_source,  # v4.3 新增：標註價格來源
                "technical": technical,
                "fundamental": fundamental,
                "risk_metrics": risk_metrics,
                "support_resistance": support_resistance,
                "chip_flow": chip_flow,
                "volume_analysis": volume_analysis,
                "volume_price": volume_price,  # v4.4.1 新增：量價分析
                "risk_manager": risk_manager,  # v4.4.1 新增：風險管理
                "market_regime": market_regime,
                "wave_analysis": wave_analysis,
                "mean_reversion": mean_reversion,
                "recommendation": ""
            }
            
            # v4.4.6 新增：形態分析
            if QuantConfig.ENABLE_PATTERN_ANALYSIS:
                try:
                    from analyzers import PatternAnalyzer
                    pattern_analysis = PatternAnalyzer.analyze(
                        hist, 
                        lookback=QuantConfig.PATTERN_LOOKBACK_DAYS
                    )
                    result["pattern_analysis"] = pattern_analysis
                except Exception as e:
                    print(f"形態分析錯誤: {e}")
                    result["pattern_analysis"] = {'available': False, 'message': str(e)}
            else:
                result["pattern_analysis"] = {'available': False, 'message': '形態分析已停用'}
            
            # === v4.5.19 相對強度 (RS) 計算 ===
            # A2 修正：原本用 DataSourceManager.get_history("TWII","美股") 取大盤，
            # 但 yfinance 需要 "^TWII"，去掉 "^" 後變成查無此代碼（404）→ RS 永遠
            # fallback 成 50/0，導致全系統 RS 因子（含 L1 ±12、L2 動能模式）失效。
            # 改用與 beta 計算相同、可正常運作的 yf.Ticker(MARKET_INDEX) 路徑，並加快取。
            try:
                market_symbol = QuantConfig.MARKET_INDEX_TW if market == "台股" else QuantConfig.MARKET_INDEX_US
                market_hist = QuickAnalyzer._get_index_history_cached(market_symbol)

                if market_hist is not None and len(market_hist) > 20:
                    # 計算 5/20/60 日相對表現
                    stock_ret_5d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-5] - 1) * 100 if len(hist) > 5 else 0
                    stock_ret_20d = (hist['Close'].iloc[-1] / hist['Close'].iloc[-20] - 1) * 100 if len(hist) > 20 else 0

                    market_ret_5d = (market_hist['Close'].iloc[-1] / market_hist['Close'].iloc[-5] - 1) * 100 if len(market_hist) > 5 else 0
                    market_ret_20d = (market_hist['Close'].iloc[-1] / market_hist['Close'].iloc[-20] - 1) * 100 if len(market_hist) > 20 else 0

                    rs_5d = stock_ret_5d - market_ret_5d      # 保留為顯示欄位（短線參考），不進分數
                    rs_20d = stock_ret_20d - market_ret_20d

                    # 60 日相對報酬（降噪主力）。資料不足 61 筆時 fallback 只用 20d 並註明。
                    _has_60d = len(hist) > 60 and len(market_hist) > 60
                    if _has_60d:
                        stock_ret_60d  = (hist['Close'].iloc[-1] / hist['Close'].iloc[-60] - 1) * 100
                        market_ret_60d = (market_hist['Close'].iloc[-1] / market_hist['Close'].iloc[-60] - 1) * 100
                        rs_60d = stock_ret_60d - market_ret_60d
                        # 20 日 40% + 60 日 60%：拉長觀察窗，避免大盤單日波動翻轉 RS
                        rs_score = rs_20d * 0.4 + rs_60d * 0.6
                        rs_note = ''
                    else:
                        rs_60d = None
                        rs_score = rs_20d          # 資料不足：只用 20d
                        rs_note = '資料不足60日，RS僅採20日'

                    # 標準化到 0–100：±25% 超額報酬映射到 0–100
                    normalized_rs = max(0, min(100, 50 + rs_score * 2))

                    result["relative_strength"] = {
                        'rs_score': round(normalized_rs, 1),
                        'vs_market': round(rs_score, 2),
                        'rs_5d': round(rs_5d, 2),      # 顯示用
                        'rs_20d': round(rs_20d, 2),
                        'rs_60d': round(rs_60d, 2) if rs_60d is not None else None,
                        'rs_note': rs_note,
                    }
                else:
                    result["relative_strength"] = {'rs_score': 50, 'vs_market': 0}
            except Exception as rs_err:
                print(f"[RS] 相對強度計算錯誤: {rs_err}")
                result["relative_strength"] = {'rs_score': 50, 'vs_market': 0}
            
            # === v4.5.19 新增：trend 結構 (用於評分系統) ===
            result["trend"] = {
                'primary_trend': technical.get('trend', '盤整'),
                'ma20_slope': technical.get('ma20_slope', 0)
            }

            # ═══════════════════════════════════════════════════════════
            # build_prompt_04：月營收動能 + 雙時間框架標籤（不進 A/B/C grade）
            # ═══════════════════════════════════════════════════════════
            # 20日均量（張）：hist Volume 為股 → /1000 轉張
            try:
                avg_vol_20d_lots = int(hist['Volume'].tail(20).mean() / 1000) if len(hist) >= 20 else 0
            except Exception:
                avg_vol_20d_lots = 0
            result["avg_vol_20d_lots"] = avg_vol_20d_lots

            # 月營收動能（讀 DB；scan_mode 不打 API，單檔分析缺資料才 backfill）
            revenue_momentum = {'available': False}
            if market == "台股" and not is_historical:
                try:
                    from revenue_data_manager import get_revenue_manager
                    _rm = get_revenue_manager(QuickAnalyzer.get_db().db_name)
                    revenue_momentum = _rm.get_revenue_momentum(symbol)
                    if not revenue_momentum.get('available') and not scan_mode:
                        _rm.backfill(symbol, months=24)
                        revenue_momentum = _rm.get_revenue_momentum(symbol)
                except Exception as _re:
                    print(f"[營收] {symbol} 讀取略過: {_re}")

            # 實證組合標籤：投信連買≥3 + YoY≥20% + 創12月高 + 20日均量≥300張
            _chip = result.get('chip_flow', {}) or {}
            _trust_days = _chip.get('trust_consecutive_days', 0) or 0
            _yoy = revenue_momentum.get('revenue_yoy')
            _combo = bool(
                _trust_days >= 3
                and _yoy is not None and _yoy >= 0.20
                and revenue_momentum.get('is_12m_high')
                and avg_vol_20d_lots >= 300
            )
            revenue_momentum['combo_signal'] = _combo
            revenue_momentum['combo_label'] = '🔥投信+營收動能' if _combo else ''
            revenue_momentum['ranking_boost'] = 15 if _combo else 0
            result["revenue_momentum"] = revenue_momentum

            # 雙時間框架標籤（Task 5）：短波段 / 趨勢波段（僅報表/排序/篩選，不改 grade）
            result["timeframe_profile"] = QuickAnalyzer._compute_timeframe_profile(
                technical, result.get('relative_strength', {}), result.get('volume_price', {}),
                current_price
            )

            # build_prompt_08：族群動能加註（顯示/排序用，不進 grade；歷史模式跳過）
            if market == "台股" and not is_historical:
                try:
                    result["theme_info"] = QuickAnalyzer._get_theme_info(symbol)
                except Exception:
                    result["theme_info"] = {}

            # 歷史模式額外欄位
            if is_historical:
                result["is_historical"] = True
                result["analysis_date"] = actual_date
                result["requested_date"] = analysis_date.strftime('%Y-%m-%d')
            
            # 決策矩陣
            decision_matrix = DecisionMatrix.analyze(result)
            result["decision_matrix"] = decision_matrix
            
            # 生成建議（便宜，產出 A/B/C 評級字串供 watchlist/報告顯示；scan_mode 也保留）
            result["recommendation"] = QuickAnalyzer._generate_recommendation_v43(result, decision_matrix)

            # 策略分析（4 個策略回測，不進三層評級；scan_mode 跳過，留給 Backtest 按鈕需要時才跑）
            if scan_mode:
                result["strategies"], result["best_strategy"] = [], None
            else:
                result["strategies"], result["best_strategy"] = QuickAnalyzer.analyze_strategies_v4(
                    hist, technical, fundamental, market_regime
                )

            result["data_time"] = hist.index[-1].strftime('%Y-%m-%d %H:%M:%S')
            
            # 歷史模式：計算未來驗證數據
            if is_historical:
                result["future_validation"] = QuickAnalyzer._calculate_future_validation(
                    stock, analysis_date, hist['Close'].iloc[-1]
                )
            
            return result
            
        except Exception as e:
            print(f"分析錯誤 {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def analyze_stock_historical(symbol, market="台股", analysis_date=None):
        """
        歷史日期分析（向後兼容，實際調用 analyze_stock）
        """
        return QuickAnalyzer.analyze_stock(symbol, market, analysis_date)
    
    @staticmethod
    def _fundamental_analysis_v4(stock, ticker_symbol, hist=None, is_historical=False):
        """
        v4.3 改進：基本面分析（整合即時與歷史模式）
        v4.4.7 更新：使用 YFinanceRateLimiter.get_info_safe 避免速率限制
        
        即時模式：使用 Forward PE + PE Band
        歷史模式：Forward PE 不可用，僅使用 Trailing PE
        """
        try:
            # 如果 stock 為 None，嘗試創建
            if stock is None:
                stock = YFinanceRateLimiter.get_ticker_safe(ticker_symbol)
            
            # 如果還是 None，返回預設值
            if stock is None:
                return QuickAnalyzer._get_default_fundamental()
            
            # 使用安全的 info 取得方法（帶快取和熔斷）
            info = YFinanceRateLimiter.get_info_safe(stock)
            
            # 取得基本數據
            trailing_pe = info.get("trailingPE", None)
            pb = info.get("priceToBook", None)
            sector = info.get("sector", "Unknown")
            industry = info.get("industry", "Unknown")
            
            # 取得 EPS 數據
            trailing_eps = info.get("trailingEps", None)
            forward_eps = info.get("forwardEps", None)
            
            # 取得殖利率
            dividend_yield = info.get("dividendYield", None)
            
            # Forward PE（僅即時模式可用）
            if is_historical:
                forward_pe = None
            else:
                forward_pe = info.get("forwardPE", None)
            
            # PE Band 計算
            pe_percentile = None
            pe_band_signal = "中性"
            
            if trailing_pe is not None:
                try:
                    # 即時模式：使用 5 年歷史數據
                    # 歷史模式：使用傳入的 hist 數據
                    if is_historical and hist is not None and len(hist) > 60:
                        hist_for_pe = hist
                    else:
                        hist_for_pe = YFinanceRateLimiter.get_history(stock, period="5y")
                    
                    if hist_for_pe is not None and len(hist_for_pe) > 252:  # 至少一年數據
                        current_price = hist_for_pe['Close'].iloc[-1]
                        implied_eps = current_price / trailing_pe if trailing_pe > 0 else 1
                        
                        historical_pe = hist_for_pe['Close'] / implied_eps
                        pe_percentile = percentileofscore(historical_pe.dropna(), trailing_pe)
                        
                        if pe_percentile < 20:
                            pe_band_signal = "歷史低檔（偏多）"
                        elif pe_percentile > 80:
                            pe_band_signal = "歷史高檔（偏空）"
                        else:
                            pe_band_signal = f"歷史 {pe_percentile:.0f}% 位置（中性）"
                except Exception as e:
                    print(f"PE Band 計算錯誤: {e}")
            
            # 綜合評級
            signal = "中性"
            signal_reason = []
            
            # Forward PE 判斷（即時模式優先使用）
            if forward_pe is not None and not is_historical:
                if forward_pe < 12:
                    signal = "偏多"
                    signal_reason.append(f"預估PE={forward_pe:.1f}偏低")
                elif forward_pe > 25:
                    signal = "偏空"
                    signal_reason.append(f"預估PE={forward_pe:.1f}偏高")
            elif trailing_pe is not None:
                # 歷史模式或無 Forward PE 時使用 Trailing PE
                if trailing_pe < 12:
                    signal = "偏多"
                    signal_reason.append(f"本益比={trailing_pe:.1f}偏低")
                elif trailing_pe > 25:
                    signal = "偏空"
                    signal_reason.append(f"本益比={trailing_pe:.1f}偏高")
            
            # PE Band 調整
            if pe_percentile is not None:
                if pe_percentile < 20:
                    if signal != "偏多":
                        signal = "偏多"
                    signal_reason.append("PE處於歷史低檔")
                elif pe_percentile > 80:
                    if signal != "偏空":
                        signal = "偏空"
                    signal_reason.append("PE處於歷史高檔")
            
            return {
                "trailing_pe": round(trailing_pe, 2) if trailing_pe else "N/A",
                "forward_pe": "歷史模式不可用" if is_historical else (round(forward_pe, 2) if forward_pe else "N/A"),
                "pb": round(pb, 2) if pb else "N/A",
                "eps": round(trailing_eps, 2) if trailing_eps else "N/A",
                "forward_eps": round(forward_eps, 2) if forward_eps else "N/A",
                "dividend_yield": round(dividend_yield, 4) if dividend_yield else "N/A",
                "sector": sector,
                "industry": industry,
                "pe_percentile": round(pe_percentile, 1) if pe_percentile else "N/A",
                "pe_band_signal": pe_band_signal,
                "signal": signal,
                "signal_reason": "；".join(signal_reason) if signal_reason else "數據有限",
                "is_historical": is_historical
            }
            
        except Exception as e:
            print(f"基本面分析錯誤: {e}")
            return {
                "trailing_pe": "N/A",
                "forward_pe": "歷史模式不可用" if is_historical else "N/A",
                "pb": "N/A",
                "eps": "N/A",
                "forward_eps": "N/A",
                "dividend_yield": "N/A",
                "sector": "Unknown",
                "industry": "Unknown",
                "pe_percentile": "N/A",
                "pe_band_signal": "無法判斷",
                "signal": "中性",
                "signal_reason": "數據有限",
                "is_historical": is_historical
            }
    
    @staticmethod
    def _analyze_chip_flow_historical(symbol, market, analysis_date):
        """嘗試取得歷史籌碼數據"""
        try:
            if market != "台股":
                return {
                    "available": False,
                    "message": "歷史籌碼僅支援台股"
                }
            
            # 嘗試查詢證交所歷史數據
            date_str = analysis_date.strftime('%Y%m%d')
            url = "https://www.twse.com.tw/fund/T86"
            params = {
                'response': 'json',
                'date': date_str,
                'selectType': 'ALL'
            }
            
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            
            if 'data' not in data or not data['data']:
                return {
                    "available": False,
                    "message": f"{analysis_date.strftime('%Y-%m-%d')} 無籌碼資料（可能為非交易日）"
                }
            
            for row in data['data']:
                if row[0] == symbol:
                    foreign_investor = int(row[4].replace(',', ''))
                    investment_trust = int(row[10].replace(',', ''))
                    
                    # 判斷籌碼狀態
                    if foreign_investor > 0 and investment_trust > 0:
                        signal = "籌碼偏多"
                    elif foreign_investor < 0 and investment_trust < 0:
                        signal = "籌碼偏空"
                    else:
                        signal = "籌碼中性"
                    
                    return {
                        "available": True,
                        "foreign": f"{'買超' if foreign_investor > 0 else '賣超'} {abs(foreign_investor):,} 張",
                        "trust": f"{'買超' if investment_trust > 0 else '賣超'} {abs(investment_trust):,} 張",
                        "dealer": "歷史模式",
                        "foreign_continuous": "歷史單日",
                        "trust_continuous": "歷史單日",
                        "signal": signal,
                        "signal_color": "positive" if signal == "籌碼偏多" else "negative" if signal == "籌碼偏空" else "neutral",
                        "message": f"📅 歷史籌碼 ({analysis_date.strftime('%Y-%m-%d')})",
                        "is_historical": True
                    }
            
            return {
                "available": False,
                "message": f"找不到 {symbol} 在 {analysis_date.strftime('%Y-%m-%d')} 的籌碼資料"
            }
            
        except Exception as e:
            return {
                "available": False,
                "message": f"歷史籌碼查詢失敗: {str(e)}"
            }
    
    @staticmethod
    def _calculate_future_validation(stock, analysis_date, analysis_price):
        """
        計算分析日期之後的實際走勢（用於驗證策略準確度）
        v4.4.7 更新：使用 YFinanceRateLimiter
        """
        try:
            # 取得分析日期之後的數據
            future_start = analysis_date + datetime.timedelta(days=1)
            future_end = datetime.datetime.now()
            
            if future_start >= future_end:
                return {
                    "available": False,
                    "message": "分析日期之後尚無數據"
                }
            
            future_hist = YFinanceRateLimiter.get_history(
                stock,
                start=future_start.strftime('%Y-%m-%d'),
                end=future_end.strftime('%Y-%m-%d')
            )
            
            if future_hist is None or future_hist.empty or len(future_hist) < 1:
                return {
                    "available": False,
                    "message": "無法取得後續數據"
                }
            
            # 計算各時間段的漲跌幅
            validation = {
                "available": True,
                "analysis_price": round(analysis_price, 2)
            }
            
            # 5天後
            if len(future_hist) >= 5:
                price_5d = future_hist['Close'].iloc[4]
                change_5d = (price_5d / analysis_price - 1) * 100
                validation["5d_price"] = round(price_5d, 2)
                validation["5d_change"] = round(change_5d, 2)
            
            # 10天後
            if len(future_hist) >= 10:
                price_10d = future_hist['Close'].iloc[9]
                change_10d = (price_10d / analysis_price - 1) * 100
                validation["10d_price"] = round(price_10d, 2)
                validation["10d_change"] = round(change_10d, 2)
            
            # 20天後
            if len(future_hist) >= 20:
                price_20d = future_hist['Close'].iloc[19]
                change_20d = (price_20d / analysis_price - 1) * 100
                validation["20d_price"] = round(price_20d, 2)
                validation["20d_change"] = round(change_20d, 2)
            
            # 最高價和最低價
            validation["max_price"] = round(future_hist['High'].max(), 2)
            validation["max_change"] = round((future_hist['High'].max() / analysis_price - 1) * 100, 2)
            validation["min_price"] = round(future_hist['Low'].min(), 2)
            validation["min_change"] = round((future_hist['Low'].min() / analysis_price - 1) * 100, 2)
            
            # 當前價格
            validation["current_price"] = round(future_hist['Close'].iloc[-1], 2)
            validation["current_change"] = round((future_hist['Close'].iloc[-1] / analysis_price - 1) * 100, 2)
            validation["days_elapsed"] = len(future_hist)
            
            return validation
            
        except Exception as e:
            print(f"未來驗證計算錯誤: {e}")
            return {
                "available": False,
                "message": f"計算錯誤: {str(e)}"
            }
        """v4.0 改進：基本面分析（PE Band + Forward PE）"""
        try:
            info = stock.info
            
            # 取得當前 PE 和預估 PE
            trailing_pe = info.get("trailingPE", None)
            forward_pe = info.get("forwardPE", None)
            pb = info.get("priceToBook", None)
            sector = info.get("sector", "Unknown")
            industry = info.get("industry", "Unknown")
            
            # v4.0 新增：計算 PE Band（歷史百分位）
            pe_percentile = None
            pe_band_signal = "中性"
            
            if trailing_pe is not None:
                try:
                    # 嘗試獲取歷史 PE 數據（透過歷史價格和 EPS 估算）
                    hist_5y = stock.history(period="5y")
                    if len(hist_5y) > 252:  # 至少一年數據
                        # 簡化計算：假設近期 EPS 穩定，用價格變動估算 PE 分布
                        # 實際應用中應使用真實的歷史 EPS 數據
                        current_price = hist_5y['Close'].iloc[-1]
                        implied_eps = current_price / trailing_pe if trailing_pe > 0 else 1
                        
                        # 計算歷史 PE 分布
                        historical_pe = hist_5y['Close'] / implied_eps
                        pe_percentile = percentileofscore(historical_pe.dropna(), trailing_pe)
                        
                        if pe_percentile < 20:
                            pe_band_signal = "歷史低檔（偏多）"
                        elif pe_percentile > 80:
                            pe_band_signal = "歷史高檔（偏空）"
                        else:
                            pe_band_signal = f"歷史 {pe_percentile:.0f}% 位置（中性）"
                except Exception as e:
                    print(f"PE Band 計算錯誤: {e}")
            
            # 綜合評級（v4.0改進：考慮 Forward PE 和 PE Band）
            signal = "中性"
            signal_reason = []
            
            # v4.4.2 修正：檢查 PE 是否為負值（公司虧損）
            pe_is_negative = False
            if forward_pe is not None and forward_pe < 0:
                pe_is_negative = True
                signal_reason.append(f"公司虧損(預估PE={forward_pe:.1f})")
            elif trailing_pe is not None and trailing_pe < 0:
                pe_is_negative = True
                signal_reason.append(f"公司虧損(當前PE={trailing_pe:.1f})")
            
            # PE 為負值時，改用 PB 判斷
            if pe_is_negative:
                if pb is not None and pb > 0:
                    if pb < 1.0:
                        signal = "中性"
                        signal_reason.append(f"PB={pb:.2f}<1（低於淨值）")
                    elif pb > 3.0:
                        signal = "偏空"
                        signal_reason.append(f"PB={pb:.2f}偏高")
                    else:
                        signal = "中性"
                        signal_reason.append(f"PB={pb:.2f}正常")
                else:
                    signal = "中性"
                    signal_reason.append("PE無效，需觀察獲利改善")
            else:
                # Forward PE 判斷（市場交易的是未來）- 必須是正數
                if forward_pe is not None and forward_pe > 0:
                    if forward_pe < 12:
                        signal = "偏多"
                        signal_reason.append(f"預估PE={forward_pe:.1f}偏低")
                    elif forward_pe > 25:
                        signal = "偏空"
                        signal_reason.append(f"預估PE={forward_pe:.1f}偏高")
                
                # PE Band 調整
                if pe_percentile is not None:
                    if pe_percentile < 20:
                        if signal != "偏多":
                            signal = "偏多"
                        signal_reason.append("PE處於歷史低檔")
                    elif pe_percentile > 80:
                        if signal != "偏空":
                            signal = "偏空"
                        signal_reason.append("PE處於歷史高檔")
                
                # 如果沒有 Forward PE，使用 Trailing PE（但降低權重）- 必須是正數
                if forward_pe is None and trailing_pe is not None and trailing_pe > 0:
                    if trailing_pe < 15:
                        signal = "偏多" if signal == "中性" else signal
                        signal_reason.append(f"當前PE={trailing_pe:.1f}偏低(參考)")
                    elif trailing_pe > 30:
                        signal = "偏空" if signal == "中性" else signal
                        signal_reason.append(f"當前PE={trailing_pe:.1f}偏高(參考)")
            
            return {
                "signal": signal,
                "signal_reason": "，".join(signal_reason) if signal_reason else "無特別訊號",
                "trailing_pe": trailing_pe if trailing_pe else "N/A",
                "forward_pe": forward_pe if forward_pe else "N/A",
                "pe_percentile": round(pe_percentile, 1) if pe_percentile else "N/A",
                "pe_band_signal": pe_band_signal,
                "pb": pb if pb else "N/A",
                "sector": sector,
                "industry": industry
            }
        except Exception as e:
            print(f"基本面分析錯誤: {e}")
            return {
                "signal": "中性", 
                "signal_reason": "資料不足",
                "trailing_pe": "N/A", 
                "forward_pe": "N/A",
                "pe_percentile": "N/A",
                "pe_band_signal": "N/A",
                "pb": "N/A",
                "sector": "Unknown",
                "industry": "Unknown"
            }
    
    @staticmethod
    def _calculate_risk_metrics_v4(hist_long, ticker_symbol, market="台股"):
        """v4.0 改進：使用長期數據計算風險指標 + Beta 係數"""
        try:
            if hist_long.empty or len(hist_long) < 60:
                return QuickAnalyzer._get_default_risk_metrics()
            
            daily_returns = hist_long['Close'].pct_change(fill_method=None).dropna()
            
            # 年化波動率
            volatility = daily_returns.std() * np.sqrt(252) * 100
            
            # v4.0 改進：使用長期數據計算 VaR
            var_95 = np.percentile(daily_returns, 5) * 100
            var_99 = np.percentile(daily_returns, 1) * 100  # 新增 99% VaR
            
            # 最大回撤
            cumulative = (1 + daily_returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = drawdown.min() * 100
            
            # v4.0 新增：Beta 係數計算
            beta = QuickAnalyzer._calculate_beta(daily_returns, market)
            
            # 波動率分級
            if volatility < 20:
                vol_level = "低波動"
            elif volatility < 40:
                vol_level = "中波動"
            else:
                vol_level = "高波動"
            
            # v4.0 新增：Beta 分類
            if beta is not None:
                if beta < 0.8:
                    beta_type = "防禦型（低Beta）"
                elif beta > 1.2:
                    beta_type = "攻擊型（高Beta）"
                else:
                    beta_type = "中性型"
            else:
                beta_type = "N/A"
            
            return {
                "volatility": round(volatility, 2),
                "vol_level": vol_level,
                "var_95": round(var_95, 2),
                "var_99": round(var_99, 2),  # v4.0 新增
                "max_drawdown": round(max_drawdown, 2),
                "beta": round(beta, 2) if beta else "N/A",  # v4.0 新增
                "beta_type": beta_type,  # v4.0 新增
                "data_period": f"{len(hist_long)}天 ({QuantConfig.RISK_DATA_YEARS}年)"  # v4.0 新增
            }
        except Exception as e:
            print(f"風險指標計算錯誤: {e}")
            return QuickAnalyzer._get_default_risk_metrics()
    
    @staticmethod
    def _get_default_risk_metrics():
        """返回預設風險指標"""
        return {
            "volatility": 0,
            "vol_level": "未知",
            "var_95": 0,
            "var_99": 0,
            "max_drawdown": 0,
            "beta": "N/A",
            "beta_type": "N/A",
            "data_period": "N/A"
        }
    
    @staticmethod
    def _get_default_fundamental():
        """返回預設基本面數據（當無法取得時使用）"""
        return {
            "signal": "中性",
            "signal_reason": "資料不足",
            "trailing_pe": "N/A",
            "forward_pe": "N/A",
            "pe_percentile": "N/A",
            "pe_band_signal": "N/A",
            "pb": "N/A",
            "eps": "N/A",
            "forward_eps": "N/A",
            "dividend_yield": "N/A",
            "sector": "Unknown",
            "industry": "Unknown"
        }
    
    @staticmethod
    def _calculate_beta(stock_returns, market="台股"):
        """v4.0 新增：計算 Beta 係數"""
        try:
            # 取得大盤數據
            if market == "台股":
                index_symbol = QuantConfig.MARKET_INDEX_TW
            else:
                index_symbol = QuantConfig.MARKET_INDEX_US
            
            # B2 #4：改用當日快取的大盤指數（原本每檔都重抓 2y，純浪費網路）
            index_hist = QuickAnalyzer._get_index_history_cached(
                index_symbol, period=f"{QuantConfig.RISK_DATA_YEARS}y"
            )

            if index_hist is None or index_hist.empty:
                return None
            
            index_returns = index_hist['Close'].pct_change(fill_method=None).dropna()
            
            # 對齊日期
            common_dates = stock_returns.index.intersection(index_returns.index)
            if len(common_dates) < 60:
                return None
            
            stock_aligned = stock_returns.loc[common_dates]
            index_aligned = index_returns.loc[common_dates]
            
            # 計算協方差和變異數
            covariance = stock_aligned.cov(index_aligned)
            market_variance = index_aligned.var()
            
            if market_variance > 0:
                beta = covariance / market_variance
                return beta
            return None
            
        except Exception as e:
            print(f"Beta 計算錯誤: {e}")
            return None
    
    @staticmethod
    def _analyze_volume_spike(hist):
        """v4.0 新增：成交量異常偵測"""
        try:
            if len(hist) < QuantConfig.VOLUME_MA_PERIOD + 1:
                return {"spike_detected": False, "message": "資料不足"}
            
            # 計算成交量移動平均
            volume_ma = hist['Volume'].rolling(window=QuantConfig.VOLUME_MA_PERIOD).mean()
            current_volume = hist['Volume'].iloc[-1]
            avg_volume = volume_ma.iloc[-1]
            
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # 判斷是否爆量
            spike_detected = volume_ratio >= QuantConfig.VOLUME_SPIKE_THRESHOLD
            
            # 分析爆量的意義
            price_change = (hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100
            
            if spike_detected:
                if price_change > 1:
                    spike_signal = "爆量上漲（可能是突破訊號）"
                    spike_action = "偏多"
                elif price_change < -1:
                    spike_signal = "爆量下跌（可能是恐慌賣壓）"
                    spike_action = "偏空"
                else:
                    spike_signal = "爆量震盪（可能是換手）"
                    spike_action = "中性"
            else:
                spike_signal = "成交量正常"
                spike_action = "中性"
            
            # 近5日成交量趨勢
            recent_volumes = hist['Volume'].tail(5)
            volume_trend = "放大" if recent_volumes.iloc[-1] > recent_volumes.iloc[0] else "縮小"
            
            return {
                "spike_detected": spike_detected,
                "volume_ratio": round(volume_ratio, 2),
                "current_volume": int(current_volume),
                "avg_volume": int(avg_volume),
                "spike_signal": spike_signal,
                "spike_action": spike_action,
                "volume_trend": volume_trend,
                "price_change": round(price_change, 2)
            }
        except Exception as e:
            print(f"成交量分析錯誤: {e}")
            return {"spike_detected": False, "message": f"分析錯誤: {e}"}
    
    @staticmethod
    def _analyze_chip_flow_cached(symbol, market="台股", scan_mode=False):
        """
        籌碼面分析統一出口（build_prompt_03）。

        改由 ChipDataManager.get_chip_flow() 提供：FinMind 主源 + SQLite 落地 +
        本地依交易日曆計算連買天數 + 缺日偵測。DB 無資料時 get_chip_flow 內部
        會先觸發 backfill 再讀。掃描模式下 daily_update 已在掃描前批次跑過，
        此處只讀 DB / 命中既有資料，維持零額外 API 呼叫的熱路徑原則。

        舊版 _analyze_chip_flow_wukong / _crawl_invest 已 deprecate（見下），
        僅保留供 debug 交叉比對，不在主流程呼叫。
        """
        if market != "台股":
            return {
                "available": False,
                "message": "籌碼面分析僅適用於台股"
            }
        try:
            from chip_data_manager import get_chip_manager
            mgr = get_chip_manager(QuickAnalyzer.get_db().db_name)
            # 掃描熱路徑 allow_fetch=False → 只讀 DB、零 API（daily_update 已批次補過）
            return mgr.get_chip_flow(symbol, allow_fetch=not scan_mode)
        except Exception as e:
            print(f"[籌碼] {symbol} ChipDataManager 失敗: {e}")
            import traceback
            traceback.print_exc()
            return {"available": False, "message": f"籌碼分析失敗: {str(e)}"}

    @staticmethod
    def _analyze_chip_flow_wukong(symbol):
        """
        [DEPRECATED build_prompt_03] 悟空 API 籌碼（連續筆數非連續交易日、無缺日偵測）。
        已被 ChipDataManager 取代，不在主流程呼叫；僅保留供 debug 交叉比對。

        API: https://api.wukong.com.tw/stock/{stockId}/iibs
        
        實際回傳格式：
        {
          "iibs": [
            {
              "inputDate": "2026-01-16",
              "foreignInvestorsBuySell": 10105,    // 外資買賣超（張數）
              "investmentTrustBuySell": 208,        // 投信買賣超（張數）
              "dealerBuySell": -1134,               // 自營商買賣超（張數）
              "total": 9179
            },
            ...
          ]
        }
        """
        try:
            url = f"https://api.wukong.com.tw/stock/{symbol}/iibs"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://wukong.com.tw/'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"[悟空API] {symbol} 請求失敗: {response.status_code}")
                return None
            
            data = response.json()
            
            # 正確解析格式：{"iibs": [...]}
            iibs_list = data.get('iibs', [])
            if not iibs_list:
                print(f"[悟空API] {symbol} 無 iibs 數據")
                return None
            
            # 依日期排序取最新筆
            try:
                iibs_list_sorted = sorted(iibs_list, key=lambda x: x.get('inputDate', ''), reverse=True)
                latest = iibs_list_sorted[0]
                print(f"[悟空API] {symbol} 取得最新資料日期：{latest.get('inputDate', 'N/A')}")
            except (ValueError, TypeError, IndexError):
                print(f"[悟空API] {symbol} 排序失敗，使用第一筆")
                latest = iibs_list[0]
            
            # 解析正確的欄位名稱（數值為張數）
            foreign_net = latest.get('foreignInvestorsBuySell', 0) or 0  # 張數
            trust_net = latest.get('investmentTrustBuySell', 0) or 0      # 張數
            dealer_net = latest.get('dealerBuySell', 0) or 0              # 張數
            total_net = latest.get('total', 0) or 0
            
            print(f"[悟空API] {symbol} 解析結果：外資={foreign_net}張, 投信={trust_net}張, 自營商={dealer_net}張")
            
            # 計算連續天數（分析歷史數據）
            foreign_consecutive_days = 0
            trust_consecutive_days = 0
            
            # 往前找連續同方向的天數
            if len(iibs_list_sorted) >= 2:
                # 外資連續天數
                if foreign_net > 0:
                    for i, item in enumerate(iibs_list_sorted):
                        if item.get('foreignInvestorsBuySell', 0) > 0:
                            foreign_consecutive_days = i + 1
                        else:
                            break
                elif foreign_net < 0:
                    for i, item in enumerate(iibs_list_sorted):
                        if item.get('foreignInvestorsBuySell', 0) < 0:
                            foreign_consecutive_days = -(i + 1)  # 負值表示賣超
                        else:
                            break
                
                # 投信連續天數
                if trust_net > 0:
                    for i, item in enumerate(iibs_list_sorted):
                        if item.get('investmentTrustBuySell', 0) > 0:
                            trust_consecutive_days = i + 1
                        else:
                            break
                elif trust_net < 0:
                    for i, item in enumerate(iibs_list_sorted):
                        if item.get('investmentTrustBuySell', 0) < 0:
                            trust_consecutive_days = -(i + 1)
                        else:
                            break
            else:
                # 只有一筆資料
                foreign_consecutive_days = 1 if foreign_net > 0 else (-1 if foreign_net < 0 else 0)
                trust_consecutive_days = 1 if trust_net > 0 else (-1 if trust_net < 0 else 0)
            
            print(f"[悟空API] {symbol} 連續天數：外資={foreign_consecutive_days}天, 投信={trust_consecutive_days}天")
            
            # 判斷外資訊號
            if foreign_net > 0:
                if abs(foreign_consecutive_days) >= 2:
                    foreign_text = f"連{abs(foreign_consecutive_days)}日買超"
                    foreign_signal = "偏多"
                else:
                    foreign_text = "買超"
                    foreign_signal = "中性偏多"
            elif foreign_net < 0:
                if abs(foreign_consecutive_days) >= 2:
                    foreign_text = f"連{abs(foreign_consecutive_days)}日賣超"
                    foreign_signal = "偏空"
                else:
                    foreign_text = "賣超"
                    foreign_signal = "中性偏空"
            else:
                foreign_text = "觀望"
                foreign_signal = "中性"
            
            # 判斷投信訊號
            if trust_net > 0:
                if abs(trust_consecutive_days) >= 2:
                    trust_text = f"連{abs(trust_consecutive_days)}日買超"
                    trust_signal = "偏多"
                else:
                    trust_text = "買超"
                    trust_signal = "中性偏多"
            elif trust_net < 0:
                if abs(trust_consecutive_days) >= 2:
                    trust_text = f"連{abs(trust_consecutive_days)}日賣超"
                    trust_signal = "偏空"
                else:
                    trust_text = "賣超"
                    trust_signal = "中性偏空"
            else:
                trust_text = "觀望"
                trust_signal = "中性"
            
            # 判斷自營商訊號
            if dealer_net > 0:
                dealer_text = "買超"
            elif dealer_net < 0:
                dealer_text = "賣超"
            else:
                dealer_text = "觀望"
            
            # 綜合訊號
            if foreign_signal == "偏多" and trust_signal == "偏多":
                overall_signal = "籌碼集中"
                signal_color = "positive"
            elif foreign_signal == "偏多" or trust_signal == "偏多":
                overall_signal = "籌碼偏多"
                signal_color = "positive"
            elif foreign_signal == "偏空" and trust_signal == "偏空":
                overall_signal = "籌碼分散"
                signal_color = "warning"
            elif foreign_signal == "偏空" or trust_signal == "偏空":
                overall_signal = "籌碼偏空"
                signal_color = "warning"
            else:
                overall_signal = "籌碼中性"
                signal_color = "neutral"
            
            # 格式化金額（張數轉換顯示）
            def format_volume(val):
                """格式化張數顯示"""
                abs_val = abs(val)
                if abs_val >= 10000:
                    return f"{val / 10000:.2f}萬張"
                else:
                    return f"{val:,}張"
            
            date_str = latest.get('inputDate', datetime.datetime.now().strftime('%Y-%m-%d'))
            
            return {
                "available": True,
                "data_source": "悟空API",
                "foreign": f"{foreign_text} ({format_volume(foreign_net)})",
                "trust": f"{trust_text} ({format_volume(trust_net)})",
                "dealer": f"{dealer_text} ({format_volume(dealer_net)})",
                "foreign_continuous": foreign_text,
                "trust_continuous": trust_text,
                "foreign_net": foreign_net,   # 單位：張（不再 ×1000，全系統統一用張）
                "trust_net": trust_net,
                "dealer_net": dealer_net,
                "foreign_consecutive_days": foreign_consecutive_days,
                "trust_consecutive_days": trust_consecutive_days,
                "signal": overall_signal,
                "signal_color": signal_color,
                "message": f"最新資料日期：{date_str}（悟空API）"
            }
            
        except requests.exceptions.Timeout:
            print(f"[悟空API] {symbol} 請求超時")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[悟空API] {symbol} 請求錯誤: {e}")
            return None
        except Exception as e:
            print(f"[悟空API] {symbol} 解析錯誤: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def _crawl_invest(date, stock_code):
        """[DEPRECATED build_prompt_03] 舊 TWSE T86 抓法（舊端點 /fund/T86、
        selectType='ALL' 含權證、單位股、只看最後 2 天）。已被 ChipDataManager
        的官方備援（rwd/zh/fund/T86 + ALLBUT0999，欄位以 fields 名稱定位）取代。
        僅保留供 debug 交叉比對，不在主流程呼叫。"""
        date_str = date.strftime('%Y%m%d')

        url = "https://www.twse.com.tw/fund/T86"
        params = {
            'response': 'json',
            'date': date_str,
            'selectType': 'ALL'
        }
        
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if 'data' not in data or not data['data']:
                return None
                
            for row in data['data']:
                if row[0] == stock_code:
                    foreign_investor = int(row[4].replace(',', ''))
                    investment_trust = int(row[10].replace(',', ''))
                    
                    return {
                        'date': date_str,
                        'stock_code': stock_code,
                        'foreign_investor': foreign_investor,
                        'investment_trust': investment_trust
                    }
            return None
        except Exception as e:
            return None
    
    @staticmethod
    def _analyze_chip_flow_simulated(symbol, market="台股"):
        """模擬籌碼面數據"""
        last_digit = int(symbol[-1]) if symbol[-1].isdigit() else 0
        
        if last_digit >= 7:
            return {
                "available": True,
                "foreign": "連續買超 (模擬)",
                "trust": "買超 (模擬)",
                "dealer": "模擬數據",
                "foreign_continuous": "連續買超",
                "trust_continuous": "買超",
                "signal": "籌碼集中",
                "signal_color": "positive",
                "message": "⚠️ 使用模擬數據"
            }
        elif last_digit >= 4:
            return {
                "available": True,
                "foreign": "買超 (模擬)",
                "trust": "觀望 (模擬)",
                "dealer": "模擬數據",
                "foreign_continuous": "買超",
                "trust_continuous": "觀望",
                "signal": "籌碼穩定",
                "signal_color": "neutral",
                "message": "⚠️ 使用模擬數據"
            }
        else:
            return {
                "available": True,
                "foreign": "賣超 (模擬)",
                "trust": "賣超 (模擬)",
                "dealer": "模擬數據",
                "foreign_continuous": "賣超",
                "trust_continuous": "賣超",
                "signal": "籌碼分散",
                "signal_color": "warning",
                "message": "⚠️ 使用模擬數據"
            }
    
    @staticmethod
    def _technical_analysis(hist):
        """
        技術面分析 - v4.5.19 高盛級升級
        
        新增：
        - KD 值 (k, d)
        - MACD 完整數據 (macd, macd_signal, macd_histogram)
        - MACD 背離偵測 (macd_divergence)
        - MA20 斜率 (ma20_slope)
        """
        from analyzers import calculate_kd, calculate_macd, wilder_rsi

        ma5 = hist['Close'].rolling(window=5).mean()
        ma20 = hist['Close'].rolling(window=20).mean()
        ma60 = hist['Close'].rolling(window=60).mean()

        # === 長期均線（資料不足 → None，禁止 "N/A" 字串）===
        # 富邦資料源有 1 年上限（約 240–250 個交易日），ma240 可能算不出來，
        # 引擎端（decision_engine）在 None 時等比降級，不視為錯誤
        close = hist['Close']
        ma120 = float(close.rolling(120).mean().iloc[-1]) if len(hist) >= 120 else None
        ma240 = float(close.rolling(240).mean().iloc[-1]) if len(hist) >= 240 else None

        # === MA20 序列（引擎斜率計算用）：近 6 筆 MA20，由舊到新 ===
        # decision_engine.score_direction 取 [-1] 與 [-5] 計 5 日斜率，需長度 ≥ 5
        ma20_series = [float(x) for x in ma20.tail(6)] if len(hist) >= 25 else None

        # === ATR14（Wilder 平滑）===
        tr = pd.concat([
            hist['High'] - hist['Low'],
            (hist['High'] - hist['Close'].shift(1)).abs(),
            (hist['Low'] - hist['Close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        atr14 = float(tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]) if len(hist) >= 15 else None

        # === 個股布林壓縮：BB(20,2) 帶寬處於近 120 日最低 20 百分位 ===
        bb_std = close.rolling(20).std()
        bandwidth = (4 * bb_std) / ma20            # (upper-lower)/mid = 4σ/mid
        if len(hist) >= 60:
            bw_recent = bandwidth.dropna().tail(120)
            bb_squeeze = bool(bandwidth.iloc[-1] <= bw_recent.quantile(0.20)) if len(bw_recent) > 0 else None
        else:
            bb_squeeze = None

        # RSI 計算（Wilder 平滑，共用 analyzers.wilder_rsi）
        rsi = wilder_rsi(hist['Close'], 14)

        current_price = hist['Close'].iloc[-1]
        current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
        
        # 計算 ADX
        adx, plus_di, minus_di = MarketRegimeAnalyzer.calculate_adx(hist)
        current_adx = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 20
        
        # === v4.5.19 新增：KD 計算 ===
        try:
            k_series, d_series = calculate_kd(hist)
            k_value = k_series.iloc[-1] if not pd.isna(k_series.iloc[-1]) else 50
            d_value = d_series.iloc[-1] if not pd.isna(d_series.iloc[-1]) else 50
        except:
            k_value = 50
            d_value = 50
        
        # === v4.5.19 新增：MACD 計算 ===
        try:
            macd_line, signal_line, macd_hist_series = calculate_macd(hist['Close'])
            macd = macd_line.iloc[-1] if not pd.isna(macd_line.iloc[-1]) else 0
            macd_signal = signal_line.iloc[-1] if not pd.isna(signal_line.iloc[-1]) else 0
            macd_histogram = macd_hist_series.iloc[-1] if not pd.isna(macd_hist_series.iloc[-1]) else 0
        except:
            macd = 0
            macd_signal = 0
            macd_histogram = 0
            macd_hist_series = pd.Series([0])
        
        # === v4.5.19 新增：MACD 背離偵測 ===
        macd_divergence = {'bullish_divergence': False, 'bearish_divergence': False}
        try:
            if len(hist) >= 20 and len(macd_hist_series) >= 20:
                prices = hist['Close'].values[-20:]
                macd_vals = macd_hist_series.values[-20:]
                
                # 簡化版背離偵測
                # 底背離：價格新低但 MACD 底部墊高
                price_min_idx = np.argmin(prices[-10:])
                price_prev_min_idx = np.argmin(prices[:10])
                
                if prices[-10:][price_min_idx] < prices[:10][price_prev_min_idx]:
                    # 價格創新低
                    if macd_vals[-10:][price_min_idx] > macd_vals[:10][price_prev_min_idx]:
                        # MACD 底部墊高
                        macd_divergence['bullish_divergence'] = True
                
                # 頂背離：價格新高但 MACD 頂部降低
                price_max_idx = np.argmax(prices[-10:])
                price_prev_max_idx = np.argmax(prices[:10])
                
                if prices[-10:][price_max_idx] > prices[:10][price_prev_max_idx]:
                    # 價格創新高
                    if macd_vals[-10:][price_max_idx] < macd_vals[:10][price_prev_max_idx]:
                        # MACD 頂部降低
                        macd_divergence['bearish_divergence'] = True
        except:
            pass
        
        # === v4.5.19 新增：MA20 斜率 (用於 RSI 區間判斷) ===
        try:
            ma20_slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] if not pd.isna(ma20.iloc[-5]) else 0
        except:
            ma20_slope = 0
        
        # 趨勢判斷
        if current_price > ma20.iloc[-1] > ma60.iloc[-1]:
            trend = "上升趨勢"
            signal = "偏多"
        elif current_price < ma20.iloc[-1] < ma60.iloc[-1]:
            trend = "下降趨勢"
            signal = "偏空"
        else:
            trend = "盤整格局"
            signal = "中性"

        # ═══════════════════════════════════════════════════════════════
        # build_prompt_04：波段因子（PTH / Donchian / volume z-score / 斜率 / 報酬）
        # ═══════════════════════════════════════════════════════════════
        cur = float(current_price)

        # --- 任務1：PTH 52週高接近度（George & Hwang 2004）---
        _lb = min(240, len(hist))
        high_52w = float(hist['High'].rolling(_lb).max().iloc[-1])
        low_52w  = float(hist['Low'].rolling(_lb).min().iloc[-1])
        pth_52w = round(cur / high_52w, 4) if high_52w > 0 else None
        dist_from_low_52w = round(cur / low_52w - 1, 4) if low_52w > 0 else None
        pth_short_history = len(hist) < 120   # 歷史不足120日 → PTH 參考性較低

        # --- 任務3：Donchian 20/55 通道（前N日最高，不含今日）---
        donchian_high_20 = float(hist['High'].iloc[-21:-1].max()) if len(hist) >= 21 else None
        donchian_high_55 = float(hist['High'].iloc[-56:-1].max()) if len(hist) >= 56 else None

        # 成交量 Z-Score（60日窗；今日量相對均量的標準差倍數）
        _vol = hist['Volume']
        _vwin = QuantConfig.VOLUME_ZSCORE_WINDOW
        if len(hist) >= _vwin:
            _vmean = _vol.rolling(_vwin).mean().iloc[-1]
            _vstd  = _vol.rolling(_vwin).std().iloc[-1]
            volume_zscore = round(float((_vol.iloc[-1] - _vmean) / _vstd), 2) if _vstd and _vstd > 0 else 0.0
        else:
            volume_zscore = 0.0
        _vol_spike = volume_zscore >= QuantConfig.VOLUME_ZSCORE_SPIKE

        breakout_20 = bool(donchian_high_20 is not None and cur > donchian_high_20 and _vol_spike)
        breakout_55 = bool(donchian_high_55 is not None and cur > donchian_high_55 and _vol_spike)

        # --- 任務5 素材：MA120 近20日斜率、60日報酬 ---
        try:
            _ma120_full = close.rolling(120).mean()
            if len(hist) >= 140 and not pd.isna(_ma120_full.iloc[-21]):
                ma120_slope_20d = round(float((_ma120_full.iloc[-1] - _ma120_full.iloc[-21]) / _ma120_full.iloc[-21]), 4)
            else:
                ma120_slope_20d = None
        except Exception:
            ma120_slope_20d = None
        ret_60d = round(float(cur / close.iloc[-61] - 1) * 100, 2) if len(hist) >= 61 else None

        return {
            "trend": trend,
            "signal": signal,
            "rsi": round(current_rsi, 2),
            "adx": round(current_adx, 2),
            # === build_prompt_04：波段因子 ===
            "pth_52w": pth_52w,                       # 0~1，越近1越接近52週新高
            "high_52w": round(high_52w, 2) if high_52w else None,
            "low_52w": round(low_52w, 2) if low_52w else None,
            "dist_from_low_52w": dist_from_low_52w,   # 距52週低點漲幅
            "pth_short_history": pth_short_history,
            "donchian_high_20": round(donchian_high_20, 2) if donchian_high_20 else None,
            "donchian_high_55": round(donchian_high_55, 2) if donchian_high_55 else None,
            "volume_zscore": volume_zscore,
            "breakout_20": breakout_20,               # Donchian20 帶量突破
            "breakout_55": breakout_55,               # Donchian55 帶量突破（中期）
            "ma120_slope_20d": ma120_slope_20d,
            "ret_60d": ret_60d,                       # 60日報酬%（橫斷面RS用）
            # 均線：資料不足 → None（禁止 "N/A" 字串，避免下游 float 與 str 比較拋錯）
            "ma5": round(ma5.iloc[-1], 2) if not pd.isna(ma5.iloc[-1]) else None,
            "ma20": round(ma20.iloc[-1], 2) if not pd.isna(ma20.iloc[-1]) else None,
            "ma60": round(ma60.iloc[-1], 2) if not pd.isna(ma60.iloc[-1]) else None,
            # === 決策引擎接線新增欄位（資料不足 → None）===
            "ma120": round(ma120, 2) if ma120 is not None else None,
            "ma240": round(ma240, 2) if ma240 is not None else None,
            "ma20_series": ma20_series,                      # list[float]（舊→新，長度 6）或 None
            "atr": round(atr14, 2) if atr14 is not None else None,     # 同值兩鍵，相容引擎現有讀取
            "atr14": round(atr14, 2) if atr14 is not None else None,
            "bb_squeeze": bb_squeeze,                        # bool 或 None（個股布林壓縮）
            # === v4.5.19 新增欄位 ===
            "k": round(k_value, 2),
            "d": round(d_value, 2),
            "macd": round(macd, 4),
            "macd_signal": round(macd_signal, 4),
            "macd_histogram": round(macd_histogram, 4),
            "macd_divergence": macd_divergence,
            "ma20_slope": round(ma20_slope, 4)
        }
    
    @staticmethod
    def _compute_timeframe_profile(tech, rs_data, vp, current, rs_rank_60d=None):
        """
        build_prompt_04 任務5：雙時間框架標籤（僅報表/排序/篩選，不改 A/B/C grade）。

        short_swing_ready（5–20日）：突破型觸發 + 相對強度 + 量能
        position_trend_ready（1–6月）：Minervini 趨勢模板簡化版（用現有均線層）

        rs_rank_60d（橫斷面同儕排名）優先；單檔分析尚無排名時，以 normalized_rs
        （對大盤）作 proxy。ma240=None 時 position_trend 以三層判斷（沿用 fix_01 等比降級）。
        """
        def _n(x):
            if x is None or isinstance(x, str):
                return None
            try:
                v = float(x)
                return None if v != v else v
            except (TypeError, ValueError):
                return None

        cur   = _n(current)
        ma60  = _n(tech.get('ma60'))
        ma120 = _n(tech.get('ma120'))
        ma240 = _n(tech.get('ma240'))
        slope = _n(tech.get('ma120_slope_20d'))
        pth   = _n(tech.get('pth_52w'))
        dfl   = _n(tech.get('dist_from_low_52w'))

        # 相對強度門檻：優先橫斷面排名，否則用對大盤 normalized_rs proxy
        if rs_rank_60d is not None:
            rs_ok = rs_rank_60d >= 60
            rs_basis = f'rs_rank={rs_rank_60d:.0f}'
        else:
            _nrs = _n((rs_data or {}).get('rs_score')) or 50
            rs_ok = _nrs >= 60
            rs_basis = f'normalized_rs={_nrs:.0f}(proxy)'

        # 突破觸發
        _vp05 = False
        if vp and vp.get('available'):
            _vp05 = any(s.get('code') == 'VP05' for s in vp.get('signals', []))
        _bo20 = bool(tech.get('breakout_20'))
        _bo55 = bool(tech.get('breakout_55'))
        _squeeze_break = bool(tech.get('bb_squeeze')) and \
            (_n(tech.get('volume_zscore')) or 0) >= QuantConfig.VOLUME_ZSCORE_SPIKE
        short_trigger = _bo20 or _bo55 or _vp05 or _squeeze_break
        short_swing_ready = bool(short_trigger and rs_ok)

        # 趨勢波段：均線多頭結構 + 長均線上揚 + 距高近 + 距低夠遠
        if cur is not None and ma60 is not None and ma120 is not None:
            if ma240 is not None:
                ma_stack = cur > ma60 > ma120 > ma240
            else:
                ma_stack = cur > ma60 > ma120        # ma240 缺 → 三層判斷
        else:
            ma_stack = False
        position_trend_ready = bool(
            ma_stack
            and slope is not None and slope > 0
            and pth is not None and pth >= 0.75
            and dfl is not None and dfl >= 0.30
        )

        return {
            'short_swing_ready': short_swing_ready,
            'position_trend_ready': position_trend_ready,
            'short_trigger': short_trigger,
            'rs_basis': rs_basis,
        }

    @staticmethod
    def _calculate_support_resistance(hist, technical):
        """計算支撐壓力位與停損停利建議"""
        try:
            current_price = hist['Close'].iloc[-1]
            
            ma20 = technical.get('ma20')
            if not isinstance(ma20, (int, float)):
                ma20 = current_price * 0.95
            
            recent_low = hist['Low'].tail(20).min()
            support1 = max(ma20, recent_low)
            support2 = hist['Low'].tail(60).min()
            
            recent_high = hist['High'].tail(20).max()
            sma = hist['Close'].rolling(window=20).mean().iloc[-1]
            std = hist['Close'].rolling(window=20).std().iloc[-1]
            upper_band = sma + (2 * std)
            resistance1 = min(recent_high, upper_band)
            resistance2 = hist['High'].tail(60).max()
            
            stop_loss = support1 * 0.98
            take_profit = resistance1 * 0.98
            
            if current_price > stop_loss:
                risk_reward = (take_profit - current_price) / (current_price - stop_loss)
            else:
                risk_reward = 0
            
            return {
                "support1": round(support1, 2),
                "support2": round(support2, 2),
                "resistance1": round(resistance1, 2),
                "resistance2": round(resistance2, 2),
                "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2),
                "risk_reward": round(risk_reward, 2)
            }
        except:
            return {
                "support1": 0, "support2": 0,
                "resistance1": 0, "resistance2": 0,
                "stop_loss": 0, "take_profit": 0,
                "risk_reward": 0
            }
    
    @staticmethod
    def analyze_strategies_v4(hist, technical, fundamental, market_regime):
        """v4.0 改進：策略分析（考慮市場環境 + 穩定性評分）"""
        strategies = {}
        
        current_price = hist['Close'].iloc[-1]
        ma5 = hist['Close'].rolling(window=5).mean()
        ma20 = hist['Close'].rolling(window=20).mean()
        ma60 = hist['Close'].rolling(window=60).mean()
        
        # 1. 趨勢策略分析
        trend_strength = abs((ma5.iloc[-1] - ma20.iloc[-1]) / ma20.iloc[-1] * 100) if not pd.isna(ma5.iloc[-1]) and not pd.isna(ma20.iloc[-1]) else 0
        
        if current_price > ma5.iloc[-1]:
            short_term = "建議買進"
            short_reason = "價格站上短期均線"
        elif current_price < ma5.iloc[-1]:
            short_term = "建議賣出"
            short_reason = "價格跌破短期均線"
        else:
            short_term = "建議觀望"
            short_reason = "價格在均線附近"
        
        if ma5.iloc[-1] > ma20.iloc[-1]:
            mid_term = "建議買進"
            mid_reason = "黃金交叉，多頭排列"
        elif ma5.iloc[-1] < ma20.iloc[-1]:
            mid_term = "建議賣出"
            mid_reason = "死亡交叉，空頭排列"
        else:
            mid_term = "建議觀望"
            mid_reason = "均線糾結"
        
        if not pd.isna(ma60.iloc[-1]):
            if ma20.iloc[-1] > ma60.iloc[-1]:
                long_term = "建議買進"
                long_reason = "長期趨勢向上"
            elif ma20.iloc[-1] < ma60.iloc[-1]:
                long_term = "建議賣出"
                long_reason = "長期趨勢向下"
            else:
                long_term = "建議觀望"
                long_reason = "長期趨勢不明"
        else:
            long_term = "資料不足"
            long_reason = "需更多歷史資料"
        
        signal = "適合" if trend_strength > 2 else "不適合"
        
        strategies['趨勢策略'] = {
            'signal': signal,
            'strength': trend_strength,
            'reason': f"當前{'多頭' if ma5.iloc[-1] > ma20.iloc[-1] else '空頭'}排列",
            'execution': f"建議使用MA5/MA20交叉策略",
            'risk': "注意盤整時期的假突破" if trend_strength < 1 else "注意趨勢反轉訊號",
            'short_term': short_term, 'short_reason': short_reason,
            'mid_term': mid_term, 'mid_reason': mid_reason,
            'long_term': long_term, 'long_reason': long_reason
        }
        
        # 2. 動能策略分析
        rsi = technical['rsi']
        
        if rsi < 30:
            short_term = "建議買進"
            short_reason = "RSI超賣，可能反彈"
            momentum_signal = "適合"
        elif rsi > 70:
            short_term = "建議賣出"
            short_reason = "RSI超買，可能回檔"
            momentum_signal = "適合"
        else:
            short_term = "建議觀望"
            short_reason = f"RSI={rsi:.1f}，中性區域"
            momentum_signal = "不適合"
        
        if 40 < rsi < 60:
            mid_term = "建議觀望"
            mid_reason = "動能不足，等待極值"
        elif rsi < 40:
            mid_term = "建議逢低買進"
            mid_reason = "動能偏弱，可分批進場"
        else:
            mid_term = "建議逢高賣出"
            mid_reason = "動能偏強，可分批出場"
        
        strategies['動能策略'] = {
            'signal': momentum_signal,
            'strength': abs(rsi - 50),
            'reason': f"RSI={rsi:.1f}",
            'execution': f"建議在RSI極值時操作",
            'risk': "強勢股RSI可能長期超買",
            'short_term': short_term, 'short_reason': short_reason,
            'mid_term': mid_term, 'mid_reason': mid_reason,
            'long_term': "不適用", 'long_reason': "動能策略適合短中線操作"
        }
        
        # 3. 通道策略分析
        sma = hist['Close'].rolling(window=20).mean()
        std = hist['Close'].rolling(window=20).std()
        upper = sma + (2 * std)
        lower = sma - (2 * std)
        
        position_in_channel = (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]) if (upper.iloc[-1] - lower.iloc[-1]) > 0 else 0.5
        
        if position_in_channel > 0.8:
            short_term = "建議賣出"
            short_reason = "接近上軌，可能回檔"
            channel_signal = "適合"
        elif position_in_channel < 0.2:
            short_term = "建議買進"
            short_reason = "接近下軌，可能反彈"
            channel_signal = "適合"
        else:
            short_term = "建議觀望"
            short_reason = f"在通道{position_in_channel*100:.0f}%位置"
            channel_signal = "不適合"
        
        strategies['通道策略'] = {
            'signal': channel_signal,
            'strength': abs(position_in_channel - 0.5) * 100,
            'reason': f"價格在通道{position_in_channel*100:.0f}%位置",
            'execution': "上軌賣出，下軌買進",
            'risk': "突破通道後可能形成新趨勢",
            'short_term': short_term, 'short_reason': short_reason,
            'mid_term': "依短線訊號", 'mid_reason': "通道正常，依位置操作",
            'long_term': "不適用", 'long_reason': "通道策略適合短中線操作"
        }
        
        # 4. 均值回歸策略分析
        z_score = (current_price - sma.iloc[-1]) / std.iloc[-1] if std.iloc[-1] > 0 else 0
        
        if z_score > 2:
            short_term = "建議賣出"
            short_reason = f"Z={z_score:.2f}，遠高於均值"
            reversion_signal = "適合"
        elif z_score < -2:
            short_term = "建議買進"
            short_reason = f"Z={z_score:.2f}，遠低於均值"
            reversion_signal = "適合"
        else:
            short_term = "建議觀望"
            short_reason = f"Z={z_score:.2f}，接近均值"
            reversion_signal = "不適合"
        
        strategies['均值回歸策略'] = {
            'signal': reversion_signal,
            'strength': abs(z_score) * 50,
            'reason': f"Z-Score={z_score:.2f}",
            'execution': "偏離均值過大時反向操作",
            'risk': "趨勢市場中均值會不斷改變",
            'short_term': short_term, 'short_reason': short_reason,
            'mid_term': "建議等待回歸" if abs(z_score) > 1 else "建議觀望",
            'mid_reason': "偏離均值" if abs(z_score) > 1 else "接近均值",
            'long_term': "不適用", 'long_reason': "均值回歸適合短中線操作"
        }
        
        # v4.0 改進：執行回測並整合穩定性評分
        backtest_results = {}
        
        try:
            backtest_results['趨勢策略'] = BacktestEngine.backtest_trend_strategy(hist)
        except:
            backtest_results['趨勢策略'] = None
        
        try:
            backtest_results['動能策略'] = BacktestEngine.backtest_momentum_strategy(hist)
        except:
            backtest_results['動能策略'] = None
        
        try:
            backtest_results['通道策略'] = BacktestEngine.backtest_channel_strategy(hist)
        except:
            backtest_results['通道策略'] = None
        
        try:
            backtest_results['均值回歸策略'] = BacktestEngine.backtest_mean_reversion_strategy(hist)
        except:
            backtest_results['均值回歸策略'] = None
        
        # v4.0 改進：綜合評分（適用性 + 績效 + 穩定性 + 市場環境調整）
        strategy_total_scores = {}
        
        # 取得市場環境調整權重
        regime_adjustments = market_regime.get('strategy_adjustment', {}) if market_regime.get('available') else {}
        
        for strategy_name, strategy_info in strategies.items():
            # 適用性評分
            if strategy_info['signal'] == '適合':
                applicability_score = min(100, strategy_info['strength'])
            else:
                applicability_score = 0
            
            # 績效評分
            bt_result = backtest_results.get(strategy_name)
            if bt_result:
                backtest_return = bt_result['total_return']
                performance_score = min(100, max(0, (backtest_return + 50)))
                
                # v4.0 新增：穩定性評分（使用 Sharpe Ratio）
                sharpe = bt_result['sharpe_ratio']
                stability_score = min(100, max(0, sharpe * 30 + 50))  # Sharpe 1.5 = 95分
            else:
                performance_score = 50
                stability_score = 50
                backtest_return = 0
                sharpe = 0
            
            # v4.0 改進：綜合評分 = 適用性×0.3 + 績效×0.35 + 穩定性×0.35
            base_score = (
                applicability_score * QuantConfig.WEIGHT_APPLICABILITY +
                performance_score * QuantConfig.WEIGHT_PERFORMANCE +
                stability_score * QuantConfig.WEIGHT_STABILITY
            )
            
            # v4.0 新增：市場環境調整
            regime_weight = regime_adjustments.get(strategy_name, {}).get('weight', 1.0)
            adjusted_score = base_score * regime_weight
            
            strategy_total_scores[strategy_name] = {
                'total_score': adjusted_score,
                'base_score': base_score,
                'applicability_score': applicability_score,
                'performance_score': performance_score,
                'stability_score': stability_score,
                'backtest_return': backtest_return,
                'sharpe_ratio': sharpe,
                'regime_weight': regime_weight
            }
            
            # 更新策略資訊
            strategies[strategy_name]['backtest_return'] = f"{backtest_return:.2f}%"
            strategies[strategy_name]['sharpe_ratio'] = f"{sharpe:.2f}"
            strategies[strategy_name]['total_score'] = f"{adjusted_score:.1f}"
            strategies[strategy_name]['regime_adjustment'] = regime_adjustments.get(strategy_name, {}).get('recommendation', '')
        
        # 選擇最佳策略
        if strategy_total_scores:
            best_strategy = max(strategy_total_scores.keys(),
                              key=lambda x: strategy_total_scores[x]['total_score'])
            
            best_score_info = strategy_total_scores[best_strategy]
            
            if best_score_info['total_score'] < 30:
                best_strategy = "暫無特別適合的策略，建議觀望"
            else:
                # 附加說明
                best_strategy_detail = (
                    f"{best_strategy} "
                    f"(評分:{best_score_info['total_score']:.0f}, "
                    f"Sharpe:{best_score_info['sharpe_ratio']:.2f})"
                )
                best_strategy = best_strategy_detail
        else:
            best_strategy = "暫無特別適合的策略，建議觀望"
        
        return strategies, best_strategy
    
    @staticmethod
    def _generate_recommendation_v43(result, decision_matrix):
        """
        v4.3 新版本：基於多因子決策矩陣生成綜合建議
        v4.4.6 更新：整合形態分析評分 + 否決權 + 矛盾仲裁
        
        此函數整合決策矩陣結果、形態分析與傳統評分系統，產出一致性的投資建議。
        
        評分權重（v4.4.6 加權制）：
        - 形態學：40%（最高優先）
        - 波段策略：30%
        - 量價分析：20%
        - 輔助指標：10%
        
        新增機制：
        1. 絕對否決權：RSI > 85 或 乖離 > 20% 時強制限制評分上限
        2. 形態否決權：頭部形態確立時禁止做多
        3. 矛盾仲裁：形態與波段衝突時，以成交量裁決
        """
        # 傳統評分（用於輔助判斷）
        tech_signal = result["technical"]["signal"]
        fund_signal = result["fundamental"]["signal"]
        rsi = result["technical"]["rsi"]
        
        chip_signal = "中性"
        if "chip_flow" in result and result["chip_flow"]["available"]:
            chip_signal = result["chip_flow"]["signal"]
        
        # ============================================================
        # v4.4.6：新版加權評分系統
        # ============================================================
        
        # 1. 形態學分數（權重 40%）
        pattern_score = 50  # 基準分數
        pattern_info = None
        pattern_is_bearish = False  # 追蹤形態是否看空
        pattern_is_bullish = False  # 追蹤形態是否看多
        
        if result.get('pattern_analysis', {}).get('available'):
            pa = result['pattern_analysis']
            pattern_info = pa
            if pa.get('detected'):
                pattern_score += pa.get('score_impact', 0)
                pattern_score = max(0, min(100, pattern_score))
                
                # 標記形態方向
                pattern_status = pa.get('status', '')
                pattern_signal = pa.get('signal', 'neutral')
                if 'CONFIRMED' in pattern_status:
                    if pattern_signal == 'sell':
                        pattern_is_bearish = True
                    elif pattern_signal == 'buy':
                        pattern_is_bullish = True
        
        # 2. 波段策略分數（權重 30%）
        wave_score = 50
        wave_is_bullish = False
        wave_is_bearish = False
        
        wave = result.get('wave_analysis', {})
        if wave.get('available'):
            if wave.get('breakout_signal', {}).get('detected'):
                if wave.get('breakout_signal', {}).get('volume_confirmed'):
                    wave_score = 85
                else:
                    wave_score = 70
                wave_is_bullish = True
            elif wave.get('breakdown_signal', {}).get('detected'):
                wave_score = 20
                wave_is_bearish = True
            elif wave.get('is_bullish_env'):
                wave_score = 65
                wave_is_bullish = True
            elif wave.get('is_bearish_env'):
                wave_score = 35
                wave_is_bearish = True
        
        # 3. 量價分析分數（權重 20%）
        volume_score = 50
        volume_ratio = 1.0  # 用於矛盾仲裁
        
        vp = result.get('volume_price', {})
        if vp.get('available'):
            vp_score_raw = vp.get('vp_score', 0)
            volume_score = 50 + vp_score_raw / 2
            volume_score = max(0, min(100, volume_score))
        
        # 取得成交量比率（用於仲裁）
        vol_analysis = result.get('volume_analysis', {})
        if vol_analysis:
            volume_ratio = vol_analysis.get('volume_ratio', 1.0)
        
        # 4. 輔助指標分數（權重 10%）
        indicator_score = 50
        if tech_signal == "偏多":
            indicator_score = 70
        elif tech_signal == "偏空":
            indicator_score = 30
        if rsi > 70:
            indicator_score -= 15
        elif rsi < 30:
            indicator_score += 15
        
        # ============================================================
        # v4.4.6 新增：矛盾仲裁機制
        # ============================================================
        conflict_resolved = False
        conflict_message = ""
        
        # 情境 1：形態看空 (M頭/頭肩頂) 但波段看多
        if pattern_is_bearish and wave_is_bullish:
            if volume_ratio < 1.0:
                # 量縮：可能是假跌破，減輕形態扣分
                pattern_score = min(pattern_score + 20, 50)  # 把扣掉的分補回一些
                conflict_resolved = True
                conflict_message = "⚠️ 形態看空但量縮，判定可能為假跌破"
            else:
                # 帶量跌破：聽形態的，壓制波段分數
                wave_score = min(wave_score, 50)
                conflict_resolved = True
                conflict_message = "⚠️ 形態帶量跌破，以形態判斷為主"
        
        # 情境 2：形態看多 (W底) 但波段看空
        if pattern_is_bullish and wave_is_bearish:
            if volume_ratio >= 1.2:
                # 帶量突破：聽形態的，這是真突破
                wave_score = max(wave_score, 50)
                conflict_resolved = True
                conflict_message = "✓ 形態帶量突破，以形態判斷為主"
            else:
                # 量不足：突破可能失敗
                pattern_score = min(pattern_score, 60)
                conflict_resolved = True
                conflict_message = "⚠️ 形態突破但量能不足，突破可能失敗"
        
        # ============================================================
        # 計算加權總分
        # ============================================================
        weighted_score = (
            pattern_score * QuantConfig.WEIGHT_PATTERN +
            wave_score * QuantConfig.WEIGHT_WAVE +
            volume_score * QuantConfig.WEIGHT_VOLUME +
            indicator_score * QuantConfig.WEIGHT_INDICATOR
        )
        
        # ============================================================
        # v4.4.6 新增：絕對否決權 (Veto Rules)
        # ============================================================
        veto_applied = False
        veto_reason = ""
        score_cap = 100  # 評分上限（預設無限制）
        risk_notes = []  # A2 改動4：強勢股的過熱/形態風險改為提示，不壓分

        # 取得乖離率
        mr = result.get('mean_reversion', {})
        bias_20 = mr.get('bias_analysis', {}).get('bias_20', 0) if mr.get('available') else 0

        # A2 改動4：動能模式（RS 領先+多頭排列）由三層引擎判定，覆蓋層共用同一旗標。
        # 強勢領漲股的「過熱/頭部」一律降為風險提示，不把 overall 蓋成觀望/暫緩。
        _is_mom = bool(
            ((decision_matrix.get('three_layer', {}) or {}).get('position') or {}).get('is_momentum', False)
        ) if decision_matrix.get('available') else False

        # 否決權 1：RSI 極度過熱 (> 85)
        if rsi > 85:
            if _is_mom:
                risk_notes.append(f"RSI過熱（{rsi:.0f}），強勢股續抱、留意追高")
            else:
                score_cap = min(score_cap, 55)  # 鎖定評分上限，不會出現強力買進
                veto_applied = True
                veto_reason = f"RSI極度過熱（{rsi:.0f}），禁止追價"

        # 否決權 2：乖離率過大 (> 20%)
        if bias_20 > 20:
            if _is_mom:
                risk_notes.append(f"乖離率偏大（{bias_20:.1f}%），強勢延伸、留意追高")
            else:
                score_cap = min(score_cap, 50)
                veto_applied = True
                veto_reason = f"乖離率過大（{bias_20:.1f}%），禁止追價"

        # 否決權 3：形態頭部確立
        # 注意：頭部形態對強勢飆股易誤判（拉回常被當做頭），故動能模式下僅提示。
        if pattern_is_bearish:
            if _is_mom:
                risk_notes.append(
                    f"形態疑似頭部（{pattern_info.get('pattern_name', '')}），"
                    f"但 RS 領先+趨勢成立，僅供留意"
                )
            else:
                score_cap = min(score_cap, 45)  # 頭部確立時，最高只能觀望
                veto_applied = True
                if not veto_reason:
                    veto_reason = f"頭部形態確立（{pattern_info.get('pattern_name', '')}），禁止做多"
        
        # 應用評分上限
        weighted_score = min(weighted_score, score_cap)
        
        # 傳統分數（向後兼容）
        score = 0
        if tech_signal == "偏多":
            score += 30
        elif tech_signal == "中性":
            score += 15
        if fund_signal == "偏多":
            score += 30
        elif fund_signal == "中性":
            score += 15
        if chip_signal in ["籌碼集中", "籌碼偏多"]:
            score += 30
        elif chip_signal in ["籌碼中性", "中性", "籌碼穩定"]:
            score += 20
        
        # A2 改動4(b)：UI 分數與訊號同源。
        # 改用三層引擎綜合分（direction×0.35 + position×0.65，由 ThreeLayerEngine
        # 輸出於 decision_matrix['score']），解決「分數來源(形態40%)與最終文字
        # (三層引擎)是兩套、會不一致」的問題。形態退為資訊註記，不再當 score 主權重。
        # 加權分(weighted_score)/傳統分(score) 僅在三層引擎無輸出時作為 fallback。
        if decision_matrix.get('available') and isinstance(decision_matrix.get('score'), (int, float)):
            final_score = int(decision_matrix['score'])
        elif result.get('pattern_analysis', {}).get('available'):
            final_score = int(weighted_score)
        else:
            final_score = score

        # v4.4.3 新增：限制總分在 0-100 之間 (Clamp score)
        final_score = max(0, min(100, final_score))
        
        # 從決策矩陣獲取核心建議
        if decision_matrix.get('available'):
            dm = decision_matrix
            dv = dm.get('decision_vars', {})
            
            overall = dm.get('recommendation', '建議觀望')
            action_timing = dm.get('action_timing', '等待明確訊號')
            scenario = dm.get('scenario', 'X')
            scenario_name = dm.get('scenario_name', '待觀察')
            warning_message = dm.get('warning_message', '')
            confidence = dm.get('confidence', 'Medium')
            downgraded = dm.get('downgraded', False)
            filters_applied = dm.get('filters_applied', [])
            rr_ratio = dv.get('rr_ratio', 0)
            bias_20 = dv.get('bias_20', 0)
            
            # v5.0 / fix_07：形態分析覆蓋建議（裁決層級：賣出訊號＞大盤/籌碼濾網＞形態覆蓋）
            _overall_before = overall            # 記錄覆蓋前文字（供 adjustment_trail）
            _pat_override_blocked = None          # 被防線擋下的原因（供 trail）
            if pattern_info and pattern_info.get('detected'):
                pattern_status = pattern_info.get('status', '')
                pattern_signal = pattern_info.get('signal', 'neutral')
                pattern_name   = pattern_info.get('pattern_name', '')
                p_target       = pattern_info.get('target_price', 0) or 0
                p_stop         = pattern_info.get('stop_loss', 0) or 0
                current_px     = result.get('current_price', 0) or 0

                # ── 買進形態覆蓋：先過「前置否決」，再過三道防線 ──────
                if 'CONFIRMED' in pattern_status and pattern_signal == 'buy':

                    # 前置資料
                    _is_vshape = ('V型' in pattern_name or 'V形' in pattern_name)
                    try:
                        _vol_z = float(result.get('technical', {}).get('volume_zscore') or 0)
                    except (TypeError, ValueError):
                        _vol_z = 0.0
                    _pat_desc = pattern_info.get('description', '') or ''
                    _pending  = ('待確認' in pattern_status) or ('待確認' in _pat_desc)

                    # 防線 0（最優先，fix_07）：引擎裁決屬賣出族 → 買進覆蓋一律禁止
                    _sell_state = (
                        dm.get('scenario') in ('SELL', 'EXIT')
                        or str(dm.get('action_code', '')).upper().startswith('SELL')
                        or ((dm.get('three_layer') or {}).get('sell_signal') or {}).get('triggered', False)
                    )

                    if _sell_state:
                        # 不覆蓋，僅附註記（賣出訊號優先）
                        warning_message = (warning_message + f' ｜ 形態註記：偵測到{pattern_name}，'
                                           '但賣出訊號優先，不改變裁決').strip(' ｜')
                        _pat_override_blocked = f'偵測到{pattern_name}，賣訊優先，不改變裁決'
                    elif _is_vshape:
                        # fix_07：V 型反轉移出買進覆蓋白名單（回測期望 −3.74%），僅觀察註記
                        warning_message = (warning_message + f' ｜ 形態註記：偵測到{pattern_name}'
                                           '（V型反轉回測期望為負，僅供觀察，不改變裁決）').strip(' ｜')
                        _pat_override_blocked = f'偵測到{pattern_name}，V型不覆蓋，僅供觀察'
                    elif _pending:
                        # fix_07：量能待確認 → 不覆蓋
                        warning_message = (warning_message + f' ｜ 形態註記：{pattern_name}成立，'
                                           '待量能確認，不改變裁決').strip(' ｜')
                        _pat_override_blocked = f'{pattern_name}量能待確認，不覆蓋'
                    elif True:
                        # 防線 1（fix_07 修）：目標價高於現價；無目標價時需帶量（量能 Z≥1.0）
                        _target_valid = (p_target > current_px * 1.02) if p_target > 0 else (_vol_z >= 1.0)

                        # 防線 2：三層引擎的場景不能是 SKIP / WAIT（方向或位置否決）
                        _engine_ok = dm.get('scenario', '') not in ('SKIP', 'WAIT')

                        # 防線 3：乖離率不能過熱（> 15%）。動能模式不擋（正乖離=強度）。
                        _bias_ok = True if _is_mom else (abs(bias_20) <= 15)

                        if _target_valid and _engine_ok and _bias_ok:
                            # 全防線通過 → 允許形態覆蓋，輸出買進建議
                            overall = f'強烈建議買進（{pattern_name}確立）'
                            action_timing = '形態突破，可進場'
                            warning_message = (
                                pattern_info.get('description', '')
                                + (f' 目標價${p_target:.2f}，停損${p_stop:.2f}' if p_target > 0 else '')
                            )
                            confidence = 'High'
                        elif _is_mom:
                            # A2 改動4：強勢領漲股不蓋成「暫緩」。
                            # 保留三層引擎的 overall 裁決，形態問題只當風險註記附上。
                            _pat_notes = []
                            if not _target_valid:
                                _pat_notes.append(
                                    f'形態目標 ${p_target:.2f} 已被現價 ${current_px:.2f} 超越（測幅達成，僅供參考）'
                                )
                            if not _engine_ok:
                                _pat_notes.append(
                                    f'三層引擎場景：{dm.get("scenario_name", dm.get("scenario", ""))}'
                                )
                            if _pat_notes:
                                warning_message = (warning_message + ' ｜ 形態註記：'
                                                   + '；'.join(_pat_notes)).strip(' ｜')
                            _pat_override_blocked = '動能股防線未過，保留引擎裁決'
                        else:
                            # 非強勢股：任一防線失守 → 降為觀察，附上原因
                            _block_reasons = []
                            if not _target_valid:
                                _block_reasons.append(
                                    f'目標價 ${p_target:.2f} 已低於現價 ${current_px:.2f}（形態目標已達成，追高風險大）'
                                )
                            if not _engine_ok:
                                _block_reasons.append(
                                    f'三層引擎否決（場景：{dm.get("scenario_name", dm.get("scenario", ""))}）'
                                )
                            if not _bias_ok:
                                _block_reasons.append(
                                    f'乖離率過大（{bias_20:+.1f}%），追高風險高'
                                )
                            overall = f'形態確立但暫緩買進（{pattern_name}）'
                            action_timing = '等待拉回或乖離收斂後再進場'
                            warning_message = (
                                pattern_info.get('description', '')
                                + ' ⚠️ 覆蓋條件未達：' + '；'.join(_block_reasons)
                            )
                            confidence = 'Medium'

                # ── 賣出形態覆蓋（無需防線，頭部形態確立直接賣）──────
                elif 'CONFIRMED' in pattern_status and pattern_signal == 'sell':
                    overall = f'建議賣出（{pattern_name}確立）'
                    action_timing = '形態跌破，應出場'
                    warning_message = (
                        pattern_info.get('description', '')
                        + (f' 目標價${p_target:.2f}' if p_target > 0 else '')
                    )
                    confidence = 'High'

                # ── TARGET_REACHED 狀態：形態已完成，不再建議買進 ─────
                elif pattern_status == 'TARGET_REACHED':
                    # 不覆蓋 overall，保留三層引擎的裁決
                    # 只補充說明
                    warning_message = pattern_info.get('description', warning_message)
            
            # 生成分段操作建議
            # 修正：改傳 action_code（與上方三層引擎裁決同源），避免 scenario
            # 代碼撞號（三層引擎 'A'=A級主攻，舊字典 'A'=多頭過熱，意思相反）。
            _action_code = dm.get('action_code', '')
            short_term = QuickAnalyzer._get_short_term_from_scenario(scenario, dv, result, _action_code)
            mid_term = QuickAnalyzer._get_mid_term_from_scenario(scenario, dv, result, _action_code)
            long_term = QuickAnalyzer._get_long_term_recommendation(result, final_score)
            
            # 構建基本建議結果
            recommendation_result = {
                "overall": overall,
                "score": final_score,
                "action_timing": action_timing,
                "scenario": scenario,
                "scenario_name": scenario_name,
                "warning_message": warning_message,
                "confidence": confidence,
                "downgraded": downgraded,
                "filters_applied": filters_applied,
                "original_recommendation": decision_matrix.get('original_recommendation', overall),
                "rr_ratio": rr_ratio,
                "bias_20": bias_20,
                "short_term": short_term,
                "mid_term": mid_term,
                "long_term": long_term,
                # v4.4.6 新增：分項分數
                "score_breakdown": {
                    "pattern_score": pattern_score,
                    "wave_score": wave_score,
                    "volume_score": volume_score,
                    "indicator_score": indicator_score,
                    "weighted_score": round(weighted_score, 1),
                    "score_cap": score_cap  # 評分上限
                },
                # v4.4.6 新增：否決權與矛盾仲裁資訊
                "veto_info": {
                    "veto_applied": veto_applied,
                    "veto_reason": veto_reason,
                    "conflict_resolved": conflict_resolved,
                    "conflict_message": conflict_message
                }
            }
            
            # 如果有否決權觸發，在警告訊息中加入
            if veto_applied and veto_reason:
                if warning_message:
                    recommendation_result["warning_message"] = f"🛑 {veto_reason} | {warning_message}"
                else:
                    recommendation_result["warning_message"] = f"🛑 {veto_reason}"
            
            # 資料異常：漲跌幅超過漲跌停 → 最高優先警示（整份分析可能不可信）
            if result.get('price_anomaly'):
                _pa = (f"🛑 資料異常：漲跌幅 {result.get('price_change_pct', 0):+.1f}% 超過±10%漲跌停，"
                       f"即時價與昨收可能未對齊，本檔分析請勿採信")
                _ew = recommendation_result.get("warning_message", "")
                recommendation_result["warning_message"] = f"{_pa} | {_ew}" if _ew else _pa

            # A2 改動4：強勢股的過熱/形態風險提示（不壓分，純資訊）併入警示
            if risk_notes:
                existing_warning = recommendation_result.get("warning_message", "")
                _rn = '⚠️ 風險提示：' + '；'.join(risk_notes)
                recommendation_result["warning_message"] = (
                    f"{existing_warning} | {_rn}" if existing_warning else _rn
                )

            # 如果有矛盾被仲裁，也加入
            if conflict_resolved and conflict_message:
                existing_warning = recommendation_result.get("warning_message", "")
                if existing_warning:
                    recommendation_result["warning_message"] = f"{existing_warning} | {conflict_message}"
                else:
                    recommendation_result["warning_message"] = conflict_message
            
            # v4.4.6 新增：形態資訊
            if pattern_info and pattern_info.get('detected'):
                recommendation_result['pattern_info'] = {
                    'pattern_name': pattern_info.get('pattern_name'),
                    'status': pattern_info.get('status'),
                    'neckline_price': pattern_info.get('neckline_price'),
                    'target_price': pattern_info.get('target_price'),
                    'stop_loss': pattern_info.get('stop_loss'),
                    'signal': pattern_info.get('signal'),
                    'volume_confirmed': pattern_info.get('volume_confirmed', False)
                }
            
            # v4.4.7 新增：解釋原因和目標價
            explanation = dm.get('explanation', '')
            if explanation:
                recommendation_result['explanation'] = explanation
            
            price_targets = dm.get('price_targets', {})
            if price_targets and price_targets.get('available'):
                recommendation_result['price_targets'] = price_targets
            
            # 修正：場景 E 或 F（區間操作），加入 range_info
            range_info = dm.get('range_info', {})
            if range_info and scenario in ['E', 'F']:
                recommendation_result['range_info'] = range_info

            # fix_07：回填「形態覆蓋」裁決軌跡（文字層變化 from/to；被擋則 to=None）
            try:
                _trail = decision_matrix.get('adjustment_trail')
                if _trail:
                    _ob = _overall_before
                    for _e in _trail:
                        if _e.get('stage') != '形態覆蓋':
                            continue
                        if overall and overall != _ob:
                            # 覆蓋成功：記錄文字層變化
                            _e['from'] = _ob
                            _e['to'] = overall
                            _e['reason'] = '形態確立 → 建議覆蓋'
                        elif _pat_override_blocked:
                            # 被防線擋下：to=None，記錄原因（修掉無意義的 SELL→SELL）
                            _e['from'] = None
                            _e['to'] = None
                            _e['reason'] = _pat_override_blocked
                        break
            except Exception:
                pass

            return recommendation_result
        else:
            # 決策矩陣不可用時，使用傳統邏輯
            return QuickAnalyzer._generate_recommendation(result)
    
    @staticmethod
    def _get_short_term_from_scenario(scenario, decision_vars, result, action_code=''):
        """根據三層引擎的 action_code 生成短線建議（與上方裁決同源）。

        修正：原本依 scenario 查舊字典，但三層引擎的 scenario 代碼（'A'=A級主攻）
        與舊字典（'A'=多頭過熱）撞號，導致「A級主攻」卻顯示「暫停加碼」的自相矛盾。
        改以 action_code 為主。
        """
        bias_20 = decision_vars.get('bias_20', 0)
        rsi = decision_vars.get('rsi', 50)
        rr_ratio = decision_vars.get('rr_ratio', 0)

        # 與三層引擎裁決同源（action_code 明確、不撞號）
        _ac_map = {
            'STRONG_BUY': {'action': '積極進場（A級主攻）',
                           'reason': '方向+位置+時機三者到位，順勢操作'},
            'BUY':        {'action': '可進場、分批佈局（B級追蹤）',
                           'reason': '訊號成形，等量能/拉回確認可加碼'},
            'HOLD':       {'action': '持股續抱、暫不加碼',
                           'reason': '已有部位者續抱，空手者等更好位置'},
            'WAIT':       {'action': '等待拉回再進場',
                           'reason': '方向偏多但位置偏高，等乖離收斂'},
            'SKIP':       {'action': '不參與',
                           'reason': '趨勢/方向不利，避開'},
            'SELL':       {'action': '賣出 / 出場',
                           'reason': '觸發賣出訊號'},
            'TAKE_PROFIT': {'action': '分批停利',
                            'reason': '高檔過熱，獲利了結'},
        }
        if action_code in _ac_map:
            return _ac_map[action_code]

        # 場景 E 或 F 特殊處理：加入區間詳細資訊
        if scenario in ['E', 'F']:
            # 嘗試從支撐壓力位取得箱頂箱底
            sr = result.get('support_resistance', {})
            current_price = result.get('current_price', 0)
            
            box_top = sr.get('resistance1', 0)
            box_bottom = sr.get('support1', 0)
            
            # 如果有有效的箱頂箱底，計算位置並給出具體建議
            if box_top > 0 and box_bottom > 0 and box_top > box_bottom:
                range_width = box_top - box_bottom
                position_pct = ((current_price - box_bottom) / range_width) * 100 if range_width > 0 else 50
                
                if position_pct <= 30:
                    action = '區間操作：接近箱底，適合買進'
                    reason = f'箱底${box_bottom:.1f}↔箱頂${box_top:.1f}，目前靠近箱底'
                elif position_pct >= 70:
                    action = '區間操作：接近箱頂，適合賣出'
                    reason = f'箱底${box_bottom:.1f}↔箱頂${box_top:.1f}，目前靠近箱頂'
                else:
                    action = '區間操作：觀望為主'
                    reason = f'箱底${box_bottom:.1f}↔箱頂${box_top:.1f}，區間中段'
                
                return {'action': action, 'reason': reason}
            else:
                return {'action': '區間操作', 'reason': '箱底買、箱頂賣'}
        
        scenario_short_term = {
            'A': {  # 多頭過熱
                'action': '暫停加碼，持股續抱',
                'reason': f'乖離{bias_20:+.1f}%過熱，等拉回再加碼'
            },
            'B': {  # 黃金買點
                'action': '強烈建議買進',
                'reason': f'拉回甜蜜點，盈虧比{rr_ratio:.1f}'
            },
            'B2': {  # 多頭正常
                'action': '可買進',
                'reason': '趨勢向上，順勢操作'
            },
            'C': {  # 空頭超賣
                'action': '勿殺低，可搶反彈',
                'reason': f'乖離{bias_20:+.1f}%超跌，逆勢高風險'
            },
            'D': {  # 空頭確認
                'action': '建議賣出',
                'reason': '空頭趨勢，反彈即出場'
            },
            'X': {  # 待觀察
                'action': '觀望',
                'reason': '等待明確訊號'
            }
        }
        
        return scenario_short_term.get(scenario, {'action': '觀望', 'reason': '無明確訊號'})
    
    @staticmethod
    def _get_mid_term_from_scenario(scenario, decision_vars, result, action_code=''):
        """根據三層引擎 action_code 生成中線建議（與上方裁決同源）。"""
        trend = decision_vars.get('trend_status', 'Range')

        _ac_map = {
            'STRONG_BUY': {'action': '偏多持有', 'reason': '多頭趨勢成立，持股續抱'},
            'BUY':        {'action': '偏多持有', 'reason': '趨勢向上，順勢操作'},
            'HOLD':       {'action': '中線持有 / 觀望', 'reason': '維持部位，留意趨勢變化'},
            'WAIT':       {'action': '中線偏多、等位置', 'reason': '趨勢偏多但等更好進場點'},
            'SKIP':       {'action': '避開', 'reason': '趨勢偏弱，不宜中線佈局'},
            'SELL':       {'action': '減碼 / 出場', 'reason': '趨勢轉弱或觸發賣訊'},
            'TAKE_PROFIT': {'action': '逢高減碼', 'reason': '高檔過熱，分批了結'},
        }
        if action_code in _ac_map:
            return _ac_map[action_code]

        # 舊場景碼相容（三層引擎不產生 E/F，保留以防其他呼叫路徑）
        if scenario == 'E':
            return {'action': '區間操作', 'reason': '盤整格局，高拋低吸'}

        return {'action': '中線觀望', 'reason': '等待趨勢明確'}
    
    @staticmethod
    def _generate_recommendation(result):
        """生成綜合推薦 - v4.1 整合波段分析，消除建議矛盾"""
        tech_signal = result["technical"]["signal"]
        fund_signal = result["fundamental"]["signal"]
        rsi = result["technical"]["rsi"]
        
        chip_signal = "中性"
        if "chip_flow" in result and result["chip_flow"]["available"]:
            chip_signal = result["chip_flow"]["signal"]
        
        # v4.1 新增：取得波段分析結果
        wave = result.get("wave_analysis", {})
        wave_status = wave.get("wave_status", "") if wave.get("available") else ""
        wave_action = wave.get("action_advice", "") if wave.get("available") else ""
        breakout_detected = wave.get("breakout_signal", {}).get("detected", False)
        breakdown_detected = wave.get("breakdown_signal", {}).get("detected", False)
        
        # v4.2 新增：取得均值回歸分析結果
        mr = result.get("mean_reversion", {})
        left_buy_triggered = mr.get("left_buy_signal", {}).get("triggered", False) if mr.get("available") else False
        left_sell_triggered = mr.get("left_sell_signal", {}).get("triggered", False) if mr.get("available") else False
        bias_20 = mr.get("bias_analysis", {}).get("bias_20", 0) if mr.get("available") else 0
        is_overbought = mr.get("bias_analysis", {}).get("is_overbought", False) if mr.get("available") else False
        is_oversold = mr.get("bias_analysis", {}).get("is_oversold", False) if mr.get("available") else False
        
        # 計算綜合評分
        score = 0
        
        # 技術面評分（30%）
        if tech_signal == "偏多":
            score += 30
        elif tech_signal == "中性":
            score += 15
        
        # 基本面評分（30%）
        if fund_signal == "偏多":
            score += 30
        elif fund_signal == "中性":
            score += 15
        
        # 籌碼面評分（40%）
        if chip_signal == "籌碼集中":
            score += 40
        elif chip_signal == "籌碼偏多":
            score += 30
        elif chip_signal in ["籌碼中性", "中性", "籌碼穩定"]:
            score += 20
        elif chip_signal == "籌碼偏空":
            score += 10
        
        # v4.0 新增：成交量異常調整
        volume_analysis = result.get("volume_analysis", {})
        if volume_analysis.get("spike_detected"):
            if volume_analysis.get("spike_action") == "偏多":
                score += 5
            elif volume_analysis.get("spike_action") == "偏空":
                score -= 5
        
        # v4.0 新增：市場環境調整
        market_regime = result.get("market_regime", {})
        if market_regime.get("available"):
            if market_regime.get("trend_direction") == "空頭":
                score -= 10
            elif market_regime.get("trend_direction") == "多頭":
                score += 5
        
        # RSI 調整
        if rsi > 80:
            score -= 10
        elif rsi < 20:
            score += 10
        
        # v4.1 新增：波段分析調整評分
        if breakdown_detected:
            score -= 15  # 三盤跌破，大幅扣分
        
        # v4.2 新增：均值回歸調整評分
        if left_sell_triggered and is_overbought:
            score -= 10  # 嚴重過熱，扣分
        if left_buy_triggered and is_oversold:
            score += 5  # 超跌可能反彈，小幅加分（但風險仍高）
        
        # v4.4.3 新增：限制總分在 0-100 之間 (Clamp score)
        score = max(0, min(100, score))
        
        # ============================================================
        # v4.2 修正：生成一致性的總體建議（整合波段分析 + 均值回歸）
        # ============================================================
        
        # 判斷當前是否適合立即進場
        immediate_entry_ok = True
        wait_reason = ""
        
        # 條件1：RSI 超買需要等待
        if rsi > 70:
            immediate_entry_ok = False
            wait_reason = f"RSI={rsi:.0f}超買"
        
        # 條件2：波段分析建議等拉回
        if "等" in wave_action and ("拉回" in wave_action or "縮量" in wave_action):
            immediate_entry_ok = False
            if wait_reason:
                wait_reason += "，且波段建議等拉回"
            else:
                wait_reason = "波段建議等拉回確認"
        
        # 條件3：三盤跌破
        if breakdown_detected:
            immediate_entry_ok = False
            wait_reason = "三盤跌破，波段結束"
        
        # 條件4 (v4.2新增)：嚴重正乖離
        if is_overbought:
            immediate_entry_ok = False
            if wait_reason:
                wait_reason += f"，乖離率{bias_20:.1f}%過熱"
            else:
                wait_reason = f"乖離率{bias_20:.1f}%嚴重過熱"
        
        # 生成總體建議（考慮是否適合立即進場 + 均值回歸訊號）
        if breakdown_detected:
            # 三盤跌破優先
            overall = "建議出場觀望"
            action_timing = "立即"
        elif left_sell_triggered and is_overbought:
            # v4.2：嚴重過熱，觸發左側賣訊
            overall = "建議積極停利"
            action_timing = "短線過熱，鎖住獲利"
        elif left_buy_triggered and is_oversold:
            # v4.2：嚴重超跌，觸發左側買訊（逆勢操作，高風險）
            if score >= 40:
                overall = "可嘗試搶反彈（高風險）"
                action_timing = "超跌反彈機會，但屬逆勢操作"
            else:
                overall = "超跌但趨勢向下，觀望"
                action_timing = "等止跌訊號確認"
        elif score >= 70:
            if immediate_entry_ok:
                overall = "強烈建議買進"
                action_timing = "可立即進場"
            else:
                overall = "看好，但等拉回再買"
                action_timing = f"等待（{wait_reason}）"
        elif score >= 50:
            if immediate_entry_ok:
                overall = "建議買進"
                action_timing = "可考慮進場"
            else:
                overall = "偏多，等回檔佈局"
                action_timing = f"等待（{wait_reason}）"
        elif score >= 35:
            overall = "建議觀望"
            action_timing = "暫不操作"
        elif score >= 20:
            overall = "建議減碼"
            action_timing = "逢高減碼"
        else:
            overall = "建議賣出"
            action_timing = "儘速離場"
        
        # v4.2 修正：短線建議與總體建議保持一致（加入均值回歸）
        short_term = QuickAnalyzer._get_short_term_recommendation_v42(result, score, wave, mr, immediate_entry_ok, wait_reason)
        mid_term = QuickAnalyzer._get_mid_term_recommendation(result, score)
        long_term = QuickAnalyzer._get_long_term_recommendation(result, score)
        
        return {
            "overall": overall,
            "score": score,
            "action_timing": action_timing,  # v4.1 新增：進場時機說明
            "short_term": short_term,
            "mid_term": mid_term,
            "long_term": long_term
        }
    
    @staticmethod
    def _get_short_term_recommendation_v42(result, score, wave, mr, immediate_entry_ok, wait_reason):
        """v4.2 修正：短線建議整合波段分析 + 均值回歸"""
        rsi = result["technical"]["rsi"]
        chip = result.get("chip_flow", {})
        volume = result.get("volume_analysis", {})
        
        breakdown_detected = wave.get("breakdown_signal", {}).get("detected", False) if wave.get("available") else False
        breakout_detected = wave.get("breakout_signal", {}).get("detected", False) if wave.get("available") else False
        
        # v4.2：取得均值回歸訊號
        left_buy_triggered = mr.get("left_buy_signal", {}).get("triggered", False) if mr.get("available") else False
        left_sell_triggered = mr.get("left_sell_signal", {}).get("triggered", False) if mr.get("available") else False
        is_overbought = mr.get("bias_analysis", {}).get("is_overbought", False) if mr.get("available") else False
        is_oversold = mr.get("bias_analysis", {}).get("is_oversold", False) if mr.get("available") else False
        bias_20 = mr.get("bias_analysis", {}).get("bias_20", 0) if mr.get("available") else 0
        
        # 優先級1：三盤跌破 - 必須出場
        if breakdown_detected:
            return {"action": "建議出場", "reason": "三盤跌破，波段結束"}
        
        # 優先級2 (v4.2新增)：左側賣出訊號 - 積極停利
        if left_sell_triggered and is_overbought:
            return {"action": "建議積極停利", "reason": f"乖離{bias_20:.1f}%過熱，觸發左側賣訊"}
        
        # 優先級3 (v4.2新增)：左側買進訊號 - 超跌反彈
        if left_buy_triggered and is_oversold:
            return {"action": "可嘗試搶反彈（高風險）", "reason": f"乖離{bias_20:.1f}%超跌，屬逆勢操作"}
        
        # 優先級4：三盤突破但需等拉回
        if breakout_detected and not immediate_entry_ok:
            return {"action": "等拉回再進場", "reason": wait_reason}
        
        # 優先級5：三盤突破且可立即進場
        if breakout_detected and immediate_entry_ok:
            strength = wave.get("breakout_signal", {}).get("strength", "")
            if strength == "strong":
                return {"action": "可進場", "reason": "三盤突破（強勢）"}
            else:
                return {"action": "可小量試單", "reason": "三盤突破，等拉回加碼"}
        
        # 優先級6：乖離偏高但未觸發左側賣訊
        if bias_20 > 10:
            return {"action": "短線過熱，不宜追高", "reason": f"乖離{bias_20:.1f}%偏高"}
        
        # 優先級7：爆量判斷
        if volume.get("spike_detected"):
            if volume.get("spike_action") == "偏多":
                return {"action": "爆量買進訊號", "reason": volume.get("spike_signal", "")}
            elif volume.get("spike_action") == "偏空":
                return {"action": "爆量賣出訊號", "reason": volume.get("spike_signal", "")}
        
        # 優先級8：籌碼面（v4.4.1 修正：改用數值驅動，不用中文句子比對）
        if chip.get("available"):
            # 取得數值欄位
            foreign_net = chip.get("foreign_net", 0)
            trust_net = chip.get("trust_net", 0)
            foreign_days = chip.get("foreign_consecutive_days", 0)
            trust_days = chip.get("trust_consecutive_days", 0)
            
            # 同步買超信號：外資投信都買超且連續天數>=2
            is_sync_buy = (foreign_net > 0 and trust_net > 0 and 
                          foreign_days >= 2 and trust_days >= 2)
            # 同步賣超信號：外資投信都賣超且連續天數>=2
            is_sync_sell = (foreign_net < 0 and trust_net < 0 and 
                           abs(foreign_days) >= 2 and abs(trust_days) >= 2)
            
            if is_sync_buy:
                if immediate_entry_ok:
                    return {"action": "建議買進", "reason": f"外資投信同步連續買超（外資連{foreign_days}日，投信連{trust_days}日）"}
                else:
                    return {"action": "等拉回買進", "reason": f"籌碼面佳但{wait_reason}"}
            elif is_sync_sell:
                return {"action": "建議賣出", "reason": f"外資投信同步連續賣超（外資連{abs(foreign_days)}日，投信連{abs(trust_days)}日）"}
        
        # 優先級9：RSI 判斷
        if rsi < 30:
            return {"action": "可考慮買進", "reason": f"RSI={rsi:.0f}超賣區"}
        elif rsi > 70:
            return {"action": "短線過熱，等拉回", "reason": f"RSI={rsi:.0f}超買區"}
        
        # 優先級10：綜合評分
        if score >= 60:
            if immediate_entry_ok:
                return {"action": "短線偏多", "reason": "技術面籌碼面配合良好"}
            else:
                return {"action": "看好但等拉回", "reason": wait_reason}
        elif score <= 30:
            return {"action": "短線偏空", "reason": "技術面籌碼面偏弱"}
        else:
            return {"action": "短線觀望", "reason": "方向不明確"}
    
    @staticmethod
    def _get_mid_term_recommendation(result, score):
        """中線建議"""
        tech = result["technical"]
        chip = result.get("chip_flow", {})
        
        if tech.get("trend") == "上升趨勢":
            if chip.get("signal") in ["籌碼集中", "籌碼偏多"]:
                return {"action": "建議持有", "reason": "趨勢向上且籌碼面支撐"}
            else:
                return {"action": "持有觀察", "reason": "趨勢向上但籌碼面未配合"}
        elif tech.get("trend") == "下降趨勢":
            if chip.get("signal") in ["籌碼分散", "籌碼偏空"]:
                return {"action": "建議減碼", "reason": "趨勢向下且籌碼流出"}
            else:
                return {"action": "觀察反彈", "reason": "趨勢向下但可能有反彈"}
        
        return {"action": "中線觀望", "reason": "等待明確訊號"}
    
    @staticmethod
    def _get_long_term_recommendation(result, score):
        """
        長線建議
        v4.4.2 修正：當 PE 為負值時，改用其他指標判斷
        """
        fund = result["fundamental"]
        
        # v4.0 改進：使用 PE Band 和 Forward PE
        pe_percentile = fund.get("pe_percentile", "N/A")
        forward_pe = fund.get("forward_pe", "N/A")
        trailing_pe = fund.get("trailing_pe", "N/A")
        pb = fund.get("pb", "N/A")
        
        # v4.4.2 修正：檢查 PE 是否為負值（公司虧損）
        pe_is_negative = False
        if forward_pe not in ["N/A", "歷史模式不可用", None] and isinstance(forward_pe, (int, float)):
            if forward_pe < 0:
                pe_is_negative = True
        
        # 如果沒有 Forward PE，檢查 Trailing PE
        if not pe_is_negative and trailing_pe not in ["N/A", None] and isinstance(trailing_pe, (int, float)):
            if trailing_pe < 0:
                pe_is_negative = True
        
        # ============================================================
        # PE 為負值時的處理邏輯（公司虧損）
        # ============================================================
        if pe_is_negative:
            # 嘗試使用 PB（股價淨值比）判斷
            if pb not in ["N/A", None] and isinstance(pb, (int, float)) and pb > 0:
                if pb < 1.0:
                    return {
                        "action": "長線觀察", 
                        "reason": f"公司虧損(PE<0)，但PB={pb:.2f}<1（股價低於淨值），可關注轉機"
                    }
                elif pb < 2.0:
                    return {
                        "action": "長線謹慎", 
                        "reason": f"公司虧損(PE<0)，PB={pb:.2f}，需觀察獲利改善"
                    }
                else:
                    return {
                        "action": "長線避開", 
                        "reason": f"公司虧損(PE<0)且PB={pb:.2f}偏高，估值風險大"
                    }
            
            # 沒有 PB 資料，使用技術面和籌碼面判斷
            chip_signal = "中性"
            if "chip_flow" in result and result["chip_flow"].get("available"):
                chip_signal = result["chip_flow"].get("signal", "中性")
            
            tech_signal = result.get("technical", {}).get("signal", "中性")
            
            # 技術面和籌碼面都偏多，可能有轉機題材
            if tech_signal == "偏多" and chip_signal in ["籌碼集中", "籌碼偏多"]:
                return {
                    "action": "長線觀察", 
                    "reason": "公司虧損(PE<0)，但技術面+籌碼面偏多，可能有轉機題材"
                }
            elif tech_signal == "偏空" or chip_signal in ["籌碼分散", "籌碼偏空"]:
                return {
                    "action": "長線避開", 
                    "reason": "公司虧損(PE<0)，技術面或籌碼面偏空，風險較高"
                }
            else:
                return {
                    "action": "長線謹慎", 
                    "reason": "公司虧損(PE<0)，長線價值需觀察獲利改善"
                }
        
        # ============================================================
        # 正常 PE 判斷邏輯
        # ============================================================
        # 確保 forward_pe 是正數才進行比較
        if forward_pe not in ["N/A", "歷史模式不可用", None] and isinstance(forward_pe, (int, float)):
            if forward_pe > 0:  # v4.4.2 修正：必須是正數
                if forward_pe < 12:
                    return {"action": "長線看好", "reason": f"預估PE={forward_pe:.1f}偏低，具投資價值"}
                elif forward_pe > 25:
                    return {"action": "長線謹慎", "reason": f"預估PE={forward_pe:.1f}偏高，留意風險"}
        
        # 確保 pe_percentile 是數字才進行比較
        if pe_percentile not in ["N/A", None] and isinstance(pe_percentile, (int, float)):
            if pe_percentile < 20:
                return {"action": "長線看好", "reason": f"PE處於歷史{pe_percentile:.0f}%低檔"}
            elif pe_percentile > 80:
                return {"action": "長線謹慎", "reason": f"PE處於歷史{pe_percentile:.0f}%高檔"}
        
        if score >= 60:
            return {"action": "長線持有", "reason": "整體面向正面"}
        elif score <= 30:
            return {"action": "長線觀望", "reason": "整體面向偏弱"}
        else:
            return {"action": "長線中性", "reason": "維持現有部位"}


# ============================================================================
# v4.0 新增：相關性分析器
# ============================================================================


# ============================================================================
# v4.0 改進：回測結果彈窗（含淨值曲線）
# ============================================================================

class BacktestDialog:
    """回測結果彈窗 v4.0 - 增加淨值曲線圖"""
    
    def __init__(self, parent, symbol, strategy_name, results):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"📊 {symbol} - {strategy_name} 回測結果")
        self.dialog.geometry("900x750")
        
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(
            main_frame,
            text=f"📈 {symbol} - {strategy_name}",
            font=("Arial", 18, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        if results is None:
            ttk.Label(main_frame, text="回測失敗或資料不足", font=("Arial", 12)).pack()
            return
        
        # 上半部：績效指標
        metrics_frame = ttk.LabelFrame(main_frame, text="績效指標", padding=15)
        metrics_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 分兩列顯示指標
        left_frame = ttk.Frame(metrics_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        right_frame = ttk.Frame(metrics_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        left_metrics = [
            ("總報酬率", f"{results['total_return']:.2f}%", 
             "green" if results['total_return'] > 0 else "red"),
            ("年化報酬率", f"{results['annual_return']:.2f}%",
             "green" if results['annual_return'] > 0 else "red"),
            ("買入持有報酬", f"{results['buy_hold_return']:.2f}%", "blue"),
            ("最大回撤", f"{results['max_drawdown']:.2f}%",
             "red" if results['max_drawdown'] < -10 else "orange"),
        ]
        
        right_metrics = [
            ("Sharpe Ratio", f"{results['sharpe_ratio']:.2f}",
             "green" if results['sharpe_ratio'] > 1 else "orange" if results['sharpe_ratio'] > 0 else "red"),
            ("Sortino Ratio", f"{results['sortino_ratio']:.2f}",
             "green" if results['sortino_ratio'] > 1 else "orange"),
            ("勝率", f"{results['win_rate']:.2f}%",
             "green" if results['win_rate'] > 50 else "orange"),
            ("無風險利率", f"{results['risk_free_rate']:.2f}%", "gray"),
        ]
        
        for label, value, color in left_metrics:
            row = ttk.Frame(left_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}：", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("Arial", 10), foreground=color).pack(side=tk.LEFT)
        
        for label, value, color in right_metrics:
            row = ttk.Frame(right_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}：", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("Arial", 10), foreground=color).pack(side=tk.LEFT)
        
        # v4.0 新增：淨值曲線圖
        chart_frame = ttk.LabelFrame(main_frame, text="淨值曲線 (Equity Curve)", padding=10)
        chart_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self._plot_equity_curve(chart_frame, results)
        
        # 結論
        conclusion_frame = ttk.LabelFrame(main_frame, text="結論", padding=10)
        conclusion_frame.pack(fill=tk.X, pady=(0, 10))
        
        conclusion = self._generate_conclusion(results)
        ttk.Label(conclusion_frame, text=conclusion, font=("Arial", 10), wraplength=800).pack()
        
        # 按鈕
        ttk.Button(main_frame, text="關閉", command=self.dialog.destroy, width=15).pack()
    
    def _plot_equity_curve(self, parent, results):
        """繪製淨值曲線"""
        try:
            fig = Figure(figsize=(8, 3), dpi=100)
            ax = fig.add_subplot(111)
            
            equity_curve = results.get('equity_curve', [])
            equity_dates = results.get('equity_dates', [])
            
            if equity_curve and len(equity_curve) > 1:
                # 簡化日期顯示
                x = range(len(equity_curve))
                ax.plot(x, equity_curve, 'b-', linewidth=1.5, label='策略淨值')
                ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='起始值')
                
                # 填充獲利區域
                ax.fill_between(x, 1.0, equity_curve, 
                               where=[e >= 1.0 for e in equity_curve],
                               alpha=0.3, color='green')
                ax.fill_between(x, 1.0, equity_curve,
                               where=[e < 1.0 for e in equity_curve],
                               alpha=0.3, color='red')
                
                ax.set_title('策略淨值曲線', fontproperties=zh_font, fontsize=11)
                ax.set_xlabel('交易日', fontproperties=zh_font, fontsize=9)
                ax.set_ylabel('淨值', fontproperties=zh_font, fontsize=9)
                ax.legend(loc='upper left', prop=zh_font)
                ax.grid(True, alpha=0.3)
            else:
                ax.text(0.5, 0.5, '無法繪製淨值曲線', ha='center', va='center',
                       fontproperties=zh_font, fontsize=12)
            
            fig.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, master=parent)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
        except Exception as e:
            print(f"繪製淨值曲線錯誤: {e}")
            ttk.Label(parent, text=f"無法繪製淨值曲線: {e}").pack()
    
    def _generate_conclusion(self, results):
        """生成結論"""
        conclusions = []
        
        if results['total_return'] > results['buy_hold_return']:
            conclusions.append("✓ 該策略表現優於買入持有策略")
        else:
            conclusions.append("✗ 該策略表現不如買入持有策略")
        
        if results['sharpe_ratio'] > 1.5:
            conclusions.append("✓ 風險調整後報酬優異（Sharpe > 1.5）")
        elif results['sharpe_ratio'] > 1:
            conclusions.append("○ 風險調整後報酬良好（Sharpe > 1）")
        elif results['sharpe_ratio'] > 0:
            conclusions.append("○ 風險調整後報酬普通（Sharpe > 0）")
        else:
            conclusions.append("✗ 風險調整後報酬不佳（Sharpe < 0）")
        
        conclusions.append(f"最大回撤為{results['max_drawdown']:.2f}%，需注意風險控管")
        
        return " | ".join(conclusions)


# ============================================================================
# 投資建議彈窗
# ============================================================================


"""
RecommendationDialog v4.5.3 - 現代暗黑金融風配色
修復：滾輪綁定問題、配色優化
"""

# ============================================================================
# 配色常數定義 - 現代暗黑金融風
# ============================================================================
class DarkTheme:
    """暗黑金融風配色方案"""
    # 背景色
    BG_MAIN = "#1e1e1e"        # 主背景（極深灰）
    BG_CARD = "#2d2d2d"        # 卡片背景
    BG_HEADER = "#252525"      # 標題列背景
    BG_TABLE_ODD = "#2d2d2d"   # 表格奇數行
    BG_TABLE_EVEN = "#363636"  # 表格偶數行
    
    # 文字色
    TEXT_PRIMARY = "#e0e0e0"   # 主要文字（米白）
    TEXT_SECONDARY = "#9e9e9e" # 次要文字（淺灰）
    TEXT_TITLE = "#81d4fa"     # 標題文字（淡藍）
    
    # 強調色
    ACCENT_BLUE = "#2962ff"    # 藍色按鈕
    ACCENT_GOLD = "#ffd700"    # 金色（重要提示）
    
    # 漲跌色
    UP_COLOR = "#00e676"       # 上漲（亮綠）
    DOWN_COLOR = "#ff1744"     # 下跌（亮紅）
    NEUTRAL_COLOR = "#ffc107"  # 中性（琥珀）
    
    # 建議色
    STRONG_BUY_BG = "#1b5e20"  # 強力買進背景（深綠）
    STRONG_BUY_FG = "#69f0ae"  # 強力買進文字（亮綠）
    STRONG_SELL_BG = "#b71c1c" # 強力賣出背景（深紅）
    STRONG_SELL_FG = "#ff8a80" # 強力賣出文字（粉紅）
    HOLD_BG = "#f57f17"        # 持有背景（深黃）
    HOLD_FG = "#ffeb3b"        # 持有文字（亮黃）
    
    # 邊框色
    BORDER_COLOR = "#424242"   # 邊框（深灰）


class RecommendationDialog:
    """投資建議彈窗 v4.5.3 - 現代暗黑金融風"""
    
    def __init__(self, parent, analysis_result):
        from analyzers import DecisionMatrix
        
        self.dialog = tk.Toplevel(parent)
        self.result = analysis_result
        self.parent = parent
        self._unbind_mousewheel = None  # 將在 _create_scrollable_frame 中設置
        
        # 取得股票名稱
        stock_name = analysis_result.get('name', analysis_result.get('symbol', ''))
        symbol = analysis_result.get('symbol', '')
        
        # 視窗標題
        if analysis_result.get('is_historical'):
            title = f"📊 {symbol} {stock_name} 歷史分析報告 [{analysis_result.get('analysis_date', '')}]"
        else:
            title = f"📊 {symbol} {stock_name} 完整量化分析報告 v4.5"
        self.dialog.title(title)
        self.dialog.geometry("1050x900")
        self.dialog.configure(bg=DarkTheme.BG_MAIN)
        
        # build_prompt_06：單一真相源。報告只讀 build_verdict，不重算任何分數/等級/目標。
        from report_formatter import build_verdict
        try:
            self.verdict = build_verdict(analysis_result)
        except Exception as e:
            print(f"build_verdict 失敗: {e}")
            import traceback; traceback.print_exc()
            self.verdict = {'grade': 'X', 'grade_label': '無法產生', 'overall_text': '',
                            'score': None, 'scores': {}, 'score_notes': {}, 'term_advice': {},
                            'adjustments': [], 'plan': {}, 'volume_profile': {}, 'chip_detail': [],
                            'chip_summary': {}, 'evidence': {}, 'warnings': ['分析資料不足']}

        # 主框架 - 使用 Canvas 實現滾動
        self._create_scrollable_frame()

        # build_prompt_06 定稿版面：八區塊，順序固定不得增刪調序
        self._build_block_01_verdict()        # 01 裁決
        self._build_block_02_term_advice()    # 02 分期建議
        self._build_block_03_trade_plan()     # 03 交易計畫
        self._build_block_04_scores_trail()   # 04 三層分數與裁決軌跡
        self._build_block_05_volume()         # 05 量價分析
        self._build_block_06_chip_detail()    # 06 籌碼近10日明細
        self._build_block_07_evidence()       # 07 證據明細
        self._build_block_08_risk()           # 08 風險與警示＋免責
        
        # 關閉按鈕 - 使用深色背景
        btn_frame = tk.Frame(self.dialog, bg=DarkTheme.BG_MAIN)
        btn_frame.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame, text="關閉視窗", command=self._on_close,
                 font=("Arial", 12, "bold"), bg="#424242", fg="white",
                 activebackground="#616161", activeforeground="white",
                 width=15, height=1, relief=tk.RAISED, cursor="hand2").pack()
        
        # 視窗關閉時清理綁定
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _on_close(self):
        """視窗關閉時清理滾輪綁定"""
        try:
            # 使用保存的解綁函數
            if hasattr(self, '_unbind_mousewheel') and self._unbind_mousewheel:
                self._unbind_mousewheel()
            # 備用：直接解綁
            elif hasattr(self, 'canvas'):
                try:
                    self.canvas.unbind_all("<MouseWheel>")
                    self.canvas.unbind_all("<Button-4>")
                    self.canvas.unbind_all("<Button-5>")
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                self.dialog.destroy()
            except Exception:
                pass
    
    def _create_scrollable_frame(self):
        """創建可滾動的主框架（完整修復版）"""
        # 外層容器
        container = tk.Frame(self.dialog, bg=DarkTheme.BG_MAIN)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Canvas
        self.canvas = tk.Canvas(container, bg=DarkTheme.BG_MAIN, 
                               highlightthickness=0, borderwidth=0)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        # 內容框架
        self.content_frame = tk.Frame(self.canvas, bg=DarkTheme.BG_MAIN)
        
        # 創建視窗
        self.canvas_window = self.canvas.create_window(0, 0, window=self.content_frame, anchor="nw")
        
        # 更新滾動區域
        def _on_frame_configure(event):
            try:
                if self.canvas.winfo_exists():
                    self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            except Exception:
                pass
        
        def _on_canvas_configure(event):
            try:
                if self.canvas.winfo_exists():
                    self.canvas.itemconfig(self.canvas_window, width=event.width)
            except Exception:
                pass
        
        self.content_frame.bind("<Configure>", _on_frame_configure)
        self.canvas.bind("<Configure>", _on_canvas_configure)
        
        # 滑鼠滾輪支援（跨平台）- 關鍵修正：加入存活檢查
        def _on_mousewheel(event):
            try:
                # 關鍵修正：先檢查 canvas 是否還存在
                if not self.canvas.winfo_exists():
                    return
                
                # 執行滾動
                if event.delta:
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    self.canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.canvas.yview_scroll(1, "units")
            except Exception:
                # 發生任何錯誤（如視窗已關閉），直接忽略
                pass
        
        # 綁定滾輪事件到 canvas
        self.canvas.bind("<MouseWheel>", _on_mousewheel)
        self.canvas.bind("<Button-4>", _on_mousewheel)
        self.canvas.bind("<Button-5>", _on_mousewheel)
        
        # 讓內容區域也能接收滾輪事件
        def _bind_to_mousewheel(event):
            try:
                if self.canvas.winfo_exists():
                    self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
                    self.canvas.bind_all("<Button-4>", _on_mousewheel)
                    self.canvas.bind_all("<Button-5>", _on_mousewheel)
            except Exception:
                pass
        
        def _unbind_from_mousewheel(event=None):
            try:
                if hasattr(self, 'canvas') and self.canvas.winfo_exists():
                    self.canvas.unbind_all("<MouseWheel>")
                    self.canvas.unbind_all("<Button-4>")
                    self.canvas.unbind_all("<Button-5>")
            except Exception:
                pass
        
        # 保存解綁函數供 _on_close 使用
        self._unbind_mousewheel = _unbind_from_mousewheel
        
        # 設定滑鼠進出事件
        self.canvas.bind("<Enter>", _bind_to_mousewheel)
        self.canvas.bind("<Leave>", _unbind_from_mousewheel)
    
    def _create_card(self, parent, title, title_color=None):
        """創建一個卡片區塊"""
        if title_color is None:
            title_color = DarkTheme.TEXT_TITLE
        
        card = tk.Frame(parent, bg=DarkTheme.BG_CARD, relief=tk.FLAT, 
                       highlightbackground=DarkTheme.BORDER_COLOR, highlightthickness=1)
        card.pack(fill=tk.X, padx=5, pady=8)
        
        # 標題列
        title_frame = tk.Frame(card, bg=DarkTheme.BG_HEADER)
        title_frame.pack(fill=tk.X)
        
        tk.Label(title_frame, text=title, font=("Arial", 14, "bold"),
                fg=title_color, bg=DarkTheme.BG_HEADER, pady=10, padx=15).pack(side=tk.LEFT)
        
        # 內容區
        content = tk.Frame(card, bg=DarkTheme.BG_CARD, padx=15, pady=12)
        content.pack(fill=tk.X)
        
        return content
    
    # ══════════════════════════════════════════════════════════════════
    # build_prompt_06 定稿版面：設計 token 工具
    # ══════════════════════════════════════════════════════════════════
    _MONO = "Menlo"           # 等寬字體（macOS）；缺字時 tkinter 自動替換
    _WARN_BG = "#403a1e"      # 唯一允許的強調底色（軌跡降級行 / 缺日列）
    # fix_07：等級徽章色（台股慣例）— A 琥珀 / B 藍 / C 灰 / SELL·X 綠；不用紅色。
    # （綠自此只承載賣出/下跌語意，橘=買進族）
    _GRADE_COLORS = {
        'A': ("#4a3d10", "#EF9F27"), 'B': ("#12365a", "#5FA8E0"),
        'C': ("#2a2f37", "#8B9099"), 'SELL': ("#123a2a", "#4CB782"),
        'WAIT': ("#2a2f37", "#8B9099"), 'SKIP': ("#2a2f37", "#8B9099"),
        'X': ("#123a2a", "#4CB782"),
    }

    @staticmethod
    def _fmtnum(x, dec=0, sign=False, dash='—'):
        """數字格式化：千分位、可帶正負號；None/str/NaN → '—'（禁止 N/A/None 字樣）。"""
        try:
            if x is None or isinstance(x, str):
                return dash
            v = float(x)
            if v != v:
                return dash
            s = f"{v:+,.{dec}f}" if sign else f"{v:,.{dec}f}"
            return s
        except (TypeError, ValueError):
            return dash

    def _net_color(self, v):
        """台股慣例：淨額正=紅、負=綠。"""
        try:
            v = float(v)
        except (TypeError, ValueError):
            return DarkTheme.TEXT_SECONDARY
        if v > 0:
            return DarkTheme.DOWN_COLOR   # 紅
        if v < 0:
            return DarkTheme.UP_COLOR     # 綠
        return DarkTheme.TEXT_SECONDARY

    def _section(self, no, name):
        """區塊容器：編號＋名稱（muted 11px）+ 0.5px 分隔線，回傳內容 frame。"""
        wrap = tk.Frame(self.content_frame, bg=DarkTheme.BG_MAIN)
        wrap.pack(fill=tk.X, padx=14, pady=(10, 0))
        head = tk.Frame(wrap, bg=DarkTheme.BG_MAIN)
        head.pack(fill=tk.X)
        tk.Label(head, text=f"{no}", font=(self._MONO, 11), fg=DarkTheme.TEXT_SECONDARY,
                 bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)
        tk.Label(head, text=f"  {name}", font=("Arial", 11), fg=DarkTheme.TEXT_SECONDARY,
                 bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)
        sep = tk.Frame(wrap, bg=DarkTheme.BORDER_COLOR, height=1)
        sep.pack(fill=tk.X, pady=(4, 8))
        body = tk.Frame(wrap, bg=DarkTheme.BG_MAIN)
        body.pack(fill=tk.X)
        return body

    def _kv_rows(self, parent, rows):
        """標籤-值單欄表。rows=[(label, value_text, value_color_or_None), ...]。"""
        for i, (label, val, color) in enumerate(rows):
            r = tk.Frame(parent, bg=DarkTheme.BG_MAIN)
            r.pack(fill=tk.X, pady=1)
            tk.Label(r, text=label, font=("Arial", 11), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_MAIN, width=16, anchor="w").pack(side=tk.LEFT)
            tk.Label(r, text=val, font=(self._MONO, 11), fg=(color or DarkTheme.TEXT_PRIMARY),
                     bg=DarkTheme.BG_MAIN, anchor="w").pack(side=tk.LEFT)

    # ── 01 裁決 ─────────────────────────────────────────────────────────
    def _build_block_01_verdict(self):
        v = self.verdict
        body = self._section("01", "裁決")
        top = tk.Frame(body, bg=DarkTheme.BG_MAIN)
        top.pack(fill=tk.X)
        bg, fg = self._GRADE_COLORS.get(v.get('grade'), self._GRADE_COLORS['X'])
        tk.Label(top, text=f" {v.get('grade','—')} ", font=("Arial", 22, "bold"),
                 fg=fg, bg=bg, padx=10, pady=2).pack(side=tk.LEFT)
        tk.Label(top, text=f"  {v.get('name', v.get('symbol',''))}", font=("Arial", 15, "bold"),
                 fg=DarkTheme.TEXT_PRIMARY, bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT, padx=6)
        tk.Label(top, text=self._fmtnum(v.get('score'), 0), font=(self._MONO, 26, "bold"),
                 fg=DarkTheme.TEXT_PRIMARY, bg=DarkTheme.BG_MAIN).pack(side=tk.RIGHT)
        tk.Label(top, text="綜合分 ", font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                 bg=DarkTheme.BG_MAIN).pack(side=tk.RIGHT)
        # 覆蓋建議一行（同源 overall_text）— fix_07：文字色吃動作語意（買=橘/賣=綠/中性=灰）
        import theme as _thm
        _act_col = _thm.action_color(v.get('action_code') or v.get('overall_text', ''))
        tk.Label(body, text=v.get('overall_text', ''), font=("Arial", 12),
                 fg=_act_col, bg=DarkTheme.BG_MAIN, anchor="w").pack(fill=tk.X, pady=(4, 2))
        # meta 行
        cs = v.get('chip_summary', {}) or {}
        reliable = cs.get('reliable')
        chip_txt = "完整" if reliable is not False else f"缺 {len(cs.get('missing_dates') or [])} 日"
        chip_color = DarkTheme.TEXT_SECONDARY if reliable is not False else DarkTheme.NEUTRAL_COLOR
        meta = tk.Frame(body, bg=DarkTheme.BG_MAIN)
        meta.pack(fill=tk.X)
        tk.Label(meta, text=f"資料基準：{v.get('data_date','—') or '—'}", font=("Arial", 10),
                 fg=DarkTheme.TEXT_SECONDARY, bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)
        tk.Label(meta, text=f"｜信心：{v.get('confidence','—') or '—'}", font=("Arial", 10),
                 fg=DarkTheme.TEXT_SECONDARY, bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)
        tk.Label(meta, text=f"｜籌碼資料：{chip_txt}", font=("Arial", 10),
                 fg=chip_color, bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)

    # ── 02 分期建議 ─────────────────────────────────────────────────────
    def _build_block_02_term_advice(self):
        body = self._section("02", "分期建議")
        ta = self.verdict.get('term_advice', {}) or {}
        rows = [("短線 5–20 日", ta.get('short', {})),
                ("中線 1–3 月", ta.get('mid', {})),
                ("長線 3–6 月", ta.get('long', {}))]
        for label, adv in rows:
            r = tk.Frame(body, bg=DarkTheme.BG_MAIN)
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=label, font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_MAIN, width=12, anchor="w").pack(side=tk.LEFT)
            tk.Label(r, text=(adv.get('action') or '—'), font=("Arial", 12, "bold"),
                     fg=DarkTheme.TEXT_PRIMARY, bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)
            reason = adv.get('reason') or ''
            if reason:
                tk.Label(r, text=f" — {reason}", font=("Arial", 10),
                         fg=DarkTheme.TEXT_SECONDARY, bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)

    # ── 03 交易計畫 ─────────────────────────────────────────────────────
    def _build_block_03_trade_plan(self):
        body = self._section("03", "交易計畫")
        p = self.verdict.get('plan', {}) or {}

        def _pos_num(x):
            v = self._fmtnum(x, 2)
            return v if v != '—' else None

        if p.get('is_exit'):
            # fix_07 任務4：賣出族 → 出場計畫版型（退化欄位一律 '—'）
            body_title = "交易計畫（出場）"
            exit_ref = _pos_num(p.get('exit_ref'))
            hstop = _pos_num(p.get('holder_stop'))
            dref = _pos_num(p.get('downside_ref'))
            cards = [
                ("出場參考", f"{exit_ref}" if exit_ref else '—'),
                ("持有者停損", (f"{hstop}  (ATR×{self._fmtnum(p.get('stop_atr_mult'),1)})" if hstop else '—')),
                ("下檔風險參考", f"{dref}" if dref else '—'),
                ("建議部位", "出清 / 避開"),
            ]
        else:
            ez = p.get('entry_zone')
            # 禁止退化：單點進場區（上下緣相同）→ '—'
            if isinstance(ez, (list, tuple)) and self._fmtnum(ez[0], 2) != self._fmtnum(ez[1], 2):
                ez_txt = f"{self._fmtnum(ez[0],2)} – {self._fmtnum(ez[1],2)}"
            else:
                ez_txt = '—'
            sl = self._fmtnum(p.get('stop_loss'), 2)
            sl_txt = (f"{sl}  (ATR×{self._fmtnum(p.get('stop_atr_mult'),1)})" if sl != '—' else '—')
            tgt = self._fmtnum(p.get('target'), 2)
            rr = p.get('rr')
            # 禁止退化：RR 0.0 → '—'
            _rr_txt = self._fmtnum(rr, 1)
            try:
                if rr is None or float(rr) <= 0:
                    _rr_txt = '—'
            except (TypeError, ValueError):
                _rr_txt = '—'
            tgt_txt = (f"{tgt}   RR {_rr_txt}" if tgt != '—' else '—')
            pos = p.get('position_pct')
            # 禁止退化：部位 0.0% → '—'
            try:
                pos_txt = f"{self._fmtnum(pos,1)}%" if (pos is not None and float(pos) > 0) else '—'
            except (TypeError, ValueError):
                pos_txt = '—'
            cards = [("進場參考區", ez_txt), ("停損", sl_txt), ("目標 ＋ RR", tgt_txt), ("建議部位", pos_txt)]
        grid = tk.Frame(body, bg=DarkTheme.BG_MAIN)
        grid.pack(fill=tk.X)
        for idx, (lab, val) in enumerate(cards):
            cell = tk.Frame(grid, bg=DarkTheme.BG_CARD, highlightbackground=DarkTheme.BORDER_COLOR,
                            highlightthickness=1)
            cell.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=4, pady=4)
            tk.Label(cell, text=lab, font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_CARD).pack(anchor="w", padx=10, pady=(8, 0))
            tk.Label(cell, text=val, font=(self._MONO, 14, "bold"), fg=DarkTheme.TEXT_PRIMARY,
                     bg=DarkTheme.BG_CARD).pack(anchor="w", padx=10, pady=(0, 8))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    # ── 04 三層分數與裁決軌跡 ───────────────────────────────────────────
    def _build_block_04_scores_trail(self):
        body = self._section("04", "三層分數與裁決軌跡")
        sc = self.verdict.get('scores', {}) or {}
        notes = self.verdict.get('score_notes', {}) or {}
        for key, label in [('direction', '方向'), ('position', '位置'), ('timing', '時機')]:
            val = sc.get(key)
            r = tk.Frame(body, bg=DarkTheme.BG_MAIN)
            r.pack(fill=tk.X, pady=2)
            tk.Label(r, text=label, font=("Arial", 11), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_MAIN, width=6, anchor="w").pack(side=tk.LEFT)
            if isinstance(val, (int, float)):
                bar_bg = tk.Frame(r, bg=DarkTheme.BG_HEADER, width=200, height=12)
                bar_bg.pack(side=tk.LEFT, padx=4)
                bar_bg.pack_propagate(False)
                fillw = max(0, min(200, int(val / 100 * 200)))
                # fix_07 任務6 規則3：三層分數條由綠改中性藍（綠只承載賣出/下跌）
                import theme as _thm
                col = _thm.NEUTRAL_BLUE if val >= 50 else DarkTheme.TEXT_SECONDARY
                fill = tk.Frame(bar_bg, bg=col, width=fillw, height=12)
                fill.pack(side=tk.LEFT)
                tk.Label(r, text=self._fmtnum(val, 0), font=(self._MONO, 11),
                         fg=DarkTheme.TEXT_PRIMARY, bg=DarkTheme.BG_MAIN, width=4).pack(side=tk.LEFT)
            else:
                tk.Label(r, text=f" {val or '—'} ", font=(self._MONO, 11, "bold"),
                         fg=DarkTheme.TEXT_PRIMARY, bg=DarkTheme.BG_HEADER).pack(side=tk.LEFT, padx=4)
            note = notes.get(key) or '—'
            tk.Label(r, text=f"  {note}", font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_MAIN).pack(side=tk.LEFT)
        # 軌跡表
        tk.Label(body, text="裁決軌跡", font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                 bg=DarkTheme.BG_MAIN).pack(anchor="w", pady=(8, 2))
        for step in (self.verdict.get('adjustments') or []):
            downgrade = step.get('to') is not None and step.get('from') is not None
            rbg = self._WARN_BG if downgrade else DarkTheme.BG_MAIN
            r = tk.Frame(body, bg=rbg)
            r.pack(fill=tk.X, pady=1)
            change = (f"{step.get('from')}→{step.get('to')}" if downgrade else "—")
            tk.Label(r, text=step.get('stage', ''), font=("Arial", 10), fg=DarkTheme.TEXT_PRIMARY,
                     bg=rbg, width=10, anchor="w").pack(side=tk.LEFT, padx=(4, 0))
            tk.Label(r, text=change, font=(self._MONO, 10), fg=DarkTheme.TEXT_PRIMARY,
                     bg=rbg, width=8, anchor="w").pack(side=tk.LEFT)
            tk.Label(r, text=step.get('reason', ''), font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                     bg=rbg, anchor="w").pack(side=tk.LEFT)

    # ── 05 量價分析 ─────────────────────────────────────────────────────
    def _build_block_05_volume(self):
        body = self._section("05", "量價分析")
        vp = self.verdict.get('volume_profile', {}) or {}
        rows = [
            ("今日量（張）", self._fmtnum(vp.get('today_volume'), 0), None),
            ("量比 vs 5日均", self._fmtnum(vp.get('vol_ratio'), 2), None),
            ("量能 Z", self._fmtnum(vp.get('volume_zscore'), 2), None),
            ("均量結構", vp.get('volume_trend') or '—', None),
            ("量價配合", (", ".join(vp.get('vp_signals') or []) or '—'), None),
        ]
        spike = vp.get('spike_signal')
        if spike:
            rows.append(("爆量／背離", str(spike), DarkTheme.NEUTRAL_COLOR))
        self._kv_rows(body, rows)

    # ── 06 籌碼近10日明細 ───────────────────────────────────────────────
    def _build_block_06_chip_detail(self):
        body = self._section("06", "籌碼近 10 日明細")
        cs = self.verdict.get('chip_summary', {}) or {}
        fd, td = cs.get('foreign_days'), cs.get('trust_days')
        def _daytxt(d):
            if not isinstance(d, (int, float)) or d == 0:
                return "—"
            return f"連{abs(int(d))}日{'買' if d > 0 else '賣'}超"
        summ = f"外資 {_daytxt(fd)}　投信 {_daytxt(td)}　單位：張"
        if cs.get('reliable') is False:
            summ += f"　⚠️ 資料不完整（缺 {len(cs.get('missing_dates') or [])} 日，已排除於連買計算）"
        tk.Label(body, text=summ, font=("Arial", 10), fg=DarkTheme.TEXT_SECONDARY,
                 bg=DarkTheme.BG_MAIN).pack(anchor="w", pady=(0, 4))
        cols = [("日期", 11), ("外資買", 8), ("外資賣", 8), ("外資淨", 8),
                ("投信買", 8), ("投信賣", 8), ("投信淨", 8), ("自營淨", 8), ("合計淨", 9)]
        hdr = tk.Frame(body, bg=DarkTheme.BG_HEADER)
        hdr.pack(fill=tk.X)
        for name, w in cols:
            tk.Label(hdr, text=name, font=(self._MONO, 10), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_HEADER, width=w, anchor="e").pack(side=tk.LEFT, padx=1)
        for i, d in enumerate(self.verdict.get('chip_detail') or []):
            miss = d.get('is_missing')
            rbg = self._WARN_BG if miss else (DarkTheme.BG_TABLE_ODD if i % 2 else DarkTheme.BG_TABLE_EVEN)
            r = tk.Frame(body, bg=rbg)
            r.pack(fill=tk.X)
            if miss:
                tk.Label(r, text=d.get('date', ''), font=(self._MONO, 10), fg=DarkTheme.TEXT_PRIMARY,
                         bg=rbg, width=11, anchor="e").pack(side=tk.LEFT, padx=1)
                tk.Label(r, text="資料缺漏（已排除於連買計算）", font=("Arial", 10),
                         fg=DarkTheme.NEUTRAL_COLOR, bg=rbg, anchor="w").pack(side=tk.LEFT, padx=6)
                continue
            vals = [
                (d.get('date', ''), DarkTheme.TEXT_PRIMARY),
                (self._fmtnum(d.get('foreign_buy'), 0), DarkTheme.TEXT_PRIMARY),
                (self._fmtnum(d.get('foreign_sell'), 0), DarkTheme.TEXT_PRIMARY),
                (self._fmtnum(d.get('foreign_net'), 0, sign=True), self._net_color(d.get('foreign_net'))),
                (self._fmtnum(d.get('trust_buy'), 0), DarkTheme.TEXT_PRIMARY),
                (self._fmtnum(d.get('trust_sell'), 0), DarkTheme.TEXT_PRIMARY),
                (self._fmtnum(d.get('trust_net'), 0, sign=True), self._net_color(d.get('trust_net'))),
                (self._fmtnum(d.get('dealer_net'), 0, sign=True), self._net_color(d.get('dealer_net'))),
                (self._fmtnum(d.get('total_net'), 0, sign=True), self._net_color(d.get('total_net'))),
            ]
            for (txt, col), (_n, w) in zip(vals, cols):
                tk.Label(r, text=txt, font=(self._MONO, 10), fg=col, bg=rbg,
                         width=w, anchor="e").pack(side=tk.LEFT, padx=1)

    # ── 07 證據明細 ─────────────────────────────────────────────────────
    def _build_block_07_evidence(self):
        body = self._section("07", "證據明細")
        ev = self.verdict.get('evidence', {}) or {}
        pth = ev.get('pth')
        pth_txt = (f"{self._fmtnum(pth,3)}（距52週高 {self._fmtnum(ev.get('dist_from_high'),1,sign=True)}%）"
                   if pth is not None else '—')
        tf = ev.get('timeframe', {}) or {}
        tf_txt = "　".join([t for t in [
            ("短波段✓" if tf.get('short_swing') else None),
            ("趨勢波段✓" if tf.get('position_trend') else None)] if t]) or '—'
        trig = ev.get('triggers') or []
        trig_txt = "；".join(trig[:3]) if trig else '—'
        yoy = ev.get('revenue_yoy')
        rev_txt = ('—' if yoy is None else
                   f"YoY {self._fmtnum(yoy*100,1,sign=True)}%" + ("　創12月高✓" if ev.get('rev_12m_high') else ""))
        # build_prompt_08：所屬題材（題材強度百分位／領導股）
        th = ev.get('theme', {}) or {}
        if th.get('theme_name'):
            _parts = [th['theme_name']]
            if th.get('theme_rank_pct') is not None:
                _parts.append(f"題材強度 {self._fmtnum(th['theme_rank_pct'],0)}")
            if th.get('is_theme_leader'):
                _parts.append("領導股")
            elif th.get('is_top_theme'):
                _parts.append("主流題材")
            theme_txt = "（".join([_parts[0], "・".join(_parts[1:]) + "）"]) if len(_parts) > 1 else _parts[0]
        else:
            theme_txt = '—'
        rows = [
            ("PTH 52週高", pth_txt, None),
            ("RS 同儕排名", (self._fmtnum(ev.get('rs_rank'), 0) if ev.get('rs_rank') is not None
                          else self._fmtnum(ev.get('rs_score'), 0)), None),
            ("突破觸發", trig_txt, None),
            ("時間框架", tf_txt, None),
            ("月營收動能", rev_txt, None),
            ("組合標籤", (ev.get('combo_tag') or '—'), (DarkTheme.NEUTRAL_COLOR if ev.get('combo_tag') else None)),
            ("所屬題材", theme_txt, (DarkTheme.ACCENT_GOLD if th.get('is_top_theme') else None)),
        ]
        self._kv_rows(body, rows)

    # ── 08 風險與警示＋免責 ─────────────────────────────────────────────
    def _build_block_08_risk(self):
        body = self._section("08", "風險與警示")
        warns = self.verdict.get('warnings') or []
        if not warns:
            tk.Label(body, text="無重大警示", font=("Arial", 11), fg=DarkTheme.TEXT_SECONDARY,
                     bg=DarkTheme.BG_MAIN).pack(anchor="w")
        for w in warns:
            row = tk.Frame(body, bg=DarkTheme.BG_MAIN)
            row.pack(fill=tk.X, pady=2)
            tk.Frame(row, bg=DarkTheme.NEUTRAL_COLOR, width=2).pack(side=tk.LEFT, fill=tk.Y)
            tk.Label(row, text=f"  {w}", font=("Arial", 11), fg=DarkTheme.TEXT_PRIMARY,
                     bg=DarkTheme.BG_MAIN, justify=tk.LEFT, wraplength=980, anchor="w").pack(side=tk.LEFT)
        tk.Label(body, text="本報告為量化模型輸出，僅供研究參考，不構成投資建議；投資有風險，決策請自負盈虧。",
                 font=("Arial", 9), fg=DarkTheme.TEXT_SECONDARY, bg=DarkTheme.BG_MAIN,
                 wraplength=1000, justify=tk.LEFT).pack(anchor="w", pady=(10, 4))
# ============================================================================
# v4.0 新增：相關性分析彈窗
# ============================================================================


# ============================================================================
# v4.0 新增：相關性分析彈窗
# ============================================================================

class CorrelationDialog:
    """相關性分析彈窗"""
    
    def __init__(self, parent, symbols, market="台股"):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("📊 自選股相關性分析")
        self.dialog.geometry("800x700")
        
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="📊 自選股相關性分析", font=("Arial", 16, "bold")).pack(pady=(0, 15))
        
        # 執行相關性計算
        result, error = CorrelationAnalyzer.calculate_correlation_matrix(symbols, market)
        
        if error:
            ttk.Label(main_frame, text=f"錯誤：{error}", foreground="red").pack()
            ttk.Button(main_frame, text="關閉", command=self.dialog.destroy).pack(pady=20)
            return
        
        # 顯示相關性矩陣圖
        chart_frame = ttk.Frame(main_frame)
        chart_frame.pack(fill=tk.BOTH, expand=True)
        
        self._plot_correlation_heatmap(chart_frame, result['matrix'])
        
        # 分析結果
        analysis = result['analysis']
        
        result_frame = ttk.LabelFrame(main_frame, text="分析結果", padding=10)
        result_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(result_frame, text=f"平均相關性：{analysis['avg_correlation']:.3f}",
                 font=("Arial", 11)).pack(anchor=tk.W)
        ttk.Label(result_frame, text=f"分散化程度：{analysis['diversification']}",
                 font=("Arial", 11, "bold")).pack(anchor=tk.W)
        ttk.Label(result_frame, text=analysis['diversification_advice'],
                 font=("Arial", 10), wraplength=700).pack(anchor=tk.W, pady=5)
        
        if analysis['high_corr_pairs']:
            high_corr_text = "高相關配對：" + ", ".join([f"{p[0]}-{p[1]}({p[2]:.2f})" for p in analysis['high_corr_pairs'][:5]])
            ttk.Label(result_frame, text=high_corr_text, font=("Arial", 10), foreground="red").pack(anchor=tk.W)
        
        ttk.Button(main_frame, text="關閉", command=self.dialog.destroy, width=15).pack(pady=10)
    
    def _plot_correlation_heatmap(self, parent, corr_matrix):
        """繪製相關性熱力圖"""
        try:
            fig = Figure(figsize=(7, 5), dpi=100)
            ax = fig.add_subplot(111)
            
            im = ax.imshow(corr_matrix.values, cmap='RdYlGn', vmin=-1, vmax=1)
            
            # 設定標籤
            ax.set_xticks(range(len(corr_matrix.columns)))
            ax.set_yticks(range(len(corr_matrix.columns)))
            ax.set_xticklabels(corr_matrix.columns, rotation=45, ha='right')
            ax.set_yticklabels(corr_matrix.columns)
            
            # 添加數值標註
            for i in range(len(corr_matrix)):
                for j in range(len(corr_matrix)):
                    text = ax.text(j, i, f'{corr_matrix.iloc[i, j]:.2f}',
                                  ha='center', va='center', fontsize=8)
            
            fig.colorbar(im, ax=ax, label='相關係數')
            ax.set_title('股票相關性矩陣', fontproperties=zh_font)
            fig.tight_layout()
            
            canvas = FigureCanvasTkAgg(fig, master=parent)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
        except Exception as e:
            print(f"繪製相關性圖錯誤: {e}")
            ttk.Label(parent, text=f"無法繪製相關性圖: {e}").pack()


# ============================================================================
# 主GUI應用程式 v4.0
# ============================================================================


# ============================================================================
# 主GUI應用程式 v4.0
# ============================================================================

class StockAnalysisApp(tk.Tk):
    """股票分析主應用程式 v4.0"""
    
    def __init__(self):
        super().__init__()

        self.title("量化投資分析系統 v4.3")
        self.geometry("1550x1000")

        # === UI 改造：套用專業投資終端外觀（純呈現層）===
        try:
            import theme
            self._theme = theme
            theme.apply_theme(self)
            theme.apply_matplotlib_dark()
        except Exception as _te:
            print(f"[UI] 主題套用略過: {_te}")
            self._theme = None

        self.db = WatchlistDatabase()
        
        self.df = None
        self.current_symbol = None
        self.auto_analysis_done = False
        self.slippage_var = None
        
        # v4.3.6 新增：儲存最後一次分析結果（供下單視窗使用）
        self.last_analysis_result = None
        
        self._create_widgets()
        self.refresh_watchlist()
        self.after(1000, self.auto_analyze_watchlist)
        
        # 清理過期緩存
        self.db.clean_old_cache(days=7)

        # v4.3 新增：開啟程式時顯示市場排行
        self.after(500, self._show_market_ranking)

        # build_prompt_03：籌碼資料層啟動初始化 + 每日排程（背景執行，不卡 UI）
        self.after(1500, self._chip_startup_init)
        self._schedule_daily_chip_update()

    def _chip_startup_init(self):
        """
        程式啟動時的籌碼資料初始化（背景執行緒）：
        - 首次執行：sync_calendar + 對 watchlist backfill(90)
        - 之後：若 chip_daily 最新日落後 trading_calendar 最新日 > 1 交易日 → 自動補洞
        """
        import threading

        def _work():
            try:
                from chip_data_manager import get_chip_manager
                mgr = get_chip_manager(self.db.db_name)
                # 交易日曆（首次或過期）
                if not mgr.get_latest_trading_day():
                    mgr.sync_calendar()
                else:
                    mgr.sync_calendar()   # 每次啟動輕量補最新交易日

                stocks = self.db.get_all_stocks()
                syms = [s[0] for s in stocks if (s[2] if len(s) > 2 else '台股') == '台股']
                if not syms:
                    return

                # 首次執行偵測：chip_daily 完全沒資料 → 對 watchlist backfill(90)
                import sqlite3
                conn = sqlite3.connect(self.db.db_name)
                has_any = conn.execute("SELECT 1 FROM chip_daily LIMIT 1").fetchone()
                conn.close()
                if not has_any:
                    print(f"[籌碼] 首次執行：backfill {len(syms)} 檔（各 90 交易日）")
                    for sym in syms:
                        mgr.backfill(sym, trading_days=90)
                        import time as _t; _t.sleep(0.2)
                    print("[籌碼] 首次 backfill 完成")
                    return

                # 常態：檢查落後程度
                latest_cal = mgr.get_latest_trading_day()
                conn = sqlite3.connect(self.db.db_name)
                row = conn.execute("SELECT MAX(date) FROM chip_daily WHERE foreign_net IS NOT NULL").fetchone()
                conn.close()
                latest_chip = row[0] if row else None
                if latest_cal and latest_chip:
                    # 若最新籌碼日落後最新交易日，代表有洞 → 補
                    if latest_chip < latest_cal:
                        print(f"[籌碼] 資料落後（chip={latest_chip} < cal={latest_cal}），自動補洞")
                        mgr.daily_update(syms, holes=5)

                # build_prompt_04：月營收首次 backfill（revenue_monthly 空時）
                try:
                    from revenue_data_manager import get_revenue_manager
                    rmgr = get_revenue_manager(self.db.db_name)
                    conn = sqlite3.connect(self.db.db_name)
                    has_rev = conn.execute("SELECT 1 FROM revenue_monthly LIMIT 1").fetchone()
                    conn.close()
                    if not has_rev:
                        print(f"[營收] 首次執行：backfill {len(syms)} 檔（各 24 月）")
                        for sym in syms:
                            rmgr.backfill(sym, months=24)
                            import time as _t2; _t2.sleep(0.2)
                        print("[營收] 首次 backfill 完成")
                except Exception as _rev_e:
                    print(f"[營收] 啟動 backfill 略過: {_rev_e}")
            except Exception as e:
                print(f"[籌碼] 啟動初始化略過: {e}")

        threading.Thread(target=_work, daemon=True).start()

    def _schedule_daily_chip_update(self):
        """
        每交易日 16:30 後執行 daily_update（法人資料盤後陸續更新）。
        以 self.after 週期檢查，每日僅觸發一次；當日資料尚未出現時該日留 NULL，
        明日自動補洞。
        """
        import datetime as _dt

        def _tick():
            try:
                now = _dt.datetime.now()
                today = now.strftime('%Y-%m-%d')
                already = getattr(self, '_chip_updated_date', None)
                if now.hour >= 16 and (now.hour > 16 or now.minute >= 30) and already != today:
                    self._chip_updated_date = today
                    import threading
                    def _do():
                        try:
                            from chip_data_manager import get_chip_manager
                            mgr = get_chip_manager(self.db.db_name)
                            mgr.sync_calendar()
                            stocks = self.db.get_all_stocks()
                            syms = [s[0] for s in stocks if (s[2] if len(s) > 2 else '台股') == '台股']
                            if syms:
                                n = mgr.daily_update(syms, holes=5)
                                print(f"[籌碼] 16:30 排程 daily_update 補齊 {n} 筆")
                            # build_prompt_04：每月 10–12 日跑一次月營收更新
                            if 10 <= now.day <= 12 and syms:
                                from revenue_data_manager import get_revenue_manager
                                rmgr = get_revenue_manager(self.db.db_name)
                                rn = rmgr.monthly_update(syms)
                                print(f"[營收] 月更 monthly_update 補齊 {rn} 檔")
                        except Exception as e:
                            print(f"[籌碼] 排程 daily_update 略過: {e}")
                    threading.Thread(target=_do, daemon=True).start()
            except Exception:
                pass
            # 每 10 分鐘檢查一次
            self.after(10 * 60 * 1000, _tick)

        # 啟動後 10 分鐘首次檢查
        self.after(10 * 60 * 1000, _tick)


    def _show_market_ranking(self):
        """顯示市場排行彈窗"""
        def on_stock_select(symbol):
            """點擊股票時的回調"""
            self.symbol_entry.delete(0, tk.END)
            self.symbol_entry.insert(0, symbol)
            self.market_var.set("台股")
            self.plot_chart()
        
        try:
            MarketRankingDialog(self, on_stock_select)
        except Exception as e:
            print(f"市場排行載入錯誤: {e}")
    
    def _show_order_dialog(self):
        """v4.3.5: 顯示富邦證券下單對話框"""
        try:
            # 取得目前查詢的股票代號
            current_symbol = self.symbol_entry.get().strip()
            
            # 取得全域 trader 實例
            trader = get_trader()
            
            # 顯示下單對話框
            create_order_dialog(self, symbol=current_symbol, trader=trader)
        except Exception as e:
            messagebox.showerror("錯誤", f"無法開啟下單功能: {e}\n\n請確認已安裝 fubon_trading 模組")
    
    def _show_auto_trader(self):
        """v4.4.4 新增: 顯示 AutoTrader 自動交易介面"""
        try:
            from auto_trader_gui import open_auto_trader_gui
            # v4.4.5：傳入已登入的 FubonTrader 實例
            fubon_trader = None
            try:
                from fubon_trading import get_trader
                fubon_trader = get_trader()
            except:
                pass
            open_auto_trader_gui(parent=self, fubon_trader=fubon_trader)
        except ImportError as e:
            messagebox.showerror("錯誤", f"無法開啟自動交易功能: {e}\n\n請確認 auto_trader_gui.py 存在")
        except Exception as e:
            messagebox.showerror("錯誤", f"開啟自動交易失敗: {e}")
    
    def _create_widgets(self):
        """建立UI元件"""
        # 頂部行情/狀態列（純呈現層）
        self._build_status_bar()

        main_container = ttk.Frame(self)
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        left_panel = ttk.Frame(main_container, width=440)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left_panel.pack_propagate(False)

        right_panel = ttk.Frame(main_container)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._create_left_panel(left_panel)
        self._create_right_panel(right_panel)

    # ── 頂部行情/狀態列 ──────────────────────────────────────────────
    def _build_status_bar(self):
        """頂部行情/狀態列：加權、櫃買（紅綠）、盤別、即時時鐘、最後更新。
        純呈現層；指數資料用既有 yf 路徑延遲填入，失敗則維持佔位。"""
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, side=tk.TOP, padx=8, pady=6)

        _th = getattr(self, '_theme', None)
        f_label = _th.ui_font(_th.SIZE_SMALL) if _th else ("TkDefaultFont", 11)
        f_num   = _th.num_font(_th.SIZE_SMALL, bold=True) if _th else ("TkFixedFont", 11, "bold")

        def _cell(parent, caption):
            box = ttk.Frame(parent); box.pack(side=tk.LEFT, padx=(0, 16))
            ttk.Label(box, text=caption, font=f_label,
                      foreground=(_th.TEXT_3 if _th else "gray")).pack(side=tk.LEFT, padx=(0, 4))
            val = ttk.Label(box, text="—", font=f_num,
                            foreground=(_th.TEXT if _th else "black"))
            val.pack(side=tk.LEFT)
            return val

        self._sb_taiex = _cell(bar, "加權")
        self._sb_tpex  = _cell(bar, "櫃買")

        # 右側：最後更新、盤別、即時時鐘
        self._sb_clock = ttk.Label(bar, text="--:--:--", font=f_num,
                                   foreground=(_th.TEXT if _th else "black"))
        self._sb_clock.pack(side=tk.RIGHT, padx=(8, 0))
        self._sb_session = ttk.Label(bar, text="", font=f_label,
                                    foreground=(_th.ACCENT if _th else "orange"))
        self._sb_session.pack(side=tk.RIGHT, padx=(8, 0))
        self._sb_update = ttk.Label(bar, text="更新 --:--", font=f_label,
                                   foreground=(_th.TEXT_2 if _th else "gray"))
        self._sb_update.pack(side=tk.RIGHT, padx=(8, 0))

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.TOP)

        self._tick_status_clock()
        self.after(1500, self._refresh_status_indices)

    def _tick_status_clock(self):
        """每秒更新時鐘與盤別（純時間判斷，不抓資料）。"""
        import datetime as _dt
        now = _dt.datetime.now()
        try:
            self._sb_clock.config(text=now.strftime("%H:%M:%S"))
            # 台股盤別（一般交易時段 09:00–13:30）
            hm = now.hour * 60 + now.minute
            wd = now.weekday()  # 5,6 = 週末
            if wd >= 5:
                sess = "休市"
            elif hm < 9 * 60:
                sess = "盤前"
            elif hm <= 13 * 60 + 30:
                sess = "盤中"
            else:
                sess = "收盤"
            self._sb_session.config(text=sess)
        except Exception:
            return
        self.after(1000, self._tick_status_clock)

    def _refresh_status_indices(self):
        """延遲填入加權/櫃買指數漲跌（用既有 yf 路徑，純呈現、失敗即略過）。"""
        _th = getattr(self, '_theme', None)

        def _fmt(label_widget, pct):
            if pct is None:
                return
            try:
                color = _th.trend_color(pct) if _th else ("red" if pct > 0 else "green" if pct < 0 else "gray")
                txt = (f"{pct:+.2f}%")
                label_widget.config(text=txt, foreground=color)
            except Exception:
                pass

        def _idx_pct(symbol):
            try:
                import yfinance as yf
                h = yf.Ticker(symbol).history(period="5d")
                if h is None or len(h) < 2:
                    return None
                c = h['Close'].dropna()
                return (c.iloc[-1] / c.iloc[-2] - 1) * 100
            except Exception:
                return None

        import threading, datetime as _dt
        def _work():
            taiex = _idx_pct("^TWII")
            tpex  = _idx_pct("^TWOII")
            def _apply():
                _fmt(self._sb_taiex, taiex)
                _fmt(self._sb_tpex, tpex)
                self._sb_update.config(text=f"更新 {_dt.datetime.now().strftime('%H:%M')}")
            try:
                self.after(0, _apply)
            except Exception:
                pass
        threading.Thread(target=_work, daemon=True).start()
    
    def _create_left_panel(self, parent):
        """建立左側控制面板 (v4.5.18 標準金融字型版)"""
        # 使用 PanedWindow 讓上下區域可調整高度
        paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # === 上半部：功能分頁區 ===
        top_frame = ttk.Frame(paned)
        paned.add(top_frame, weight=2)  # 權重2
        
        # 建立分頁（不使用表情符號）
        self.left_notebook = ttk.Notebook(top_frame)
        self.left_notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # [分頁1] 個股分析
        stock_tab = ttk.Frame(self.left_notebook, padding=5)
        self.left_notebook.add(stock_tab, text="Analysis")
        self._build_stock_analysis_ui(stock_tab)
        
        # [分頁2] 熱門題材 (Trend Scanner)
        trend_tab = ttk.Frame(self.left_notebook, padding=5)
        self.left_notebook.add(trend_tab, text="Sectors")
        self._build_trend_scanner_ui(trend_tab)

        # === 下半部：自選股清單 (升級版，不使用表情符號) ===
        watchlist_frame = ttk.LabelFrame(paned, text="[Watchlist] by Industry", padding=5)
        paned.add(watchlist_frame, weight=3)  # 權重3，給予更多空間
        
        # 工具列（使用文字按鈕，不用表情符號）
        tool_frame = ttk.Frame(watchlist_frame)
        tool_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(tool_frame, text="+Add", command=self.add_to_watchlist, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="-Del", command=self.remove_from_watchlist, width=5).pack(side=tk.LEFT, padx=2)
        ttk.Button(tool_frame, text="Scan", command=self.refresh_all_watchlist_analysis, width=5).pack(side=tk.LEFT, padx=2)
        
        # 排序按鈕
        ttk.Separator(tool_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)
        ttk.Button(tool_frame, text="Up", command=self.move_watchlist_up, width=3).pack(side=tk.LEFT)
        ttk.Button(tool_frame, text="Dn", command=self.move_watchlist_down, width=3).pack(side=tk.LEFT)
        ttk.Button(tool_frame, text="Top", command=self.move_watchlist_to_top, width=3).pack(side=tk.LEFT, padx=1)
        ttk.Button(tool_frame, text="Bot", command=self.move_watchlist_to_bottom, width=3).pack(side=tk.LEFT, padx=1)
        
        # 刷新進度標籤
        self.watchlist_progress_label = ttk.Label(tool_frame, text="", foreground="gray")
        self.watchlist_progress_label.pack(side=tk.RIGHT, padx=5)
        
        self.watchlist_count_label = ttk.Label(tool_frame, text="0/100", foreground="blue")
        self.watchlist_count_label.pack(side=tk.RIGHT, padx=5)

        # 排序選項
        sort_frame = ttk.Frame(watchlist_frame)
        sort_frame.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Label(sort_frame, text="排序：").pack(side=tk.LEFT)
        self.watchlist_sort_var = tk.StringVar(value='industry')  # 預設按族群
        sort_options = [
            ('族群', 'industry'),
            ('自訂', 'sort_order'),
            ('代碼', 'symbol'),
            ('建議', 'recommendation')
        ]
        for text, value in sort_options:
            ttk.Radiobutton(sort_frame, text=text, variable=self.watchlist_sort_var, 
                           value=value, command=self.refresh_watchlist).pack(side=tk.LEFT, padx=3)

        # ★ 樹狀列表 (支援族群分組)
        tree_frame = ttk.Frame(watchlist_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.watchlist_tree = ttk.Treeview(
            tree_frame, 
            columns=("name", "score", "signal"), 
            show="tree headings", 
            height=10
        )
        
        # 定義欄位 (第一欄 #0 為樹狀結構)
        self.watchlist_tree.heading("#0", text="族群 / 代碼", anchor="w")
        self.watchlist_tree.heading("name", text="名稱", anchor="w")
        self.watchlist_tree.heading("score", text="評分", anchor="center")
        self.watchlist_tree.heading("signal", text="量化建議", anchor="center")
        
        # stretch=False：欄位不自動撐滿視窗，總寬可溢出 → 橫向卷軸才拉得動
        self.watchlist_tree.column("#0", width=120, minwidth=90, stretch=False)
        self.watchlist_tree.column("name", width=66, minwidth=50, stretch=False)
        self.watchlist_tree.column("score", width=50, minwidth=40, anchor="e", stretch=False)     # 數字右對齊
        self.watchlist_tree.column("signal", width=240, minwidth=140, anchor="w", stretch=False)  # 加寬，建議看得完整
        
        # 設定顏色：建立時即套用主題（深色終端 + 紅漲綠跌 token）
        if getattr(self, '_theme', None) is not None:
            self._theme.style_treeview(self.watchlist_tree)
        else:
            self.watchlist_tree.tag_configure("group", background="#E0E0E0", foreground="#2C3E50", font=("Arial", 10, "bold"))
            # fix_07 任務6：動作語意色（買=橘 ACTION_BUY / 賣=綠 ACTION_SELL / 中性=灰）
            import theme as _thm
            self.watchlist_tree.tag_configure("buy", foreground=_thm.ACTION_BUY)
            self.watchlist_tree.tag_configure("hold", foreground=_thm.ACTION_NEUTRAL)
            self.watchlist_tree.tag_configure("sell", foreground=_thm.ACTION_SELL)
            self.watchlist_tree.tag_configure("wait", foreground=_thm.ACTION_NEUTRAL)
            self.watchlist_tree.tag_configure("hot", background="#FFEBEE")
            self.watchlist_tree.tag_configure("cold", background="#E8F5E9")
        
        # 滾動條
        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.watchlist_tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.watchlist_tree.xview)
        self.watchlist_tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        self.watchlist_tree.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        self.watchlist_tree.bind('<Double-1>', self.on_watchlist_double_click)
        
        # 用於記錄排序方向
        self._watchlist_sort_reverse = {}
        
        # 版本資訊（標準金融字型）
        info_frame = ttk.Frame(watchlist_frame)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text="v4.5.18 | Industry Groups | Quant Score", 
                 font=("Consolas", 8), foreground="#666666").pack()
    
    def _build_stock_analysis_ui(self, parent):
        """建立個股分析的 UI 內容（v4.5.18 標準金融字型版）"""
        # 標題區（含功能按鈕，不使用表情符號）
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(header_frame, text="Symbol:").pack(side=tk.LEFT)
        
        # 功能按鈕（不使用表情符號）
        ttk.Button(header_frame, text="Rank", 
                  command=self._show_market_ranking, width=5).pack(side=tk.RIGHT)
        ttk.Button(header_frame, text="Order", 
                  command=self._show_order_dialog, width=5).pack(side=tk.RIGHT, padx=2)
        ttk.Button(header_frame, text="Auto", 
                  command=self._show_auto_trader, width=5).pack(side=tk.RIGHT, padx=2)
        
        # 輸入框
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, pady=5)
        
        self.symbol_entry = ttk.Entry(input_frame, font=("Consolas", 11))
        self.symbol_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.symbol_entry.bind('<Return>', lambda e: self.plot_chart())
        
        ttk.Button(input_frame, text="Query", command=self.plot_chart, width=6,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(5, 0))
        
        # 市場選擇
        market_frame = ttk.Frame(parent)
        market_frame.pack(fill=tk.X, pady=3)
        
        ttk.Label(market_frame, text="Market:").pack(side=tk.LEFT)
        self.market_var = tk.StringVar(value="台股")
        ttk.Radiobutton(market_frame, text="TW", variable=self.market_var, value="台股").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(market_frame, text="US", variable=self.market_var, value="美股").pack(side=tk.LEFT)
        
        # 週期選擇（水平排列節省空間）
        period_frame = ttk.Frame(parent)
        period_frame.pack(fill=tk.X, pady=3)
        
        ttk.Label(period_frame, text="Period:").pack(side=tk.LEFT)
        self.period_var = tk.StringVar(value="6mo")
        periods = [("1M", "1mo"), ("3M", "3mo"), ("6M", "6mo"), ("1Y", "1y")]
        for text, value in periods:
            ttk.Radiobutton(period_frame, text=text, variable=self.period_var, 
                          value=value, command=self.plot_chart).pack(side=tk.LEFT, padx=2)
        
        # 初始化圖表選項變數
        self.indicator_var = tk.StringVar(value="KD")
        self.show_ma_var = tk.BooleanVar(value=True)
        self.show_vol_var = tk.BooleanVar(value=True)
        self.show_bb_var = tk.BooleanVar(value=False)
        
        # 策略回測區（不使用表情符號）
        strategy_frame = ttk.LabelFrame(parent, text="[Backtest]", padding=5)
        strategy_frame.pack(fill=tk.X, pady=5)
        
        # 策略選擇
        strategy_row = ttk.Frame(strategy_frame)
        strategy_row.pack(fill=tk.X)
        ttk.Label(strategy_row, text="Strategy:").pack(side=tk.LEFT)
        self.strategy_var = tk.StringVar(value="趨勢策略")
        strategies = ["趨勢策略", "動能策略", "通道策略", "均值回歸策略"]
        strategy_combo = ttk.Combobox(strategy_row, textvariable=self.strategy_var, 
                                     values=strategies, state="readonly", width=12)
        strategy_combo.pack(side=tk.LEFT, padx=5)
        
        # 滑價設定
        ttk.Label(strategy_row, text="Slip%:").pack(side=tk.LEFT, padx=(10, 0))
        self.slippage_var = tk.DoubleVar(value=0.3)
        ttk.Spinbox(strategy_row, from_=0, to=5, increment=0.1,
                   textvariable=self.slippage_var, width=5).pack(side=tk.LEFT, padx=2)
        
        # 按鈕列
        btn_frame = ttk.Frame(strategy_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Backtest", command=self.run_backtest, width=8,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Report", command=self.show_analysis_report, width=8).pack(side=tk.LEFT, padx=2)
        
        # 歷史分析日期（不使用表情符號）
        date_frame = ttk.Frame(strategy_frame)
        date_frame.pack(fill=tk.X, pady=3)
        
        ttk.Label(date_frame, text="Date:").pack(side=tk.LEFT)
        self.analysis_date_mode = tk.StringVar(value="today")
        ttk.Radiobutton(date_frame, text="Today", variable=self.analysis_date_mode, 
                       value="today", command=self._toggle_date_entry).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(date_frame, text="Custom", variable=self.analysis_date_mode,
                       value="custom", command=self._toggle_date_entry).pack(side=tk.LEFT, padx=2)
        
        self.analysis_date_var = tk.StringVar(value=datetime.datetime.now().strftime('%Y-%m-%d'))
        self.analysis_date_entry = ttk.Entry(date_frame, textvariable=self.analysis_date_var, width=10, state='disabled')
        self.analysis_date_entry.pack(side=tk.LEFT, padx=3)
        
        self.date_picker_btn = ttk.Button(date_frame, text="...", width=3, 
                                          command=self._show_date_picker, state='disabled')
        self.date_picker_btn.pack(side=tk.LEFT)
    
    def _build_trend_scanner_ui(self, parent):
        """建立熱門題材掃描的 UI（v4.5.18 標準金融字型版）"""
        # 強勢族群區塊（不使用表情符號）
        sector_frame = ttk.LabelFrame(parent, text="[Hot Sectors] 5D Momentum", padding=5)
        sector_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # 族群列表
        self.sector_tree = ttk.Treeview(sector_frame,
            columns=("momentum", "category", "leader"),
            show="tree headings",
            height=6
        )
        self.sector_tree.heading("#0", text="Sector")
        self.sector_tree.heading("momentum", text="5D%")
        self.sector_tree.heading("category", text="Type")
        self.sector_tree.heading("leader", text="Leader")
        
        self.sector_tree.column("#0", width=90)
        self.sector_tree.column("momentum", width=65)
        self.sector_tree.column("category", width=55)
        self.sector_tree.column("leader", width=90)
        
        # 顏色標籤（套用主題；hot/warm/cool 為動能強弱）
        if getattr(self, '_theme', None) is not None:
            self._theme.style_treeview(self.sector_tree)
            self.sector_tree.tag_configure("hot",  foreground=self._theme.UP)
            self.sector_tree.tag_configure("warm", foreground=self._theme.ACCENT)
            self.sector_tree.tag_configure("cool", foreground=self._theme.TEXT_2)
        else:
            self.sector_tree.tag_configure("hot", foreground="#FF4444")
            self.sector_tree.tag_configure("warm", foreground="#FF8800")
            self.sector_tree.tag_configure("cool", foreground="#4488FF")

        self.sector_tree.pack(fill=tk.BOTH, expand=True)
        self.sector_tree.bind('<<TreeviewSelect>>', self._on_sector_select)
        
        # 領頭羊區塊（不使用表情符號）
        leader_frame = ttk.LabelFrame(parent, text="[Constituents]", padding=5)
        leader_frame.pack(fill=tk.BOTH, expand=True)
        
        self.leader_tree = ttk.Treeview(leader_frame,
            columns=("price", "change"),
            show="tree headings",
            height=5
        )
        self.leader_tree.heading("#0", text="Stock")
        self.leader_tree.heading("price", text="Price")
        self.leader_tree.heading("change", text="Chg%")
        
        self.leader_tree.column("#0", width=110)
        self.leader_tree.column("price", width=70, anchor="e")    # 數字右對齊
        self.leader_tree.column("change", width=60, anchor="e")   # 數字右對齊
        
        # 套用主題（up/down 紅漲綠跌走 token）
        if getattr(self, '_theme', None) is not None:
            self._theme.style_treeview(self.leader_tree)
        else:
            self.leader_tree.tag_configure("up", foreground="#FF4444")
            self.leader_tree.tag_configure("down", foreground="#44FF44")

        self.leader_tree.pack(fill=tk.BOTH, expand=True)
        self.leader_tree.bind('<Double-1>', self._on_leader_double_click)
        
        # 控制按鈕（不使用表情符號）
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="Refresh", 
                  command=self._refresh_market_trends, width=10).pack(side=tk.LEFT, padx=2)
        
        # 狀態標籤
        self.sector_status_label = ttk.Label(btn_frame, text="點擊「重新整理」載入數據", foreground="gray")
        self.sector_status_label.pack(side=tk.RIGHT)
        
        # 初始化 MarketTrendManager
        self._market_manager = None
        if TREND_SCANNER_AVAILABLE:
            try:
                self._market_manager = MarketTrendManager()
            except Exception as e:
                print(f"[TrendScanner] 初始化失敗: {e}")
    
    def _on_sector_select(self, event):
        """當選擇族群時，載入成分股"""
        selection = self.sector_tree.selection()
        if not selection:
            return
        
        sector_id = selection[0]
        
        def load_constituents():
            if self._market_manager:
                try:
                    stocks = self._market_manager.get_sector_constituents(sector_id)
                    self.after(0, lambda: self._update_leader_tree(stocks))
                except Exception as e:
                    print(f"[TrendScanner] 載入成分股失敗: {e}")
        
        # 在背景線程中載入
        import threading
        threading.Thread(target=load_constituents, daemon=True).start()
    
    def _on_leader_double_click(self, event):
        """雙擊領頭羊股票，載入到主圖表"""
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
        """重新整理市場熱點數據"""
        if not self._market_manager:
            self.sector_status_label.config(text="模組未載入")
            return
        
        self.sector_status_label.config(text="載入中...")
        
        def load_sectors():
            try:
                sectors = self._market_manager.get_hot_sectors(limit=12, force_refresh=True)
                self.after(0, lambda: self._update_sector_tree(sectors))
                self.after(0, lambda: self.sector_status_label.config(
                    text=f"更新: {datetime.datetime.now().strftime('%H:%M:%S')}"
                ))
            except Exception as e:
                # 修正：先抽出訊息字串，避免 lambda 延遲執行時 except 變數 e 已被刪除
                _err_text = f"錯誤: {str(e)[:15]}"
                self.after(0, lambda: self.sector_status_label.config(text=_err_text))
        
        import threading
        threading.Thread(target=load_sectors, daemon=True).start()
    
    def _update_sector_tree(self, sectors):
        """更新族群列表"""
        # 清空現有項目
        for item in self.sector_tree.get_children():
            self.sector_tree.delete(item)
        
        # 新增項目
        for sector in sectors:
            momentum = getattr(sector, 'momentum_5d', 0) or 0
            
            # 決定顏色標籤
            if momentum >= 5:
                tag = "hot"
            elif momentum >= 2:
                tag = "warm"
            else:
                tag = "cool"
            
            leader_text = f"{getattr(sector, 'leader_symbol', '')} {getattr(sector, 'leader_name', '')}"
            
            self.sector_tree.insert("", "end",
                iid=getattr(sector, 'sector_id', ''),
                text=getattr(sector, 'sector_name', ''),
                values=(
                    f"{momentum:+.1f}%",
                    getattr(sector, 'category', ''),
                    leader_text.strip()
                ),
                tags=(tag,)
            )
    
    def _update_leader_tree(self, stocks):
        """更新領頭羊列表"""
        # 清空現有項目
        for item in self.leader_tree.get_children():
            self.leader_tree.delete(item)
        
        # 新增項目
        for stock in stocks:
            change_pct = getattr(stock, 'change_pct', 0) or 0
            tag = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
            
            self.leader_tree.insert("", "end",
                text=f"{getattr(stock, 'symbol', '')} {getattr(stock, 'name', '')}",
                values=(
                    f"${getattr(stock, 'price', 0):.2f}",
                    f"{change_pct:+.2f}%"
                ),
                tags=(tag,)
            )
    
    def _create_right_panel(self, parent):
        """建立右側圖表區域"""
        # 圖表選項
        options_frame = ttk.Frame(parent)
        options_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Checkbutton(options_frame, text="顯示均線", variable=self.show_ma_var,
                       command=self.plot_chart).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(options_frame, text="顯示成交量", variable=self.show_vol_var,
                       command=self.plot_chart).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(options_frame, text="顯示布林通道", variable=self.show_bb_var,
                       command=self.plot_chart).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(options_frame, text="副圖指標：").pack(side=tk.LEFT, padx=(20, 5))
        indicators = ["KD", "MACD", "RSI"]
        indicator_combo = ttk.Combobox(options_frame, textvariable=self.indicator_var,
                                      values=indicators, state="readonly", width=10)
        indicator_combo.pack(side=tk.LEFT)
        indicator_combo.bind('<<ComboboxSelected>>', lambda e: self.update_indicator())
        
        # 主圖表區域
        self.main_chart_frame = ttk.Frame(parent)
        self.main_chart_frame.pack(fill=tk.BOTH, expand=True)
        
        # 副圖表區域
        self.lower_chart_frame = ttk.Frame(parent, height=200)
        self.lower_chart_frame.pack(fill=tk.X, pady=(5, 0))
        self.lower_chart_frame.pack_propagate(False)
    
    def plot_chart(self):
        """繪製股票圖表"""
        symbol = self.symbol_entry.get().strip()
        if not symbol:
            return
        
        market = self.market_var.get()
        period = self.period_var.get()
        
        name = symbol
        
        if market == "台股":
            # 先嘗試上市 (.TW)
            ticker_symbol = f"{symbol}.TW"
            if symbol.isdigit():
                try:
                    name = f"{symbol} {twstock.codes[symbol].name}"
                except:
                    name = symbol
        else:
            ticker_symbol = symbol
        
        try:
            stock = yf.Ticker(ticker_symbol)
            self.df = stock.history(period=period)
            
            # 如果上市沒數據，嘗試上櫃 (.TWO)
            if self.df.empty and market == "台股":
                ticker_symbol = f"{symbol}.TWO"
                stock = yf.Ticker(ticker_symbol)
                self.df = stock.history(period=period)
            
            if self.df.empty:
                messagebox.showerror("錯誤", "無法取得股票資料，請確認代碼是否正確")
                return
            
            self.current_symbol = symbol
            
            # 清除舊圖表
            for widget in self.main_chart_frame.winfo_children():
                widget.destroy()
            
            # v4.3 新增：嘗試爬取即時股價
            realtime_data = None
            if market == "台股":
                realtime_data = RealtimePriceFetcher.get_realtime_price(symbol, market)
            
            # 取得昨收價（日期對齊；與分析報告共用同一邏輯確保漲跌幅一致）
            prev_close = QuickAnalyzer.aligned_prev_close(self.df)
            if prev_close is None:
                prev_close = self.df['Close'].iloc[-1]

            # 使用即時股價或 yfinance 數據
            if realtime_data and realtime_data.get('price'):
                current_price = realtime_data['price']
                # 即時報價若提供同源昨收則優先用（與分析報告一致）
                _rt_prev = realtime_data.get('prev_close')
                if _rt_prev and _rt_prev > 0:
                    prev_close = _rt_prev
                price_change = current_price - prev_close
                price_change_pct = (price_change / prev_close * 100) if prev_close != 0 else 0
                update_time = f"即時 {realtime_data.get('time', '')}"
                price_source = 'yahoo_scrape'
            else:
                # Fallback 到 yfinance 數據
                current_price = self.df['Close'].iloc[-1]
                price_change = current_price - prev_close
                price_change_pct = (price_change / prev_close * 100) if prev_close != 0 else 0
                update_time = self.df.index[-1].strftime('%Y-%m-%d %H:%M')
                price_source = 'yfinance'
            
            # v4.1 新增：在圖表上方顯示股價資訊
            price_info_frame = ttk.Frame(self.main_chart_frame)
            price_info_frame.pack(fill=tk.X, pady=(0, 5))
            
            # 股票名稱和代碼（優先使用 twstock 名稱）
            ttk.Label(price_info_frame, text=f"📈 {name}", 
                     font=("SimHei", 14, "bold")).pack(side=tk.LEFT, padx=5)
            
            # 當前價格（標註來源）
            source_icon = "⚡" if price_source == 'yahoo_scrape' else "📊"
            ttk.Label(price_info_frame, text=f"{source_icon} 現價: ${current_price:.2f}", 
                     font=("SimHei", 12, "bold")).pack(side=tk.LEFT, padx=10)
            
            # 漲跌幅（台股紅漲綠跌，走 theme token）
            _th = getattr(self, '_theme', None)
            _UP   = _th.UP   if _th else "red"
            _DOWN = _th.DOWN if _th else "green"
            _FLAT = _th.FLAT if _th else "gray"
            if price_change > 0:
                change_text = f"▲ {price_change:.2f} (+{price_change_pct:.2f}%)"
                change_color = _UP
            elif price_change < 0:
                change_text = f"▼ {abs(price_change):.2f} ({price_change_pct:.2f}%)"
                change_color = _DOWN
            else:
                change_text = f"－ 0.00 (0.00%)"
                change_color = _FLAT
            
            change_label = ttk.Label(price_info_frame, text=change_text, 
                                    font=("SimHei", 12, "bold"), foreground=change_color)
            change_label.pack(side=tk.LEFT, padx=5)
            
            # 昨收價
            ttk.Label(price_info_frame, text=f"昨收: ${prev_close:.2f}", 
                     font=("SimHei", 10)).pack(side=tk.LEFT, padx=10)
            
            # 更新時間
            ttk.Label(price_info_frame, text=f"更新: {update_time}", 
                     font=("SimHei", 9), foreground="gray").pack(side=tk.RIGHT, padx=5)
            
            # 設定均線
            mav = ()
            if self.show_ma_var.get():
                mav = (5, 20, 60)
            
            # 設定樣式（暗色面板 + 紅漲綠跌；走 theme，失敗則退回原淺色樣式）
            if getattr(self, '_theme', None) is not None:
                try:
                    mc, s = self._theme.mpf_market_style()
                except Exception:
                    mc = mpf.make_marketcolors(up='red', down='green', edge='black', wick='black', volume='inherit')
                    s = mpf.make_mpf_style(marketcolors=mc, gridcolor='lightgray', gridstyle='--',
                        rc={'font.sans-serif': ['SimHei', 'Microsoft JhengHei', 'PingFang SC', 'Heiti TC', 'Arial Unicode MS']})
            else:
                mc = mpf.make_marketcolors(up='red', down='green', edge='black', wick='black', volume='inherit')
                s = mpf.make_mpf_style(marketcolors=mc, gridcolor='lightgray', gridstyle='--',
                    rc={'font.sans-serif': ['SimHei', 'Microsoft JhengHei', 'PingFang SC', 'Heiti TC', 'Arial Unicode MS']})
            
            # 繪製蠟燭圖
            add_plots = []

            # 訊號標記/布林通道顏色（走 theme token，與紅漲綠跌 K 棒區隔）
            _th = getattr(self, '_theme', None)
            _boll_c = _th.BOLL_COLOR if _th else 'purple'
            _buy_c  = _th.SIGNAL_BUY_COLOR if _th else 'lime'
            _sell_c = _th.SIGNAL_SELL_COLOR if _th else 'red'

            if self.show_bb_var.get():
                sma, upper, lower = calculate_bollinger_bands(self.df['Close'])
                add_plots.append(mpf.make_addplot(upper, color=_boll_c, linestyle='--'))
                add_plots.append(mpf.make_addplot(lower, color=_boll_c, linestyle='--'))

            # ============================================================
            # v4.4.3 新增：買賣點視覺化 (Signal Visualization)
            # ============================================================
            try:
                buy_signals, sell_signals = self._detect_signals_for_chart(self.df)

                # 買進訊號：K 棒下方向上三角（琥珀，中性、不與紅綠 K 棒衝突）
                if buy_signals is not None and buy_signals.notna().any():
                    add_plots.append(mpf.make_addplot(
                        buy_signals,
                        type='scatter',
                        markersize=100,
                        marker='^',
                        color=_buy_c
                    ))

                # 賣出訊號：K 棒上方向下三角（藍）
                if sell_signals is not None and sell_signals.notna().any():
                    add_plots.append(mpf.make_addplot(
                        sell_signals,
                        type='scatter',
                        markersize=100,
                        marker='v',
                        color=_sell_c
                    ))
            except Exception as e:
                print(f"買賣點視覺化錯誤: {e}")
            
            # 構建繪圖參數（避免 addplot=None 錯誤）
            plot_kwargs = {
                'type': 'candle',
                'style': s,
                'title': f'{name} K線圖',
                'mav': mav,
                'volume': self.show_vol_var.get(),
                'figsize': (10, 6),
                'returnfig': True
            }
            
            # 只有在有附加圖形時才加入 addplot 參數
            if add_plots:
                plot_kwargs['addplot'] = add_plots
            
            fig, axes = mpf.plot(self.df, **plot_kwargs)
            
            canvas = FigureCanvasTkAgg(fig, master=self.main_chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            plt.close(fig)
            
            # 更新副圖
            self.update_indicator()
            
        except Exception as e:
            messagebox.showerror("錯誤", f"繪製圖表失敗：{str(e)}")
    
    def _detect_signals_for_chart(self, df):
        """
        v4.5.15 效能優化：完全向量化訊號偵測
        
        原本使用 for 迴圈逐一檢查每根 K 棒，複雜度 O(N)
        優化後使用 pandas 向量化運算，速度提升 50-100 倍
        
        偵測以下訊號：
        - 買進訊號：三盤突破、左側買訊（超跌反彈）、黃金買點條件
        - 賣出訊號：三盤跌破、左側賣訊（過熱回檔）、放量跌破
        
        Returns:
            tuple: (buy_signals, sell_signals) - 兩個 Series，非訊號位置為 NaN
        """
        import pandas as pd
        import numpy as np
        
        if df is None or len(df) < 60:
            return None, None
        
        try:
            # ============================================================
            # Step 1: 預計算所有技術指標（向量化）
            # ============================================================
            ma5 = df['Close'].rolling(5).mean()
            ma20 = df['Close'].rolling(20).mean()
            ma55 = df['Close'].rolling(55).mean()
            
            # RSI（Wilder，共用 analyzers.wilder_rsi）
            from analyzers import wilder_rsi
            rsi = wilder_rsi(df['Close'], 14)

            # 乖離率
            bias_20 = ((df['Close'] - ma20) / ma20 * 100).fillna(0)
            
            # 成交量
            vol_ma20 = df['Volume'].rolling(20).mean()
            vol_ratio = df['Volume'] / vol_ma20
            
            # 近期高低點
            high_20 = df['High'].rolling(20).max()
            low_20 = df['Low'].rolling(20).min()
            
            # ============================================================
            # Step 2: 向量化計算所有條件
            # ============================================================
            close = df['Close']
            open_price = df['Open']
            low = df['Low']
            high = df['High']
            
            # 通用濾網：高檔爆量收黑（主力出貨跡象）
            is_distribution_bar = (vol_ratio > 2.5) & (close < open_price)
            
            # ============================================================
            # 買進訊號向量化計算
            # ============================================================
            
            # 條件1：三盤突破（連續3天收在 MA55 之上，且突破前高）
            above_ma55_today = close > ma55
            above_ma55_1 = close.shift(1) > ma55.shift(1)
            above_ma55_2 = close.shift(2) > ma55.shift(2)
            above_ma55_3days = above_ma55_today & above_ma55_1 & above_ma55_2
            breakout_high = close > high_20.shift(1)
            buy_cond1 = above_ma55_3days & breakout_high & ~is_distribution_bar
            
            # 條件2：左側買訊（超跌反彈）- 乖離 < -10% 且 RSI < 30
            buy_cond2 = (bias_20 < QuantConfig.BIAS_OVERSOLD_THRESHOLD) & (rsi < 30)
            
            # 條件3：黃金買點 - 多頭趨勢 + 乖離回到 -5%~2% + RSI < 60
            is_bull = (ma5 > ma20) & (close > ma20)
            golden_bias = (bias_20 >= QuantConfig.GOLDEN_BUY_BIAS_MIN) & (bias_20 <= QuantConfig.GOLDEN_BUY_BIAS_MAX)
            golden_rsi = rsi < QuantConfig.GOLDEN_BUY_RSI_MAX
            buy_cond3 = is_bull & golden_bias & golden_rsi & ~is_distribution_bar
            
            # 合併買進訊號
            buy_signal_mask = buy_cond1 | buy_cond2 | buy_cond3
            
            # ============================================================
            # 賣出訊號向量化計算
            # ============================================================
            
            # 條件1：三盤跌破（連續3天收在 MA55 之下，且跌破前低）
            below_ma55_today = close < ma55
            below_ma55_1 = close.shift(1) < ma55.shift(1)
            below_ma55_2 = close.shift(2) < ma55.shift(2)
            below_ma55_3days = below_ma55_today & below_ma55_1 & below_ma55_2
            breakdown_low = close < low_20.shift(1)
            sell_cond1 = below_ma55_3days & breakdown_low
            
            # 條件2：左側賣訊（過熱回檔）- 乖離 > 15% 且 RSI > 75
            sell_cond2 = (bias_20 > QuantConfig.BIAS_OVERBOUGHT_THRESHOLD) & (rsi > 75)
            
            # 條件3：放量跌破 - 跌破 MA20 且成交量 > 2 倍均量
            sell_cond3 = (close < ma20) & (vol_ratio > 2.0)
            
            # 合併賣出訊號
            sell_signal_mask = sell_cond1 | sell_cond2 | sell_cond3
            
            # ============================================================
            # Step 3: 生成訊號 Series
            # ============================================================
            # 初始化為 NaN
            buy_signals = pd.Series(index=df.index, dtype=float)
            sell_signals = pd.Series(index=df.index, dtype=float)
            
            # 標記買進訊號（在 K 棒低點下方 2%）
            buy_signals[buy_signal_mask] = low[buy_signal_mask] * 0.98
            
            # 標記賣出訊號（在 K 棒高點上方 2%）
            sell_signals[sell_signal_mask] = high[sell_signal_mask] * 1.02
            
            # 過濾掉前 55 天（指標不穩定）
            buy_signals.iloc[:55] = np.nan
            sell_signals.iloc[:55] = np.nan
            
            return buy_signals, sell_signals
            
        except Exception as e:
            print(f"訊號偵測錯誤: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def update_indicator(self):
        """更新副圖指標"""
        if self.df is None:
            return
        
        # 清除舊圖表
        for widget in self.lower_chart_frame.winfo_children():
            widget.destroy()
        
        indicator = self.indicator_var.get()
        
        fig_indicator, ax_indicator = plt.subplots(figsize=(10, 2.5))
        
        if indicator == "KD":
            k, d = calculate_kd(self.df)
            ax_indicator.plot(k.index, k, label="K", color='blue', linewidth=1.5)
            ax_indicator.plot(d.index, d, label="D", color='orange', linewidth=1.5)
            ax_indicator.set_title("KD 隨機指標", fontproperties=zh_font, fontsize=11, fontweight='bold')
            ax_indicator.axhline(80, color='red', linestyle='--', alpha=0.7)
            ax_indicator.axhline(20, color='green', linestyle='--', alpha=0.7)
            ax_indicator.set_ylim(0, 100)
            ax_indicator.legend(loc='upper left')
            ax_indicator.grid(True, alpha=0.3)
            
        elif indicator == "MACD":
            macd_line, signal_line, hist = calculate_macd(self.df['Close'])
            hist_colors = ['red' if v >= 0 else 'green' for v in hist]
            ax_indicator.plot(macd_line.index, macd_line, label="MACD", linewidth=1.5)
            ax_indicator.plot(signal_line.index, signal_line, label="Signal", linewidth=1.5)
            ax_indicator.bar(hist.index, hist, label="Histogram", color=hist_colors, alpha=0.6)
            ax_indicator.set_title("MACD 指標", fontproperties=zh_font, fontsize=11, fontweight='bold')
            ax_indicator.legend(loc='upper left')
            ax_indicator.grid(True, alpha=0.3)
            ax_indicator.axhline(0, color='black', linewidth=0.8)
            
        elif indicator == "RSI":
            rsi = calculate_rsi(self.df['Close'])
            ax_indicator.plot(rsi.index, rsi, label="RSI(14)", linewidth=1.5, color='purple')
            ax_indicator.axhline(70, color='red', linestyle='--', alpha=0.7)
            ax_indicator.axhline(30, color='green', linestyle='--', alpha=0.7)
            ax_indicator.set_ylim(0, 100)
            ax_indicator.set_title("RSI 指標", fontproperties=zh_font, fontsize=11, fontweight='bold')
            ax_indicator.legend(loc='upper left')
            ax_indicator.grid(True, alpha=0.3)
        
        ax_indicator.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax_indicator.tick_params(axis='x', rotation=30)
        
        fig_indicator.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig_indicator, master=self.lower_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        plt.close(fig_indicator)
    
    def run_backtest(self):
        """執行策略回測"""
        if self.df is None or self.current_symbol is None:
            messagebox.showwarning("警告", "請先查詢股票")
            return
        
        strategy = self.strategy_var.get()
        
        try:
            slippage_pct = self.slippage_var.get()
            if slippage_pct < 0 or slippage_pct > 5:
                messagebox.showwarning("警告", "滑價應在0-5%之間")
                return
        except:
            slippage_pct = 0.3
        
        if strategy == "趨勢策略":
            results = BacktestEngine.backtest_trend_strategy(self.df, slippage_pct=slippage_pct)
        elif strategy == "動能策略":
            results = BacktestEngine.backtest_momentum_strategy(self.df, slippage_pct=slippage_pct)
        elif strategy == "通道策略":
            results = BacktestEngine.backtest_channel_strategy(self.df, slippage_pct=slippage_pct)
        elif strategy == "均值回歸策略":
            results = BacktestEngine.backtest_mean_reversion_strategy(self.df, slippage_pct=slippage_pct)
        else:
            messagebox.showinfo("提示", "該策略尚未實作")
            return
        
        BacktestDialog(self, self.current_symbol, strategy, results)
    
    def show_analysis_report(self):
        """顯示完整分析報告（支援歷史日期）"""
        symbol = self.symbol_entry.get().strip()
        if not symbol:
            messagebox.showwarning("警告", "請先輸入股票代碼")
            return
        
        # v4.4.7：檢查熔斷狀態
        if YFinanceRateLimiter.is_circuit_breaker_active():
            remaining = YFinanceRateLimiter.get_circuit_breaker_remaining()
            stats = YFinanceRateLimiter.get_stats()
            messagebox.showwarning(
                "YFinance 暫時鎖定",
                f"Yahoo Finance API 目前被鎖定\n"
                f"請等待 {remaining} 秒後再試\n\n"
                f"統計：請求 {stats['total_requests']} 次，失敗 {stats['failures']} 次\n\n"
                f"建議：等待幾分鐘後重試，或減少分析頻率"
            )
            return
        
        market = self.market_var.get()
        
        # v4.3：檢查是否選擇了歷史日期
        analysis_date = None
        date_str = "今天"
        
        if hasattr(self, 'analysis_date_mode') and self.analysis_date_mode.get() == "custom":
            try:
                analysis_date = datetime.datetime.strptime(self.analysis_date_var.get(), '%Y-%m-%d')
                if analysis_date.date() >= datetime.datetime.now().date():
                    # 選擇的日期是今天或未來，使用即時分析
                    analysis_date = None
                else:
                    date_str = self.analysis_date_var.get()
            except ValueError:
                analysis_date = None
        
        # 顯示載入中訊息
        loading = tk.Toplevel(self)
        loading.title("分析中" if analysis_date is None else "歷史分析中")
        loading.geometry("350x100")
        ttk.Label(loading, text=f"正在分析 {symbol} ({date_str})...", font=("Arial", 12)).pack(expand=True)
        loading.update()
        
        try:
            # 統一使用 analyze_stock，傳入 analysis_date 參數
            result = QuickAnalyzer.analyze_stock(symbol, market, analysis_date)
            loading.destroy()
            
            if result:
                # v4.3.6 新增：儲存最後分析結果供下單視窗使用
                result['symbol'] = symbol
                self.last_analysis_result = result
                
                # 即時分析才儲存到資料庫
                if analysis_date is None:
                    try:
                        rec = result['recommendation']
                        if isinstance(rec, dict):
                            # v4.3：存儲更多信息（用 | 分隔）
                            overall = rec.get('overall', '待分析')
                            scenario = rec.get('scenario_name', '')
                            short_term = rec.get('short_term', {})
                            short_action = short_term.get('action', '') if isinstance(short_term, dict) else ''
                            timing = rec.get('action_timing', '')
                            recommendation_str = f"{overall}|{scenario}|{short_action}|{timing}"
                        else:
                            recommendation_str = str(rec)
                        
                        self.db.save_analysis(
                            symbol,
                            result['technical']['signal'],
                            result['fundamental']['signal'],
                            recommendation_str,
                            result
                        )
                        # 同步更新自選股的建議
                        self.db.update_recommendation(symbol, recommendation_str)
                        self.refresh_watchlist()
                    except Exception as e:
                        print(f"儲存分析結果錯誤: {e}")
                
                RecommendationDialog(self, result)
            else:
                # v4.4.7：檢查是否因熔斷導致失敗
                if YFinanceRateLimiter.is_circuit_breaker_active():
                    remaining = YFinanceRateLimiter.get_circuit_breaker_remaining()
                    messagebox.showerror(
                        "分析失敗 - YFinance 鎖定",
                        f"Yahoo Finance API 已被暫時鎖定\n"
                        f"請等待 {remaining} 秒後再試\n\n"
                        f"提示：這是 Yahoo 的速率限制，不是程式錯誤"
                    )
                else:
                    messagebox.showerror("錯誤", f"分析失敗，請確認股票代碼是否正確\n（日期：{date_str}）")
        except Exception as e:
            loading.destroy()
            # v4.4.7：錯誤訊息中加入熔斷狀態
            error_msg = str(e)
            if YFinanceRateLimiter.is_circuit_breaker_active():
                remaining = YFinanceRateLimiter.get_circuit_breaker_remaining()
                error_msg += f"\n\n⛔ YFinance 已觸發熔斷保護，請等待 {remaining} 秒"
            messagebox.showerror("錯誤", f"分析發生錯誤：{error_msg}")
    
    def _toggle_date_entry(self):
        """切換日期輸入框的啟用狀態"""
        if self.analysis_date_mode.get() == "custom":
            self.analysis_date_entry.config(state='normal')
            self.date_picker_btn.config(state='normal')
        else:
            self.analysis_date_entry.config(state='disabled')
            self.date_picker_btn.config(state='disabled')
    
    def _show_date_picker(self):
        """顯示簡易日期選擇器"""
        picker = tk.Toplevel(self)
        picker.title("選擇日期")
        picker.resizable(True, True)
        picker.transient(self)
        picker.grab_set()
        # 套用深色主題背景（與主視窗一致）
        if getattr(self, '_theme', None) is not None:
            try:
                picker.configure(bg=self._theme.BG_APP)
            except Exception:
                pass
        
        # 取得當前日期
        try:
            current = datetime.datetime.strptime(self.analysis_date_var.get(), '%Y-%m-%d')
        except:
            current = datetime.datetime.now()
        
        main_frame = ttk.Frame(picker, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 年份選擇
        year_frame = ttk.Frame(main_frame)
        year_frame.pack(fill=tk.X, pady=5)
        ttk.Label(year_frame, text="年份：").pack(side=tk.LEFT)
        year_var = tk.IntVar(value=current.year)
        year_spin = ttk.Spinbox(year_frame, from_=2015, to=datetime.datetime.now().year,
                               textvariable=year_var, width=8)
        year_spin.pack(side=tk.LEFT, padx=5)
        
        # 月份選擇
        month_frame = ttk.Frame(main_frame)
        month_frame.pack(fill=tk.X, pady=5)
        ttk.Label(month_frame, text="月份：").pack(side=tk.LEFT)
        month_var = tk.IntVar(value=current.month)
        month_spin = ttk.Spinbox(month_frame, from_=1, to=12,
                                textvariable=month_var, width=8)
        month_spin.pack(side=tk.LEFT, padx=5)
        
        # 日期選擇
        day_frame = ttk.Frame(main_frame)
        day_frame.pack(fill=tk.X, pady=5)
        ttk.Label(day_frame, text="日期：").pack(side=tk.LEFT)
        day_var = tk.IntVar(value=current.day)
        day_spin = ttk.Spinbox(day_frame, from_=1, to=31,
                              textvariable=day_var, width=8)
        day_spin.pack(side=tk.LEFT, padx=5)
        
        # 快速選擇按鈕
        quick_frame = ttk.Frame(main_frame)
        quick_frame.pack(fill=tk.X, pady=10)
        
        def set_days_ago(days):
            target = datetime.datetime.now() - datetime.timedelta(days=days)
            year_var.set(target.year)
            month_var.set(target.month)
            day_var.set(target.day)
        
        ttk.Button(quick_frame, text="1週前", command=lambda: set_days_ago(7), width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="1月前", command=lambda: set_days_ago(30), width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="3月前", command=lambda: set_days_ago(90), width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="6月前", command=lambda: set_days_ago(180), width=6).pack(side=tk.LEFT, padx=2)
        
        def confirm():
            try:
                selected = datetime.datetime(year_var.get(), month_var.get(), day_var.get())
                if selected > datetime.datetime.now():
                    messagebox.showwarning("警告", "不能選擇未來日期")
                    return
                self.analysis_date_var.set(selected.strftime('%Y-%m-%d'))
                picker.destroy()
            except ValueError as e:
                messagebox.showwarning("警告", f"日期無效：{e}")

        # 確認/取消按鈕（正常由上往下排，最後讓視窗自動貼合內容高度，絕不被切）
        _accent = "Accent.TButton" if getattr(self, '_theme', None) else "TButton"
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(12, 8))
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(btn_frame, text="確認", command=confirm, width=10,
                   style=_accent).pack(side=tk.LEFT, padx=20)
        ttk.Button(btn_frame, text="取消", command=picker.destroy, width=10).pack(side=tk.RIGHT, padx=20)

        # 視窗自動貼合內容高度（量實際需求 + 邊距），不再寫死尺寸而被切
        picker.update_idletasks()
        _w = max(420, picker.winfo_reqwidth() + 20)
        _h = picker.winfo_reqheight() + 20
        picker.geometry(f"{_w}x{_h}")
        picker.minsize(_w, _h)
    
    def show_historical_analysis(self):
        """執行歷史日期分析"""
        symbol = self.symbol_entry.get().strip()
        if not symbol:
            messagebox.showwarning("警告", "請先輸入股票代碼")
            return
        
        market = self.market_var.get()
        
        # 取得分析日期
        if self.analysis_date_mode.get() == "today":
            analysis_date = None  # 今天，使用即時分析
            date_str = "今天"
        else:
            try:
                analysis_date = datetime.datetime.strptime(self.analysis_date_var.get(), '%Y-%m-%d')
                if analysis_date.date() >= datetime.datetime.now().date():
                    messagebox.showwarning("警告", "歷史分析請選擇過去的日期")
                    return
                date_str = self.analysis_date_var.get()
            except ValueError:
                messagebox.showerror("錯誤", "日期格式錯誤，請使用 YYYY-MM-DD 格式")
                return
        
        # 顯示載入中訊息
        loading = tk.Toplevel(self)
        loading.title("歷史分析中")
        loading.geometry("350x120")
        ttk.Label(loading, text=f"正在分析 {symbol} 於 {date_str} 的數據...", 
                 font=("Arial", 11)).pack(expand=True, pady=10)
        ttk.Label(loading, text="⏳ 歷史分析需要較多時間，請稍候...", 
                 font=("Arial", 9)).pack(pady=5)
        loading.update()
        
        try:
            # 統一使用 analyze_stock，傳入 analysis_date 參數
            result = QuickAnalyzer.analyze_stock(symbol, market, analysis_date)
            
            loading.destroy()
            
            if result:
                RecommendationDialog(self, result)
            else:
                messagebox.showerror("錯誤", f"無法取得 {date_str} 的歷史數據\n可能該日期為非交易日或數據不存在")
        except Exception as e:
            loading.destroy()
            messagebox.showerror("錯誤", f"歷史分析發生錯誤：{str(e)}")
            import traceback
            traceback.print_exc()
    
    def refresh_all_watchlist_analysis(self):
        """
        v4.4.2 新增：批次刷新所有自選股的量化分析
        
        行為：
        1. 取得目前自選股清單
        2. 逐一執行每支股票的量化分析
        3. 每完成一支就更新 UI 狀態
        4. 全部完成後顯示結果
        """
        stocks = self.db.get_all_stocks()
        if not stocks:
            messagebox.showinfo("提示", "目前沒有自選股")
            return
        
        total = len(stocks)
        
        # 標記刷新中，防止重複觸發
        if hasattr(self, '_refreshing') and self._refreshing:
            messagebox.showinfo("提示", "正在刷新中，請稍候...")
            return
        
        # v4.4.7：檢查熔斷狀態
        if YFinanceRateLimiter.is_circuit_breaker_active():
            remaining = YFinanceRateLimiter.get_circuit_breaker_remaining()
            messagebox.showwarning(
                "YFinance 暫時鎖定",
                f"Yahoo Finance API 目前被鎖定\n請等待 {remaining} 秒後再試\n\n"
                f"建議：減少分析頻率，或等待幾分鐘後重試"
            )
            return
        
        self._refreshing = True
        self._refresh_errors = []
        
        print(f"[自選股刷新] 開始刷新 {total} 檔股票...")
        
        def analyze_in_background():
            # v4.5.13: 進入背景線程，禁用自動垃圾回收
            ThreadSafeGC.enter_background_thread()
            success_count = 0

            try:
                # B2 #1：刷新前批次預抓歷史，逐檔 get_history 命中快取
                try:
                    _tw = [s[0] for s in stocks if (s[2] if len(s) > 2 else '台股') == '台股']
                    if _tw:
                        DataSourceManager.prefetch_histories(_tw, '台股')
                        DataSourceManager.prefetch_realtime(_tw, '台股')
                except Exception as _pe:
                    print(f'[B2] 批次預抓略過: {_pe}')

                # build_prompt_03：掃描前批次補籌碼洞（daily_update），
                # 之後平行掃描過程只讀 DB、零籌碼 API 呼叫（維持 scan_mode 速度原則）。
                try:
                    _tw_syms = [s[0] for s in stocks if (s[2] if len(s) > 2 else '台股') == '台股']
                    if _tw_syms:
                        from chip_data_manager import get_chip_manager
                        _cm = get_chip_manager(self.db.db_name)
                        if not _cm.get_latest_trading_day():
                            _cm.sync_calendar()
                        _filled = _cm.daily_update(_tw_syms, holes=5)
                        print(f'[籌碼] 掃描前 daily_update 補齊 {_filled} 筆')
                except Exception as _ce:
                    print(f'[籌碼] 掃描前 daily_update 略過: {_ce}')

                # ── 平行掃描（B2 #3）：scan_mode + 批次預抓快取命中 → 可安全併發 ──
                # worker 只做分析/計算，不碰 DB/UI（執行緒安全）；DB 寫入與 UI 更新
                # 集中在主迴圈序列化（tkinter 元件非執行緒安全，UI 走 _safe_ui_update）。
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def _analyze_one(stock_data):
                    symbol = stock_data[0]; name = stock_data[1]; market = stock_data[2]
                    try:
                        result = QuickAnalyzer.analyze_stock(symbol, market, scan_mode=True)
                        if not result:
                            return {'symbol': symbol, 'ok': False, 'error': '無分析結果'}
                        quant_score = 0; trend_status = "待分析"; bias_20 = 0
                        try:
                            # fix_07 任務3：watchlist 分數單一化 = 引擎綜合分（含賣訊下修），
                            # 與報告綜合分同源，不再用雙軌分數另算。
                            quant_score = result.get('decision_matrix', {}).get('score', 50)
                            trend_status = result.get('trend', {}).get('primary_trend', '盤整') if isinstance(result.get('trend'), dict) else '待分析'
                            bias_20 = result.get('bias', {}).get('bias_20', 0) if isinstance(result.get('bias'), dict) else 0
                        except Exception as dm_err:
                            print(f"[自選股刷新] {symbol} 評分計算錯誤: {dm_err}")
                        rec = result['recommendation']
                        if isinstance(rec, dict):
                            overall = rec.get('overall', '待分析')
                            scenario = rec.get('scenario_name', '')
                            short_term = rec.get('short_term', {})
                            short_action = short_term.get('action', '') if isinstance(short_term, dict) else ''
                            timing = rec.get('action_timing', '')
                            recommendation = f"{overall}|{scenario}|{short_action}|{timing}"
                        else:
                            overall = str(rec); recommendation = str(rec)
                        return {'symbol': symbol, 'ok': True, 'overall': overall,
                                'recommendation': recommendation, 'quant_score': quant_score,
                                'trend_status': trend_status, 'bias_20': bias_20,
                                # build_prompt_04：橫斷面RS用 60日報酬
                                'ret_60d': (result.get('technical', {}) or {}).get('ret_60d')}
                    except Exception as e:
                        return {'symbol': symbol, 'ok': False, 'error': str(e)}

                done = 0
                _scan_results = []   # build_prompt_04：收集本批供橫斷面RS排名
                with ThreadPoolExecutor(max_workers=8) as _ex:
                    _futs = {_ex.submit(_analyze_one, sd): sd for sd in stocks}
                    for fut in as_completed(_futs):
                        if not hasattr(self, '_refreshing') or not self._refreshing:
                            print("[自選股刷新] 刷新已取消")
                            break
                        r = fut.result()
                        done += 1
                        self._safe_ui_update(lambda d=done, s=r['symbol']:
                                             self._update_progress(f"刷新中：{d}/{total} ({s})"))
                        if r['ok']:
                            # DB 寫入在主迴圈序列化（每次 update 各自開連線，sqlite 檔案鎖安全）
                            self.db.update_recommendation(r['symbol'], r['recommendation'])
                            self.db.update_quant_data(
                                r['symbol'], quant_score=r['quant_score'],
                                trend_status=r['trend_status'], bias_20=r['bias_20'])
                            success_count += 1
                            _scan_results.append(r)
                            print(f"[自選股刷新] {r['symbol']} 完成: {r['overall']} (Score: {r['quant_score']:.0f})")
                        else:
                            self._refresh_errors.append(f"{r['symbol']}: {r['error']}")
                            print(f"[自選股刷新] {r['symbol']} 失敗: {r['error']}")

                # build_prompt_04 任務2：全樣本掃描完成 → 橫斷面RS百分位，寫回 DB
                try:
                    from trend_scanner import compute_cross_sectional_rs_rank
                    rank_map = compute_cross_sectional_rs_rank(_scan_results)
                    for _sym, _rk in rank_map.items():
                        if _rk is not None:
                            self.db.update_quant_data(_sym, rs_rank_60d=_rk)
                    print(f"[自選股刷新] 橫斷面RS排名完成（{len(rank_map)} 檔）")
                except Exception as _rse:
                    print(f"[自選股刷新] 橫斷面RS排名略過: {_rse}")
            finally:
                # v4.5.13: 離開背景線程，重新啟用垃圾回收
                ThreadSafeGC.exit_background_thread()
            
            # 完成後更新 UI
            def on_complete():
                self._refreshing = False
                self.refresh_watchlist()
                self._update_progress("")
                
                # 顯示完成訊息
                if self._refresh_errors:
                    error_summary = "\n".join(self._refresh_errors[:10])  # 最多顯示10個
                    if len(self._refresh_errors) > 10:
                        error_summary += f"\n...還有 {len(self._refresh_errors) - 10} 個錯誤"
                    messagebox.showwarning(
                        "刷新完成（部分失敗）",
                        f"完成 {success_count}/{total} 檔\n\n失敗項目：\n{error_summary}"
                    )
                else:
                    messagebox.showinfo("刷新完成", f"成功更新 {success_count} 檔自選股")
                
                print(f"[自選股刷新] 完成：成功 {success_count}，失敗 {len(self._refresh_errors)}")
            
            self._safe_ui_update(on_complete)
        
        # 在背景執行緒執行
        thread = threading.Thread(target=analyze_in_background, daemon=True)
        thread.start()
    
    def _update_progress(self, text):
        """更新進度標籤"""
        try:
            if hasattr(self, 'watchlist_progress_label') and self.watchlist_progress_label.winfo_exists():
                self.watchlist_progress_label.config(text=text)
        except tk.TclError:
            pass
    
    def _safe_ui_update(self, func):
        """安全的 UI 更新（避免視窗關閉後出錯）"""
        def wrapper():
            try:
                if self.winfo_exists():
                    func()
            except tk.TclError as e:
                print(f"[UI更新跳過] {e}")
        try:
            self.after(0, wrapper)
        except tk.TclError:
            pass
    
    def show_correlation_analysis(self):
        """顯示相關性分析"""
        stocks = self.db.get_all_stocks()
        if len(stocks) < 2:
            messagebox.showwarning("警告", "至少需要2檔自選股才能進行相關性分析")
            return
        
        symbols = [s[0] for s in stocks]
        market = stocks[0][2] if stocks else "台股"
        
        CorrelationDialog(self, symbols, market)
    
    def auto_analyze_watchlist(self):
        """自動分析所有自選股（v4.5.18 更新：儲存評分到資料庫）"""
        if self.auto_analysis_done:
            return
        
        stocks = self.db.get_all_stocks()
        if not stocks:
            return
        
        def analyze_in_background():
            # v4.5.13: 進入背景線程，禁用自動垃圾回收
            ThreadSafeGC.enter_background_thread()
            try:
                from analyzers import DecisionMatrix

                # B2 #1：掃描前批次預抓歷史（單次 yf.download），
                # 後續逐檔 analyze_stock 的 get_history 直接命中快取。
                try:
                    _tw = [s[0] for s in stocks if (s[2] if len(s) > 2 else '台股') == '台股']
                    if _tw:
                        DataSourceManager.prefetch_histories(_tw, '台股')
                        DataSourceManager.prefetch_realtime(_tw, '台股')
                except Exception as _pe:
                    print(f'[B2] 批次預抓略過: {_pe}')

                # ── 平行掃描（B2 #3）：worker 只算、不碰 DB；DB 寫入在主迴圈序列化 ──
                from concurrent.futures import ThreadPoolExecutor, as_completed

                SCENARIO_SHORT_NAMES = {
                    'A': '雙強共振', 'B': '拉回佈局', 'C': '投機反彈',
                    'D': '高檔震盪', 'E': '多空不明', 'F': '弱勢盤整',
                    'G': '頭部確立', 'H': '空頭確認', 'I': '動能交易'
                }

                def _auto_one(stock):
                    symbol = stock[0]; name = stock[1]; market = stock[2]
                    try:
                        result = QuickAnalyzer.analyze_stock(symbol, market, scan_mode=True)
                        if not result:
                            return None
                        quant_score = 0; trend_status = "待分析"; bias_20 = 0
                        try:
                            short_term_data = DecisionMatrix.calculate_short_term_score(result)
                            long_term_data = DecisionMatrix.calculate_long_term_score(result)
                            investment_advice = DecisionMatrix.get_investment_advice(
                                short_term_data.get('score', 50), long_term_data.get('score', 50))
                            # fix_07 任務3：watchlist 分數單一化 = 引擎綜合分（與報告同源）
                            quant_score = result.get('decision_matrix', {}).get('score', 50)
                            trend_status = result.get('trend', {}).get('primary_trend', '盤整') if isinstance(result.get('trend'), dict) else '待分析'
                            bias_20 = result.get('bias', {}).get('bias_20', 0) if isinstance(result.get('bias'), dict) else 0
                            scenario_code = investment_advice.get('scenario_code', 'E')
                            scenario_name = SCENARIO_SHORT_NAMES.get(scenario_code, scenario_code)
                            action_zh = investment_advice.get('action_zh', '觀望')
                            rec = result.get('recommendation', {})
                            if isinstance(rec, dict):
                                short_term = rec.get('short_term', {})
                                short_action = short_term.get('action', action_zh) if isinstance(short_term, dict) else action_zh
                                timing = rec.get('action_timing', '觀望中')
                                overall = rec.get('overall', action_zh)
                            else:
                                short_action = action_zh; timing = '觀望中'; overall = action_zh
                            recommendation = f"{overall}|{scenario_name}|{short_action}|{timing}"
                        except Exception as dm_error:
                            print(f"DecisionMatrix 計算錯誤 {symbol}: {dm_error}")
                            rec = result['recommendation']
                            if isinstance(rec, dict):
                                overall = rec.get('overall', '待分析')
                                scenario = rec.get('scenario_name', '')
                                short_term = rec.get('short_term', {})
                                short_action = short_term.get('action', '') if isinstance(short_term, dict) else ''
                                timing = rec.get('action_timing', '')
                                recommendation = f"{overall}|{scenario}|{short_action}|{timing}"
                            else:
                                recommendation = str(rec)
                        return {'symbol': symbol, 'recommendation': recommendation,
                                'quant_score': quant_score, 'trend_status': trend_status, 'bias_20': bias_20}
                    except Exception as e:
                        print(f"自動分析 {symbol} 錯誤: {e}")
                        return None

                with ThreadPoolExecutor(max_workers=8) as _ex:
                    for fut in as_completed([_ex.submit(_auto_one, st) for st in stocks]):
                        r = fut.result()
                        if r:
                            self.db.update_recommendation(r['symbol'], r['recommendation'])
                            self.db.update_quant_data(
                                r['symbol'], quant_score=r['quant_score'],
                                trend_status=r['trend_status'], bias_20=r['bias_20'])
                
                # v4.4.2 修正：使用安全的 UI 更新
                def safe_update():
                    try:
                        if self.winfo_exists():
                            self.refresh_watchlist()
                            self.auto_analysis_done = True
                    except tk.TclError:
                        pass
                
                try:
                    self.after(0, safe_update)
                except tk.TclError:
                    pass
                    
            except Exception as e:
                print(f"背景分析出錯: {e}")
            finally:
                # v4.5.13: 離開背景線程，重新啟用垃圾回收
                ThreadSafeGC.exit_background_thread()
        
        # v4.4.2 修正：線程啟動放在正確位置
        thread = threading.Thread(target=analyze_in_background, daemon=True)
        thread.start()
    
    def add_to_watchlist(self):
        """加入自選股（v4.4.7 更新：只分析新加入的股票，不全部重跑）"""
        symbol = self.symbol_entry.get().strip()
        if not symbol:
            messagebox.showwarning("警告", "請先輸入股票代碼")
            return
        
        if self.db.get_stock_count() >= 100:
            messagebox.showwarning("警告", "自選股已達上限（100筆）")
            return
        
        market = self.market_var.get()
        
        name = ""
        if symbol.isdigit() and market == "台股":
            try:
                name = twstock.codes[symbol].name
            except:
                pass
        
        if self.db.add_stock(symbol, name, market):
            messagebox.showinfo("成功", f"已將 {symbol} 加入自選股")
            self.refresh_watchlist()
            
            # v4.4.7: 只分析新加入的股票，不全部重跑
            self._analyze_single_stock(symbol, name, market)
        else:
            messagebox.showwarning("警告", "該股票已在自選股中")
    
    def _analyze_single_stock(self, symbol, name, market):
        """
        v4.4.7 新增：分析單一股票（背景執行）
        v4.5.8 修正：統一使用 DecisionMatrix（與報告一致）
        
        用於新加入自選股時，只分析該股票而不是全部重跑
        """
        def analyze_in_background():
            # v4.5.13: 進入背景線程，禁用自動垃圾回收
            ThreadSafeGC.enter_background_thread()
            try:
                from analyzers import DecisionMatrix
                
                print(f"[單股分析] 開始分析 {symbol} ({name or 'N/A'})")
                result = QuickAnalyzer.analyze_stock(symbol, market, scan_mode=True)
                
                if result:
                    # v4.5.8：使用 DecisionMatrix 統一計算（與報告一致）
                    try:
                        short_term_data = DecisionMatrix.calculate_short_term_score(result)
                        long_term_data = DecisionMatrix.calculate_long_term_score(result)
                        investment_advice = DecisionMatrix.get_investment_advice(
                            short_term_data.get('score', 50),
                            long_term_data.get('score', 50)
                        )
                        
                        # v4.5.11 修正：場景顯示簡短名稱（與報告一致）
                        scenario_code = investment_advice.get('scenario_code', 'E')
                        # 場景代碼轉簡短名稱
                        SCENARIO_SHORT_NAMES = {
                            'A': '雙強共振', 'B': '拉回佈局', 'C': '投機反彈',
                            'D': '高檔震盪', 'E': '多空不明', 'F': '弱勢盤整',
                            'G': '頭部確立', 'H': '空頭確認', 'I': '動能交易'
                        }
                        scenario_name = SCENARIO_SHORT_NAMES.get(scenario_code, scenario_code)
                        action_zh = investment_advice.get('action_zh', '觀望')
                        
                        # 取得短線操作建議和進場時機（從 recommendation 取，與報告一致）
                        rec = result.get('recommendation', {})
                        if isinstance(rec, dict):
                            short_term = rec.get('short_term', {})
                            short_action = short_term.get('action', action_zh) if isinstance(short_term, dict) else action_zh
                            # v4.5.10 修正：使用 recommendation['action_timing']
                            timing = rec.get('action_timing', '觀望中')
                            # v4.5.10 修正：總結使用 recommendation['overall']（與報告一致）
                            overall = rec.get('overall', action_zh)
                        else:
                            short_action = action_zh
                            timing = '觀望中'
                            overall = action_zh
                        
                        recommendation = f"{overall}|{scenario_name}|{short_action}|{timing}"
                    except Exception as dm_error:
                        print(f"DecisionMatrix 計算錯誤 {symbol}: {dm_error}")
                        # 回退到舊方法
                        rec = result['recommendation']
                        if isinstance(rec, dict):
                            overall = rec.get('overall', '待分析')
                            scenario = rec.get('scenario_name', '')
                            short_term = rec.get('short_term', {})
                            short_action = short_term.get('action', '') if isinstance(short_term, dict) else ''
                            timing = rec.get('action_timing', '')
                            recommendation = f"{overall}|{scenario}|{short_action}|{timing}"
                        else:
                            recommendation = str(rec)
                    
                    self.db.update_recommendation(symbol, recommendation)
                    print(f"[單股分析] {symbol} 分析完成: {overall}")
                    
                    # 安全更新 UI
                    def safe_update():
                        try:
                            if self.winfo_exists():
                                self.refresh_watchlist()
                        except tk.TclError:
                            pass
                    
                    self.after(0, safe_update)
                else:
                    print(f"[單股分析] {symbol} 分析失敗")
                    
            except Exception as e:
                print(f"[單股分析] {symbol} 錯誤: {e}")
            finally:
                # v4.5.13: 離開背景線程，重新啟用垃圾回收
                ThreadSafeGC.exit_background_thread()
        
        # 背景執行分析
        thread = threading.Thread(target=analyze_in_background, daemon=True)
        thread.start()
    
    def remove_from_watchlist(self):
        """移除自選股"""
        selection = self.watchlist_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "請先選擇要移除的股票")
            return
        
        item = self.watchlist_tree.item(selection[0])
        symbol_text = item['text']
        symbol = symbol_text.split()[0]
        
        if messagebox.askyesno("確認", f"確定要移除 {symbol} 嗎？"):
            self.db.remove_stock(symbol)
            messagebox.showinfo("成功", f"已移除 {symbol}")
            self.refresh_watchlist()
    
    def refresh_watchlist(self):
        """刷新自選股列表（v4.5.18 標準金融字型版）"""
        # 清空舊資料
        for item in self.watchlist_tree.get_children():
            self.watchlist_tree.delete(item)
        
        # 取得排序選項
        order_by = getattr(self, 'watchlist_sort_var', None)
        if order_by:
            order_by = order_by.get()
        else:
            order_by = 'industry'  # 預設按族群排序
        
        stocks = self.db.get_all_stocks(order_by=order_by)
        
        # ========================================
        # v4.5.18 標準金融終端機風格
        # ========================================
        # 標準金融字型：Consolas (數字等寬)、Segoe UI (中文)
        FONT_FAMILY = "Consolas"
        FONT_SIZE = 9
        
        # UI 改造：Treeview 樣式統一由 theme.style_treeview 管理（在建立時已套用），
        # 不再於每次刷新重設 ttk.Style（避免覆蓋主題、且省去重複設定）。
        # tag 顏色一律走 theme token。
        if getattr(self, '_theme', None) is not None:
            self._theme.style_treeview(self.watchlist_tree)
        else:
            # 後備：主題未載入時維持可讀的深色 tag
            self.watchlist_tree.tag_configure("group", background="#1a1a2e", foreground="#ffffff")
            # fix_07 任務6：動作語意色（買=橘 / 賣=綠 / 中性=灰）
            import theme as _thm
            self.watchlist_tree.tag_configure("buy", foreground=_thm.ACTION_BUY)
            self.watchlist_tree.tag_configure("hold", foreground=_thm.ACTION_NEUTRAL)
            self.watchlist_tree.tag_configure("sell", foreground=_thm.ACTION_SELL)
            self.watchlist_tree.tag_configure("wait", foreground=_thm.ACTION_NEUTRAL)
            self.watchlist_tree.tag_configure("hot", background="#3a1a1a")
            self.watchlist_tree.tag_configure("cold", background="#1a3a1a")

        # 判斷是否使用分組模式
        use_grouping = (order_by == 'industry')
        
        if use_grouping:
            # ========================================
            # 分組模式：族群 -> 個股
            # ========================================
            grouped_data = {}
            for stock_data in stocks:
                # 安全讀取
                if len(stock_data) < 7:
                    stock_data = list(stock_data) + ['未分類'] * (7 - len(stock_data))
                
                industry = stock_data[6] or "未分類"
                
                if industry not in grouped_data:
                    grouped_data[industry] = []
                grouped_data[industry].append(stock_data)
            
            total_count = 0
            
            # 遍歷每個族群
            for industry, items in grouped_data.items():
                # 計算族群統計（安全讀取評分）
                scores = []
                for s in items:
                    if len(s) > 8 and s[8]:
                        scores.append(s[8])
                avg_score = sum(scores) / len(scores) if scores else 0
                
                # 建立族群父節點（不使用表情符號）
                group_text = f"[{industry}] ({len(items)})"
                if avg_score > 0:
                    group_text += f" Avg:{avg_score:.0f}"
                
                group_id = self.watchlist_tree.insert("", "end", 
                    text=group_text, 
                    values=("", "", ""),
                    open=True, 
                    tags=('group',)
                )
                
                # 插入個股子節點
                for item in items:
                    symbol = item[0] if len(item) > 0 else ''
                    name = item[1] if len(item) > 1 else ''
                    recommendation = item[5] if len(item) > 5 else ''
                    quant_score = item[8] if len(item) > 8 else 0
                    bias_20 = item[11] if len(item) > 11 else 0
                    
                    # 解析建議字串："overall|scenario_name|short_action|timing"（同源 build_verdict）
                    signal = "待分析"
                    _scen_name = ''
                    _short_act = ''
                    if recommendation and '|' in recommendation:
                        parts = recommendation.split('|')
                        signal = parts[0] if len(parts) > 0 else '待分析'
                        _scen_name = parts[1] if len(parts) > 1 else ''
                        _short_act = parts[2] if len(parts) > 2 else ''
                    elif recommendation:
                        signal = recommendation

                    # build_prompt_06 任務3：等級取自 scenario_name 首碼（A/B/C），
                    # tag 以 grade 為主、grade_tag 字串比對降為 fallback。
                    _grade = next((g for g in ('A', 'B', 'C')
                                   if _scen_name.startswith(g) or signal.startswith(g)), '')
                    tags = []
                    if _grade:
                        tags.append({'A': 'grade_A', 'B': 'grade_B', 'C': 'grade_C'}[_grade])
                    else:
                        _gtag = self._theme.grade_tag(_scen_name or signal) if getattr(self, '_theme', None) else None
                        if _gtag:
                            tags.append(_gtag)
                        elif any(x in signal for x in ["買", "多", "進場", "看好"]):
                            tags.append("buy")
                        elif any(x in signal for x in ["賣", "空", "減碼", "撤退", "停損"]):
                            tags.append("sell")
                        elif any(x in signal for x in ["持有", "續抱"]):
                            tags.append("hold")
                        else:
                            tags.append("wait")

                    # 過熱/超跌背景
                    if bias_20 and bias_20 > 10:
                        tags.append("hot")
                    elif bias_20 and bias_20 < -10:
                        tags.append("cold")

                    # 評分顯示
                    score_str = f"{quant_score:.0f}" if quant_score else "-"

                    # build_prompt_06 任務3：欄位格式 {等級} {簡短action}，超長截斷（tooltip 由既有機制）
                    if _grade:
                        _act = (_short_act or signal).replace("建議", "").strip()
                        display_signal = f"{_grade} {_act}"[:20]
                    else:
                        display_signal = signal.replace("建議", "")[:20]
                    
                    self.watchlist_tree.insert(group_id, "end", 
                        text=symbol, 
                        values=(name, score_str, display_signal),
                        tags=tuple(tags)
                    )
                    total_count += 1
            
            # v4.5.18：檢查數據新舊，顯示提示
            oldest_date = None
            for stock_data in stocks:
                if len(stock_data) > 12 and stock_data[12]:  # last_analyzed
                    try:
                        analyzed_date = stock_data[12].split()[0]  # 取日期部分
                        if oldest_date is None or analyzed_date < oldest_date:
                            oldest_date = analyzed_date
                    except:
                        pass
            
            # 更新計數標籤
            status_text = f"{total_count} / {len(grouped_data)} Groups"
            if oldest_date:
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if oldest_date < today:
                    status_text += f" [!{oldest_date}]"  # 提示數據已過期
                    self.watchlist_count_label.config(foreground="#ff8800")  # 橙色警告
                else:
                    self.watchlist_count_label.config(foreground="#00aaff")
            self.watchlist_count_label.config(text=status_text)
        
        else:
            # ========================================
            # 平面模式：原有顯示方式
            # ========================================
            for stock_data in stocks:
                # 安全讀取
                if len(stock_data) < 6:
                    stock_data = list(stock_data) + [''] * (6 - len(stock_data))
                
                symbol = stock_data[0]
                name = stock_data[1]
                recommendation = stock_data[5] if len(stock_data) > 5 else ''
                quant_score = stock_data[8] if len(stock_data) > 8 else 0
                
                display_text = f"{symbol} {name if name else ''}"
                
                # 解析建議
                signal = "待分析"
                _scen_name = ''
                _short_act = ''
                if recommendation and '|' in recommendation:
                    parts = recommendation.split('|')
                    signal = parts[0]
                    _scen_name = parts[1] if len(parts) > 1 else ''
                    _short_act = parts[2] if len(parts) > 2 else ''
                elif recommendation:
                    signal = recommendation

                # build_prompt_06 任務3：tag 以 grade 為主，grade_tag 字串比對為 fallback
                _grade = next((g for g in ('A', 'B', 'C')
                               if _scen_name.startswith(g) or signal.startswith(g)), '')
                if _grade:
                    tag = {'A': 'grade_A', 'B': 'grade_B', 'C': 'grade_C'}[_grade]
                else:
                    tag = (self._theme.grade_tag(_scen_name or signal) if getattr(self, '_theme', None) else None)
                    if not tag:
                        if any(x in signal for x in ["買", "多"]):
                            tag = "buy"
                        elif any(x in signal for x in ["賣", "減碼"]):
                            tag = "sell"
                        elif "持有" in signal:
                            tag = "hold"
                        else:
                            tag = "wait"

                score_str = f"{quant_score:.0f}" if quant_score else "-"
                if _grade:
                    _act = (_short_act or signal).replace("建議", "").strip()
                    display_signal = f"{_grade} {_act}"[:20]
                else:
                    display_signal = signal.replace("建議", "")[:20]

                self.watchlist_tree.insert("", "end",
                    text=display_text,
                    values=(name, score_str, display_signal),
                    tags=(tag,)
                )
            
            count = len(stocks)
            self.watchlist_count_label.config(text=f"{count}/100")
            
            if count >= 100:
                self.watchlist_count_label.config(foreground="red")
            else:
                self.watchlist_count_label.config(foreground="#00aaff")
    
    # ========================================================================
    # v4.4.7 新增：自選股排序功能
    # ========================================================================
    
    def _get_selected_watchlist_symbol(self):
        """取得目前選中的自選股代碼"""
        selection = self.watchlist_tree.selection()
        if not selection:
            return None
        item = self.watchlist_tree.item(selection[0])
        symbol_text = item['text']
        return symbol_text.split()[0]
    
    def move_watchlist_up(self):
        """將選中的股票上移一位"""
        symbol = self._get_selected_watchlist_symbol()
        if not symbol:
            messagebox.showwarning("提示", "請先選擇要移動的股票")
            return
        
        if self.db.move_stock_up(symbol):
            # 切換到自訂排序模式
            self.watchlist_sort_var.set('sort_order')
            self.refresh_watchlist()
            # 重新選中該項目
            self._select_watchlist_item(symbol)
    
    def move_watchlist_down(self):
        """將選中的股票下移一位"""
        symbol = self._get_selected_watchlist_symbol()
        if not symbol:
            messagebox.showwarning("提示", "請先選擇要移動的股票")
            return
        
        if self.db.move_stock_down(symbol):
            self.watchlist_sort_var.set('sort_order')
            self.refresh_watchlist()
            self._select_watchlist_item(symbol)
    
    def move_watchlist_to_top(self):
        """將選中的股票移到最上面"""
        symbol = self._get_selected_watchlist_symbol()
        if not symbol:
            messagebox.showwarning("提示", "請先選擇要移動的股票")
            return
        
        if self.db.move_stock_to_top(symbol):
            self.watchlist_sort_var.set('sort_order')
            self.refresh_watchlist()
            self._select_watchlist_item(symbol)
    
    def move_watchlist_to_bottom(self):
        """將選中的股票移到最下面"""
        symbol = self._get_selected_watchlist_symbol()
        if not symbol:
            messagebox.showwarning("提示", "請先選擇要移動的股票")
            return
        
        if self.db.move_stock_to_bottom(symbol):
            self.watchlist_sort_var.set('sort_order')
            self.refresh_watchlist()
            self._select_watchlist_item(symbol)
    
    def _select_watchlist_item(self, symbol):
        """選中指定股票（用於移動後保持選中狀態）"""
        for item_id in self.watchlist_tree.get_children():
            item = self.watchlist_tree.item(item_id)
            if item['text'].startswith(symbol + ' ') or item['text'] == symbol:
                self.watchlist_tree.selection_set(item_id)
                self.watchlist_tree.see(item_id)
                break
    
    def _sort_watchlist_by(self, column):
        """
        點擊欄位標題時的排序（v4.4.7 新增）
        
        點擊同一欄位會切換升序/降序
        """
        if not hasattr(self, '_watchlist_sort_reverse'):
            self._watchlist_sort_reverse = {}
        
        # 取得當前所有項目
        items = []
        for item_id in self.watchlist_tree.get_children():
            item = self.watchlist_tree.item(item_id)
            text = item['text']
            values = item['values']
            tags = item['tags']
            items.append((item_id, text, values, tags))
        
        # 根據欄位排序
        reverse = self._watchlist_sort_reverse.get(column, False)
        
        if column == 'symbol':
            # 按股票代碼排序
            items.sort(key=lambda x: x[1].split()[0], reverse=reverse)
        elif column == 'scenario':
            items.sort(key=lambda x: x[2][0] if x[2] else '', reverse=reverse)
        elif column == 'short_term':
            items.sort(key=lambda x: x[2][1] if len(x[2]) > 1 else '', reverse=reverse)
        elif column == 'timing':
            items.sort(key=lambda x: x[2][2] if len(x[2]) > 2 else '', reverse=reverse)
        elif column == 'recommendation':
            items.sort(key=lambda x: x[2][3] if len(x[2]) > 3 else '', reverse=reverse)
        
        # 切換排序方向
        self._watchlist_sort_reverse[column] = not reverse
        
        # 重新插入項目
        for idx, (item_id, text, values, tags) in enumerate(items):
            self.watchlist_tree.move(item_id, '', idx)
    
    def on_watchlist_double_click(self, event):
        """雙擊自選股項目時查詢（v4.5.17 支援族群分組）"""
        selection = self.watchlist_tree.selection()
        if not selection:
            return
        
        item = self.watchlist_tree.item(selection[0])
        symbol_text = item['text']
        
        # 檢查是否為族群節點（以 📂 開頭）
        if symbol_text.startswith('📂'):
            # 雙擊族群節點：展開/收起
            if self.watchlist_tree.item(selection[0], 'open'):
                self.watchlist_tree.item(selection[0], open=False)
            else:
                self.watchlist_tree.item(selection[0], open=True)
            return
        
        # 個股節點：取得代碼並查詢
        symbol = symbol_text.split()[0]
        
        # 從資料庫取得市場資訊
        stocks = self.db.get_all_stocks()
        for stock in stocks:
            if stock[0] == symbol:
                market = stock[2] if len(stock) > 2 else '台股'
                self.market_var.set(market)
                break
        
        self.symbol_entry.delete(0, tk.END)
        self.symbol_entry.insert(0, symbol)
        self.plot_chart()


# ============================================================================
# 主程式入口
# ============================================================================

def main():
    """主程式"""
    print("=" * 60)
    print("量化投資分析系統 v4.5.18")
    print("=" * 60)
    print("v4.5.18 更新：")
    print(" - 標準金融終端機字型 (Consolas)")
    print(" - 移除表情符號，統一字體大小")
    print(" - 評分計算修復（短線60%+長線40%）")
    print(" - 族群分組顯示")
    print("-" * 60)
    print("v4.5.17 新增功能：")
    print(" - 熱門題材掃描（強勢族群、領頭羊）")
    print(" - 資料庫族群欄位（自動標註）")
    print(" - 進階分析器（VCP、RS、ATR停損）")
    print("-" * 60)
    print("v4.3 核心功能：")
    print(" 23. 核心決策變數（趨勢、乖離、盈虧比、量能）")
    print(" 24. 五大場景決策矩陣（A~E）")
    print(" 25. 強制濾網條件（RR<1.5降級、假突破警示）")
    print(" 26. 一致性建議輸出")
    print(" 27. 歷史日期選擇（策略驗證）")
    print(" 28. 未來驗證區塊（5/10/20天後走勢）")
    print("-" * 60)
    print("v4.2 新增功能：")
    print(" 18. 乖離率分析（20MA/60MA，過熱/超跌警示）")
    print(" 19. 左側買進訊號（超跌反彈偵測）")
    print(" 20. 左側賣出訊號（漲多預判拉回）")
    print(" 21. 雙軌出場策略（防守型 vs 積極型）")
    print(" 22. 操作建議總結（趨勢+乖離綜合判斷）")
    print("-" * 60)
    print("v4.1 新增功能：")
    print(" 11. 波段環境篩選（K線>55MA 且 55MA上揚）")
    print(" 12. 三盤突破偵測（進場訊號）")
    print(" 13. 三盤跌破偵測（出場訊號）")
    print(" 14. 爆量K線守則")
    print(" 15. 量價共振判斷")
    print(" 16. K線圖顯示即時股價資訊")
    print("-" * 60)
    print("v4.0 改進項目：")
    print("  1. PE Band 歷史百分位評估 + Forward PE 預估本益比")
    print("  2. 風險指標使用 2 年長期數據計算")
    print("  3. 籌碼面 SQLite 緩存機制（避免 IP 封鎖）")
    print("  4. 市場環境過濾器（ADX 趨勢/震盪判斷）")
    print("  5. 策略穩定性評分（Sharpe Ratio 權重）")
    print("  6. Sharpe Ratio 扣除無風險利率")
    print("  7. 回測彈窗增加 Equity Curve 淨值曲線")
    print("  8. Beta 係數計算（防禦型/攻擊型分類）")
    print("  9. Volume Spike 成交量異常偵測")
    print(" 10. 自選股相關性矩陣分析")
    print("=" * 60)
    
    app = StockAnalysisApp()
    app.mainloop()


if __name__ == "__main__":
    main()
