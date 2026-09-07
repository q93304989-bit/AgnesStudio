"""历史记录面板（Apple 风格）。

结构：
  顶部  — 类型筛选（全部 / 图片 / 视频）+ 提示词搜索 + 刷新
  中部  — 可滚动记录卡片（缩略图 + 类型徽标 + 时间 + 提示词摘要 + 参数标签）
  底部  — 载入参数 / 删除 / 清空全部

选中某条记录后通过 on_select 回调交给主程序，在右侧预览区展示大图或视频信息。
"""
import os
import sys
import subprocess
import tkinter as tk
from datetime import datetime

import customtkinter as ctk
from PIL import Image

import history_store
import ui_theme
import ui_anim  # 卡片选中态颜色插值 / 减弱动态效果
from ui_theme import (
    SCROLLBAR, SCROLLBAR_HOVER,
    S_XS, S_SM,
    H_CHIP, R_CTRL, R_THUMB, R_PILL,
)

# 列表一次最多渲染的卡片数（避免上百条记录时重建界面卡顿）
RENDER_LIMIT = 200


def short_time(created_at: str) -> str:
    """2026-08-29 15:30:12 → 08-29 15:30（跨年显示完整日期）"""
    if not created_at:
        return ""
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(created_at)
    if dt.year == datetime.now().year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d")


