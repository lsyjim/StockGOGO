"""
diagnose_v_pattern.py
用法：python3 diagnose_v_pattern.py [股票代碼]
例如：python3 diagnose_v_pattern.py 2313
若不傳參數，預設分析 2313

功能：逐關印出 V型反轉偵測的實際數字，
      讓你對照日線圖，看清楚演算法「看到了什麼」
"""
import warnings, sys
warnings.filterwarnings('ignore')

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else '2313'

# ── 抓資料 ──────────────────────────────────────────────────────────────────
print(f"\n{'='*65}")
print(f"  {SYMBOL} — V型反轉形態診斷報告")
print(f"{'='*65}\n")

try:
    import yfinance as yf
    ticker = yf.Ticker(f"{SYMBOL}.TW")
    df = ticker.history(period="4mo")
    df = df[['Open','High','Low','Close','Volume']].dropna()
    import pandas as pd
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index()
except Exception as e:
    print(f"yfinance 抓資料失敗：{e}")
    print("請確認已安裝 yfinance：pip install yfinance")
    sys.exit(1)

if len(df) < 30:
    print(f"資料不足（只有{len(df)}根），無法分析")
    sys.exit(1)

print(f"資料範圍：{df.index[0].date()} ~ {df.index[-1].date()}，共 {len(df)} 根K棒")
print(f"最新收盤：{df['Close'].iloc[-1]:.2f}")
print()

# ── 參數（與 PatternConfig 預設值完全一致）──────────────────────────────────
LOOKBACK         = 60    # 取最近60天
V_DROP_LOOKBACK  = 5     # 急跌判斷回看天數
V_MIN_DROP_PCT   = 0.05  # 急跌最小幅度 5%
V_LOWER_SHADOW_R = 2.0   # 下影長 > 實體 × 2
V_MIN_REBOUND_R  = 0.50  # 需收復跌幅的 50%
PRIOR_TREND_LOOK = 20    # 前置趨勢回看天數
PRIOR_TREND_MIN  = 0.10  # 前置趨勢最小跌幅 10%

# 準備資料
import pandas as pd
df_r    = df.tail(LOOKBACK).copy().reset_index(drop=True)
recent  = df_r.tail(20).copy().reset_index(drop=True)
r_off   = len(df_r) - 20   # recent 在 df_r 中的起始偏移
df_dated = df.tail(LOOKBACK).copy().reset_index()
date_col = df_dated.columns[0]

# ── 關卡 1：找最低點 ─────────────────────────────────────────────────────────
print("【關卡1】 最近20根K棒中找最低點")
print("─" * 50)
min_idx_r   = int(recent['Low'].idxmin())
min_idx_dfr = r_off + min_idx_r
min_price   = recent['Low'].iloc[min_idx_r]
min_date    = df_dated.iloc[min_idx_dfr][date_col]

print(f"  最低點日期：{min_date.strftime('%Y/%m/%d')}")
print(f"  最低點價格：{min_price:.2f}")
print(f"  位置（0=最舊 19=最新）：{min_idx_r}")
boundary_ok = 3 <= min_idx_r <= 16
print(f"  邊界檢查（需在3~16）：{'✓ 通過' if boundary_ok else '✗ 失敗 → 停止，不觸發V型反轉'}")
print()
if not boundary_ok:
    print(">>> 最低點在邊界，演算法不觸發V型反轉")
    sys.exit(0)

# ── 關卡 2：急跌幅度 ─────────────────────────────────────────────────────────
print("【關卡2】 急跌幅度（最低點前5根最高 → 最低點）")
print("─" * 50)
pre_start     = max(0, min_idx_r - V_DROP_LOOKBACK)
ph_slice      = recent['High'].iloc[pre_start:min_idx_r]
pre_drop_high = ph_slice.max()
ph_idx        = int(ph_slice.idxmax())
ph_date       = df_dated.iloc[r_off + ph_idx][date_col]
drop_pct      = (min_price - pre_drop_high) / pre_drop_high
sharp_pass    = drop_pct <= -V_MIN_DROP_PCT

