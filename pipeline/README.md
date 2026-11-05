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


## S4 脚本

| 步骤 | 脚本 | 输出 |
| --- | --- | --- |
| S4-4 海面 | `14_extract_sea.py` | `data/processed/basemap/shanghai-sea.geojson`（1 个面 / 24,829.3 km²） |

`14_extract_sea.py` 读五省 PBF 的 `natural=coastline`，与 bbox 边框 polygonize 后用「bbox 减陆地」得到海面，岛屿自动成为洞。约 55 s（含五份 PBF 扫描）。

## S2 步骤与脚本映射（进行中）

规则见 `docs/decisions/0001-modeling-rules.md`。S2 的目标是把 65 条上海关系收敛成 20 条 `line` + `branch` + `station` + `segment` + `transfer`。

| 步骤 | 脚本 | 产物 | 状态 |
| --- | --- | --- | --- |
| S2-1 规则定稿 | —（ADR） | `docs/decisions/0001-modeling-rules.md` | ✅ R0–R8 九节 |
| S2-2 关系归一 · 第一步 骨架导出 | `06_export_mapping.py` | `data/manual/shanghai-relation-mapping.csv`（65 行 × 16 列，后 4 列为空待填） | ✅ 完成 |
| S2-2 关系归一 · 第二步 人工判定 + 校验 | 人工填 CSV → `07_check_mapping.py` | 同上 CSV 的 `decide` / `target_line` / `target_branch` / `note`；`--write-md` 重渲 `docs/mappings/shanghai-relations.md` | ✅ 65/65 行已填，六项校验通过 |
| S2-2 关系归一 · 第三步 生成 lines.json | `08_build_lines.py` | `data/processed/shanghai/lines.json`（20 条 line / 23 个 branch，41 KB） | ✅ 完成 |
| S2-3 站点抽取与合并 | `09_build_stations.py` | `data/processed/shanghai/station.json`（441 KB）+ `docs/mappings/station-merge-decisions.md` | ✅ 430 站 / 592 站次 |
| S2-4 区间切分 | `10_build_segments.py` | `data/processed/shanghai/segment.geojson`（570 段 / 792 KB） | ✅ 23 条 branch 全覆盖 |
| S2-5 换乘 | `11_build_transfers.py` | `data/processed/shanghai/transfer.json`（22 条 / 17 KB）+ `docs/mappings/transfer-decisions.md` | ✅ 12 组候选全落，10 条待复核 |
| S2-6 属性补全 | `12_build_attributes.py` + `data/manual/shanghai-lines.csv` | 回填 `lines.json`（颜色/里程/开通年/运营方/英文名）+ `docs/colors.md` | ✅ 20 条齐全，颜色 4 条改用官图采样 |
| S2-7 校验与提交 | `13_validate.py` | `docs/validation-s2.md` | ✅ 八项全过（含确定性重跑） |

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

### S2-5 换乘（`11_build_transfers.py`）

S2-3 产出的 22 条换乘候选（12 组同名多站）落成 `transfer.json`。三条口径：

1. **只表达未合并的两站**（ADR R5）—— 合并成一站的多线站不产生 transfer。
2. **`type` 是人工判定，不是几何推导**。OSM 没有换乘类型字段，站内通道制图也太稀疏：本次扫描候选站附近带
   `tunnel/covered/indoor/level` 的步行要素只有 113 条，其中静安寺、南京西路、曹杨路、桂林路、国家会展中心、
   浦东南路的 A 侧**一个步行节点都没有**。把候选两站 60 m 邻域建图做连通判定，只能得到 8 对「连通」，
   但连通也分不清「站内通道」与「出站换乘」——上海火车站（出站换乘）在图上同样连通。
   → 类型写在脚本的 `GROUP_TYPES` 里，带 `confidence`；改类型只改这张表、重跑，不手改产物。
3. **`walk_minutes` 一律 `null`**（ADR R7：没有可靠来源就不编数字）。

`type_confidence` 为 `medium`/`low` 的记录标 `needs_review: true`，明细与待办清单见
`docs/mappings/transfer-decisions.md`。当前 22 条里 12 条判「通道」、10 条判「出站换乘」，其中 **10 条待复核**。

