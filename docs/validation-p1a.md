# P1a-6 自证：前端多城化（6.0 → 6.6）

> 范围：把「单城上海」的前端改成四城站点（上海 / 广州 / 成都 / 合肥），并发布到 GitHub Pages。
> 本文件记录**每一子步的证据**与**A1–A8 验收结果**，不重复设计理由（见 `docs/plan-p1a.md` 与 `docs/decisions/`）。
> 生成时间：2026-11-11。

---

## 一、结论

| 项 | 结论 |
| --- | --- |
| 四城页面 | `/`、`/gz/`、`/cd/`、`/hf/` 四个静态页，构建期生成，`dynamicParams = false` |
| 数据 | 26 个文件 / 5.5 MB（`public/data/<code>/` + `cities.json`） |
| 校验 | `npm run verify` **87 项 / 4 城 / 0 失败**；`npm run test:search` **61 条 / 0 失败** |
| 导出 | **74 文件 / 7.91 MB**（gzip ≈1.47 MB），上限 10 MB（ADR 0005） |
| 线上 | 第 4 轮部署后四页 `map.loaded()` 全 true，`basemap` 源全在，冒烟 26/26 数据文件 200 |
| 上海回归 | 数据层 `regression.py --run` **16 一致 / 0 不一致 / 1 跳过**，本轮前端改动不触碰数据产物 |

---

## 二、四城现状（自 `public/data/cities.json`）

| 城市 | 页面 | 线路 | 分支 | 车站 | 区间 | 换乘 | 数据体积 | 底图 | 快照 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 上海 | `/` | 20 | 23 | 423 | 570 | 12 | 1,927 KB | 含海面 | 2026-11-01 |
| 广州 | `/gz/` | 19 | 22 | 320 | 393 | 3 | 1,795 KB | 轻底图 222 KB | 2026-11-03 |
| 成都 | `/cd/` | 16 | 17 | 364 | 454 | 4 | 1,219 KB | 轻底图 236 KB | 2026-11-03 |
| 合肥 | `/hf/` | 8 | 8 | 195 | 207 | 0 | 690 KB | 轻底图 232 KB | 2026-11-01 |

每城文件构成（`meta.json` 实测）：

- 上海：`lines 43 / station 424 / transfer 10 / segment 876 / basemap 484 / sea 90`（KB）
- 广州：`lines 39 / station 309 / transfer 3 / segment 1222 / basemap 222`
- 成都：`lines 35 / station 354 / transfer 3 / segment 590 / basemap 236`
- 合肥：`lines 18 / station 178 / transfer 0 / segment 262 / basemap 232`

> 广州 `segment.geojson` 是最大的单文件（1.22 MB）：19 条线路共 393 段真实几何。gzip 后 **170 KB**，仍属「单城首屏 ≤1.3 MB」可接受区间。

---

## 三、A1–A8 验收

| # | 验收项 | 结果 | 证据 |
| --- | --- | --- | --- |
| A1 | 四个页面都要能打开（本地 + 线上） | ✅ | 本地 `http://127.0.0.1:4399/subways/{,gz/,cd/,hf/}` 全 200；线上 `https://yukkki305.github.io/subways/{,gz/,cd/,hf/}` 全 200（部署冒烟 `页面 4/4`） |
| A2 | 每城线路数/站数与数据层一致 | ✅ | `verify` 的「线路数与城市配置一致」+「`meta.counts` 自洽」两项；`cities.json` 与四份 `meta.json` 逐字段一致（20-19-16-8 / 423-320-364-195） |
| A3 | 视野覆盖该城全部车站，缩放合理 | ✅ | `verify` 的「全部车站坐标落在 `sceneBbox` 内」；`fitBounds` 后实测 上海 9.71 / 广州 9.02 / 成都 9.56 / 合肥 10.11（见 `docs/plan-p1a.md` 第 4 条状态） |
| A4 | 核心功能可用（搜索、切换、点击详情、底图） | ✅ | `/gz/` 搜「广州塔」命中 3 号线 + APM 线；标题里的城市名可切换四城（`aria-current` 正确、Esc 还焦点）；点击站点开抽屉（线路 chips / 站序 / 换乘）；四页均渲染底图 |
| A5 | `verify` 四城全绿 | ✅ | **87 项 / 4 城 / 0 失败**；反向验证把 `hf.stations` 改成 999 → 恰好 1 项失败，改回即恢复 |
| A6 | 导出体积在预算内 | ✅ | 7.91 MB < 10 MB（ADR 0005）；gzip ≈1.47 MB；单城首屏 0.7–1.9 MB |
| A7 | 线上无 4xx | ✅ | 部署冒烟覆盖 4 页 + `cities.json` + 26 个数据文件，第 3 轮全部 200；浏览器复核 19 个资源请求 0 个 ≥400 |
| A8 | 上海回归不变 | ✅ | 数据层 16 一致 / 0 不一致 / 1 跳过；上海页 20 线 / 423 站、`sea-fill` 与海面仍在（`has_sea: true`） |

---

## 四、子步证据链