print(f"  起跌高點日期：{ph_date.strftime('%Y/%m/%d')}")
print(f"  起跌高點價格：{pre_drop_high:.2f}  ← 這是 V 型反轉的「目標價」")
print(f"  最低點價格：  {min_price:.2f}")
print(f"  實際跌幅：    {drop_pct*100:.2f}%")
print(f"  門檻：需 ≤ -{V_MIN_DROP_PCT*100:.0f}%  →  {'✓ 通過' if sharp_pass else '✗ 不通過 → 停止，急跌幅度不足'}")
print()
if not sharp_pass:
    print(">>> 急跌幅度不足，演算法不偵測V型反轉")
    sys.exit(0)

# ── 關卡 3：關鍵K棒 ──────────────────────────────────────────────────────────
print("【關卡3】 關鍵K棒（最低點當日或次日）")
print("─" * 50)
found_candle = False
candle_type  = ''
abs_min_idx  = len(df) - 20 + min_idx_r

for ci in [min_idx_r, min(min_idx_r + 1, 19)]:
    row = recent.iloc[ci]
    o, c, h, l = row['Open'], row['Close'], row['High'], row['Low']
    body         = abs(c - o)
    lower_shadow = min(o, c) - l
    shadow_ratio = lower_shadow / body if body > 0 else 0
    direction    = "▲紅K" if c >= o else "▼黑K"
    d_date       = df_dated.iloc[r_off + ci][date_col]

    print(f"  [{ci}] {d_date.strftime('%Y/%m/%d')} {direction}")
    print(f"       O:{o:.2f}  H:{h:.2f}  L:{l:.2f}  C:{c:.2f}")
    print(f"       實體={body:.2f}  下影={lower_shadow:.2f}  下影/實體={shadow_ratio:.2f}x（門檻≥{V_LOWER_SHADOW_R}x）", end='')

    if body > 0 and lower_shadow > body * V_LOWER_SHADOW_R:
        print("  ✓ 長下影線！")
        found_candle, candle_type = True, f"長下影線 {shadow_ratio:.1f}x"
        break
    else:
        print("  ✗ 未達長下影線")

    if ci > 0 and c > o:
        prev = recent.iloc[ci - 1]
        po, pc = prev['Open'], prev['Close']
        engulf = (c > max(po, pc)) and (o < min(po, pc))
        print(f"       吞噬紅K：{'✓' if engulf else '✗'}  （前日實體 {min(po,pc):.2f}~{max(po,pc):.2f}）")
        if engulf:
            found_candle, candle_type = True, "吞噬紅K"
            break

print()
if not found_candle:
    print("  → ✗ 無關鍵K棒，演算法不觸發V型反轉")
    sys.exit(0)
else:
    print(f"  → ✓ 關鍵K棒：{candle_type}")
    print()

# ── 關卡 4：反彈幅度 ─────────────────────────────────────────────────────────
print("【關卡4】 反彈幅度（最低點 → 現收）")
print("─" * 50)
current_close    = df['Close'].iloc[-1]
rebound_pct      = (current_close - min_price) / min_price
required_rebound = abs(drop_pct) * V_MIN_REBOUND_R
rebound_pass     = rebound_pct >= required_rebound

print(f"  最低點：{min_price:.2f}  現收：{current_close:.2f}")
print(f"  實際反彈：{rebound_pct*100:.2f}%")
print(f"  門檻：跌幅{abs(drop_pct)*100:.1f}% × {V_MIN_REBOUND_R*100:.0f}% = {required_rebound*100:.2f}%")
print(f"  → {'✓ 通過' if rebound_pass else '✗ 不通過 → 停止，反彈幅度不足'}")
print()
if not rebound_pass:
    print(">>> 反彈幅度不足，演算法不觸發V型反轉")
    sys.exit(0)

# ── 關卡 5（前置趨勢）+ 關卡 6（確立判斷）────────────────────────────────────
print("【關卡5】 前置下跌趨勢")
print("─" * 50)
trend_start  = max(0, abs_min_idx - PRIOR_TREND_LOOK)
ts           = df['Close'].iloc[trend_start:abs_min_idx+1]
trend_change = (ts.iloc[-1] - ts.iloc[0]) / ts.iloc[0]
trend_pass   = trend_change <= -PRIOR_TREND_MIN

