import sys
import pandas as pd
import numpy as np
import yfinance as yf
import datetime

class DayTradingBacktester:
    def __init__(self, symbol, initial_capital=500000):
        self.symbol = symbol
        # 台股代碼修正
        if symbol.isdigit():
            self.ticker_symbol = f"{symbol}.TW"
        else:
            self.ticker_symbol = symbol
            
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.trade_log = []
        
        # 當沖參數設定
        self.timeframe = "5m"  # 5分鐘K線
        self.period = "1mo"    # 回測近一個月 (Yahoo限制)
        self.stop_loss_pct = 1.5  # 1.5% 停損
        self.take_profit_pct = 3.0 # 3% 停利
        
        # 交易手續費 (當沖稅率減半 0.15% + 手續費 0.1425%)
        self.cost_rate = 0.001425 + 0.0015 

    def fetch_intraday_data(self):
        """抓取分鐘級資料"""
        print(f"📥 正在抓取 {self.ticker_symbol} 近期 {self.timeframe} 資料...")
        try:
            # 抓取最近 1 個月的 5 分鐘線
            df = yf.Ticker(self.ticker_symbol).history(period=self.period, interval=self.timeframe)
            
            if df.empty:
                # 嘗試上櫃
                if self.ticker_symbol.endswith(".TW"):
                    self.ticker_symbol = self.ticker_symbol.replace(".TW", ".TWO")
                    print(f"⚠️ 嘗試上櫃代碼 {self.ticker_symbol}...")
                    df = yf.Ticker(self.ticker_symbol).history(period=self.period, interval=self.timeframe)
            
            if df.empty:
                print("❌ 無法取得分鐘資料")
                return None
                
            # 轉換索引為本地時間 (處理時區問題)
            df.index = df.index.tz_convert('Asia/Taipei')
            return df
        except Exception as e:
            print(f"❌ 資料抓取錯誤: {e}")
            return None

    def calculate_intraday_indicators(self, df):
        """計算當沖指標 (VWAP, MA)"""
        df = df.copy()
        
        # 計算 VWAP (每日重置)
        # 這裡簡化計算：用當前區間的典型價格 * 成交量 的累加 / 成交量累加
        # 實務上應該要 detect 日期變更重置，這裡做一個簡易版全域 VWAP
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['Cum_Vol'] = df['Volume'].cumsum()
        df['Cum_PV'] = (df['Typical_Price'] * df['Volume']).cumsum()
        df['VWAP'] = df['Cum_PV'] / df['Cum_Vol']
        
        # 短期均線 (5MA on 5min = 25分鐘線)
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        # 成交量放大 (量比)
        df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
        df['Vol_Ratio'] = df['Volume'] / df['Vol_MA5']
        
        return df

    def run(self):
        df = self.fetch_intraday_data()
        if df is None: return
        
        df = self.calculate_intraday_indicators(df)
        
        print(f"\n🚀 開始當沖回測: {self.symbol}")
        print(f"💰 初始資金: ${self.initial_capital:,.0f}")
        print("-" * 80)
        print(f"{'時間':<20} {'動作':<6} {'價格':<8} {'股數':<6} {'損益':<10} {'餘額':<10} {'原因'}")
        print("-" * 80)
        
        position = 0
        entry_price = 0
        entry_time = None
        
        # 模擬逐根 K 棒走勢
        # 為了簡化，我們假設每天是一場獨立的戰役
        
        current_date = None
        
        for i in range(20, len(df)): # 前20根算指標
            bar = df.iloc[i]
            ts = df.index[i]
            time_str = ts.strftime('%m-%d %H:%M')
            
            # 檢查是否換日 (換日要強制平倉檢查)
            if current_date != ts.date():
                if position > 0:
                    # 隔日強制平倉 (實際上 13:25 就要平，這裡模擬沒平到的狀況)
                    self._close_position(ts, df.iloc[i-1]['Close'], position, "隔日開盤強平")
                    position = 0
                current_date = ts.date()
                
            close = bar['Close']
            
            # === [時間出場機制] 13:25 強制平倉 ===
            # 判斷時間是否接近收盤 (13:25)
            if ts.hour == 13 and ts.minute >= 25:
                if position > 0:
                    self._close_position(ts, close, position, "13:25 強制平倉")
                    position = 0
                continue # 收盤前不進場
                
            # === [進場邏輯] ===
            if position == 0:
                # 策略：VWAP 突破 + 爆量
                # 條件1: 收盤價站上 VWAP
                # 條件2: 5分K 爆量 (大於均量 1.5 倍)
                # 條件3: 均線多頭 (MA5 > MA20)
                # 時間過濾: 只在 09:00 - 12:00 進場
                
                if (ts.hour < 12) and \
                   (close > bar['VWAP']) and \
                   (bar['Vol_Ratio'] > 1.5) and \
                   (bar['MA5'] > bar['MA20']):
                    
                    # 進場買進 (資金允許的最大股數，最多2張)
                    max_qty = 2000
                    afford_qty = int(self.cash / close)
                    qty = min(max_qty, afford_qty)
                    
                    if qty >= 1000: # 至少買一張
                        cost = qty * close * (1 + 0.001425)
                        self.cash -= cost
                        position = qty
                        entry_price = close
                        entry_time = ts
                        print(f"{time_str:<20} 買進   {close:<8.1f} {qty:<6} {'-':<10} {self.cash:<10.0f} VWAP帶量突破")

            # === [出場邏輯] ===
            elif position > 0:
                profit_pct = (close - entry_price) / entry_price * 100
                
                # 停利
                if profit_pct >= self.take_profit_pct:
                    self._close_position(ts, close, position, f"停利 (+{profit_pct:.1f}%)")
                    position = 0
                    
                # 停損
                elif profit_pct <= -self.stop_loss_pct:
                    self._close_position(ts, close, position, f"停損 ({profit_pct:.1f}%)")
                    position = 0
                    
                # 技術面出場：跌破 VWAP
                elif close < bar['VWAP'] and profit_pct < -0.5: # 稍微給點緩衝
                    self._close_position(ts, close, position, "跌破 VWAP")
                    position = 0

    def _close_position(self, ts, price, qty, reason):
        revenue = price * qty * (1 - self.cost_rate) # 扣除當沖稅費
        self.cash += revenue
        
        # 計算該筆損益
        last_trade = self.trade_log[-1] if self.trade_log else None
        cost = 0
        # 這裡簡單推算，實際上應該紀錄 entry cost
        # 為了 demo 方便，直接印出餘額變化
        pnl = revenue - (self.cash - revenue + price*qty) # 近似值
        
        pnl_val = self.cash - self.initial_capital
        
        time_str = ts.strftime('%m-%d %H:%M')
        print(f"{time_str:<20} 賣出   {price:<8.1f} {qty:<6} {pnl:<+10.0f} {self.cash:<10.0f} {reason}")

if __name__ == "__main__":
    symbol = input("請輸入股票代號 (如 2330): ")
    bt = DayTradingBacktester(symbol)
    bt.run()