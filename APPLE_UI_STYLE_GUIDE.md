# Agnes 图像生成小工具 · Apple UI 风格指南

> 本文件是本项目 UI 的**唯一设计规范**。任何 AI 或开发者在修改界面之前必须通读本文，
> 并在提交前逐项过一遍文末检查清单。所有 token 的代码事实来源是 `ui_theme.py`，
> 本文与其保持同步；两者冲突时，先改 `ui_theme.py` 再同步本文。

---

## 1. 设计原则

1. **极简与克制**：一屏只保留必要的控件；没有功能的装饰一律删除。
   操作入口按使用频率收敛（主操作 1 个，次操作 ≤3 个）。
2. **内容优先**：图片是主角。控件默认隐形，悬停才渐显（画廊卡片 / 大图查看器）。
3. **轻盈材质**：用「页面 243 灰 → 白色卡片 → 内容区灰」三级底色制造层次，
   不使用纹理、金属、霓虹、强渐变。
4. **统一即美**：同一种控件全应用只有一种样式；所有取值必须来自
   `ui_theme.py` 的 token，禁止散落硬编码。
5. **宽容而非打扰**：错误用红色文字 + 浅红底徽标提示，不弹突兀对话框；
   破坏性操作保留确认弹窗。

## 2. 颜色系统

全部颜色定义于 `ui_theme.py`（浅色为静态声明值，深色在运行时按主题覆写）。
**规则：业务代码只允许 `from ui_theme import ...`，禁止出现十六进制字面量。**

| Token | 用途 | 浅色 | 深色 | 对比度 |
|---|---|---|---|---|
| `PAGE_BG` | 页面背景 | `#F3F3F3` | `#1A1A1C` | — |
| `CARD_BG` | 外层卡片 | `#FFFFFF` | `#232326` | — |
| `CARD_BORDER` | 卡片描边（强档） | `#D2D2D7` | `#3A3A3C` | — |
| `FIELD_BG` | 内容区 / 输入框底 | `#F3F3F3` | `#2C2C2E` | — |
| `FIELD_BORDER` | 描边统一档 | `#E5E5EA` | `#48484A` | — |
| `TEXT_MAIN` | 主文字 | `#1D1D1F` | `#F5F5F7` | 16.1 : 1 |
| `TEXT_SUB` | 次要文字 | `#6E6E73` | `#A8A8AD` | ≥ 4.6 : 1 |
| `TEXT_DISABLED` | 禁用态 / 占位符 | `#AEAEB2` | `#6E6E73` | 豁免 |
| `ACCENT` | 主按钮底 | `#0071E3` | `#FFD1DC` | 浅：白字 4.70 / 深：樱花粉深紫黑字 10.5 : 1 |
| `ACCENT_HOVER` | 主按钮悬停 | `#0064D2` | `#FFB7C5` | 深 hover 略深 |
| `ACCENT_TEXT` | 可读文字（浅蓝 / 深浅粉） | `#0062CC` | `#FFC2DE` | 深底上 8.77 : 1 |
| `ACCENT_SOFT` | 次级按钮 / 选中项底 | `#F0F7FF` | `#46263A` | — |
| `ACCENT_SOFT_HOVER` | ACCENT_SOFT 悬停 | `#E0EEFC` | `#57304A` | — |
| `FILL` / `FILL_HOVER` | 次级按钮 / chip / 悬停底 | `#F3F3F3` / `#E5E5EA` | `#333338` / `#3D3D44` | — |
| `ON_ACCENT` | 主按钮上的文字 | `#FFFFFF` | `#3A1225` | 深色主按钮 = 樱花粉底深紫黑字（10.5 : 1） |
| `WARNING_TEXT` | 警告文字 | `#A05A00` | `#FF9F0A` | ≥ 5.0 : 1 |
| `DESTRUCTIVE` | 破坏性（图标 / 描边） | `#FF3B30` | `#FF453A` | — |
| `ERROR_TEXT` / `ERROR_BG` | 错误 | `#D0342C` / `#FDEBEB` | `#FF6B61` / `#3A2628` | ≥ 5.1 : 1 |
| `SUCCESS_TEXT` / `SUCCESS_BG` | 成功 | `#1E8E3E` / `#E8F7EC` | `#32D74B` / `#24382A` | ≥ 6.5 : 1 |
| `VIDEO_BG` / `VIDEO_TEXT` | 视频徽标 | `#E3F0FF` / `#0B5BCB` | `#22344E` / `#8AB9FF` | ≥ 5.4 : 1 |
| `SELECTED_BG` | 列表选中卡片底 | `#F0F7FF` | `#46263A` | — |
| `SCROLLBAR` / `_HOVER` | 滚动条 | `#D8D8DE` / `#C6C6D0` | `#4A4A4F` / `#5A5A60` | — |
| `OVERLAY_BG` / `_HOVER` / `_TEXT` | 媒体上的浮层 | `#1D1D1F` / `#3A3A3C` / `#FFFFFF` | `#0E0E10` / `#2C2C2E` / `#FFFFFF` | — |
| `TOOLTIP_BG` / `_TEXT` | 提示气泡（恒为深色 HUD） | `#1D1D1F` / `#FFFFFF` | `#38383D` / `#FFFFFF` | — |
| `LB_*` | 大图查看器 HUD（恒为深色） | 见 `ui_theme.py` | 同左 | — |

