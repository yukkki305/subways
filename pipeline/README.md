# pipeline：数据管道

本目录是「原始数据 → 可提交产物」的全部代码。前端不联网取数，所有数据都从这里生成。

- 工作契约见仓库根目录 `AGENTS.md`（尤其第 5、7、8、15 节）
- 每个数据文件的来源、许可、截止日期，写在 `data/README.md`

## 环境

| 项 | 值 |
| --- | --- |
| 解释器 | `E:\subway-data\venv\Scripts\python.exe`（Python 3.14.6，仓库外，不进 git） |
| 关键依赖 | geopandas 1.2.0 / shapely 2.2.0 / pyproj 3.8.0 / pyogrio 0.13.0 / pyosmium 4.3.2 |
| 必备环境变量 | `PYTHONUTF8=1`（否则 Windows 控制台中文乱码） |
| 已知坑 | `fiona` 无 cp314 wheel，一律用 `pyogrio`；`shapely.ops.transform()` 已废弃，用 `shapely.transform()` |

## 一条命令

```powershell
$env:PYTHONUTF8 = '1'
E:\subway-data\venv\Scripts\python.exe pipeline\run_s1.py
```

`run_s1.py` 编排可执行的 5 步（S1-2～S1-6），S1-1 与 S1-7 是人工步骤。**当前状态：S1-1～S1-7 全部完成。**

| 用法 | 作用 | 实测 |
| --- | --- | --- |
| `run_s1.py --list` | 列步骤表，并标出哪些产物已存在 | 即时 |
| `run_s1.py` | 全跑（会重新下载 327 MB） | ≈ 8–10 分钟（下载主导） |
| `run_s1.py --from S1-3` | 跳过下载，从抽取开始 | **95.4 s**（S1-3 68.0 / S1-4 11.1 / S1-5 0.3 / S1-6 16.0） |
| `run_s1.py --only S1-6` | 只重跑归属 | 16.0 s |

编排器的约定：不并发（下载与解析会互相抢资源）、不缓存（每步幂等，重跑即覆盖）、失败即停（不自动重试，报错里给出「从哪步重跑」）。

**幂等性实测**：整套重跑后，`relation-index.json` 除 `generated_at` / `attribution_generated_at` / `changes` 外与上一版逐字段一致，`changes` 变为全空（说明没有实质变更）；`attribution-report.json` 与 `docs/conflicts.md` 只变生成时间。

## S1 步骤与脚本映射

| 步骤 | 脚本 | 输入 | 输出 | 状态 |
| --- | --- | --- | --- | --- |
| S1-1 目录与环境 | —（本文件 + `.gitignore`） | — | 目录骨架 | ✅ 完成 |
| S1-2 快照下载与归档 | `01_fetch_snapshot.py` | `download.openstreetmap.fr/extracts/asia/china/` | `E:\subway-data\snapshots\<date>\*.osm.pbf`；`data/snapshots/<date>/{*.sha256,manifest.json}` | ✅ 完成（20261101 五省：上海 29.7 MB / 江苏 89.4 MB / 浙江 99.0 MB / 安徽 46.3 MB / 山东 78.9 MB，合计 327.4 MB） |
| S1-3 轨道关系抽取 | `02_extract_transit.py` | 上一步的 PBF | `data/raw/transit-relations.json`（不提交） | ✅ 完成（五省 287 条关系 / 上海子集 65 条 / 6,129 个 stop 节点 / 未解析坐标 4） |
| S1-4 底图要素抽取 | `03_extract_basemap.py` | 同 PBF | `data/processed/basemap/shanghai-basemap.geojson`（提交，目标 <5 MB） | ✅ 完成（22 要素 / 0.47 MB / 46.6 s） |
| S1-5 关系清单与指纹 | `04_track.py` | S1-3 产物 | `data/processed/relation-index.json`（提交） | ✅ 完成（287 条 / 0.56 MB / 两次运行全程可复现） |
| S1-6 归属校验 | `05_attribution.py` | S1-3 产物 + 五省 PBF 的行政界 | `data/processed/attribution-report.json`、`docs/conflicts.md`，并回填 `relation-index.json` 的 `city`/`province` | ✅ 完成（287 条里 241 条定案；上海关系 1,129 站市内、6 站界外且全部判到苏州；详见下文） |
| S1-7 汇总与提交 | —（人工） | 以上全部 | `data/README.md` 三问表 + 提交 | ✅ 完成 |

