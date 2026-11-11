# UX 阶段 0：颜色盘点与调色板契约

> 目的：在动深色模式之前，先把「颜色散落在哪些地方」数清楚，并把**唯一取色入口**定下来。
> 结论先给：**地图侧 21 个图层、18 个颜色字段已全部收进 `web/lib/theme.ts`；界面侧 50 处十六进制待收进 20 个 CSS token（阶段 1 做）。**
> 生成时间：2026-11-11。

---

## 一、盘点结论

| 位置 | 改动前的颜色数量 | 现状 |
| --- | --- | --- |
| `web/lib/mapStyle.ts` | 8 个字面量（`PALETTE`）+ 9 处散落字面量（`#FFFFFF`、`#6E6E6E`、`#222222`、`#4A4A4A`、`rgba(244,241,234,…)`、`rgba(255,255,255,.95)`、`#999999`） | **已全部改为 `palette.*`**，`buildStyle(..., palette = LIGHT)`，浅色下取色与改动前逐字节一致 |
| `web/app/globals.css` | 50 处（含 6 个 `:root` 变量） | **尚未收口**，阶段 1 改为 `var(--c-*)` |
| `web/app/layout.tsx` | 1 处 `themeColor: "#f4f2ee"` | 阶段 1 跟随主题（`viewport` 的 `themeColor` 支持 `media` 条件） |
| `web/components/StationPanel.tsx` | 1 处 `l?.colour ?? "#999"` | 这是**数据兜底色**，不是主题色；阶段 2 与 `palette.lineFallback` 对齐即可 |

---

## 二、地图侧：`Palette` 字段与取值

`web/lib/theme.ts` 定义的 18 个字段（`LIGHT` 为现值，`DARK` 为阶段 2 将使用值）：

| 字段 | 用途（图层） | 浅色 | 深色 |
| --- | --- | --- | --- |
| `paper` | `background`、`metro-line-casing`、`station-transfer-halo` | `#F4F1EA` | `#1A1A18` |
| `sea` | `sea-fill`（仅上海） | `#DCE6EF` | `#121C24` |
| `water` | `water-fill` | `#D7E4EF` | `#16222B` |
| `waterLine` | `water-line` | `#C6D8E8` | `#233642` |
| `coastline` | `coastline` | `#BFC9D2` | `#3A4650` |
| `district` | `district-line` | `#DBD5C8` | `#2B2B28` |
| `province` | `province-line` | `#B4AC9C` | `#4C4C45` |
| `casing` | `metro-line-casing`（独立字段，便于深色下微调而不动底色） | `#F4F1EA` | `#1A1A18` |
| `ink` | `station-selected` 描边、`station-hover-label` 文字 | `#2B2B2B` | `#E9E6DF` |
| `labelPrimary` | `station-label-major` / `bilingual*` 主层文字 | `#222222` | `#F0EDE6` |
| `labelSecondary` | `station-label-minor` 文字 | `#4A4A4A` | `#BDB8AF` |
| `labelSubtle` | 双语层的英文副行（`text-color`） | `#6E6E6E` | `#8F8A81` |
| `haloPrimary` | `station-label-major` / `bilingual*` 光晕 | `rgba(244,241,234,.95)` | `rgba(26,26,24,.92)` |
| `haloSecondary` | `station-label-minor` 光晕 | `rgba(244,241,234,.9)` | `rgba(26,26,24,.88)` |
| `hoverHalo` | 悬停标签光晕 | `rgba(255,255,255,.95)` | `rgba(26,26,24,.95)` |
| `dotFill` | `station-dot` / `station-dot-transfer` 填充 | `#FFFFFF` | `#F2F0EB` |
| `dotRing` | 普通站环 | `#6E6E6E` | `#8A8A83` |
| `dotRingTransfer` | 换乘站环 | `#2B2B2B` | `#E9E6DF` |
| `lineFallback` | `colorExpression` 的兜底色（数据异常时才出现） | `#999999` | `#6E6E6E` |

函数契约（阶段 0 已落地）：

```ts
export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";
export function paletteFor(theme: ResolvedTheme): Palette;
export function resolveTheme(mode: ThemeMode, systemPrefersDark: boolean): ResolvedTheme;
export function nextMode(mode: ThemeMode): ThemeMode;
export const THEME_STORAGE_KEY = "subways-theme";
```

---

## 三、界面侧（`globals.css`）50 处 → 分组

### 3.1 已有变量（6 个，直接被各处 `var()` 引用）

