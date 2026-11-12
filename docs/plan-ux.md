# UX 计划：城市总览页 + 深色模式

> 目标：让四座城市“被看见”，并给地图加上深色模式。不触碰 P2（示意化）的工作。
> 状态：阶段 0–2 已完成；阶段 3–5 待做。
> 关联：[颜色盘点](ux-color-inventory.md)、[P1a 自证](validation-p1a.md)。

---

## 一、已定决策（用户，2026-11-11）

| # | 决策 | 结论 |
| --- | --- | --- |
| D1 | 总览页位置 | **新增 `/cities/` 路由**，`/` 仍是上海（保住已发出去的旗舰链接） |
| D2 | 总览页缩略图 | **构建期生成 SVG 网络轮廓**（只画线路几何，不画底图） |
| D3 | 主题切换入口 | **页脚右侧按钮**，三态循环“跟随系统 → 浅色 → 深色” |
| D4 | 主题模型 | **三态 + localStorage 记忆**，遵循 `prefers-color-scheme` |
| D5 | 深色地图实现 | **调色板 + `setPaintProperty` 逐层改色**（保留相机与选中态） |
| D6 | 深色下线路颜色 | **不微调，严格沿用官图色**；对比不足只靠 casing 留白 |

---

## 二、阶段与状态

| 阶段 | 内容 | 工时 | 状态 |
| --- | --- | --- | --- |
| 0 | 颜色盘点 + `lib/theme.ts` 契约（`Palette`/`LIGHT`/`DARK`/`resolveTheme`） | 0.5 h | ✅ 本轮 |
| 1 | 界面深色地基：CSS token 化、`<html data-theme>` 注水脚本、`ThemeToggle` | 2.5 h | ✅ 本轮 |
| 2 | 地图深色：`buildStyle(palette)` 接线、`applyTheme()` 覆盖 21 层、对比度校准 | 3 h | ✅ 本轮 |
| 3 | 城市总览页：`/cities/`、卡片、SVG 缩略图脚本、三处入口 | 3 h | 待做 |
| 4 | 校验与自证：verify 增项、sitemap、主题持久化 E2E、`docs/validation-ux.md` | 2 h | 待做 |
| 5 | 发布：5 页进冒烟、线上深浅各复核一次 | 0.5 h | 待做 |

合计 **≈11.5 h**。

---

## 三、阶段 0 交付（已完成）

1. `web/lib/theme.ts`：18 字段 `Palette` 类型 + 浅/深两套值 + `paletteFor` / `resolveTheme` / `nextMode` / `THEME_STORAGE_KEY`。
2. `web/lib/mapStyle.ts`：删除本地 `PALETTE`，改为 `buildStyle(..., palette: Palette = LIGHT)`；**所有图层取色改走 `palette.*`**，浅色值与改动前完全相同（运行时回读逐值一致）。
3. `docs/ux-color-inventory.md`：地图 21 层/18 字段、界面 50 处颜色分组、阶段 1 的 20 个 CSS token 草案、D6 约束说明。

验证：`typecheck` 干净、`build` 成功、`verify` **87 项 / 4 城 / 0 失败**、导出体积仍 **7.91 MB**（证明只是重构，没有改动观感）。

---

## 五、阶段 1 交付（已完成）

1. `web/app/globals.css`：`:root` 改为 **44 个 `--c-*` token**（颜色 36 + 阴影 5 + 焦点环），旧变量（`--bg/--paper/--ink/--muted/--line/--panel`）保留为别名；新增 `:root[data-theme="dark"]` 覆盖块。界面里 **50 处颜色字面量全部改走 token**（脚本 `tokenize-css.mjs` 逐条断言命中数，最后再扫一遍 token 区之外的残留，为 0 才写盘）。
2. `web/app/layout.tsx`：`<head>` 内联 `THEME_INIT` 小脚本，首屏前把 `localStorage["subways-theme"]` 解析成 `documentElement.dataset.theme`，避免深色用户看到一闪而过的浅色；`viewport.themeColor` 给浅/深两值（按系统偏好）。
3. `web/components/ThemeToggle.tsx`：页脚三态按钮（跟随系统 → 浅色 → 深色），图标 + 当前模式文字，`aria-label` 带当前态；「跟随系统」时监听 `matchMedia` 的 change 事件。