print(f"  趨勢起點：{df.index[trend_start].strftime('%Y/%m/%d')}  收={ts.iloc[0]:.2f}")
print(f"  最低點：  {df.index[abs_min_idx].strftime('%Y/%m/%d')}  收={ts.iloc[-1]:.2f}")
print(f"  趨勢變化：{trend_change*100:.2f}%  （門檻：≤ -{PRIOR_TREND_MIN*100:.0f}%）")
print(f"  → {'✓ 通過' if trend_pass else '✗ 不通過 → 停止，前置下跌趨勢不足'}")
print()
if not trend_pass:
    print(">>> 前置趨勢不足，演算法不觸發V型反轉")
    sys.exit(0)

print("【關卡6】 確立 or 形成中判斷")
print("─" * 50)
ma10       = df['Close'].rolling(10).mean().iloc[-1]
above_ma   = current_close > ma10
rec_thresh = pre_drop_high * 0.8
c1         = current_close >= rec_thresh
c2         = above_ma and (rebound_pct >= abs(drop_pct) * 0.6)
confirmed  = c1 or c2
exceeded   = current_close > pre_drop_high * 1.05

print(f"  MA10 = {ma10:.2f}  站上MA10：{'是' if above_ma else '否'}")
print(f"  確立條件1：現價{current_close:.2f} ≥ 起跌點80% {rec_thresh:.2f}  →  {'✓' if c1 else '✗'}")
print(f"  確立條件2：站上MA10 + 反彈≥跌幅60%（{abs(drop_pct)*60:.1f}%）  →  {'✓' if c2 else '✗'}")
print(f"  → 狀態：{'CONFIRMED_BREAKOUT（已確立）' if confirmed else 'FORMING（形成中）'}")

if confirmed:
    print(f"\n  目標價（起跌點）= {pre_drop_high:.2f}")
    print(f"  現價 {current_close:.2f}  vs  目標×1.05 = {pre_drop_high*1.05:.2f}")
    if exceeded:
        print(f"  → TARGET_REACHED：目標早已超越，不輸出買進訊號（信心度降為40，score_impact=0）")
    else:
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        vol_confirmed = df['Volume'].iloc[-1] >= vol_ma5
        confidence = 80 if vol_confirmed else 60
        print(f"  → 正常確立，輸出買進訊號  信心度={confidence}%  量能確認={'是' if vol_confirmed else '否'}")

# ── 最近 20 根 K 棒對照表 ─────────────────────────────────────────────────────
print()
print("【附錄】 最近20根日K（供對照圖面）")
print("─" * 65)
print(f"  {'日期':10s}  {'方向':4s}  {'開':>7s}  {'高':>7s}  {'低':>7s}  {'收':>7s}  {'量比':>5s}  備註")
print("  " + "-" * 62)
vol_ma5_ser = df['Volume'].rolling(5).mean()
for i, (dt, row) in enumerate(df.tail(20).iterrows()):
    bar   = "▲紅" if row['Close'] >= row['Open'] else "▼黑"
    vm    = vol_ma5_ser.loc[dt]
    vr    = row['Volume'] / vm if vm > 0 else 0
    idx_in_df = len(df) - 20 + i
    note = ""
    if idx_in_df == abs_min_idx:
        note = " ← V底最低點"
    elif idx_in_df == len(df) - 20 + ph_idx + (len(df_r) - 20):
        note = " ← 起跌高點（目標價）"
    print(f"  {dt.strftime('%Y/%m/%d')}  {bar}  {row['Open']:7.2f}  {row['High']:7.2f}  {row['Low']:7.2f}  {row['Close']:7.2f}  {vr:5.1f}x{note}")

print()
print(f"{'='*65}")
print(f"  診斷完成。如有任何關卡未通過，V型反轉就不會被偵測到。")
print(f"{'='*65}\n")
