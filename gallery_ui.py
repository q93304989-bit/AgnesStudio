"""视觉陈列版组件。

三个可复用部件：
  1. AspectPicker  —— 图示化画幅选择（画出真实比例的缩略矩形，替代 "1920x1080" 裸数字）
  2. GalleryGrid   —— 瀑布流画廊（最短列优先放置，保留原始宽高比）
  3. Lightbox      —— 大图查看器（ESC 关闭 / ←→ 切换 / 滚轮 10%~400% 缩放 / 拖拽平移）

设计约束：
  - 8px 间距网格、圆角 12/8/999 三档、控件高度 28
  - 设计 token 统一从 ui_theme.py 引用（单一事实来源，含浅 / 深双主题）
  - 网络请求一律外抛给调用方（loader 回调），本模块只负责 UI 与图像处理
"""
import math
import os
import sys
import subprocess
import tkinter as tk
from io import BytesIO

import customtkinter as ctk
from PIL import Image, ImageTk

import history_store
from history_ui import short_time

# ===================== Design Token：统一从 ui_theme 引用（单一事实来源） =====================
import ui_theme
import ui_anim  # 弹层淡入淡出 / 减弱动态效果
from ui_theme import (
    PAGE_BG, CARD_BG, CARD_BORDER, FIELD_BORDER,
    TEXT_MAIN, TEXT_SUB, TEXT_DISABLED,
    ACCENT, ACCENT_TEXT, ACCENT_SOFT,
    FILL, FILL_HOVER,
    ERROR_BG, ERROR_TEXT, SUCCESS_BG, SUCCESS_TEXT,
    VIDEO_BG, VIDEO_TEXT,
    OVERLAY_BG, OVERLAY_HOVER, OVERLAY_TEXT,
    LB_BG, LB_BAR, LB_BTN, LB_BTN_HOVER, LB_TEXT, LB_TEXT_DIM, LB_HINT,
    SCROLLBAR, SCROLLBAR_HOVER,
    S_XS, S_SM, CARD_PAD,
    R_CTRL, R_THUMB, R_PILL,
    H_CHIP,
)

# 画廊一次最多渲染的卡片数（图片解码成本高于列表，故低于列表的 200）
GALLERY_RENDER_LIMIT = 120
# 卡片信息条高度（缩略图下方：徽标+时间 一行、提示词 一行）
CARD_FOOTER_H = 56
# 单张缩略图最高不超过列宽的 1.8 倍，避免长图霸屏
CARD_MAX_RATIO = 1.8


# ===================== 通用工具 =====================
def aspect_of_size(size_str: str) -> str:
    """'1920x1080' → '16:9'；无法解析时返回 '1:1'"""
    try:
        w, h = (int(x) for x in str(size_str).lower().split("x"))
        if w <= 0 or h <= 0:
            return "1:1"
        g = math.gcd(w, h)
        return f"{w // g}:{h // g}"
    except Exception:
        return "1:1"


def ratio_to_float(ratio: str) -> float:
    """'16:9' → 0.5625（高/宽），解析失败返回 1.0"""
    try:
        w, h = (float(x) for x in str(ratio).split(":"))
        return (h / w) if w else 1.0
    except Exception:
        return 1.0


def _load_image(path: str):
    """读图：with + copy，避免 Windows 下 PIL 持有文件句柄锁住缓存文件"""
    with Image.open(path) as im:
        return im.copy()


