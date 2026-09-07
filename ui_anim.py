# -*- coding: utf-8 -*-
"""ui_anim：轻量动效基础设施（tkinter 落地，无第三方依赖）

对应「生成主流程动效规格书」的可执行部分：
- 循环等待动画（骨架 shimmer）按 30fps 低帧率跑，避免整页重绘
- 「减弱动态效果」：读 Windows SPI_GETCLIENTAREAANIMATION，开启时上层直接跳到终态
- 颜色/缓动工具：tk 无原生插值，帧色一律预计算

性能约定：
- 动画帧回调内禁止网络 / 解码 / 文件 IO（与 main.py 既有约定一致）
- 每帧 PhotoImage 需外部保持强引用防 GC；播放完统一清理
"""

import ctypes

# ===================== 减弱动态效果（Reduce Motion） =====================

_reduce_motion = None  # None=尚未检测 / False=正常动画 / True=已减弱


def _query_windows_setting() -> bool:
    """系统「动画显示效果」关闭 → 返回 True（Windows；失败则保守返回 False）"""
    try:
        SPI_GETCLIENTAREAANIMATION = 0x1042
        value = ctypes.c_uint()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
        return ok and int(value.value) == 0
    except Exception:
        return False


def reduce_motion() -> bool:
    """读取系统减弱动态效果设置（惰性检测，仅一次系统调用）"""
    global _reduce_motion
    if _reduce_motion is None:
        _reduce_motion = _query_windows_setting()
    return _reduce_motion


def set_reduce_motion_override(flag: bool):
    """应用内显式开关（将来接设置页时使用），优先于系统值"""
    global _reduce_motion
    _reduce_motion = bool(flag)


# ===================== 颜色工具 =====================


def hex_to_rgb(color) -> tuple:
    """'#rrggbb' / '#rgb' / 元组 → (r, g, b)；无法解析时返回中性灰"""
    if color is None:
        return (128, 128, 128)
    if isinstance(color, tuple):
        return tuple(max(0, min(255, int(c))) for c in color[:3])
    s = str(color).strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) == 6:
            try:
                return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
    return (128, 128, 128)


def rgb_to_hex(rgb: tuple) -> str:
    return "#%02x%02x%02x" % tuple(int(round(max(0.0, min(255.0, c)))) for c in rgb[:3])


def mix_color(c1, c2, t: float) -> str:
    """按比例 t∈[0,1] 从 c1 插值到 c2（t=1 取 c2），返回 hex"""
    t = max(0.0, min(1.0, t))
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


def luminance(color) -> float:
    """近似相对亮度 0~1，用于判断亮色向白/暗色向白偏移的方向"""
    r, g, b = hex_to_rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


# ===================== 缓动函数（t ∈ [0,1]） =====================


def ease_linear(t: float) -> float:
    return max(0.0, min(1.0, t))


def ease_in_out(t: float) -> float:
    """对称过渡（图标/底色互换、shimmer 扫过），往返无方向性"""
    t = max(0.0, min(1.0, t))
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def ease_out(t: float) -> float:
    """快启动慢落定；近似 cubic-bezier(0.22, 1, 0.36, 1)"""
    t = max(0.0, min(1.0, t))
    u = 1 - t
    return 1 - u ** 5


def ease_in(t: float) -> float:
    """慢启动快结束（退场加速用）"""
    t = max(0.0, min(1.0, t))
    return t ** 3


# ===================== 动效时长语义（ms，与生成主流程动效规格书对齐） =====================

T_PRESS_MS = 80       # 按压 press-in
T_STATE_MS = 180      # 状态换肤 / 交叉淡化
T_REVEAL_MS = 350     # 内容就位
T_SHAKE_MS = 300      # 错误抖动（上限）
T_COUNT_MS = 600      # 真实数据计数演绎
T_FADE_IN_MS = 180    # 弹层进场
T_FADE_OUT_MS = 140   # 弹层退场（快于进场）
T_SHRIMMER_MS = 1800  # 骨架扫描周期


# ===================== 弹层窗口淡入淡出（CTkToplevel alpha 通道） =====================

def _safe_set_alpha(win, value: float):
    """窗口可能已销毁 / 不支持 alpha 时静默跳过"""
    try:
        win.attributes("-alpha", max(0.0, min(1.0, value)))
    except Exception:
        pass


def fade_window_in(win, steps: int = 6, step_ms: int = 30):
    """Toplevel alpha 0→1 淡入（默认约 180ms，ease-out）。

    调用前窗口应已完成布局；函数内部会先映射再置透明，避免首帧闪现。
    reduce_motion 开启时直接落 alpha=1（无动画）。
    """
    if reduce_motion():
        _safe_set_alpha(win, 1.0)
        return
    token = getattr(win, "_fade_in_token", 0) + 1
    win._fade_in_token = token
    try:
        win.attributes("-alpha", 0.02)
        win.update_idletasks()
    except Exception:
        return

    def _set(i: int):
        # 淡出已启动（token 被递增）→ 让位，避免两链帧互相覆盖
        if getattr(win, "_fade_in_token", None) != token:
            return
        _safe_set_alpha(win, ease_out(i / steps))

    for i in range(1, steps + 1):
        win.after(i * step_ms, lambda i=i: _set(i))