### S2-6 属性补全（`12_build_attributes.py`）

```powershell
& $PY pipeline\12_build_attributes.py
```

**里程**：`length_km` 是该线所有 branch 几何 **先并集再量长**（dissolve 掉支线与主线的重叠段），投影到
UTM 51N 后计算；`length_km_sum`（各 branch 直接相加）只作参考。官方里程来自 `data/manual/shanghai-lines.csv`，
差值的记录口径按 ADR R7：「差 >5% 只记录、不阻断」。

20 条里 18 条与官方口径相差在 ±5% 以内（多数 ±2%），两个例外：**2 号线 −6.5%**（官方 66 km 含延伸段口径）、
**浦江线 −5.1%**（官方 6.64 km vs 实测 6.30 km，绝对差 340 m）。

**颜色**：ADR R6「官图为准、OSM 兜底」。把官方线路图 JPEG（5497×7693）按「饱和度 >0.22 且非近白」取彩色像素，
5 bit/通道量化找高频色簇，与 OSM 颜色比欧氏距离：≤30 视为一致（12 条）；>30 且簇可信则改用官图色
（**2、4、5、14 号线**，见 `docs/colors.md` 的像素数与距离）；官图分辨不出的 4 条（10 淡紫、16 水绿、
磁浮青绿、浦江灰）保留 OSM 并标 `colour_verified=false` 与原因。

**属性来源**：开通年月与运营方来自百度百科词条的结构化字段（人工表 `data/manual/shanghai-lines.csv`，
`source` / `source_url` / `as_of` 三列可追）；13、16 号线百科未给运营方 → 回退 OSM；18 号线百科记「磁浮公司」
疑与 16 号线笔误重复，已在 `note` 留痕。`name_en` 归一成 `Line N` / `Maglev Line` / `Pujiang Line`，
原路线描述存 `name_en_route`。

S2-5 之后按用户指示追加了 ADR R5 的一句：`type` 允许低置信度，`medium`/`low` 标 `needs_review`。

### S2-4 区间切分（2026-11-01）

```powershell
& $PY pipeline\10_build_segments.py                 # 全部 23 条 branch
& $PY pipeline\10_build_segments.py --only sh-line-2-main sh-line-4-main   # 单独打样
```

**几何怎么来的**：不用「按成员顺序把 way 串起来」——OSM 关系里 way 的先后与方向并不保证一致（打样时 2 号线 16 个 way 有 3 处接不上，其中一个是只含 1 个节点的残段）。改用图方法：

1. 把该 branch 代表关系的所有成员 way 摊成一张无向图（节点 = OSM 节点 id，边权 = 两点大圆距离），方向与顺序都不再重要；
2. 对**相邻两个车站节点**求最短路，最短路经过的节点序列就是这一区间的轨道几何；
3. 环线（ADR R3）把末站与 `loop_start` 之间也算一段，所以区间数 = 站数。

车站节点都在 way 的节点集合里（打样 2/10/4 号线 0 缺失），因此每段都走得通；若某段不通，脚本会记 `gap` 并明确报出，**不伪造几何**。本次 570 段全部连通，`gap` 为空。

产物 `data/processed/shanghai/segment.geojson`（792 KB）：570 个 `LineString`，要素属性含 `id`（`<branch>-<三位序号>`）、`branch_id`、`seq`、`from_station`/`to_station`（**station id**，另有 `from_name`/`to_name` 供人读）、`length_m`、`node_count`、`is_loop_close` 与三问字段。