## S1-6 归属：口径与已知缺口

省份与城市都是**点面判定**（`shapely.contains_xy`），不是手写台账：

| 层级 | 用哪个面 | 实测面积 | 备注 |
| --- | --- | --- | --- |
| 上海市 | L4 `913067` | 16,229.5 km²（2 部件，含海域） | 官方陆地 6,340 km²，差额是海域 |
| 浙江省 | L4 `553302` | 144,895.7 km²（单文件只有 239/241 way，必须跨 extract 并集） | 含海域 |
| 安徽省 | L4 `913011` | 141,251.4 km² | 官方 14.01 万 km²，吻合 |
| 江苏省 | **无可用 L4** | 地级市并集 11/13 → 81,289.5 km² | 江苏 L4 的 374 个 way 全都在五省 PBF 里，仍拼不闭合（23 个碎片、309.4 km²）；缺与山东/安徽共边的节点，加了两省仍未闭合 |
| 城市 | L5 地级市（上海用 L4） | 38 个可用 | 江苏另配 13 市固定名称表，市名命中即判江苏省 |

**已知缺口（46 条关系未定，全部写在 `docs/conflicts.md`）：**

- **山东 39 条**（济南、青岛、济宁云巴/孔孟快线）：山东省面同样拼不闭合（4.0 km² / 8 个碎片），其地级市面也一并缺；补齐需要河北、河南的 extract —— 按用户 m01450「不扩大范围」暂不下载。
- **江苏南通 4 条**（1 号线平潮↔振兴路、2 号线幸福↔先锋，共 56 站）：南通市面 81 个 way 拼不闭合（长江口边界被 extract 裁切）；盐城无轨道线路，不影响。
- **3 条无站点母关系**（上海地铁1号线 `6800211`、嘉兴有轨T1 `15711260`、济南轨交9号线 `21045624`），S2 建模时过滤。

**已验证的关键事实：**

- 上海 11 号线「迪士尼→花桥」34 站在上海、3 站在苏州市（`5611110` / `5611111`）；
- 苏州 11 号线「横山↔花桥」52 站全判为苏州市（`16025193` / `16097172`）；
- 磁浮线 2 条关系 2 站全部判为上海市（`443258` / `9786758`）；
- 上海关系内 1,129 个站落在上海市面内，界外只有 6 个（花桥段 3 站 × 双向重复），**「界外且未定」为 0**。

## S1-4 底图：口径与已知局限

产物 `data/processed/basemap/shanghai-basemap.geojson` 共 22 个要素，五个 `layer`：

| layer | 要素数 | 内容 | 简化容差 |
| --- | --- | --- | --- |
| `district_boundary` | 16 | 上海 16 个区界（`admin_level=6` 关系，描边线） | 25 m |
| `province_boundary` | 1 | 上海市界（关系 `913067`，**含海域边界**） | 8 m |
| `water` | 1 | 淀山湖 62.27 km²（关系 `1122227`，跨省，需 shanghai + jiangsu 两份 PBF） | 25 m |
| `water_line` | 3 | 长江口中心线 443.0 km、吴淞江（苏州河）110.6 km、黄浦江 84.8 km | 8 m |
| `coastline` | 1 | 130 段海岸线 884.4 km（含岛屿） | 8 m |

**三条不能改的口径**：

