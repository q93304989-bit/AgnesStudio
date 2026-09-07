"""Apple / macOS 风格集中式 Design Token（单一事实来源）。

所有 UI 模块（main / gallery_ui / history_ui）的颜色、间距、圆角、控件高度
一律从本模块引用，禁止在业务代码里出现第二份色值定义。

═══════════════════════════════════════════════════════════════
架构说明（v2 治本重构）
═══════════════════════════════════════════════════════════════
旧版的两个致命缺陷（导致「切换主题只有部分组件变色」）：
  1. token 是模块级全局变量，靠 globals().update() 覆写 + 白名单同步消费模块。
     任何新增模块 / 新增引用都会漏掉，且函数默认参数会烤死旧值。
  2. tk.Canvas 上的图元（create_rectangle / create_polygon …）不响应
     ctk.set_appearance_mode()，只有重建窗口才会重画 —— 表现为「部分不变色」。

新版的三层保障：
  ─ 第 1 层：模块级 __getattr__（PEP 562）
    apply_palette 后从 globals 移除 token 键，使 ui_theme.FILL / 
    from ui_theme import FILL 一律走 __getattr__ 实时读当前调色板。
    这样 token 永不「烤死」，函数默认参数问题也从根上消除。
  ─ 第 2 层：_sync_consumers() 自动扫描
    遍历 sys.modules 中「项目目录内」的所有模块，统一刷新其 __dict__ 中的
    token 名字绑定 —— 不再依赖手写白名单，新增模块自动覆盖。
  ─ 第 3 层：subscribe() 订阅机制（治 Canvas 图元）
    Canvas 图元不会自动跟随主题。组件通过 subscribe() 注册重绘回调，
    apply_palette 时统一通知，实现原地重绘（无需重建窗口）。

设计规则速查：
  - 8pt 栅格：间距只用 4 / 8 / 16 / 24 / 32（4 为半步长）
  - 圆角四档：R_CARD 16 · R_CTRL 12 · R_THUMB 8 · R_PILL 999（胶囊）
  - 控件高度：H_CTA / H_NAV 44 · H_INPUT 36 · H_DROP / H_STATUS 32 · H_CHIP 28
  - 对比度：正文与按钮文字对各自底色 ≥ 4.5:1（WCAG AA）；
    深色主按钮白字 4.56:1，浅色主按钮白字 4.70:1
"""
import os
import sys
import tkinter as tk
import weakref

import customtkinter as ctk

import app_config

# ===================== 8pt 栅格与几何（主题无关） =====================
S_XS, S_SM, S_MD, S_LG, S_XL = 4, 8, 16, 24, 32
PAGE_PAD = S_LG      # 24  页边距
CARD_PAD = S_MD      # 16  卡片内边距
BLOCK_GAP = S_MD     # 16  区块间距
LABEL_GAP = S_SM     # 8   标签 → 控件

H_CTA = H_NAV = 44   # 主按钮 / 导航项
H_INPUT = 36         # 输入框
H_DROP = H_STATUS = 32   # 下拉菜单 / 状态条
H_CHIP = 28          # 胶囊按钮 / 徽标 / 小工具按钮（最小点击区 28）

R_CARD = 16          # 外层三栏大卡片
R_CTRL = 12          # 输入框 / 下拉 / 主按钮 / 历史卡片
R_THUMB = 8          # 缩略图 / 徽标 / 小卡片
R_PILL = 999         # 胶囊按钮（次级操作 / chip / 状态胶囊 / 图标圆钮）

W_NAV, W_INPUT = 200, 400

# 运行时字体族：由 main.pick_font_family() 检测后调用 set_font_family() 覆写。
# Canvas / ToolTip 等非 CTk 控件必须使用它，保证与 CTk 控件同族。
FONT_FAMILY = "Microsoft YaHei UI"


def set_font_family(family: str):
    """运行时覆写全局字体族（需要 Tk root 已存在才能检测系统字体）"""
    global FONT_FAMILY
    if family:
        FONT_FAMILY = family


