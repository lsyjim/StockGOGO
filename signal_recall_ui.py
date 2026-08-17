"""
signal_recall_ui.py — 訊號驗證視窗（獨立 Toplevel，不佔主畫面版位）

版面（由上而下）：
  1. 控制列：清單來源下拉 ＋「開始驗證」＋ 進度
  2. 四日摘要卡（T-4→T-1）：各等級「檔數｜隔日上漲數/有效數」
  3. 四日合計表：列＝A/B/C/R/賣出，欄＝短線隔日／中線方向／長線方向
  4. 逐檔明細（Treeview）：可依日期/等級篩選，雙擊開完整報告

配色一律取自 theme.py token（A琥珀/B藍/C灰/R紫/賣出綠；漲紅跌綠），不 hardcode。
"""

from __future__ import annotations

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import theme
import signal_recall as SR

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _label_color(label):
    return {
        'A': theme.ACCENT, 'B': theme.GRADE_B, 'C': theme.TEXT_2,
        'R': theme.R_TRACK, '賣出': theme.ACTION_SELL,
    }.get(label, theme.TEXT_2)


class SignalRecallWindow(tk.Toplevel):
    """訊號驗證視窗：T-4~T-1 樣本外重放 + 隔日/中長期命中統計。"""

    def __init__(self, parent, db_name, get_watchlist):
        super().__init__(parent)
        self.parent = parent
        self.db_name = db_name
        self.get_watchlist = get_watchlist
        self.rows = []
        self._running = False

        self.title("訊號驗證 — T-4~T-1 樣本外重放")
        self.geometry("1080x820")
        self.configure(bg=theme.BG_APP)

        self._build_control_row()
        self._build_cards()
        self._build_totals()
        self._build_detail()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 1. 控制列 ────────────────────────────────────────────────────────
    def _build_control_row(self):
        bar = tk.Frame(self, bg=theme.BG_APP)
        bar.pack(fill=tk.X, padx=12, pady=(12, 6))

        tk.Label(bar, text="清單來源", bg=theme.BG_APP, fg=theme.TEXT_2).pack(side=tk.LEFT)
        self.source_var = tk.StringVar(value="Watchlist")
        self.source_cb = ttk.Combobox(bar, textvariable=self.source_var, width=26,
                                      state="readonly", values=self._list_sources())
        self.source_cb.pack(side=tk.LEFT, padx=(6, 12))

        self.run_btn = tk.Button(bar, text="開始驗證", command=self._start,
                                 bg=theme.ACCENT, fg="#1a1400", relief=tk.FLAT, bd=0,
                                 padx=14, pady=4, cursor="hand2")
        self.run_btn.pack(side=tk.LEFT)

        self.progress_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.progress_var, bg=theme.BG_APP,
                 fg=theme.ACCENT).pack(side=tk.LEFT, padx=10)

        tk.Label(bar, text="※ 中長期為方向追蹤中，非最終結果", bg=theme.BG_APP,
                 fg=theme.TEXT_3).pack(side=tk.RIGHT)

    def _list_sources(self):
        srcs = ["Watchlist"]
        try:
            p = os.path.join(_ROOT, 'theme_map.json')
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    themes = (json.load(f).get('themes') or {})
                srcs += [f"Watchlist ＋ {t}" for t in themes]
                srcs.append("Watchlist ＋ 全部題材")
        except Exception:
            pass
        return srcs

    def _resolve_symbols(self):
        """依下拉選擇組出 [(code,name,market)]（已去重）。"""
        try:
            base = list(self.get_watchlist() or [])
        except Exception:
            base = []
        syms = [(str(s[0]), (s[1] if len(s) > 1 else str(s[0])),
                 (s[2] if len(s) > 2 else '台股')) for s in base]

        sel = self.source_var.get()
        if sel != "Watchlist":
            try:
                with open(os.path.join(_ROOT, 'theme_map.json'), encoding='utf-8') as f:
                    themes = (json.load(f).get('themes') or {})
                if sel.endswith("全部題材"):
                    add = [c for v in themes.values() for c in v]
                else:
                    add = themes.get(sel.split("＋", 1)[1].strip(), [])
                for c in add:
                    syms.append((str(c), str(c), '台股'))
            except Exception as e:
                print(f"[訊號驗證] 題材清單讀取略過: {e}")

        seen, uniq = set(), []
        for s in syms:
            if s[0] in seen:
                continue
            seen.add(s[0])
            uniq.append(s)
        return uniq

    # ── 2. 四日摘要卡 ────────────────────────────────────────────────────
    def _build_cards(self):
        wrap = tk.LabelFrame(self, text=" 四日摘要（T-4 → T-1）", bg=theme.BG_APP,
                             fg=theme.TEXT_2, bd=1, relief=tk.SOLID)
        wrap.pack(fill=tk.X, padx=12, pady=6)
        self.cards_frame = tk.Frame(wrap, bg=theme.BG_APP)
        self.cards_frame.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(self.cards_frame, text="尚未執行驗證", bg=theme.BG_APP,
                 fg=theme.TEXT_3).pack()

    def _render_cards(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        by_date = SR.summarize_by_date(self.rows)
        if not by_date:
            tk.Label(self.cards_frame, text="無資料", bg=theme.BG_APP,
                     fg=theme.TEXT_3).pack()
            return
        for i, d in enumerate(sorted(by_date)):
            card = tk.Frame(self.cards_frame, bg=theme.BG_PANEL,
                            highlightbackground=theme.BORDER, highlightthickness=1)
            card.grid(row=0, column=i, sticky="nsew", padx=4)
            self.cards_frame.columnconfigure(i, weight=1)
            tk.Label(card, text=d, bg=theme.BG_PANEL, fg=theme.TEXT,
                     font=("Arial", 11, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
            for lab in SR.LABELS:
                s = by_date[d].get(lab)
                if not s:
                    continue     # 無資料的等級整列省略
                r = tk.Frame(card, bg=theme.BG_PANEL)
                r.pack(fill=tk.X, padx=8, pady=1)
                tk.Label(r, text=lab, bg=theme.BG_PANEL, fg=_label_color(lab),
                         width=4, anchor="w").pack(side=tk.LEFT)
                txt = f"{s['n']} 檔"
                if s['valid']:
                    txt += f"｜隔日漲 {s['up']}/{s['valid']}"
                tk.Label(r, text=txt, bg=theme.BG_PANEL,
                         fg=theme.TEXT_2).pack(side=tk.LEFT)
            tk.Frame(card, bg=theme.BG_PANEL, height=6).pack()

    # ── 3. 合計表 ────────────────────────────────────────────────────────
    def _build_totals(self):
        wrap = tk.LabelFrame(self, text=" 四日合計｜短中長期命中", bg=theme.BG_APP,
                             fg=theme.TEXT_2, bd=1, relief=tk.SOLID)
        wrap.pack(fill=tk.X, padx=12, pady=6)
        self.totals_frame = tk.Frame(wrap, bg=theme.BG_APP)
        self.totals_frame.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(self.totals_frame, text="尚未執行驗證", bg=theme.BG_APP,
                 fg=theme.TEXT_3).pack()

    def _current_close(self, symbol):
        return self._cur_closes.get(str(symbol))

    def _render_totals(self):
        for w in self.totals_frame.winfo_children():
            w.destroy()
        tot = SR.summarize_totals(self.rows, cur_close_fn=self._current_close)
        hdr = ["等級", "檔數", "短線（隔日）", "中線（方向）", "長線（方向）"]
        for c, h in enumerate(hdr):
            tk.Label(self.totals_frame, text=h, bg=theme.BG_ELEV, fg=theme.TEXT_3,
                     width=(8 if c == 0 else 16), anchor="w",
                     padx=6, pady=3).grid(row=0, column=c, sticky="we", padx=1, pady=1)
        r = 1
        for lab in SR.LABELS:
            s = tot.get(lab)
            if not s:
                continue
            tk.Label(self.totals_frame, text=lab, bg=theme.BG_PANEL, fg=_label_color(lab),
                     width=8, anchor="w", padx=6, pady=3).grid(row=r, column=0, sticky="we", padx=1, pady=1)
            vals = [str(s['n']), SR.fmt_rate(s['short']),
                    ('—' if lab == 'R' else SR.fmt_rate(s['mid'])),
                    ('—' if lab == 'R' else SR.fmt_rate(s['long']))]
            for c, v in enumerate(vals, start=1):
                tk.Label(self.totals_frame, text=v, bg=theme.BG_PANEL, fg=theme.TEXT,
                         width=16, anchor="w", padx=6, pady=3).grid(row=r, column=c, sticky="we", padx=1, pady=1)
            r += 1
        if r == 1:
            tk.Label(self.totals_frame, text="無資料", bg=theme.BG_APP,
                     fg=theme.TEXT_3).grid(row=1, column=0)

    # ── 4. 逐檔明細 ──────────────────────────────────────────────────────
    def _build_detail(self):
        wrap = tk.LabelFrame(self, text=" 逐檔明細（雙擊開完整報告）", bg=theme.BG_APP,
                             fg=theme.TEXT_2, bd=1, relief=tk.SOLID)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))

        fbar = tk.Frame(wrap, bg=theme.BG_APP)
        fbar.pack(fill=tk.X, padx=8, pady=(6, 2))
        tk.Label(fbar, text="日期", bg=theme.BG_APP, fg=theme.TEXT_2).pack(side=tk.LEFT)
        self.f_date = ttk.Combobox(fbar, width=14, state="readonly", values=["全部"])
        self.f_date.set("全部"); self.f_date.pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(fbar, text="等級", bg=theme.BG_APP, fg=theme.TEXT_2).pack(side=tk.LEFT)
        self.f_label = ttk.Combobox(fbar, width=10, state="readonly",
                                    values=["全部"] + list(SR.LABELS))
        self.f_label.set("全部"); self.f_label.pack(side=tk.LEFT, padx=4)
        self.f_date.bind("<<ComboboxSelected>>", lambda e: self._render_detail())
        self.f_label.bind("<<ComboboxSelected>>", lambda e: self._render_detail())

        cols = ("date", "symbol", "name", "label", "t_close", "t1_close", "pct")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=14)
        for c, txt, w in [("date", "日期", 95), ("symbol", "代號", 70),
                          ("name", "名稱", 130), ("label", "推薦", 70),
                          ("t_close", "T收盤", 90), ("t1_close", "T+1收盤", 90),
                          ("pct", "隔日%", 80)]:
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=("w" if c in ("name",) else "center"))
        try:
            theme.style_treeview(self.tree)
        except Exception:
            pass
        for lab in SR.LABELS:
            self.tree.tag_configure(f"lab_{lab}", foreground=_label_color(lab))
        self.tree.tag_configure("up", foreground=theme.PRICE_UP)
        self.tree.tag_configure("down", foreground=theme.PRICE_DOWN)
        self.tree.tag_configure("stale", foreground=theme.TEXT_3)   # 缺 T+1：降透明度示意
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 8))
        self.tree.bind("<Double-1>", self._open_report)

    def _render_detail(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        fd, fl = self.f_date.get(), self.f_label.get()
        for r in self.rows:
            if fd != "全部" and r['date'] != fd:
                continue
            if fl != "全部" and r['label'] != fl:
                continue
            pct = r.get('next_day_pct')
            tags = [f"lab_{r['label']}"]
            if pct is None:
                pct_txt = '—'
                tags = ["stale"]          # 不計入統計，整列淡化
            else:
                pct_txt = f"{pct:+.2f}%"
                tags.append("up" if pct > 0 else "down")
            self.tree.insert("", "end", values=(
                r['date'], r['symbol'], r.get('name', ''), r['label'],
                (f"{r['t_close']:.2f}" if r.get('t_close') else '—'),
                (f"{r['t1_close']:.2f}" if r.get('t1_close') else '—'),
                pct_txt), tags=tuple(tags))

    def _open_report(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        v = self.tree.item(sel[0], 'values')
        date_str, symbol = v[0], v[1]
        try:
            import datetime
            from main import QuickAnalyzer, RecommendationDialog
            dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            res = QuickAnalyzer.analyze_stock(symbol, '台股', analysis_date=dt)
            if not res:
                messagebox.showwarning("無法產生", f"{symbol} @ {date_str} 無足夠歷史資料")
                return
            RecommendationDialog(self, res)
        except Exception as e:
            messagebox.showerror("錯誤", f"開啟報告失敗：{e}")

    # ── 執行 ─────────────────────────────────────────────────────────────
    def _start(self):
        if self._running:
            return
        syms = self._resolve_symbols()
        if not syms:
            messagebox.showinfo("提示", "清單為空")
            return
        self._running = True
        self.run_btn.config(state=tk.DISABLED)
        self.progress_var.set("準備中…")

        def work():
            try:
                dates = SR.recent_trading_days(self.db_name, 4)
                if not dates:
                    self.after(0, lambda: self.progress_var.set("無交易日曆資料"))
                    return

                def cb(done, total):
                    self.after(0, lambda: self.progress_var.set(f"{done}/{total} 完成"))

                rows = SR.run_recall(syms, dates, self.db_name, progress_cb=cb)
                # 中長期方向驗證用的「目前收盤」
                closes = {}
                try:
                    from main import DataSourceManager
                    for c, _n, m in syms:
                        try:
                            h = DataSourceManager.get_history(c, m, period='6mo')
                            if h is not None and len(h):
                                closes[c] = float(h['Close'].iloc[-1])
                        except Exception:
                            continue
                except Exception:
                    pass
                self.after(0, lambda: self._done(rows, dates, closes))
            except Exception as e:
                self.after(0, lambda: self.progress_var.set(f"失敗：{e}"))
            finally:
                self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
                self._running = False

        threading.Thread(target=work, daemon=True).start()

    def _done(self, rows, dates, closes):
        self.rows = rows
        self._cur_closes = closes
        self.f_date.config(values=["全部"] + sorted({r['date'] for r in rows}))
        self._render_cards()
        self._render_totals()
        self._render_detail()
        self.progress_var.set(f"完成：{len(rows)} 筆訊號（{len(dates)} 個交易日）")

    def _on_close(self):
        self._running = False
        self.destroy()


def open_signal_recall_window(parent, db_name, get_watchlist):
    win = SignalRecallWindow(parent, db_name, get_watchlist)
    win._cur_closes = {}
    return win