def fade_window_out(win, steps: int = 5, step_ms: int = 28, on_finished=None):
    """Toplevel alpha 1→0 加速淡出（默认约 140ms，ease-in）后执行 on_finished。

    - 以窗口上的 _fade_out_token 防重复进入（重复调用直接忽略）；
    - 启动时取消未完成的淡入链（_fade_in_token 递增）；
    - reduce_motion 开启时立即执行 on_finished；
    - on_finished 默认 win.destroy；tk 对已销毁窗口 destroy 幂等。
    """
    done = on_finished or win.destroy
    try:
        # 取消尚在排队的淡入帧，避免 alpha 两链竞争
        win._fade_in_token = (getattr(win, "_fade_in_token", 0) + 1)
    except Exception:
        pass
    token = getattr(win, "_fade_out_token", 0) + 1
    win._fade_out_token = token
    if reduce_motion():
        done()
        return

    def tick(i: int = 0):
        if getattr(win, "_fade_out_token", None) != token:
            return
        if i >= steps:
            done()
            return
        _safe_set_alpha(win, 1.0 - ease_in((i + 1) / steps))
        win.after(step_ms, lambda: tick(i + 1))

    tick(0)


# ===================== 通用颜色帧插值（configure 落点） =====================

# ===================== 活动颜色帧链登记（主题切换前收口） =====================
# retheme_explicit 按「旧值→新值」映射整树刷新后，若仍有 after 帧链在跑，
# 会把旧调色板的中间色又 configure 回去 —— 而中间色不在映射表，换肤校验
# 即违规。因此所有颜色帧链（blend_configure / CTA 脉冲等）启动时在此登记，
# 主题切换前由 settle_all() 统一「落语义终态 + 停链」，让 retheme 能接手。

_ACTIVE_CHAINS = []  # [widget, attr, token, end_cfg]


def _drop_chain(widget, attr: str, token: int):
    """按 (widget, attr, token) 精确反登记；找不到（已被顶替/收口）则忽略"""
    for i, item in enumerate(_ACTIVE_CHAINS):
        if item[0] is widget and item[1] == attr and item[2] == token:
            _ACTIVE_CHAINS.pop(i)
            return


def track_chain(widget, attr: str, token: int, end_cfg: dict):
    """登记一条活动颜色帧链。end_cfg 为该链的语义终态（当前调色板 token 色）。

    同一 widget 同 attr 只保留最新一条链（新 token 启动自动顶替旧登记，
    避免中断帧残留堆积）。
    """
    _ACTIVE_CHAINS[:] = [it for it in _ACTIVE_CHAINS
                         if not (it[0] is widget and it[1] == attr)]
    _ACTIVE_CHAINS.append([widget, attr, token, dict(end_cfg)])


def drop_chain(widget, attr: str, token: int):
    """链自然结束后反登记。"""
    _drop_chain(widget, attr, token)


def settle_all():
    """主题切换前收口所有活动颜色帧链：立即 configure 到语义终态并停链。

    终态均为「当前调色板 token 值」，随后 retheme_explicit 才能把它们按
    旧→新映射刷成新主题色；不提前收口会残留半途中间色（映射表查不到）。
    已被新链顶替（token 不匹配）的旧登记直接丢弃。
    """
    while _ACTIVE_CHAINS:
        widget, attr, token, end_cfg = _ACTIVE_CHAINS.pop()
        try:
            if getattr(widget, attr, None) == token:
                setattr(widget, attr, token + 1)  # 停链：后续 after 帧让位
                widget.configure(**end_cfg)
        except Exception:
            pass


def is_hex_color(color) -> bool:
    """判断是否为可插值的 6 位 hex（#rrggbb）。命名色 / transparent / None → False"""
    return (isinstance(color, str) and len(color) == 7
            and color.startswith("#"))


def blend_configure(widget, targets: dict, duration_ms: int = T_STATE_MS,
                    steps: int | None = None):
    """widget.configure(**targets) 的颜色插值帧循环（token 打断制）。

    - targets: {option: '#rrggbb'}，如 {"fg_color": "#3A7BF6", "text_color": "..."}；
    - 插值起点 = configure 前各 option 的当前值（cget），终帧精确落目标色；
    - 当前值或目标值不可插值（transparent / 命名色 / None）→ 直接落终态；
    - 新调用使旧链失效（widget._blend_token 递增），列表重建等并发场景自动让位；
    - 帧回调 try/except：目标控件已销毁 → 静默终止；
    - reduce_motion 或 duration_ms<=0 → 直接落终态。
    """

    def _apply(cfg: dict):
        try:
            widget.configure(**cfg)
        except Exception:
            pass

    if reduce_motion() or duration_ms <= 0:
        _apply(targets)
        return
    token = getattr(widget, "_blend_token", 0) + 1
    widget._blend_token = token
    try:
        cur = {k: widget.cget(k) for k in targets}
    except Exception:
        _apply(targets)
        return
    # 逐项分组：仅「当前值 + 目标值均为可插值 hex」的项走帧插值；
    # 其余（list/tuple/transparent/命名色/None）立即 configure 落终态——
    # 不因个别不可插值项而放弃整条链（如 CTkButton.text_color cget 为双值
    # list，但 fg_color 是可插值 hex，二者应各自走对应路径）。
    instant, frames = {}, {}
    for k, tv in targets.items():
        if is_hex_color(cur.get(k)) and is_hex_color(tv):
            frames[k] = tv
        else:
            instant[k] = tv
    if instant:
        _apply(instant)
    if not frames:
        return  # 无插值项，全部已即时落终态
    if steps is None:
        steps = max(2, int(round(duration_ms / 30.0)))
    step_ms = duration_ms / steps
    track_chain(widget, "_blend_token", token, targets)

    def tick(i: int = 0):
        if getattr(widget, "_blend_token", None) != token:
            return  # 已被新链顶替或 settle_all 收口停链
        t = ease_in_out((i + 1) / steps)
        cfg = {k: mix_color(cur[k], tv, t) for k, tv in frames.items()}
        _apply(cfg)
        if i + 1 < steps:
            widget.after(int(step_ms), lambda: tick(i + 1))
        else:
            drop_chain(widget, "_blend_token", token)  # 自然结束反登记

    tick(0)