# ===================== 色彩（浅色值；仅作 IDE 静态分析与文档用途） =====================
# 注意：运行时这些键会从 globals 中移除（见 apply_palette），
# 实际取值一律经由下方 __getattr__ 从 _CURRENT_PALETTE 实时返回。
PAGE_BG = "#F3F3F3"        # 页面背景
CARD_BG = "#FFFFFF"        # 外层卡片
CARD_BORDER = "#D2D2D7"    # 卡片描边（强档）
FIELD_BG = "#F3F3F3"       # 内容区 / 输入框底
FIELD_BORDER = "#E5E5EA"   # 描边统一档
TEXT_MAIN = "#1D1D1F"      # 主文字（对白 16.1:1）
TEXT_SUB = "#6E6E73"       # 次要文字（对 243 灰 4.6:1）
TEXT_DISABLED = "#AEAEB2"  # 禁用态 / 占位符
ACCENT = "#0071E3"         # 主按钮底（白字 4.7:1）
ACCENT_HOVER = "#0064D2"
ACCENT_TEXT = "#0062CC"    # 浅底上的可读蓝（5.4:1）
ACCENT_SOFT = "#F0F7FF"    # 选中项底
ACCENT_SOFT_HOVER = "#E0EEFC"  # ACCENT_SOFT 的 hover 深一档
FILL = "#F3F3F3"           # 次级按钮 / chip / 悬停底
FILL_HOVER = "#E5E5EA"
ON_ACCENT = "#FFFFFF"      # 主按钮上的文字
WARNING_TEXT = "#A05A00"   # 警告文字（对 243 灰 5.0:1）
DESTRUCTIVE = "#FF3B30"    # 破坏性：仅图标 / 描边
ERROR_TEXT = "#D0342C"
ERROR_BG = "#FDEBEB"
SUCCESS_TEXT = "#1E8E3E"
SUCCESS_BG = "#E8F7EC"
VIDEO_BG = "#E3F0FF"       # 视频徽标底（Apple 蓝浅色阶）
VIDEO_TEXT = "#0B5BCB"     # 对 #E3F0FF 5.4:1
SELECTED_BG = "#F0F7FF"    # 历史记录选中卡片底
SCROLLBAR = "#D8D8DE"
SCROLLBAR_HOVER = "#C6C6D0"
OVERLAY_BG = "#1D1D1F"     # 媒体上的深色浮层（角标 / 展开钮）
OVERLAY_HOVER = "#3A3A3C"
OVERLAY_TEXT = "#FFFFFF"
TOOLTIP_BG = "#1D1D1F"     # 提示气泡（深色 HUD，两种外观一致）
TOOLTIP_TEXT = "#FFFFFF"
# 兼容旧命名（历史面板 / 主程序内引用）
BTN_GRAY = FILL
BTN_GRAY_HOVER = FILL_HOVER
GREEN_PILL_BG = SUCCESS_BG
GREEN_PILL_TX = SUCCESS_TEXT
RED_PILL_BG = ERROR_BG
RED_PILL_TX = ERROR_TEXT

# ===================== 调色板（键名与上方声明一一对应） =====================
_LIGHT = {
    "PAGE_BG": "#F3F3F3", "CARD_BG": "#FFFFFF", "CARD_BORDER": "#D2D2D7",
    "FIELD_BG": "#F3F3F3", "FIELD_BORDER": "#E5E5EA",
    "TEXT_MAIN": "#1D1D1F", "TEXT_SUB": "#6E6E73", "TEXT_DISABLED": "#AEAEB2",
    "ACCENT": "#0071E3", "ACCENT_HOVER": "#0064D2",
    "ACCENT_TEXT": "#0062CC", "ACCENT_SOFT": "#F0F7FF", "ACCENT_SOFT_HOVER": "#E0EEFC",
    "FILL": "#F3F3F3", "FILL_HOVER": "#E5E5EA",
    "ON_ACCENT": "#FFFFFF", "WARNING_TEXT": "#A05A00",
    "DESTRUCTIVE": "#FF3B30", "ERROR_TEXT": "#D0342C", "ERROR_BG": "#FDEBEB",
    "SUCCESS_TEXT": "#1E8E3E", "SUCCESS_BG": "#E8F7EC",
    "VIDEO_BG": "#E3F0FF", "VIDEO_TEXT": "#0B5BCB",
    "SELECTED_BG": "#F0F7FF",
    "SCROLLBAR": "#D8D8DE", "SCROLLBAR_HOVER": "#C6C6D0",
    "OVERLAY_BG": "#1D1D1F", "OVERLAY_HOVER": "#3A3A3C", "OVERLAY_TEXT": "#FFFFFF",
    "TOOLTIP_BG": "#1D1D1F", "TOOLTIP_TEXT": "#FFFFFF",
    "BTN_GRAY": "#F3F3F3", "BTN_GRAY_HOVER": "#E5E5EA",
    "GREEN_PILL_BG": "#E8F7EC", "GREEN_PILL_TX": "#1E8E3E",
    "RED_PILL_BG": "#FDEBEB", "RED_PILL_TX": "#D0342C",
}

