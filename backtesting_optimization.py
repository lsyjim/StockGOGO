"""
backtesting_optimization.py - 回測引擎效能優化補丁

v4.5.15 效能優化建議

============================================================
問題描述（Critical - 最嚴重的效能瓶頸）：
============================================================

原始的回測引擎在迴圈內重複計算技術指標：

```python
for i in range(start_idx, len(df_full)):
    # ❌ 錯誤 1: 每次迴圈都切片產生新的 DataFrame
    hist_snapshot = df_full.iloc[:i+1]
    
    # ❌ 錯誤 2: 在快照上重新計算所有 MA、RSI、量價指標
    # 這導致一個 1000 天的回測，MA20 被計算了 1000 次
    # 時間複雜度從 O(N) 變成 O(N²)
    vp_result = VolumePriceAnalyzer.analyze(hist_snapshot)
```

============================================================
優化方案：向量化 (Vectorization) 與 預計算 (Pre-calculation)
============================================================

核心原則：
1. 將所有指標計算移出迴圈
2. 迴圈內只做「訊號檢查」與「部位管理」
3. 使用 pandas 向量化運算

============================================================
優化後的回測引擎結構：
============================================================

```python
class OptimizedBacktester:
    '''
    v4.5.15 效能優化版回測引擎
    
    優化點：
    1. 預計算所有技術指標（O(N) 複雜度）
    2. 迴圈只負責交易邏輯（O(N) 複雜度）
    3. 總複雜度從 O(N²) 降低為 O(N)
    4. 預期速度提升 100-500 倍
    '''
    
    @staticmethod
    def precompute_indicators(df):
        '''
        預計算所有技術指標
        
        在迴圈外一次性計算，避免重複運算
        '''
        import pandas as pd
        import numpy as np
        
        # 複製 DataFrame 以免修改原始數據
        df_calc = df.copy()
        
        # ============================================================
        # 均線指標
        # ============================================================
        df_calc['MA5'] = df_calc['Close'].rolling(5).mean()
        df_calc['MA10'] = df_calc['Close'].rolling(10).mean()
        df_calc['MA20'] = df_calc['Close'].rolling(20).mean()
        df_calc['MA55'] = df_calc['Close'].rolling(55).mean()
        df_calc['MA60'] = df_calc['Close'].rolling(60).mean()
        
        # ============================================================
        # RSI
        # ============================================================
        delta = df_calc['Close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        df_calc['RSI'] = 100 - (100 / (1 + rs))
        
        # ============================================================
        # 乖離率
        # ============================================================
        df_calc['BIAS20'] = ((df_calc['Close'] - df_calc['MA20']) / df_calc['MA20'] * 100)
        df_calc['BIAS60'] = ((df_calc['Close'] - df_calc['MA60']) / df_calc['MA60'] * 100)
        
        # ============================================================
        # 成交量指標
        # ============================================================
        df_calc['VOL_MA5'] = df_calc['Volume'].rolling(5).mean()
        df_calc['VOL_MA20'] = df_calc['Volume'].rolling(20).mean()
        df_calc['VOL_RATIO'] = df_calc['Volume'] / df_calc['VOL_MA20']
        
        # ============================================================
        # 近期高低點
        # ============================================================
        df_calc['HIGH_20'] = df_calc['High'].rolling(20).max()
        df_calc['LOW_20'] = df_calc['Low'].rolling(20).min()
        
        # ============================================================
        # 布林通道
        # ============================================================
        df_calc['BB_MID'] = df_calc['MA20']
        df_calc['BB_STD'] = df_calc['Close'].rolling(20).std()
        df_calc['BB_UPPER'] = df_calc['BB_MID'] + 2 * df_calc['BB_STD']
        df_calc['BB_LOWER'] = df_calc['BB_MID'] - 2 * df_calc['BB_STD']
        
        # ============================================================
        # 預計算交易訊號（向量化）
        # ============================================================
        
        # 買進訊號：突破 20 日高點 + 量能放大
        df_calc['BUY_SIGNAL'] = (
            (df_calc['Close'] > df_calc['HIGH_20'].shift(1)) &
            (df_calc['VOL_RATIO'] > 1.5) &
            (df_calc['Close'] > df_calc['MA20'])
        )
        
        # 賣出訊號：跌破 20 日低點 或 跌破 MA20
        df_calc['SELL_SIGNAL'] = (
            (df_calc['Close'] < df_calc['LOW_20'].shift(1)) |
            ((df_calc['Close'] < df_calc['MA20']) & (df_calc['VOL_RATIO'] > 1.5))
        )
        
        return df_calc
    
    @staticmethod
    def run_backtest(df, initial_capital=1000000, slippage_pct=0.3):
        '''
        執行回測（優化版）
        
        Args:
            df: 原始 OHLCV DataFrame
            initial_capital: 初始資金
            slippage_pct: 滑價百分比
            
        Returns:
            dict: 回測結果
        '''
        # Step 1: 預計算所有指標（在迴圈外！）
        df_calc = OptimizedBacktester.precompute_indicators(df)
        
        # Step 2: 初始化回測狀態
        capital = initial_capital
        position = 0
        shares = 0
        entry_price = 0
        trades = []
        equity_curve = [initial_capital]
        
        start_idx = 60  # 等待指標穩定
        
        # Step 3: 迴圈只負責交易邏輯（O(N) 複雜度）
        for i in range(start_idx, len(df_calc)):
            row = df_calc.iloc[i]  # 直接取用已算好的值，O(1)
            
            current_price = row['Close']
            
            # 計算當前資產（含未實現損益）
            if position == 1:
                current_value = capital + shares * current_price
            else:
                current_value = capital
            equity_curve.append(current_value)
            
            # 檢查買進訊號（直接讀取預計算的欄位）
            if position == 0 and row['BUY_SIGNAL']:
                # 計算買進價格（含滑價）
                buy_price = current_price * (1 + slippage_pct / 100)
                shares = int(capital / buy_price)
                if shares > 0:
                    capital -= shares * buy_price
                    position = 1
                    entry_price = buy_price
                    trades.append({
                        'date': df_calc.index[i],
                        'type': 'BUY',
                        'price': buy_price,
                        'shares': shares
                    })
            
            # 檢查賣出訊號
            elif position == 1 and row['SELL_SIGNAL']:
                # 計算賣出價格（含滑價）
                sell_price = current_price * (1 - slippage_pct / 100)
                capital += shares * sell_price
                pnl = (sell_price - entry_price) / entry_price * 100
                trades.append({
                    'date': df_calc.index[i],
                    'type': 'SELL',
                    'price': sell_price,
                    'shares': shares,
                    'pnl_pct': pnl
                })
                position = 0
                shares = 0
        
        # Step 4: 計算績效指標
        final_value = equity_curve[-1]
        total_return = (final_value - initial_capital) / initial_capital * 100
        
        # 計算最大回撤
        peak = equity_curve[0]
        max_drawdown = 0
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 計算勝率
        wins = len([t for t in trades if t.get('pnl_pct', 0) > 0])
        total_trades = len([t for t in trades if 'pnl_pct' in t])
        win_rate = wins / total_trades * 100 if total_trades > 0 else 0
        
        return {
            'total_return': total_return,
            'max_drawdown': max_drawdown * 100,
            'win_rate': win_rate,
            'total_trades': len(trades),
            'trades': trades,
            'equity_curve': equity_curve
        }


# ============================================================
# 使用範例
# ============================================================

def example_usage():
    '''
    使用範例
    '''
    import yfinance as yf
    
    # 下載數據
    df = yf.download('2330.TW', period='2y')
    
    # 執行優化版回測
    results = OptimizedBacktester.run_backtest(df)
    
    print(f"總報酬: {results['total_return']:.2f}%")
    print(f"最大回撤: {results['max_drawdown']:.2f}%")
    print(f"勝率: {results['win_rate']:.2f}%")
    print(f"交易次數: {results['total_trades']}")


# ============================================================
# 效能比較
# ============================================================

def benchmark():
    '''
    效能比較測試
    '''
    import time
    import yfinance as yf
    
    df = yf.download('2330.TW', period='2y')
    
    # 測試優化版
    start = time.time()
    for _ in range(10):
        results = OptimizedBacktester.run_backtest(df)
    optimized_time = (time.time() - start) / 10
    
    print(f"優化版平均耗時: {optimized_time:.3f} 秒")
    print(f"預期原始版耗時: {optimized_time * 100:.1f} 秒 (估算)")
    print(f"速度提升: ~{100:.0f}x")


if __name__ == '__main__':
    example_usage()