| branch | 站 | 段 | 实测 km | 对照 |
| --- | --- | --- | --- | --- |
| 1 号线 | 28 | 27 | 37.01 | 官方 36.9 |
| 2 号线 | 31 | 30 | 61.65 | 官方 64.0（−3.7%，差在两端道岔不入区间） |
| 3 号线 | 29 | 28 | 40.14 | 官方 40.3 |
| 4 号线（环） | 26 | 26 | 33.71 | 官方 33.6 |
| 5 号线 main / b1 | 15 / 11 | 14 / 10 | 27.22 / 16.63 | — |
| 6 / 7 / 8 / 9 号线 | 28 / 33 / 30 / 34 | 27 / 32 / 29 / 33 | 32.51 / 43.79 / 37.05 / 63.70 | 33.2 / 44.4 / 37.5 / 63.8 |
| 10 号线 main / b1 | 34 / 33 | 33 / 32 | 40.61 / 39.21 | main 40.6 |
| 11 号线 main / b1 | 33 / 37 | 32 / 36 | 62.56 / 73.08 | 常引「全线 82.4」是按两交路合计的口径 |
| 12 / 13 / 14 / 15 号线 | 32 / 31 / 31 / 30 | 31 / 30 / 30 / 29 | 39.92 / 38.03 / 38.27 / 41.77 | 40.4 / 38.8 / 39.1 / 42.3 |
| 16 / 17 / 18 号线 | 13 / 14 / 31 | 12 / 13 / 30 | 58.75 / 40.99 / 44.19 | 59.0 / 41.0 / 44.5 |
| 磁浮 / 浦江线 | 2 / 6 | 1 / 5 | 29.07 / 6.31 | 30.5 / 6.7 |

质检（`--only` 打样 + 全量各跑一遍）：段数 = 站数或站数−1（逐 branch 核对，23/23 相符）；相邻段端点坐标完全一致（0 处不连续）；`length_m / 两端直线距离` 全部 ≤3 且无 <200 m 的段（0 处异常）；每条 branch 都有几何，无 `gap`。

预览：`E:\subway-data\preview\segments.html`（仓库外），截图 `seg-z11.png`（全城）、`seg-line10-fork.png`（10 号线主线红/支线蓝在龙溪路分岔）、`seg-line4-loop.png`（4 号线闭环）。预览用的线色是按线路 id 轮转的**临时色**，官方配色属 S2-6。

### S2-7 校验与提交（`13_validate.py`）

```powershell
& $PY pipeline\13_validate.py            # 1–7 项，秒级
& $PY pipeline\13_validate.py --rerun    # 追加第 8 项：重跑 5 个脚本比对确定性（约 2–3 分钟）
```

按 ADR R8 逐项跑，任一不过退出码非 0，报告写 `docs/validation-s2.md`。八项全过：

| # | 项 | 实测 |
| --- | --- | --- |
| 1 | line 数 / 每线 ≥2 站 / 唯一 main | 20 条，全部满足 |
| 2 | 站坐标落在上海包围盒或白名单 | 430 站，越界 0 |
| 3 | 站 `lines[]` 非空且引用有效 | 悬空 0 |
| 4 | 环线段数=站数且首尾闭合；非环线段数=站数−1 | 23 条 branch 全符 |
| 5 | segment 两端站点存在、站序相邻 | 570 段全符 |
| 6 | transfer 成对、站距与坐标一致、证据齐全 | 22 条全符 |
| 7 | 颜色 hex、拼音非空 | 20 线 + 430 站全符 |
| 8 | 两次运行产物一致（除时间戳） | 4 份产物差异 0 |

**跑校验时修掉的三处真问题**（都不是文档措辞，是模型/实现不一致）：

1. **segment 原先用站名引用车站**，两个人同名（上海南站拆成 3 站）就无法区分，改名也会断链。已改为存 `station.id`，站名另存 `from_name`/`to_name`（ADR R2 补了一句「实体之间一律用稳定 id 引用」）。
2. **transfer 的 `dist_m` 与校验用的距离算法不同**（haversine 球面 vs WGS-84 椭球），3 条对不上 1 米左右。已统一为 `pyproj.Geod` 椭球测地线。
3. **ADR R8 第 4 项措辞与模型冲突**：原文要求「环线首末站相同」，但模型里 `stops` 只存 26 站一次（不重复首站），靠第 26 段回环。已把 ADR 措辞改成「末段 `to_station` 等于首段 `from_station`」，与实现一致。

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

## 快照目录的不可变约定（P1a-2 合肥发现）