# ===================== 1. 图示化画幅选择器 =====================
class AspectPicker(ctk.CTkFrame):
    """画幅图示选择：每个选项画出真实比例的矩形

    选中态：底色 ACCENT_SOFT（#F0F7FF）+ 矩形填充主色；
    未选中：底色 FILL（#F3F3F3）+ 矩形填充灰。
    选项用 grid(uniform) 均分宽度，5 项与 6 项都能铺满容器。
    """

    ICON = 28          # 图标画布边长
    HEIGHT = 52        # 单元高度 = 图标 28 + 标签 16 + 内边距 8

    def __init__(self, parent, ratios, value=None, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.ratios = list(ratios)
        self.on_change = on_change or (lambda r: None)
        self._cells = {}
        self._canvases = {}
        self._labels = {}
        self.value = value if value in self.ratios else self.ratios[0]

        for i, ratio in enumerate(self.ratios):
            self.grid_columnconfigure(i, weight=1, uniform="ap")
            cell = ctk.CTkFrame(self, fg_color=ui_theme.t.FILL,
                                corner_radius=R_CTRL,
                                height=self.HEIGHT, cursor="hand2")
            cell.grid(row=0, column=i, sticky="ew",
                      padx=(0 if i == 0 else S_XS, 0))
            cell.grid_propagate(False)

            canvas = tk.Canvas(cell, width=self.ICON, height=self.ICON,
                               highlightthickness=0, bd=0,
                               bg=ui_theme.t.FILL)
            canvas.pack(pady=(S_XS, 0))
            label = ctk.CTkLabel(
                cell, text=ratio,
                font=ctk.CTkFont(family=ui_theme.FONT_FAMILY, size=11),
                text_color=ui_theme.t.TEXT_SUB)
            label.pack()

            self._cells[ratio] = cell
            self._canvases[ratio] = canvas
            self._labels[ratio] = label
            for w in (cell, canvas, label):
                w.bind("<Button-1>", lambda e, r=ratio: self._pick(r))

        self._paint()
        # 画幅图示是 Canvas 图元，不会自动跟随 CTk 主题，
        # 订阅主题变化后原地重绘（_paint 内部实时读取 token）。
        ui_theme.subscribe(self._paint)

    def _pick(self, ratio: str):
        if ratio == self.value or ratio not in self.ratios:
            return
        self.value = ratio
        self._paint()
        self.on_change(ratio)

    def _paint(self):
        """重绘全部单元。色值一律经 ui_theme.t 实时读取，
        因此同一个方法既能响应选中变化，也能响应主题切换。"""
        for ratio in self.ratios:
            cell = self._cells[ratio]
            canvas = self._canvases[ratio]
            selected = ratio == self.value
            bg = ui_theme.t.ACCENT_SOFT if selected else ui_theme.t.FILL
            rect = ui_theme.t.ACCENT if selected else ui_theme.t.TEXT_DISABLED
            cell.configure(fg_color=bg)
            canvas.configure(bg=bg)
            self._labels[ratio].configure(
                text_color=ui_theme.t.ACCENT_TEXT if selected
                else ui_theme.t.TEXT_SUB)

            canvas.delete("all")
            side = self.ICON - 4
            ar = ratio_to_float(ratio)
            if ar <= 1:
                rw, rh = side, max(6, side * ar)
            else:
                rh, rw = side, max(6, side / ar)
            x0 = (self.ICON - rw) / 2
            y0 = (self.ICON - rh) / 2
            canvas.create_rectangle(x0, y0, x0 + rw, y0 + rh,
                                    fill=rect, outline="")

    def get(self) -> str:
        return self.value

    def set(self, ratio: str):
        if ratio in self.ratios:
            self.value = ratio
            self._paint()


# ===================== 2. 瀑布流画廊 =====================
class GalleryGrid(ctk.CTkFrame):
    """历史记录画廊：2~5 列瀑布流，按原始宽高比排布

    交互：
      单击卡片    —— 选中（与列表一致，启用「载入参数 / 删除」）
      双击卡片    —— 打开 Lightbox
      卡片 ⤢ 按钮 —— 打开 Lightbox
    """

    FILTER_LABELS = {"全部": "all", "图片": "image", "视频": "video"}

    def __init__(self, parent, fonts: dict, on_select=None, on_open=None,
                 on_status=None, on_load_params=None):
        super().__init__(parent, fg_color="transparent")
        self.fonts = fonts
        self.on_select = on_select or (lambda rec: None)
        self.on_open = on_open or (lambda records, index: None)
        self.on_status = on_status or (lambda text: None)
        self.on_load_params = on_load_params

        self.records: list = []
        self.filter_type = "all"
        self.keyword = ""
        self.selected_id = None
        self.visible_cache: list = []
        self.columns: list = []
        self._cards: dict = {}
        self.grid_host = None        # 瀑布流宿主 frame（每次渲染重建）
        self._render_extras: list = []  # 直接挂在 scroll 上的空态提示等（每次渲染重建）
        self._ar_cache: dict = {}     # rid → 高/宽（避免重复解码）
        self._photo_cache: dict = {}  # "rid@列宽" → CTkImage
        self._search_job = None
        self._resize_job = None
        self._cols_now = 0

        self._build()
        self.refresh()

    # ---------------- 界面 ----------------
    def _build(self):
        f_small = self.fonts.get("small")

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill=tk.X, padx=CARD_PAD, pady=(CARD_PAD, S_SM))

        self.seg = ctk.CTkSegmentedButton(
            tools, values=list(self.FILTER_LABELS.keys()),
            command=self._on_filter_changed,
            height=H_CHIP, corner_radius=R_PILL, font=f_small,
            fg_color=FILL, selected_color=CARD_BG,
            selected_hover_color=ACCENT_SOFT,
            unselected_color=FILL, unselected_hover_color=FILL_HOVER,
            text_color=TEXT_MAIN,
        )
        self.seg.pack(side=tk.LEFT)

        self.search_var = ctk.StringVar()
        self.search = ctk.CTkEntry(
            tools, textvariable=self.search_var, placeholder_text="🔍 搜索提示词",
            height=H_CHIP, corner_radius=R_CTRL, font=f_small,
            fg_color=PAGE_BG, border_width=1, border_color=FIELD_BORDER,
            text_color=TEXT_MAIN, placeholder_text_color=TEXT_SUB,
        )
        self.search.pack(side=tk.LEFT, fill=tk.X, expand=True,
                         padx=(S_SM, S_SM))
        self.search.bind("<KeyRelease>", self._on_search_changed)

        self.btn_refresh = self._tool_btn(tools, "⟳", lambda: self.refresh())
        self.btn_refresh.pack(side=tk.LEFT)
        self.btn_folder = self._tool_btn(tools, "📂", self._open_folder)
        self.btn_folder.pack(side=tk.LEFT, padx=(S_XS, 0))

        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=SCROLLBAR,
            scrollbar_button_hover_color=SCROLLBAR_HOVER,
        )
        self.scroll.pack(fill=tk.BOTH, expand=True, padx=S_XS, pady=(0, S_XS))
        self.scroll.bind("<Configure>", self._on_resize)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill=tk.X, padx=CARD_PAD, pady=(0, CARD_PAD))
        self.count_label = ctk.CTkLabel(bar, text="", font=f_small,
                                        text_color=TEXT_SUB)
        self.count_label.pack(side=tk.LEFT)
        self.btn_load = self._mini_btn(bar, "载入参数", self._load_selected)
        self.btn_load.pack(side=tk.RIGHT)
        self.btn_delete = self._mini_btn(bar, "删除", self._delete_selected,
                                         destructive=True)
        self.btn_delete.pack(side=tk.RIGHT, padx=(0, S_SM))

        self.seg.set("全部")

    def _tool_btn(self, parent, text, command):
        return ctk.CTkButton(
            parent, text=text, command=command, width=30, height=H_CHIP,
            corner_radius=R_PILL, font=self.fonts.get("small"),
            fg_color=FILL, hover_color=FILL_HOVER, text_color=TEXT_MAIN,
        )

    def _mini_btn(self, parent, text, command, destructive: bool = False):
        if destructive:
            fg, hover, tx = "transparent", ERROR_BG, ERROR_TEXT
        else:
            fg, hover, tx = FILL, FILL_HOVER, TEXT_MAIN
        return ctk.CTkButton(
            parent, text=text, command=command, height=H_CHIP,
            corner_radius=R_PILL, font=self.fonts.get("small"),
            fg_color=fg, hover_color=hover, text_color=tx, border_width=0,
        )

    # ---------------- 数据 ----------------
    def refresh(self):
        self.records = history_store.load_history()
        self._photo_cache = {}
        self._render()

    def set_state(self, filter_type: str = None, keyword: str = None,
                  selected_id=None):
        """从列表视图切换过来时同步筛选与选中态"""
        if filter_type:
            self.filter_type = filter_type
            label = next((k for k, v in self.FILTER_LABELS.items()
                          if v == filter_type), "全部")
            self.seg.set(label)
        if keyword is not None:
            self.keyword = keyword
            self.search_var.set(keyword)
        if selected_id is not None:
            self.selected_id = selected_id
        self._render()

    def get_state(self) -> tuple:
        return self.filter_type, self.keyword, self.selected_id

    def _visible(self) -> list:
        kw = (self.keyword or "").strip().lower()
        out = []
        for r in self.records:
            if self.filter_type != "all" and r.get("type") != self.filter_type:
                continue
            if kw:
                hay = " ".join([
                    str(r.get("prompt") or ""),
                    " ".join(str(v) for v in (r.get("params") or {}).values()),
                    " ".join(str(v) for v in (r.get("meta") or {}).values()),
                ]).lower()
                if kw not in hay:
                    continue
            out.append(r)
        return out

    # ---------------- 瀑布流布局 ----------------
    def _on_resize(self, event=None):
        """宽度变化后重排（防抖 200ms，列数不变则跳过）"""
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(200, self._render_if_cols_changed)

    def _render_if_cols_changed(self):
        self._resize_job = None
        try:
            cols = self._calc_cols()
        except Exception:
            return
        if cols != self._cols_now:
            self._render()

    def _calc_cols(self) -> int:
        width = self.scroll.winfo_width() or 640
        avail = max(width - 24, 240)
        return max(2, min(5, int(avail // 200)))

    def _clear_render(self):
        """清掉上一次渲染直接挂在 scroll 上的内容，避免重复渲染时控件累积"""
        host = getattr(self, "grid_host", None)
        if host is not None:
            try:
                host.destroy()
            except Exception:
                pass
        self.grid_host = None
        self.columns = []   # 列是 grid_host 的子控件，随宿主一并销毁
        self._cards = {}
        for w in getattr(self, "_render_extras", []):
            try:
                w.destroy()
            except Exception:
                pass
        self._render_extras = []

    def _render(self):
        self.visible_cache = self._visible()
        shown = self.visible_cache[:GALLERY_RENDER_LIMIT]

        self._clear_render()

        if not shown:
            tip = ("暂无历史记录\n生成图片或视频后会自动记录在这里"
                   if not self.records else "没有匹配的记录")
            label = ctk.CTkLabel(
                self.scroll, text=tip, font=self.fonts.get("body"),
                text_color=TEXT_SUB, justify=tk.CENTER,
            )
            label.pack(pady=40)
            self._render_extras.append(label)
            self._update_bar(len(self.visible_cache), 0)
            return

        width = self.scroll.winfo_width() or 640
        avail = max(width - 24, 240)
        cols = max(2, min(5, int(avail // 200)))
        self._cols_now = cols
        col_w = int((avail - S_SM * (cols - 1)) / cols)

        self.grid_host = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.grid_host.pack(fill=tk.BOTH, expand=True)

        heights = [0] * cols
        self.columns = []
        for i in range(cols):
            col = ctk.CTkFrame(self.grid_host, fg_color="transparent",
                               width=col_w)
            col.pack(side=tk.LEFT, fill=tk.Y, anchor=tk.N,
                     padx=(0 if i == 0 else S_SM, 0))
            self.columns.append(col)

        for rec in shown:
            # 最短列优先：保证各列底部落差最小
            idx = heights.index(min(heights))
            card_h = self._build_card(self.columns[idx], rec, col_w)
            heights[idx] += card_h + S_SM

        self._update_bar(len(self.visible_cache), len(shown))

    def _build_card(self, parent, rec: dict, col_w: int) -> int:
        f_small = self.fonts.get("small")
        rid = rec.get("id")
        selected = rid == self.selected_id

        ar = self._aspect(rec)
        thumb_h = max(72, min(int(round(col_w * ar)),
                              int(col_w * CARD_MAX_RATIO)))

        card = ctk.CTkFrame(
            parent, corner_radius=R_CTRL,
            fg_color=ACCENT_SOFT if selected else CARD_BG,
            border_width=1,
            border_color=ACCENT if selected else CARD_BORDER,
        )
        card.pack(fill=tk.X, pady=(0, S_SM))

        photo = self._thumb_for(rec, col_w, thumb_h)
        is_video = rec.get("type") == "video"
        thumb = ctk.CTkLabel(
            card, text="" if photo else ("🎬" if is_video else "🖼"),
            image=photo, width=col_w, height=thumb_h, corner_radius=0,
            fg_color=PAGE_BG, font=self.fonts.get("body"),
        )
        thumb.pack(fill=tk.X)

        # 视频角标：叠在缩略图左下
        if is_video:
            badge = ctk.CTkLabel(card, text=" 🎬 ", font=f_small,
                                 corner_radius=R_THUMB, fg_color=OVERLAY_BG,
                                 text_color=OVERLAY_TEXT)
            badge.place(x=S_SM, y=thumb_h - 24)

        open_btn = ctk.CTkButton(
            card, text="⤢", width=H_CHIP, height=H_CHIP,
            corner_radius=R_PILL,
            font=f_small, fg_color=OVERLAY_BG, hover_color=OVERLAY_HOVER,
            text_color=OVERLAY_TEXT,
            command=lambda r=rec: self._open(r),
        )
        open_btn.place(relx=1.0, x=-S_SM, y=S_SM, anchor="ne")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill=tk.X, padx=S_SM, pady=(S_SM, S_SM))

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill=tk.X)
        badge_text, badge_bg, badge_fg = self._badge(rec)
        ctk.CTkLabel(head, text=badge_text, font=f_small,
                     corner_radius=R_CTRL, fg_color=badge_bg,
                     text_color=badge_fg).pack(side=tk.LEFT)
        ctk.CTkLabel(head, text=short_time(rec.get("created_at")),
                     font=f_small, text_color=TEXT_SUB).pack(side=tk.RIGHT)

        snippet = " ".join((rec.get("prompt") or "").split()) or "（无提示词）"
        if len(snippet) > 28:
            snippet = snippet[:28] + "…"
        ctk.CTkLabel(body, text=snippet, font=f_small, anchor="w",
                     justify=tk.LEFT,
                     text_color=ERROR_TEXT if rec.get("status") == "failed"
                     else TEXT_MAIN).pack(fill=tk.X, pady=(S_XS, 0))

        self._bind_select(card, rec)
        self._cards[rid] = card
        return thumb_h + CARD_FOOTER_H

    def _bind_select(self, widget, rec: dict):
        widget.bind("<Button-1>", lambda e, r=rec: self._select(r))
        widget.bind("<Double-Button-1>", lambda e, r=rec: self._open(r))
        for child in widget.winfo_children():
            self._bind_select(child, rec)

    def _badge(self, rec: dict):
        if rec.get("status") == "failed":
            return "失败", ERROR_BG, ERROR_TEXT
        if rec.get("type") == "video":
            return "视频", VIDEO_BG, VIDEO_TEXT
        return "图片", SUCCESS_BG, SUCCESS_TEXT

    def _aspect(self, rec: dict) -> float:
        """高/宽：优先读缓存图真实尺寸，其次解析参数，最后按类型兜底"""
        rid = rec.get("id")
        if rid in self._ar_cache:
            return self._ar_cache[rid]
        ar = None
        for key in ("thumb_path", "media_path"):
            path = rec.get(key)
            if path and os.path.exists(path):
                try:
                    with Image.open(path) as im:
                        w, h = im.size
                    if w and h:
                        ar = h / w
                        break
                except Exception:
                    continue
        if ar is None:
            p = rec.get("params") or {}
            if rec.get("type") == "video" and p.get("aspect_ratio"):
                ar = ratio_to_float(p["aspect_ratio"])
            elif p.get("size") and "x" in str(p["size"]):
                try:
                    w, h = (int(x) for x in str(p["size"]).split("x"))
                    ar = h / w if w else 1.0
                except Exception:
                    ar = None
        if ar is None:
            ar = 0.5625 if rec.get("type") == "video" else 1.0
        ar = max(0.35, min(ar, CARD_MAX_RATIO))
        self._ar_cache[rid] = ar
        return ar

    def _thumb_for(self, rec: dict, col_w: int, thumb_h: int):
        rid = rec.get("id")
        cache_key = f"{rid}@{col_w}"
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]
        for key in ("thumb_path", "media_path"):
            path = rec.get(key)
            if not path or not os.path.exists(path):
                continue
            try:
                img = _load_image(path)
                img = img.resize((col_w, thumb_h), Image.LANCZOS)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                photo = ctk.CTkImage(light_image=img, size=(col_w, thumb_h))
                self._photo_cache[cache_key] = photo
                return photo
            except Exception:
                continue
        return None

    # ---------------- 交互 ----------------
    def _select(self, rec: dict):
        prev_card = self._cards.get(self.selected_id)
        if prev_card is not None:
            ui_anim.blend_configure(
                prev_card, {"fg_color": CARD_BG, "border_color": CARD_BORDER},
                duration_ms=120)
        self.selected_id = rec.get("id")
        card = self._cards.get(self.selected_id)
        if card is not None:
            ui_anim.blend_configure(
                card, {"fg_color": ACCENT_SOFT, "border_color": ACCENT},
                duration_ms=120)
        self._update_bar()
        self.on_select(rec)

    def _open(self, rec: dict):
        """双击 / ⤢：把当前可见集合与序号交给 Lightbox，支持 ←→ 连续翻看"""
        records = self.visible_cache[:GALLERY_RENDER_LIMIT]
        try:
            index = next(i for i, r in enumerate(records)
                         if r.get("id") == rec.get("id"))
        except StopIteration:
            records, index = [rec], 0
        self._select(rec)
        self.on_open(records, index)

    def _selected_record(self):
        for r in self.records:
            if r.get("id") == self.selected_id:
                return r
        return None

    def _update_bar(self, matched: int = None, shown: int = None):
        if matched is None:
            matched = len(self.visible_cache)
        if shown is None:
            shown = min(matched, GALLERY_RENDER_LIMIT)
        sel = self._selected_record()
        state = "normal" if sel else "disabled"
        self.btn_load.configure(state=state)
        self.btn_delete.configure(state=state)
        n_img = sum(1 for r in self.records if r.get("type") == "image")
        n_vid = sum(1 for r in self.records if r.get("type") == "video")
        self.count_label.configure(
            text=f"共 {len(self.records)} 条（🖼 {n_img} · 🎬 {n_vid}）· 显示 {shown}"
        )

    def _on_filter_changed(self, value: str):
        self.filter_type = self.FILTER_LABELS.get(value, "all")
        if getattr(self, "scroll", None) is None:
            return
        self._render()

    def _on_search_changed(self, event=None):
        if self._search_job:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(260, self._do_search)

    def _do_search(self):
        self._search_job = None
        self.keyword = self.search_var.get() or ""
        self._render()

    def _open_folder(self):
        path = history_store.ensure_dirs()
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            self.on_status(f"📂 已打开历史目录: {path}")
        except Exception as e:
            self.on_status(f"⚠️ 无法打开历史目录: {e}")

    def _load_selected(self):
        rec = self._selected_record()
        if rec and self.on_load_params:
            self.on_load_params(rec)

    def _delete_selected(self):
        rec = self._selected_record()
        if not rec:
            return
        from tkinter import messagebox
        if not messagebox.askyesno(
                "删除记录", "确定删除这条历史记录吗？\n本地缓存文件也会一并删除。"):
            return
        history_store.delete_record(rec["id"])
        self.selected_id = None
        self.refresh()
        self.on_select(None)
        self.on_status("🗑 已删除该历史记录")

    def clear_selection(self):
        card = self._cards.get(self.selected_id)
        if card is not None:
            try:
                card.configure(fg_color=CARD_BG, border_color=CARD_BORDER)
            except Exception:
                pass
        self.selected_id = None
        self._update_bar()


# ===================== 3. Lightbox 大图查看器 =====================
class Lightbox(ctk.CTkToplevel):
    """全屏大图查看器

    交互（均有具体数值约束）：
      ESC / 点击关闭   关闭
      ← / →            上一张 / 下一张
      滚轮             以光标为锚点缩放，范围 10%~400%，每档 ×1.15
      拖拽             平移（限制在半个画面内，避免拖飞）
      双击 / 0         复位为适应窗口（100%）
      +/-              放大 / 缩小一档
    """

    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.10, 4.00, 1.15
    FILL_RATIO = 0.94          # 适应窗口时占可用面积的比例
    MAX_PIXELS = 40_000_000    # 单次重采样上限，防止超大缩放时内存爆掉

    def __init__(self, master, records, index: int = 0, fonts: dict = None,
                 loader=None, on_status=None, on_play=None):
        super().__init__(master)
        self.records = list(records or [])
        self.index = max(0, min(index, len(self.records) - 1))
        self.fonts = fonts or {}
        self.loader = loader
        self.on_status = on_status or (lambda text: None)
        self.on_play = on_play

        self._pil = None
        self._photo = None
        self._img_item = None
        self._zoom = 1.0
        self._offset = [0, 0]
        self._drag_from = None
        self._loading = False

        self.title("大图查看")
        self.configure(fg_color=LB_BG)
        self._size_to_screen()

        self.canvas = tk.Canvas(self, bg=LB_BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self.canvas.bind("<MouseWheel>", self._on_wheel)      # Windows
        self.canvas.bind("<Button-4>", self._on_wheel)        # Linux 上滚
        self.canvas.bind("<Button-5>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", lambda e: self._fit())

        self._build_footer()
        self._bind_keys()

        self.transient(master)
        self._closing = False
        # 弹层淡入：先完成首帧布局并置透明，再 alpha 0→1（约 180ms），避免首帧闪现
        if not ui_anim.reduce_motion():
            try:
                self.update_idletasks()
                self.attributes("-alpha", 0.02)
                ui_anim.fade_window_in(self)
            except Exception:
                pass
        self.after(60, self._focus_and_show)

    def _close(self):
        """加速淡出后销毁（关闭按钮 / ESC 统一入口，防重入）"""
        if getattr(self, "_closing", False):
            return
        self._closing = True
        ui_anim.fade_window_out(self, on_finished=self.destroy)

    def _size_to_screen(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = int(sw * 0.92), int(sh * 0.90)
        self.geometry(f"{w}x{h}+{int((sw - w) / 2)}+{int((sh - h) * 0.42)}")
        self.minsize(720, 480)

    def _focus_and_show(self):
        try:
            self.lift()
            self.focus_force()
            self.canvas.focus_set()
        except Exception:
            pass
        self._show(self.index)

    def _build_footer(self):
        f_small = self.fonts.get("small") or ctk.CTkFont(size=11)
        bar = ctk.CTkFrame(self, fg_color=LB_BAR, corner_radius=0, height=48)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self.btn_prev = ctk.CTkButton(
            bar, text="‹ 上一张", width=88, height=H_CHIP, corner_radius=R_PILL,
            font=f_small, fg_color=LB_BTN, hover_color=LB_BTN_HOVER,
            text_color=LB_TEXT, command=lambda: self._step(-1))
        self.btn_prev.pack(side=tk.LEFT, padx=(CARD_PAD, S_XS))

        self.btn_next = ctk.CTkButton(
            bar, text="下一张 ›", width=88, height=H_CHIP, corner_radius=R_PILL,
            font=f_small, fg_color=LB_BTN, hover_color=LB_BTN_HOVER,
            text_color=LB_TEXT, command=lambda: self._step(1))
        self.btn_next.pack(side=tk.LEFT, padx=(0, CARD_PAD))

        self.info_label = ctk.CTkLabel(bar, text="", font=f_small,
                                       text_color=LB_TEXT_DIM, anchor="w")
        self.info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctk.CTkButton(bar, text="－", width=32, height=H_CHIP,
                      corner_radius=R_PILL, font=f_small, fg_color=LB_BTN,
                      hover_color=LB_BTN_HOVER, text_color=LB_TEXT,
                      command=lambda: self._zoom_by(1 / self.ZOOM_STEP)
                      ).pack(side=tk.RIGHT)
        self.zoom_label = ctk.CTkLabel(bar, text="100%", width=56,
                                       font=f_small, text_color=LB_TEXT)
        self.zoom_label.pack(side=tk.RIGHT)
        ctk.CTkButton(bar, text="＋", width=32, height=H_CHIP,
                      corner_radius=R_PILL, font=f_small, fg_color=LB_BTN,
                      hover_color=LB_BTN_HOVER, text_color=LB_TEXT,
                      command=lambda: self._zoom_by(self.ZOOM_STEP)
                      ).pack(side=tk.RIGHT)
        ctk.CTkButton(bar, text="适应", width=56, height=H_CHIP,
                      corner_radius=R_PILL, font=f_small, fg_color=LB_BTN,
                      hover_color=LB_BTN_HOVER, text_color=LB_TEXT,
                      command=self._fit).pack(side=tk.RIGHT, padx=S_XS)
        if self.on_play:
            ctk.CTkButton(bar, text="▶ 播放", width=72, height=H_CHIP,
                          corner_radius=R_PILL, font=f_small,
                          fg_color=LB_BTN, hover_color=LB_BTN_HOVER,
                          text_color=LB_TEXT, command=self._play
                          ).pack(side=tk.RIGHT, padx=S_XS)
        ctk.CTkButton(bar, text="关闭 ESC", width=88, height=H_CHIP,
                      corner_radius=R_PILL, font=f_small, fg_color=LB_BTN,
                      hover_color=LB_BTN_HOVER, text_color=LB_TEXT,
                      command=self._close).pack(side=tk.RIGHT, padx=(0, CARD_PAD))

    def _bind_keys(self):
        for widget in (self, self.canvas):
            widget.bind("<Escape>", lambda e: self._close())
            widget.bind("<Left>", lambda e: self._step(-1))
            widget.bind("<Right>", lambda e: self._step(1))
            widget.bind("<Key-0>", lambda e: self._fit())
            widget.bind("<Key-plus>", lambda e: self._zoom_by(self.ZOOM_STEP))
            widget.bind("<Key-equal>", lambda e: self._zoom_by(self.ZOOM_STEP))
            widget.bind("<Key-minus>", lambda e: self._zoom_by(1 / self.ZOOM_STEP))

    # ---------------- 载入与渲染 ----------------
    def _step(self, delta: int):
        if not self.records or self._loading:
            return
        self._show((self.index + delta) % len(self.records))

    def _show(self, index: int):
        self.index = index
        rec = self.records[index]
        prompt = " ".join((rec.get("prompt") or "（无提示词）").split())
        if len(prompt) > 46:
            prompt = prompt[:46] + "…"
        self.info_label.configure(
            text=f"{index + 1}/{len(self.records)}  ·  {prompt}")
        self.btn_prev.configure(state="normal" if len(self.records) > 1
                                else "disabled")
        self.btn_next.configure(state="normal" if len(self.records) > 1
                                else "disabled")

        self._pil = None
        self._photo = None
        self._img_item = None
        self._zoom = 1.0
        self._offset = [0, 0]
        self.canvas.delete("all")

        is_video = rec.get("type") == "video"
        if is_video:
            # 视频不进 PIL 解码管线：优先展示本地缓存封面，否则提示播放
            cover = None
            thumb_path = rec.get("thumb_path")
            if thumb_path and os.path.exists(thumb_path):
                try:
                    cover = _load_image(thumb_path)
                except Exception:
                    cover = None
            if cover is not None:
                self._pil = cover
                self._fit()
            else:
                self._hint("🎬 视频记录\n无封面缓存，点「▶ 播放」观看")
            return

        self._loading = True
        self._hint("载入中…")
        if self.loader:
            self.loader(rec, self._on_bytes)
        else:
            self._on_bytes(None)

    def _on_bytes(self, data):
        self._loading = False
        if not data:
            self._hint("无法载入图片\n本地缓存缺失且下载失败")
            return
        try:
            self._pil = Image.open(BytesIO(data))
            self._pil.load()
        except Exception as e:
            self._hint(f"图片解析失败\n{type(e).__name__}: {e}")
            return
        self._fit()

    def _hint(self, text: str):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 640
        h = self.canvas.winfo_height() or 420
        self.canvas.create_text(w // 2, h // 2, text=text, fill=LB_HINT,
                                font=(ui_theme.FONT_FAMILY, 13),
                                justify=tk.CENTER)

    def _fit(self):
        self._zoom = 1.0
        self._offset = [0, 0]
        self._paint()

    def _display_size(self):
        """适应窗口 → 再乘缩放系数，并限制单次重采样像素总量"""
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        iw, ih = self._pil.size
        fit = min(cw * self.FILL_RATIO / iw, ch * self.FILL_RATIO / ih)
        w = max(16, int(iw * fit * self._zoom))
        h = max(16, int(ih * fit * self._zoom))
        if w * h > self.MAX_PIXELS:
            k = math.sqrt(self.MAX_PIXELS / (w * h))
            w, h = max(16, int(w * k)), max(16, int(h * k))
        return w, h

    def _paint(self):
        if self._pil is None:
            return
        w, h = self._display_size()
        img = self._pil.resize((w, h), Image.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        self._photo = ImageTk.PhotoImage(img)

        cw = self.canvas.winfo_width() or w
        ch = self.canvas.winfo_height() or h
        self._clamp_offset(w, h, cw, ch)
        cx, cy = cw // 2 + self._offset[0], ch // 2 + self._offset[1]

        self.canvas.delete("all")
        self._img_item = self.canvas.create_image(cx, cy, image=self._photo,
                                                  anchor=tk.CENTER)
        self.zoom_label.configure(text=f"{round(self._zoom * 100)}%")

    def _clamp_offset(self, w, h, cw, ch):
        """平移范围限制在半个画面内，避免把图拖出视野"""
        max_x = max(0, (w - cw) / 2) + cw / 2
        max_y = max(0, (h - ch) / 2) + ch / 2
        self._offset[0] = max(-max_x, min(max_x, self._offset[0]))
        self._offset[1] = max(-max_y, min(max_y, self._offset[1]))

    # ---------------- 缩放与平移 ----------------
    def _zoom_by(self, factor: float):
        self._zoom_at(None, None, factor)

    def _on_wheel(self, event):
        if self._pil is None:
            return
        if getattr(event, "num", None) == 4:
            delta, x, y = 120, event.x, event.y
        elif getattr(event, "num", None) == 5:
            delta, x, y = -120, event.x, event.y
        else:
            delta, x, y = event.delta, event.x, event.y
        self._zoom_at(x, y, self.ZOOM_STEP if delta > 0 else 1 / self.ZOOM_STEP)

    def _zoom_at(self, x, y, factor: float):
        """以光标为锚点缩放：光标下的图像像素保持不动"""
        if self._pil is None:
            return
        old_w, old_h = self._display_size()
        cw = self.canvas.winfo_width() or old_w
        ch = self.canvas.winfo_height() or old_h
        ax, ay = (x if x is not None else cw / 2, y if y is not None else ch / 2)

        # 光标相对图像左上角的比例（0~1）
        fx = (ax - (cw / 2 + self._offset[0])) / old_w + 0.5
        fy = (ay - (ch / 2 + self._offset[1])) / old_h + 0.5

        new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        self._zoom = new_zoom

        new_w, new_h = self._display_size()
        self._offset[0] = ax - cw / 2 - (fx - 0.5) * new_w
        self._offset[1] = ay - ch / 2 - (fy - 0.5) * new_h
        self._paint()

    def _on_press(self, event):
        self._drag_from = (event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _on_drag(self, event):
        if not self._drag_from or self._pil is None:
            return
        dx = event.x - self._drag_from[0]
        dy = event.y - self._drag_from[1]
        self._drag_from = (event.x, event.y)
        self._offset[0] += dx
        self._offset[1] += dy
        # 平移不改尺寸：只移动画布上的图像项，避免每次移动都重采样
        if self._img_item is not None:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            w, h = self._display_size()
            self._clamp_offset(w, h, cw, ch)
            self.canvas.coords(self._img_item,
                               cw // 2 + self._offset[0],
                               ch // 2 + self._offset[1])

    def _on_release(self, event):
        self._drag_from = None
        self.canvas.configure(cursor="")

    def _play(self):
        rec = self.records[self.index] if self.records else None
        if rec and self.on_play:
            self.on_play(rec)
