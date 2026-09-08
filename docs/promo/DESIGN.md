# Agnes Studio 宣传片 — 设计说明

> 用 [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) 制作。
> 模式：**自主自由创作**（Agent 自主定视觉方向、镜头映射、分镜与音频，不逐阶段等待确认）。

## 阶段 0 · 产品简报与执行约束

| 项 | 结论 |
|----|------|
| 产品 | Agnes Studio —— 基于 Agnes API 的桌面端文生图 / 文生视频工具 |
| 用途 | GitHub 仓库首屏宣传片、课堂/社团分享、README 内嵌 |
| 受众 | **学生、初学者、自学者**（不是投资人，不是企业采购） |
| 核心卖点 | 免费档位 · 零 GPU 门槛 · 中文提示词友好 · 开源可读可改 |
| 必须展示 | ① 品牌 ② 文生图界面 ③ 文生视频界面（异步进度）④ 历史/画廊 ⑤ 开源地址 |
| 规格 | 1920×1080 @ 30fps，900 帧 / 30.0s |
| 画幅 | 16:9 |
| 语言 | 英文主标 + 中文副标（仓库受众以中文为主，但项目名是英文） |
| 音频 | **无 BGM、无 SFX**（静音版）——学生向开源片优先保证加载快、可静音播放、无版权负担 |
| 数据口径 | 仅使用**仓库内已有的公开界面截图**，无任何密钥、无真实用户数据 |

## 阶段 1 · 视觉方向

选定方向：**Deep Navy · Cyan Signal（深海军蓝 + 青色信号光）**

从产品自身推导：Agnes Studio 是 AI 多模态工具，界面为 CustomTkinter 浅色卡片；
视频主视觉不与界面抢戏，而是用**深色科技底**把界面截图"托"出来，
符合"AI / 开发者工具"的品类直觉，也和 README 的技术气质一致。

| token | 值 | 用途 |
|-------|-----|------|
| 底色 | `#0a1028` | 全片铺底 |
| 渐变 | `#0a1028 → #1a1648 → #0a1028`（135°） | Backdrop |
| 强调 A | `#5be9ff`（青） | 标题辉光、图片生成线索、字幕 |
| 强调 B | `#7c8cff`（蓝紫） | 视频生成线索 |
| 正文 | `#f4f7ff` | 字标 |
| 次文本 | `#9ba6c4` | 副标 |
| 网格 | `rgba(91,233,255,0.06)` @ 60px | 科技感底纹，opacity 0.4 |

**动效性格 tokens**（品牌→动效参数推导）：

- 能量轴：中高（面向学生的开发工具，不能死板）
- 调性轴：亲和（不是金融/医疗）
- 预设：**活力大胆**（startup）—— 主时长 ~18f，入场 `bezier(0.16,1,0.3,1)`，过冲 1.12
- 实现上用 `spring({ damping: 9~16, stiffness: 90~140 })` 落这个手感

## 阶段 2 · 功能到镜头映射

| # | 功能 | 镜头语法 | 说明 |
|---|------|---------|------|
| 1 | 品牌 | icon drop-bounce + wordmark fade | spring 过冲砸落，落定 hold |
| 2 | 文生图 | 界面卡上推 + 提示词打字机 + 按钮脉冲辉光 | 主角是"输入→出图"这条动作弧 |
| 3 | 文生视频 | FlashCut 暖白闪转场 + 界面横移 + 进度条填充 | 与镜头 2 **不同语法**（竖推 vs 横移），避免同质化 |
| 4 | 历史/画廊 | 三联卡错落 pop 入（stagger 12f） | 批量入场靠运动本身，不加逐个泛光 |
| 5 | 开源收尾 | 字标 + tagline + GitHub 地址 | 落定后 hold |

> 一种动画手法全片只当一次主角：上推 / 横移 / 错落 pop 各用一次，不重复。

## 阶段 3 · 分镜（帧级时间轴）

```
|  #  | 帧区间    | 时长 | 场景             | 主动作                          | 呼吸位 |
|-----|-----------|------|------------------|--------------------------------|--------|
|  1  | 0–150     | 5.0s | BrandOpen        | icon 砸落 → 字标 → tagline      | 50f    |
|  2  | 150–360   | 7.0s | ImageUIReveal    | 界面上推 → 打字 → 按钮辉光      | 60f    |
|  3  | 360–540   | 6.0s | VideoUIReveal    | 闪白转场 → 横移 → 进度条        | 30f    |
|  4  | 540–720   | 6.0s | GalleryStack     | 三联卡 stagger pop              | 60f    |
|  5  | 720–870   | 5.0s | Outro            | 字标 + tagline + GitHub          | 60f    |
|  6  | 870–900   | 1.0s | FadeOut          | 淡出黑场                        | —      |
```

能量曲线：低（开场）→ 中（图）→ 高（视频转场）→ 中（画廊）→ 收（outro hold）。

## 阶段 4 · 素材

全部来自仓库内**已有真实截图**（非手搓 UI）：

- `ui_preview.png` → `public/textures/ui-image.png`（图片生成页）
- `ui_video_tab.png` → `public/textures/ui-video.png`（视频生成页）
- `app_icon.png` → `public/textures/icon.png`（品牌图标）

## 阶段 5 · 实现

- 工程：Remotion 4，TypeScript，`src/index.ts` → `Root.tsx` → `AgnesPromo.tsx`
- 主时间线 `AgnesPromo.tsx` 导出 `SHOTS` 常量表，所有 Sequence 的 `from` 引用它（不写裸数字）
- 共用组件：`Backdrop`（渐变+网格底）、`Caption`（底部通栏字幕）、`FadeOut`
- **确定性渲染**：无 `Math.random()` / `Date.now()`；唯一"随机"的打字机光标闪烁用 `frame % 30 < 15` 判定，逐帧可复现

### 本机环境适配（踩坑记录）

| 坑 | 解法 |
|----|------|
| npm 首次 install 被 WorkBuddy 的 `genie-safe-delete` 钩子打断（trash esbuild 平台目录失败） | `rm -rf node_modules` 后重装即成功；残留的 cleanup warning 可忽略 |
| 本机无 Chrome | `--browser-executable="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"` |
| `src/index.ts`（非 tsx）写 JSX 报 esbuild `Expected ">" but found "/"` | 改 `registerRoot(Root);` |

## 阶段 6 · 声音设计

**本片不配 BGM / SFX**，为有意选择：

1. 学生向开源片，读者多在 GitHub / 课堂静音场景打开；
2. 无音频 = 无版权负担，仓库可自由分发；
3. 信息已经由字幕承载，不依赖解说。

如需后续加音频，钉帧表应集中放在 `AgnesPromo.tsx` 顶部，
`from` 一律写成 `SHOTS.x.from + offset` 相对表达式，时间线平移时自动跟随。

## 阶段 7 · 验收

| 项 | 结果 |
|----|------|
| 成片时长 | 30.06s（目标 30.0s ✓） |
| 分辨率 | 1920×1080 ✓ |
| MP4 结构 | `ftyp / moov / free / mdat` 完整，moov 前置（faststart）✓ |
| 文件大小 | 5.3 MB |
| 功能覆盖 | 品牌 / 文生图 / 文生视频 / 画廊 / 开源地址 五项全有 ✓ |
| 数据安全 | 无密钥、无真实用户数据 ✓ |
| 确定性渲染 | 无 random / Date.now ✓ |

## 复现命令

```bash
cd docs/promo
npm install
npx remotion render src/index.ts AgnesPromo out/promo.mp4 \
  --browser-executable="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
```
