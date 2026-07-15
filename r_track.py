"""
r_track.py - build_prompt_12：R 軌（超跌反彈獨立軌）

R 軌是一條與 A/B/C 動能等級完全獨立的逆勢短線軌道（見 research_r_signal.md §7）。
硬停損已被 BP11 研究否證（mean 4.37→1.43），出場唯一規則為時間出場（10 交易日）。

紅線：R 軌只寫獨立欄位（r_signal / r_strength / r_exit_date），
絕不觸碰 grade/action_code/建議文字（依據 research_r_signal.md §7）。
本檔案任何位置都不得出現硬停損 / 停損邏輯。
"""


def _nth_trading_day_after(as_of_str, trading_days, n):
    """trading_days: 由舊到新排序的交易日字串 list（含未來日）。回傳 as_of 之後第 n 個交易日；
    未來日不足（近端訊號）→ 回傳 None（呼叫端顯示為預估）。"""
    if not trading_days or n < 1:
        return None
    future = [d for d in trading_days if d > as_of_str]
    if len(future) < n:
        return None
    return future[n - 1]


def evaluate_r_track(result, as_of_str, trading_days=None):
    """獨立評估 R 軌。回傳 dict：
       {'r_signal': 'R-TRADE'|'R-WATCH'|None, 'r_strength': 'strong'|'moderate'|None, 'r_exit_date': 'YYYY-MM-DD'|None}
    紅線：本函式不修改 result 的任何動能欄位，只回傳獨立 dict。
    R_TRACK_ENABLED=False → 一律回 {'r_signal': None, 'r_strength': None, 'r_exit_date': None}（動能管線零影響）。"""
    from config import QuantConfig as _QC
    out = {'r_signal': None, 'r_strength': None, 'r_exit_date': None}
    if not getattr(_QC, 'R_TRACK_ENABLED', False):
        return out
    mr = (result.get('mean_reversion') or {})
    lbs = (mr.get('left_buy_signal') or {})
    if not lbs.get('triggered'):
        return out
    reg = (result.get('market_regime') or {})
    trend = reg.get('trend_direction') if reg.get('available') else None
    # r_signal：盤整→R-TRADE（可交易）；多頭/空頭→R-WATCH（僅參考）
    if trend in getattr(_QC, 'R_TRADE_REGIMES', ['盤整']):
        out['r_signal'] = 'R-TRADE'
    elif trend in ('多頭', '空頭'):
        out['r_signal'] = 'R-WATCH'
    else:
        return out  # regime 不明 → 不出 R 訊號
    # r_strength：cond3（strong 由 analyzer 給）或多重確認（trigger_reasons>=2）→ strong
    n_reasons = len(lbs.get('trigger_reasons') or [])
    out['r_strength'] = 'strong' if (lbs.get('strength') == 'strong' or n_reasons >= 2) else 'moderate'
    # r_exit_date：第 R_HOLD_DAYS 個交易日（時間出場，無停損）
    if trading_days:
        out['r_exit_date'] = _nth_trading_day_after(as_of_str, trading_days,
                                                    getattr(_QC, 'R_HOLD_DAYS', 10))
    return out