### 三个真问题（都不是「写错了」而是环境行为）

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | 点按钮毫无反应，`localStorage` 一直空 | `.map-footer` 整体 `pointer-events: none`（原本只有「关于」按钮靠浏览器默认行为漏过事件） | `.theme-toggle { pointer-events: auto }` |
| 2 | 深色下输入框周围一圈刺眼白环、搜索结果按钮是纯白字 | UA 焦点环 + `button` 默认 `buttontext`（`color-scheme: dark` 下变纯白） | 输入框 `outline: none`、外框用 `--c-focus` + `--c-focus-ring`；`.search__item { color: inherit }` |
| 3 | 改了 CSS 却「看不出变化」，一度以为样式没生效 | 本地预览服务器不带缓存头，浏览器复用旧 HTML/CSS | 预览服务器加 `cache-control: no-store`（`E:\subway-data\probe-ux\serve.mjs`），并给 URL 加 `?v=N` |

另外补了一处窄屏回归：页脚多一个按钮后，648 px 下会溢出右边界 → `@media (max-width: 760px)` 里让统计胶囊独占一行并允许省略号，按钮换到第二行。

### 验证

- 浅色逐值不变：`--c-paper #f4f1ea`、`--c-bg #f4f2ee`、页脚 `rgba(255,255,255,0.94)`、标题 `rgba(255,255,255,0.86)`、搜索框 `#f4f1ea` / 边框 `#e2dccf`、关于按钮 `#fffdf8`，地图 `background #F4F1EA`、图层仍 **21** 个。
- 深色：`--c-paper #1a1a18`、页脚 `rgba(38,38,35,0.94)`、面板 `rgb(34,34,31)`、正文 `#e9e6df`。
- 三态循环实测：`system→light→dark→system`，`localStorage` 分别写 `light/dark/system`；刷新后保持（首屏脚本先生效）。
- 「跟随系统」解析：把 `matchMedia` 打桩成 dark 后切到 system，`data-theme` 变 `dark`（真实 bundle，不是源码推理）。
- `typecheck` 干净；`npm run verify` **87 项 / 4 城 / 0 失败**；导出 **7.93 MB**（+0.02 MB，gzip ≈1.48 MB）。

---

## 六、阶段 2 交付（已完成）

1. `web/lib/mapStyle.ts`：
   - 新增 `PALETTE_PAINT`（**20 条** `[layer, prop, keyof Palette]`）——深色地图的唯一清单；
   - 新增 `BILINGUAL_LAYERS`（3 个双语站名层）与 `bilingualField()`；
   - 新增 `applyPalette(map, palette)`：逐层 `setPaintProperty` + 对三个双语层 `setLayoutProperty("text-field", …)`。
2. `web/components/MapView.tsx`：
   - 首帧按 `documentElement.dataset.theme` 选 `paletteFor(theme)` 建 style（深色用户不会先看到一帧浅色地图）；
   - `MutationObserver` 监听 `data-theme` 变化 → `applyPalette()`，卸载时 `disconnect()`。
3. `web/app/globals.css`：maplibre 缩放控件跟随主题（`--c-ctrl-icon-filter` 浅 `none` / 深 `invert(0.86)`）。