1. **不产出陆地填充面**。OSM 的 16 区界多边形并集是 16,204.7 km²（官方陆地 6,340.5 km² 的 2.56 倍），因为区界把海域也算进去了；而 130 段 coastline 不闭合，反推陆地失败（`bbox − 海面 = 446.9 km²`）。所以 P0 底图 = 单色背景（背景即陆地）+ 水面 + 行政界线，**不画假海岸**，也不做「陆面积 = 6,340 km²」这类验收。
2. **河流画中心线加粗，不伪造江面多边形**。黄浦江的水面关系 `197357` 只有上游 1 段 2.73 km²，长江水面关系 `1999842` 的 bounds 在江阴—南通上游、不在上海视野。
3. **苏州河在 OSM 的正式名称是吴淞江**。命名 way 只覆盖到 lon 121.381，市中心段在 `type=waterway` 关系 `9064903` 里，成员 way 无 name。`feature.alias` 记了「苏州河」，前端若要按「苏州河」检索需读这个字段。

## S1-5 关系清单：指纹口径与变更分类

产物 `data/processed/relation-index.json`（225 条关系 / 436,319 B），每条关系一条档案，三个指纹各管一类变化：

| 指纹 | 算法 | 检出什么 |
| --- | --- | --- |
| `fingerprint` | 成员按 `type\|role\|ref[|lon6\|lat6]` 排序后 sha256 | 走线改动、成员增删（节点坐标只在已解析时参与） |
| `stops_hash` | 按成员顺序的站名序列 sha256 | 站序变化、站改名、插站/减站 |
| `tag_hash` | 按键排序的标签 sha256（排除 `payment:*`、`opening_*`、`check_*`） | 改名、改色、改 operator/network、改 from/to |
| `index_fingerprint` | 全表 `id:fingerprint` 排序后 sha256，**不含 `generated_at`** | 整表可复现性 |

**为什么必须比指纹而不是文件哈希**（探测 4）：Overpass/PBF 的对象输出顺序不稳定，同一查询原始字节的 SHA-256 三次三值；规范化后指纹三次一致。

**环线判据**（OSM 没有 loop 标签，只有两种写法，且「没有 from/to」不等于环线）：

- `from == to`：上海 4 号线（`from=to=宜山路`，name 写内圈/外圈）
- 站序首尾同名：松江有轨电车 2 号线（`松江大学城 -> … -> 松江大学城`）
- 反例：苏州 7 号线、高新有轨都缺 `from`/`to` 但首末站不同；上海地铁 1 号线母关系 `6800211` 一个站都没有

`loop_evidence` 字段记的判据来源。当前 4 条环线：`196854`/`7448423`（4 号线内/外圈）、`16159672`/`16159673`（松江有轨 2 号线两交路）。

**变更检测**：`04_track.py` 默认读自身旧版做增量比对（`--no-prev` 关闭，`--prev X --raw Y --out Z` 可做离线演练）。五类结果：`added` / `removed` / `tag_changed` / `stops_changed` / `members_changed`。消失的关系**保留档案**（`status: removed`，保留 `first_seen`/`last_seen`），便于回溯「哪条线没了」——这正是探测 4 里 54 → 52 那种「不是线路增减」的情况要看的东西。

**演练证据**（改坏一份 raw 再比）：改名一个站 → `stops_changed` 1 条并列出 `added:["人民广场站"] removed:["人民广场"]`；改一个 `colour` → `tag_changed` 1 条并给出 `["#57C45B","#FF00FF"]`；删 2 个成员 → `members_changed` + `stops_changed`；删关系 → `removed`；克隆新 id → `added`。

**`city` 字段一律 `null`**：城市归属由 S1-6 用 `admin_level=4` 精确边界填，不在这一步猜（探测 10 已证 bbox 与粗边界都不可靠）。


## S2 步骤与脚本映射（进行中）

规则见 `docs/decisions/0001-modeling-rules.md`。S2 的目标是把 65 条上海关系收敛成 20 条 `line` + `branch` + `station` + `segment` + `transfer`。

