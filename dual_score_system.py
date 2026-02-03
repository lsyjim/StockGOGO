"""
雙軌評分系統 (Dual-Track Scoring System) v1.0

將評分系統拆分為「短線波段 (Short-term)」與「中長線投資 (Long-term)」兩套獨立標準。

設計原則：
1. 加分制算法 (Additive Scoring)：基準分 50 分
   - 符合做多條件 → 加分
   - 符合做空條件 → 扣分
   - 分數範圍：0 ~ 100

2. 短線波段評分：專注於形態、均線突破、量能爆發
3. 中長線投資評分：專注於年線趨勢、基本面(PE/PB)、籌碼面

作者：Stock Analysis System
版本：v1.0 (2026-01-27)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum


# ============================================================================
# 評分權重配置
# ============================================================================

@dataclass
class ShortTermWeights:
    """
    短線波段評分權重配置
    
    =====================================================
    權重設計邏輯：
    =====================================================
    總權重空間 = 100 分（基準 50 + 最大加分 50 或 最大扣分 50）
    
    做多加分項（最大 +65 分）：
    - 形態確立 (Pattern): +25（權重最重，確立形態是最強訊號）
    - 波段突破 (Wave): +20（三盤突破/均線多排）
    - 量能確認 (Volume): +15（爆量長紅）
    - 技術指標 (Tech): +10（KD/RSI 黃金交叉）
    
    做空扣分項（最大 -65 分）：
    - 形態確立 (Pattern): -30（頭部形態比底部形態更危險）
    - 波段跌破 (Wave): -20
    - 量能異常 (Volume): -15（爆量長黑）
    - 技術指標 (Tech): -10（背離）
    - 風險警示 (Risk): -15（乖離過熱）
    """
    # 做多加分
    PATTERN_BOTTOM_CONFIRMED: int = 25      # W底/頭肩底確立
    PATTERN_BOTTOM_FORMING: int = 10        # 底部形態形成中
    WAVE_BREAKOUT: int = 20                 # 三盤突破/均線多排
    WAVE_BULLISH_ENV: int = 8               # 多頭環境（未突破）
    VOLUME_BULLISH_SURGE: int = 15          # 爆量長紅
    VOLUME_BREAKOUT_CONFIRM: int = 8        # 突破有量確認
    TECH_KD_GOLDEN_CROSS: int = 5           # KD 黃金交叉
    TECH_RSI_GOLDEN_CROSS: int = 5          # RSI 黃金交叉（從超賣回升）
    TECH_MACD_BULLISH: int = 5              # MACD 多頭
    
    # 做空扣分
    PATTERN_TOP_CONFIRMED: int = -30        # M頭/頭肩頂確立（最危險）
    PATTERN_TOP_FORMING: int = -15          # 頭部形態形成中
    WAVE_BREAKDOWN: int = -20               # 三盤跌破
    WAVE_BEARISH_ENV: int = -10             # 空頭環境
    VOLUME_BEARISH_SURGE: int = -15         # 爆量長黑
    VOLUME_NO_RISE: int = -10               # 放量不漲（派發）
    TECH_KD_DEATH_CROSS: int = -5           # KD 死亡交叉
    TECH_RSI_DIVERGENCE: int = -5           # RSI 背離
    TECH_MACD_BEARISH: int = -5             # MACD 空頭
    
    # 風險扣分（純扣分項）
    RISK_BIAS_OVERHEATED: int = -15         # 乖離率過熱（> +8%）
    RISK_RSI_OVERBOUGHT: int = -8           # RSI 超買（> 80）
    RISK_VOLUME_SHRINK: int = -5            # 量縮（假突破疑慮）
    RISK_LOW_RR: int = -8                   # 風險回報比不佳


@dataclass
class LongTermWeights:
    """
    中長線投資評分權重配置
    
    =====================================================
    權重設計邏輯：
    =====================================================
    中長線投資更注重趨勢的穩定性和價值面，而非短期波動。
    
    做多加分項（最大 +55 分）：
    - 年線趨勢: 站上 MA240 +20，MA240 上揚 +15
    - 價值面: PE < 15 或位於歷史低檔 +20
    - 籌碼面: 法人連買 +10
    
    做空扣分項（最大 -55 分）：
    - 年線趨勢: 跌破 MA240 -20，MA240 下彎 -15
    - 價值面: PE > 30 或位於歷史高檔 -15
    - 籌碼面: 法人連賣 -10
    """
    # 年線趨勢（做多）
    ABOVE_MA240: int = 20                   # 站上年線
    MA240_RISING: int = 15                  # 年線上揚
    ABOVE_MA120: int = 10                   # 站上半年線
    MA_BULLISH_ALIGN: int = 10              # 均線多頭排列（MA20 > MA60 > MA240）
    
    # 年線趨勢（做空）
    BELOW_MA240: int = -20                  # 跌破年線
    MA240_FALLING: int = -15                # 年線下彎
    BELOW_MA120: int = -10                  # 跌破半年線
    MA_BEARISH_ALIGN: int = -10             # 均線空頭排列
    
    # 價值面（做多）
    PE_LOW: int = 20                        # PE < 15（低估值）
    PE_HISTORICAL_LOW: int = 10             # PE 位於歷史低檔
    PB_LOW: int = 10                        # PB < 1.5（低估值）
    DIVIDEND_HIGH: int = 8                  # 高殖利率（> 4%）
    
    # 價值面（做空）
    PE_HIGH: int = -15                      # PE > 30（高估值）
    PE_HISTORICAL_HIGH: int = -10           # PE 位於歷史高檔
    PB_HIGH: int = -8                       # PB > 5（高估值）
    
    # 籌碼面（做多）
    INSTITUTIONAL_BUY_STREAK: int = 10      # 法人連續買超
    INSTITUTIONAL_BIG_BUY: int = 8          # 法人大量買超
    FOREIGN_NET_BUY: int = 5                # 外資淨買
    
    # 籌碼面（做空）
    INSTITUTIONAL_SELL_STREAK: int = -10    # 法人連續賣超
    INSTITUTIONAL_BIG_SELL: int = -8        # 法人大量賣超
    FOREIGN_NET_SELL: int = -5              # 外資淨賣


# ============================================================================
# 評分結果資料結構
# ============================================================================

@dataclass
class ScoreComponent:
    """單一評分項目"""
    name: str                   # 項目名稱
    score: int                  # 加/扣分數
    reason: str                 # 評分原因
    category: str               # 類別（Pattern/Wave/Volume/Tech/Risk/Value/Chip）
    is_positive: bool           # 是否為正面因素


@dataclass
class ScoreResult:
    """評分結果"""
    base_score: int = 50                    # 基準分
    final_score: int = 50                   # 最終分數
    components: List[ScoreComponent] = field(default_factory=list)  # 評分項目明細
    score_label: str = ""                   # 分數等級標籤
    action_suggestion: str = ""             # 操作建議
    confidence: str = "Medium"              # 信心度
    
    def add_component(self, name: str, score: int, reason: str, category: str):
        """新增評分項目"""
        self.components.append(ScoreComponent(
            name=name,
            score=score,
            reason=reason,
            category=category,
            is_positive=score > 0
        ))
        self.final_score = max(0, min(100, self.final_score + score))
    
    def get_breakdown(self) -> Dict[str, int]:
        """取得各類別分數明細"""
        breakdown = {}
        for comp in self.components:
            if comp.category not in breakdown:
                breakdown[comp.category] = 0
            breakdown[comp.category] += comp.score
        return breakdown


# ============================================================================
# 雙軌評分器
# ============================================================================

class DualTrackScorer:
    """
    雙軌評分器
    
    將股票分析結果轉換為短線波段分數和中長線投資分數。
    
    使用方法：
    ```python
    scorer = DualTrackScorer(result)
    short_term = scorer.calculate_short_term_score()
    long_term = scorer.calculate_long_term_score()
    report = scorer.get_comprehensive_report()
    ```
    """
    
    # 分數等級定義
    SCORE_LABELS = {
        (90, 100): ('極強', '強力買進'),
        (75, 89): ('偏多', '建議買進'),
        (60, 74): ('中性偏多', '可考慮買進'),
        (40, 59): ('中性', '觀望'),
        (25, 39): ('中性偏空', '謹慎操作'),
        (10, 24): ('偏空', '建議賣出'),
        (0, 9): ('極弱', '清倉'),
    }
    
    def __init__(self, result: Dict[str, Any], 
                 short_weights: ShortTermWeights = None,
                 long_weights: LongTermWeights = None):
        """
        初始化評分器
        
        Args:
            result: QuickAnalyzer.analyze_stock() 的回傳結果
            short_weights: 短線評分權重配置
            long_weights: 長線評分權重配置
        """
        self.result = result
        self.short_weights = short_weights or ShortTermWeights()
        self.long_weights = long_weights or LongTermWeights()
        
        # 快取評分結果
        self._short_term_score: Optional[ScoreResult] = None
        self._long_term_score: Optional[ScoreResult] = None
    
    # ========================================================================
    # 短線波段評分
    # ========================================================================
    
    def calculate_short_term_score(self) -> ScoreResult:
        """
        計算短線波段評分
        
        =====================================================
        評分邏輯（加分制，基準 50 分）：
        =====================================================
        
        1. 形態學 (Pattern) - 權重最重
           - W底/頭肩底確立: +25
           - M頭/頭肩頂確立: -30
           - 形態形成中: ±10~15
        
        2. 波段 (Wave) - 趨勢確認
           - 三盤突破/均線多排: +20
           - 三盤跌破: -20
        
        3. 量能 (Volume) - 動能確認
           - 爆量長紅: +15
           - 爆量長黑: -15
        
        4. 技術指標 (Tech) - 輔助確認
           - KD/RSI 黃金交叉: +10
           - 背離: -10
        
        5. 風險 (Risk) - 純扣分項
           - 乖離率過熱: -15
           - RSI 超買: -8
        
        Returns:
            ScoreResult: 短線波段評分結果
        """
        if self._short_term_score is not None:
            return self._short_term_score
        
        score = ScoreResult(base_score=50, final_score=50)
        w = self.short_weights
        
        # ========================================
        # 1. 形態學評分 (Pattern)
        # ========================================
        self._score_pattern(score, w)
        
        # ========================================
        # 2. 波段評分 (Wave)
        # ========================================
        self._score_wave(score, w)
        
        # ========================================
        # 3. 量能評分 (Volume)
        # ========================================
        self._score_volume(score, w)
        
        # ========================================
        # 4. 技術指標評分 (Tech)
        # ========================================
        self._score_technical(score, w)
        
        # ========================================
        # 5. 風險評分 (Risk) - 純扣分
        # ========================================
        self._score_risk(score, w)
        
        # ========================================
        # 計算最終標籤和建議
        # ========================================
        score.score_label, score.action_suggestion = self._get_score_label(score.final_score)
        score.confidence = self._calculate_confidence(score)
        
        self._short_term_score = score
        return score
    
    def _score_pattern(self, score: ScoreResult, w: ShortTermWeights):
        """
        形態學評分
        
        數學邏輯：
        - 底部形態確立 → 代表下跌動能耗盡，多方開始反攻
        - 頭部形態確立 → 代表上漲動能耗盡，空方開始反攻
        - 形態學是技術分析中最可靠的訊號之一
        """
        pattern = self.result.get('pattern_analysis', {})
        
        if not pattern.get('detected'):
            return
        
        pattern_type = pattern.get('pattern_type', '')
        pattern_status = pattern.get('status', '')
        pattern_name = pattern.get('pattern_name', '')
        pattern_confidence = pattern.get('confidence', 50)
        
        # 底部形態
        if pattern_type == 'bottom':
            if 'CONFIRMED' in pattern_status:
                # 底部形態確立
                score.add_component(
                    name='底部形態確立',
                    score=w.PATTERN_BOTTOM_CONFIRMED,
                    reason=f'{pattern_name}突破頸線確立（信心度{pattern_confidence}%）',
                    category='Pattern'
                )
            else:
                # 底部形態形成中
                score.add_component(
                    name='底部形態形成中',
                    score=w.PATTERN_BOTTOM_FORMING,
                    reason=f'{pattern_name}形成中，等待突破頸線',
                    category='Pattern'
                )
        
        # 頭部形態
        elif pattern_type == 'top':
            if 'CONFIRMED' in pattern_status:
                # 頭部形態確立（最危險）
                score.add_component(
                    name='頭部形態確立',
                    score=w.PATTERN_TOP_CONFIRMED,
                    reason=f'{pattern_name}跌破頸線確立（信心度{pattern_confidence}%）',
                    category='Pattern'
                )
            else:
                # 頭部形態形成中
                score.add_component(
                    name='頭部形態形成中',
                    score=w.PATTERN_TOP_FORMING,
                    reason=f'{pattern_name}形成中，留意頸線支撐',
                    category='Pattern'
                )
    
    def _score_wave(self, score: ScoreResult, w: ShortTermWeights):
        """
        波段評分
        
        數學邏輯：
        - 三盤突破 = 收盤價突破前三日高點，代表多方力量強勁
        - 均線多排 = MA5 > MA10 > MA20 > MA60，趨勢向上
        - 三盤跌破 = 收盤價跌破前三日低點，代表空方力量強勁
        """
        wave = self.result.get('wave_analysis', {})
        
        if not wave.get('available'):
            return
        
        # 三盤突破
        breakout = wave.get('breakout_signal', {})
        if breakout.get('detected'):
            volume_confirmed = breakout.get('volume_confirmed', False)
            if volume_confirmed:
                score.add_component(
                    name='三盤突破（帶量）',
                    score=w.WAVE_BREAKOUT,
                    reason='收盤價突破前三日高點，且成交量放大確認',
                    category='Wave'
                )
            else:
                # 量縮突破，打折
                score.add_component(
                    name='三盤突破（量縮）',
                    score=int(w.WAVE_BREAKOUT * 0.6),
                    reason='收盤價突破前三日高點，但成交量萎縮',
                    category='Wave'
                )
        
        # 多頭環境（未突破但環境偏多）
        elif wave.get('is_bullish_env'):
            score.add_component(
                name='多頭環境',
                score=w.WAVE_BULLISH_ENV,
                reason='均線多頭排列，趨勢向上',
                category='Wave'
            )
        
        # 三盤跌破
        breakdown = wave.get('breakdown_signal', {})
        if breakdown.get('detected'):
            score.add_component(
                name='三盤跌破',
                score=w.WAVE_BREAKDOWN,
                reason='收盤價跌破前三日低點，趨勢轉空',
                category='Wave'
            )
        
        # 空頭環境
        elif wave.get('is_bearish_env'):
            score.add_component(
                name='空頭環境',
                score=w.WAVE_BEARISH_ENV,
                reason='均線空頭排列，趨勢向下',
                category='Wave'
            )
    
    def _score_volume(self, score: ScoreResult, w: ShortTermWeights):
        """
        量能評分
        
        數學邏輯：
        - 爆量長紅 = 成交量 > 5日均量 1.5 倍 + 收盤漲幅 > 2%
        - 爆量長黑 = 成交量 > 5日均量 1.5 倍 + 收盤跌幅 > 2%
        - 量是價的先行指標，爆量代表大資金進場
        """
        vol = self.result.get('volume_analysis', {})
        vp = self.result.get('volume_price', {})
        
        if not vol:
            return
        
        volume_ratio = vol.get('volume_ratio', 1.0)
        price_change_pct = self.result.get('price_change_pct', 0)
        
        # 爆量長紅
        if volume_ratio > 1.5 and price_change_pct > 2:
            score.add_component(
                name='爆量長紅',
                score=w.VOLUME_BULLISH_SURGE,
                reason=f'成交量達均量{volume_ratio:.1f}倍，收漲{price_change_pct:.1f}%',
                category='Volume'
            )
        
        # 爆量長黑
        elif volume_ratio > 1.5 and price_change_pct < -2:
            score.add_component(
                name='爆量長黑',
                score=w.VOLUME_BEARISH_SURGE,
                reason=f'成交量達均量{volume_ratio:.1f}倍，收跌{abs(price_change_pct):.1f}%',
                category='Volume'
            )
        
        # 放量不漲（派發跡象）
        if vp.get('available'):
            signals = vp.get('signals', [])
            for s in signals:
                if s.get('code') == 'VP07':  # 放量不漲
                    score.add_component(
                        name='放量不漲',
                        score=w.VOLUME_NO_RISE,
                        reason='高位放量但價格未漲，疑似派發',
                        category='Volume'
                    )
                    break
    
    def _score_technical(self, score: ScoreResult, w: ShortTermWeights):
        """
        技術指標評分
        
        數學邏輯：
        - KD 黃金交叉 = K 線由下往上穿越 D 線，且在 20 以下（超賣區）
        - RSI 回升 = RSI 從 < 30 回升至 > 30
        - MACD 多頭 = DIF > MACD 且柱狀體由負轉正
        """
        tech = self.result.get('technical', {})
        
        if not tech:
            return
        
        k_value = tech.get('k', 50)
        d_value = tech.get('d', 50)
        rsi = tech.get('rsi', 50)
        macd_hist = tech.get('macd_histogram', 0)
        
        # KD 黃金交叉（K > D 且 K < 30）
        if k_value > d_value and k_value < 30:
            score.add_component(
                name='KD 黃金交叉',
                score=w.TECH_KD_GOLDEN_CROSS,
                reason=f'K={k_value:.0f} > D={d_value:.0f}，且處於超賣區',
                category='Tech'
            )
        
        # KD 死亡交叉（K < D 且 K > 70）
        elif k_value < d_value and k_value > 70:
            score.add_component(
                name='KD 死亡交叉',
                score=w.TECH_KD_DEATH_CROSS,
                reason=f'K={k_value:.0f} < D={d_value:.0f}，且處於超買區',
                category='Tech'
            )
        
        # RSI 從超賣回升
        if 30 < rsi < 40:
            score.add_component(
                name='RSI 回升',
                score=w.TECH_RSI_GOLDEN_CROSS,
                reason=f'RSI={rsi:.0f}，從超賣區回升',
                category='Tech'
            )
        
        # MACD 多頭
        if macd_hist > 0:
            score.add_component(
                name='MACD 多頭',
                score=w.TECH_MACD_BULLISH,
                reason='MACD 柱狀體為正，多頭動能',
                category='Tech'
            )
        elif macd_hist < 0:
            score.add_component(
                name='MACD 空頭',
                score=w.TECH_MACD_BEARISH,
                reason='MACD 柱狀體為負，空頭動能',
                category='Tech'
            )
    
    def _score_risk(self, score: ScoreResult, w: ShortTermWeights):
        """
        風險評分（純扣分項）
        
        數學邏輯：
        - 乖離率過熱 = 股價偏離 MA20 超過 8%，短線超漲
        - RSI 超買 = RSI > 80，技術面過熱
        - 這些都是「追高風險」的警示
        """
        mr = self.result.get('mean_reversion', {})
        tech = self.result.get('technical', {})
        
        # 乖離率過熱
        if mr.get('available'):
            bias_20 = mr.get('bias_analysis', {}).get('bias_20', 0)
            if bias_20 > 8:
                score.add_component(
                    name='乖離率過熱',
                    score=w.RISK_BIAS_OVERHEATED,
                    reason=f'乖離率 {bias_20:+.1f}% 超過 +8%，短線超漲',
                    category='Risk'
                )
        
        # RSI 超買
        rsi = tech.get('rsi', 50)
        if rsi > 80:
            score.add_component(
                name='RSI 超買',
                score=w.RISK_RSI_OVERBOUGHT,
                reason=f'RSI={rsi:.0f} > 80，技術面過熱',
                category='Risk'
            )
        
        # 量縮風險
        vol = self.result.get('volume_analysis', {})
        volume_ratio = vol.get('volume_ratio', 1.0)
        if volume_ratio < 0.6:
            score.add_component(
                name='量縮風險',
                score=w.RISK_VOLUME_SHRINK,
                reason=f'成交量萎縮至均量{volume_ratio*100:.0f}%',
                category='Risk'
            )
        
        # 風險回報比不佳
        sr = self.result.get('support_resistance', {})
        current_price = self.result.get('current_price', 0)
        take_profit = sr.get('take_profit', current_price * 1.1)
        stop_loss = sr.get('stop_loss', current_price * 0.95)
        
        if current_price > 0:
            potential_gain = (take_profit - current_price) / current_price
            potential_loss = (current_price - stop_loss) / current_price
            
            if potential_loss > 0:
                rr_ratio = potential_gain / potential_loss
                if rr_ratio < 1.5:
                    score.add_component(
                        name='風險回報比不佳',
                        score=w.RISK_LOW_RR,
                        reason=f'RR={rr_ratio:.2f} < 1.5，上檔空間有限',
                        category='Risk'
                    )
    
    # ========================================================================
    # 中長線投資評分
    # ========================================================================
    
    def calculate_long_term_score(self) -> ScoreResult:
        """
        計算中長線投資評分
        
        =====================================================
        評分邏輯（加分制，基準 50 分）：
        =====================================================
        
        1. 年線趨勢 - 最重要
           - 站上 MA240: +20
           - MA240 上揚: +15
           - 跌破 MA240: -20
           - MA240 下彎: -15
        
        2. 價值面 - 估值判斷
           - PE < 15: +20
           - PE 位於歷史低檔: +10
           - PE > 30: -15
        
        3. 籌碼面 - 大戶動向
           - 法人連買: +10
           - 法人連賣: -10
        
        Returns:
            ScoreResult: 中長線投資評分結果
        """
        if self._long_term_score is not None:
            return self._long_term_score
        
        score = ScoreResult(base_score=50, final_score=50)
        w = self.long_weights
        
        # ========================================
        # 1. 年線趨勢評分
        # ========================================
        self._score_yearly_trend(score, w)
        
        # ========================================
        # 2. 價值面評分
        # ========================================
        self._score_valuation(score, w)
        
        # ========================================
        # 3. 籌碼面評分
        # ========================================
        self._score_institutional(score, w)
        
        # ========================================
        # 計算最終標籤和建議
        # ========================================
        score.score_label, score.action_suggestion = self._get_score_label(score.final_score, is_long_term=True)
        score.confidence = self._calculate_confidence(score)
        
        self._long_term_score = score
        return score
    
    def _score_yearly_trend(self, score: ScoreResult, w: LongTermWeights):
        """
        年線趨勢評分
        
        數學邏輯：
        - MA240（年線）是機構投資人最關注的均線
        - 站上年線 = 長期趨勢向上
        - 年線上揚 = 長期趨勢加速
        """
        tech = self.result.get('technical', {})
        current_price = self.result.get('current_price', 0)
        
        ma240 = tech.get('ma240', 0)
        ma120 = tech.get('ma120', 0)
        ma60 = tech.get('ma60', 0)
        ma20 = tech.get('ma20', 0)
        
        if current_price <= 0:
            return
        
        # 站上/跌破年線
        if ma240 > 0:
            if current_price > ma240:
                score.add_component(
                    name='站上年線',
                    score=w.ABOVE_MA240,
                    reason=f'現價${current_price:.2f} > MA240=${ma240:.2f}',
                    category='YearlyTrend'
                )
            else:
                score.add_component(
                    name='跌破年線',
                    score=w.BELOW_MA240,
                    reason=f'現價${current_price:.2f} < MA240=${ma240:.2f}',
                    category='YearlyTrend'
                )
        
        # 站上/跌破半年線
        if ma120 > 0:
            if current_price > ma120:
                score.add_component(
                    name='站上半年線',
                    score=w.ABOVE_MA120,
                    reason=f'現價 > MA120=${ma120:.2f}',
                    category='YearlyTrend'
                )
            else:
                score.add_component(
                    name='跌破半年線',
                    score=w.BELOW_MA120,
                    reason=f'現價 < MA120=${ma120:.2f}',
                    category='YearlyTrend'
                )
        
        # 均線多頭/空頭排列
        if ma20 > 0 and ma60 > 0 and ma240 > 0:
            if ma20 > ma60 > ma240:
                score.add_component(
                    name='均線多頭排列',
                    score=w.MA_BULLISH_ALIGN,
                    reason='MA20 > MA60 > MA240，長期趨勢向上',
                    category='YearlyTrend'
                )
            elif ma20 < ma60 < ma240:
                score.add_component(
                    name='均線空頭排列',
                    score=w.MA_BEARISH_ALIGN,
                    reason='MA20 < MA60 < MA240，長期趨勢向下',
                    category='YearlyTrend'
                )
    
    def _score_valuation(self, score: ScoreResult, w: LongTermWeights):
        """
        價值面評分
        
        數學邏輯：
        - PE < 15 → 低估值，長線投資價值高
        - PE > 30 → 高估值，估值風險
        - PB < 1.5 → 股價低於淨值 1.5 倍，可能被低估
        """
        # 嘗試從 result 中取得基本面資料
        fundamental = self.result.get('fundamental', {})
        
        pe_ratio = fundamental.get('pe_ratio', None)
        pb_ratio = fundamental.get('pb_ratio', None)
        dividend_yield = fundamental.get('dividend_yield', None)
        
        # PE 評分
        if pe_ratio is not None and pe_ratio > 0:
            if pe_ratio < 15:
                score.add_component(
                    name='低本益比',
                    score=w.PE_LOW,
                    reason=f'PE={pe_ratio:.1f} < 15，估值偏低',
                    category='Valuation'
                )
            elif pe_ratio > 30:
                score.add_component(
                    name='高本益比',
                    score=w.PE_HIGH,
                    reason=f'PE={pe_ratio:.1f} > 30，估值偏高',
                    category='Valuation'
                )
        
        # PB 評分
        if pb_ratio is not None and pb_ratio > 0:
            if pb_ratio < 1.5:
                score.add_component(
                    name='低股價淨值比',
                    score=w.PB_LOW,
                    reason=f'PB={pb_ratio:.2f} < 1.5，可能被低估',
                    category='Valuation'
                )
            elif pb_ratio > 5:
                score.add_component(
                    name='高股價淨值比',
                    score=w.PB_HIGH,
                    reason=f'PB={pb_ratio:.2f} > 5，估值偏高',
                    category='Valuation'
                )
        
        # 殖利率評分
        if dividend_yield is not None and dividend_yield > 4:
            score.add_component(
                name='高殖利率',
                score=w.DIVIDEND_HIGH,
                reason=f'殖利率={dividend_yield:.1f}% > 4%，配息穩定',
                category='Valuation'
            )
    
    def _score_institutional(self, score: ScoreResult, w: LongTermWeights):
        """
        籌碼面評分
        
        數學邏輯：
        - 法人連買 = 三大法人連續淨買超，代表專業投資人看好
        - 法人連賣 = 三大法人連續淨賣超，代表專業投資人出貨
        """
        # 嘗試從 result 中取得籌碼資料
        chip = self.result.get('chip_analysis', {})
        
        if not chip.get('available'):
            return
        
        foreign_net = chip.get('foreign_net', 0)
        trust_net = chip.get('trust_net', 0)
        dealer_net = chip.get('dealer_net', 0)
        consecutive_buy_days = chip.get('consecutive_buy_days', 0)
        consecutive_sell_days = chip.get('consecutive_sell_days', 0)
        
        # 法人連買
        if consecutive_buy_days >= 3:
            score.add_component(
                name='法人連買',
                score=w.INSTITUTIONAL_BUY_STREAK,
                reason=f'法人連續{consecutive_buy_days}天淨買超',
                category='Chip'
            )
        
        # 法人連賣
        elif consecutive_sell_days >= 3:
            score.add_component(
                name='法人連賣',
                score=w.INSTITUTIONAL_SELL_STREAK,
                reason=f'法人連續{consecutive_sell_days}天淨賣超',
                category='Chip'
            )
        
        # 外資淨買/賣
        if foreign_net > 0:
            score.add_component(
                name='外資淨買',
                score=w.FOREIGN_NET_BUY,
                reason=f'外資今日淨買超{foreign_net:,}張',
                category='Chip'
            )
        elif foreign_net < 0:
            score.add_component(
                name='外資淨賣',
                score=w.FOREIGN_NET_SELL,
                reason=f'外資今日淨賣超{abs(foreign_net):,}張',
                category='Chip'
            )
    
    # ========================================================================
    # 輔助方法
    # ========================================================================
    
    def _get_score_label(self, final_score: int, is_long_term: bool = False) -> Tuple[str, str]:
        """根據分數取得標籤和建議"""
        for (low, high), (label, suggestion) in self.SCORE_LABELS.items():
            if low <= final_score <= high:
                # 長線建議稍微保守
                if is_long_term:
                    if suggestion == '強力買進':
                        suggestion = '長線布局'
                    elif suggestion == '建議買進':
                        suggestion = '可長期持有'
                    elif suggestion == '建議賣出':
                        suggestion = '長線觀望'
                return label, suggestion
        return '中性', '觀望'
    
    def _calculate_confidence(self, score: ScoreResult) -> str:
        """計算評分信心度"""
        # 根據評分項目數量和一致性計算信心度
        positive_count = sum(1 for c in score.components if c.is_positive)
        negative_count = sum(1 for c in score.components if not c.is_positive)
        total_count = len(score.components)
        
        if total_count == 0:
            return 'Low'
        
        # 信號一致性
        consistency = abs(positive_count - negative_count) / total_count
        
        # 分數偏離中性的程度
        deviation = abs(score.final_score - 50) / 50
        
        if consistency > 0.7 and deviation > 0.4:
            return 'High'
        elif consistency > 0.4 or deviation > 0.2:
            return 'Medium'
        else:
            return 'Low'
    
    # ========================================================================
    # 綜合報告
    # ========================================================================
    
    def get_comprehensive_report(self) -> Dict[str, Any]:
        """
        取得綜合雙軌評分報告
        
        Returns:
            dict: 包含短線和長線評分的完整報告
        """
        short_term = self.calculate_short_term_score()
        long_term = self.calculate_long_term_score()
        
        # 產生綜合建議
        combined_advice = self._generate_combined_advice(short_term, long_term)
        
        return {
            'available': True,
            'symbol': self.result.get('symbol', ''),
            'current_price': self.result.get('current_price', 0),
            
            # 短線評分
            'short_term': {
                'score': short_term.final_score,
                'base_score': short_term.base_score,
                'label': short_term.score_label,
                'action': short_term.action_suggestion,
                'confidence': short_term.confidence,
                'components': [
                    {
                        'name': c.name,
                        'score': c.score,
                        'reason': c.reason,
                        'category': c.category
                    }
                    for c in short_term.components
                ],
                'breakdown': short_term.get_breakdown()
            },
            
            # 長線評分
            'long_term': {
                'score': long_term.final_score,
                'base_score': long_term.base_score,
                'label': long_term.score_label,
                'action': long_term.action_suggestion,
                'confidence': long_term.confidence,
                'components': [
                    {
                        'name': c.name,
                        'score': c.score,
                        'reason': c.reason,
                        'category': c.category
                    }
                    for c in long_term.components
                ],
                'breakdown': long_term.get_breakdown()
            },
            
            # 綜合建議
            'combined': {
                'advice': combined_advice['advice'],
                'explanation': combined_advice['explanation'],
                'short_action': combined_advice['short_action'],
                'long_action': combined_advice['long_action'],
                'conflict': combined_advice['conflict'],
                'risk_level': combined_advice['risk_level']
            }
        }
    
    def _generate_combined_advice(self, short_term: ScoreResult, long_term: ScoreResult) -> Dict[str, str]:
        """
        產生綜合建議
        
        根據短線和長線評分的組合，給出不同的操作建議。
        
        組合矩陣：
        ┌───────────┬─────────────┬─────────────┬─────────────┐
        │           │ 長線偏多    │ 長線中性    │ 長線偏空    │
        │           │ (≥60)      │ (40-59)     │ (<40)       │
        ├───────────┼─────────────┼─────────────┼─────────────┤
        │短線偏多   │ 積極買進    │ 短線操作    │ 搶反彈      │
        │(≥60)     │             │             │ (嚴設停損)  │
        ├───────────┼─────────────┼─────────────┼─────────────┤
        │短線中性   │ 長線布局    │ 觀望        │ 減碼        │
        │(40-59)    │             │             │             │
        ├───────────┼─────────────┼─────────────┼─────────────┤
        │短線偏空   │ 逢低布局    │ 減碼觀望    │ 清倉        │
        │(<40)      │ (長線思維)  │             │             │
        └───────────┴─────────────┴─────────────┴─────────────┘
        """
        ss = short_term.final_score
        ls = long_term.final_score
        
        # 判斷方向
        short_bullish = ss >= 60
        short_neutral = 40 <= ss < 60
        short_bearish = ss < 40
        
        long_bullish = ls >= 60
        long_neutral = 40 <= ls < 60
        long_bearish = ls < 40
        
        # 判斷是否存在矛盾
        conflict = (short_bullish and long_bearish) or (short_bearish and long_bullish)
        
        # 組合判斷
        if short_bullish and long_bullish:
            return {
                'advice': '積極買進',
                'explanation': '短線與長線訊號一致偏多，可積極進場。',
                'short_action': short_term.action_suggestion,
                'long_action': long_term.action_suggestion,
                'conflict': False,
                'risk_level': 'Low'
            }
        
        elif short_bullish and long_neutral:
            return {
                'advice': '短線操作',
                'explanation': '短線有買訊但長線趨勢不明，建議短線進出，快進快出。',
                'short_action': short_term.action_suggestion,
                'long_action': '觀望',
                'conflict': False,
                'risk_level': 'Medium'
            }
        
        elif short_bullish and long_bearish:
            return {
                'advice': '搶反彈（輕倉）',
                'explanation': '⚠️ 短線有買訊但長線趨勢偏空，僅適合搶反彈，嚴設停損。',
                'short_action': '搶短（輕倉）',
                'long_action': '不建議持有',
                'conflict': True,
                'risk_level': 'High'
            }
        
        elif short_neutral and long_bullish:
            return {
                'advice': '長線布局',
                'explanation': '短線無明確訊號但長線趨勢向上，適合分批布局。',
                'short_action': '觀望',
                'long_action': long_term.action_suggestion,
                'conflict': False,
                'risk_level': 'Low'
            }
        
        elif short_neutral and long_neutral:
            return {
                'advice': '觀望',
                'explanation': '短線和長線皆無明確方向，建議觀望等待。',
                'short_action': '觀望',
                'long_action': '觀望',
                'conflict': False,
                'risk_level': 'Medium'
            }
        
        elif short_neutral and long_bearish:
            return {
                'advice': '減碼',
                'explanation': '長線趨勢偏空，建議減碼降低風險。',
                'short_action': '觀望',
                'long_action': '減碼',
                'conflict': False,
                'risk_level': 'High'
            }
        
        elif short_bearish and long_bullish:
            return {
                'advice': '逢低布局',
                'explanation': '短線超跌但長線趨勢向上，可考慮逢低分批布局。',
                'short_action': '勿追空',
                'long_action': '逢低布局',
                'conflict': True,
                'risk_level': 'Medium'
            }
        
        elif short_bearish and long_neutral:
            return {
                'advice': '減碼觀望',
                'explanation': '短線偏空且長線趨勢不明，建議減碼觀望。',
                'short_action': short_term.action_suggestion,
                'long_action': '觀望',
                'conflict': False,
                'risk_level': 'High'
            }
        
        else:  # short_bearish and long_bearish
            return {
                'advice': '清倉',
                'explanation': '短線與長線訊號一致偏空，建議清倉避險。',
                'short_action': short_term.action_suggestion,
                'long_action': long_term.action_suggestion,
                'conflict': False,
                'risk_level': 'Very High'
            }
    
    def generate_report_text(self) -> str:
        """產生文字版報告"""
        report = self.get_comprehensive_report()
        
        if not report.get('available'):
            return "雙軌評分不可用"
        
        lines = []
        lines.append("=" * 60)
        lines.append("【📊 雙軌評分系統報告 v1.0】")
        lines.append("=" * 60)
        
        # 基本資訊
        lines.append(f"\n股票代碼：{report['symbol']}")
        lines.append(f"現價：${report['current_price']:.2f}")
        
        # 短線評分
        st = report['short_term']
        lines.append(f"\n{'─' * 30}")
        lines.append(f"📈 短線波段評分：{st['score']} 分（{st['label']}）")
        lines.append(f"   操作建議：{st['action']}")
        lines.append(f"   信心度：{st['confidence']}")
        lines.append(f"   評分明細：")
        for comp in st['components']:
            sign = '+' if comp['score'] > 0 else ''
            lines.append(f"     • [{comp['category']}] {comp['name']}: {sign}{comp['score']} - {comp['reason']}")
        
        # 長線評分
        lt = report['long_term']
        lines.append(f"\n{'─' * 30}")
        lines.append(f"📉 中長線投資評分：{lt['score']} 分（{lt['label']}）")
        lines.append(f"   操作建議：{lt['action']}")
        lines.append(f"   信心度：{lt['confidence']}")
        lines.append(f"   評分明細：")
        for comp in lt['components']:
            sign = '+' if comp['score'] > 0 else ''
            lines.append(f"     • [{comp['category']}] {comp['name']}: {sign}{comp['score']} - {comp['reason']}")
        
        # 綜合建議
        cb = report['combined']
        lines.append(f"\n{'─' * 30}")
        lines.append(f"🎯 綜合建議：{cb['advice']}")
        lines.append(f"   {cb['explanation']}")
        if cb['conflict']:
            lines.append(f"   ⚠️ 注意：短線與長線訊號存在矛盾")
        lines.append(f"   風險等級：{cb['risk_level']}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)


# ============================================================================
# 整合到 DecisionMatrix 的擴展方法
# ============================================================================

def integrate_dual_score_to_decision_matrix(DecisionMatrix):
    """
    將雙軌評分系統整合到 DecisionMatrix 類別
    
    使用方式：
    ```python
    from dual_score_system import integrate_dual_score_to_decision_matrix
    integrate_dual_score_to_decision_matrix(DecisionMatrix)
    ```
    """
    
    @staticmethod
    def calculate_short_term_score(result: Dict[str, Any]) -> Dict[str, Any]:
        """計算短線波段評分"""
        scorer = DualTrackScorer(result)
        score_result = scorer.calculate_short_term_score()
        return {
            'score': score_result.final_score,
            'label': score_result.score_label,
            'action': score_result.action_suggestion,
            'confidence': score_result.confidence,
            'components': [
                {'name': c.name, 'score': c.score, 'reason': c.reason, 'category': c.category}
                for c in score_result.components
            ],
            'breakdown': score_result.get_breakdown()
        }
    
    @staticmethod
    def calculate_long_term_score(result: Dict[str, Any]) -> Dict[str, Any]:
        """計算中長線投資評分"""
        scorer = DualTrackScorer(result)
        score_result = scorer.calculate_long_term_score()
        return {
            'score': score_result.final_score,
            'label': score_result.score_label,
            'action': score_result.action_suggestion,
            'confidence': score_result.confidence,
            'components': [
                {'name': c.name, 'score': c.score, 'reason': c.reason, 'category': c.category}
                for c in score_result.components
            ],
            'breakdown': score_result.get_breakdown()
        }
    
    @staticmethod
    def get_comprehensive_report(result: Dict[str, Any]) -> Dict[str, Any]:
        """取得綜合雙軌評分報告"""
        scorer = DualTrackScorer(result)
        return scorer.get_comprehensive_report()
    
    @staticmethod
    def generate_dual_score_report_text(result: Dict[str, Any]) -> str:
        """產生雙軌評分文字報告"""
        scorer = DualTrackScorer(result)
        return scorer.generate_report_text()
    
    # 將方法綁定到 DecisionMatrix
    DecisionMatrix.calculate_short_term_score = calculate_short_term_score
    DecisionMatrix.calculate_long_term_score = calculate_long_term_score
    DecisionMatrix.get_comprehensive_report = get_comprehensive_report
    DecisionMatrix.generate_dual_score_report_text = generate_dual_score_report_text
    
    return DecisionMatrix


# ============================================================================
# 測試用例
# ============================================================================

if __name__ == '__main__':
    # 模擬測試資料
    mock_result = {
        'symbol': '2330',
        'current_price': 580.0,
        'price_change_pct': 2.5,
        
        'pattern_analysis': {
            'detected': True,
            'pattern_type': 'bottom',
            'pattern_name': 'W底',
            'status': 'CONFIRMED_BREAKOUT',
            'confidence': 85
        },
        
        'wave_analysis': {
            'available': True,
            'breakout_signal': {
                'detected': True,
                'volume_confirmed': True
            },
            'breakdown_signal': {
                'detected': False
            },
            'is_bullish_env': True,
            'is_bearish_env': False
        },
        
        'volume_analysis': {
            'volume_ratio': 1.8
        },
        
        'technical': {
            'k': 25,
            'd': 20,
            'rsi': 45,
            'macd_histogram': 1.5,
            'ma20': 570,
            'ma60': 560,
            'ma120': 550,
            'ma240': 540
        },
        
        'mean_reversion': {
            'available': True,
            'bias_analysis': {
                'bias_20': 3.5
            }
        },
        
        'support_resistance': {
            'take_profit': 620,
            'stop_loss': 550
        },
        
        'fundamental': {
            'pe_ratio': 18.5,
            'pb_ratio': 2.8,
            'dividend_yield': 2.5
        },
        
        'chip_analysis': {
            'available': True,
            'foreign_net': 5000,
            'consecutive_buy_days': 5
        }
    }
    
    print("=" * 60)
    print("雙軌評分系統 v1.0 - 測試")
    print("=" * 60)
    
    scorer = DualTrackScorer(mock_result)
    print(scorer.generate_report_text())