`01_fetch_snapshot.py` 原来只比体积就复用、并且**整份重写 manifest**，多城依次跑时会出两个问题：

1. 上游日更让同名文件变大 → 旧快照里的字节被**静默覆盖**（合肥取数时 `anhui-latest.osm.pbf` 从 46,314,742 B 变成 46,320,575 B）；
2. manifest 被重写成只含本次城市的省 → 其它省的记录**丢失**。

现在的规则：

| 情况 | 行为 |
| --- | --- |
| 磁盘 sha256 == manifest 记录 | 复用，不下载 |
| 磁盘存在但 sha256 不同 | **不覆盖**，按磁盘现值记录，并在条目里写 `upstream_changed: true` + `previous_sha256` + `note`；要换成上游最新版须换快照键或加 `--refresh` |
| manifest 已有其它省的条目 | 按文件名合并，不会丢 |
| 已标记过 upstream_changed 的条目 | 后续跑即使 sha 已一致，也保留 `previous_sha256` 与说明 |

## 校验的多城口径（P1a-5.4）

- `13_validate.py` 的期望线路数来自城市配置（`len(CFG.line_ids)`），不再写死 20；采集框与白名单同样来自配置。
- 报告按城分开写：上海仍写 `docs/validation-s2.md`，其它城写 `docs/validation-s2-<code>.md`（避免互相覆盖）。
- `08_build_lines.py` 给 `from`/`to` 增加了兜底：OSM 关系没有 `from`/`to` 标签时（广州的 11/12 号线就是如此），取站序首站与末站；环线仍为 `null`。

## 属性补全的多城口径（P1a-5）

`12_build_attributes.py` 按城读人工表，缺表不崩：

| 文件 | 用途 | 缺失时 |
| --- | --- | --- |
| `data/manual/<slug>/lines.csv` | `opened` / `length_km_official` / `operator` / 官图色名 | 这几个字段留 `null`（颜色照常处理） |
| `data/manual/<slug>/colours.json` | `colour_override` / `colour_unverified` / `colour_confirmed_osm` / `name_en` | 回退到脚本内上海字面量 |

`colour_confirmed_osm` 是新增的第四态：**该城没有可采样的官方线路图，但已用第二来源（百度百科「标志色」）逐条核对过** → 颜色沿用 OSM，记 `colour_source: "OSM（无官图，经百科色名核对）"`、`colour_verified: false`。

`08_build_lines.py` 的 `norm_name()` 会剥掉线路名前缀（`地铁` / `轨道交通` / `轻轨` / 城市名），广州 OSM 的「地铁 1号线」因此变成「1号线」；像「12号线东段」这种区段命名用 `NAME_OVERRIDE` 显式指定。

## 城市配置（P1a-1.1）

P0 只做上海，多个脚本把「上海」「sh-」「shanghai」写死在常量里。P1a 起，城市相关的
事实集中到 `pipeline/cities/<code>.json`，由 `pipeline/cityconfig.py` 加载校验：

```powershell
$env:PYTHONUTF8 = '1'
E:\subway-data\venv\Scripts\python.exe pipeline\cityconfig.py --list
E:\subway-data\venv\Scripts\python.exe pipeline\cityconfig.py --check        # 全部
E:\subway-data\venv\Scripts\python.exe pipeline\cityconfig.py --check gz     # 单城
E:\subway-data\venv\Scripts\python.exe pipeline\cityconfig.py --show gz      # 含派生字段
E:\subway-data\venv\Scripts\python.exe pipeline\cityconfig.py --schema       # 字段说明
```

| 城市 | 文件 | 省份 L4 | 城市面 | 线路 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 上海 sh | `cities/sh.json` | 913067 | L4 913067 | 20 | 回归基准 |
| 广州 gz | `cities/gz.json` | 911844（**不闭合**） | L5 3287346 | 19 | 省面走 21 市并集；有轨电车按 `ref` 排除 |
| 成都 cd | `cities/cd.json` | 913068（闭合） | L5 2110264 | 16 | |
| 合肥 hf | `cities/hf.json` | 913011（闭合） | L5 3288965 | 8 | |