| 变量 | 现值 | 深色方向 |
| --- | --- | --- |
| `--bg` | `#f4f2ee` | 与 `palette.paper` 同步（`#1A1A18`） |
| `--ink` | `#2b2b2b` | `#E9E6DF` |
| `--muted` | `#6b6b6b` | `#A8A39A` |
| `--line` | `#dcd8d0` | `#35352F` |
| `--panel` | `rgba(255,255,255,.86)` | `rgba(32,32,29,.9)` |
| `--shadow-card` | 两层黑阴影 | 深色下阴影几乎不可见，需换成“1px 描边 + 更深阴影” |

### 3.2 面板与卡片（9 处）

| 选择器 | 现值 | 拟用 token |
| --- | --- | --- |
| `.map-loading` 遮罩 | `rgba(244,241,234,.55)` | `--c-scrim` |
| `.map-loading__card` | `rgba(255,255,255,.94)` + 黑阴影 | `--c-surface` / `--c-shadow-lg` |
| `.station-panel` | `rgba(255,255,255,.96)` + 黑阴影 | `--c-surface` / `--c-shadow-lg` |
| `.search__list` | `#fff` + `rgba(43,43,43,.16)` | `--c-surface` / `--c-shadow-md` |
| `.about` | `#fffdf8` + 暖黑阴影 | `--c-surface-warm` / `--c-shadow-lg` |
| `.about-button` | `#fffdf8` / `#ded7c8` / `#5b5548` | `--c-surface-warm` / `--c-border` / `--c-text-body` |
| `.map-footer span` | `rgba(255,255,255,.72)` | `--c-surface` |
| `.chip` | `#f4f2ec` | `--c-surface-2` |
| `.station-panel__close:hover` | `#f0ede6` | `--c-surface-2` |

### 3.3 文字与描边（10 处）

| 选择器 | 现值 | 拟用 token |
| --- | --- | --- |
| `.search__box` | `#f4f1ea` / `#e2dccf` / `#b9b2a2`(focus) | `--c-paper` / `--c-border` / `--c-border-strong` |
| `.search__input` | `var(--ink)` | `--c-text` |
| `.search__input::placeholder`、`.search__clear` | `#9c9486` | `--c-text-placeholder` |
| `.search__icon`、`.search__sub`、`.search__kind`、`.search__empty`、`.about__close`、`.about__kv dt` | `#8b8374` | `--c-text-subtle` |
| `.about__lead`、`.about__kv dd` | `#3f3a32` | `--c-text-body` |
| `table.seq td`、`ul.transfers li`、`.about__foot` | `#f0ece3` / `#eee7d8` | `--c-border-soft` |
| `.search__kind` 边框 | `#e4ded1` | `--c-border-soft` |
| `.about-button:hover` | `#c9c0ad` | `--c-border-strong` |
| `:focus-visible` outline（3 处） | `#1f5fa8` | `--c-focus` |
| `button.link`、`.about__foot a` | `#1f5fa8` | `--c-accent` |

### 3.4 状态色（11 处）

| 选择器 | 现值 | 拟用 token |
| --- | --- | --- |
| `.map-loading__dot` | `#c0392b` + 红晕 | `--c-danger` |
| `.map-loading.is-error .map-loading__dot` | `#8c1d1d` | `--c-danger-strong` |
| `.map-loading.is-error .map-loading__title` | `#8c1d1d` | `--c-danger-strong` |
| `.badge` | `#eef1f4` / `#45505c` | `--c-badge-bg` / `--c-badge-ink` |
| `.badge.conf-high` | `#e6f0e6` / `#2f6b34` | `--c-ok-bg` / `--c-ok-ink` |
| `.badge.conf-medium` | `#fdf3e0` / `#8a6212` | `--c-warn-bg` / `--c-warn-ink` |
| `.badge.conf-low` | `#fde9e9` / `#8c2f2f` | `--c-bad-bg` / `--c-bad-ink` |
| `.search__title mark` | `#ffe9a8` | `--c-mark` |
| `.search__sub mark` | `#fff2c9` | `--c-mark-2` |
| `.city-switch__item.is-current` 徽标 | `#fff` on 深底 | `--c-on-invert` |
| `.city-switch__btn:hover`、`.city-switch__item:focus-visible`、`.is-current` | `rgba(0,0,0,.055/.045)` | `--c-hover` / `--c-active` |

---

## 四、阶段 1 的 token 草案（20 个）

