"""
theme.py — 專業投資終端外觀（純呈現層）

集中管理主視窗的色彩、字體、ttk 樣式、Treeview 樣式、數字格式化與
matplotlib 暗色樣式。**只負責外觀，不含任何分析/資料邏輯。**

台股慣例：紅漲綠跌（UP=紅、DOWN=綠）。

用法（在 main.py 主視窗）：
    import theme
    theme.apply_theme(self)                 # root = tk.Tk()
    theme.style_treeview(self.watchlist_tree)
    theme.apply_matplotlib_dark()
"""

import tkinter.font as tkfont

# ============================================================================
# (a) 色彩 token（深色終端起始值，之後可微調）
# ============================================================================
BG_APP   = "#0E1116"   # 視窗最底
BG_PANEL = "#161A20"   # 面板/表格
BG_ELEV  = "#1C2128"   # 抬升元素（表頭、輸入框、選取列底）
DIVIDER  = "#22272E"   # 分隔線
BORDER   = "#2A2F37"   # 邊框

TEXT     = "#E6E8EB"   # 主要文字
TEXT_2   = "#8B9099"   # 次要文字
TEXT_3   = "#6B7079"   # 第三層（表頭、註解）

UP       = "#F0696A"   # 上漲（台股 紅漲）
DOWN     = "#4CB782"   # 下跌（台股 綠跌）
FLAT     = "#8B9099"   # 平盤

ACCENT   = "#EF9F27"   # 選取 / 作用中 / 連結（琥珀）

# 斑馬紋（極淡）
ROW_ODD  = BG_PANEL
ROW_EVEN = "#13171D"
ROW_SEL  = "#2A2410"   # 選取列：淡琥珀底（ACCENT 的暗化）

# ============================================================================
# (b) 字體：從候選清單挑第一個系統可用字體
# ============================================================================
_UI_FONT_CANDIDATES  = ["PingFang TC", "Microsoft JhengHei UI", "Microsoft JhengHei",
                        "Noto Sans TC", "Segoe UI"]
_NUM_FONT_CANDIDATES = ["SF Mono", "Menlo", "JetBrains Mono", "Roboto Mono",
                        "Consolas", "monospace"]

# 字級
SIZE_SMALL  = 11
SIZE_BASE   = 13
SIZE_TITLE  = 15
SIZE_BIGNUM = 21

_resolved = {"ui": None, "num": None}


def _pick_font(candidates, fallback):
    """從候選清單挑第一個系統實際可用的字體；都沒有時回 fallback。"""
    try:
        available = set(tkfont.families())
    except Exception:
        return fallback
    for name in candidates:
        if name in available:
            return name
    return fallback


def ui_font(size=SIZE_BASE, bold=False):
    """中文 UI 字體 (family, size, weight)。"""
    if _resolved["ui"] is None:
        _resolved["ui"] = _pick_font(_UI_FONT_CANDIDATES, "TkDefaultFont")
    return (_resolved["ui"], size, "bold" if bold else "normal")


def num_font(size=SIZE_BASE, bold=False):
    """數字等寬字體 (family, size, weight)。"""
    if _resolved["num"] is None:
        _resolved["num"] = _pick_font(_NUM_FONT_CANDIDATES, "TkFixedFont")
    return (_resolved["num"], size, "bold" if bold else "normal")


