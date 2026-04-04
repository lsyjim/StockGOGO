"""
decision_engine.py - 三層決策引擎 v2.0

設計原則：
1. 三層各自獨立，有否決門檻，不通過就不進下一層
2. 各層評分不跨層混合（方向分不加進位置分，位置分不加進時機分）
3. 買點分 A/B/C 三級，而非 0-100 的模糊分數
4. 賣點分 防守 / 停利 / 反轉 三類，清楚好執行
5. 籌碼作為排序器/過濾器，不決定買賣

Layer 1 - 方向分 (Direction):
    問題：這檔股票現在的大方向值不值得看？
    否決門檻：< 40 → 直接跳過，不看下去

Layer 2 - 位置分 (Position):
    問題：現在的位置是不是適合進場？
    否決門檻：< 40 → 不買，等位置改善

Layer 3 - 時機分 (Timing):
    問題：今天是不是該動手？
    輸出：A級主攻 / B級追蹤 / C級觀察 / X無訊號
"""

from __future__ import annotations
from typing import Any


# ============================================================================
# 主引擎
# ============================================================================

class ThreeLayerEngine:

    # 各層否決門檻
    DIRECTION_VETO = 40
    POSITION_VETO  = 40

    # ─── 主入口 ──────────────────────────────────────────────────────────────

    @staticmethod
    def analyze(result: dict) -> dict:
        """
        主入口：取代舊版 DecisionMatrix.analyze(result)

        Returns:
            dict: 與舊版格式兼容的決策結果，並額外包含 three_layer 詳細分解
        """
        try:
            # Layer 1: 方向
            direction = ThreeLayerEngine.score_direction(result)
            if direction['score'] < ThreeLayerEngine.DIRECTION_VETO:
                return ThreeLayerEngine._build_skip_output(direction, result)

            # Layer 2: 位置
            position = ThreeLayerEngine.score_position(result)
            if position['score'] < ThreeLayerEngine.POSITION_VETO:
                return ThreeLayerEngine._build_wait_output(direction, position, result)

            # Layer 3: 時機
            timing = ThreeLayerEngine.score_timing(result)

            # 籌碼過濾（可能降級 timing.grade）
            chip = ThreeLayerEngine.apply_chip_filter(result, timing)

            # 賣訊檢查（優先於買訊）
            sell = ThreeLayerEngine.check_sell_signal(result)

            return ThreeLayerEngine._build_buy_output(direction, position, timing, chip, sell, result)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'available': False, 'message': f'三層引擎錯誤: {e}'}

    # ─── Layer 1: 方向分 ─────────────────────────────────────────────────────

    @staticmethod
    def score_direction(result: dict) -> dict:
        """
        方向分 (0–100)，閾值 40

        判斷邏輯：
        - 主判斷：均線排列（MA20 / MA60 / MA120 / MA240）
          → 決定 tier（強多/偏多/中性/偏空/強空）
        - 輔判斷：ADX 趨勢強度
          → 在 tier 內微調 ±10，不改變 tier

        設計意圖：
        - 4 條均線各自判斷方向，多頭條數越多分數越高
        - ADX 只能「加強」或「削弱」，不能逆轉方向
        - 分數可直接解讀：60 = 偏多但非強勢多頭
        """
        tech         = result.get('technical', {})
        wave         = result.get('wave_analysis', {})
        current      = result.get('current_price', 0)

        ma20  = tech.get('ma20',  current) or current
        ma60  = tech.get('ma60',  current) or current
        ma120 = tech.get('ma120', current) or current
        ma240 = tech.get('ma240', current) or current
        adx   = tech.get('adx', 20) or 20

        details = []

        # --- 均線多頭/空頭計數 ---
        # 每一層從上到下：價格 > MA20 > MA60 > MA120 > MA240
        bull_layers = [
            current > ma20,
            ma20    > ma60,
            ma60    > ma120,
            ma120   > ma240,
        ]
        bull_count = sum(bull_layers)
        bear_count = sum(not x for x in bull_layers)

        # 線性映射：bull_count 0→4 對應基礎分 15→80
        base_score = 15 + bull_count * 16.25  # 15, 31, 47, 63, 80

        if bull_count == 4:
            details.append('均線完全多頭排列（4/4）')
        elif bull_count == 3:
            details.append('均線偏多排列（3/4）')
        elif bull_count == 2:
            details.append('均線中性混合（2/4）')
        elif bull_count == 1:
            details.append('均線偏空排列（1/4）')
        else:
            details.append('均線完全空頭排列（0/4）')

        # --- ADX 輔助修正（最大 ±10）---
        if adx >= 30:
            adx_mod = 10
            details.append(f'趨勢強 ADX={adx:.0f}')
        elif adx >= 20:
            adx_mod = 0
            details.append(f'趨勢中 ADX={adx:.0f}')
        else:
            adx_mod = -10
            details.append(f'趨勢弱 ADX={adx:.0f}（盤整市）')

        score = max(0, min(100, int(base_score + adx_mod)))

        # 標籤
        if score >= 70:
            label = '強多頭'
        elif score >= 55:
            label = '偏多'
        elif score >= 45:
            label = '中性'
        elif score >= 30:
            label = '偏空'
        else:
            label = '強空頭'

        return {
            'score':      score,
            'label':      label,
            'details':    details,
            'bull_count': bull_count,
            'bear_count': bear_count,
        }

    # ─── Layer 2: 位置分 ─────────────────────────────────────────────────────

    @staticmethod
    def score_position(result: dict) -> dict:
        """
        位置分 (0–100)，閾值 40

        判斷邏輯：
        - 主判斷：乖離率（bias_20）— 決定基礎分，有「天花板」
          過熱（bias > +10%）→ 最高只能拿到 30 分，位置否決
        - 輔判斷 1：RSI — 調整 ±20
        - 輔判斷 2：風險報酬比 — 調整 ±15

        設計意圖：
        - 追高問題源於「過熱但其他指標補分」
        - 乖離天花板防止過熱股靠其他因子撐過位置層
        - 三個因子各司其職，不互搶主導
        """
        tech    = result.get('technical', {})
        mr      = result.get('mean_reversion', {})
        sr      = result.get('support_resistance', {})
        current = result.get('current_price', 0)

        rsi = tech.get('rsi', 50) or 50

        # 乖離率
        if mr.get('available'):
            bias_20 = mr.get('bias_analysis', {}).get('bias_20', 0) or 0
        else:
            ma20    = tech.get('ma20', current) or current
            bias_20 = ((current - ma20) / ma20 * 100) if ma20 > 0 else 0

        details = []

        # --- 乖離：主判斷（設天花板）---
        if bias_20 > 15:
            bias_base = 10
            bias_cap  = 20   # 嚴重過熱：硬上限 20，必過否決
            details.append(f'嚴重過熱 乖離{bias_20:+.1f}%（天花板 {bias_cap}）')
        elif bias_20 > 8:
            bias_base = 25
            bias_cap  = 35   # 過熱：硬上限 35
            details.append(f'偏熱 乖離{bias_20:+.1f}%（天花板 {bias_cap}）')
        elif bias_20 > 3:
            bias_base = 45
            bias_cap  = 100  # 略熱：無天花板，靠 RSI/RR 決定
            details.append(f'略熱 乖離{bias_20:+.1f}%')
        elif bias_20 >= -5:
            bias_base = 65
            bias_cap  = 100  # 理想位置
            details.append(f'理想位置 乖離{bias_20:+.1f}%')
        elif bias_20 >= -10:
            bias_base = 55
            bias_cap  = 100  # 輕微超跌
            details.append(f'輕微超跌 乖離{bias_20:+.1f}%')
        else:
            bias_base = 40
            bias_cap  = 75   # 深度超跌：可能持續下跌，略壓上限
            details.append(f'深度超跌 乖離{bias_20:+.1f}%（小心接刀）')

        # --- RSI 輔助 ±20 ---
        if rsi > 80:
            rsi_adj = -20
            details.append(f'RSI超買 {rsi:.0f}')
        elif rsi > 70:
            rsi_adj = -10
            details.append(f'RSI偏熱 {rsi:.0f}')
        elif 40 <= rsi <= 65:
            rsi_adj = 15
            details.append(f'RSI健康 {rsi:.0f}')
        elif rsi < 30:
            rsi_adj = 10
            details.append(f'RSI超賣 {rsi:.0f}（可能反彈）')
        else:
            rsi_adj = 0
            details.append(f'RSI中性 {rsi:.0f}')

        # --- 風險報酬比 ±15 ---
        take_profit = sr.get('take_profit', current * 1.1)
        stop_loss   = sr.get('stop_loss',   current * 0.95)
        if isinstance(take_profit, str): take_profit = current * 1.1
        if isinstance(stop_loss,   str): stop_loss   = current * 0.95

        potential_gain = take_profit - current
        potential_loss = current - stop_loss
        rr = potential_gain / potential_loss if potential_loss > 0 else 0

        if rr >= 2.5:
            rr_adj = 15
            details.append(f'RR={rr:.1f} 優秀')
        elif rr >= 1.5:
            rr_adj = 5
            details.append(f'RR={rr:.1f} 合格')
        else:
            rr_adj = -15
            details.append(f'RR={rr:.1f} 不足')

        raw_score = bias_base + rsi_adj + rr_adj
        score     = max(0, min(bias_cap, raw_score))   # 套用天花板

        if score >= 70:
            label = '位置優異'
        elif score >= 55:
            label = '位置合理'
        elif score >= 40:
            label = '位置勉強'
        else:
            label = '位置不佳'

        return {
            'score':    score,
            'label':    label,
            'details':  details,
            'bias_20':  round(bias_20, 2),
            'rsi':      rsi,
            'rr_ratio': round(rr, 2),
        }

    # ─── Layer 3: 時機分 ─────────────────────────────────────────────────────

    @staticmethod
    def score_timing(result: dict) -> dict:
        """
        時機分：輸出 A / B / C / X 分級，而非數字

        A 主攻：量價到位 + 形態確立，立即行動
        B 追蹤：訊號形成但未完整確認，等待
        C 觀察：環境偏多但無催化劑，列入名單
        X 無訊號：不滿足任何觸發條件

        設計意圖：
        - 分級比數字更好執行：A = 打，B = 等，C = 看
        - 先判斷 A，再判斷 B，不做加分累積
        - 籌碼過濾器在此層之後可能降級 A→B 或 B→C
        """
        wave    = result.get('wave_analysis', {})
        pattern = result.get('pattern_analysis', {})
        vp      = result.get('volume_price', {})
        mr      = result.get('mean_reversion', {})
        current = result.get('current_price', 0)

        triggers: list[str] = []
        grade = 'X'

        # ── A 級觸發條件（任一即可）──────────────────────────────
        # A1: 三盤突破 + 帶量確認
        if wave.get('available'):
            bo = wave.get('breakout_signal', {})
            if bo.get('detected') and bo.get('volume_confirmed'):
                triggers.append('三盤突破（帶量確認）')
                grade = 'A'

        # A2: VP05 帶量突破
        if grade != 'A' and vp.get('available'):
            for sig in vp.get('signals', []):
                if sig.get('code') == 'VP05':
                    triggers.append('帶量突破 VP05')
                    grade = 'A'
                    break

        # A3: 底部形態確立（CONFIRMED）
        if grade != 'A' and pattern.get('detected'):
            if (pattern.get('pattern_type') == 'bottom' and
                    'CONFIRMED' in pattern.get('status', '')):
                triggers.append(f'{pattern.get("pattern_name", "底部形態")}突破確立')
                grade = 'A'

        # ── B 級觸發條件（任一即可）──────────────────────────────
        if grade != 'A':
            # B1: 三盤突破但量能不足
            if wave.get('available'):
                bo = wave.get('breakout_signal', {})
                if bo.get('detected') and not bo.get('volume_confirmed'):
                    triggers.append('三盤突破（量能待確認）')
                    grade = 'B'

            # B2: 超跌反彈左側訊號
            if grade != 'B' and mr.get('available'):
                left_buy = mr.get('left_buy_signal', {})
                if left_buy.get('triggered'):
                    triggers.append('超跌反彈訊號')
                    grade = 'B'

            # B3: 底部形態形成中，且接近頸線（< 3%）
            if grade != 'B' and pattern.get('detected'):
                if (pattern.get('pattern_type') == 'bottom' and
                        'FORMING' in pattern.get('status', '')):
                    neckline = pattern.get('neckline_price', 0)
                    if neckline > 0 and current > 0:
                        dist_pct = (neckline - current) / current * 100
                        if 0 < dist_pct < 3:
                            triggers.append(
                                f'{pattern.get("pattern_name", "底部形態")}形成中'
                                f'（距頸線 {dist_pct:.1f}%）'
                            )
                            grade = 'B'

        # ── C 級：環境偏多但無特定觸發 ──────────────────────────
        if grade == 'X':
            if wave.get('is_bullish_env'):
                triggers.append('多頭環境，等待催化劑')
                grade = 'C'
            else:
                triggers.append('無明確進場訊號')

        _grade_labels = {
            'A': '主攻（立即進場）',
            'B': '追蹤（等待確認）',
            'C': '觀察（記錄追蹤）',
            'X': '無訊號',
        }

        return {
            'grade':    grade,
            'label':    _grade_labels[grade],
            'triggers': triggers,
        }

    # ─── 籌碼過濾器 ──────────────────────────────────────────────────────────

    @staticmethod
    def apply_chip_filter(result: dict, timing: dict) -> dict:
        """
        籌碼：排序器 + 過濾器，不做主判斷

        用途：
        - ranking_boost：同類型股票中，籌碼強的排前面（+2/+1/0/-1/-2）
        - 過濾降級：B/C 且法人連賣 ≥ 5 天 → 降為 C/X

        不用途：
        - 不加分到 direction/position 分
        - 不單獨決定買賣
        """
        chip = result.get('chip_analysis', {})

        if not chip.get('available'):
            return {'filter': 'neutral', 'note': '無籌碼資料', 'ranking_boost': 0}

        consecutive_buy  = chip.get('consecutive_buy_days',  0) or 0
        consecutive_sell = chip.get('consecutive_sell_days', 0) or 0
        foreign_net      = chip.get('foreign_net', 0) or 0

        notes: list[str] = []
        ranking_boost = 0

        # 排序分數
        if consecutive_buy >= 5:
            ranking_boost = 2
            notes.append(f'法人連買 {consecutive_buy} 天（強）')
        elif consecutive_buy >= 3:
            ranking_boost = 1
            notes.append(f'法人連買 {consecutive_buy} 天')
        elif consecutive_sell >= 5:
            ranking_boost = -2
            notes.append(f'法人連賣 {consecutive_sell} 天（警示）')
        elif consecutive_sell >= 3:
            ranking_boost = -1
            notes.append(f'法人連賣 {consecutive_sell} 天')

        if foreign_net > 0:
            notes.append(f'外資淨買 {foreign_net:,} 張')
        elif foreign_net < 0:
            notes.append(f'外資淨賣 {abs(foreign_net):,} 張')

        # 降級邏輯（只在邊緣情況起作用）
        filter_action = 'pass'
        grade = timing.get('grade', 'C')

        if consecutive_sell >= 5 and grade in ('B', 'C'):
            filter_action = 'downgrade'
            if grade == 'B':
                timing['grade'] = 'C'
                timing['label'] = '觀察（籌碼降級）'
                notes.append('B→C 籌碼持續惡化')
            else:
                timing['grade'] = 'X'
                timing['label'] = '無訊號（籌碼出場）'
                notes.append('C→X 籌碼惡化，跳過')

        return {
            'filter':        filter_action,
            'ranking_boost': ranking_boost,
            'note':          '；'.join(notes) if notes else '籌碼中性',
        }

    # ─── 賣訊檢查 ────────────────────────────────────────────────────────────

    @staticmethod
    def check_sell_signal(result: dict) -> dict:
        """
        賣訊：3 種類型，清楚分層

        1. 防守型 (DEFENSIVE)：停損 / 跌破關鍵均線
           → 最高優先，severity='urgent'
        2. 停利型 (PROFIT_TAKE)：過熱賣訊 / 移動停利
           → severity='warning'
        3. 反轉型 (REVERSAL)：頭部形態確立 / 籌碼嚴重惡化
           → severity 視嚴重程度而定

        設計意圖：
        - 賣點不超過 3 類，每類有明確觸發條件
        - urgent 訊號 → action_code = SELL
        - warning 訊號 → action_code = HOLD（注意）
        """
        tech    = result.get('technical',      {})
        wave    = result.get('wave_analysis',  {})
        mr      = result.get('mean_reversion', {})
        pattern = result.get('pattern_analysis', {})
        chip    = result.get('chip_analysis',  {})
        current = result.get('current_price',  0)

        ma20 = tech.get('ma20', 0) or 0
        sell_signals: list[dict] = []

        # ── 1. 防守型 ─────────────────────────────────────────────
        # 1a: 三盤跌破
        if wave.get('available'):
            bd = wave.get('breakdown_signal', {})
            if bd.get('detected'):
                sell_signals.append({
                    'type':     'DEFENSIVE',
                    'reason':   '三盤跌破，趨勢轉空',
                    'severity': 'urgent',
                })

        # 1b: 收盤跌破 MA20 超過 2%
        if ma20 > 0 and current < ma20 * 0.98:
            sell_signals.append({
                'type':     'DEFENSIVE',
                'reason':   f'跌破 MA20（現價 {current:.2f} < MA20 {ma20:.2f} ×0.98）',
                'severity': 'warning',
            })

        # ── 2. 停利型 ─────────────────────────────────────────────
        if mr.get('available'):
            left_sell = mr.get('left_sell_signal', {})
            if left_sell.get('triggered'):
                reasons = '、'.join(left_sell.get('trigger_reasons', ['過熱']))
                sell_signals.append({
                    'type':     'PROFIT_TAKE',
                    'reason':   f'過熱賣訊：{reasons}',
                    'severity': 'warning',
                })

        # ── 3. 反轉型 ─────────────────────────────────────────────
        # 3a: 頭部形態確立
        if (pattern.get('detected') and
                pattern.get('pattern_type') == 'top' and
                'CONFIRMED' in pattern.get('status', '')):
            sell_signals.append({
                'type':     'REVERSAL',
                'reason':   f'{pattern.get("pattern_name", "頭部形態")}確立，趨勢反轉',
                'severity': 'urgent',
            })

        # 3b: 法人連賣 ≥ 7 天
        if chip.get('available'):
            csell = chip.get('consecutive_sell_days', 0) or 0
            if csell >= 7:
                sell_signals.append({
                    'type':     'REVERSAL',
                    'reason':   f'法人連賣 {csell} 天，籌碼嚴重惡化',
                    'severity': 'warning',
                })

        if not sell_signals:
            return {'triggered': False, 'primary': None, 'all': []}

        # urgent 優先
        urgent = [s for s in sell_signals if s['severity'] == 'urgent']
        primary = urgent[0] if urgent else sell_signals[0]
        return {'triggered': True, 'primary': primary, 'all': sell_signals}

    # ─── 目標價計算（簡化版）────────────────────────────────────────────────

    @staticmethod
    def _compute_targets(result: dict, is_buy: bool) -> dict:
        """
        計算目標價與停損，作為報告使用

        優先順序：
        1. 形態學測幅
        2. 支撐/壓力位
        3. ATR 估算
        """
        current = result.get('current_price', 0)
        if current <= 0:
            return {'available': False}

        pattern = result.get('pattern_analysis', {})
        sr      = result.get('support_resistance', {})
        tech    = result.get('technical', {})

        target_price = 0
        stop_loss    = 0
        source       = ''

        # 1. 形態測幅（最高優先）
        if pattern.get('detected') and pattern.get('target_price', 0) > 0:
            pt   = pattern['pattern_type']
            tgt  = pattern['target_price']
            stop = pattern.get('stop_loss', 0)
            if (pt == 'bottom' and is_buy) or (pt == 'top' and not is_buy):
                target_price = tgt
                stop_loss    = stop
                source       = f'{pattern.get("pattern_name", "形態")}測幅'

        # 2. 支撐/壓力位
        if target_price <= 0:
            if is_buy:
                r1 = sr.get('resistance1', 0)
                s1 = sr.get('support1',    0)
                target_price = r1 if r1 > current else round(current * 1.08, 2)
                stop_loss    = s1 if (s1 > 0 and s1 < current) else round(current * 0.93, 2)
                source       = '壓力位 / 預估 8%'
            else:
                s1 = sr.get('support1', 0)
                target_price = s1 if (s1 > 0 and s1 < current) else round(current * 0.92, 2)
                stop_loss    = round(current * 1.05, 2)
                source       = '支撐位'

        # 確保目標價已超過現價時動態推移
        if is_buy and target_price > 0 and current >= target_price:
            ma60 = tech.get('ma60', 0) or current
            target_price = round(max(ma60, current) * 1.10, 2)
            source += '（動態推移）'

        gain = (target_price - current) / current * 100 if target_price > 0 else 0
        loss = (current - stop_loss)    / current * 100 if stop_loss    > 0 else 0
        rr   = abs(gain / loss)                          if loss > 0    else 0

        return {
            'available':         True,
            'target_price':      round(target_price, 2) if target_price > 0 else None,
            'stop_loss':         round(stop_loss,    2) if stop_loss    > 0 else None,
            'target_source':     source,
            'potential_gain_pct': round(gain, 2),
            'potential_loss_pct': round(loss, 2),
            'rr_ratio':           round(rr,   2),
            'current_price':      current,
        }

    # ─── 輸出建構 ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_skip_output(direction: dict, result: dict) -> dict:
        """Layer 1 否決：方向不對，跳過"""
        return {
            'available':    True,
            'scenario':     'SKIP',
            'scenario_name': '方向不對',
            'score':        direction['score'],
            'recommendation': '不建議關注',
            'action_timing':  f'{direction["label"]}，方向分 {direction["score"]} < 40',
            'warning_message': f'均線空頭排列（{direction["bull_count"]}/4 多頭）',
            'confidence':     'High',
            'action_code':    'SKIP',
            'filters_applied': ['方向否決'],
            'downgraded':     False,
            'short_term_action': '跳過',
            'original_recommendation': '不建議關注',
            'three_layer': {
                'direction': direction,
                'position':  None,
                'timing':    None,
                'chip':      None,
                'sell_signal': None,
            },
            'price_targets': {'available': False},
        }

    @staticmethod
    def _build_wait_output(direction: dict, position: dict, result: dict) -> dict:
        """Layer 2 否決：位置不佳，等待"""
        composite = int(direction['score'] * 0.4 + position['score'] * 0.6)
        return {
            'available':    True,
            'scenario':     'WAIT',
            'scenario_name': '位置不佳',
            'score':        composite,
            'recommendation': '等待拉回',
            'action_timing':  f'{position["label"]}，位置分 {position["score"]} < 40',
            'warning_message': '；'.join(position['details'][:3]),
            'confidence':     'Medium',
            'action_code':    'WAIT',
            'filters_applied': ['位置否決'],
            'downgraded':     False,
            'short_term_action': '觀望',
            'original_recommendation': '等待拉回',
            'three_layer': {
                'direction': direction,
                'position':  position,
                'timing':    None,
                'chip':      None,
                'sell_signal': None,
            },
            'price_targets': {'available': False},
        }

    @staticmethod
    def _build_buy_output(
        direction: dict,
        position:  dict,
        timing:    dict,
        chip:      dict,
        sell:      dict,
        result:    dict,
    ) -> dict:
        """Layer 1+2 通過後的完整決策輸出"""

        grade = timing['grade']

        # 賣訊優先於買訊
        if sell['triggered']:
            primary_sell = sell['primary']
            is_urgent = primary_sell['severity'] == 'urgent'
            action_code   = 'SELL' if is_urgent else 'HOLD'
            recommendation = f'賣出訊號（{primary_sell["type"]}）' if is_urgent else f'注意賣訊（{primary_sell["type"]}）'
            scenario       = 'SELL'
            scenario_name  = '賣出訊號'
            action_timing  = primary_sell['reason']
            score          = 25 if is_urgent else 42
            confidence     = 'High' if is_urgent else 'Medium'
            is_buy         = False

        elif grade == 'A':
            action_code    = 'STRONG_BUY'
            recommendation = 'A 級主攻，立即進場'
            scenario       = 'A'
            scenario_name  = 'A 級主攻'
            action_timing  = '；'.join(timing['triggers'])
            # A 級分數保底 70
            score          = max(70, int(direction['score'] * 0.35 + position['score'] * 0.65))
            confidence     = 'High'
            is_buy         = True

        elif grade == 'B':
            action_code    = 'BUY'
            recommendation = 'B 級追蹤，等待確認'
            scenario       = 'B'
            scenario_name  = 'B 級追蹤'
            action_timing  = '；'.join(timing['triggers'])
            score          = max(55, min(69, int(direction['score'] * 0.35 + position['score'] * 0.65)))
            confidence     = 'Medium'
            is_buy         = True

        else:  # C 或 X
            action_code    = 'HOLD'
            recommendation = 'C 級觀察，列入追蹤'
            scenario       = 'C'
            scenario_name  = 'C 級觀察'
            action_timing  = '；'.join(timing['triggers']) if timing['triggers'] else '等待進場時機'
            score          = min(54, int(direction['score'] * 0.35 + position['score'] * 0.65))
            confidence     = 'Low'
            is_buy         = True

        # 籌碼備注
        chip_note = chip.get('note', '') if chip else ''

        # 目標價
        price_targets = ThreeLayerEngine._compute_targets(result, is_buy)

        return {
            'available':    True,
            'scenario':     scenario,
            'scenario_name': scenario_name,
            'score':        score,
            'recommendation': recommendation,
            'action_timing':  action_timing,
            'warning_message': chip_note,
            'confidence':     confidence,
            'action_code':    action_code,
            'filters_applied': [] if chip.get('filter') == 'pass' else ['籌碼降級'],
            'downgraded':     chip.get('filter') == 'downgrade',
            'short_term_action': recommendation,
            'original_recommendation': recommendation,
            'three_layer': {
                'direction':   direction,
                'position':    position,
                'timing':      timing,
                'chip':        chip,
                'sell_signal': sell,
            },
            'price_targets': price_targets,
        }