class HistoryPanel(ctk.CTkFrame):
    """历史记录列表 + 筛选 + 条目操作

    色板规则：以 ui_theme 当前主题为基底（浅 / 深自动），
    colors 参数仍可覆盖个别键（兼容旧调用方与冒烟测试）。
    """

    FILTER_LABELS = {"全部": "all", "图片": "image", "视频": "video"}

    # 色板键名 → ui_theme token 名
    _TOKEN_ALIASES = {
        "page_bg": "PAGE_BG", "card_bg": "CARD_BG", "card_border": "CARD_BORDER",
        "field_bg": "FIELD_BG", "field_border": "FIELD_BORDER",
        "text_main": "TEXT_MAIN", "text_sub": "TEXT_SUB",
        "text_disabled": "TEXT_DISABLED",
        "accent": "ACCENT", "accent_hover": "ACCENT_HOVER",
        "accent_soft": "ACCENT_SOFT",
        "btn_gray": "BTN_GRAY", "btn_gray_hover": "BTN_GRAY_HOVER",
        "fill": "FILL", "fill_hover": "FILL_HOVER",
        "destructive": "DESTRUCTIVE",
        "error_bg": "ERROR_BG", "error_text": "ERROR_TEXT",
        "success_bg": "SUCCESS_BG", "success_text": "SUCCESS_TEXT",
        "video_bg": "VIDEO_BG", "video_text": "VIDEO_TEXT",
        "selected_bg": "SELECTED_BG",
    }

    def __init__(self, parent, fonts: dict, colors: dict,
                 on_select=None, on_status=None, on_load_params=None):
        super().__init__(parent, fg_color="transparent")
        self.fonts = fonts
        self.c = {k: getattr(ui_theme, attr)
                  for k, attr in self._TOKEN_ALIASES.items()}
        self.c.update(colors or {})
        self.on_select = on_select or (lambda rec: None)
        self.on_status = on_status or (lambda text: None)
        self.on_load_params = on_load_params

        self.records: list = []
        self.filter_type = "all"
        self.keyword = ""
        self.selected_id = None
        self._thumbs = {}        # record_id -> CTkImage（缓存，防止被垃圾回收）
        self._cards = {}         # record_id -> 卡片 frame
        self._list_widgets = []  # 直接挂到列表容器上的控件（重建时整体销毁）
        self._search_job = None
        self._visible_cache: list = []

        self._build()
        self.refresh()

    # ===================== 界面构建 =====================
    def _build(self):
        f_small = self.fonts.get("small")

        # ---- 顶部工具条 ----
        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill=tk.X, padx=S_SM, pady=(S_SM, S_XS))

        self.seg = ctk.CTkSegmentedButton(
            tools,
            values=list(self.FILTER_LABELS.keys()),
            command=self._on_filter_changed,
            height=H_CHIP, corner_radius=R_PILL, font=f_small,
            fg_color=self.c["fill"],
            selected_color=self.c["card_bg"],
            selected_hover_color=self.c["accent_soft"],
            unselected_color=self.c["fill"],
            unselected_hover_color=self.c["fill_hover"],
            text_color=self.c["text_main"],
        )
        self.seg.pack(side=tk.LEFT)

        self.search_var = ctk.StringVar()
        self.search = ctk.CTkEntry(
            tools, textvariable=self.search_var,
            placeholder_text="🔍 搜索提示词",
            height=H_CHIP, corner_radius=R_CTRL, font=f_small,
            fg_color=self.c["field_bg"], border_width=1,
            border_color=self.c["field_border"],
            text_color=self.c["text_main"],
            placeholder_text_color=self.c["text_sub"],
        )
        self.search.pack(side=tk.LEFT, fill=tk.X, expand=True,
                         padx=(S_SM, S_XS))
        self.search.bind("<KeyRelease>", self._on_search_changed)

        self.btn_refresh = ctk.CTkButton(
            tools, text="⟳", command=lambda: self.refresh(),
            width=30, height=H_CHIP, corner_radius=R_PILL, font=f_small,
            fg_color=self.c["btn_gray"], hover_color=self.c["btn_gray_hover"],
            text_color=self.c["text_main"],
        )
        self.btn_refresh.pack(side=tk.LEFT)

        self.btn_folder = ctk.CTkButton(
            tools, text="📂", command=self._open_folder,
            width=30, height=H_CHIP, corner_radius=R_PILL, font=f_small,
            fg_color=self.c["btn_gray"], hover_color=self.c["btn_gray_hover"],
            text_color=self.c["text_main"],
        )
        self.btn_folder.pack(side=tk.LEFT, padx=(S_XS, 0))

        # ---- 记录列表 ----
        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=SCROLLBAR,
            scrollbar_button_hover_color=SCROLLBAR_HOVER,
        )
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=S_XS,
                             pady=(S_XS, S_XS))

        # ---- 底部操作栏 ----
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill=tk.X, padx=S_SM, pady=(S_XS, S_SM))

        self.count_label = ctk.CTkLabel(
            bar, text="", font=f_small, text_color=self.c["text_sub"])
        self.count_label.pack(side=tk.LEFT)

        self.btn_clear = self._mini_btn(bar, "清空全部", self._clear_all, destructive=True)
        self.btn_clear.pack(side=tk.RIGHT, padx=(S_XS, 0))
        self.btn_delete = self._mini_btn(bar, "删除", self._delete_selected, destructive=True)
        self.btn_delete.pack(side=tk.RIGHT, padx=(S_XS, 0))
        self.btn_load = self._mini_btn(bar, "载入参数", self._load_selected)
        self.btn_load.pack(side=tk.RIGHT, padx=(S_XS, 0))

        # 分段控件的高亮初始化放在最后：某些版本 set() 会同步触发 command，
        # 此时上面的 list_frame 必须已经创建好
        self.seg.set("全部")

    def _mini_btn(self, parent, text, command, destructive: bool = False):
        if destructive:
            fg, hover, tx = "transparent", self.c["error_bg"], self.c["error_text"]
        else:
            fg, hover, tx = self.c["btn_gray"], self.c["btn_gray_hover"], self.c["text_main"]
        return ctk.CTkButton(
            parent, text=text, command=command, height=H_CHIP,
            corner_radius=R_PILL,
            font=self.fonts.get("small"), fg_color=fg, hover_color=hover,
            text_color=tx, border_width=0,
        )

    # ===================== 数据刷新 =====================
    def refresh(self):
        """重新读取磁盘记录并重建列表"""
        self.records = history_store.load_history()
        self._thumbs = {k: v for k, v in self._thumbs.items()
                        if any(r.get("id") == k for r in self.records)}
        self._render()

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

    def _clear_list(self):
        """清空列表容器（只销毁自己创建的控件，不碰滚动容器内部结构）"""
        for w in self._list_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._list_widgets = []
        self._cards = {}

    def _add_list_widget(self, widget, **pack_kw):
        widget.pack(**pack_kw)
        self._list_widgets.append(widget)
        return widget

    def _render(self):
        visible = self._visible()
        self._visible_cache = visible
        shown = visible[:RENDER_LIMIT]

        self._clear_list()

        if not shown:
            tip = ("暂无历史记录\n生成图片或视频后会自动记录在这里"
                   if not self.records else "没有匹配的记录")
            self._add_list_widget(
                ctk.CTkLabel(
                    self.list_frame, text=tip, font=self.fonts.get("body"),
                    text_color=self.c["text_sub"], justify=tk.CENTER,
                ),
                pady=40,
            )
            self._update_bar(len(visible), len(shown))
            return

        for rec in shown:
            card = self._build_card(rec)
            self._cards[rec.get("id")] = card

        if len(visible) > len(shown):
            self._add_list_widget(
                ctk.CTkLabel(
                    self.list_frame,
                    text=f"仅显示最近 {len(shown)} 条，共 {len(visible)} 条匹配",
                    font=self.fonts.get("small"), text_color=self.c["text_sub"],
                ),
                pady=8,
            )

        self._update_bar(len(visible), len(shown))

    def _update_bar(self, matched: int = None, shown: int = None):
        if matched is None:
            matched = len(self._visible_cache)
        if shown is None:
            shown = min(matched, RENDER_LIMIT)
        sel = self._selected_record()
        state = "normal" if sel else "disabled"
        self.btn_load.configure(state=state)
        self.btn_delete.configure(state=state)
        self.btn_clear.configure(state="normal" if self.records else "disabled")

        n_img = sum(1 for r in self.records if r.get("type") == "image")
        n_vid = sum(1 for r in self.records if r.get("type") == "video")
        self.count_label.configure(
            text=f"共 {len(self.records)} 条（🖼 {n_img} · 🎬 {n_vid}）· 显示 {shown}"
        )

    # ===================== 记录卡片 =====================
    def _build_card(self, rec: dict) -> ctk.CTkFrame:
        f_small = self.fonts.get("small")
        selected = rec.get("id") == self.selected_id

        card = ctk.CTkFrame(
            self.list_frame, corner_radius=R_CTRL,
            fg_color=self.c["selected_bg"] if selected else self.c["card_bg"],
            border_width=1,
            border_color=self.c["accent"] if selected else self.c["card_border"],
        )
        self._add_list_widget(card, fill=tk.X, padx=S_SM, pady=S_XS)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill=tk.X, padx=S_SM, pady=S_SM)

        # 缩略图 / 类型图标
        photo = self._thumb_for(rec)
        icon = "🎬" if rec.get("type") == "video" else "🖼"
        ctk.CTkLabel(
            body, text="" if photo else icon, image=photo,
            width=56, height=56, corner_radius=R_THUMB,
            fg_color=self.c["field_bg"], font=self.fonts.get("body"),
        ).pack(side=tk.LEFT, padx=(0, S_SM))

        # 右侧信息区
        info = ctk.CTkFrame(body, fg_color="transparent")
        info.pack(side=tk.LEFT, fill=tk.X, expand=True)

        head = ctk.CTkFrame(info, fg_color="transparent")
        head.pack(fill=tk.X)
        badge_text, badge_bg, badge_fg = self._badge(rec)
        ctk.CTkLabel(
            head, text=badge_text, font=f_small, corner_radius=R_THUMB,
            fg_color=badge_bg, text_color=badge_fg,
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            head, text=short_time(rec.get("created_at")), font=f_small,
            text_color=self.c["text_sub"],
        ).pack(side=tk.RIGHT)

        snippet = " ".join((rec.get("prompt") or "").split()) or "（无提示词）"
        if len(snippet) > 64:
            snippet = snippet[:64] + "…"
        ctk.CTkLabel(
            info, text=snippet, font=f_small, anchor=tk.W, justify=tk.LEFT,
            text_color=self.c["text_main"], wraplength=330,
        ).pack(fill=tk.X, pady=(S_XS, 0))

        chips = self._chips(rec)
        if chips:
            chip_row = ctk.CTkFrame(info, fg_color="transparent")
            chip_row.pack(fill=tk.X, pady=(S_SM, 0))
            for text in chips[:4]:
                ctk.CTkLabel(
                    chip_row, text=text, font=f_small, corner_radius=R_THUMB,
                    fg_color=self.c["field_bg"], text_color=self.c["text_sub"],
                ).pack(side=tk.LEFT, padx=(0, S_XS))

        if rec.get("status") == "failed":
            err = " ".join(str(rec.get("error") or "生成失败").split())
            if len(err) > 46:
                err = err[:46] + "…"
            ctk.CTkLabel(
                info, text="⚠ " + err, font=f_small, anchor=tk.W,
                text_color=self.c["destructive"], wraplength=330,
            ).pack(fill=tk.X, pady=(S_XS, 0))

        self._bind_select(card, rec)
        return card

    def _badge(self, rec: dict):
        is_video = rec.get("type") == "video"
        if rec.get("status") == "failed":
            return "⚠ 失败", self.c["error_bg"], self.c["error_text"]
        if is_video:
            return "🎬 视频", self.c["video_bg"], self.c["video_text"]
        return "🖼 图片", self.c["success_bg"], self.c["success_text"]

    @staticmethod
    def _chips(rec: dict) -> list:
        p = rec.get("params") or {}
        chips = []
        if rec.get("type") == "video":
            for key, suffix in (("seconds", "s"), ("aspect_ratio", ""), ("size", "")):
                if p.get(key):
                    chips.append(f"{p[key]}{suffix}")
        else:
            if p.get("size"):
                chips.append(str(p["size"]))
        if p.get("model"):
            chips.append(str(p["model"]))
        refs = rec.get("refs") or []
        if refs:
            chips.append(f"参考图 {len(refs)}")
        if rec.get("media_path") and os.path.exists(rec["media_path"]):
            chips.append("已缓存")
        return chips

    def _thumb_for(self, rec: dict):
        rid = rec.get("id")
        if not rid:
            return None
        if rid in self._thumbs:
            return self._thumbs[rid]
        path = rec.get("thumb_path")
        if not path or not os.path.exists(path):
            return None
        try:
            # with 确保文件句柄及时释放（Windows 下否则会锁住缓存文件）
            with Image.open(path) as im:
                img = im.copy()
            photo = ctk.CTkImage(light_image=img, size=(56, 56))
            self._thumbs[rid] = photo
            return photo
        except Exception:
            return None

    # ===================== 交互 =====================
    def _bind_select(self, widget, rec: dict):
        widget.bind("<Button-1>", lambda e, r=rec: self._select(r))
        for child in widget.winfo_children():
            self._bind_select(child, rec)

    def _apply_card_style(self, card, selected: bool):
        if card is None:
            return
        # 选中/取消选中：底色 + 描边 120ms 插值（token 打断；控件已销毁时静默直落终态）
        ui_anim.blend_configure(
            card,
            {
                "fg_color": self.c["selected_bg"] if selected else self.c["card_bg"],
                "border_color": self.c["accent"] if selected else self.c["card_border"],
            },
            duration_ms=120,
        )

    def _select(self, rec: dict):
        prev = self.selected_id
        new_id = rec.get("id")
        if prev == new_id and prev in self._cards:
            # 已选中：仍然回调一次，方便用户重复点击刷新预览
            self.on_select(rec)
            return
        if prev and prev in self._cards:
            self._apply_card_style(self._cards[prev], False)
        self.selected_id = new_id
        self._apply_card_style(self._cards.get(new_id), True)
        self._update_bar()
        self.on_select(rec)

    def _selected_record(self):
        for r in self.records:
            if r.get("id") == self.selected_id:
                return r
        return None

    def _on_filter_changed(self, value: str):
        self.filter_type = self.FILTER_LABELS.get(value, "all")
        # 部分版本在构造 / set() 时会同步回调，此时列表容器可能还没建好
        if getattr(self, "list_frame", None) is None:
            return
        self._render()

    def _on_search_changed(self, event=None):
        # 输入防抖：避免每敲一个字就重建整个列表
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
        """打开历史数据目录（缓存图片 / 视频存放位置）"""
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
        if not rec or not self.on_load_params:
            return
        self.on_load_params(rec)

    def _delete_selected(self):
        rec = self._selected_record()
        if not rec:
            return
        from tkinter import messagebox
        if not messagebox.askyesno("删除记录", "确定删除这条历史记录吗？\n本地缓存文件也会一并删除。"):
            return
        history_store.delete_record(rec["id"])
        self.selected_id = None
        self.refresh()
        self.on_select(None)
        self.on_status("🗑 已删除该历史记录")

    def _clear_all(self):
        if not self.records:
            return
        from tkinter import messagebox
        if not messagebox.askyesno(
            "清空历史",
            f"确定清空全部 {len(self.records)} 条历史记录吗？\n"
            "包括已缓存的本地图片，此操作不可撤销。",
        ):
            return
        n = history_store.clear_history()
        self.selected_id = None
        self._thumbs = {}
        self.refresh()
        self.on_select(None)
        self.on_status(f"🗑 已清空 {n} 条历史记录")

    # ===================== 对外接口 =====================
    def clear_selection(self):
        """取消选中（例如用户开始了新的生成任务）"""
        if self.selected_id and self.selected_id in self._cards:
            self._apply_card_style(self._cards[self.selected_id], False)
        self.selected_id = None
        self._update_bar()