# ============================================================================
# (c) apply_theme(root)：統一 ttk 樣式（base theme = 'clam'，最易客製）
# ============================================================================
def apply_theme(root):
    """套用整體深色扁平樣式到 root 與所有 ttk widget。"""
    from tkinter import ttk

    try:
        root.configure(bg=BG_APP)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")   # clam 最容易客製、可移除立體邊框
    except Exception:
        pass

    f_base  = ui_font(SIZE_BASE)
    f_small = ui_font(SIZE_SMALL)
    f_bold  = ui_font(SIZE_BASE, bold=True)

    # ── 容器 ──────────────────────────────────────────────
    style.configure("TFrame", background=BG_PANEL, borderwidth=0, relief="flat")
    style.configure("TLabelframe", background=BG_PANEL, borderwidth=1,
                    relief="flat", bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG_PANEL,
                    foreground=TEXT_3, font=f_small)
    style.configure("TPanedwindow", background=BG_APP)

    # ── Label ─────────────────────────────────────────────
    style.configure("TLabel", background=BG_PANEL, foreground=TEXT, font=f_base)

    # ── Button（扁平 + 琥珀 hover）────────────────────────
    style.configure("TButton", background=BG_ELEV, foreground=TEXT,
                    font=f_base, borderwidth=0, relief="flat",
                    focuscolor=BG_ELEV, padding=(10, 5))
    style.map("TButton",
              background=[("pressed", ACCENT), ("active", BORDER)],
              foreground=[("pressed", BG_APP), ("active", TEXT)])

    # ── Entry / Combobox ─────────────────────────────────
    style.configure("TEntry", fieldbackground=BG_ELEV, foreground=TEXT,
                    insertcolor=ACCENT, borderwidth=0, relief="flat", padding=4)
    style.configure("TCombobox", fieldbackground=BG_ELEV, background=BG_ELEV,
                    foreground=TEXT, arrowcolor=TEXT_2, borderwidth=0,
                    relief="flat", padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", BG_ELEV)],
              foreground=[("readonly", TEXT)])

    # ── Checkbutton / Radiobutton ────────────────────────
    for w in ("TCheckbutton", "TRadiobutton"):
        style.configure(w, background=BG_PANEL, foreground=TEXT, font=f_base,
                        focuscolor=BG_PANEL, indicatorcolor=BG_ELEV)
        style.map(w, background=[("active", BG_PANEL)],
                  foreground=[("active", ACCENT)])

    # ── Notebook（分頁扁平化）────────────────────────────
    style.configure("TNotebook", background=BG_APP, borderwidth=0, tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", background=BG_APP, foreground=TEXT_2,
                    font=f_base, padding=(14, 6), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", BG_PANEL)],
              foreground=[("selected", ACCENT), ("active", TEXT)])

    # ── Scrollbar ────────────────────────────────────────
    style.configure("Vertical.TScrollbar", background=BG_ELEV, troughcolor=BG_APP,
                    borderwidth=0, arrowcolor=TEXT_3)
    style.configure("Horizontal.TScrollbar", background=BG_ELEV, troughcolor=BG_APP,
                    borderwidth=0, arrowcolor=TEXT_3)

    # ── Separator ────────────────────────────────────────
    style.configure("TSeparator", background=DIVIDER)

    # ── Treeview 基礎（細節在 style_treeview）─────────────
    style.configure("Treeview", background=BG_PANEL, fieldbackground=BG_PANEL,
                    foreground=TEXT, borderwidth=0, relief="flat",
                    rowheight=27, font=num_font(SIZE_BASE))
    style.configure("Treeview.Heading", background=BG_ELEV, foreground=TEXT_3,
                    font=ui_font(SIZE_SMALL, bold=True), borderwidth=0, relief="flat")
    style.map("Treeview.Heading", background=[("active", BG_ELEV)])
    style.map("Treeview",
              background=[("selected", ROW_SEL)],
              foreground=[("selected", ACCENT)])

    return style