| 子步 | 产物 | 关键证据 | 提交 |
| --- | --- | --- | --- |
| 6.0 前置核对 | `docs/probe/p1a-6.md` | 四城前端四件 4.5 MB；底图仅上海；差距 G1–G10 带文件行号 | `646583a` |
| 6.1 数据目录 | `public/data/<code>/`、`cities.json` | 22 文件 / 4.83 MB；`--all` 幂等；旧扁平文件必须删（否则多背 1.8 MB） | `2a56279` `c69f53c` |
| 6.2 路由与元信息 | `lib/cities.ts`、`app/[city]/page.tsx` | 路由表 `○ / ● /gz ● /cd ● /hf`；四页 canonical 各指其页；`og:image` 曾被 `metadataBase` 解析成站点根 → 改绝对地址 | `9f9bff5` `d37b0df` `eee78db` |
| 6.3 城市切换器 | `components/CitySwitcher.tsx` | 菜单「N 条 · M 站」；Esc 还焦点、点外部关闭；672 px 下菜单曾压住搜索框 → `top: calc(100% + 56px)` | `7e7d5f8` |
| 6.4 底图多城化 | `pipeline/16_extract_light_basemap.py` | 广州首轮 1.02 MB / 2111 要素（珠江口 2056 段海岸线）→ 封顶后 227 KB / 75 要素；成都 242 KB、合肥 237 KB | `b3f97ff` |
| 6.5 校验矩阵 | `verify-build.mjs`、`test-search.mjs` | 87 项 / 4 城；`parseCityArg` 曾让矩阵静默退化成单城（加了 `explicit`）；ADR 0005 把上限抬到 10 MB | `e26ae1a` |
| 6.6 发布 | `deploy.mjs` | `pagesInBuild()` 曾把 `out/404/` 当城市；冒烟五轮 `[0,15,20,30,45]s`，第 3 轮通过（页面 4/4｜数据 26/26） | `c292a1e` |

---

## 五、复现命令

```powershell
# 0. 环境
$env:PYTHONUTF8 = '1'
$env:PATH = "E:\node;" + $env:PATH
$PY = "E:\subway-data\venv\Scripts\python.exe"

# 1. 数据侧（四城产物已入库，通常不必重跑）
cd E:\subway
& $PY pipeline\cityconfig.py --check        # 四城配置自检
& $PY pipeline\regression.py --run          # 上海全链路 + 17 项回归（16 一致 / 1 跳过）

# 2. 前端
cd E:\subway\web
npm run sync -- --all      # 四城数据 → public/data/<code>/ + cities.json
npm run verify             # 87 项 / 4 城
npm run test:search        # 61 条检索用例
npm run typecheck
npm run build              # 74 文件 / 7.91 MB

# 3. 本地按子路径预览（basePath=/subways）
npx serve out -l 4399      # 打开 http://127.0.0.1:4399/subways/

# 4. 发布 + 线上冒烟
npm run deploy             # 构建 + 推送 gh-pages + 五轮冒烟
```

---

## 六、已知局限（P1a 范围内接受）

1. **四城之外还是空白**：`/` 是上海，其余三城靠切换器；没有城市总览页，也没有全国视图（P1b 才做）。
2. **底图是「轻底图」不是真地图**：只有市界、邻市界、河道、水面、海岸线，没有路网与地名。视觉上够做地理参照，但用户无法靠它定位街道。真底图（PMTiles）仍未解（S0 探测 8：跨境带宽不可用）。
3. **广州 `segment.geojson` 1.22 MB**：单文件最大的那个，若 P1b 扩到 20 城需改成按线路分片。
4. **搜索只在当前城**：跨城搜「人民广场」不会给出上海结果（D3 决策：按城隔离，避免同名站误导）。
5. **换乘类型仍是人工判定**，且四条城合计 19 条换乘的 `walk_minutes` 全为 `null`（ADR R5：没有可靠来源就留空，不编数）。
6. **快照不实时**：四城分别是 2026-11-01 / 2026-11-03 的 OSM 快照，页脚已标注日期。

---

## 七、两条写进流程的教训

1. **「通过」要能被证明**：`verify` 之所以可信，是因为做过反向验证（故意改坏一个数，必须恰好失败 1 项）。同理，`parseCityArg` 那个 bug 的教训是——**校验脚本的输出必须打印「校验了几座城」**，否则矩阵退化成单城也看不出来。
2. **「发布成功」不等于「线上可用」**：Pages 重建有 30–60 s 延迟，冒烟轮询把「还没重建完」与「真的 404」分开；撞上 GitHub `:443` 断网（2026-11-11 08:19–08:34）时不要加大重试参数，先 `Test-NetConnection`，通了再跑一次。

---

## 八、截图

| 文件 | 内容 |
| --- | --- |
| `docs/screenshots/shanghai-overview.png` | 上海全城（P0 基线，用于回归对比） |
| `docs/screenshots/shanghai-downtown.png` | 上海市中心 z13（站名分层与共线段） |
| `docs/screenshots/station-panel.png` | 站点抽屉（静安寺，manual_merge 三站合一） |
| `docs/screenshots/about-panel.png` | 「关于这张地图」面板（六行数据说明） |

四城线上实拍与本地复核截图存放在仓库外的 `E:\subway-data\preview\`（`live-sh.png`、`live-hf.png`、`p1a6-4-gz.png`、`p1a6-4-cd.png` 等），不随仓库分发。