### 两个真问题

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | 深色下右上角缩放按钮仍是一块白底 | maplibre 的样式表在 `globals.css` **之后**加载，同权重时我方规则被覆盖（`background`/`border-radius`/`box-shadow` 全丢，只有不冲突的 `filter` 生效） | 选择器加 `body` 前缀提到 `0,1,1`，并对 maplibre 自带的 `.maplibregl-ctrl-group:not(:empty)` 用同形选择器对齐 |
| 2 | 双语站名的英文副行在深色下仍是浅色 | 英文颜色写在 `text-field` 的 `format` 段里，属于 **layout** 而不是 paint，`setPaintProperty("text-color")` 改不到 | `applyPalette()` 里额外重设三个双语层的 `text-field`（`bilingualField(palette, withEn)`） |

### 验证

- 浅色逐值不变（运行时回读）：`background #F4F1EA`、`metro-line-casing #F4F1EA`、`station-transfer-halo #F4F1EA`、`station-dot #FFFFFF`、`station-label-major #222222`、`text-halo rgba(244,241,234,0.95)`、`water-fill #D7E4EF`、双语层英文色 `#6E6E6E`。
- 深色（同一次回读）：`background #1A1A18`、casing/halo `#1A1A18`、`station-dot #F2F0EB` / 环 `#8A8A83`、换乘点环 `#E9E6DF`、`station-label-major #F0EDE6` / halo `rgba(26,26,24,0.92)`、`station-label-minor #BDB8AF`、`water #16222B`、`sea #121C24`、`district-line #2B2B28`、双语英文色 `#8F8A81`。
- **切换不动相机**：切换前后 `zoom` 与 `center` 完全一致（`cameraSame: true`）。
- **线路颜色未变**（D6）：`metro-line.line-color` 仍是那组 `match` 表达式，20 条线一色不改。
- 缩放控件：深色下 `background rgb(38,38,35)`、`border-radius 10px`、投影为深色 token。
- `typecheck` 干净；`build` 成功（postbuild 释放 5.14 MB）；`verify` **87 项 / 4 城 / 0 失败**。
- 截图：`E:\subway-data\preview\ux2-sh-dark.png`（全城）、`ux2-sh-dark-z13.png`（站名与圆点）、`ux2-sh-dark-panel.png`（选中态 + 抽屉）。

---

## 四、验收（U-A1…U-A7）

| # | 项 | 口径 |
| --- | --- | --- |
| U-A1 | 五页可打开 | `/cities/` + 四城页，本地与线上均 200 |
| U-A2 | 总览数字一致 | 卡片上的线路/站/区间/换乘与 `cities.json` 逐字段相同（verify 断言） |
| U-A3 | 可读性 | 正文对比度 ≥ 4.5:1，图形边界 ≥ 3:1；深浅两主题都测 |
| U-A4 | 主题行为 | 三态可切、刷新保持、首帧不闪白；跟随模式下系统切换时自动跟随 |
| U-A5 | 深色地图 | 线路仍可区分、站名可读、底图不抢主体；21 层无“浅色残块” |
| U-A6 | 校验与体积 | `verify` 增项后全绿；导出 < 10 MB |
| U-A7 | 线上 | 0 个 4xx；五页 `map.loaded()` 全 true |

---

## 五、风险与对策

| 风险 | 对策 |
| --- | --- |
| 深色下官方深色线路与背景贴近（D6 不允许改色） | 加大 casing 与底色的一致性、提高站点点环对比；必要时只调 casing 宽度，不调线路色 |
| `setPaintProperty` 漏层 → 局部保持浅色 | 21 层清单写进代码常量，阶段 4 的 verify 断言清单长度 |
| 首帧闪白（FOUC） | 注水脚本内联在 `<head>`，不用 `useEffect` |
| 界面 50 处颜色改漏 | 阶段 1 完成后跑一次 `grep '#[0-9a-fA-F]{3,8}'`，要求只剩 `lib/theme.ts` 与 token 定义 |
| 缩略图体积膨胀 | 3 位小数 + 简化；单城 ≤ 40 KB，verify 断言总预算 |
| 新增页面漏 canonical/sitemap | 页面与 `sitemap.ts`、verify 断言同一次提交 |