# 深色：以 Apple 深色系统色为基准（systemBlue 调深为 #0A6CFF，白字 4.56:1 达 AA；
# 全部避免纯黑，页面/卡片/输入框三级抬升制造层次）
_DARK = {
    "PAGE_BG": "#1A1A1C", "CARD_BG": "#232326", "CARD_BORDER": "#3A3A3C",
    "FIELD_BG": "#2C2C2E", "FIELD_BORDER": "#48484A",
    "TEXT_MAIN": "#F5F5F7", "TEXT_SUB": "#A8A8AD", "TEXT_DISABLED": "#6E6E73",
    "ACCENT": "#FFD1DC", "ACCENT_HOVER": "#FFB7C5",
    "ACCENT_TEXT": "#FFC2DE", "ACCENT_SOFT": "#46263A", "ACCENT_SOFT_HOVER": "#57304A",
    "FILL": "#333338", "FILL_HOVER": "#3D3D44",
    "ON_ACCENT": "#3A1225", "WARNING_TEXT": "#FF9F0A",
    "DESTRUCTIVE": "#FF453A", "ERROR_TEXT": "#FF6B61", "ERROR_BG": "#3A2628",
    "SUCCESS_TEXT": "#32D74B", "SUCCESS_BG": "#24382A",
    "VIDEO_BG": "#22344E", "VIDEO_TEXT": "#8AB9FF",
    "SELECTED_BG": "#46263A",
    "SCROLLBAR": "#4A4A4F", "SCROLLBAR_HOVER": "#5A5A60",
    "OVERLAY_BG": "#0E0E10", "OVERLAY_HOVER": "#2C2C2E", "OVERLAY_TEXT": "#FFFFFF",
    "TOOLTIP_BG": "#38383D", "TOOLTIP_TEXT": "#FFFFFF",
    "BTN_GRAY": "#333338", "BTN_GRAY_HOVER": "#3D3D44",
    "GREEN_PILL_BG": "#24382A", "GREEN_PILL_TX": "#32D74B",
    "RED_PILL_BG": "#3A2628", "RED_PILL_TX": "#FF6B61",
}

# Lightbox 深色 HUD（大图查看器始终为深色，两种外观一致）
LB_BG = "#1D1D1F"
LB_BAR = "#2C2C2E"
LB_BTN = "#3A3A3C"
LB_BTN_HOVER = "#48484A"
LB_TEXT = "#FFFFFF"
LB_TEXT_DIM = "#D8D8DC"
LB_HINT = "#8E8E93"

# 当前调色板（唯一运行时真相，pure token，不含辅助键）
_CURRENT_PALETTE: dict = {}
# 上一次的调色板（供显式色控件按「旧值→新值」反查刷新）
_PREV_PALETTE: dict = {}
# 当前外观（"light" / "dark"）
_RESOLVED_MODE: str = "light"
# 上一次「实际生效」的外观，用于判断是否需要通知重绘（避免无谓刷新）
_applied_mode: str = ""
# 项目根目录（用于 _sync_consumers 判定「项目内模块」）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