**禁用清单**：`#007AFF`（对白 4.0:1 不达 AA，故主按钮用 `#0071E3`）、
`#86868B` 作正文（仅 3.33:1）、Google Material 蓝 `#1A56C4`、纯黑 `#000000` 作背景。

**使用禁令（务必遵守）**：token **禁止用作函数 / 方法的默认参数值或类属性默认值**。
默认参数在 import（定义）时求值，会把当时的色板烤进 `__defaults__`；
之后 `apply_palette()` 改的只是模块全局变量，碰不到 `__defaults__`。
- 典型事故：`PanelCard.__init__(self, ..., fg_color=CARD_BG, border_color=CARD_BORDER)`
  导致三栏外框在切到深色后仍是白色；而子控件普遍用 `fg_color="transparent"`
  继承父级底色，于是白底连片 —— 表现为「切换深色时只有部分组件变色」。
- 正确写法：默认参数一律置 `None`，在函数体内解析：

```python
def __init__(self, master, fg_color=None, border_color=None, **kwargs):
    # 调用时解析，才能读到当前主题的值
    self._fg_color = CARD_BG if fg_color is None else fg_color
    self._border_color = CARD_BORDER if border_color is None else border_color
```

## 3. 字体排印

- **字体族**：运行时探测，优先级 `SF Pro Text/Display`（macOS）→
  `Segoe UI Variable Display` / `Segoe UI`（Windows）→ `Microsoft YaHei UI`（中文兜底）。
  探测结果写入 `ui_theme.FONT_FAMILY`；**Canvas、ToolTip 等非 CTk 控件必须引用它**，
  与 CTk 控件保持同族。
- **字号阶梯**（weight / 用途）：

| 层级 | Token | 字号 | 字重 |
|---|---|---|---|
| 页面大标题 | `f_title` | 18 px | 600 |
| 区块标题 | `f_section` | 14 px | 600 |
| 主按钮文字 | `f_cta` | 15 px | 600 |
| 正文 | `f_body` | 13 px | 400 |
| 次要 / 说明 / 徽标 | `f_small` | 11 px | 400 |

- 行高：多行说明文字 ≥ 1.4；按钮 / 标签单行居中即可。
- 中英混排不手动加空格键距；禁止斜体、下划线、描边文字。

## 4. 间距与布局

- **8pt 栅格**：间距只允许 `4 / 8 / 16 / 24 / 32`（`S_XS / S_SM / S_MD / S_LG / S_XL`，
  4 为半步长），通过 `padx` / `pady` 引用 token，禁止裸数字。
- 语义常量：`PAGE_PAD 24`（页边距）、`CARD_PAD 16`（卡片内边距）、
  `BLOCK_GAP 16`（区块间距）、`LABEL_GAP 8`（标签 → 控件）。
- 内容最大宽度：设置页内边距 32（`S_XL`），不设横向无限拉伸区；
  双列参数用 `grid(uniform)` 均分。
- 三栏结构：左导航 200（`W_NAV`）/ 中间输入 / 右预览，`PanedWindow` 分隔条 6px、
  颜色同页面背景（视觉上无痕）。