校验规则（`load_city()` 时执行，错误一次性全部列出）：必填字段齐全、无未知字段、
`bbox`/`scene_bbox` 西<东 南<北、`km_per_deg` 为正、`line_ids` 与 `line_count_expected`
一致且前缀匹配、`province_face` 模式与 `names` 匹配、`route_scope` 的 route/类型合法。

**分工**：配置只放机器可读的事实；要人判断的东西（同名站合并白名单、换乘类型、
颜色覆盖、官方里程）在 `data/manual/<city>/`，不进配置。决策见
`docs/decisions/0004-city-config.md`。

## 路径层（P1a-1.2）

所有「文件放哪儿」由 `pipeline/paths.py` 统一给出，业务脚本不再自己拼字符串：

```python
from cityconfig import load_city
from paths import Paths

p = Paths(load_city("sh"))
p.lines_json          # data/processed/shanghai/lines.json
p.station_json
p.transfer_json
p.segment_geojson
p.basemap_geojson     # data/processed/basemap/shanghai-basemap.geojson
p.sea_geojson
p.relation_index()    # 上海沿用 P0 的全局位置
p.attribution_report()
p.manual_lines_csv    # data/manual/shanghai-lines.csv
p.docs_colors_md      # docs/colors.md
p.pbf("shanghai", "20261101")
p.snapshot_manifest("20261101")   # 仓库内 data/snapshots/<key>/manifest.json
```

命令行可当检查表用：

```powershell
E:\subway-data\venv\Scripts\python.exe pipeline\paths.py --roots
E:\subway-data\venv\Scripts\python.exe pipeline\paths.py --show sh    # 逐项标 [有]/[缺]/[—]
E:\subway-data\venv\Scripts\python.exe pipeline\paths.py --check      # 上海回归基准的 15 项必需产物
```

两条布局约定（P1a 期间）：

| 情况 | 规则 | 原因 |
| --- | --- | --- |
| 上海 `sh` | `attribution-report.json` / `relation-index.json` / `basemap/*.geojson` **沿用 P0 的共享位置**，不进 `data/processed/shanghai/` | 让 P1a-1.6「上海产物逐字节不变」成立；P1b 再统一搬迁 |
| 其它城 | 一律 `data/processed/<city>/`，底图与海面放 `<city>/basemap/` | 避免多城互相覆盖 |

