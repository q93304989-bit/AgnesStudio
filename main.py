"""
Agnes 生成小工具 - 主程序（Apple / macOS 风格 UI）
基于 customtkinter 实现：浅 / 深双主题、白色圆角卡片、系统蓝强调色、胶囊按钮。
设计 token 统一由 ui_theme.py 提供（8px 网格 / 四档圆角 / WCAG AA）。

集成功能：
  1. 🎨 图片生成（文生图 / 图生图，支持多参考图）
  2. 🎬 视频生成（文生视频 / 图片参考视频，异步轮询）
"""
import os
import sys
import json
import time
import shutil
import threading
import webbrowser
import math
import tkinter as tk
from tkinter import font as tkfont, filedialog, messagebox, simpledialog
from io import BytesIO

import requests
import customtkinter as ctk
from PIL import Image
from PIL.ImageTk import PhotoImage as TkPhotoImage


def _patch_dropdown_arrow_to_chevron():
    """将 CustomTkinter 下拉箭头（默认 ▼/Y 字形）替换为极简向下 “⌄” chevron。

    CTkOptionMenu/CTkComboBox 的箭头由 DrawEngine.draw_dropdown_arrow 绘制，
    控件本身无箭头样式参数；故在启动时对 DrawEngine 打补丁 —— 所有下拉统一
    变为三点折线 “⌄”（向下开口），颜色仍由控件 text_color 自动控制并随主题刷新。
    """
    try:
        from customtkinter.windows.widgets.core_rendering.draw_engine import DrawEngine
    except Exception:
        return  # 版本变更导致找不到引擎时保持默认外观，不阻塞启动

    def draw_dropdown_arrow(self, x_position, y_position, size):
        """三点折线 chevron（向下开口的 ⌄）——极简风"""
        x_position, y_position, size = round(x_position), round(y_position), round(size)
        requires_recoloring = False
        existing = self._canvas.find_withtag("dropdown_arrow")
        if not existing:
            self._canvas.create_line(
                0, 0, 0, 0, tags="dropdown_arrow",
                width=max(round(size / 3), 1),
                joinstyle=tk.ROUND, capstyle=tk.ROUND)
            self._canvas.tag_raise("dropdown_arrow")
            requires_recoloring = True
        elif self._canvas.type(existing[0]) != "line":
            # 兼容 font_shapes 等其它绘制路径残留的旧字形项
            self._canvas.delete("dropdown_arrow")
            self._canvas.create_line(
                0, 0, 0, 0, tags="dropdown_arrow",
                width=max(round(size / 3), 1),
                joinstyle=tk.ROUND, capstyle=tk.ROUND)
            self._canvas.tag_raise("dropdown_arrow")
            requires_recoloring = True
        # 向下 “⌄”：(左上) → (下中) → (右上)，顶点在下方中央
        self._canvas.coords(
            "dropdown_arrow",
            x_position - (size / 2), y_position - (size / 3),
            x_position, y_position + (size / 3),
            x_position + (size / 2), y_position - (size / 3))
        return requires_recoloring

    DrawEngine.draw_dropdown_arrow = draw_dropdown_arrow


_patch_dropdown_arrow_to_chevron()

from agens_core import AgnesImageGenerator, resource_path, runtime_dir
from http_session import adaptive_request, set_network_mode
from image_host import upload_to_image_host
import app_config
import history_store
from history_ui import HistoryPanel
from gallery_ui import AspectPicker, GalleryGrid, Lightbox, aspect_of_size
from video_core import (
    AgnesVideoGenerator,
    VIDEO_MODELS,
    ASPECT_RATIOS,
    SECONDS_OPTIONS,
    VideoQueueFullError,
    VideoRateLimitError,
    RETRYABLE_VIDEO_ERRORS,
)

# ===================== Design Token：统一从 ui_theme 引用（单一事实来源） =====================
# 8px 网格 / 四档圆角 / WCAG AA 校验 / 浅深双主题，完整定义见 ui_theme.py
import ui_theme
import ui_anim  # 动效基础设施：缓动 / 颜色插值 / 减弱动态效果检测
from ui_theme import (
    # 色彩
    PAGE_BG, CARD_BG, CARD_BORDER, FIELD_BG, FIELD_BORDER,
    TEXT_MAIN, TEXT_SUB, TEXT_DISABLED,
    ACCENT, ACCENT_HOVER, ACCENT_TEXT, ACCENT_SOFT, ACCENT_SOFT_HOVER,
    FILL, FILL_HOVER, ON_ACCENT, WARNING_TEXT,
    DESTRUCTIVE, ERROR_TEXT, ERROR_BG, SUCCESS_TEXT, SUCCESS_BG,
    SELECTED_BG, BTN_GRAY, BTN_GRAY_HOVER,
    GREEN_PILL_TX, RED_PILL_TX,
    SCROLLBAR, SCROLLBAR_HOVER, TOOLTIP_BG, TOOLTIP_TEXT,
    # 间距（8px 网格）
    S_XS, S_SM, S_MD, PAGE_PAD, CARD_PAD, BLOCK_GAP, LABEL_GAP,
    # 控件高度
    H_CTA, H_NAV, H_INPUT, H_DROP, H_CHIP,
    # 圆角
    R_CARD, R_CTRL, R_THUMB, R_PILL,
    W_NAV, W_INPUT,
)

# 导航页标识（左侧导航栏 → 功能内容页）
PAGE_IMAGE = "image"
PAGE_VIDEO = "video"
PAGE_HISTORY = "history"
PAGE_SETTINGS = "settings"

# 支持的图片尺寸
SIZE_OPTIONS = [
    "1024x768",
    "512x512",
    "768x1024",
    "1024x1024",
    "1280x720",
    "720x1280",
    "1920x1080",
]

MODEL_OPTIONS = [
    "agnes-image-2.1-flash",
]

# 图片画幅（图示化选择）→ 该画幅下可选的像素尺寸
IMAGE_ASPECTS = ["1:1", "4:3", "3:4", "16:9", "9:16"]
SIZE_BY_ASPECT = {
    "1:1": ["512x512", "1024x1024"],
    "4:3": ["1024x768"],
    "3:4": ["768x1024"],
    "16:9": ["1280x720", "1920x1080"],
    "9:16": ["720x1280"],
}

VIDEO_MODEL_OPTIONS = list(VIDEO_MODELS)
VIDEO_ASPECT_OPTIONS = list(ASPECT_RATIOS)
VIDEO_SECONDS_OPTIONS = list(SECONDS_OPTIONS)

# 设置页：网络模式 / 主题 的中文标签与内部编码
NETWORK_MODE_LABELS = {
    "auto": "自动（直连优先，失败换代理）",
    "direct": "仅直连（不走代理）",
    "proxy": "仅系统代理",
}
NETWORK_MODE_CODES = {v: k for k, v in NETWORK_MODE_LABELS.items()}

THEME_LABELS = {
    "system": "跟随系统",
    "light": "浅色",
    "dark": "深色",
}
THEME_CODES = {v: k for k, v in THEME_LABELS.items()}


def pick_font_family() -> str:
    """优先使用苹方系字体，Windows 下回退到 Segoe UI（中文自动字体链接到雅黑）。"""
    candidates = ["SF Pro Display", "SF Pro Text", "PingFang SC",
                  "Segoe UI Variable Display", "Segoe UI", "Microsoft YaHei UI"]
    available = set(tkfont.families())
    for name in candidates:
        if name in available:
            return name
    return "Microsoft YaHei UI"