| 步骤 | 脚本 | 产物 | 状态 |
| --- | --- | --- | --- |
| S2-1 规则定稿 | —（ADR） | `docs/decisions/0001-modeling-rules.md` | ✅ R0–R8 九节 |
| S2-2 关系归一 · 第一步 骨架导出 | `06_export_mapping.py` | `data/manual/shanghai-relation-mapping.csv`（65 行 × 16 列，后 4 列为空待填） | ✅ 完成 |
| S2-2 关系归一 · 第二步 人工判定 + 校验 | 人工填 CSV → `07_check_mapping.py` | 同上 CSV 的 `decide` / `target_line` / `target_branch` / `note`；`--write-md` 重渲 `docs/mappings/shanghai-relations.md` | ✅ 65/65 行已填，六项校验通过 |
| S2-2 关系归一 · 第三步 生成 lines.json | `08_build_lines.py` | `data/processed/shanghai/lines.json`（20 条 line / 23 个 branch，41 KB） | ✅ 完成 |
| S2-3 站点抽取与合并 | `09_build_stations.py` | `data/processed/shanghai/station.json`（441 KB）+ `docs/mappings/station-merge-decisions.md` | ✅ 430 站 / 592 站次 |
| S2-4 区间切分 | 待定（先打样 2 / 10 / 4 号线） | `segment.geojson` | 待做 |
| S2-5 换乘 | 待定 | `transfer.json` | 待做 |
| S2-6 属性补全 | 待定 + `data/manual/shanghai-lines.csv` | 回填各表 | 待做 |
| S2-7 校验与提交 | `09_validate.py`（待写） | 八项校验全过 | 待做 |

### S2-2 的两条命令

```powershell
$env:PYTHONUTF8 = '1'
$PY = 'E:\subway-data\venv\Scripts\python.exe'

# 第一步：生成骨架（CSV 已有判定时会拒绝覆盖，确需重建加 --force）
& $PY pipeline\06_export_mapping.py

# 第二步：校验填好的表，并重渲人可读文档
& $PY pipeline\07_check_mapping.py --allow-pending --write-md
```

`07_check_mapping.py` 六项校验：行数 = S1-5 上海子集；`decide` 取值合法；每条 line 恰好一个 `-main` 保留；`丢弃` 必须写 `note`；`合并` 指向真实 branch 且站序是其子集；每个 branch 至少 1 条保留。`--allow-pending` 时，仍有待决策行的线路降级为提示（当前只有 `sh-line-11`）。

`06_export_mapping.py` 的两个细节：

- **`hint` 列是机器提示，不是结论**。现在给六类线索：`?非上海：<市名>`、`?母关系：0 站`、`?服务变体`（普通车/大站车/直达车/大站快车/区间）、`?环线`、`?同线多交路（ref=N 共 M 条）`、`?同站集：<对向关系 id>`（站名集合完全相同的两条，多为同一线路的双向）。
- 65 行里 **60 行有孪生提示**，5 行没有：母关系 `6800211`；16 号线直达车 `13618691`（12 站）与 `13618692`（2 站）——OSM 里这个直达车关系一个方向只登记了龙阳路、滴水湖两站，属数据缺陷；松江有轨 2 号线 `16159672`（42 站）与 `16159673`（41 站）——两个方向的终点记录不同且站数不等。

### S2-2 判定结果（2026-11-01，65/65 行）

保留 23 条关系 → **20 条 line / 23 个 branch**；合并 29 条；丢弃 13 条（母关系 1 + 机场捷运 4 + 松江有轨 4 + 苏州 11 号线 4，依据 ADR R0/R1 + D2）。

支线共三条：5 号线 `-b1`（闵行开发区↔莘庄，11 站）、10 号线 `-b1`（航中路↔基隆路，33 站）、11 号线 `-b1`（迪士尼↔花桥，37 站，含昆山 3 站 `city=苏州市`）。

4 号线为环线：`is_loop=true`，26 站，`loop_start=宜山路`（站序已旋转到从宜山路开始，末站上海体育馆回到起点）。

