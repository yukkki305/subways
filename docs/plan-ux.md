# UX 计划：城市总览页 + 深色模式

> 目标：让四座城市“被看见”，并给地图加上深色模式。不触碰 P2（示意化）的工作。
> 状态：阶段 0 已完成；阶段 1–5 待做。
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
| 1 | 界面深色地基：CSS token 化、`<html data-theme>` 注水脚本、`ThemeToggle` | 2.5 h | 待做 |
| 2 | 地图深色：`buildStyle(palette)` 接线、`applyTheme()` 覆盖 21 层、对比度校准 | 3 h | 待做 |
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