## 5. 圆角与阴影

**圆角四档（全应用唯一体系）**：

| Token | 值 | 适用 |
|---|---|---|
| `R_CARD` | 16 | 外层三栏大卡片（唯一 16 档容器） |
| `R_CTRL` | 12 | 输入框、下拉、主按钮、历史 / 画廊卡片 |
| `R_THUMB` | 8 | 缩略图、徽标、小 chip、参数标签 |
| `R_PILL` | 999 | 胶囊按钮（次级操作、工具钮、图标圆钮、状态胶囊） |

- 面板拼接处允许单侧平角（`PanelCard` 的 `_panel_shape_points`），
  但外轮廓圆角仍为 16。
- **阴影**：Tkinter 无真阴影，用「描边 1px `CARD_BORDER` + 底色抬升」替代；
  禁止在代码里叠加多层边框模拟立体感。

## 6. 材质与效果

- **毛玻璃已放弃**：Tkinter 平台无法实现真实玻璃材质且第三方 hack 打包后不可控，
  本应用**以扁平灰阶层次模拟轻盈感**：浅色 243 → 255 → 243；深色 1A1A → 2323 → 2C2C。
  浅 / 深对比图见 `generated-images/theme_compare.png`。
- 禁用效果列表：霓虹 / 发光、金属渐变、强彩色投影、内阴影、噪点纹理、
  半透明彩色蒙层、Windows Aero 玻璃、毛玻璃 / Acrylic / Mica / Vibrancy。
- 允许的「动态感」仅限：悬停换底色（`*_HOVER`）、骨架屏渐变、结果状态图标。

## 7. 组件规范

所有高度取自 token，禁止自定义高度数值。

| 组件 | 尺寸 | 样式 |
|---|---|---|
| 主按钮 CTA | 高 `H_CTA 44`，圆角 `R_CTRL 12` | 底 `ACCENT`，字 `ON_ACCENT` 15/600；悬停 `ACCENT_HOVER` |
| 导航项 | 高 `H_NAV 44`，宽 `W_NAV 200`，圆角 `R_PILL` | 透明底；选中 `ACCENT_SOFT` + 字 `ACCENT_TEXT` |
| 次级按钮 / chip | 高 `H_CHIP 28`，圆角 `R_PILL` | 底 `FILL`，字 `TEXT_MAIN`；悬停 `FILL_HOVER` |
| 破坏性按钮 | 高 `H_CHIP 28`，圆角 `R_PILL` | 透明底 + 字 `ERROR_TEXT`；悬停底 `ERROR_BG` |
| 输入框 / 下拉 | 高 `H_INPUT 36` / `H_DROP 32`，圆角 `R_CTRL 12` | 底 `FIELD_BG`，边 `FIELD_BORDER` 1px |
| 搜索框 | 高 `H_CHIP 28`，圆角 `R_CTRL 12` | 与列表 / 画廊工具条同规格 |
| 图标方 / 圆钮 | 30×`H_CHIP` 或 `H_CHIP`×`H_CHIP`，圆角 `R_PILL` | 底 `FILL`；媒体浮层上的用 `OVERLAY_*` |
| 分段控件 | 高 `H_CHIP 28`，圆角 `R_PILL` | 底 `FILL`，选中段 `CARD_BG` + 悬停 `ACCENT_SOFT`（列表 / 画廊 / 视频页统一） |
| 开关 | 标准 CTk Switch | 选中 `ACCENT` |
| 进度条 | 高 6，圆角 = 高/2（胶囊） | 底 `FILL`，进度 `ACCENT` |
| 状态徽标 | 圆角 `R_THUMB 8` | 视频 `VIDEO_*`、失败 `ERROR_*`、成功 `SUCCESS_*` |
| 滚动条 | 宽度取 CTk 默认 | `SCROLLBAR` / `SCROLLBAR_HOVER`，禁用默认灰色 |

## 8. 标题栏规范

- **保留系统原生标题栏**（Windows 平台），不自绘 macOS 红绿灯：
  在 Windows 上伪造 macOS 车窗控件会牺牲窗口拖拽 / 贴边 / 系统菜单等原生行为，
  且与宿主系统割裂。窗口标题与图标按项目规范设置。