class ReferenceImageList(ctk.CTkFrame):
    """参考图列表组件：支持添加 URL / 本地文件、缩略图预览、删除、清空"""

    def __init__(self, parent, max_items: int = 5, title: str = "参考图",
                 on_change=None, fonts=None, allow_local: bool = True,
                 auto_upload=None, status_cb=None):
        super().__init__(parent, fg_color=FILL, corner_radius=R_CTRL, border_width=0)
        self.max_items = max_items
        self.title = title
        self.on_change = on_change
        self.fonts = fonts or {}
        self.allow_local = allow_local   # False 时本地文件不直接入列
        self.auto_upload = auto_upload   # 提供时：选本地文件 → 自动传图床 → 以 URL 入列
        self.status_cb = status_cb       # 上传进度回调（在 UI 线程执行）
        self.items: list = []      # 每项为 str：本地路径或 URL
        self.thumb_rows = []       # 每项对应的控件 (label_name, del_btn)
        self._expanded = False     # 抽屉展开态（默认收起，空列表不占垂直空间）

        f_small = self.fonts.get("small")

        # 头部条：40px 一行，收起态只显示「参考图 n/5 + 添加」
        self.bar = ctk.CTkFrame(self, fg_color="transparent", height=40)
        self.bar.pack(fill=tk.X, padx=CARD_PAD)
        self.bar.pack_propagate(False)

        self.title_label = ctk.CTkLabel(
            self.bar, text=f"📎 {title} 0/{max_items}", font=f_small,
            text_color=TEXT_MAIN,
        )
        self.title_label.pack(side=tk.LEFT)

        self.toggle_btn = ctk.CTkButton(
            self.bar, text="▸ 添加", command=self._toggle, width=72,
            height=H_CHIP, corner_radius=R_PILL, font=f_small,
            fg_color="transparent", hover_color=FILL_HOVER,
            text_color=ACCENT_TEXT, border_width=0,
        )
        self.toggle_btn.pack(side=tk.RIGHT)

        # 抽屉：展开后显示添加入口、缩略图列表、清空（破坏性操作收进抽屉内）
        self.drawer = ctk.CTkFrame(self, fg_color="transparent")

        add_row = ctk.CTkFrame(self.drawer, fg_color="transparent")
        add_row.pack(fill=tk.X, padx=CARD_PAD, pady=(S_XS, S_SM))
        self.add_url_btn = self._mini_btn(add_row, "+ URL", self._add_url)
        self.add_url_btn.pack(side=tk.LEFT, padx=(0, S_SM))
        if allow_local or auto_upload:
            self.add_file_btn = self._mini_btn(add_row, "+ 文件", self._add_file)
            self.add_file_btn.pack(side=tk.LEFT)

        self.list_frame = ctk.CTkFrame(self.drawer, fg_color="transparent")
        self.list_frame.pack(fill=tk.X, padx=CARD_PAD)

        self.clear_btn = ctk.CTkButton(
            self.drawer, text="清空全部", command=self.clear, width=72,
            height=H_CHIP, corner_radius=R_PILL, font=f_small,
            fg_color="transparent", hover_color=ERROR_BG,
            text_color=ERROR_TEXT, border_width=0,
        )
        self.clear_btn.pack(side=tk.RIGHT, padx=CARD_PAD, pady=(S_XS, S_MD))

        self._rebuild_list()

    def _toggle(self):
        """展开 / 收起参考图抽屉"""
        self._expanded = not self._expanded
        if self._expanded:
            self.drawer.pack(fill=tk.X, pady=(0, S_XS))
            self.toggle_btn.configure(text="▾ 收起")
        else:
            self.drawer.pack_forget()
            self.toggle_btn.configure(text="▸ 添加")

    def _expand(self):
        if not self._expanded:
            self._toggle()

    def _mini_btn(self, parent, text, command):
        return ctk.CTkButton(
            parent, text=text, command=command, width=64, height=H_CHIP,
            corner_radius=R_PILL, font=self.fonts.get("small"),
            fg_color=CARD_BG, hover_color=FILL_HOVER,
            text_color=TEXT_MAIN, border_width=1, border_color=FIELD_BORDER,
        )

    def _rebuild_list(self):
        """重建列表显示（抽屉内）"""
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.thumb_rows = []

        n = len(self.items)
        self.title_label.configure(text=f"📎 {self.title} {n}/{self.max_items}")
        self.clear_btn.configure(state="normal" if n else "disabled")

        if not n:
            ctk.CTkLabel(
                self.list_frame,
                text=f"未添加 = 文生图；添加后 = 图生图（最多 {self.max_items} 张）",
                font=self.fonts.get("small"), text_color=TEXT_SUB,
                anchor="w", wraplength=W_INPUT - 64, justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(0, S_XS))
            return

        for i, item in enumerate(self.items):
            row = ctk.CTkFrame(self.list_frame, fg_color=CARD_BG,
                               corner_radius=R_THUMB)
            row.pack(fill=tk.X, pady=(0, S_XS), ipady=S_XS)

            # 缩略图（本地路径显示图片缩略图，URL 显示图标文字）
            thumb = ctk.CTkLabel(row, text="🌐", width=40, height=36,
                                 corner_radius=R_THUMB, fg_color=FIELD_BG,
                                 font=self.fonts.get("small"))
            thumb.pack(side=tk.LEFT, padx=(S_SM, S_SM))
            if os.path.exists(item):
                thumb.configure(text="🖼️")
                try:
                    img = Image.open(item)
                    img.thumbnail((72, 72))
                    photo = ctk.CTkImage(light_image=img, size=(36, 36))
                    thumb.configure(image=photo, text="")
                    thumb._ctk_photo = photo  # 保存引用防止被垃圾回收
                except Exception:
                    thumb.configure(text="🖼️", image=None)

            name = item if len(item) <= 42 else item[:40] + "..."
            ctk.CTkLabel(row, text=name, anchor=tk.W,
                         font=self.fonts.get("small"),
                         text_color=TEXT_MAIN).pack(side=tk.LEFT, fill=tk.X, expand=True)

            del_btn = ctk.CTkButton(
                row, text="✕", width=H_CHIP, height=H_CHIP, corner_radius=R_PILL,
                font=self.fonts.get("small"), fg_color="transparent",
                hover_color=ERROR_BG, text_color=ERROR_TEXT,
                command=lambda idx=i: self._remove(idx),
            )
            del_btn.pack(side=tk.RIGHT, padx=S_SM)
            self.thumb_rows.append((thumb, del_btn))

    def _remove(self, index: int):
        if 0 <= index < len(self.items):
            self.items.pop(index)
            self._rebuild_list()
            if self.on_change:
                self.on_change()

    def _add_url(self):
        if len(self.items) >= self.max_items:
            messagebox.showwarning("提示", f"最多添加 {self.max_items} 张参考图")
            return
        url = simpledialog.askstring("添加图片URL", "请输入参考图片的公网URL：\n（例如 https://example.com/pic.png）")
        if url:
            url = url.strip()
            if url:
                self.items.append(url)
                self._expand()
                self._rebuild_list()
                if self.on_change:
                    self.on_change()

    def _post_status(self, text: str):
        """把状态文本回调到应用状态栏（确保在 UI 线程执行）"""
        cb = self.status_cb
        if not cb:
            return
        try:
            self.winfo_toplevel().after(0, lambda: cb(text))
        except Exception:
            pass

    def _add_file(self):
        if len(self.items) >= self.max_items:
            messagebox.showwarning("提示", f"最多添加 {self.max_items} 张参考图")
            return
        path = filedialog.askopenfilename(
            title="选择参考图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        if self.auto_upload:
            # 视频模式：本地文件先自动传图床，成功后以公网 URL 入列
            self._post_status("⏳ 正在上传参考图到图床（SM.MS），请稍候...")
            threading.Thread(target=self._upload_worker, args=(path,), daemon=True).start()
        else:
            self.items.append(path)
            self._expand()
            self._rebuild_list()
            if self.on_change:
                self.on_change()

    def _upload_worker(self, path: str):
        """后台线程：上传本地参考图到图床，成功后回 UI 线程入列"""
        try:
            url = self.auto_upload(path)
        except Exception as e:
            # 必须在 except 块内立刻拼好消息（except as e 结束会删除 e）
            msg = f"[{type(e).__name__}] {e}"
            self._post_status(f"❌ 参考图上传失败：{msg}")
            return

        def _done():
            if len(self.items) >= self.max_items:
                self._post_status("⚠️ 参考图数量已满，本次上传结果未添加")
                return
            self.items.append(url)
            self._expand()
            self._rebuild_list()
            if self.on_change:
                self.on_change()
            self._post_status("✅ 本地参考图已自动上传图床并添加为 URL")

        try:
            self.winfo_toplevel().after(0, _done)
        except Exception:
            pass

    def clear(self):
        if self.items:
            self.items = []
            self._rebuild_list()
            if self.on_change:
                self.on_change()

    def get_items(self) -> list:
        """返回当前参考图列表（本地路径或 URL）"""
        return list(self.items)

    def set_items(self, items):
        """整体替换参考图列表（用于从历史记录载入参数）"""
        self.items = [str(i) for i in (items or [])][:self.max_items]
        if self.items:
            self._expand()
        self._rebuild_list()
        if self.on_change:
            self.on_change()


def _panel_shape_points(w: int, h: int, radii, steps: int = 10):
    """生成「可逐角指定圆角」的矩形路径点集（tk.Canvas 坐标，y 轴向下）。

    :param radii: (左上, 右上, 右下, 左下) 四个角的圆角半径，0 表示该角为平角
    """
    tl, tr, br, bl = radii
    pts = [(tl, 0.0), (w - tr, 0.0)]

    # 右上角：270° → 360°
    if tr:
        for i in range(1, steps + 1):
            a = math.radians(270 + 90 * i / steps)
            pts.append((w - tr + tr * math.cos(a), tr + tr * math.sin(a)))
    pts.append((w, h - br))

    # 右下角：0° → 90°
    if br:
        for i in range(1, steps + 1):
            a = math.radians(90 * i / steps)
            pts.append((w - br + br * math.cos(a), h - br + br * math.sin(a)))
    pts.append((bl, h))

    # 左下角：90° → 180°
    if bl:
        for i in range(1, steps + 1):
            a = math.radians(90 + 90 * i / steps)
            pts.append((bl + bl * math.cos(a), h - bl + bl * math.sin(a)))
    pts.append((0, tl))

    # 左上角：180° → 270°
    if tl:
        for i in range(1, steps + 1):
            a = math.radians(180 + 90 * i / steps)
            pts.append((tl + tl * math.cos(a), tl + tl * math.sin(a)))
    return pts


class PanelCard(ctk.CTkFrame):
    """三栏外框卡片：支持「指定某一侧为平角」

    CTkFrame 的 corner_radius 只能四角统一设置，无法只把靠近中间栏的那一侧
    改成平角，因此这里自行用 Canvas 绘制背景与边框：

      flat_side=None   四角全圆角（中栏）
      flat_side="right" 右侧两角平角（左栏，紧贴中栏的一侧）
      flat_side="left"  左侧两角平角（右栏，紧贴中栏的一侧）

    子控件一律挂到 `.content` 上（透明底板，露出下方 Canvas 绘制的形状）。
    """

    def __init__(self, master, flat_side=None, corner_radius=R_CARD,
                 fg_color=None, border_color=None, border_width=1,
                 **kwargs):
        super().__init__(master, fg_color="transparent", corner_radius=0,
                         **kwargs)
        self._radius = corner_radius
        self._flat_side = flat_side
        # 颜色默认值必须在这里「调用时」解析，不能写成默认参数：
        # 默认参数在 import（类定义）时求值，会把当时的浅色值烤进 __defaults__，
        # 之后 apply_palette 改的是模块全局变量，碰不到 __defaults__，
        # 于是主题切换后重建出来的窗口，三栏外框仍是旧色 ——
        # 而子控件多用 fg_color="transparent" 继承它，造成「只有部分组件变色」。
        # 记录「是否走 token 默认」，供 on_theme_changed 重新解析。
        self._use_token_fg = fg_color is None
        self._use_token_border = border_color is None
        self._fg_color = ui_theme.t.CARD_BG if self._use_token_fg else fg_color
        self._border_color = (ui_theme.t.CARD_BORDER if self._use_token_border
                              else border_color)
        self._border_width = border_width

        r = corner_radius
        if flat_side == "right":        # 左栏：右上、右下平角
            self._radii = (r, 0, 0, r)
        elif flat_side == "left":       # 右栏：左上、左下平角
            self._radii = (0, r, r, 0)
        else:                           # 中栏：四角全圆角
            self._radii = (r, r, r, r)

        self._shape_canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                       bg=ui_theme.t.PAGE_BG)
        self._shape_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._shape_canvas.bind("<Configure>", self._redraw)

        self.content = ctk.CTkFrame(self, fg_color="transparent",
                                    corner_radius=0)
        self.content.place(x=0, y=0, relwidth=1, relheight=1)

        # 本组件用 Canvas 画圆角面板，图元不会自动跟随 CTk 主题，
        # 因此订阅主题变化，原地重绘（无需重建窗口）。
        ui_theme.subscribe(self.on_theme_changed)

    def on_theme_changed(self):
        """主题切换后重新解析 token 色并重绘面板形状。

        必须走 configure() 而不是直接改 _fg_color：CTkFrame.configure 在
        fg_color 变化时会同步把新色下发到透明子树（bg_color 联动，见
        customtkinter ctk_frame.py 的 fg_color 分支），否则 content 及挂在
        其上的透明子控件会残留旧主题派生的 _bg_color（浅色块）。
        """
        card = ui_theme.t.CARD_BG
        page = ui_theme.t.PAGE_BG
        try:
            if self._use_token_fg:
                self.configure(fg_color=card)        # 联动 content.bg_color ← card
            if self._use_token_border:
                self.configure(border_color=ui_theme.t.CARD_BORDER)
            self.configure(bg_color=page)            # 基座 canvas 四角外露 = 页面色
            # content 钉住底色，同时联动其直接子树
            self.content.configure(fg_color=card, bg_color=card)
            self._shape_canvas.configure(bg=page)
        except Exception:
            pass
        self._redraw()

    def _redraw(self, event=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        r = self._radius
        # 缩小半径，避免窄栏时圆角互相重叠
        radii = tuple(min(x, w // 2, h // 2) for x in self._radii)
        self._shape_canvas.delete("panel")
        self._shape_canvas.create_polygon(
            _panel_shape_points(w, h, radii),
            fill=self._fg_color, outline=self._border_color,
            width=self._border_width, tags="panel",
        )
        # 边框只画在内侧：把背景层抬到内容之上会挡住控件，故保持 z 序不变，
        # 用 0.5px 内缩避免描边被控件边缘裁掉
        self._shape_canvas.tag_lower("panel")


class ToolTip:
    """轻量文字提示（解决示例/图标按钮文案被截断后无法识别的问题）

    悬停 500ms 后在其下方浮出，离开即销毁。
    """

    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip = None
        self._after = None
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)

    def _on_enter(self, _event=None):
        self._schedule()

    def _on_leave(self, _event=None):
        self._cancel()
        self._hide()

    def _schedule(self):
        self._cancel()
        try:
            self._after = self.widget.after(self.delay, self._show)
        except Exception:
            pass

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                self.tip, text=self.text, justify=tk.LEFT,
                background=TOOLTIP_BG, foreground=TOOLTIP_TEXT,
                relief=tk.SOLID, borderwidth=0,
                font=(ui_theme.FONT_FAMILY, 10), padx=S_SM, pady=S_XS,
            ).pack()
        except Exception:
            self.tip = None

    def _hide(self):
        if self.tip:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class ImageGeneratorApp:
    """Agnes 生成桌面应用（图片 + 视频）— Apple 风格界面"""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("Agnes 生成器")
        self.root.geometry("1280x840")
        self.root.minsize(1120, 720)
        self.root.configure(fg_color=PAGE_BG)

        # 字体阶梯：title 18/600 · h2 14/600 · body 13/400 · caption 11/400 · cta 15/600
        family = pick_font_family()
        self.f_title = ctk.CTkFont(family=family, size=18, weight="bold")
        self.f_section = ctk.CTkFont(family=family, size=14, weight="bold")
        self.f_body = ctk.CTkFont(family=family, size=13)
        self.f_small = ctk.CTkFont(family=family, size=11)
        self.f_btn = ctk.CTkFont(family=family, size=13)
        self.f_btn_big = ctk.CTkFont(family=family, size=15, weight="bold")
        self.f_mono = ctk.CTkFont(family="Consolas", size=11)

        # 结果状态
        self.current_image_url = None
        self.current_image_data = None
        self.current_image = None
        self.current_video_url = None
        self.current_video_data = None
        self.last_mode = None        # "image" / "video"
        self.is_generating = False
        self.video_id = None

        # 历史记录相关状态
        self.active_record = None    # 当前在预览区查看的历史记录（None = 查看本次生成结果）
        self._pending_params = None  # 本次生成使用的输入参数（用于写入历史）
        self._pending_record_id = None  # 刚写入的历史记录 id（用于补写本地缓存）
        self.history_panel = None
        self.gallery_grid = None    # 视觉陈列版：画廊视图（首次切到画廊时懒创建）
        self._page_frames = {}       # 导航页标识 → 内容页 frame
        self._nav_buttons = {}       # 导航页标识 → 导航按钮
        self.current_page = PAGE_IMAGE
        self._preview_expanded = False  # 预览区是否展开占满全窗
        self._cancel_requested = False  # 生成中止标志（线程不可强杀：完成后丢弃结果）
        self._result_state = "idle"     # idle / loading / success / error
        self._result_summary = ""       # 结果条摘要（主题切换后重绘用）
        self._result_detail = ""        # 结果详情全文（详情弹层展示，不在主界面铺全文）
        self._skeleton_on = False       # 画布骨架屏动画开关
        self._result_tint_token = 0     # 结果条换肤代数（新状态到来即打断旧插值）
        self._cost_token = 0            # 耗时计数演绎代数（任何 _set_result 即打断）
        self._wait_token = 0            # 「已等待」计时代数（启停即失效旧链）
        self._gen_started_at = None     # 生成开始时间（结果条展示耗时）
        self._restart_requested = False  # 主题切换后重建窗口（main() 据此循环）
        self._prompt_placeholder = "描述画面：主体 + 风格 + 光线 + 构图"

        # 初始化生成器
        try:
            self.generator = AgnesImageGenerator()
            self.api_key = self.generator.api_key
            self.video_generator = AgnesVideoGenerator()
        except ValueError as e:
            self.generator = None
            self.video_generator = None
            self.api_key = None
            messagebox.showwarning("API Key 未配置", str(e))

        self._build_ui()
        self._animate_progress()  # 启动进度条脉冲动画循环

    # ===================== UI 构建 =====================
    def _build_ui(self):
        root = self.root

        # ---- 主内容：三栏可拖拽骨架（导航 | 输入 | 预览）
        # 顶栏已取消：品牌并入导航顶部、连接状态并入状态栏，回收 44px 垂直空间 ----
        main = ctk.CTkFrame(root, fg_color="transparent")
        main.pack(fill=tk.BOTH, expand=True, padx=PAGE_PAD, pady=(S_MD, S_SM))

        self.paned = tk.PanedWindow(
            main, orient=tk.HORIZONTAL, sashwidth=6, sashrelief=tk.FLAT,
            bg=PAGE_BG, bd=0,
        )
        self.paned.pack(fill=tk.BOTH, expand=True)
        self.paned.bind("<ButtonRelease-1>", lambda e: self._save_ui_state())

        # ===== 左栏：导航（品牌 + 功能入口）—— 右侧接缝平角 =====
        nav_frame = PanelCard(self.paned, flat_side="right")
        self.nav_frame = nav_frame
        self.paned.add(nav_frame, width=W_NAV, minsize=176, stretch="never")

        brand = ctk.CTkFrame(nav_frame.content, fg_color="transparent")
        brand.pack(fill=tk.X, padx=CARD_PAD, pady=(CARD_PAD, 0))
        ctk.CTkLabel(brand, text="Agnes", font=self.f_title,
                     text_color=TEXT_MAIN).pack(side=tk.LEFT)
        ctk.CTkLabel(brand, text="生成器", font=self.f_small,
                     text_color=TEXT_SUB).pack(side=tk.LEFT, padx=(S_XS, 0),
                                               pady=(S_XS, 0))

        ctk.CTkLabel(nav_frame.content, text="工作台", font=self.f_small,
                     text_color=TEXT_SUB).pack(anchor=tk.W, padx=CARD_PAD,
                                               pady=(S_MD, S_SM))

        for key, icon, label in (
            (PAGE_IMAGE, "🖼", "图片生成"),
            (PAGE_VIDEO, "🎬", "视频生成"),
            (PAGE_HISTORY, "🕘", "历史记录"),
            (PAGE_SETTINGS, "⚙", "设置"),
        ):
            btn = ctk.CTkButton(
                nav_frame.content, text=f"{icon}  {label}", anchor="w",
                height=H_NAV, corner_radius=R_CTRL, font=self.f_body,
                fg_color="transparent", hover_color=FILL,
                text_color=TEXT_MAIN,
                command=lambda k=key: self._select_page(k),
            )
            btn.pack(fill=tk.X, padx=S_SM, pady=S_XS)
            self._nav_buttons[key] = btn

        # ===== 中栏：功能内容页（四页叠放，随导航切换） =====
        mid_frame = ctk.CTkFrame(self.paned, fg_color="transparent")
        self.mid_frame = mid_frame
        self.paned.add(mid_frame, width=W_INPUT, minsize=360, stretch="always")

        # 中栏：四角全圆角（两侧都不与其它栏相接）
        content = PanelCard(mid_frame)
        content.pack(fill=tk.BOTH, expand=True)
        content.content.grid_rowconfigure(0, weight=1)
        content.content.grid_columnconfigure(0, weight=1)
        for key in (PAGE_IMAGE, PAGE_VIDEO, PAGE_HISTORY, PAGE_SETTINGS):
            fr = ctk.CTkFrame(content.content, fg_color="transparent")
            fr.grid(row=0, column=0, sticky="nsew")
            fr.grid_remove()
            self._page_frames[key] = fr

        self._build_image_tab(self._page_frames[PAGE_IMAGE])
        self._build_video_tab(self._page_frames[PAGE_VIDEO])
        self._build_history_tab(self._page_frames[PAGE_HISTORY])
        self._build_settings_page(self._page_frames[PAGE_SETTINGS])
        # 应用设置里的生成默认值与网络模式（图像/视频参数下拉框）
        self._apply_generation_defaults()

        # ===== 右栏：预览与结果区（可伸缩，⛶ 一键展开占满全窗） =====
        right_frame = PanelCard(self.paned, flat_side="left")
        self.right_frame = right_frame
        self.paned.add(right_frame, width=560, minsize=420, stretch="always")

        header = ctk.CTkFrame(right_frame.content, fg_color="transparent")
        header.pack(fill=tk.X, padx=CARD_PAD, pady=(S_SM, 0))
        self.preview_title = ctk.CTkLabel(header, text="生成结果", font=self.f_section,
                                          text_color=TEXT_MAIN)
        self.preview_title.pack(side=tk.LEFT, pady=S_SM)
        self.preview_badge = ctk.CTkLabel(header, text="", font=self.f_small,
                                          text_color=TEXT_SUB)
        self.preview_badge.pack(side=tk.LEFT, padx=(S_SM, 0), pady=S_SM)
        self.btn_expand_preview = ctk.CTkButton(
            header, text="⛶", width=H_CHIP, height=H_CHIP, corner_radius=R_PILL,
            font=self.f_small, fg_color=FILL, hover_color=FILL_HOVER,
            text_color=TEXT_MAIN, command=self._toggle_preview_expand,
        )
        self.btn_expand_preview.pack(side=tk.RIGHT, pady=S_SM)
        ToolTip(self.btn_expand_preview, "展开 / 还原预览（占满窗口）")

        self.image_canvas = tk.Canvas(
            right_frame.content, bg=ui_theme.t.PAGE_BG,
            highlightthickness=0, bd=0,
        )
        self.image_canvas.pack(fill=tk.BOTH, expand=True, padx=CARD_PAD, pady=S_SM)
        self.image_canvas.bind("<Configure>", self._resize_preview)
        # 画布内容（骨架 / 提示文字）为 Canvas 图元，不随 CTk 主题自动刷新：
        # 记录当前内容，主题切换时原样重绘。
        self._canvas_hint_text = None

        # 结果条（40px）：生成状态收敛为一处，全文（URL / 参数）收进「详情」弹层
        self.result_bar = ctk.CTkFrame(right_frame.content, fg_color=FILL,
                                       corner_radius=R_CTRL)
        self.result_bar.pack(fill=tk.X, padx=CARD_PAD, pady=S_SM)
        self.result_icon = ctk.CTkLabel(self.result_bar, text="○", width=16,
                                        font=self.f_body, text_color=TEXT_SUB)
        self.result_icon.pack(side=tk.LEFT, padx=(CARD_PAD, S_SM), pady=S_SM)
        self.result_text = ctk.CTkLabel(self.result_bar, text="尚未生成",
                                        font=self.f_body, text_color=TEXT_SUB,
                                        anchor="w")
        self.result_text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=S_SM)
        self.btn_detail = ctk.CTkButton(
            self.result_bar, text="详情", width=56, height=H_CHIP,
            corner_radius=R_PILL, font=self.f_small, fg_color="transparent",
            hover_color=FILL_HOVER, text_color=ACCENT_TEXT, state="disabled",
            command=self._show_result_detail,
        )
        self.btn_detail.pack(side=tk.RIGHT, padx=CARD_PAD, pady=S_SM)

        # 操作条（44px）：播放 / 重试按结果类型条件渲染，替代永久禁用占位
        bottom = ctk.CTkFrame(right_frame.content, fg_color="transparent")
        bottom.pack(fill=tk.X, padx=CARD_PAD, pady=(0, CARD_PAD))

        self.btn_save = self._secondary_btn(bottom, "保存", self._save_result)
        self.btn_save.pack(side=tk.LEFT, pady=S_SM)

        self.btn_copy_url = self._secondary_btn(bottom, "复制 URL", self._copy_url)
        self.btn_copy_url.pack(side=tk.LEFT, padx=(S_SM, 0), pady=S_SM)

        self.btn_open = self._secondary_btn(bottom, "浏览器打开", self._open_in_browser)
        self.btn_open.pack(side=tk.LEFT, padx=S_SM, pady=S_SM)

        self.btn_play = self._secondary_btn(bottom, "▶ 播放", self._play_current)
        self.btn_retry = self._secondary_btn(bottom, "重试", self._retry_generation)

        # 底部状态栏（32px）：操作反馈 + 连接状态 + 进度
        status_bar = ctk.CTkFrame(root, fg_color="transparent")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=PAGE_PAD, pady=(0, S_XS))

        self.status_var = ctk.StringVar(value="就绪")
        ctk.CTkLabel(status_bar, textvariable=self.status_var, font=self.f_small,
                     text_color=TEXT_SUB).pack(side=tk.LEFT, pady=S_SM)

        self.progress_bar = ctk.CTkProgressBar(
            status_bar, width=200, height=6, corner_radius=3,
            progress_color=ACCENT, fg_color=FILL_HOVER,
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(side=tk.RIGHT, pady=S_SM)

        # 连接状态胶囊：不再展示密钥片段（防肩窥），点击直达设置
        self._top_key_pill = ctk.CTkLabel(
            status_bar, text="", font=self.f_small, corner_radius=R_CTRL,
            fg_color=FILL, text_color=TEXT_SUB, cursor="hand2",
        )
        self._top_key_pill.pack(side=tk.RIGHT, padx=(0, S_MD), pady=S_SM)
        self._top_key_pill.bind(
            "<Button-1>", lambda e: self._select_page(PAGE_SETTINGS))
        ToolTip(self._top_key_pill, "点击前往设置，管理 API 密钥")
        self._refresh_key_pill()

        self._bind_shortcuts()
        self._select_page(PAGE_IMAGE)
        # 初始：未输入提示词 → 两个 CTA 禁用；无结果 → 操作按钮禁用
        self._refresh_cta_state()
        self._update_action_buttons()

        # 订阅主题变化：CTk 控件由 set_appearance_mode 自动刷新，
        # 这里补充刷新 Canvas 图元与显式色控件（见 on_theme_changed）。
        ui_theme.subscribe(self.on_theme_changed)

        # 恢复上次的分栏宽度与预览展开状态（等布局稳定后应用）
        self.root.after(250, self._apply_ui_state)

    def on_theme_changed(self):
        """主题切换后原地刷新：处理 CTk 主题系统覆盖不到的部分。

        CTk 控件（按钮 / 输入框 / 标签 / 分段控件 …）在 ctk.set_appearance_mode
        时会自动重绘；但以下两类不会：
          1. tk.Canvas 上的图元（预览画布的骨架条 / 提示文字 / 底色）
          2. 显式传了 fg_color=TOKEN 的控件（CTk 视为「用户自定义色」，不跟随主题）
        前者在下方手动重绘，后者交给 ui_theme.retheme_explicit 按值反查刷新，
        两者合计即可完整换肤，无需销毁重建窗口（无闪烁、不丢状态）。
        """
        # ① 显式 token 色：按「旧值 → 新值」映射整体刷新
        try:
            ui_theme.retheme_explicit(self.root)
        except Exception:
            pass

        # ② tk 原生容器（不响应 CTk 外观模式，需手动换底色）
        try:
            self.paned.configure(bg=ui_theme.t.PAGE_BG)
        except Exception:
            pass

        # ③ Canvas 底色与图元
        try:
            self.image_canvas.configure(bg=ui_theme.t.PAGE_BG)
        except Exception:
            pass

        # 预览画布：按当前内容类型原样重绘（图片 / 骨架 / 提示文字）
        try:
            if getattr(self, "current_image", None) is not None:
                self._resize_preview()
            elif getattr(self, "_skeleton_on", False):
                self._skeleton_on = False      # 先停，避免叠加出第二条动画
                self._draw_canvas_skeleton(
                    getattr(self, "_skel_title", "正在生成…"))
            elif getattr(self, "_canvas_hint_text", None):
                self._draw_canvas_hint(self._canvas_hint_text)
            else:
                self.image_canvas.delete("all")
        except Exception:
            pass

        # 导航选中态：显式色，需手动刷新
        try:
            self._select_page(self.current_page, pulse=False)
        except Exception:
            pass
        # 进度条 / 结果条 / 密钥胶囊：显式色，需手动刷新
        try:
            self.progress_bar.configure(
                progress_color=ui_theme.t.ACCENT,
                fg_color=ui_theme.t.FILL_HOVER)
            self.result_bar.configure(fg_color=ui_theme.t.FILL)
            self._top_key_pill.configure(fg_color=ui_theme.t.FILL)
        except Exception:
            pass
        # 结果条状态色（图标 + 文字）随主题重新取值
        # （animate=False：主题原子刷新期间直接落终态，不跑颜色插值）
        try:
            if getattr(self, "_result_state", None):
                self._set_result(self._result_state, self._result_summary or "",
                                 self._result_detail, animate=False)
        except Exception:
            pass

    # ---------- 导航与布局 ----------
    def _select_page(self, key: str, pulse: bool = True):
        """左侧导航选中某个功能页：更新按钮态、切换内容页、刷新状态栏

        pulse=False：主题重绘等被动重放路径跳过 CTA 提亮脉冲。
        """
        self.current_page = key
        for k, btn in self._nav_buttons.items():
            sel = (k == key)
            btn.configure(
                fg_color=SELECTED_BG if sel else "transparent",
                text_color=ACCENT_TEXT if sel else TEXT_MAIN,
                hover_color=ACCENT_SOFT if sel else FILL,
            )
        for k, fr in self._page_frames.items():
            if k == key:
                fr.grid()
            else:
                fr.grid_remove()

        if key == PAGE_IMAGE:
            self.status_var.set("图片生成模式：提示词 + 可选参考图")
        elif key == PAGE_VIDEO:
            self.status_var.set("视频生成模式：提示词 + 可选参考图（异步生成，需等待）")
        elif key == PAGE_HISTORY:
            self._refresh_history()
            total = len(history_store.load_history())
            self.status_var.set(
                f"历史记录：共 {total} 条，点击条目在右侧查看提示词、参数与结果"
            )
        else:
            self.status_var.set("设置")
        self._update_action_buttons()
        # CTA 提亮脉冲：每次切到生成页、CTA 可用时做 1 次 600ms 明度上浮回落
        # （等布局稳定再触发；禁用态 / 生成中 / 减弱动态效果时自动跳过）
        if pulse and key in (PAGE_IMAGE, PAGE_VIDEO):
            self.root.after(150, self._pulse_cta_if_ready)

    # ---- CTA 提亮脉冲（引导，一次性，不做持续强调） ----
    def _pulse_cta_if_ready(self):
        """取首个可用 CTA 提亮 1 次；被后续状态变化打断即让位"""
        if self.is_generating or ui_anim.reduce_motion():
            return
        for btn in (self.btn_gen_image, self.btn_gen_video):
            try:
                if str(btn.cget("state")) == "normal":
                    self._pulse_cta(btn)
                    break
            except Exception:
                continue

    def _pulse_cta(self, btn):
        """fg 色向白 18% 上浮 300ms（ease-out）→ 回落 300ms（ease-in）。

        一次性；期间进入生成（_tint_cta 接管）或按钮变禁用即中止，
        通过 btn._cta_pulse_token 打断旧链，避免与语义换色叠打。
        """
        token = getattr(btn, "_cta_pulse_token", 0) + 1
        btn._cta_pulse_token = token
        try:
            base = btn.cget("fg_color")
            if not ui_anim.is_hex_color(base):
                return
        except Exception:
            return
        hi = ui_anim.mix_color(base, "#FFFFFF", 0.18)
        n, step_ms = 6, 50  # 6×50=300ms 上行 + 300ms 回落 = 600ms
        # 登记活动链：主题切换收口时直接落回 base（当前调色板 token 色），
        # 让 retheme_explicit 能按旧→新映射接手，不留半途亮色。
        ui_anim.track_chain(btn, "_cta_pulse_token", token, {"fg_color": base})

        def alive() -> bool:
            if getattr(btn, "_cta_pulse_token", None) != token:
                return False  # 已被新链顶替或 settle_all 停链
            if self.is_generating:
                return False
            try:
                return str(btn.cget("state")) == "normal"
            except Exception:
                return False

        def up(i: int = 0):
            if not alive():
                return
            try:
                btn.configure(
                    fg_color=ui_anim.mix_color(
                        base, hi, ui_anim.ease_out((i + 1) / n)))
            except Exception:
                return
            if i + 1 < n:
                btn.after(step_ms, lambda: up(i + 1))
            else:
                down()

        def down(i: int = 0):
            if not alive():
                return
            try:
                btn.configure(
                    fg_color=ui_anim.mix_color(
                        hi, base, ui_anim.ease_in((i + 1) / n)))
            except Exception:
                return
            if i + 1 < n:
                btn.after(step_ms, lambda: down(i + 1))
            else:
                ui_anim.drop_chain(btn, "_cta_pulse_token", token)  # 自然结束

        up()

    def _toggle_preview_expand(self):
        """预览区展开/还原：展开时隐藏导航栏与功能页，占满全窗"""
        self._preview_expanded = not self._preview_expanded
        expanded = self._preview_expanded
        try:
            self.paned.paneconfig(self.nav_frame, hide=expanded)
            self.paned.paneconfig(self.mid_frame, hide=expanded)
        except Exception:
            pass
        self.btn_expand_preview.configure(text="⤢" if expanded else "⛶")
        # 等 sash 位移结束后重算预览尺寸（250ms 位移 + 一帧）
        self.root.after(260, self._resize_preview)
        self._save_ui_state()

    # ---------- 界面状态持久化 ----------
    def _ui_state_path(self):
        return os.path.join(history_store.get_data_dir(), "ui_state.json")

    def _load_ui_state(self) -> dict:
        try:
            with open(self._ui_state_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_ui_state(self):
        """保存分栏宽度与预览展开状态（拖动分隔条 / 切换展开时触发）

        注意：经典 tk.PanedWindow 没有 ttk 的 sashpos()，实际宽度要用
        winfo_width() 读取；恢复时用 paneconfig(width=) 设置。
        """
        try:
            history_store.ensure_dirs()
            state = {"preview_expanded": bool(self._preview_expanded)}
            if not self._preview_expanded:  # 隐藏态的宽度无意义，跳过
                state["nav_width"] = int(self.nav_frame.winfo_width())
                state["mid_width"] = int(self.mid_frame.winfo_width())
            tmp = self._ui_state_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._ui_state_path())
        except Exception:
            pass

    def _apply_ui_state(self):
        """启动后延迟恢复：上次的分栏宽度与预览展开状态"""
        state = self._load_ui_state()
        if not state.get("preview_expanded"):
            try:
                nav_w = max(176, min(int(state.get("nav_width") or W_NAV), 300))
                mid_w = max(360, min(int(state.get("mid_width") or W_INPUT), 760))
                self.paned.paneconfig(self.nav_frame, width=nav_w)
                self.paned.paneconfig(self.mid_frame, width=mid_w)
            except Exception:
                pass
        if state.get("preview_expanded"):
            self._preview_expanded = False  # _toggle 会翻转，先归零
            self._toggle_preview_expand()

    def _secondary_btn(self, parent, text, command):
        return ctk.CTkButton(
            parent, text=text, command=command, height=H_CHIP, corner_radius=R_PILL,
            font=self.f_body, fg_color=FILL, hover_color=FILL_HOVER,
            text_color=TEXT_MAIN,
        )

    def _option_menu(self, parent, values, width):
        """统一风格的下拉菜单（32px / 圆角 12）"""
        return ctk.CTkOptionMenu(
            parent, values=list(values), width=width, height=H_DROP,
            corner_radius=R_CTRL, font=self.f_small, dropdown_font=self.f_small,
            fg_color=FILL, button_color=FILL_HOVER,
            button_hover_color=FILL, text_color=TEXT_MAIN,
            dropdown_fg_color=CARD_BG,
            dropdown_text_color=TEXT_MAIN, dropdown_hover_color=ACCENT_SOFT,
            anchor="center",
        )

    # ---------- 图片生成页 ----------
    def _build_image_tab(self, parent):
        # CTA 贴底：空提示词时禁用（事前防错，替代点击后才弹窗校验）
        self.btn_gen_image = ctk.CTkButton(
            parent, text="开始生成图片（Ctrl+Enter）",
            command=lambda: self._start_generate("image"),
            height=H_CTA, corner_radius=R_CTRL, font=self.f_btn_big,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, state="disabled",
        )
        self.btn_gen_image.pack(side=tk.BOTTOM, fill=tk.X, padx=CARD_PAD,
                                pady=(S_SM, CARD_PAD))

        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=CARD_PAD, pady=(CARD_PAD, 0))

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill=tk.X)
        ctk.CTkLabel(head, text="提示词", font=self.f_section,
                     text_color=TEXT_MAIN).pack(side=tk.LEFT)
        self.prompt_count = ctk.CTkLabel(head, text="0 字", font=self.f_small,
                                        text_color=TEXT_SUB)
        self.prompt_count.pack(side=tk.RIGHT)

        # 提示词框：96px（4 行）起步，随内容长高，192px（8 行）封顶
        self.prompt_image = ctk.CTkTextbox(
            inner, height=96, corner_radius=R_CTRL, font=self.f_body,
            fg_color=FIELD_BG, border_width=1, border_color=FIELD_BORDER,
            text_color=TEXT_DISABLED, wrap="word",
        )
        self.prompt_image.pack(fill=tk.X, pady=(LABEL_GAP, BLOCK_GAP))
        self._init_prompt_box(self.prompt_image)

        # 参考图：默认收起为 40px 一行条
        self.ref_image = ReferenceImageList(
            inner, max_items=5, title="参考图", on_change=None, fonts={
                "small": self.f_small,
            },
        )
        self.ref_image.pack(fill=tk.X, pady=(0, BLOCK_GAP))

        # 示例提示词：完整文案（2×2 网格），点击追加而非覆盖
        ctk.CTkLabel(inner, text="示例提示词（点击追加）", font=self.f_small,
                     text_color=TEXT_SUB, anchor=tk.W).pack(fill=tk.X,
                                                            pady=(0, LABEL_GAP))
        ex_frame = ctk.CTkFrame(inner, fg_color="transparent")
        ex_frame.pack(fill=tk.X)
        ex_frame.grid_columnconfigure((0, 1), weight=1, uniform="ex")
        for i, ex in enumerate((
            "一只可爱的猫咪在花园里玩耍",
            "科幻风格的未来城市，霓虹灯光",
            "梵高风格的向日葵油画",
            "赛博朋克风格的少女肖像",
        )):
            btn = ctk.CTkButton(
                ex_frame, text=ex, command=lambda e=ex: self._append_prompt(e),
                height=H_CHIP, corner_radius=R_PILL, font=self.f_small,
                fg_color=FILL, hover_color=FILL_HOVER, text_color=TEXT_MAIN,
            )
            btn.grid(row=i // 2, column=i % 2, sticky="ew",
                     padx=(0 if i % 2 else S_SM), pady=S_XS)
            ToolTip(btn, f"追加到提示词：{ex}")

        # 画幅：图示化选择（画出真实比例，替代裸数字下拉）
        ctk.CTkLabel(inner, text="画幅", font=self.f_small,
                     text_color=TEXT_SUB, anchor="w").pack(fill=tk.X,
                                                           pady=(BLOCK_GAP, 0))
        self.aspect_image = AspectPicker(inner, IMAGE_ASPECTS, value="4:3",
                                         on_change=self._on_image_aspect)
        self.aspect_image.pack(fill=tk.X, pady=(LABEL_GAP, BLOCK_GAP))

        # 参数区（32px 一行：尺寸 | 模型）
        param_frame = ctk.CTkFrame(inner, fg_color="transparent")
        param_frame.pack(fill=tk.X)
        ctk.CTkLabel(param_frame, text="尺寸", font=self.f_small,
                     text_color=TEXT_SUB).pack(side=tk.LEFT)
        self.size_image = self._option_menu(param_frame, SIZE_OPTIONS, 112)
        self.size_image.set("1024x768")
        self.size_image.pack(side=tk.LEFT, padx=(LABEL_GAP, BLOCK_GAP))
        ctk.CTkLabel(param_frame, text="模型", font=self.f_small,
                     text_color=TEXT_SUB).pack(side=tk.LEFT)
        self.model_image = self._option_menu(param_frame, MODEL_OPTIONS, 176)
        self.model_image.set(MODEL_OPTIONS[0])
        self.model_image.pack(side=tk.LEFT, padx=(LABEL_GAP, 0))

    # ---------- 视频生成页 ----------
    def _build_video_tab(self, parent):
        self.btn_gen_video = ctk.CTkButton(
            parent, text="开始生成视频（Ctrl+Enter）",
            command=lambda: self._start_generate("video"),
            height=H_CTA, corner_radius=R_CTRL, font=self.f_btn_big,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, state="disabled",
        )
        self.btn_gen_video.pack(side=tk.BOTTOM, fill=tk.X, padx=CARD_PAD,
                                pady=(S_SM, CARD_PAD))

        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.pack(fill=tk.BOTH, expand=True, padx=CARD_PAD, pady=(CARD_PAD, 0))

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill=tk.X)
        ctk.CTkLabel(head, text="提示词", font=self.f_section,
                     text_color=TEXT_MAIN).pack(side=tk.LEFT)
        ctk.CTkLabel(head, text="描述视频内容与运镜", font=self.f_small,
                     text_color=TEXT_SUB).pack(side=tk.LEFT, padx=(LABEL_GAP, 0),
                                               pady=(S_XS, 0))
        self.prompt_count_video = ctk.CTkLabel(head, text="0 字",
                                              font=self.f_small,
                                              text_color=TEXT_SUB)
        self.prompt_count_video.pack(side=tk.RIGHT)

        # 提示词框：96px（4 行）起步，随内容长高，192px 封顶
        self.prompt_video = ctk.CTkTextbox(
            inner, height=96, corner_radius=R_CTRL, font=self.f_body,
            fg_color=FIELD_BG, border_width=1, border_color=FIELD_BORDER,
            text_color=TEXT_DISABLED, wrap="word",
        )
        self.prompt_video.pack(fill=tk.X, pady=(LABEL_GAP, BLOCK_GAP))
        self._init_prompt_box(self.prompt_video)

        # 参考图列表（可选，最多 5 张；选本地文件会自动上传图床转成公网 URL）
        self.ref_video = ReferenceImageList(
            inner, max_items=5, title="参考图", on_change=None,
            fonts={"small": self.f_small},
            auto_upload=self._upload_to_image_host,
            status_cb=lambda s: self.status_var.set(s),
        )
        self.ref_video.pack(fill=tk.X, pady=(0, BLOCK_GAP))

        ctk.CTkLabel(
            inner,
            text="💡 本地图自动上传图床转 URL（推荐免费 GitHub 方案：.env 配 "
                 "GITHUB_TOKEN+GITHUB_REPO）；也可「+ URL」手动粘贴直链",
            font=self.f_small, text_color=TEXT_SUB, anchor="w",
            wraplength=W_INPUT - 32, justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, BLOCK_GAP))

        # 参数区（2×2 网格：时长|画幅 / 尺寸|模型）
        param_frame = ctk.CTkFrame(inner, fg_color="transparent")
        param_frame.pack(fill=tk.X, pady=(0, 0))
        param_frame.grid_columnconfigure((0, 1), weight=1, uniform="vp")

        def _vp(row, col, label, values=None, width=0, note=None, set_value=None):
            cell = ctk.CTkFrame(param_frame, fg_color="transparent")
            cell.grid(row=row, column=col, sticky="w", padx=(0, BLOCK_GAP),
                      pady=(0, S_SM))
            ctk.CTkLabel(cell, text=label, font=self.f_small,
                         text_color=TEXT_SUB).pack(side=tk.LEFT)
            if values is not None:
                menu = self._option_menu(cell, values, width)
                if set_value:
                    menu.set(set_value)
                menu.pack(side=tk.LEFT, padx=(LABEL_GAP, 0))
                return menu
            if note is not None:
                ctk.CTkLabel(cell, text=note, font=self.f_small,
                             text_color=TEXT_SUB).pack(side=tk.LEFT, padx=(LABEL_GAP, 0))
            return None

        self.video_seconds = _vp(0, 0, "时长", VIDEO_SECONDS_OPTIONS, 76,
                                 set_value="5")
        self.model_video = _vp(0, 1, "模型", VIDEO_MODEL_OPTIONS, 168,
                               set_value=VIDEO_MODEL_OPTIONS[0])
        _vp(1, 0, "尺寸", note="720P（固定）")

        # 画幅：图示化选择，占满整行（6 个选项均分宽度）
        ctk.CTkLabel(inner, text="画幅", font=self.f_small,
                     text_color=TEXT_SUB, anchor="w").pack(fill=tk.X,
                                                           pady=(S_SM, 0))
        self.aspect_video = AspectPicker(inner, VIDEO_ASPECT_OPTIONS,
                                         value="16:9", on_change=None)
        self.aspect_video.pack(fill=tk.X, pady=(LABEL_GAP, 0))

        # 费用说明
        ctk.CTkLabel(
            inner,
            text="💰 视频生成按秒计费（当前 Agnes 平台限时免费，具体以平台公告为准）",
            font=self.f_small, text_color=WARNING_TEXT, anchor=tk.W,
        ).pack(fill=tk.X, pady=(S_SM, 0))

    # ---------- 历史记录页（列表 / 画廊双视图） ----------
    def _build_history_tab(self, parent):
        # 顶部视图切换：列表（信息密集） / 画廊（瀑布流陈列）
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill=tk.X, padx=S_SM, pady=(S_SM, 0))
        self.history_view_seg = ctk.CTkSegmentedButton(
            top, values=["列表", "画廊"], command=self._switch_history_view,
            height=H_CHIP, corner_radius=R_PILL, font=self.f_small,
            fg_color=FILL, selected_color=CARD_BG,
            selected_hover_color=ACCENT_SOFT,
            unselected_color=FILL, unselected_hover_color=FILL_HOVER,
            text_color=TEXT_MAIN,
        )
        self.history_view_seg.set("列表")
        self.history_view_seg.pack(side=tk.RIGHT)

        host = ctk.CTkFrame(parent, fg_color="transparent")
        host.pack(fill=tk.BOTH, expand=True)
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)
        self.history_list_host = ctk.CTkFrame(host, fg_color="transparent")
        self.history_list_host.grid(row=0, column=0, sticky="nsew")
        self.history_gallery_host = ctk.CTkFrame(host, fg_color="transparent")
        self.history_gallery_host.grid(row=0, column=0, sticky="nsew")
        self.history_gallery_host.grid_remove()   # 画廊懒创建，默认隐藏

        self.history_panel = HistoryPanel(
            self.history_list_host,
            fonts={
                "small": self.f_small,
                "body": self.f_body,
                "section": self.f_section,
            },
            colors={
                # 启动时由 ui_theme 解析好的色板（键名与历史面板约定一致）
                "page_bg": PAGE_BG,
                "card_bg": CARD_BG,
                "card_border": CARD_BORDER,
                "field_bg": FIELD_BG,
                "field_border": FIELD_BORDER,
                "text_main": TEXT_MAIN,
                "text_sub": TEXT_SUB,
                "accent": ACCENT,
                "accent_hover": ACCENT_HOVER,
                "btn_gray": BTN_GRAY,
                "btn_gray_hover": BTN_GRAY_HOVER,
                "destructive": DESTRUCTIVE,
                "selected_bg": SELECTED_BG,
            },
            on_select=self._on_history_select,
            on_status=lambda s: self.status_var.set(s),
            on_load_params=self._load_params_from_record,
        )
        self.history_panel.pack(fill=tk.BOTH, expand=True, padx=S_SM,
                                pady=(S_SM, 0))

    def _switch_history_view(self, view: str):
        """列表 ↔ 画廊切换，双向同步筛选关键词与选中记录"""
        to_gallery = view == "画廊"
        if to_gallery:
            if self.gallery_grid is None:
                self.gallery_grid = GalleryGrid(
                    self.history_gallery_host,
                    fonts={"small": self.f_small, "body": self.f_body},
                    on_select=self._on_history_select,
                    on_open=self._open_lightbox,
                    on_status=lambda s: self.status_var.set(s),
                    on_load_params=self._load_params_from_record,
                )
                self.gallery_grid.pack(fill=tk.BOTH, expand=True)
            self.gallery_grid.set_state(
                filter_type=self.history_panel.filter_type,
                keyword=self.history_panel.keyword,
                selected_id=self.history_panel.selected_id,
            )
            self.history_list_host.grid_remove()
            self.history_gallery_host.grid()
        else:
            self.history_gallery_host.grid_remove()
            self.history_list_host.grid()
            if self.gallery_grid is not None:
                rec = self.gallery_grid._selected_record()
                if rec is not None:
                    self.history_panel._select(rec)

    # ---------- 设置页（密钥管理 / 生成默认值 / 网络模式 / 主题 / 存储目录） ----------
    def _build_settings_page(self, parent):
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=SCROLLBAR,
            scrollbar_button_hover_color=SCROLLBAR_HOVER,
        )
        self._settings_scroll = scroll
        scroll.pack(fill=tk.BOTH, expand=True, padx=CARD_PAD, pady=(CARD_PAD, 0))

        ctk.CTkLabel(scroll, text="设置", font=self.f_section,
                     text_color=TEXT_MAIN).pack(anchor=tk.W)

        # ----- 1. 密钥管理 + 测试连接 -----
        card = self._settings_card(
            scroll, "🔑 密钥管理",
            "图片/视频接口共用，保存到程序目录 .env（AGNES_API_KEY / AGNES_BASE_URL）",
        )
        cur_key = (os.environ.get("AGNES_API_KEY") or "").strip()
        self.settings_api_key_entry = self._settings_field_row(
            card, "API 密钥",
            lambda p: ctk.CTkEntry(
                p, height=H_INPUT, corner_radius=R_CTRL, font=self.f_body,
                show="•", fg_color=CARD_BG, border_color=FIELD_BORDER,
            ),
            tip="未配置时无法生成；点击「测试连接」可验证密钥与网络是否可用",
        )
        if cur_key:
            self.settings_api_key_entry.insert(0, cur_key)

        cur_base = (os.environ.get("AGNES_BASE_URL") or "https://apihub.agnes-ai.com/v1").strip()
        self.settings_base_url_entry = self._settings_field_row(
            card, "接口地址",
            lambda p: ctk.CTkEntry(
                p, height=H_INPUT, corner_radius=R_CTRL, font=self.f_body,
                fg_color=CARD_BG, border_color=FIELD_BORDER,
            ),
        )
        self.settings_base_url_entry.insert(0, cur_base)

        self._settings_btn_row(card, [
            ("💾 保存密钥", self._save_api_key, "primary"),
            ("🔌 测试连接", self._test_api_connection, "secondary"),
        ])
        self.settings_key_status = ctk.CTkLabel(
            card, text="", font=self.f_small, text_color=TEXT_SUB, anchor="w",
        )
        self.settings_key_status.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_MD))

        # ----- 2. 图床密钥（视频参考图自动上传用） -----
        card = self._settings_card(
            scroll, "🖼 图床密钥（视频参考图自动上传）",
            "推荐免费 GitHub 方案：公开仓库 + Personal Access Token（repo 权限）",
        )
        self.settings_gh_token_entry = self._settings_field_row(
            card, "GitHub Token",
            lambda p: ctk.CTkEntry(
                p, height=H_INPUT, corner_radius=R_CTRL, font=self.f_body,
                show="•", fg_color=CARD_BG, border_color=FIELD_BORDER,
            ),
        )
        self.settings_gh_token_entry.insert(0, os.environ.get("GITHUB_TOKEN", ""))

        self.settings_gh_repo_entry = self._settings_field_row(
            card, "GitHub 仓库",
            lambda p: ctk.CTkEntry(
                p, height=H_INPUT, corner_radius=R_CTRL, font=self.f_body,
                fg_color=CARD_BG, border_color=FIELD_BORDER,
            ),
            tip="如 用户名/my-images（公开仓库）",
        )
        self.settings_gh_repo_entry.insert(0, os.environ.get("GITHUB_REPO", ""))

        self.settings_see_token_entry = self._settings_field_row(
            card, "S.EE Token",
            lambda p: ctk.CTkEntry(
                p, height=H_INPUT, corner_radius=R_CTRL, font=self.f_body,
                show="•", fg_color=CARD_BG, border_color=FIELD_BORDER,
            ),
            tip="付费方案；配了 GITHUB 则优先使用 GitHub",
        )
        self.settings_see_token_entry.insert(0, os.environ.get("SEE_API_TOKEN", ""))

        self._settings_btn_row(card, [
            ("💾 保存图床密钥", self._save_host_keys, "secondary"),
        ])
        self.settings_host_status = ctk.CTkLabel(
            card, text="", font=self.f_small, text_color=TEXT_SUB, anchor="w",
        )
        self.settings_host_status.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_MD))

        # ----- 3. 生成默认值 -----
        card = self._settings_card(
            scroll, "🎛 生成默认值",
            "保存后立即应用到图片/视频生成页的默认参数",
        )
        settings = app_config.load()
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill=tk.X, padx=CARD_PAD, pady=(S_SM, S_XS))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="sd")

        def _default_row(row, col, label, values, width, current, fallback):
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=row, column=col, sticky="w", padx=(0, S_SM),
                      pady=(S_XS, S_XS))
            ctk.CTkLabel(cell, text=label, font=self.f_small,
                         text_color=TEXT_SUB).pack(side=tk.LEFT)
            menu = self._option_menu(cell, values, width)
            menu.set(current if current in values else fallback)
            menu.pack(side=tk.LEFT, padx=(LABEL_GAP, 0))
            return menu

        self.defaults_img_size = _default_row(0, 0, "图片尺寸", SIZE_OPTIONS, 112,
                                              settings.get("img_size", ""), "1024x768")
        self.defaults_img_model = _default_row(1, 0, "图片模型", MODEL_OPTIONS, 150,
                                               settings.get("img_model", ""), MODEL_OPTIONS[0])
        self.defaults_vid_seconds = _default_row(0, 1, "视频时长", VIDEO_SECONDS_OPTIONS, 76,
                                                 settings.get("vid_seconds", ""), "5")
        self.defaults_vid_aspect = _default_row(1, 1, "视频画幅", VIDEO_ASPECT_OPTIONS, 90,
                                                settings.get("vid_aspect", ""), "16:9")
        self.defaults_vid_model = _default_row(2, 1, "视频模型", VIDEO_MODEL_OPTIONS, 168,
                                               settings.get("vid_model", ""), VIDEO_MODEL_OPTIONS[0])

        self._settings_btn_row(card, [
            ("💾 保存默认值", self._save_generation_defaults, "primary"),
            ("↺ 恢复默认", self._reset_generation_defaults, "secondary"),
        ], pady=S_MD)
        self.settings_defaults_status = ctk.CTkLabel(
            card, text="", font=self.f_small, text_color=TEXT_SUB, anchor="w",
        )
        self.settings_defaults_status.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_MD))

        # ----- 4. 网络模式 -----
        card = self._settings_card(
            scroll, "🌐 网络模式",
            "本机代理不稳定时切换请求策略：直连优先 / 仅直连 / 仅系统代理",
        )
        net_labels = list(NETWORK_MODE_LABELS.values())
        self.settings_network_menu = self._option_menu(card, net_labels, 320)
        net_cur = settings.get("network_mode", "auto")
        self.settings_network_menu.set(NETWORK_MODE_LABELS.get(net_cur, NETWORK_MODE_LABELS["auto"]))
        self.settings_network_menu.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_SM, S_XS))
        self._settings_btn_row(card, [
            ("✅ 应用网络模式", self._save_network_mode, "secondary"),
        ])
        self.settings_network_status = ctk.CTkLabel(
            card, text=f"当前：{NETWORK_MODE_LABELS.get(net_cur, '自动')}",
            font=self.f_small, text_color=TEXT_SUB, anchor="w",
        )
        self.settings_network_status.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_MD))

        # ----- 5. 主题 -----
        card = self._settings_card(scroll, "🎨 主题",
                                   "切换外观模式（跟随系统 / 浅色 / 深色）；勾选“自动重启”则切换后重启程序彻底生效")
        theme_labels = list(THEME_LABELS.values())
        self.settings_theme_menu = self._option_menu(card, theme_labels, 320)
        theme_cur = settings.get("theme", "system")
        theme_restart = bool(settings.get("theme_auto_restart", False))
        self.settings_theme_menu.set(THEME_LABELS.get(theme_cur, THEME_LABELS["system"]))
        self.settings_theme_menu.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_SM, S_XS))
        self.settings_theme_restart = ctk.CTkCheckBox(
            card, text="切换后自动重启程序（彻底刷新，避免残留）",
            command=self._on_theme_restart_toggle,
            checkbox_width=18, checkbox_height=18, corner_radius=R_THUMB, border_width=1,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=FIELD_BORDER,
            checkmark_color=ON_ACCENT, text_color=TEXT_SUB,
            font=self.f_small,
        )
        if theme_restart:
            self.settings_theme_restart.select()
        self.settings_theme_restart.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_XS))
        self._settings_btn_row(card, [
            ("✅ 应用主题", self._save_theme, "secondary"),
        ])
        self.settings_theme_status = ctk.CTkLabel(
            card, text=self._theme_status_text(theme_cur, theme_restart),
            font=self.f_small, text_color=TEXT_SUB, anchor="w",
        )
        self.settings_theme_status.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_MD))

        # ----- 6. 文件存储地址与历史记录 -----
        card = self._settings_card(
            scroll, "📂 文件存储地址与历史记录",
            "历史记录 history.json、图片/视频缓存 media/、缩略图 thumbs/ 都保存在该目录",
        )
        self.settings_data_dir_entry = self._settings_field_row(
            card, "数据目录",
            lambda p: ctk.CTkEntry(
                p, height=H_INPUT, corner_radius=R_CTRL, font=self.f_body,
                fg_color=CARD_BG, border_color=FIELD_BORDER,
            ),
            tip="默认 F:\\AgnesGeneratorData；环境变量 AGNES_HISTORY_DIR 会覆盖此设置",
        )
        self.settings_data_dir_entry.insert(0, history_store.get_data_dir())

        self._settings_btn_row(card, [
            ("📁 浏览…", self._browse_data_dir, "secondary"),
            ("💾 保存路径", self._save_data_dir, "primary"),
            ("📂 打开文件夹", self._open_history_folder, "secondary"),
        ])
        self.settings_data_dir_status = ctk.CTkLabel(
            card, text="", font=self.f_small, text_color=TEXT_SUB, anchor="w",
        )
        self.settings_data_dir_status.pack(anchor=tk.W, padx=CARD_PAD, pady=(S_XS, S_MD))

        ctk.CTkLabel(
            scroll,
            text="设置保存位置：%APPDATA%\\AgnesGenerator\\settings.json（密钥在程序目录 .env）",
            font=self.f_small, text_color=TEXT_SUB, anchor=tk.W, wraplength=332,
        ).pack(anchor=tk.W, pady=(S_MD, S_XS))

    # ---------- 设置页辅助组件 ----------
    def _settings_card(self, parent, title: str, subtitle: str = None) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=FIELD_BG, corner_radius=R_CTRL,
                            border_width=1, border_color=FIELD_BORDER)
        card.pack(fill=tk.X, pady=(BLOCK_GAP, 0), padx=S_XS)
        ctk.CTkLabel(card, text=title, font=self.f_section,
                     text_color=TEXT_MAIN).pack(anchor=tk.W, padx=CARD_PAD,
                                                pady=(S_MD, S_XS))
        if subtitle:
            ctk.CTkLabel(card, text=subtitle, font=self.f_small,
                         text_color=TEXT_SUB, anchor="w", wraplength=332,
                         justify=tk.LEFT).pack(anchor=tk.W, padx=CARD_PAD,
                                               pady=(0, S_SM))
        return card

    def _settings_field_row(self, parent, label: str, widget_factory, tip: str = None):
        """字段行：标签+控件横向排列、说明文字另起一行。

        控件必须用子帧 top 作为 master 创建，并让标签/控件同放 top 内，
        否则控件会被 pack 到父卡片或受下方说明文字影响而宽度错乱。
        """
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill=tk.X, padx=CARD_PAD, pady=(S_SM, S_XS))
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill=tk.X)
        ctk.CTkLabel(top, text=label, width=88, font=self.f_small,
                     text_color=TEXT_SUB, anchor="w").pack(side=tk.LEFT,
                                                           padx=(0, LABEL_GAP))
        widget = widget_factory(top)
        widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if tip:
            ctk.CTkLabel(row, text=tip, font=self.f_small,
                         text_color=TEXT_SUB, anchor="w", wraplength=332,
                         justify=tk.LEFT).pack(anchor=tk.W, pady=(S_XS, 0))
        return widget

    def _settings_btn_row(self, card, buttons: list, pady=S_XS):
        """卡内按钮行：space-evenly 均匀分布（等效 CSS justify-content: space-evenly）。

        布局原理：n 个按钮占 2n+1 列 —— 空列(weight=1)与按钮列(weight=0)交替，
        空列平分剩余宽度，使所有间隙严格相等：首尾间隙 = 相邻间隙
        （区别于 space-around 的首尾减半、space-between 的无首尾间隙）。
        buttons: (text, command, kind) 元组，kind="primary" 主按钮 / "secondary" 次级按钮。
        """
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill=tk.X, padx=CARD_PAD, pady=(pady, S_XS))
        for i in range(2 * len(buttons) + 1):
            row.grid_columnconfigure(i, weight=1 if i % 2 == 0 else 0)
        for i, (text, command, kind) in enumerate(buttons):
            primary = kind == "primary"
            ctk.CTkButton(
                row, text=text, command=command,
                height=H_CHIP, corner_radius=R_PILL, font=self.f_body,
                fg_color=ACCENT if primary else ACCENT_SOFT,
                hover_color=ACCENT_HOVER if primary else ACCENT_SOFT_HOVER,
                text_color=ON_ACCENT if primary else ACCENT_TEXT,
                border_width=0,
            ).grid(row=0, column=2 * i + 1)
        return row

    # ---------- 设置页：密钥管理 ----------
    def _write_env_key(self, key_name: str, value: str):
        """把键值写入程序目录 .env 并同步到 os.environ（保留注释与其余配置）"""
        value = (value or "").strip()
        path = os.path.join(runtime_dir(), ".env")
        lines = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        out = []
        found = False
        for line in lines:
            if line.strip().startswith(key_name + "="):
                out.append(f"{key_name}={value}")
                found = True
            else:
                out.append(line)
        if not found:
            if out and out[-1].strip():
                out.append("")
            out.append(f"{key_name}={value}")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.environ[key_name] = value

    def _reload_generators(self):
        """用最新的 AGNES_API_KEY / AGNES_BASE_URL 刷新生成器实例"""
        key = (os.environ.get("AGNES_API_KEY") or "").strip()
        base = (os.environ.get("AGNES_BASE_URL") or "https://apihub.agnes-ai.com/v1").strip().rstrip("/")
        try:
            if self.generator is not None:
                self.generator.api_key = key or self.generator.api_key
                self.generator.base_url = base + "/images/generations"
            if self.video_generator is not None:
                self.video_generator.api_key = key or self.video_generator.api_key
                self.video_generator.base_url = base or self.video_generator.base_url
        except Exception as e:
            print(f"[settings] 刷新生成器失败: {type(e).__name__}: {e}")
        # 启动时未配置密钥的实例，保存密钥后补建
        if self.generator is None or self.video_generator is None:
            try:
                if self.generator is None:
                    self.generator = AgnesImageGenerator(key)
                if self.video_generator is None:
                    self.video_generator = AgnesVideoGenerator(key)
            except ValueError:
                pass

    def _refresh_key_pill(self):
        """状态栏连接胶囊：只给状态、不给密钥片段（点击跳设置）"""
        pill = getattr(self, "_top_key_pill", None)
        if pill is None:
            return
        if self.api_key:
            pill.configure(text="● 已连接",
                           fg_color=SUCCESS_BG, text_color=SUCCESS_TEXT)
        else:
            pill.configure(text="⚠ 未配置密钥 · 去设置",
                           fg_color=ERROR_BG, text_color=ERROR_TEXT)

    def _save_api_key(self):
        key = self.settings_api_key_entry.get().strip()
        base = self.settings_base_url_entry.get().strip() or "https://apihub.agnes-ai.com/v1"
        if not key:
            messagebox.showwarning("提示", "请先填写 API 密钥")
            return
        try:
            self._write_env_key("AGNES_API_KEY", key)
            self._write_env_key("AGNES_BASE_URL", base)
            self.api_key = key
            self._reload_generators()
            self._refresh_key_pill()
            self.settings_key_status.configure(text="✅ 密钥已保存到 .env 并生效", text_color=GREEN_PILL_TX)
            self.status_var.set("✅ API 密钥已保存")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存密钥失败：\n{e}")

    def _test_api_connection(self):
        key = self.settings_api_key_entry.get().strip() or (os.environ.get("AGNES_API_KEY") or "").strip()
        base = self.settings_base_url_entry.get().strip() or "https://apihub.agnes-ai.com/v1"
        if not key:
            self.settings_key_status.configure(text="❌ 请先填写 API 密钥", text_color=RED_PILL_TX)
            return
        self.settings_key_status.configure(text="⏳ 正在测试连接…", text_color=WARNING_TEXT)
        threading.Thread(target=self._test_connection_worker, args=(key, base), daemon=True).start()

    def _test_connection_worker(self, key: str, base: str):
        url = base.rstrip("/") + "/models"
        start = time.time()
        try:
            resp = adaptive_request(
                "GET", url,
                headers={"Authorization": key, "Accept": "application/json"},
                timeout=15,
            )
            ms = int((time.time() - start) * 1000)
            if 200 <= resp.status_code < 300:
                msg = f"✅ 连接成功（{ms}ms，HTTP {resp.status_code}）"
                ok = True
            elif resp.status_code in (401, 403):
                msg = f"❌ 密钥无效或无权限（HTTP {resp.status_code}）"
                ok = False
            else:
                msg = f"⚠️ 服务可访问，接口返回 HTTP {resp.status_code}（{ms}ms）"
                ok = True
        except Exception as e:
            # 必须在 except 内立刻拼好消息（except as e 块结束会删除 e）
            msg = f"❌ 连接失败: [{type(e).__name__}] {e}"
            ok = False
        self.root.after(0, lambda m=msg, o=ok: self._show_conn_result(m, o))

    def _show_conn_result(self, msg: str, ok: bool):
        self.settings_key_status.configure(
            text=msg, text_color=GREEN_PILL_TX if ok else RED_PILL_TX)
        self.status_var.set(msg)

    def _save_host_keys(self):
        try:
            self._write_env_key("GITHUB_TOKEN", self.settings_gh_token_entry.get())
            self._write_env_key("GITHUB_REPO", self.settings_gh_repo_entry.get())
            self._write_env_key("SEE_API_TOKEN", self.settings_see_token_entry.get())
            self.settings_host_status.configure(text="✅ 图床密钥已保存到 .env", text_color=GREEN_PILL_TX)
            self.status_var.set("✅ 图床密钥已保存")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存图床密钥失败：\n{e}")

    # ---------- 设置页：生成默认值 ----------
    def _apply_generation_defaults(self):
        s = app_config.load()
        if s.get("img_size") in SIZE_OPTIONS:
            self.size_image.set(s["img_size"])
            # 画幅图示与尺寸保持同步：由已保存尺寸反推画幅
            self._sync_aspect_from_size(s["img_size"])
        if s.get("img_model") in MODEL_OPTIONS:
            self.model_image.set(s["img_model"])
        if s.get("vid_seconds") in VIDEO_SECONDS_OPTIONS:
            self.video_seconds.set(s["vid_seconds"])
        if s.get("vid_aspect") in VIDEO_ASPECT_OPTIONS:
            self.aspect_video.set(s["vid_aspect"])
        if s.get("vid_model") in VIDEO_MODEL_OPTIONS:
            self.model_video.set(s["vid_model"])

    # ---------- 画幅与尺寸联动 ----------
    def _on_image_aspect(self, ratio: str):
        """切换画幅：尺寸下拉只保留该画幅下的像素选项"""
        options = SIZE_BY_ASPECT.get(ratio) or SIZE_OPTIONS
        current = self.size_image.get()
        self.size_image.configure(values=options)
        self.size_image.set(current if current in options else options[-1])
        self.status_var.set(f"画幅 {ratio} · 可选尺寸 {len(options)} 种")

    def _sync_aspect_from_size(self, size_str: str):
        """由尺寸反推画幅（如 1920x1080 → 16:9），用于载入默认值与历史参数"""
        ratio = aspect_of_size(size_str)
        if ratio in IMAGE_ASPECTS:
            self.aspect_image.set(ratio)
            self._on_image_aspect(ratio)

    def _save_generation_defaults(self):
        values = {
            "img_size": self.defaults_img_size.get(),
            "img_model": self.defaults_img_model.get(),
            "vid_seconds": self.defaults_vid_seconds.get(),
            "vid_aspect": self.defaults_vid_aspect.get(),
            "vid_model": self.defaults_vid_model.get(),
        }
        app_config.update(**values)
        self._apply_generation_defaults()
        self.settings_defaults_status.configure(text="✅ 默认值已保存并应用到生成页", text_color=GREEN_PILL_TX)
        self.status_var.set("✅ 生成默认值已保存")

    def _reset_generation_defaults(self):
        self.defaults_img_size.set("1024x768")
        self.defaults_img_model.set(MODEL_OPTIONS[0])
        self.defaults_vid_seconds.set("5")
        self.defaults_vid_aspect.set("16:9")
        self.defaults_vid_model.set(VIDEO_MODEL_OPTIONS[0])
        self.settings_defaults_status.configure(
            text="↺ 已恢复内置默认值，点击「保存默认值」生效", text_color=TEXT_SUB)

    # ---------- 设置页：网络模式 / 主题 ----------
    def _save_network_mode(self):
        label = self.settings_network_menu.get()
        code = NETWORK_MODE_CODES.get(label, "auto")
        app_config.update(network_mode=code)
        set_network_mode(code)
        self.settings_network_status.configure(
            text=f"当前：{NETWORK_MODE_LABELS.get(code, '自动')}", text_color=GREEN_PILL_TX)
        self.status_var.set(f"✅ 网络模式已切换：{NETWORK_MODE_LABELS.get(code, code)}")

    def _theme_status_text(self, code: str, auto_restart=None) -> str:
        """主题卡状态行文本：当前模式 + 是否已开启「切换后自动重启」"""
        if auto_restart is None:
            auto_restart = bool(app_config.load().get("theme_auto_restart", False))
        base = f"当前：{THEME_LABELS.get(code, '跟随系统')}"
        return f"{base} · 切换后自动重启" if auto_restart else base

    def _on_theme_restart_toggle(self):
        """勾选框实时持久化，并同步状态行文案"""
        enabled = bool(self.settings_theme_restart.get())
        app_config.update(theme_auto_restart=enabled)
        try:
            code = THEME_CODES.get(self.settings_theme_menu.get(), "system")
            self.settings_theme_status.configure(text=self._theme_status_text(code, enabled))
        except Exception:
            pass
        self.status_var.set("✅ 已开启：切换主题后自动重启程序"
                            if enabled else "主题切换改为原地换肤（不再自动重启）")

    def _save_theme(self):
        """保存并应用主题。

        原地换肤（默认）：apply_palette 一次调用内完成三件事，整窗原地换肤 ——
         ① ctk.set_appearance_mode  → CTk 原生控件自动重绘
         ② ui_theme.retheme_explicit → 显式 token 色按「旧值→新值」反查刷新
         ③ 订阅回调 on_theme_changed → Canvas 图元重绘

        为避免肉眼看到切换过程的中间帧（ctk.set 与 retheme 之间的过渡窗口
        包含数百次 widget.configure，单纯同步串行执行时画面会逐 widget 变
        色），整体期间临时 withdraw 窗口、update 强制刷新所有 widget、
        再 deiconify —— 用户视觉上只看到最终态，无中间态。

        自动重启（勾选「切换后自动重启程序」）：保存设置后销毁窗口并置
        _restart_requested，main() 外层循环以新主题重建整个窗口 —— 所有控件
        与 Canvas 图元都在新主题下全新构造，最彻底、绝无残留。
        """
        label = self.settings_theme_menu.get()
        code = THEME_CODES.get(label, "system")
        app_config.update(theme=code)
        if self.is_generating:
            self.settings_theme_status.configure(
                text="⚠ 生成进行中，完成后再应用主题", text_color=ui_theme.t.WARNING_TEXT)
            return

        # 自动重启分支：保存状态 → 请求重建 → 销毁窗口（main() 按 _restart_requested 循环）
        if getattr(self.settings_theme_restart, "get", lambda: False)():
            try:
                self._save_ui_state()
            except Exception:
                pass
            try:
                self.settings_theme_status.configure(
                    text=f"⏳ 正在重启，应用主题：{THEME_LABELS.get(code, code)}",
                    text_color=ui_theme.t.TEXT_SUB)
                self.root.update_idletasks()
            except Exception:
                pass
            self.status_var.set(
                f"✅ 主题已保存：{THEME_LABELS.get(code, code)}，正在重启程序…")
            self._restart_requested = True
            self.root.after(250, self.root.destroy)
            return

        # 原地换肤（视觉原子化 —— 用户看不到中间帧）
        # 先收口活动颜色帧链（卡片选中插值 / CTA 语义换色 / 提亮脉冲）：
        # 若不收口，它们会在 retheme 刷新后把旧调色板中间色又 configure 回去，
        # 而中间色不在「旧值→新值」映射表，换肤校验将违规（见 ui_anim.settle_all）。
        try:
            ui_anim.settle_all()
        except Exception:
            pass
        was_mapped = bool(self.root.state() != "withdrawn")
        if was_mapped:
            try:
                self.root.withdraw()
            except Exception:
                pass
        try:
            resolved = ui_theme.apply_palette(code)
            # 与 on_theme_changed 双保险：apply_palette 仅在 changed=True 时
            # 通过 _notify_subscribers 走一次，但「同一 mode 重复触发」（如
            # 黑暗模式下点选「深色」）会跳过那条链，导致显式 token 控件不刷新。
            # 这里主动再调一次 ensure_retheme，强制按当前 prev→current 重映射。
            try:
                ui_theme.retheme_explicit(self.root)
            except Exception:
                pass
            try:
                self.on_theme_changed()
            except Exception:
                pass
            try:
                self.root.update_idletasks()    # 把 ctk 内 + 我们 configure 队列一次性消化
            except Exception:
                pass
        finally:
            if was_mapped:
                try:
                    self.root.deiconify()
                    # 窗口淡回：重现瞬间 alpha 0.02→1（约 150ms），
                    # 给「消失-重现」的原子刷新加一层完成感；
                    # reduce_motion / alpha 不可用时直接落 1.0
                    ui_anim.fade_window_in(self.root, steps=5, step_ms=30)
                    self.root.update_idletasks()
                except Exception:
                    pass

        self.settings_theme_status.configure(
            text=f"✅ 已应用：{THEME_LABELS.get(code, code)}",
            text_color=ui_theme.t.GREEN_PILL_TX)
        self.status_var.set(
            f"✅ 主题已切换：{THEME_LABELS.get(code, code)}"
            f"（{'深色' if resolved == 'dark' else '浅色'}）")

    # ---------- 设置页：数据目录 ----------
    def _browse_data_dir(self):
        current = self.settings_data_dir_entry.get().strip() or history_store.get_data_dir()
        path = filedialog.askdirectory(title="选择文件/历史记录存储目录", initialdir=current)
        if path:
            self.settings_data_dir_entry.delete(0, tk.END)
            self.settings_data_dir_entry.insert(0, os.path.normpath(path))

    def _save_data_dir(self):
        path = self.settings_data_dir_entry.get().strip()
        if not path:
            messagebox.showwarning("提示", "请选择存储目录")
            return
        path = os.path.abspath(os.path.expanduser(path))
        try:
            app_config.update(data_dir=path)
            history_store.ensure_dirs()
            self.settings_data_dir_entry.delete(0, tk.END)
            self.settings_data_dir_entry.insert(0, path)
            self.settings_data_dir_status.configure(
                text=f"✅ 已保存：{path}", text_color=GREEN_PILL_TX)
            self.status_var.set(f"✅ 文件/历史记录存储目录已更新：{path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"更新存储目录失败：\n{e}")

    def _open_history_folder(self):
        history_store.ensure_dirs()
        try:
            os.startfile(history_store.get_data_dir())
            self.status_var.set("✅ 已打开历史数据文件夹")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹：\n{e}")

    # ============ 输入交互：占位符 / 自适应高度 / 事前防错 / 快捷键 ============
    def _init_prompt_box(self, box):
        """CTkTextbox 无原生 placeholder：用聚焦进出模拟，避免预填真实文案"""
        box.insert("1.0", self._prompt_placeholder)
        box.configure(text_color=TEXT_DISABLED)
        box.bind("<FocusIn>", lambda e, b=box: self._prompt_focus_in(b))
        box.bind("<FocusOut>", lambda e, b=box: self._prompt_focus_out(b))
        box.bind("<KeyRelease>", lambda e, b=box: self._prompt_changed(b))

    def _prompt_focus_in(self, box):
        if box.get("1.0", "end-1c").strip() == self._prompt_placeholder:
            box.delete("1.0", "end")
            box.configure(text_color=TEXT_MAIN)

    def _prompt_focus_out(self, box):
        if not box.get("1.0", "end-1c").strip():
            box.insert("1.0", self._prompt_placeholder)
            box.configure(text_color=TEXT_DISABLED)
        self._prompt_changed(box)

    def _prompt_text(self, box) -> str:
        """取真实提示词（占位符视为空）"""
        text = box.get("1.0", "end-1c").strip()
        return "" if text == self._prompt_placeholder else text

    def _prompt_changed(self, box):
        """一次做完三件事：字数统计 + 自适应高度 + CTA 可用态"""
        n = len(self._prompt_text(box))
        label = (self.prompt_count if box is self.prompt_image
                 else self.prompt_count_video)
        label.configure(text=f"{n} 字")
        self._autosize_prompt(box)
        self._refresh_cta_state()

    def _autosize_prompt(self, box, min_h: int = 96, max_h: int = 192):
        """按内容行数自适应：96px（4 行）起步，192px（8 行）封顶后内部滚动"""
        try:
            width = max(box.winfo_width(), 240)
            per_line = max(1, (width - 24) // 13)
            lines = 0
            for seg in box.get("1.0", "end-1c").split("\n"):
                lines += max(1, (len(seg) + per_line - 1) // per_line)
            height = min(max(min_h, lines * 20 + 16), max_h)
            if box.cget("height") != height:
                box.configure(height=height)
        except Exception:
            pass

    def _refresh_cta_state(self):
        """提示词为空时禁用 CTA：事前防错，替代点击后才弹窗校验"""
        if self.is_generating:
            return
        self.btn_gen_image.configure(
            state="normal" if self._prompt_text(self.prompt_image) else "disabled")
        self.btn_gen_video.configure(
            state="normal" if self._prompt_text(self.prompt_video) else "disabled")

    def _append_prompt(self, text: str):
        """示例提示词：追加而非覆盖用户已输入内容"""
        box = (self.prompt_image if self.current_page == PAGE_IMAGE
               else self.prompt_video)
        cur = self._prompt_text(box)
        self._write_prompt(box, f"{cur}，{text}" if cur else text)

    def _write_prompt(self, box, text: str):
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(text_color=TEXT_MAIN)
        self._prompt_changed(box)

    def _set_prompt(self, text: str):
        """兼容旧调用：等价于追加"""
        self._append_prompt(text)

    def _bind_shortcuts(self):
        """Ctrl+Enter 直接生成（文本框内绑定并 break，避免插入换行）"""
        self._bind_cta_press_feedback()
        def _fire(_event=None):
            mode = (self.current_page if self.current_page in (PAGE_IMAGE, PAGE_VIDEO)
                    else PAGE_IMAGE)
            self._start_generate(mode)
            return "break"

        for box in (self.prompt_image, self.prompt_video):
            box.bind("<Control-Return>", lambda e: _fire())
        self.root.bind_all("<Control-Return>", lambda e: _fire())

    # ============ CTA 按压反馈（反馈维度：按下加深 / 松开或移出复位） ============
    def _bind_cta_press_feedback(self):
        """在 CTkButton 内部 canvas/标签上追加绑定（其 bind() 自带 add 语义，
        不破坏库自身的 100ms 点击动画）；重复调用幂等"""
        if getattr(self, "_cta_feedback_bound", False):
            return
        self._cta_feedback_bound = True
        for btn in (self.btn_gen_image, self.btn_gen_video):
            btn.bind("<ButtonPress-1>", lambda e, b=btn: self._on_cta_press(b), add="+")
            btn.bind("<ButtonRelease-1>", lambda e, b=btn: self._on_cta_release(b), add="+")
            btn.bind("<Leave>", lambda e, b=btn: self._on_cta_leave(b), add="+")

    def _on_cta_press(self, btn):
        """按下即向暗加深一档（近线性、瞬时生效，等效规格书 press-in 80ms）。
        注意：CTkButton 悬停绘制用 hover_color 覆盖 fg_color，故两者同置为按压色"""
        if btn.cget("state") != "normal":
            return
        btn._press_fg = btn.cget("fg_color")
        btn._press_hover = btn.cget("hover_color")
        btn._press_text = btn.cget("text")
        pressed = ui_anim.mix_color(btn._press_fg, "#000000", 0.18)
        try:
            btn.configure(fg_color=pressed, hover_color=pressed)
        except Exception:
            btn._press_fg = btn._press_hover = None

    def _on_cta_release(self, btn):
        """松开复位；若命令已切换按钮状态（文本已变）则交给内部状态色处理"""
        base_fg = getattr(btn, "_press_fg", None)
        base_hover = getattr(btn, "_press_hover", base_fg)
        btn._press_fg = btn._press_hover = None
        if base_fg is None:
            return
        if (btn.cget("text") != getattr(btn, "_press_text", "")
                or btn.cget("state") != "normal"):
            return
        try:
            btn.configure(fg_color=base_fg, hover_color=base_hover)
        except Exception:
            pass

    def _on_cta_leave(self, btn):
        """按住不放移出按钮：同样复位，避免颜色卡死"""
        base_fg = getattr(btn, "_press_fg", None)
        base_hover = getattr(btn, "_press_hover", base_fg)
        btn._press_fg = btn._press_hover = None
        if base_fg is None or btn.cget("state") != "normal":
            return
        try:
            btn.configure(fg_color=base_fg, hover_color=base_hover)
        except Exception:
            pass

    def _shake_widget(self, widget, cycles: int = 3, offset: int = 4,
                      step_ms: int = 50):
        """校验失败的就地抖动：±4px 衰减振荡，≤300ms，替代模态弹窗打断。

        幅值按 0.66 逐「来回」指数衰减（阻尼正弦的方波近似），
        区别于等幅方波——收敛感传达「可恢复的提示」而非「系统报错」。
        """
        try:
            base = widget.pack_info().get("padx", 0)
        except Exception:
            return

        def _run(i: int = 0):
            if i >= cycles * 2:
                try:
                    widget.pack_configure(padx=base)
                except Exception:
                    pass
                return
            amp = offset * (0.66 ** (i // 2))
            try:
                widget.pack_configure(padx=base + (amp if i % 2 == 0 else -amp))
            except Exception:
                return
            widget.after(step_ms, lambda: _run(i + 1))

        _run()

    def _flash_button(self, button, temp_text: str, restore_text: str,
                      hold_ms: int = 1500):
        """操作反馈就地呈现：按钮文案临时替换，1500ms 后还原"""
        button.configure(text=temp_text, text_color=SUCCESS_TEXT)
        button.after(hold_ms, lambda: button.configure(
            text=restore_text, text_color=TEXT_MAIN))

    def _elapsed_text(self) -> str:
        """耗时文本：结果条展示，替代无从判断的漫长等待"""
        if not self._gen_started_at:
            return "-"
        return f"{time.time() - self._gen_started_at:.1f}s"

    def _abort_generation(self):
        """中止生成：线程不可强杀，置标志后丢弃回传结果并恢复界面"""
        if not self.is_generating:
            return
        self._cancel_requested = True
        self.btn_gen_image.configure(state="disabled")
        self.btn_gen_video.configure(state="disabled")
        self.status_var.set("⏹ 正在中止，等待当前请求返回后丢弃结果")

    def _on_aborted(self):
        self._set_generating(False)
        self._skeleton_on = False
        self.image_canvas.delete("all")
        self._set_result("idle", "已中止生成")
        self.status_var.set("⏹ 已中止，结果已丢弃")

    # ============ 结果区状态机：四态收敛为一处 ============
    def _set_result(self, state: str, summary: str, detail: str = None,
                    animate: bool = True):
        """结果条四态：idle / loading / success / error

        summary 单行（≤40 字）在主界面展示，detail 全文收进「详情」弹层，
        避免 131 字符的 URL 霸占主界面 3 行。

        信息优先：图标字符、文本与按钮状态即时落定（不依赖动画完成即可读）；
        颜色语义随后以 180ms 插值过渡到目标态。animate=False（主题重绘路径）
        与「减弱动态效果」开启时直接落终态。
        """
        self._result_state = state
        self._result_summary = summary
        self._result_detail = detail or summary
        self._cost_token += 1  # 任何状态更新都打断进行中的耗时计数演绎
        # 状态色实时读取 token（而非快照），主题切换后可直接重绘
        styles = {
            "idle": ("○", ui_theme.t.TEXT_SUB),
            "loading": ("◌", ui_theme.t.ACCENT),
            "success": ("✓", ui_theme.t.SUCCESS_TEXT),
            "error": ("!", ui_theme.t.ERROR_TEXT),
        }
        icon, color = styles.get(state, styles["idle"])
        # 信息先行：文本与图标字符立即就位（文字色由下方插值接管）
        self.result_icon.configure(text=icon)
        self.result_text.configure(
            text=summary if len(summary) <= 40 else summary[:38] + "…")
        self.btn_detail.configure(state="normal" if detail else "disabled")
        self._update_action_buttons()
        # 颜色语义过渡
        self._tint_to(
            icon_color=color,
            text_color=color if state != "idle" else TEXT_SUB,
            bar_color=ERROR_BG if state == "error" else FILL,
            animate=animate,
        )

    # ---- 结果条颜色插值（token 打断制，6 帧 × 30ms ≈ 180ms） ----
    def _tint_to(self, icon_color: str, text_color: str, bar_color: str,
                 animate: bool = True):
        token = self._result_tint_token + 1
        self._result_tint_token = token
        try:
            c_icon = self.result_icon.cget("text_color")
            c_text = self.result_text.cget("text_color")
            c_bar = self.result_bar.cget("fg_color")
        except Exception:
            return
        if (c_icon == icon_color and c_text == text_color and c_bar == bar_color):
            return  # 语义未变（如视频轮询 loading→loading），仅文本刷新过
        if not animate or ui_anim.reduce_motion():
            self._apply_result_colors(icon_color, text_color, bar_color)
            return
        n, step_ms = 6, 30

        def tick(i: int = 0):
            if token != self._result_tint_token:
                return
            t = ui_anim.ease_in_out((i + 1) / n)
            self._apply_result_colors(
                ui_anim.mix_color(c_icon, icon_color, t),
                ui_anim.mix_color(c_text, text_color, t),
                ui_anim.mix_color(c_bar, bar_color, t))
            if i + 1 < n:
                self.root.after(step_ms, lambda: tick(i + 1))

        tick(0)

    def _apply_result_colors(self, icon_color: str, text_color: str,
                             bar_color: str):
        try:
            self.result_icon.configure(text_color=icon_color)
            self.result_text.configure(text_color=text_color)
            self.result_bar.configure(fg_color=bar_color)
        except Exception:
            self._result_tint_token += 1  # 控件异常（重建中）→ 停止后续帧

    # ---- 成功耗时计数演绎（提升体验）：0 → 真实秒，600ms，可被任何状态更新打断 ----
    def _count_up_result(self, prefix: str, real_sec: float):
        total = max(1, int(round(real_sec)))
        token = self._cost_token + 1
        self._cost_token = token
        if total <= 2:  # 秒数太少时直接展示终值，不做无意义的快速滚动
            return
        n, step_ms = 10, 60
        last_text = None

        def tick(i: int = 0):
            nonlocal last_text
            if token != self._cost_token:
                return
            try:
                cur = self.result_text.cget("text")
            except Exception:
                return
            # 中途被 _set_result 覆盖（如图片下载完成后再报「已就绪」）→ 让位
            if last_text is not None and cur != last_text:
                return
            if i >= n:
                self.result_text.configure(text=f"{prefix} · {total}s")
                return
            v = int(total * ui_anim.ease_in_out((i + 1) / n))
            last_text = f"{prefix} · {v}s"
            self.result_text.configure(text=last_text)
            self.root.after(step_ms, lambda: tick(i + 1))

        tick(0)

    # ---- 「已等待 Xs」真实计时（降低等待感）：生成中每秒刷新，进度确定后自停 ----
    def _start_wait_tick(self):
        """结果条进入 loading 后启动；每秒把「 · 已等待 Ns」拼到 base 文案后"""
        self._wait_token += 1
        tok = self._wait_token
        self._wait_tick(0, tok)

    def _wait_tick(self, i: int, tok: int):
        if tok != self._wait_token:
            return
        if not self.is_generating or not self._gen_started_at:
            return
        if self._result_state != "loading":
            return
        if getattr(self, "_progress_determinate", False):
            return  # 视频拿到确定进度 → 轮询文案接管，不再叠加计时
        base = getattr(self, "_wait_base_text", None)
        if base:
            sec = max(0, int(time.time() - self._gen_started_at))
            text = f"{base} · 已等待 {sec}s"
            if len(text) > 40:
                text = text[:38] + "…"
            try:
                self.result_text.configure(text=text)
            except Exception:
                return
        self.root.after(1000, lambda: self._wait_tick(i + 1, tok))

    def _stop_wait_tick(self):
        """生成结束 / 中止：使已调度链失效（幂等）"""
        self._wait_token += 1

    def _show_result_detail(self):
        """结果详情弹层：URL / 参数 / 任务ID 用等宽字体，主界面不铺全文"""
        if not self._result_detail:
            return
        win = ctk.CTkToplevel(self.root)
        win.title("结果详情")
        win.geometry("640x420")
        try:
            win.after(200, win.grab_set)
        except Exception:
            pass
        box = ctk.CTkTextbox(
            win, corner_radius=R_CTRL, font=self.f_mono, fg_color=FIELD_BG,
            border_width=1, border_color=FIELD_BORDER, text_color=TEXT_MAIN,
            wrap="word",
        )
        box.pack(fill=tk.BOTH, expand=True, padx=CARD_PAD, pady=(CARD_PAD, S_SM))
        box.insert("1.0", self._result_detail)
        box.configure(state="disabled")

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill=tk.X, padx=CARD_PAD, pady=(0, CARD_PAD))
        ctk.CTkButton(
            bar, text="复制全文", height=H_CHIP, corner_radius=R_PILL,
            font=self.f_body, fg_color=FILL, hover_color=FILL_HOVER,
            text_color=TEXT_MAIN,
            command=lambda: self._copy_text(self._result_detail),
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            bar, text="关闭", height=H_CHIP, corner_radius=R_PILL,
            font=self.f_body, fg_color=FILL, hover_color=FILL_HOVER,
            text_color=TEXT_MAIN,
            command=lambda: ui_anim.fade_window_out(win),
        ).pack(side=tk.RIGHT)

        # 弹层淡入：内容已就位后 alpha 0→1（约 180ms），降低「弹出」突兀感
        ui_anim.fade_window_in(win)

    def _copy_text(self, text: str):
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("✅ 已复制到剪贴板")

    def _retry_generation(self):
        """失败态就地重试：沿用上次的模式与输入参数"""
        self._start_generate(self.last_mode or PAGE_IMAGE)

    # ============ 画布骨架屏：生成中的就地反馈 ============
    def _draw_canvas_skeleton(self, title: str = "正在生成…"):
        """生成中在画布中央画骨架占位，替代 10~30 秒的空白等待"""
        self.current_image = None
        self._canvas_hint_text = None
        self.image_canvas.delete("all")
        w = self.image_canvas.winfo_width() or 480
        h = self.image_canvas.winfo_height() or 320
        cx, cy = w // 2, h // 2
        bw = min(w - 96, 320)
        for i in range(3):
            x0, y0 = cx - bw // 2, cy - 40 + i * 24
            self.image_canvas.create_rectangle(
                x0, y0, x0 + bw, y0 + 12, fill=ui_theme.t.FILL_HOVER,
                outline="", tags=("skel-bar",),
            )
        self.image_canvas.create_text(
            cx, cy + 56, text=title, fill=ui_theme.t.TEXT_SUB,
            font=(ui_theme.FONT_FAMILY, 12),
        )
        self._skel_title = title  # 供主题重绘按原语义重建骨架（历史下载等非生成场景）
        self._skeleton_on = True
        gen = getattr(self, "_skel_gen", 0) + 1
        self._skel_gen = gen  # 代数守卫：主题重绘等路径先置 False 再重开时，旧循环自动失效
        self._start_skeleton_shimmer(gen)

    # ---- 骨架微光扫描（降低等待感）：单向高光带 1.8s/周期 30fps，替代两档硬闪 ----
    def _start_skeleton_shimmer(self, gen: int):
        if ui_anim.reduce_motion():
            return  # 减弱动态效果：骨架保持静态即可
        try:
            w = self.image_canvas.winfo_width() or 480
            h = self.image_canvas.winfo_height() or 320
            cx, cy = w // 2, h // 2
            bw = min(w - 96, 320)
        except Exception:
            return
        rows = [cy - 40 + i * 24 for i in range(3)]
        glow_w = max(int(bw * 0.35), 40)
        x_lo = cx - bw // 2 - glow_w
        x_hi = cx + bw // 2
        glow = self._skeleton_glow_color()

        def tick(step: int = 0):
            if not self._skeleton_on or gen != self._skel_gen:
                return
            try:
                self.image_canvas.delete("skel-glow")
                if not self._skeleton_on:
                    return
                t = ui_anim.ease_in_out((step % 54) / 54.0)  # 54 帧 × 33ms ≈ 1.8s
                x = x_lo + (x_hi - x_lo) * t
                for y in rows:
                    self.image_canvas.create_rectangle(
                        x, y, x + glow_w, y + 12, fill=glow, outline="",
                        tags=("skel-glow",))
            except Exception:
                pass
            self.root.after(33, lambda: tick(step + 1))

        tick()

    def _skeleton_glow_color(self) -> str:
        """高光 = FILL_HOVER 向白偏移（按明度自适应），深/浅主题下均可辨"""
        try:
            base = ui_theme.t.FILL_HOVER
            lum = ui_anim.luminance(base)
            return ui_anim.mix_color(base, "#ffffff", 0.55 if lum < 0.35 else 0.45)
        except Exception:
            return "#ffffff"

    # ===================== 事件处理 =====================
    def _upload_to_image_host(self, path: str) -> str:
        """本地参考图 → S.EE 图床公网直链（视频接口仅支持公网 URL）"""
        return upload_to_image_host(path)

    def _set_prompt(self, prompt: str):
        """填充图片提示词"""
        self.prompt_image.delete("1.0", "end")
        self.prompt_image.insert("1.0", prompt)

    def _select_tab(self, name: str):
        """兼容旧调用：把 TAB 常量名映射为导航页切换（历史载入参数时跳页用）"""
        mapping = {PAGE_IMAGE: "image", PAGE_VIDEO: "video"}
        key = mapping.get(name, name)
        self._select_page(key)

    def _reset_result_state(self):
        """清空当前结果状态（回到「查看本次生成结果」模式）"""
        self.current_image_url = None
        self.current_image_data = None
        self.current_image = None
        self.current_video_url = None
        self.current_video_data = None
        self.video_id = None
        self.active_record = None
        if self.history_panel is not None:
            self.history_panel.clear_selection()
        if self.gallery_grid is not None:
            self.gallery_grid.clear_selection()
        self.preview_title.configure(text="生成结果")
        self.preview_badge.configure(text="")
        self._skeleton_on = False
        self.image_canvas.delete("all")
        self._set_result("idle", "尚未生成")

    def _update_action_buttons(self):
        """按结果类型刷新操作条：播放 / 重试按类型条件渲染，不做禁用占位"""
        rec = self.active_record

        def _show(btn, visible):
            """按类型显隐：用 winfo_manager 判断，避免窗口未映射时误判"""
            managed = btn.winfo_manager() == "pack"
            if visible and not managed:
                btn.pack(side=tk.LEFT, padx=(0, S_SM), pady=S_SM,
                        before=self.btn_open)
            elif not visible and managed:
                btn.pack_forget()

        is_video = ((rec or {}).get("type") == "video" if rec is not None
                    else bool(self.current_video_url))
        _show(self.btn_play, is_video)
        _show(self.btn_retry, self._result_state == "error")

        if rec is not None:
            url = rec.get("result_url")
            has_local = bool(rec.get("media_path")) and os.path.exists(rec["media_path"])
            self.btn_copy_url.configure(state="normal" if url else "disabled")
            self.btn_open.configure(state="normal" if url else "disabled")
            self.btn_save.configure(state="normal" if (url or has_local) else "disabled")
            self.btn_play.configure(
                state="normal" if (rec.get("type") == "video" and url) else "disabled")
            return

        url = self.current_video_url or self.current_image_url
        self.btn_copy_url.configure(state="normal" if url else "disabled")
        self.btn_open.configure(state="normal" if url else "disabled")
        self.btn_save.configure(
            state="normal" if (self.current_image_data or self.current_video_url) else "disabled")
        self.btn_play.configure(state="normal" if self.current_video_url else "disabled")

    def _current_url(self):
        """当前操作对象的结果 URL（历史记录优先）"""
        if self.active_record is not None:
            return self.active_record.get("result_url")
        return self.current_video_url or self.current_image_url

    def _start_generate(self, mode: str):
        """开始生成（后台线程执行）"""
        if self.generator is None:
            messagebox.showerror("错误", "API Key 未配置，无法生成。\n请检查程序目录下的 .env 文件。")
            return
        if self.is_generating:
            messagebox.showwarning("提示", "已有生成任务进行中，请等待完成")
            return

        self.last_mode = mode

        if mode == "image":
            prompt = self._prompt_text(self.prompt_image)
            if not prompt:
                # 正常路径下 CTA 已禁用，此处仅兜底：抖动 + 状态栏提示，不打断流程
                self._shake_widget(self.btn_gen_image)
                self.status_var.set("请先输入提示词")
                return
            refs = self.ref_image.get_items()
            params = {
                "prompt": prompt,
                "images": refs if refs else None,
                "size": self.size_image.get(),
                "model": self.model_image.get(),
            }
            thread = threading.Thread(
                target=self._image_worker, args=(params,), daemon=True
            )
        else:  # video
            prompt = self._prompt_text(self.prompt_video)
            if not prompt:
                self._shake_widget(self.btn_gen_video)
                self.status_var.set("请先输入提示词")
                return
            refs = self.ref_video.get_items()
            params = {
                "prompt": prompt,
                "images": refs if refs else None,
                "seconds": self.video_seconds.get(),
                "aspect_ratio": self.aspect_video.get(),
                "model": self.model_video.get(),
            }
            thread = threading.Thread(
                target=self._video_worker, args=(params,), daemon=True
            )

        # 参数校验通过后再清空预览（避免空提示词误清掉正在查看的历史记录）
        self._reset_result_state()

        # 记录本次输入参数，生成结束后（成功或失败）写入历史
        self._pending_params = dict(params)
        self._pending_record_id = None

        self._gen_started_at = time.time()
        self._set_generating(True)
        thread.start()

    # ---------- 图片生成（同步） ----------
    def _image_worker(self, params: dict):
        """后台线程：调用 API 生成图片"""
        try:
            self.root.after(0, lambda: self.status_var.set("⏳ 正在生成图片，请稍候..."))
            image_url = self.generator.generate_images(**params)
            if self._cancel_requested:
                self.root.after(0, self._on_aborted)
                return
            self.root.after(0, lambda: self._on_image_success(image_url))
        except Exception as e:
            # 注意：必须在 except 块内立刻拼好消息再传给 UI 线程——
            # Python 的 `except ... as e` 在块结束时会删除 e，
            # 若 lambda 延迟引用 e 会得到 NameError 或丢失真实错误信息
            msg = f"[{type(e).__name__}] {e}"
            self.root.after(0, lambda: self._on_generate_error("生成图片失败", msg))

    def _clear_history_selection(self):
        """退出历史查看模式，回到「查看本次生成结果」（不清空结果本身）"""
        if self.active_record is None:
            return
        self.active_record = None
        if self.history_panel is not None:
            self.history_panel.clear_selection()
        self.preview_title.configure(text="生成结果预览")

    def _on_image_success(self, image_url: str):
        """图片生成成功回调"""
        self._set_generating(False)
        self._clear_history_selection()
        self.current_image_url = image_url
        real_sec = time.time() - (self._gen_started_at or time.time())
        cost = f"{real_sec:.1f}s"
        self._set_result(
            "success", f"已生成 · {cost}",
            f"✅ 图片生成成功\n耗时: {cost}\n图片 URL: {image_url}",
        )
        self._count_up_result("已生成", real_sec)
        self.status_var.set("📥 正在下载图片…")
        self.preview_badge.configure(text="图片")
        # 先写历史（含提示词与参数），下载完成后再补本地缓存
        self._pending_record_id = self._record_generation("image", image_url)
        # 下载并显示
        threading.Thread(target=self._download_image_worker, args=(image_url,), daemon=True).start()

    def _download_image_worker(self, url: str):
        """后台下载图片"""
        try:
            self.root.after(0, lambda: self.status_var.set("📥 正在下载图片..."))
            resp = adaptive_request("GET", url, timeout=60)
            resp.raise_for_status()
            img_data = resp.content
            self.root.after(0, lambda: self._on_image_downloaded(img_data))
        except Exception as e:
            # 必须在 except 块内立刻拼好消息：`except ... as e` 结束时会删除 e，
            # lambda 延迟引用会得到 NameError
            msg = f"⚠️ 图片下载失败: [{type(e).__name__}] {e}"
            self.root.after(0, lambda: self.status_var.set(msg))

    def _on_image_downloaded(self, img_data: bytes):
        """图片下载完成回调"""
        self.current_image_data = img_data
        try:
            img = Image.open(BytesIO(img_data))
            self.current_image = img
            self._display_image(img)
            self.status_var.set("图片已就绪，可保存")
            self._set_result("success", f"图片已就绪 · {self._elapsed_text()}",
                             self._result_detail)
        except Exception as e:
            self.status_var.set(f"⚠️ 图片解析失败: {e}")
        self._update_action_buttons()
        self._cache_image_to_history(img_data)

    # ---------- 历史记录写入 ----------
    def _record_generation(self, kind: str, result_url=None, status: str = "success",
                           error: str = None, meta: dict = None):
        """把本次生成（成功或失败）连同输入参数写入历史，返回记录 id"""
        p = getattr(self, "_pending_params", None) or {}
        if not p:
            return None

        params = {}
        for key in ("model", "size", "seconds", "aspect_ratio"):
            if p.get(key):
                params[key] = p[key]
        if kind == "video":
            params.setdefault("size", "720P")

        refs = p.get("images") or []
        prompt = p.get("prompt", "")
        self._pending_params = None

        try:
            rec = history_store.add_record(
                kind, prompt, params=params, refs=refs,
                result_url=result_url, status=status,
                meta=meta or {}, error=error,
            )
        except Exception as e:
            print(f"[history] 写入历史失败: {type(e).__name__}: {e}")
            return None

        self._refresh_history()
        return rec.get("id")

    def _cache_image_to_history(self, img_data: bytes):
        """把生成好的图片缓存到本地，供历史记录离线查看缩略图"""
        rid = getattr(self, "_pending_record_id", None)
        if not rid:
            return
        self._pending_record_id = None

        def _worker():
            try:
                media, thumb = history_store.save_image_asset(img_data, rid)
                history_store.update_record(rid, media_path=media, thumb_path=thumb)
            except Exception as e:
                print(f"[history] 缓存图片失败: {type(e).__name__}: {e}")
            self.root.after(0, self._refresh_history)

        threading.Thread(target=_worker, daemon=True).start()

    def _refresh_history(self):
        if self.history_panel is not None:
            try:
                self.history_panel.refresh()
            except Exception as e:
                print(f"[history] 刷新列表失败: {type(e).__name__}: {e}")

    def _display_image(self, img: Image.Image):
        self._skeleton_on = False  # 统一直出路径停 shimmer（历史缓存/下载完成等）
        self.current_image = img
        self._resize_preview()

    def _resize_preview(self, event=None):
        if not hasattr(self, "current_image") or self.current_image is None:
            return
        canvas_w = self.image_canvas.winfo_width()
        canvas_h = self.image_canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1:
            return

        img = self.current_image.copy()
        img_w, img_h = img.size
        scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w = max(int(img_w * scale), 1)
        new_h = max(int(img_h * scale), 1)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        photo = TkPhotoImage(img)

        self.image_canvas.delete("all")
        self.image_canvas.create_image(
            canvas_w // 2, canvas_h // 2, image=photo, anchor=tk.CENTER
        )
        self.image_canvas.image = photo

    # ---------- 视频生成（异步轮询） ----------
    def _video_worker(self, params: dict):
        """后台线程：提交视频任务（含队列满自动重试）并轮询"""
        try:
            self.root.after(0, lambda: self.status_var.set("⏳ 正在提交视频任务..."))
            self._set_result_safe("loading", "正在提交视频任务…")
            result = self._submit_with_retry(params)
            if self._cancel_requested:
                self.root.after(0, self._on_aborted)
                return
            video_id = result.get("video_id")
            self.video_id = video_id
            if not video_id:
                raise Exception(f"服务端未返回 video_id: {result}")

            self.root.after(0, lambda: self.status_var.set("🎬 视频生成中，请耐心等待..."))
            self._set_result_safe(
                "loading", "视频任务已提交，生成中（通常 1-3 分钟）",
                f"✅ 视频任务已提交\n任务ID: {video_id}\n正在生成中（通常 1-3 分钟）...",
            )

            final = self.video_generator.wait_video(
                video_id, on_progress=self._on_video_progress,
                model_name=params.get("model"),
            )
            if self._cancel_requested:
                self.root.after(0, self._on_aborted)
                return
            video_url = final.get("url")
            if not video_url:
                raise Exception(f"任务完成但未返回视频 URL: {final}")
            self.root.after(0, lambda: self._on_video_success(video_url, final))
        except Exception as e:
            # 必须在 except 块内立刻拼好消息：`except ... as e` 在块结束时会删除 e，
            # lambda 延迟引用会得到 NameError 或丢失真实错误信息
            msg = f"[{type(e).__name__}] {e}"
            self.root.after(0, lambda: self._on_generate_error("生成视频失败", msg))

    def _submit_with_retry(self, params: dict, max_retries: int = 3):
        """提交视频任务；队列满(503)/速率限制(429)时自动退避重试，其他错误直接抛出"""
        for attempt in range(1, max_retries + 1):
            try:
                return self.video_generator.submit_video(**params)
            except RETRYABLE_VIDEO_ERRORS as e:
                if attempt >= max_retries:
                    raise
                if isinstance(e, VideoRateLimitError):
                    wait_sec = 60  # 平台限制：视频任务每分钟 1 个，等满一个窗口
                    reason = "触发速率限制（每分钟仅允许 1 个视频任务）"
                else:
                    wait_sec = 10 * attempt
                    reason = "服务端视频队列已满（免费通道较拥挤）"
                self.root.after(0, lambda w=wait_sec, n=attempt + 1, r=reason:
                                self.status_var.set(f"⏳ {r}，{w} 秒后第 {n} 次重试..."))
                self._set_result_safe(
                    "loading", f"{reason}，{wait_sec}s 后重试",
                    f"⏳ {reason}。\n"
                    f"第 {attempt}/{max_retries} 次提交失败，{wait_sec} 秒后自动重试..."
                )
                time.sleep(wait_sec)
                if self._cancel_requested:
                    return {}

    def _set_result_safe(self, state: str, summary: str, detail: str = None):
        """后台线程 → UI 线程的结果条更新"""
        self.root.after(0, lambda: self._set_result(state, summary, detail))

    def _on_video_progress(self, status: str, progress, result: dict):
        """轮询进度回调（后台线程中调用，需转发到 UI 线程）"""
        self.root.after(0, lambda: self._update_video_progress(status, progress, result))

    def _update_video_progress(self, status: str, progress, result: dict):
        status_map = {
            "queued": "排队中",
            "pending": "排队中",
            "in_progress": "生成中",
            "running": "生成中",
            "processing": "处理中",
            "completed": "已完成",
            "succeeded": "已完成",
            "success": "已完成",
            "failed": "失败",
            "error": "失败",
            "canceled": "已取消",
            "cancelled": "已取消",
            "rate_limited": "查询被限速·自动等待中",
            "query_retry": "服务端排队注册中·自动等待",
        }
        cn = status_map.get(str(status).lower(), str(status))
        self.status_var.set(f"🎬 视频{cn}... 进度: {progress}%")
        pct = None
        try:
            pct = float(progress) / 100.0
        except (TypeError, ValueError):
            pct = None
        if pct is not None:
            self._progress_determinate = True
            self.progress_bar.set(max(0.02, min(pct, 1.0)))
        self._set_result(
            "loading", f"视频{cn} · 进度 {progress}%",
            f"🎬 视频任务状态: {cn}\n任务ID: {self.video_id or '-'}\n"
            f"进度: {progress}%\n请耐心等待生成完成...",
        )

    def _on_video_success(self, video_url: str, final: dict):
        """视频生成成功回调"""
        self._set_generating(False)
        self._clear_history_selection()
        self.current_video_url = video_url
        seconds = final.get("seconds", "-")
        size = final.get("size", "-")
        quality = final.get("quality", "standard")
        real_sec = time.time() - (self._gen_started_at or time.time())
        cost = f"{real_sec:.1f}s"
        self._set_result(
            "success", f"视频生成成功 · {cost}",
            f"✅ 视频生成成功\n耗时: {cost}\n视频 URL: {video_url}\n"
            f"时长: {seconds} 秒 | 分辨率: {size} | 质量: {quality}",
        )
        self._count_up_result("视频生成成功", real_sec)
        self.status_var.set("视频生成成功，可播放或保存")
        self.preview_badge.configure(text="视频")
        self._record_generation(
            "video", video_url,
            meta={"seconds": seconds, "size": size, "quality": quality,
                  "video_id": self.video_id},
        )
        self._draw_canvas_hint("🎬 视频已生成\n点击 ▶ 播放 查看，或保存到本地")

    # ---------- 通用错误回调 ----------
    def _on_generate_error(self, title: str, error_msg: str):
        """失败反馈就地呈现：错误条 + 重试按钮，不再用模态弹窗打断流程"""
        self._set_generating(False)
        self._skeleton_on = False
        self.image_canvas.delete("all")
        self._draw_canvas_hint("生成失败\n可在结果条「详情」查看原因，或点「重试」")
        self._set_result("error", title, f"❌ {title}\n{error_msg}")
        self.status_var.set(f"❌ {title}")
        # 失败也记一笔，方便回看提示词/参数并「载入参数」重试
        self._record_generation(
            self.last_mode or "image", None, status="failed", error=error_msg,
            meta={"video_id": self.video_id} if self.last_mode == "video" else {},
        )

    def _draw_canvas_hint(self, text: str):
        """在预览画布中央绘制提示文字（用于视频/缓存缺失/失败场景）"""
        self.current_image = None
        self._skeleton_on = False
        self._canvas_hint_text = text       # 记录以便主题切换后重绘
        self.image_canvas.delete("all")
        w = self.image_canvas.winfo_width() or 400
        h = self.image_canvas.winfo_height() or 260
        self.image_canvas.create_text(
            w // 2, h // 2, text=text, fill=ui_theme.t.TEXT_SUB,
            font=(ui_theme.FONT_FAMILY, 12), justify=tk.CENTER,
        )

    # ---------- 生成状态 ----------
    def _tint_cta(self, fg_color: str, text_color: str):
        """CTA 双按钮在「生成中 / 可生成」语义间 180ms 原位换色。

        文本/命令/state 已在调用处即时落定，这里只做颜色插值，
        保证已对准光标的按钮不漂移；新状态到来自动打断旧链。
        """
        for btn in (self.btn_gen_image, self.btn_gen_video):
            ui_anim.blend_configure(
                btn, {"fg_color": fg_color, "text_color": text_color},
                duration_ms=ui_anim.T_STATE_MS)

    def _set_generating(self, is_generating: bool):
        """生成中：CTA 变为中止入口、画布切骨架屏；结束后恢复并校验可用态"""
        self.is_generating = is_generating
        if is_generating:
            self._cancel_requested = False
            self._progress_determinate = False
            self.progress_bar.set(0.08)
            for btn in (self.btn_gen_image, self.btn_gen_video):
                # 信息先行（文本/命令/悬停色即时），颜色由下方插值接管
                btn.configure(state="normal", text="■ 中止生成",
                              command=self._abort_generation,
                              hover_color=FILL_HOVER)
            self._tint_cta(FILL, TEXT_MAIN)
            self._draw_canvas_skeleton(
                "正在生成图片…" if self.last_mode == "image"
                else "正在提交视频任务…")
            # 结果条随即进入 loading 语义，并启动「已等待」真实计时
            # （视频首次轮询拿到确定进度后 _wait_tick 自动让位）
            base = ("正在生成图片…" if self.last_mode == "image"
                    else "正在提交视频任务…")
            self._wait_base_text = base
            self._set_result("loading", base)
            self._start_wait_tick()
        else:
            self.progress_bar.set(0)
            self._skeleton_on = False
            self._stop_wait_tick()
            self.btn_gen_image.configure(
                text="开始生成图片（Ctrl+Enter）",
                command=lambda: self._start_generate("image"),
                hover_color=ACCENT_HOVER)
            self.btn_gen_video.configure(
                text="开始生成视频（Ctrl+Enter）",
                command=lambda: self._start_generate("video"),
                hover_color=ACCENT_HOVER)
            self._tint_cta(ACCENT, ON_ACCENT)
            self._refresh_cta_state()

    def _animate_progress(self):
        """不确定进度的往返脉冲动画（替代 ttk 的 indeterminate 模式）

        视频任务拿到真实进度后改为确定态，不再与轮询进度互相打架。
        """
        if self.is_generating and not getattr(self, "_progress_determinate", False):
            pos = float(self.progress_bar.get())
            if not hasattr(self, "_pulse_dir"):
                self._pulse_dir = 1
            pos += 0.035 * self._pulse_dir
            if pos >= 0.95:
                pos = 0.95
                self._pulse_dir = -1
            elif pos <= 0.05:
                pos = 0.05
                self._pulse_dir = 1
            self.progress_bar.set(pos)
        else:
            self._pulse_dir = 1
        self.root.after(50, self._animate_progress)

    def _set_result_info(self, text: str):
        """兼容旧调用：整段文本作为详情，首行作为结果条摘要"""
        body = text or ""
        state = "idle"
        if body.startswith("❌"):
            state = "error"
        elif body.startswith(("✅", "✓")):
            state = "success"
        elif body.startswith(("⏳", "🎬")):
            state = "loading"
        summary = body.split("\n", 1)[0].strip() or "尚未生成"
        self._set_result(state, summary, body)

    # ---------- 历史记录查看 ----------
    def _on_history_select(self, rec):
        """历史面板选中某条记录：在右侧预览区展示提示词、参数与结果"""
        if rec is None:
            self.active_record = None
            self.current_image = None
            self.current_image_data = None
            self.current_image_url = None
            self.current_video_url = None
            self.image_canvas.delete("all")
            self.preview_title.configure(text="生成结果")
            self.preview_badge.configure(text="历史记录")
            self._set_result("idle", "未选择记录")
            return

        self.active_record = rec
        self.preview_title.configure(text="历史记录详情")
        self.current_image_data = None
        self.current_image_url = None
        self.current_video_url = None
        kind = "视频" if rec.get("type") == "video" else "图片"
        failed = rec.get("status") == "failed"
        self._set_result(
            "error" if failed else "success",
            f"{kind}记录 · {'失败' if failed else '成功'}",
            self._format_record_detail(rec),
        )

        url = rec.get("result_url")
        if rec.get("type") == "video":
            self.current_video_url = url
            self.preview_badge.configure(text="历史 · 视频")
            self._draw_canvas_hint(
                "🎬 视频记录\n点击 ▶ 播放 在线观看，或「保存」下载到本地"
            )
        else:
            self.current_image_url = url
            self.preview_badge.configure(text="历史 · 图片")
            local = rec.get("media_path")
            if local and os.path.exists(local):
                try:
                    # with + copy：避免 PIL 持有文件句柄（Windows 下会锁住缓存文件）
                    with Image.open(local) as im:
                        img = im.copy()
                    self._display_image(img)
                except Exception as e:
                    self._draw_canvas_hint(f"🖼 本地缓存读取失败\n{e}")
            elif url:
                # 下载期复用骨架 shimmer（与生成等待同一叙事语言），完成即直出图片
                self._draw_canvas_skeleton("正在加载历史图片…")
                threading.Thread(
                    target=self._download_history_image, args=(rec,), daemon=True
                ).start()
            else:
                self._draw_canvas_hint("🖼 该记录没有可用的图片")

        self._update_action_buttons()

    def _download_history_image(self, rec: dict):
        """历史图片本地缓存缺失时，后台重新下载并回写缓存"""
        url = rec.get("result_url")
        if not url:
            return
        try:
            resp = adaptive_request("GET", url, timeout=60)
            resp.raise_for_status()
            img_data = resp.content
        except Exception as e:
            # 必须在 except 块内立刻拼好消息：`except ... as e` 结束时会删除 e，
            # lambda 延迟引用会得到 NameError
            msg = f"⚠️ 历史图片加载失败: [{type(e).__name__}] {e}"
            self.root.after(0, lambda: self.status_var.set(msg))
            return

        def _done():
            # 期间用户可能已切换到别的记录
            if self.active_record is None or self.active_record.get("id") != rec.get("id"):
                return
            try:
                img = Image.open(BytesIO(img_data))
                img.load()
                self.current_image_data = img_data
                self._display_image(img)
                self.status_var.set("✅ 历史图片已加载")
            except Exception as e:
                self._draw_canvas_hint(f"🖼 图片解析失败\n{e}")
            self._update_action_buttons()
            threading.Thread(
                target=self._cache_history_image, args=(rec.get("id"), img_data), daemon=True
            ).start()

        self.root.after(0, _done)

    def _cache_history_image(self, record_id, img_data: bytes):
        try:
            media, thumb = history_store.save_image_asset(img_data, record_id)
            history_store.update_record(record_id, media_path=media, thumb_path=thumb)
        except Exception as e:
            print(f"[history] 回写缓存失败: {type(e).__name__}: {e}")
        self.root.after(0, self._refresh_history)

    def _format_record_detail(self, rec: dict) -> str:
        """历史记录详情文本：提示词 + 输入参数 + 结果信息"""
        from history_ui import short_time
        is_video = rec.get("type") == "video"
        kind = "🎬 视频" if is_video else "🖼 图片"
        status = "❌ 失败" if rec.get("status") == "failed" else "✅ 成功"

        lines = [
            f"{kind} · {status} · {short_time(rec.get('created_at'))} · ID {rec.get('id')}",
            "",
            "提示词：",
            "  " + (rec.get("prompt") or "（无）"),
            "",
            "输入参数：",
        ]

        params = rec.get("params") or {}
        label_map = [
            ("model", "模型"), ("size", "尺寸"),
            ("seconds", "时长（秒）"), ("aspect_ratio", "画幅"),
        ]
        for key, label in label_map:
            if params.get(key):
                lines.append(f"  {label}: {params[key]}")

        meta = rec.get("meta") or {}
        for key, label in (("seconds", "实际时长"), ("size", "输出分辨率"),
                           ("quality", "质量"), ("video_id", "任务ID")):
            if is_video and meta.get(key) and str(meta[key]) != str(params.get(key, "")):
                lines.append(f"  {label}: {meta[key]}")

        refs = rec.get("refs") or []
        lines.append(f"  参考图: {len(refs)} 张" if refs else "  参考图: 无")
        for i, r in enumerate(refs, 1):
            shown = r if len(r) <= 72 else r[:70] + "..."
            lines.append(f"    {i}. {shown}")

        lines.append("")
        lines.append("结果：")
        lines.append(f"  URL: {rec.get('result_url') or '（无）'}")
        local = rec.get("media_path")
        if local and os.path.exists(local):
            lines.append(f"  本地缓存: {local}")
        if rec.get("status") == "failed" and rec.get("error"):
            lines.append("")
            lines.append(f"失败原因: {rec['error']}")

        return "\n".join(lines)

    def _load_params_from_record(self, rec: dict):
        """把历史记录的提示词与参数回填到对应的生成页"""
        if not rec:
            return
        params = rec.get("params") or {}
        refs = rec.get("refs") or []

        if rec.get("type") == "video":
            self._select_page(PAGE_VIDEO)
            self._write_prompt(self.prompt_video, rec.get("prompt") or "")
            if params.get("seconds") in VIDEO_SECONDS_OPTIONS:
                self.video_seconds.set(params["seconds"])
            if params.get("aspect_ratio") in VIDEO_ASPECT_OPTIONS:
                self.aspect_video.set(params["aspect_ratio"])
            if params.get("model") in VIDEO_MODEL_OPTIONS:
                self.model_video.set(params["model"])
            self.ref_video.set_items(refs)
            self.status_var.set("📋 已载入历史视频参数，可直接重新生成")
        else:
            self._select_page(PAGE_IMAGE)
            self._write_prompt(self.prompt_image, rec.get("prompt") or "")
            if params.get("size") in SIZE_OPTIONS:
                self.size_image.set(params["size"])
                self._sync_aspect_from_size(params["size"])
            if params.get("model") in MODEL_OPTIONS:
                self.model_image.set(params["model"])
            self.ref_image.set_items(refs)
            self.status_var.set("📋 已载入历史图片参数，可直接重新生成")

    # ---------- Lightbox 大图查看（视觉陈列版） ----------
    def _open_lightbox(self, records, index: int):
        """画廊双击 / ⤢ → 全屏大图查看（ESC 关闭、←→ 切换、滚轮缩放）"""
        if not records:
            return
        Lightbox(
            self.root, records, index=index,
            fonts={"small": self.f_small},
            loader=self._lightbox_loader,
            on_status=lambda s: self.status_var.set(s),
            on_play=self._play_record,
        )

    def _lightbox_loader(self, rec: dict, callback):
        """Lightbox 取图：本地缓存优先 → 结果 URL 后台下载 → 回 UI 线程"""
        def _worker():
            data = None
            media = rec.get("media_path")
            if media and os.path.exists(media):
                try:
                    with open(media, "rb") as f:
                        data = f.read()
                except Exception:
                    data = None
            if data is None:
                url = rec.get("result_url")
                if url:
                    try:
                        resp = adaptive_request("GET", url, timeout=60)
                        resp.raise_for_status()
                        data = resp.content
                    except Exception:
                        data = None
            try:
                self.root.after(0, lambda d=data: callback(d))
            except Exception:
                pass  # 主循环已退出（窗口关闭）时结果自然丢弃

        threading.Thread(target=_worker, daemon=True).start()

    def _play_record(self, rec: dict):
        """Lightbox 内播放视频：调用系统默认播放器"""
        url = (rec or {}).get("result_url")
        if not url:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(url)
            else:
                webbrowser.open(url)
            self.status_var.set("▶ 已在默认播放器中打开视频")
        except Exception as e:
            messagebox.showerror("播放失败", f"无法打开视频: {e}")

    # ---------- 操作按钮 ----------
    def _copy_url(self):
        url = self._current_url()
        if not url:
            return
        self._copy_text(url)
        # 反馈就地发生在按钮上（原实现只在左下角状态栏提示，视线不在那里）
        self._flash_button(self.btn_copy_url, "已复制 ✓", "复制 URL")

    def _save_result(self):
        if self.active_record is not None:
            self._save_record(self.active_record)
        elif self.current_video_url:
            self._save_video_file()
        elif self.current_image_data:
            self._save_image_file()
        else:
            messagebox.showwarning("提示", "没有可保存的内容")

    def _save_record(self, rec: dict):
        """保存历史记录：优先复制本地缓存，否则从结果 URL 下载"""
        is_video = rec.get("type") == "video"
        if is_video:
            default = f"agnes_video_{rec.get('id')}.mp4"
            ext, ftypes = ".mp4", [("MP4 视频", "*.mp4"), ("所有文件", "*.*")]
        else:
            default = f"agnes_image_{rec.get('id')}.png"
            ext, ftypes = ".png", [
                ("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg *.jpeg"),
                ("所有文件", "*.*"),
            ]

        file_path = filedialog.asksaveasfilename(
            title="保存历史记录", defaultextension=ext,
            initialfile=default, filetypes=ftypes,
            initialdir=history_store.get_data_dir(),
        )
        if not file_path:
            return

        local = rec.get("media_path")
        if local and os.path.exists(local):
            try:
                shutil.copyfile(local, file_path)
                self.status_var.set(f"✅ 已保存: {file_path}")
                messagebox.showinfo("保存成功", f"已保存到:\n{file_path}")
                return
            except Exception as e:
                messagebox.showerror("保存失败", f"保存失败: {e}")
                return

        url = rec.get("result_url")
        if not url:
            messagebox.showwarning("提示", "该记录没有可保存的结果")
            return

        try:
            self.status_var.set("📥 正在下载...")
            self.root.update_idletasks()
            resp = adaptive_request("GET", url, timeout=180)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(resp.content)
            self.status_var.set(f"✅ 已保存: {file_path}")
            messagebox.showinfo("保存成功", f"已保存到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存失败: {e}")

    def _save_image_file(self):
        default_name = "agnes_image.png"
        file_path = filedialog.asksaveasfilename(
            title="保存图片",
            defaultextension=".png",
            initialfile=default_name,
            initialdir=history_store.get_data_dir(),
            filetypes=[
                ("PNG 图片", "*.png"),
                ("JPEG 图片", "*.jpg *.jpeg"),
                ("所有文件", "*.*"),
            ],
        )
        if not file_path:
            return
        try:
            img = Image.open(BytesIO(self.current_image_data))
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".jpg", ".jpeg"):
                img = img.convert("RGB")
                img.save(file_path, "JPEG", quality=95)
            else:
                img.save(file_path)
            self.status_var.set(f"✅ 图片已保存: {file_path}")
            messagebox.showinfo("保存成功", f"图片已保存到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存图片失败: {e}")

    def _save_video_file(self):
        """下载视频并保存为 MP4"""
        default_name = "agnes_video.mp4"
        file_path = filedialog.asksaveasfilename(
            title="保存视频",
            defaultextension=".mp4",
            initialfile=default_name,
            initialdir=history_store.get_data_dir(),
            filetypes=[
                ("MP4 视频", "*.mp4"),
                ("所有文件", "*.*"),
            ],
        )
        if not file_path:
            return
        try:
            self.status_var.set("📥 正在下载视频...")
            self.root.update_idletasks()
            resp = adaptive_request("GET", self.current_video_url, timeout=180)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(resp.content)
            self.status_var.set(f"✅ 视频已保存: {file_path}")
            messagebox.showinfo("保存成功", f"视频已保存到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存视频失败: {e}")

    def _open_in_browser(self):
        url = self._current_url()
        if url:
            webbrowser.open(url)

    def _play_current(self):
        """播放当前视频（调用系统默认视频播放器）"""
        if self.active_record is not None and self.active_record.get("type") != "video":
            return
        url = self._current_url()
        if not url:
            return
        try:
            # Windows 下用默认程序打开（浏览器/播放器）
            if sys.platform.startswith("win"):
                os.startfile(url)
            else:
                webbrowser.open(url)
            self.status_var.set("▶ 已在默认播放器中打开视频")
        except Exception as e:
            messagebox.showerror("播放失败", f"无法打开视频: {e}")


def _setup_window_icon(root: ctk.CTk):
    try:
        icon_path = resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            # CTk 的 iconbitmap 会置 _iconbitmap_method_called 标记，
            # 阻止其延迟应用的默认 logo 覆盖我们的图标
            root.iconbitmap(icon_path)
            root._iconbitmap_method_called = True
            # 延迟再设一次，确保赢过任何时序竞争
            root.after(300, lambda: root.iconbitmap(icon_path))
        else:
            png_path = resource_path("app_icon.png")
            if os.path.exists(png_path):
                from PIL.ImageTk import PhotoImage as _P
                root.iconphoto(True, _P(file=png_path))
                root._iconbitmap_method_called = True  # 防 ctk 默认 logo 覆盖
    except Exception as e:
        print(f"[icon] 设置图标失败: {type(e).__name__}: {e}")


def main():
    # 主题外观已由 ui_theme 在导入时按 settings 解析（浅 / 深双主题）；
    # 这里只负责网络模式与 DPI 设置
    _settings = app_config.load()
    set_network_mode(_settings.get("network_mode", "auto"))
    if hasattr(ctk, "deactivate_windows_dpi_fix"):
        ctk.deactivate_windows_dpi_fix()  # 使用系统原生 DPI 缩放，文字更锐利

    # 历史记录默认已切到 F:\\AgnesGeneratorData；首次启动把旧 %APPDATA% 数据迁移过去
    try:
        history_store.migrate_legacy()
    except Exception:
        pass

    # 主题切换 = 保存设置后重建窗口（_save_theme 置 _restart_requested）。
    # 循环退出条件：用户关闭窗口，或未请求重建。
    while True:
        # 每轮都按 settings 重新发布色板（首次启动 + 主题切换重建）。
        # 关键：ui_theme 的模块级 apply_palette 只在「首次 import」时执行过一次，
        # 重建窗口时模块已在 sys.modules 中、该行不会重跑，因此必须在此显式
        # 重新应用，否则重建出来的窗口仍是旧主题 —— 这是切换无效的根源。
        ui_theme.apply_palette(app_config.load().get("theme") or "system")
        root = ctk.CTk()
        _setup_window_icon(root)
        app = ImageGeneratorApp(root)

        def _on_close(app=app, root=root):
            try:
                app._save_ui_state()
            except Exception:
                pass
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", _on_close)
        root.mainloop()
        if not getattr(app, "_restart_requested", False):
            break


if __name__ == "__main__":
    main()
