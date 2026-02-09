"""
高盛級量化評分優化器 v1.0
Goldman Sachs Style Quantitative Score Optimizer

核心改進：
1. KD 指標：從二元訊號升級為連續性權重
2. MACD 背離偵測：捕捉強烈反轉訊號
3. 量價分析升級：整合 VP09/VP05/VP04 等高價值訊號
4. RS 相對強度：核心選股因子
5. 布林通道壓縮：捕捉變盤前夕
6. RSI 區間判斷：從交叉改為區間評估

權重調整建議（高盛觀點）：
┌────────────────────┬──────┬──────┬─────────────────────────┐
│ 評分項目           │ 舊權重 │ 新權重 │ 理由                    │
├────────────────────┼──────┼──────┼─────────────────────────┤
│ KD 黃金交叉        │ +5   │ +3~8 │ 動態權重，低檔加重      │
│ MACD 多頭          │ +5   │ +5   │ 維持不變                │
│ MACD 底背離        │ N/A  │ +15  │ 強反轉訊號              │
│ RS 相對強度        │ N/A  │ +15  │ 核心缺失！選股關鍵      │
│ 布林通道壓縮       │ N/A  │ +10  │ 蓄勢待發訊號            │
│ VP09 吸籌跡象      │ N/A  │ +10  │ 聰明錢進場特徵          │
│ VP05 帶量突破      │ N/A  │ +12  │ 有效突破確認            │
│ VP04 價跌量縮      │ N/A  │ +5   │ 良性回檔訊號            │
│ RSI 多頭區間       │ N/A  │ +8   │ 處於多方控盤區          │
│ 形態確立           │ +25  │ +25  │ 維持最高權重            │
└────────────────────┴──────┴──────┴─────────────────────────┘
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class ScoreCategory(Enum):
    """評分類別"""
    PATTERN = "Pattern"      # 形態學
    WAVE = "Wave"            # 波段
    VOLUME = "Volume"        # 量能
    TECH = "Tech"            # 技術指標
    MOMENTUM = "Momentum"    # 動能/相對強度
    RISK = "Risk"            # 風險


@dataclass
class ScoreComponent:
    """評分組件"""
    name: str
    score: float
    reason: str
    category: ScoreCategory
    
    @property
    def is_positive(self) -> bool:
        return self.score > 0


@dataclass
class ScoreResult:
    """評分結果"""
    base_score: float = 50.0
    components: List[ScoreComponent] = field(default_factory=list)
    
    def add_component(self, name: str, score: float, reason: str, category: ScoreCategory):
        """新增評分組件"""
        self.components.append(ScoreComponent(name, score, reason, category))
    
    @property
    def raw_score(self) -> float:
        """未截斷的原始分數"""
        return self.base_score + sum(c.score for c in self.components)
    
    @property
    def final_score(self) -> float:
        """截斷後的最終分數 (0-100)"""
        return max(0, min(100, self.raw_score))
    
    @property
    def total_adjustment(self) -> float:
        """總加減分"""
        return sum(c.score for c in self.components)
    
    def get_breakdown(self) -> Dict[str, float]:
        """按類別彙總分數"""
        breakdown = {}
        for comp in self.components:
            cat = comp.category.value
            if cat not in breakdown:
                breakdown[cat] = 0
            breakdown[cat] += comp.score
        return breakdown


class GoldmanScoreOptimizer:
    """
    高盛級量化評分優化器
    
    設計原則：
    1. 從「二元訊號」升級為「連續性權重」
    2. 重視「背離」等高價值訊號
    3. 整合「相對強度」選股因子
    4. 捕捉「波動率壓縮」變盤訊號
    """
    
    # ========================================
    # 優化後的權重配置
    # ========================================
    WEIGHTS = {
        # === 形態學 (維持高權重) ===
        'PATTERN_BOTTOM_CONFIRMED': 25,
        'PATTERN_BOTTOM_FORMING': 10,
        'PATTERN_TOP_CONFIRMED': -30,
        'PATTERN_TOP_FORMING': -10,
        
        # === 波段 ===
        'WAVE_BREAKOUT': 20,
        'WAVE_BREAKDOWN': -20,
        'WAVE_BULLISH_ENV': 8,
        'WAVE_BEARISH_ENV': -8,
        
        # === 量能 (新增高階訊號) ===
        'VOLUME_BULLISH_SURGE': 15,
        'VOLUME_BEARISH_SURGE': -15,
        'VOLUME_VP09_ACCUMULATION': 10,   # 吸籌跡象
        'VOLUME_VP05_VALID_BREAKOUT': 12, # 帶量突破
        'VOLUME_VP04_SELLING_EASING': 5,  # 良性回檔
        'VOLUME_HIGH_RVOL_AT_KEY': 5,     # 關鍵位置爆量
        'VOLUME_NO_RISE': -10,
        
        # === 技術指標 (動態權重) ===
        'TECH_KD_LOW_GOLDEN': 8,          # 低檔強勢金叉 (K<20)
        'TECH_KD_MID_GOLDEN': 3,          # 普通金叉 (K<50)
        'TECH_KD_HIGH_GOLDEN': 0,         # 高檔金叉不加分
        'TECH_KD_DEATH_CROSS': -5,
        
        'TECH_RSI_BULLISH_ZONE': 8,       # RSI 多頭區間
        'TECH_RSI_GOLDEN_CROSS': 3,       # RSI 回升 (降權)
        'TECH_RSI_OVERBOUGHT': -5,
        
        'TECH_MACD_BULLISH': 5,
        'TECH_MACD_BEARISH': -5,
        'TECH_MACD_BULLISH_DIVERGENCE': 15,  # 底背離 (新增)
        'TECH_MACD_BEARISH_DIVERGENCE': -15, # 頂背離 (新增)
        
        # === 動能/相對強度 (核心新增) ===
        'MOMENTUM_RS_POSITIVE': 10,       # 強於大盤
        'MOMENTUM_RS_LEADER': 10,         # 市場領頭羊
        'MOMENTUM_BB_SQUEEZE': 10,        # 布林壓縮 (蓄勢待發)
        'MOMENTUM_BB_SQUEEZE_BREAKOUT': 5, # 壓縮後突破加成
        
        # === 風險 ===
        'RISK_BIAS_OVERHEATED': -12,
        'RISK_BIAS_OVERSOLD': 5,          # 超跌反彈機會
        'RISK_LOW_RR': -8,
        'RISK_VOLUME_SHRINK': -5,
    }
    
    def __init__(self, result: dict):
        """
        初始化評分優化器
        
        Args:
            result: QuickAnalyzer.analyze_stock() 的回傳結果
        """
        self.result = result
        self.score = ScoreResult()
    
    def calculate_short_term_score(self) -> Dict:
        """
        計算優化後的短線波段評分
        
        Returns:
            dict: 短線波段評分結果
        """
        self.score = ScoreResult()
        w = self.WEIGHTS
        
        # 1. 形態學評分
        self._score_pattern(w)
        
        # 2. 波段評分
        self._score_wave(w)
        
        # 3. 量能評分 (升級版)
        self._score_volume_enhanced(w)
        
        # 4. 技術指標評分 (動態權重)
        self._score_technical_dynamic(w)
        
        # 5. 動能/相對強度評分 (核心新增)
        self._score_momentum(w)
        
        # 6. 風險評分
        self._score_risk(w)
        
        # 生成結果
        return self._generate_result()
    
    def _score_pattern(self, w: dict):
        """形態學評分"""
        pattern = self.result.get('pattern_analysis', {})
        if not pattern.get('detected'):
            return
        
        pattern_type = pattern.get('pattern_type', '')
        pattern_status = pattern.get('status', '')
        pattern_name = pattern.get('pattern_name', '')
        confidence = pattern.get('confidence', 50)
        
        if pattern_type == 'bottom':
            if 'CONFIRMED' in pattern_status:
                self.score.add_component(
                    '底部形態確立', w['PATTERN_BOTTOM_CONFIRMED'],
                    f'{pattern_name}突破頸線確立（信心度{confidence}%）',
                    ScoreCategory.PATTERN
                )
            else:
                self.score.add_component(
                    '底部形態形成中', w['PATTERN_BOTTOM_FORMING'],
                    f'{pattern_name}形成中，等待突破頸線',
                    ScoreCategory.PATTERN
                )
        elif pattern_type == 'top':
            if 'CONFIRMED' in pattern_status:
                self.score.add_component(
                    '頭部形態確立', w['PATTERN_TOP_CONFIRMED'],
                    f'{pattern_name}跌破頸線確立（信心度{confidence}%）',
                    ScoreCategory.PATTERN
                )
            else:
                self.score.add_component(
                    '頭部形態形成中', w['PATTERN_TOP_FORMING'],
                    f'{pattern_name}形成中，留意頸線支撐',
                    ScoreCategory.PATTERN
                )
    
    def _score_wave(self, w: dict):
        """波段評分"""
        wave = self.result.get('wave_analysis', {})
        if not wave.get('available'):
            return
        
        breakout = wave.get('breakout_signal', {})
        if breakout.get('detected'):
            volume_confirmed = breakout.get('volume_confirmed', False)
            if volume_confirmed:
                self.score.add_component(
                    '三盤突破（帶量）', w['WAVE_BREAKOUT'],
                    '收盤價突破前三日高點，且成交量放大確認',
                    ScoreCategory.WAVE
                )
            else:
                self.score.add_component(
                    '三盤突破（量縮）', int(w['WAVE_BREAKOUT'] * 0.6),
                    '收盤價突破前三日高點，但成交量萎縮',
                    ScoreCategory.WAVE
                )
        elif wave.get('is_bullish_env'):
            self.score.add_component(
                '多頭環境', w['WAVE_BULLISH_ENV'],
                '均線多頭排列，趨勢向上',
                ScoreCategory.WAVE
            )
        
        breakdown = wave.get('breakdown_signal', {})
        if breakdown.get('detected'):
            self.score.add_component(
                '三盤跌破', w['WAVE_BREAKDOWN'],
                '收盤價跌破前三日低點，趨勢轉空',
                ScoreCategory.WAVE
            )
        elif wave.get('is_bearish_env'):
            self.score.add_component(
                '空頭環境', w['WAVE_BEARISH_ENV'],
                '均線空頭排列，趨勢向下',
                ScoreCategory.WAVE
            )
    
    def _score_volume_enhanced(self, w: dict):
        """
        升級版量能評分
        
        整合 VolumePriceAnalyzer 的高階訊號：
        - VP09: 吸籌跡象 (Accumulation)
        - VP05: 帶量突破 (Valid Breakout)
        - VP04: 價跌量縮 (Selling Easing)
        """
        vol = self.result.get('volume_analysis', {})
        vp = self.result.get('volume_price', {})
        
        # 基礎量能評分
        if vol:
            volume_ratio = vol.get('volume_ratio', 1.0)
            price_change_pct = self.result.get('price_change_pct', 0)
            
            if volume_ratio > 1.5 and price_change_pct > 2:
                self.score.add_component(
                    '爆量長紅', w['VOLUME_BULLISH_SURGE'],
                    f'成交量達均量{volume_ratio:.1f}倍，收漲{price_change_pct:.1f}%',
                    ScoreCategory.VOLUME
                )
            elif volume_ratio > 1.5 and price_change_pct < -2:
                self.score.add_component(
                    '爆量長黑', w['VOLUME_BEARISH_SURGE'],
                    f'成交量達均量{volume_ratio:.1f}倍，收跌{abs(price_change_pct):.1f}%',
                    ScoreCategory.VOLUME
                )
            
            # 關鍵位置高 RVOL
            sr = self.result.get('support_resistance', {})
            current_price = self.result.get('current_price', 0)
            support = sr.get('support', 0)
            resistance = sr.get('resistance', 999999)
            
            if volume_ratio > 2.5:
                # 在支撐位附近爆量
                if support > 0 and current_price > 0:
                    if abs(current_price - support) / current_price < 0.02:
                        self.score.add_component(
                            '支撐位爆量', w['VOLUME_HIGH_RVOL_AT_KEY'],
                            f'RVOL={volume_ratio:.1f}x，接近支撐位主力表態',
                            ScoreCategory.VOLUME
                        )
                # 在突破位爆量
                if resistance < 999999 and current_price > resistance:
                    self.score.add_component(
                        '突破位爆量', w['VOLUME_HIGH_RVOL_AT_KEY'],
                        f'RVOL={volume_ratio:.1f}x，突破壓力位主力表態',
                        ScoreCategory.VOLUME
                    )
        
        # 高階量價訊號
        if vp.get('available'):
            signals = vp.get('signals', [])
            signal_codes = {s.get('code') for s in signals}
            
            # VP09: 吸籌跡象 (低位區量能抬升，價格不破底)
            if 'VP09' in signal_codes:
                self.score.add_component(
                    '吸籌跡象', w['VOLUME_VP09_ACCUMULATION'],
                    '低位區量能漸增，聰明錢進場特徵',
                    ScoreCategory.VOLUME
                )
            
            # VP05: 帶量突破 (比爆量長紅更精確)
            if 'VP05' in signal_codes:
                self.score.add_component(
                    '帶量有效突破', w['VOLUME_VP05_VALID_BREAKOUT'],
                    '突破20日高點且成交量放大，突破有效',
                    ScoreCategory.VOLUME
                )
            
            # VP04: 價跌量縮 (良性回檔)
            if 'VP04' in signal_codes:
                self.score.add_component(
                    '良性回檔', w['VOLUME_VP04_SELLING_EASING'],
                    '價跌量縮，賣壓減緩，拉回買點浮現',
                    ScoreCategory.VOLUME
                )
            
            # VP07: 放量不漲 (派發)
            if 'VP07' in signal_codes:
                self.score.add_component(
                    '放量不漲', w['VOLUME_NO_RISE'],
                    '高位放量但價格未漲，疑似派發',
                    ScoreCategory.VOLUME
                )
    
    def _score_technical_dynamic(self, w: dict):
        """
        動態權重技術指標評分
        
        改進：
        1. KD 根據位置給予不同權重
        2. RSI 從交叉改為區間判斷
        3. MACD 新增背離偵測
        """
        tech = self.result.get('technical', {})
        if not tech:
            return
        
        k_value = tech.get('k', 50)
        d_value = tech.get('d', 50)
        rsi = tech.get('rsi', 50)
        macd_hist = tech.get('macd_histogram', 0)
        
        # === KD 動態權重 ===
        if k_value > d_value:
            if k_value < 20:
                # 低檔強勢金叉 (超賣區)
                self.score.add_component(
                    'KD 低檔強勢金叉', w['TECH_KD_LOW_GOLDEN'],
                    f'K={k_value:.0f} < 20，超賣區金叉，反彈機率高',
                    ScoreCategory.TECH
                )
            elif k_value < 50:
                # 普通金叉
                self.score.add_component(
                    'KD 黃金交叉', w['TECH_KD_MID_GOLDEN'],
                    f'K={k_value:.0f} > D={d_value:.0f}，多頭排列',
                    ScoreCategory.TECH
                )
            # K > 50 的金叉不加分（肉不多）
        elif k_value < d_value and k_value > 70:
            self.score.add_component(
                'KD 死亡交叉', w['TECH_KD_DEATH_CROSS'],
                f'K={k_value:.0f} > 70，超買區死叉，回檔機率高',
                ScoreCategory.TECH
            )
        
        # === RSI 區間判斷 ===
        ma20_trend = self.result.get('trend', {}).get('ma20_slope', 0)
        
        if 40 < rsi < 80 and ma20_trend > 0:
            # 多頭強勢區
            self.score.add_component(
                'RSI 多頭控盤區', w['TECH_RSI_BULLISH_ZONE'],
                f'RSI={rsi:.0f}，維持在40~80強勢區間，MA20上揚',
                ScoreCategory.TECH
            )
        elif 30 < rsi < 40:
            # 從超賣區回升
            self.score.add_component(
                'RSI 回升', w['TECH_RSI_GOLDEN_CROSS'],
                f'RSI={rsi:.0f}，從超賣區回升',
                ScoreCategory.TECH
            )
        elif rsi > 80:
            self.score.add_component(
                'RSI 超買', w['TECH_RSI_OVERBOUGHT'],
                f'RSI={rsi:.0f} > 80，技術面過熱',
                ScoreCategory.TECH
            )
        
        # === MACD ===
        if macd_hist > 0:
            self.score.add_component(
                'MACD 多頭', w['TECH_MACD_BULLISH'],
                'MACD 柱狀體為正，多頭動能',
                ScoreCategory.TECH
            )
        elif macd_hist < 0:
            self.score.add_component(
                'MACD 空頭', w['TECH_MACD_BEARISH'],
                'MACD 柱狀體為負，空頭動能',
                ScoreCategory.TECH
            )
        
        # === MACD 背離偵測 ===
        self._detect_macd_divergence(w)
    
    def _detect_macd_divergence(self, w: dict):
        """
        偵測 MACD 背離
        
        底背離：股價創新低，但 MACD 底部墊高 → 強反轉訊號
        頂背離：股價創新高，但 MACD 頂部降低 → 弱勢訊號
        """
        tech = self.result.get('technical', {})
        divergence = tech.get('macd_divergence', {})
        
        if divergence.get('bullish_divergence'):
            self.score.add_component(
                'MACD 底背離', w['TECH_MACD_BULLISH_DIVERGENCE'],
                '股價創新低但MACD底部墊高，強烈反轉訊號',
                ScoreCategory.TECH
            )
        
        if divergence.get('bearish_divergence'):
            self.score.add_component(
                'MACD 頂背離', w['TECH_MACD_BEARISH_DIVERGENCE'],
                '股價創新高但MACD頂部降低，動能減弱',
                ScoreCategory.TECH
            )
        
        # 如果 divergence 不存在，嘗試從 RSI 背離推斷
        rsi_div = self.result.get('mean_reversion', {}).get('divergence', {})
        if rsi_div.get('rsi_bullish_divergence') and not divergence.get('bullish_divergence'):
            self.score.add_component(
                'RSI 底背離', int(w['TECH_MACD_BULLISH_DIVERGENCE'] * 0.7),
                'RSI 與價格背離，暗示反轉',
                ScoreCategory.TECH
            )
    
    def _score_momentum(self, w: dict):
        """
        動能/相對強度評分 (核心新增)
        
        這是高盛觀點中最重要的「選股因子」：
        1. RS 相對強度：找出抗跌領漲股
        2. 布林通道壓縮：捕捉變盤前夕
        """
        # === 相對強度 (RS) ===
        rs = self.result.get('relative_strength', {})
        rs_score = rs.get('rs_score', 0)
        rs_vs_market = rs.get('vs_market', 0)
        
        if rs_score > 0 or rs_vs_market > 0:
            self.score.add_component(
                '強於大盤', w['MOMENTUM_RS_POSITIVE'],
                f'相對強度={rs_score:.0f}，逆勢抗跌，法人護盤特徵',
                ScoreCategory.MOMENTUM
            )
        
        if rs_score > 80:
            self.score.add_component(
                '市場領頭羊', w['MOMENTUM_RS_LEADER'],
                f'RS={rs_score:.0f}，強度在市場前20%，領漲股特徵',
                ScoreCategory.MOMENTUM
            )
        
        # === 布林通道壓縮 ===
        regime = self.result.get('market_regime', {})
        is_squeeze = regime.get('is_squeeze', False)
        bb_width = regime.get('bb_width', 0)
        
        if is_squeeze:
            self.score.add_component(
                '布林壓縮', w['MOMENTUM_BB_SQUEEZE'],
                f'BB寬度={bb_width:.2f}，波動率收窄，蓄勢待發',
                ScoreCategory.MOMENTUM
            )
            
            # 壓縮後突破加成
            wave = self.result.get('wave_analysis', {})
            if wave.get('breakout_signal', {}).get('detected'):
                self.score.add_component(
                    '壓縮突破', w['MOMENTUM_BB_SQUEEZE_BREAKOUT'],
                    '布林壓縮後發生突破，大行情啟動訊號',
                    ScoreCategory.MOMENTUM
                )
    
    def _score_risk(self, w: dict):
        """風險評分"""
        tech = self.result.get('technical', {})
        vol = self.result.get('volume_analysis', {})
        mr = self.result.get('mean_reversion', {})
        
        # 乖離率
        if mr.get('available'):
            bias_20 = mr.get('bias_analysis', {}).get('bias_20', 0)
            if bias_20 > 8:
                self.score.add_component(
                    '乖離率過熱', w['RISK_BIAS_OVERHEATED'],
                    f'乖離率 {bias_20:+.1f}% 超過 +8%，短線超漲',
                    ScoreCategory.RISK
                )
            elif bias_20 < -8:
                self.score.add_component(
                    '乖離率超跌', w['RISK_BIAS_OVERSOLD'],
                    f'乖離率 {bias_20:+.1f}% 低於 -8%，超跌反彈機會',
                    ScoreCategory.RISK
                )
        
        # 量縮風險
        if vol:
            volume_ratio = vol.get('volume_ratio', 1.0)
            if volume_ratio < 0.6:
                self.score.add_component(
                    '量縮風險', w['RISK_VOLUME_SHRINK'],
                    f'成交量萎縮至均量{volume_ratio*100:.0f}%',
                    ScoreCategory.RISK
                )
        
        # RR 風險回報比
        sr = self.result.get('support_resistance', {})
        current_price = self.result.get('current_price', 0)
        if current_price > 0:
            take_profit = sr.get('take_profit', current_price * 1.1)
            stop_loss = sr.get('stop_loss', current_price * 0.95)
            
            if isinstance(take_profit, (int, float)) and isinstance(stop_loss, (int, float)):
                potential_gain = (take_profit - current_price) / current_price
                potential_loss = (current_price - stop_loss) / current_price
                
                if potential_loss > 0:
                    rr_ratio = potential_gain / potential_loss
                    if rr_ratio < 1.5:
                        self.score.add_component(
                            '風險回報比不佳', w['RISK_LOW_RR'],
                            f'RR={rr_ratio:.2f} < 1.5，上檔空間有限',
                            ScoreCategory.RISK
                        )
    
    def _generate_result(self) -> Dict:
        """生成評分結果"""
        final_score = self.score.final_score
        
        # 決定標籤和建議
        label, action = self._get_score_label(final_score)
        
        # 計算信心度
        components = self.score.components
        positive_count = sum(1 for c in components if c.is_positive)
        negative_count = sum(1 for c in components if not c.is_positive)
        total_count = len(components)
        
        if total_count > 0:
            consistency = abs(positive_count - negative_count) / total_count
            deviation = abs(final_score - 50) / 50
            
            if consistency > 0.7 and deviation > 0.4:
                confidence = 'High'
            elif consistency > 0.4 or deviation > 0.2:
                confidence = 'Medium'
            else:
                confidence = 'Low'
        else:
            confidence = 'Low'
        
        # 轉換組件格式
        components_dict = [
            {
                'name': c.name,
                'score': c.score,
                'reason': c.reason,
                'category': c.category.value,
                'is_positive': c.is_positive
            }
            for c in components
        ]
        
        return {
            'score': final_score,
            'raw_score': self.score.raw_score,
            'base_score': self.score.base_score,
            'total_adjustment': self.score.total_adjustment,
            'label': label,
            'action': action,
            'confidence': confidence,
            'components': components_dict,
            'breakdown': self.score.get_breakdown(),
            'optimizer_version': 'Goldman v1.0'
        }
    
    @staticmethod
    def _get_score_label(score: float) -> Tuple[str, str]:
        """根據分數決定標籤和建議"""
        if score >= 80:
            return '強力買進', '積極做多'
        elif score >= 65:
            return '建議買進', '逢低布局'
        elif score >= 55:
            return '偏多操作', '謹慎做多'
        elif score >= 45:
            return '中性觀望', '觀望為主'
        elif score >= 35:
            return '偏空操作', '謹慎做空'
        elif score >= 20:
            return '建議賣出', '減碼出場'
        else:
            return '強力賣出', '全面撤退'


# ============================================================================
# MACD 背離偵測器
# ============================================================================
class MACDDivergenceDetector:
    """
    MACD 背離偵測器
    
    底背離（Bullish Divergence）：
    - 股價創新低
    - MACD 柱狀體底部墊高
    - 強烈反轉訊號
    
    頂背離（Bearish Divergence）：
    - 股價創新高
    - MACD 柱狀體頂部降低
    - 動能減弱訊號
    """
    
    @staticmethod
    def detect(prices: np.ndarray, macd_hist: np.ndarray, lookback: int = 20) -> Dict:
        """
        偵測 MACD 背離
        
        Args:
            prices: 價格序列
            macd_hist: MACD 柱狀體序列
            lookback: 回顧期間
        
        Returns:
            dict: 背離偵測結果
        """
        if len(prices) < lookback or len(macd_hist) < lookback:
            return {'bullish_divergence': False, 'bearish_divergence': False}
        
        # 取最近 N 根 K 棒
        recent_prices = prices[-lookback:]
        recent_macd = macd_hist[-lookback:]
        
        # 找價格低點
        price_lows = MACDDivergenceDetector._find_local_minima(recent_prices)
        price_highs = MACDDivergenceDetector._find_local_maxima(recent_prices)
        
        bullish_divergence = False
        bearish_divergence = False
        
        # 底背離：價格新低 + MACD 墊高
        if len(price_lows) >= 2:
            # 最近兩個低點
            latest_low_idx = price_lows[-1]
            prev_low_idx = price_lows[-2]
            
            if recent_prices[latest_low_idx] < recent_prices[prev_low_idx]:
                # 價格創新低
                if recent_macd[latest_low_idx] > recent_macd[prev_low_idx]:
                    # MACD 底部墊高
                    bullish_divergence = True
        
        # 頂背離：價格新高 + MACD 降低
        if len(price_highs) >= 2:
            latest_high_idx = price_highs[-1]
            prev_high_idx = price_highs[-2]
            
            if recent_prices[latest_high_idx] > recent_prices[prev_high_idx]:
                # 價格創新高
                if recent_macd[latest_high_idx] < recent_macd[prev_high_idx]:
                    # MACD 頂部降低
                    bearish_divergence = True
        
        return {
            'bullish_divergence': bullish_divergence,
            'bearish_divergence': bearish_divergence,
            'price_lows_count': len(price_lows),
            'price_highs_count': len(price_highs)
        }
    
    @staticmethod
    def _find_local_minima(data: np.ndarray, order: int = 3) -> List[int]:
        """找局部最小值的索引"""
        minima = []
        for i in range(order, len(data) - order):
            if all(data[i] <= data[i-j] for j in range(1, order+1)) and \
               all(data[i] <= data[i+j] for j in range(1, order+1)):
                minima.append(i)
        return minima
    
    @staticmethod
    def _find_local_maxima(data: np.ndarray, order: int = 3) -> List[int]:
        """找局部最大值的索引"""
        maxima = []
        for i in range(order, len(data) - order):
            if all(data[i] >= data[i-j] for j in range(1, order+1)) and \
               all(data[i] >= data[i+j] for j in range(1, order+1)):
                maxima.append(i)
        return maxima


# ============================================================================
# 相對強度計算器
# ============================================================================
class RelativeStrengthCalculator:
    """
    相對強度計算器
    
    計算個股相對於大盤的強度：
    - RS > 0: 強於大盤
    - RS > 80: 市場前 20%，領頭羊特徵
    """
    
    @staticmethod
    def calculate(stock_returns: np.ndarray, market_returns: np.ndarray, 
                  periods: List[int] = [5, 20, 60]) -> Dict:
        """
        計算相對強度
        
        Args:
            stock_returns: 個股報酬率序列
            market_returns: 大盤報酬率序列
            periods: 計算期間列表
        
        Returns:
            dict: 相對強度結果
        """
        if len(stock_returns) < max(periods) or len(market_returns) < max(periods):
            return {'rs_score': 0, 'vs_market': 0}
        
        rs_scores = []
        
        for period in periods:
            stock_perf = np.sum(stock_returns[-period:])
            market_perf = np.sum(market_returns[-period:])
            
            # 相對表現
            relative_perf = stock_perf - market_perf
            rs_scores.append(relative_perf)
        
        # 加權平均（短期權重較高）
        weights = [0.5, 0.3, 0.2]  # 5日50%、20日30%、60日20%
        weighted_rs = sum(s * w for s, w in zip(rs_scores, weights))
        
        # 轉換為 0-100 分數
        # 假設相對表現在 -10% ~ +10% 之間
        normalized_score = max(0, min(100, 50 + weighted_rs * 500))
        
        return {
            'rs_score': round(normalized_score, 1),
            'vs_market': round(weighted_rs * 100, 2),
            'rs_5d': round(rs_scores[0] * 100, 2),
            'rs_20d': round(rs_scores[1] * 100, 2),
            'rs_60d': round(rs_scores[2] * 100, 2)
        }


# ============================================================================
# 整合函數
# ============================================================================
def calculate_goldman_score(result: dict) -> Dict:
    """
    計算高盛級優化評分
    
    Args:
        result: QuickAnalyzer.analyze_stock() 的回傳結果
    
    Returns:
        dict: 優化後的評分結果
    """
    optimizer = GoldmanScoreOptimizer(result)
    return optimizer.calculate_short_term_score()


def enhance_result_with_divergence(result: dict, prices: np.ndarray, macd_hist: np.ndarray) -> dict:
    """
    為分析結果添加 MACD 背離資訊
    
    Args:
        result: 原始分析結果
        prices: 價格序列
        macd_hist: MACD 柱狀體序列
    
    Returns:
        dict: 增強後的分析結果
    """
    divergence = MACDDivergenceDetector.detect(prices, macd_hist)
    
    if 'technical' not in result:
        result['technical'] = {}
    result['technical']['macd_divergence'] = divergence
    
    return result


# ============================================================================
# 測試函數
# ============================================================================
def test_optimizer():
    """測試評分優化器"""
    # 模擬分析結果
    mock_result = {
        'current_price': 100,
        'price_change_pct': 3.5,
        'pattern_analysis': {
            'detected': True,
            'pattern_type': 'bottom',
            'status': 'FORMING',
            'pattern_name': 'W底',
            'confidence': 65
        },
        'wave_analysis': {
            'available': True,
            'breakout_signal': {'detected': True, 'volume_confirmed': True},
            'is_bullish_env': True
        },
        'volume_analysis': {
            'volume_ratio': 2.0
        },
        'volume_price': {
            'available': True,
            'signals': [{'code': 'VP05'}, {'code': 'VP09'}]
        },
        'technical': {
            'k': 25,
            'd': 20,
            'rsi': 55,
            'macd_histogram': 0.5,
            'macd_divergence': {'bullish_divergence': True, 'bearish_divergence': False}
        },
        'relative_strength': {
            'rs_score': 75,
            'vs_market': 5.2
        },
        'market_regime': {
            'is_squeeze': True,
            'bb_width': 0.05
        },
        'mean_reversion': {
            'available': True,
            'bias_analysis': {'bias_20': 2.5}
        },
        'support_resistance': {
            'take_profit': 115,
            'stop_loss': 95
        },
        'trend': {
            'ma20_slope': 0.02
        }
    }
    
    # 計算評分
    score_result = calculate_goldman_score(mock_result)
    
    print("=" * 60)
    print("高盛級評分優化器測試結果")
    print("=" * 60)
    print(f"最終分數: {score_result['score']:.0f}")
    print(f"原始分數: {score_result['raw_score']:.1f}")
    print(f"總加減分: {score_result['total_adjustment']:+.0f}")
    print(f"標籤: {score_result['label']}")
    print(f"建議: {score_result['action']}")
    print(f"信心度: {score_result['confidence']}")
    print("-" * 60)
    print("分項分數:")
    for cat, score in score_result['breakdown'].items():
        print(f"  {cat}: {score:+.0f}")
    print("-" * 60)
    print("評分組件:")
    for comp in score_result['components']:
        sign = '+' if comp['is_positive'] else ''
        print(f"  [{comp['category']}] {comp['name']}: {sign}{comp['score']:.0f}")
        print(f"    → {comp['reason']}")
    
    return score_result


if __name__ == "__main__":
    test_optimizer()