`08_build_lines.py` 只产出线路与支线这一层：站序暂存**站名**，S2-3 再解析成 OSM 节点并分配 `sh-station-*` 稳定 id。产出 `data/processed/shanghai/lines.json`（41 KB），两次重跑除 `generated_at` 外逐字节一致。

### S2-3 站点抽取与合并（2026-11-01）

一条命令：

```powershell
& $PY pipeline\09_build_stations.py
```

做的事：按 `lines.json` 的权威站序，把每条 branch 在 `transit-relations.json` 里的 `stop*` 角色节点取出来对齐成「站次（slot）」；再按 ADR R4 的三档口径把同名同城的站次合并成 `station`。

| 口径 | 判据（同一站名、同一城市的站次整体跨度） | 处理 | 本次命中 |
| --- | --- | --- | --- |
| `auto_150` | ≤150 m | 合并为一站，无需复核 | 96 组（另 306 个单站次站不涉及合并） |
| `auto_review` | 150–300 m | 合并为一站，`needs_review=true` | 25 组 |
| `split_review` | >300 m | 不合并，组内按 150 m 连通分量拆站，并登记换乘候选 | 12 组 → 29 个站 |

产物：`data/processed/shanghai/station.json`（441 KB）+ `docs/mappings/station-merge-decisions.md`（逐组判定表）。

数字：**430 个站 / 592 个站次 / 多线站 80 个 / 待复核 54 个 / 拆分 12 组 / 换乘候选 22 条**；城市分布 上海市 427、苏州市 3（昆山段的兆丰路、光明路、花桥）。校验：23 条 branch 的站次序号连续且与 `lines.json` 的 `stop_count` 逐条相等；站 id 唯一；每条 branch 在每个站最多出现一次。

`split_review` 的 12 组是 ADR R4 的直接结果，全部登记为换乘候选（S2-5 里补 `type` 与 `walk_minutes`）：国家会展中心 793 m、浦东南路 647 m、曹杨路 434 m、娄山关路 445 m、上海南站 436 m（1/3/15 三站）、上海火车站 360 m（1/3/4 三站）、陆家嘴 359 m（2/14）、静安寺 325 m（2/7/14 三站）、南京西路 322 m（2/12/13 三站）、宜山路 320 m、桂林路 312 m、徐家汇 301 m。

已知小缺口：爱辉路、长江西路、通南路三站在 OSM 里没有 `name:en`，`name_en` 留 `null`。

## 目录分工

| 目录 | 内容 | 是否提交 |
| --- | --- | --- |
| `data/raw/` | 抓下来的中间 JSON（关系、节点、几何） | ❌ |
| `data/cache/` | 可重建的缓存 | ❌ |
| `data/manual/` | 人工维护的判定表（映射表、属性表），随快照更新 | ✅ |
| `data/processed/` | 清洗后的 GeoJSON / JSON，前端直接读 | ✅ |
| `data/snapshots/<date>/` | 快照的 `.sha256` 与 `manifest.json` | ✅（PBF 本体在仓库外） |
| `E:\subway-data\snapshots\<date>\` | 原始 PBF 与原始抓取结果 | 仓库外，不进 git |

## 失败触发器（出现即停，向用户汇报）

| 情况 | 处理 |
| --- | --- |
| PBF 下载失败或中断 | 退避重试 3 次；仍失败 → 停下问用户，不擅自换源 |
| 上海轨道关系数 <60 或多出 >5 | 停下查原因（镜像切法可能变了） |
| 归属表仍有 >5 个上海站判为界外 | 停下查边界是否缺部件（崇明 / 长兴 / 横沙） |
| 底图简化后仍 >5 MB | 停下，缩小水系抽取范围 |

## 编码约定

- 文件一律 **UTF-8 无 BOM**（PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写 BOM，Python 侧读到会异常）
- 坐标一律 `[经度, 纬度]`（GeoJSON 顺序），全链路 WGS-84 / EPSG:4326
- 中间产物里的时间戳字段不得参与算指纹，否则重跑不可比