# ===================== 第 1 层：模块级 __getattr__（PEP 562） =====================
def __getattr__(name: str):
    """模块属性兜底：token 一律实时从当前调色板返回。

    apply_palette() 会把 token 键从 globals 中移除，于是
    `ui_theme.FILL` 与 `from ui_theme import FILL` 都会走到这里，
    永远拿到当前主题的值 —— 从根上消除「值被烤死」的问题。
    """
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    pal = globals().get("_CURRENT_PALETTE") or {}
    if name in pal:
        return pal[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class _TokenView:
    """实时 token 视图：`t.PAGE_BG` 永远返回当前主题的值。

    推荐新代码使用，语义比 `from ui_theme import PAGE_BG` 更明确
    （后者拿到的是导入瞬间的快照，依赖第 2 层同步）。
    """

    __slots__ = ()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        pal = _CURRENT_PALETTE
        if name in pal:
            return pal[name]
        g = globals()
        if name in g:          # 几何 / 字体等主题无关常量
            return g[name]
        raise AttributeError(f"token {name!r} not found")

    def __getitem__(self, name):
        return self.__getattr__(name)

    def get(self, name, default=None):
        try:
            return self.__getattr__(name)
        except AttributeError:
            return default


t = _TokenView()


# ===================== 第 3 层：主题订阅（治 Canvas 图元） =====================
# 元素为 (weakref, 原回调) 元组；弱引用保证 widget 销毁后自动失效，不泄漏内存。
_subscribers: list = []


def subscribe(fn):
    """订阅主题变化。fn 为无参可调用（通常是绑定方法）。

    返回取消订阅的函数。用于 tk.Canvas 等不会自动跟随 CTk 主题的组件
    —— 它们在回调里重绘图元即可实现原地换肤。
    """
    ref = weakref.WeakMethod(fn) if hasattr(fn, "__self__") else weakref.ref(fn)
    _subscribers.append((ref, fn))
    return lambda: unsubscribe(fn)


def unsubscribe(fn):
    """取消订阅"""
    for item in list(_subscribers):
        if item[1] is fn or item[0]() is None:
            try:
                _subscribers.remove(item)
            except ValueError:
                pass


def _notify_subscribers():
    """通知所有订阅者重绘。单个订阅者抛错不影响其他订阅者。"""
    for item in list(_subscribers):
        ref = item[0]
        fn = ref()
        if fn is None:                     # 目标已销毁，顺手清理
            try:
                _subscribers.remove(item)
            except ValueError:
                pass
            continue
        try:
            fn()
        except Exception as e:
            print(f"[ui_theme] theme subscriber error: {e}")


class ThemeAware:
    """主题感知混入：构造后调用 self._bind_theme() 即可自动跟随主题。

    子类实现 on_theme_changed()，在其中重绘 canvas 图元 / 重设显式色。
    纯 CTk 控件无需继承（set_appearance_mode 会自动刷新它们），
    本混入专为含 tk.Canvas 的复合组件准备。
    """

    def _bind_theme(self):
        self._theme_unsub = subscribe(self.on_theme_changed)

    def on_theme_changed(self):
        """子类实现：主题变化后重绘"""
        raise NotImplementedError


# ===================== 第 2 层：自动同步消费模块 =====================
def _sync_consumers(pal: dict):
    """把最新色值同步进所有已加载的「项目内」模块。

    遍历 sys.modules，只处理 __file__ 位于项目目录下的模块，
    统一刷新其 __dict__ 中的 token 名字绑定 —— 不再依赖手写白名单，
    新增模块 / 新增引用自动覆盖，杜绝「漏同步导致部分不变色」。
    """
    for mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        f = getattr(mod, "__file__", None)
        if not f or not str(f).startswith(_PROJECT_ROOT):
            continue                       # 只处理项目内模块
        d = getattr(mod, "__dict__", None)
        if not d:
            continue
        for key, value in pal.items():
            if key in d:
                d[key] = value


def _windows_system_dark() -> bool:
    """读取 Windows 注册表的系统应用主题（AppsUseLightTheme=0 → 深色）"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return value == 0
    except Exception:
        return False


def current_mode() -> str:
    """返回当前外观（"light" / "dark"）"""
    return _RESOLVED_MODE


def current_palette() -> dict:
    """返回当前调色板副本（pure token）"""
    return {k: v for k, v in _CURRENT_PALETTE.items()}


def prev_palette() -> dict:
    """返回上一次的调色板副本（切换前的值）。

    与 current_palette() 配合，供「显式色控件」按值反查刷新：
    CTk 把显式传入的 fg_color / text_color 视为用户自定义色、不跟随主题，
    因此只能按「旧 token 值 → 新 token 值」的映射逐个重新 configure。
    """
    return {k: v for k, v in _PREV_PALETTE.items()}


def retheme_explicit(root) -> int:
    """原地刷新整棵控件树上的「显式 token 色」，返回更新的属性数。

    CTk 的 set_appearance_mode 只刷新「未显式设色」或设为 CTk 主题色名的控件；
    本项目大量使用 fg_color=CARD_BG 这类显式 token 色，它们不会被自动刷新，
    旧方案只能靠「销毁窗口再重建」来绕开 —— 代价是闪烁与状态丢失。

    本函数按「旧调色板值 → 新调色板值」建立映射，递归遍历控件树，
    把值命中的显式色重新 configure()，实现真正的原地换肤（无闪烁）。

    除显式实色（_fg_color 等）外，还覆盖两类 CTk 主题系统也管不到的
    「派生底色」：
      - _bg_color：transparent 控件在构造时把父级背景探测为单值存下，
        之后父色变了它也不会自己跟（CTk 官方只有 CTkFrame.configure(fg_color)
        会联动一层）。这里统一按值反查刷新：实色控件用通用映射，
        transparent 容器的 #F3F3F3 只可能来自 tk 分栏背景 → 特判为 PAGE_BG。
      - tk.Canvas 的 bg：CTkScrollableFrame 内部画布在 set_appearance_mode
        时按「当时的父 fg」解析，而父 fg 的换色要等本函数执行 —— 存在一帧
        滞后残留。本函数最后统一按映射覆盖画布底色，消除该滞后。

    仅处理 str 值；CTk 的主题色是 tuple/list（如 ('gray86','gray17')），
    由 set_appearance_mode 自行处理，不在此改动。
    """
    old, new = prev_palette(), current_palette()
    if not old:
        return 0
    mapping = {v: new[k] for k, v in old.items()
               if new.get(k) and new[k] != v}
    if not mapping:
        return 0

    # 属性名 → CTk configure 关键字
    attr_to_opt = {
        "_fg_color": "fg_color",
        "_text_color": "text_color",
        "_border_color": "border_color",
        "_progress_color": "progress_color",
        "_button_color": "button_color",
        "_button_hover_color": "button_hover_color",
        "_hover_color": "hover_color",
    }
    # transparent 容器的浅灰底只能来自 tk 分栏 / 最外层页面背景 → 页面新色
    page_bg_new = new.get("PAGE_BG")
    count = 0

    def walk(w):
        nonlocal count
        for attr, opt in attr_to_opt.items():
            if not hasattr(w, attr):
                continue
            try:
                cur = getattr(w, attr)
            except Exception:
                continue
            if isinstance(cur, str) and cur in mapping:
                try:
                    w.configure(**{opt: mapping[cur]})
                    count += 1
                except Exception:
                    pass

        # 派生底色 _bg_color：按值反查刷新（transparent 容器的浅灰特判为页面色）
        if hasattr(w, "_bg_color"):
            try:
                cur = w._bg_color
            except Exception:
                cur = None
            if isinstance(cur, str) and cur in mapping:
                try:
                    if page_bg_new and cur == "#F3F3F3" \
                            and w.cget("fg_color") == "transparent":
                        w.configure(bg_color=page_bg_new)
                    else:
                        w.configure(bg_color=mapping[cur])
                    count += 1
                except Exception:
                    pass

        # tk.Canvas 底色（CTkScrollableFrame 内部画布 / 自绘画布未自刷者）
        if isinstance(w, tk.Canvas):
            try:
                bg = w.cget("bg")
            except Exception:
                bg = None
            if isinstance(bg, str) and bg in mapping:
                try:
                    w.configure(bg=mapping[bg])
                    count += 1
                except Exception:
                    pass

        try:
            for c in w.winfo_children():
                walk(c)
        except Exception:
            pass

    walk(root)
    return count


def apply_palette(mode_code: str = "system") -> str:
    """按设置解析并发布调色板，返回实际外观（"light" / "dark"）。

    完整流程（三层保障 + CTk 同步）：
      1. 解析目标外观（显式 light/dark，或 Windows 注册表跟随系统）
      2. 更新 _CURRENT_PALETTE
      3. 从 globals 移除 token 键 → 后续访问走 __getattr__ 实时读
      4. _sync_consumers() 刷新所有项目内模块的名字绑定
      5. ctk.set_appearance_mode() 让 CTk 原生控件自动重绘
      6. _notify_subscribers() 让 Canvas 组件重绘图元（原地换肤）
    """
    global _RESOLVED_MODE, _applied_mode
    code = (mode_code or "system").lower()
    if code not in ("system", "light", "dark"):
        code = "system"
    if code == "dark":
        resolved = "dark"
    elif code == "light":
        resolved = "light"
    elif sys.platform.startswith("win"):
        # CTk 在窗口创建前对「跟随系统」的解析不可靠，Windows 上以注册表为准
        resolved = "dark" if _windows_system_dark() else "light"
    else:
        try:
            ctk.set_appearance_mode("system")
            resolved = (ctk.get_appearance_mode() or "Light").lower()
        except Exception:
            resolved = "light"

    pal = dict(_DARK if resolved.startswith("dark") else _LIGHT)
    # changed 依据「上一次生效的外观」判断；首次调用时 _applied_mode 为空 → True
    changed = _applied_mode != resolved

    # 2. 更新运行时调色板（不含任何辅助键，pure token）。
    #    注意：仅在「主题确实切换」时改 prev/current——同 mode 重复触发
    #    不重置 prev，否则反复点同一主题后 prev/curr 会同化，
    #    下次再切就拿不到正确映射（[bug] 设点「深色」两次再点「浅色」，
    #    retheme_explicit 拿到 prev=dark, curr=light 仍有效，但如果连续
    #    点了 N 次「深色」，再点「浅色」时 prev 已被覆盖成 dark，OK；
    #    但**点了 N 次「深色」再点「深色」**，prev 与 curr 重叠为 dark，
    #    再切「浅色」时 prev=dark、curr=light，这一段是正常的；
    #    真正的隐患是：连续点「浅色」「浅色」「深色」——第二次 "浅色"
    #    不会触发 prev 重置，但我们仍按 prev=dark(已切深过)、curr=light
    #    → 不变。所以这里改用严格：changed=False 时 prev/current/_applied
    #    都不动，调用方需要确保恰好发生过变更。
    if changed:
        # 先留一份旧值：显式色控件靠「旧值 → 新值」反查刷新（见 retheme_explicit）
        _PREV_PALETTE.clear()
        _PREV_PALETTE.update(_CURRENT_PALETTE)
        _CURRENT_PALETTE.clear()
        _CURRENT_PALETTE.update(pal)
        _RESOLVED_MODE = resolved
        _applied_mode = resolved

        # 3. 移除 globals 中的 token 键 → 交给 __getattr__ 实时解析
        for key in pal:
            globals().pop(key, None)

        # 4. 同步所有项目内模块（不再用白名单）
        _sync_consumers(pal)

        # 5. CTk 原生控件（下拉菜单 / 滚动条 / 分段控件 …）随外观模式自动重绘
        try:
            ctk.set_appearance_mode(resolved)
        except Exception:
            pass

        # 6. Canvas 图元原地重绘（订阅者）
        _notify_subscribers()
    else:
        # 同 mode 重复触发：不重置 prev/current（它们已在第一次切时固定下来），
        # 但仍同步模块 token 绑定（防御性：项目内模块可能新增 import）。
        _sync_consumers(pal)
        _RESOLVED_MODE = resolved

    return resolved


# 模块导入即按 settings 解析一次外观
_RESOLVED_MODE = apply_palette(app_config.load().get("theme") or "system")