- 若未来迁移到支持无边框自定义的框架，需实现：红绿灯 12px 圆点、
  左上角 20,20 起、间距 8、悬停显示 ×/−/+ 图形、过渡 150ms。

## 9. 深色模式

- 主题三态：`跟随系统 / 浅色 / 深色`（设置页）。解析优先级：
  Windows 上以注册表 `AppsUseLightTheme` 为准（`ui_theme._windows_system_dark`），
  非 Windows 用 CTk 解析。
- 切换主题 = 保存设置后**原地换肤**（`ui_theme.apply_palette(code)`），
  不销毁窗口、不丢状态。三层保障（见第 12 节「主题切换架构」）：
  1. `ctk.set_appearance_mode()` 刷新 CTk 主题色（tuple/theme 色）；
  2. `ui_theme.retheme_explicit(root)` 按「旧值 → 新值」映射刷新显式
     token 色，并覆盖 `_bg_color` 派生底色与 `CTkScrollableFrame` 内部
     画布（消除 `set_appearance_mode` 先行导致的滞后残留）；
  3. 订阅者回调（`ui_theme.subscribe`）让自绘 Canvas 组件原地重绘。
- **避免纯黑**：页面 `#1A1A1C`、卡片 `#232326`、输入框 `#2C2C2E`
  三级抬升制造层次；媒体浮层才允许接近黑（`#0E0E10`）。
- 深色下文字一律换用深色 token；主按钮白字对比 4.56:1（AA）。
- 大图查看器 / 提示气泡恒为深色 HUD，两种外观下一致。

## 10. 动效规范

Tkinter 无贝塞尔补间，动效以「短促 + 有目的」为原则：

| 场景 | 参数 |
|---|---|
| 悬停反馈 | 即时换色（CTk 内置），不加时长 |
| 骨架屏 / 进度动画 | `after` 50–400ms 帧步进（`_animate_progress` / `_animate_skeleton`） |
| 表单校验失败抖动 | ±4px × 5 帧，总时长 300ms（`_shake_widget`） |
| 搜索 / 防抖 | 200–260ms 静默后触发 |
| 原地换肤（切主题） | `apply_palette` 同步刷新，无销毁重建、无闪烁 |

若未来迁移 Web / 原生框架，统一缓动曲线 `cubic-bezier(0.4, 0, 0.2, 1)`（标准 ease-out），
时长：微交互 150ms / 控件态 200ms / 面板出现 250ms；禁止弹跳、回弹超过 5% 过冲。

## 11. 可访问性

- **对比度**：正文与按钮文字对各自底色 ≥ 4.5:1（WCAG AA）；禁用态豁免。
  每次新增色值必须在本文表格登记实测对比度。
- **点击区域**：按钮最小 28×28px（`H_CHIP`），主按钮 44px 高；
  纯图标按钮须配 ToolTip（深色 HUD，`TOOLTIP_*`）。
- **键盘**：ESC 关闭弹层、←/→ 切图、+/-/0 缩放、Tab 顺序遵循视觉流；
  输入框支持回车提交。
- **屏幕阅读器 / 状态**：结果区状态机（idle/loading/success/error）以
  文字 + 图标双通道呈现，不只用颜色。
- **语言**：界面文案简体中文，标点用全角；状态前缀约定
  `✅ 成功 / ⚠ 警告 / ❌ 失败 / ⏳ 进行中 / 🗑 删除 / 📂 打开`。

## 12. 主题切换架构（原地换肤）

切换主题 **不销毁窗口**：`_save_theme` 写入设置后直接
`ui_theme.apply_palette(code)`（`main.main()` 已弃用重建循环）。整套机制分三层：

1. **CTk 主题色层**：`ctk.set_appearance_mode()` 只负责 tuple/theme 色（如
   CTk 默认配色或 `("gray86","gray17")` 形式）的自动重绘 —— **管不到**显式
   传入的单值 token 与 tk.Canvas 图元。
