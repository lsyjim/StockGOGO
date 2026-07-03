import sys
import os
import pandas as pd
import numpy as np
import yfinance as yf
import datetime
from dateutil.parser import parse

# 引用您的模組
from analyzers import WaveAnalyzer, MeanReversionAnalyzer, VolumePriceAnalyzer, wilder_rsi
from config import QuantConfig

# 強制啟用量價分析
QuantConfig.ENABLE_VOLUME_PRICE_ANALYSIS = True

class Backtester:
    def __init__(self, symbol, start_date, initial_capital, tp_pct=20.0, sl_pct=10.0):
        self.symbol = symbol
        self.start_date = start_date
        self.initial_capital = initial_capital
        self.tp_pct = tp_pct  # 停利 %
        self.sl_pct = sl_pct  # 停損 %
        
        self.cash = initial_capital
        self.inventory = 0
        self.avg_cost = 0
        self.trade_log = []
        
        # 修正代碼格式 (台股需加 .TW)
        if symbol.isdigit():
            self.ticker_symbol = f"{symbol}.TW"
        else:
            self.ticker_symbol = symbol

    def fetch_data(self):
        """抓取歷史數據"""
        print(f"📥 正在抓取 {self.ticker_symbol} 數據...")
        fetch_start = self.start_date - datetime.timedelta(days=200)
        
        try:
            df = yf.Ticker(self.ticker_symbol).history(start=fetch_start, interval="1d")
            if df.empty:
                if self.ticker_symbol.endswith(".TW"):
                    self.ticker_symbol = self.ticker_symbol.replace(".TW", ".TWO")
                    print(f"⚠️ 上市無數據，嘗試上櫃 {self.ticker_symbol}...")
                    df = yf.Ticker(self.ticker_symbol).history(start=fetch_start, interval="1d")
            
            if df.empty:
                print("❌ 錯誤：無法取得數據，請確認代號。")
                return None
                
            return df
        except Exception as e:
            print(f"❌ 數據抓取錯誤: {e}")
            return None

    def calculate_technical_indicators(self, df):
        """計算基礎技術指標"""
        df = df.copy()
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA55'] = df['Close'].rolling(window=55).mean()
        
        df['RSI'] = wilder_rsi(df['Close'], 14)   # Wilder，共用實作

        df['Bias_20'] = ((df['Close'] - df['MA20']) / df['MA20']) * 100
        df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
        
        return df

    def _detect_signals(self, analysis_result):
        """
        訊號偵測邏輯
        [修改] 這裡只偵測買進訊號，技術面賣出訊號全部移除
        """
        signals = {
            'buy_signal': False, 'buy_reason': '',
            'sell_signal': False, 'sell_reason': '' # 預設為 False，只有風控能觸發它
        }
        
        try:
            tech = analysis_result.get('technical', {})
            rsi = tech.get('rsi', 50)
            ma5, ma20, ma55 = tech.get('ma5') or 0, tech.get('ma20') or 0, tech.get('ma55') or 0
            current_price = analysis_result.get('current_price', 0)
            bias_20 = analysis_result.get('bias_20', 0)
            vp_signals = analysis_result.get('volume_price', {}).get('signals', [])
            
            is_distribution = any(s.get('code') in ['VP07', 'VP08'] for s in vp_signals)
            
            # === 買進訊號 (維持不變) ===
            # 1. 三盤突破
            if ma5 > 0 and ma20 > 0 and ma55 > 0:
                if current_price > ma55 and ma5 > ma20 > ma55:
                    for sig in vp_signals:
                        if sig.get('code') == 'VP05' and not is_distribution:
                            signals['buy_signal'] = True
                            signals['buy_reason'] = '三盤突破 (多頭排列+帶量)'

            # 2. 左側買訊 (超跌)
            if not signals['buy_signal']:
                if bias_20 < -10 and rsi < 30:
                    signals['buy_signal'] = True
                    signals['buy_reason'] = f'左側買訊 (乖離{bias_20:.1f}%, RSI{rsi:.0f})'

            # 3. 黃金買點
            if not signals['buy_signal']:
                is_bull = ma5 > ma20 and current_price > ma20
                golden_bias = -5 <= bias_20 <= 2
                golden_rsi = rsi < 60
                if is_bull and golden_bias and golden_rsi and not is_distribution:
                    signals['buy_signal'] = True
                    signals['buy_reason'] = '黃金買點 (多頭回檔)'

            # === 賣出訊號 (技術面) ===
            # [修改] 全部移除！不讓技術指標干擾持倉
            # 只有下面的 _execute_trade 前的風控檢查能觸發賣出
                        
        except Exception:
            pass
            
        return signals

    def run(self):
        df_full = self.fetch_data()
        if df_full is None: return

        df_calc = self.calculate_technical_indicators(df_full)
        mask = df_calc.index >= pd.Timestamp(self.start_date).tz_localize(df_calc.index.dtype.tz)
        df_test = df_calc[mask]
        
        if df_test.empty:
            print("❌ 選定期間無數據")
            return

        print(f"\n🚀 開始回測 {self.symbol} | 區間: {self.start_date.date()} ~ {datetime.date.today()}")
        print(f"💰 初始資金: ${self.initial_capital:,.0f}")
        print(f"🛑 嚴格風控模式: 僅在 獲利>{self.tp_pct}% 或 虧損>{self.sl_pct}% 時賣出")
        print("-" * 80)
        print(f"{'日期':<12} {'動作':<6} {'價格':<10} {'股數':<6} {'損益/成本':<12} {'報酬率':<8} {'原因'}")
        print("-" * 80)

        start_idx = df_full.index.get_loc(df_test.index[0])
        
        for i in range(start_idx, len(df_full)):
            today_row = df_full.iloc[i]
            today_date = df_full.index[i]
            hist_snapshot = df_full.iloc[:i+1]
            if len(hist_snapshot) < 60: continue

            vp_result = VolumePriceAnalyzer.analyze(hist_snapshot)
            
            close = today_row['Close']
            ma20 = df_calc['MA20'].iloc[i]
            vol_ma20 = df_calc['Vol_MA20'].iloc[i]
            vol_ratio = (today_row['Volume'] / vol_ma20) if vol_ma20 > 0 else 1.0
            
            analysis_packet = {
                'current_price': close,
                'technical': {
                    'ma5': df_calc['MA5'].iloc[i],
                    'ma20': ma20,
                    'ma55': df_calc['MA55'].iloc[i],
                    'rsi': df_calc['RSI'].iloc[i]
                },
                'bias_20': df_calc['Bias_20'].iloc[i],
                'volume_price': vp_result,
                'volume_ratio': vol_ratio
            }
            
            signals = self._detect_signals(analysis_packet)
            
            # === [核心] 僅依賴 停損/停利 的出場檢查 ===
            if self.inventory > 0:
                profit_pct = (close - self.avg_cost) / self.avg_cost * 100
                
                # 停利檢查 (Take Profit)
                if profit_pct >= self.tp_pct:
                    signals['sell_signal'] = True
                    signals['sell_reason'] = f'🔥 停利出場 (+{profit_pct:.1f}%)'
                
                # 停損檢查 (Stop Loss)
                elif profit_pct <= -self.sl_pct:
                    signals['sell_signal'] = True
                    signals['sell_reason'] = f'❄️ 停損出場 ({profit_pct:.1f}%)'
                
                # [注意] 這裡不再有 else: check technical sell signals
                # 除非觸發 TP/SL，否則死抱不放

            self._execute_trade(today_date, close, signals)

        self._settle_up(df_full['Close'].iloc[-1])

    def _execute_trade(self, date, price, signals):
        date_str = date.strftime('%Y-%m-%d')
        
        # 賣出邏輯
        if self.inventory > 0:
            if signals['sell_signal']:
                revenue = price * self.inventory
                cost = revenue * (0.001425 + 0.003)
                net_revenue = revenue - cost
                
                trade_pnl = net_revenue - (self.avg_cost * self.inventory * 1.001425)
                roi = (trade_pnl / (self.avg_cost * self.inventory * 1.001425)) * 100
                
                self.cash += net_revenue
                color_pnl = f"${trade_pnl:+,.0f}"
                
                print(f"{date_str:<12} 賣出   {price:<10.2f} {self.inventory:<6} {color_pnl:<12} {roi:>+6.1f}%  {signals['sell_reason']}")
                
                self.trade_log.append({
                    'type': 'SELL', 'date': date_str, 'price': price, 
                    'qty': self.inventory, 'pnl': trade_pnl, 'reason': signals['sell_reason']
                })
                self.inventory = 0
                self.avg_cost = 0

        # 買進邏輯
        elif self.inventory == 0:
            if signals['buy_signal']:
                max_qty = 2000
                afford_qty = int(self.cash / (price * 1.001425))
                qty = min(max_qty, afford_qty)
                
                if qty >= 100:
                    cost_amount = price * qty * 1.001425
                    self.cash -= cost_amount
                    self.inventory = qty
                    self.avg_cost = price
                    
                    print(f"{date_str:<12} 買進   {price:<10.2f} {qty:<6} ${-cost_amount:<11,.0f} {'-':<8} {signals['buy_reason']}")
                    
                    self.trade_log.append({
                        'type': 'BUY', 'date': date_str, 'price': price, 
                        'qty': qty, 'reason': signals['buy_reason']
                    })

    def _settle_up(self, current_price):
        market_value = self.inventory * current_price
        total_assets = self.cash + market_value
        pnl = total_assets - self.initial_capital
        ret = (pnl / self.initial_capital) * 100
        
        print("-" * 80)
        print(f"🏁 回測結束")
        print(f"   最終持有: {self.inventory} 股 (現價: {current_price:.2f})")
        if self.inventory > 0:
            unrealized = (current_price - self.avg_cost) * self.inventory
            unrealized_pct = (current_price - self.avg_cost) / self.avg_cost * 100
            print(f"   未實現損益: ${unrealized:,.0f} ({unrealized_pct:+.2f}%)")
            
        print(f"   帳戶餘額: ${self.cash:,.0f}")
        print(f"   資產總值: ${total_assets:,.0f}")
        
        color = "🟢" if pnl >= 0 else "🔴"
        print(f"   總損益  : {color} ${pnl:+,.0f} ({ret:+.2f}%)")
        print("-" * 80)

if __name__ == "__main__":
    print("=== 量化策略回測工具 (純風控出場模式) ===")
    
    symbol = input("請輸入股票代號 (如 2330): ").strip()
    
    try:
        cap_input = input("請輸入起始資金 (預設 1,000,000): ").strip()
        capital = float(cap_input) if cap_input else 1000000
    except:
        capital = 1000000
    
    try:
        tp_input = input("請輸入停利 % (預設 20): ").strip()
        tp_pct = float(tp_input) if tp_input else 20.0
    except:
        tp_pct = 20.0
        
    try:
        sl_input = input("請輸入停損 % (預設 10): ").strip()
        sl_pct = float(sl_input) if sl_input else 10.0
    except:
        sl_pct = 10.0
        
    date_input = input("請輸入回測開始日期 (YYYY-MM-DD, 預設為3個月前): ").strip()
    if date_input:
        try:
            start_date = parse(date_input)
        except:
            print("日期格式錯誤，使用預設值。")
            start_date = datetime.datetime.now() - datetime.timedelta(days=90)
    else:
        start_date = datetime.datetime.now() - datetime.timedelta(days=90)
        
    bt = Backtester(symbol, start_date, capital, tp_pct, sl_pct)
    bt.run()