PBF 在仓库外 `E:\subway-data\snapshots\<key>\`，清单与 sha256 在仓库内 `data/snapshots\<key>\`，同一个 `key` 对齐；两个根都能用环境变量覆盖（`SUBWAY_SNAPSHOTS` / `SUBWAY_DATA_ROOT`，GZUPA 用 `SUBWAY_GZUPA`）。

## 编码约定

- 文件一律 **UTF-8 无 BOM**（PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写 BOM，Python 侧读到会异常）
- 坐标一律 `[经度, 纬度]`（GeoJSON 顺序），全链路 WGS-84 / EPSG:4326
- 中间产物里的时间戳字段不得参与算指纹，否则重跑不可比

## 脚本改造（P1a-1.3）

15 个编号脚本全部由配置驱动，城市通过环境变量选择：

```powershell
$env:PYTHONUTF8 = '1'
$env:SUBWAY_CITY = 'sh'      # sh / gz / cd / hf，默认 sh
E:\subway-data\venv\Scripts\python.exe pipeline\09_build_stations.py
```

| 变更 | 说明 |
|---|---|
| 头部 | 每个脚本统一 `sys.path.insert` + `load_city(SUBWAY_CITY)` + `Paths(CFG)` |
| 常量 | 全部换成 `CFG.*`（城市/省份/包围盒/km/线路清单/ref 映射/白名单）与 `P.*`（路径） |
| 人工表 | `data/manual/<slug>/{merge,transfers,colours,official-km}.json`，脚本不再内嵌 |
| 底图 | `03_extract_basemap.py` 只做上海；其它城市直接 `SystemExit` 并说明理由 |
| 编排 | `run_s1.py --city gz` 会跳过 S1-4 |

**回归**：改完重跑 02→15，上海全部产物与改造前逐字节一致（仅 `generated_at` 变化），`13_validate.py --rerun` 八项全过。细节见 `docs/decisions/0004-city-config.md` 第九节。

## 一条命令跑一座城（P1a-1.4）

`run_city.py` 把「取数 → 建模 → 校验」串起来，加新城市就用它：

```powershell
$env:PYTHONUTF8 = '1'
E:\subway-data\venv\Scripts\python.exe pipeline\run_city.py --list             # 步骤表
E:\subway-data\venv\Scripts\python.exe pipeline\run_city.py --city gz          # 广州全链路
E:\subway-data\venv\Scripts\python.exe pipeline\run_city.py --city sh --from S1-5
E:\subway-data\venv\Scripts\python.exe pipeline\run_city.py --city gz --to S1-6  # 只到归属
```

| 特点 | 说明 |
|---|---|
| 步骤表 | 13 步：S1-2…S1-6、S2-2a…S2-7；每步注入 `SUBWAY_CITY` |
| 人工闸门 | 06 生成映射骨架后若还有空 `decide`，**停下**（退出码 3）并打印怎么填、怎么续跑 |
| 跳过骨架 | 映射表已判定完时自动跳过 06，防止 `--force` 覆盖人工成果 |
| 底图 | 只在上海跑 S1-4，其它城打印跳过 |
| 全局文件 | 关系清单 / 归属报告 / `conflicts.md` 只归上海；其它城写 `data/processed/<city>/` 与 `docs/conflicts-<code>.md` |
| 城市范围 | 06 只导出本城 + `worksheet_cities`（上海含苏州、广州含佛山），不导出整省 |

广州实测：`--to S2-2a` 跑到骨架（91 行）后停在闸门，退出码 3；上海 `--from S1-5 --to S2-7` 60.5 s，八项校验全过，产物与基线只差时间戳。细节见 `docs/decisions/0004-city-config.md` 第十节。

### 同省跨市的逐站归属（P1a-2 补记）

`05_attribution.py` 对「同一省、不同地级市」的关系也写 `cross_city` 冲突，条件是
`len(distinct_cities) > 1 and len(distinct_provs) <= 1 and CFG.city in distinct_cities`：
前两个条件把跨省关系留给 `cross_province`，第三个条件保证只记本城参与的关系（上海产物不变）。
`09_build_stations.py` 读这些条目把每站落到正确的地级市；广州实测 `佛山市 22 站`（15 广佛线 + 7 号线顺德段 7 站）。

文档输出按城命名：广州写 `docs/mappings/station-merge-decisions-gz.md`、`transfer-decisions-gz.md`、`colors-gz.md`；
上海保持 `station-merge-decisions.md` / `transfer-decisions.md` / `colors.md` 不变。

## 回归测试（P1a-1.6）

```powershell
$env:PYTHONUTF8 = '1'
E:\subway-data\venv\Scripts\python.exe pipeline\regression.py          # 只比对
E:\subway-data\venv\Scripts\python.exe pipeline\regression.py --run    # 先跑 S1-5→S2-7 再比对
```

判据：把产物里的 ISO 时间戳与「耗时 N s」归一化后取 sha256，与 `git` 上一版（默认 `HEAD`）比。
`--baseline HEAD~1` 可指定参考点，`--list` 只列纳入回归的文件。

纳入回归的 17 项：`data/raw/transit-relations.json`（仓库外不入 git，自动跳过）、
`relation-index`、`attribution-report`、`lines/station/transfer/segment`、`basemap/sea`、
`docs/{conflicts,validation-s2,colors,station-merge-decisions,transfer-decisions,shanghai-relations,name-diff}.md`、`name-diff.json`。

负例实测：手工把某站名加个后缀 → 报 `[不一致] station.json` 并打印首个差异行，退出码 1；
还原后回到 16/16 一致。改文档标题这类**有意的语义变化**需要提交新版本作为基线，否则会被判失败（这是设计意图）。
