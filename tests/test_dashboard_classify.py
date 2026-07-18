"""fix_13b P0-2：清單分類（_classify_stock / _row_visuals）驗收測試。

核心防回歸：SKIP（建議文字含「不參與」/「避開」/「不建議關注」）**不得**被分成賣訊、
不得顯示「賣」徽章、不得被「賣訊」過濾收進去；必須是灰底「跳」徽章。
真賣訊（賣出／出場）才分成賣、顯示「賣」、被賣訊過濾收進去。

呼叫真正的 StockAnalysisApp._classify_stock / _row_visuals / _row_matches，
以 dummy self 綁定（避免建立 tkinter 視窗）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from main import StockAnalysisApp


class _FakeApp:
    """最小 self：_classify_stock/_row_visuals/_row_matches 只用到這些屬性。"""
    _theme = None
    _search_text = ''
    _active_filter = 'all'
    _r_strength_map = {}
    # _row_visuals / _classify_stock 內部呼叫的 staticmethod
    _r_badge_text = staticmethod(StockAnalysisApp._r_badge_text)
    _verdict_from_text = staticmethod(StockAnalysisApp._verdict_from_text)


# get_all_stocks 欄位序（database.get_all_stocks）：
# 0 symbol,1 name,2 market,3 added,4 notes,5 recommendation,6 industry,
# 7 sort_order,8 quant_score,9 trend_status,10 chip_signal,11 bias_20,12 last_analyzed
def _row(symbol, name, recommendation, score=50, bias=0.0):
    r = [''] * 13
    r[0] = symbol
    r[1] = name
    r[5] = recommendation
    r[8] = score
    r[11] = bias
    return r


def _classify(row, rmap=None):
    return StockAnalysisApp._classify_stock(_FakeApp(), row, rmap or {})


def _visuals(cls):
    return StockAnalysisApp._row_visuals(_FakeApp(), cls)


# ── SKIP 情境（P0-2 核心）──────────────────────────────────────────────
def test_skip_with_verdict_tag_is_not_sell():
    """新格式：recommendation 第 5 段直接帶引擎 verdict='SKIP'。"""
    row = _row('3227', '原相', '不建議關注|方向不對|不參與|方向分 14 < 40|SKIP')
    cls = _classify(row)
    assert cls['verdict'] == 'SKIP'
    assert cls['is_skip'] is True
    assert cls['is_sell'] is False
    assert cls['grade'] == ''
    tags, score_str, grade_badge, r_badge, adv = _visuals(cls)
    assert grade_badge == '跳'            # 灰底「跳」，不是「賣」
    assert 'skip' in tags
    assert 'sell' not in tags


def test_skip_legacy_text_avoid_is_not_sell():
    """舊格式（4 段，無 verdict）：中線建議文字含「避開」，仍須判為 SKIP，不落賣訊。"""
    row = _row('3227', '原相', '不建議關注|方向不對|不參與|避開')
    cls = _classify(row)
    assert cls['is_skip'] is True
    assert cls['is_sell'] is False
    _, _, grade_badge, _, _ = _visuals(cls)
    assert grade_badge == '跳'


def test_skip_excluded_from_sell_filter():
    """賣訊過濾（chip/摘要卡）不得收進 SKIP。"""
    app = _FakeApp()
    app._active_filter = 'SELL'
    cls = _classify(_row('3227', '原相', '不建議關注|方向不對|不參與|避開'))
    assert StockAnalysisApp._row_matches(app, cls) is False


def test_skip_rtrade_adds_reconcile_note():
    """P2-10：R-TRADE 成立且 SKIP（不參與）→ 建議欄追加「·R反彈可交易」。"""
    cls = _classify(_row('3227', '原相', '不建議關注|方向不對|不參與|避開|SKIP'),
                    rmap={'3227': 'R-TRADE'})
    _, _, _, r_badge, adv = _visuals(cls)
    assert r_badge.startswith('◆R')
    assert 'R反彈可交易' in adv


# ── 真賣訊情境 ─────────────────────────────────────────────────────────
def test_genuine_sell_classifies_as_sell():
    row = _row('2498', '宏達電', '建議賣出（頭部確立）|賣出訊號|賣出 / 出場|形態跌破|SELL')
    cls = _classify(row)
    assert cls['is_sell'] is True
    assert cls['is_skip'] is False
    assert cls['grade'] == ''
    tags, _, grade_badge, _, _ = _visuals(cls)
    assert grade_badge == '賣'
    assert 'sell' in tags


def test_genuine_sell_included_in_sell_filter():
    app = _FakeApp()
    app._active_filter = 'SELL'
    cls = _classify(_row('2498', '宏達電', '建議賣出|賣出訊號|賣出 / 出場|形態跌破|SELL'))
    assert StockAnalysisApp._row_matches(app, cls) is True


def test_sell_legacy_text_without_verdict():
    """舊格式真賣訊（無第 5 段），文字含「賣出/出場」→ SELL。"""
    cls = _classify(_row('2498', '宏達電', '建議賣出（頭部確立）|賣出訊號|賣出 / 出場|形態跌破'))
    assert cls['is_sell'] is True
    assert cls['is_skip'] is False


# ── 等級 / R 徽章 ──────────────────────────────────────────────────────
def test_grade_a_badge_and_tag():
    cls = _classify(_row('2330', '台積電', 'A 級主攻，立即進場|A 級主攻|積極進場|順勢|A'))
    assert cls['grade'] == 'A'
    tags, _, grade_badge, _, _ = _visuals(cls)
    assert grade_badge == 'A'
    assert 'grade_A' in tags


def test_r_strength_badge_strong_vs_moderate():
    assert StockAnalysisApp._r_badge_text('R-TRADE', 'strong') == '◆R+'
    assert StockAnalysisApp._r_badge_text('R-TRADE', 'moderate') == '◆R'
    assert StockAnalysisApp._r_badge_text('R-TRADE', None) == '◆R'
    assert StockAnalysisApp._r_badge_text('R-WATCH', 'strong') == '◇r'
    assert StockAnalysisApp._r_badge_text(None, None) == ''


def test_verdict_from_text_precedence():
    """SKIP 一律先於賣訊：'不建議關注' 內含「不建議」，不得被判為 SELL。"""
    f = StockAnalysisApp._verdict_from_text
    assert f('不建議關注', '方向不對', '不參與') == 'SKIP'
    assert f('等待拉回', '位置不佳', '觀望') == 'WAIT'
    assert f('建議賣出（頭部確立）', '賣出訊號', '賣出 / 出場') == 'SELL'
    assert f('A 級主攻，立即進場', 'A 級主攻', '積極進場') == 'A'


def test_compose_recommendation_appends_verdict():
    """P0-2：組字串時把 decision_matrix['scenario'] 附為第 5 段。"""
    s = main._compose_recommendation('不建議關注', '方向不對', '不參與', '方向分 14 < 40',
                                     {'decision_matrix': {'scenario': 'SKIP'}})
    assert s.split('|')[4] == 'SKIP'
    # 無 scenario → 維持 4 段（向下相容）
    s2 = main._compose_recommendation('A', 'A 級主攻', '進場', '順勢', {})
    assert len(s2.split('|')) == 4