2. **显式 token 层**：`ui_theme.retheme_explicit(root)` 按
   「`prev_palette()` 旧值 → `current_palette()` 新值」反查整棵控件树，
   把命中的单值显式色重新 `configure()`。除 `_fg_color` 等常规属性外，
   还覆盖两类派生底色：
   - `_bg_color`：transparent 控件构造时把父背景探测为单值存下，之后父色
     变化它不会自己跟（CTk 官方仅 `CTkFrame.configure(fg_color)` 联动一层）；
     transparent 容器残留的 `#F3F3F3` 只可能来自 tk 分栏背景 → 特判为页面色。
   - `tk.Canvas.bg`：`CTkScrollableFrame` 内部画布在 `set_appearance_mode`
     回调里按「当时的父 fg」解析，而父 fg 换色要等本函数 —— 本函数最后
     统一覆盖，消除这一帧滞后。
3. **自绘组件层**：`ui_theme.subscribe(cb)`（WeakMethod 弱引用）——
   `PanelCard` / `AspectPicker` / 主窗口 `on_theme_changed` 等组件注册后，
   换肤时被回调，原地重绘 Canvas 图元（骨架 / 缩略图 / 提示文字等）。
   `PanelCard.on_theme_changed` 必须走 `configure()`（而非直接赋
   `_fg_color`），才能触发 CTkFrame 把新色联动下发到透明子树。

**规则**：
- 新增自绘 Canvas 组件 → 实现 `on_theme_changed`（或 subscribe 回调），
  读 `ui_theme.t.*` 实时重绘；禁止在回调里缓存单值。
- token 一律实时读（模块级 `__getattr__` / `ui_theme.t` 代理），
  禁止把 token 烤进默认参数 / 类属性。
- CTk 控件显式色依赖第 2 层自动刷新即可，无需逐个 subscribe。

## 13. 提交前检查清单

- [ ] 没有新增十六进制色值字面量 —— 全部来自 `ui_theme`（`from ui_theme import ...`）
- [ ] 没有新增 `padx` / `pady` 裸数字 —— 只用 `S_XS/S_SM/S_MD/S_LG/S_XL` 或语义常量
- [ ] 圆角只用了四档：`R_CARD 16 / R_CTRL 12 / R_THUMB 8 / R_PILL 999`
- [ ] 控件高度只用了 `H_CTA 44 / H_NAV 44 / H_INPUT 36 / H_DROP 32 / H_CHIP 28`
- [ ] Canvas / ToolTip 等非 CTk 控件使用 `ui_theme.FONT_FAMILY`
- [ ] 新控件在浅色与深色下都检查过（`apply_palette('dark')` 后截图/目检）
- [ ] 文字对比度 ≥ 4.5:1，并在第 2 节表格登记
- [ ] 悬停态使用对应 `*_HOVER` token，未引入新颜色
- [ ] 破坏性操作走 `ERROR_*` 色与确认弹窗
- [ ] 没有引入渐变 / 霓虹 / 纹理 / 强投影等禁用效果
- [ ] 徽标 / 状态色语义正确：视频 `VIDEO_*`、失败 `ERROR_*`、成功 `SUCCESS_*`
- [ ] 动效时长在 150–400ms 内，且带防抖 / `after_cancel` 清理
- [ ] 运行过 `python _smoke_app.py`、`python _smoke_history.py`、`python _smoke_tabs.py` 全部通过
- [ ] token 没有出现在任何默认参数 / 类属性默认值里（见第 2 节「使用禁令」）
- [ ] 主题覆盖率校验通过：`python _smoke_theme.py` → `RESULT: ALL PASS`
      （浅 → 深 → 切回浅，三轮遍历全部 611 个控件的解析色，违规数须为 0）
- [ ] 原地换肤校验通过：`python _smoke_theme_inplace.py` → `RESULT: ALL PASS`
      （不销毁窗口，在同一窗口内 浅 → 深 → 切回浅 → 跟随系统，
      611 控件 + 17 Canvas 图元违规数须为 0；新增显式色使用点须注册
      `subscribe` 或依赖 `retheme_explicit` 覆盖，禁止只切 `ctk` 外观模式）
- [ ] token 变更后重新生成对比图：`python _gen_theme_compare.py`
  （浅 / 深双调色板：浅色 243/255/243 · 深色 1A1A/2323/2C2C，
  主图三栏：左导航 200 / 中输入 / 右预览 320，徽标 / 状态条全覆盖）
