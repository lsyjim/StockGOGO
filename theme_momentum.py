"""
theme_momentum.py — 族群動能因子（build_prompt_08 任務2）

順勢流派核心：強者恆強、只做主流題材、買領導股。量化為「題材相對強度」。

**只做顯示與排序加成，不進 grade**（同月營收動能的架構原則）。

用法：
    tm = ThemeMomentum()                       # 讀 theme_map.json
    strength = tm.compute(rets)                 # rets={symbol:{'ret20','ret60'}}
    info = tm.annotate('2327', strength)        # {theme_name, theme_rank_pct, is_top_theme, is_theme_leader}

題材分類來自 theme_map.json（可手動編輯生效；預留 MVPTracker 概念圖 v5 匯入介面）。
"""

from __future__ import annotations

import os
import json

_DEFAULT_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme_map.json")
_TOP_N = 3   # 題材排名前 N 視為主流（is_top_theme）


class ThemeMomentum:
    def __init__(self, map_path: str = None):
        self.map_path = map_path or _DEFAULT_MAP
        self.themes = {}          # {theme_name: [symbols]}
        self.sym2theme = {}       # {symbol: theme_name}
        self._load()

    def _load(self):
        try:
            with open(self.map_path, encoding="utf-8") as f:
                data = json.load(f)
            self.themes = {k: [str(s) for s in v] for k, v in (data.get("themes") or {}).items()}
        except Exception as e:
            print(f"[Theme] theme_map.json 讀取失敗: {e}")
            self.themes = {}
        self.sym2theme = {}
        for th, syms in self.themes.items():
            for s in syms:
                self.sym2theme.setdefault(str(s), th)   # 首個題材為主（避免重複歸屬）

    def all_symbols(self):
        return sorted(self.sym2theme.keys())

    def compute(self, rets: dict) -> dict:
        """
        rets: {symbol: {'ret20': float, 'ret60': float(可選)}}（%）
        回傳 {theme_name: {'ret20', 'rank_pct', 'is_top', 'leader', 'n'}}。
        rank_pct = 橫斷面百分位（0–100，越高越強）；leader = 題材內 60 日 RS 第一。
        """
        theme_ret = {}
        theme_leader = {}
        for th, syms in self.themes.items():
            r20 = [rets[s]["ret20"] for s in syms if s in rets and rets[s].get("ret20") is not None]
            if not r20:
                continue
            theme_ret[th] = sum(r20) / len(r20)   # 等權 20 日報酬
            # 領導股：題材內 60 日 RS 最高（無 60 日則退回 20 日）
            cand = [(s, rets[s].get("ret60", rets[s].get("ret20")))
                    for s in syms if s in rets and rets[s].get("ret60", rets[s].get("ret20")) is not None]
            theme_leader[th] = max(cand, key=lambda x: x[1])[0] if cand else None

        if not theme_ret:
            return {}
        # 橫斷面百分位排名
        vals = sorted(theme_ret.values())
        n = len(vals)
        import bisect
        ranked = sorted(theme_ret.items(), key=lambda x: -x[1])
        top_set = {th for th, _ in ranked[:_TOP_N]}
        out = {}
        for th, rv in theme_ret.items():
            lo = bisect.bisect_left(vals, rv)
            hi = bisect.bisect_right(vals, rv)
            pct = round((lo + hi) / 2.0 / n * 100, 1) if n > 0 else 50.0
            out[th] = {
                "ret20": round(rv, 2), "rank_pct": pct,
                "is_top": th in top_set,
                "leader": theme_leader.get(th),
                "n": len([s for s in self.themes[th] if s in rets]),
            }
        return out

    def annotate(self, symbol: str, strength: dict) -> dict:
        """個股加註題材欄位（顯示/排序用，不進 grade）。"""
        th = self.sym2theme.get(str(symbol))
        if not th or th not in (strength or {}):
            return {"theme_name": th, "theme_rank_pct": None,
                    "is_top_theme": False, "is_theme_leader": False}
        s = strength[th]
        return {
            "theme_name": th,
            "theme_rank_pct": s["rank_pct"],
            "is_top_theme": bool(s["is_top"]),
            "is_theme_leader": bool(s.get("leader") == str(symbol)),
        }

    def ranking(self, strength: dict):
        """題材強度排行榜（新→舊）：[(theme, ret20, rank_pct, leader)]。"""
        return sorted(
            [(th, s["ret20"], s["rank_pct"], s.get("leader")) for th, s in (strength or {}).items()],
            key=lambda x: -x[2])