# ============================================================================
# (d) style_treeview(tree)：資料網格化 + 斑馬紋 + 漲跌 tag
# ============================================================================
def style_treeview(tree, zebra=True):
    """
    把 Treeview 做成資料網格：扁平表頭、斑馬紋、漲跌紅綠 tag、選取列琥珀。
    回傳常用 tag 名供呼叫端套用。
    """
    # 斑馬紋
    if zebra:
        tree.tag_configure("odd",  background=ROW_ODD,  foreground=TEXT)
        tree.tag_configure("even", background=ROW_EVEN, foreground=TEXT)

    # 漲跌（台股 紅漲綠跌）
    tree.tag_configure("up",   foreground=UP)
    tree.tag_configure("down", foreground=DOWN)
    tree.tag_configure("flat", foreground=FLAT)

    # 量化建議分級（與原 buy/hold/sell/wait 對應，改用新 token）
    tree.tag_configure("buy",  foreground=UP)     # 買 = 紅
    tree.tag_configure("hold", foreground=ACCENT) # 持有 = 琥珀
    tree.tag_configure("sell", foreground=DOWN)   # 賣 = 綠
    tree.tag_configure("wait", foreground=TEXT_2) # 觀望 = 灰

    # 族群分組標題列
    tree.tag_configure("group", background=BG_ELEV, foreground=TEXT_3,
                       font=ui_font(SIZE_SMALL, bold=True))

    # 過熱 / 超跌（淡背景）
    tree.tag_configure("hot",  background="#241115")
    tree.tag_configure("cold", background="#0F1F18")

    return tree


# ============================================================================
# (e) 數字格式化 + 漲跌上色 helper
# ============================================================================
def fmt_price(x, decimals=2):
    """千分位、固定小數位。無效值回 '-'。"""
    try:
        return f"{float(x):,.{decimals}f}"
    except (TypeError, ValueError):
        return "-"


def fmt_pct(x, decimals=2, sign=True):
    """百分比，帶 +/- 號。傳入已是百分比數值（如 1.56 表示 +1.56%）。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    s = f"{v:+.{decimals}f}%" if sign else f"{v:.{decimals}f}%"
    return s


def fmt_change(x, decimals=2):
    """漲跌值，帶 +/- 號。"""
    try:
        return f"{float(x):+,.{decimals}f}"
    except (TypeError, ValueError):
        return "-"


def trend_color(x):
    """x>0→UP(紅)、x<0→DOWN(綠)、=0→FLAT。台股紅漲綠跌。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return FLAT
    if v > 0:
        return UP
    if v < 0:
        return DOWN
    return FLAT


def trend_tag(x):
    """回傳 'up'/'down'/'flat' tag 名，供 Treeview tag 套用。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "flat"
    return "up" if v > 0 else ("down" if v < 0 else "flat")


# ============================================================================
# (f) apply_matplotlib_dark()：只改繪圖樣式，不碰指標/訊號計算
# ============================================================================
def apply_matplotlib_dark():
    """設定 matplotlib rcParams 為暗色面板風（與 BG_PANEL 同色）。"""
    try:
        import matplotlib as mpl
    except Exception:
        return
    mpl.rcParams.update({
        "figure.facecolor": BG_PANEL,
        "axes.facecolor":   BG_PANEL,
        "savefig.facecolor": BG_PANEL,
        "axes.edgecolor":   BORDER,
        "axes.labelcolor":  TEXT_2,
        "axes.titlecolor":  TEXT,
        "xtick.color":      TEXT_2,
        "ytick.color":      TEXT_2,
        "text.color":       TEXT,
        "grid.color":       DIVIDER,
        "grid.alpha":       0.08,
        "axes.grid":        True,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "figure.edgecolor": BG_PANEL,
    })


def mpf_market_style():
    """
    回傳給 mplfinance 用的 (marketcolors, style dict) ——
    紅漲綠跌、暗色面板。只供繪圖，不影響任何計算。
    呼叫端：mc, base_kw = theme.mpf_market_style()
    """
    import mplfinance as mpf
    mc = mpf.make_marketcolors(up=UP, down=DOWN, edge="inherit",
                               wick={"up": UP, "down": DOWN},
                               volume="#3A3F47")
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mc,
        facecolor=BG_PANEL,
        figcolor=BG_PANEL,
        edgecolor=BORDER,
        gridcolor=DIVIDER,
        gridstyle="-",
        rc={"axes.grid.axis": "y", "grid.alpha": 0.08,
            "font.sans-serif": ["PingFang TC", "Microsoft JhengHei",
                                "Heiti TC", "Arial Unicode MS"]},
    )
    return mc, style