```css
:root {
  --c-paper: #f4f1ea;        /* 与地图 paper 同步，注水脚本切换 */
  --c-bg: #f4f2ee;
  --c-surface: rgba(255, 255, 255, 0.94);
  --c-surface-2: #f4f2ec;
  --c-surface-warm: #fffdf8;
  --c-scrim: rgba(244, 241, 234, 0.55);
  --c-border: #e2dccf;
  --c-border-soft: #f0ece3;
  --c-border-strong: #b9b2a2;
  --c-text: #2b2b2b;
  --c-text-body: #3f3a32;
  --c-text-muted: #6b6b6b;
  --c-text-subtle: #8b8374;
  --c-text-placeholder: #9c9486;
  --c-accent: #1f5fa8;
  --c-focus: #1f5fa8;
  --c-danger: #c0392b;
  --c-danger-strong: #8c1d1d;
  --c-hover: rgba(0, 0, 0, 0.055);
  --c-active: rgba(0, 0, 0, 0.045);
  --c-mark: #ffe9a8;
  --c-shadow-md: 0 2px 8px rgba(0, 0, 0, 0.06), 0 20px 48px rgba(0, 0, 0, 0.08);
}
```

深色覆盖写在同一文件的 `:root[data-theme="dark"]` 里；`--c-paper` 必须与 `DARK.paper` 相等，阶段 4 用 verify 断言这条一致性。

---

## 五、D6 约束：线路色一律不动

用户决策 **D6 = 不微调官图色**。因此：

1. `theme.ts` **不含任何线路色**，线路色只来自 `lines.json` 的 `colour`；
2. 深色下若深蓝（2 号线 `#6A3F8F`… 实际以数据为准）、深红（1 号线）与背景贴近，唯一允许的手段是 **casing 留白**（`palette.casing` 取底色系）与站点点环对比；
3. AGENTS §12「颜色与官方线路图一致」的口径不变——深色模式不改变任何一条线的 `colour` 值；
4. 阶段 4 的 verify 增加一条断言：`lines.json` 的 `colour` 在深浅两主题下完全相同（其实只与数据有关，加断言是为了防止有人以后在主题层动了线路色）。

---

## 六、地图层 id 清单（阶段 2 逐层设色用）

```
background
sea-fill
water-fill
coastline
water-line
district-line
province-line
metro-line-casing      ← 深色下最关键（留白靠它）
metro-line
maglev-line
apm-line
station-transfer-halo  ← 第二关键（把换乘点下的线“挖”干净）
station-dot
station-dot-transfer
station-selected
station-hover-label
station-label-major
station-label-minor
station-label-bilingual
station-label-long-zh
station-label-bilingual-long
```

共 **21 层**。阶段 2 的 `applyTheme()` 必须覆盖全部 21 层；阶段 4 的 verify 会断言这个清单长度，防止以后新增图层时漏配。

---

## 七、阶段 0 验证记录

| 检查 | 结果 |
| --- | --- |
| `tsc --noEmit` | 干净 |
| `npm run build` | 成功，路由 `○ / ● /gz ● /cd ● /hf`，postbuild 仍释放 5.14 MB |
| `npm run verify` | **87 项 / 4 城 / 0 失败**；导出 **7.91 MB**（与重构前完全一致，说明只是搬家） |
| 运行时回读（上海页 `getPaintProperty`） | `background #F4F1EA`、`metro-line-casing #F4F1EA`、`station-transfer-halo #F4F1EA`、`station-dot circle-color #FFFFFF`、`station-label-major text-color #222222`、`text-halo-color rgba(244,241,234,.95)` —— **与重构前逐值相同** |
| 图层数 | 21 层，与重构前一致 |
| 截图 | `E:\subway-data\preview\ux0-sh.png`（与 P1a-6 的上海页肉眼一致） |

## 阶段 1 落地（界面 token 化，2026-11-11）

- 界面 50 处字面量 → `--c-*` token，映射关系与命中次数见 `E:\subway-data\probe-ux\tokenize-css.mjs` 的输出（50 组：`#8b8374`×6、`#1f5fa8`×4、badge/ok/warn/bad 各 2、危险色含 3 段 keyframes 等）。
- `:root` 现在是 **44 个 `--c-*`**：颜色 36（paper/bg/panel/surface×3/scrim/mask/line/border×3/text×5/accent/focus/focus-ring/danger×3/hover/active/mark×2/on-invert/badge×2/ok×2/warn×2/bad×2）+ 阴影 5 + 其余为旧名别名。
- 地图调色板（`lib/theme.ts` 的 `Palette`）与界面 token 是**两套**：前者喂给 MapLibre 的 paint 属性，后者是 CSS；两边唯一必须一致的量是 `paper`（`--c-paper` 对 `Palette.paper`），阶段 4 的 verify 会断言这一点。
- 深色取值原则：纸面 `#1a1a18`（暖黑，不用纯黑以免与线路色冲突）、文字 `#e9e6df`（不是纯白）、强调 `#7fb2ea`、danger `#e2725b`；阴影统一加深并降低透明度。
