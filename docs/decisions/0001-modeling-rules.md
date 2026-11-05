# ADR 0001：S2 数据建模规则

- 状态：**已采纳**（2026-11-01）
- 决策人：用户（m01729 批准六项按建议执行）
- 适用范围：P0（上海单城）。P1 扩城时沿用本规则，只换城市前缀与关系映射表。
- 关联：`AGENTS.md` 第 8 节（字段名固定）、第 4 节（坐标系）、`docs/conflicts.md`（S1-6 归属结果）

## 背景

S1 产出的是 **287 条 OSM 关系**（上海子集 65 条）。OSM 的关系粒度与数据模型不是一回事：

| 维度 | OSM 的实际情况 | 数据模型要求 |
| --- | --- | --- |
| 方向 | 每条线有上下行**两个**关系 | 一条线一个实体 |
| 服务等级 | 16 号线有普通车 / 大站车 / 直达车**三个**交路 | 只画一条 |
| 区间车 | 1 号线有「上海火车站→莘庄」的短交路 | 不另立线路 |
| 支线 | 10 号线（航中路）、5 号线（闵行开发区）、11 号线 | 需要 `branch` 表达 |
| 环线 | 4 号线内圈 / 外圈，无起终站 | 需要 `is_loop` |
| 跨省 | 上海 11 号线与苏州 11 号线同名、共用花桥 | 按城市分裂 |
| 母关系 | 3 条有 0 个 stop 成员 | 丢弃 |

因此 S2 必须先定死规则，否则每处理一条线都要临时决策一次。本 ADR 就是这套规则。

## 范围（R0）

- **只建模上海**：metro（1–18 号线）、apm（浦江线）、maglev（磁浮线），共 **20 条线路**。
- **不建模**：松江有轨 T1/T2（`tram`）、浦东机场旅客捷运（`light_rail`）。它们留在 S1 产物与 `docs/conflicts.md` 里，P0 不渲染。
- 其余四省（江苏 85 / 浙江 71 / 安徽 25 条已定案关系）在 S2 只作为**交叉校验材料**，不产出实体。

判据：`data/processed/shanghai/lines.json` 的条数 = 20；`tram` 与机场捷运在产物中 0 条。

## R1 线路与支线的划分

**决定：** 一个 `line` 对应一条官方线路；交路差异用 `branch` 表达，不拆成两条 line。

- 每条 line **必须有且只有一条** `is_main: true` 的 branch；支线按官方命名依次 `b1`、`b2`。
- 方向不建模：上下行两个关系合并为一个 branch，站序取其中一个方向（默认取 `from` 为起点的那个；环线例外，见 R3）。
- 服务等级（大站车 / 直达车 / 区间车）**不进模型**，只在 line 上留 `service_notes` 文本记录存在过。
- 有支线的线路，主线站序取覆盖站点最多的那一条交路；被舍弃交路的站点必须能在某个 branch 的站序里找到。

判据：

1. 20 条 line 全部有且只有一个 `is_main`；
2. 上海子集 65 条关系逐条出现在 `docs/mappings/shanghai-relations.md` 的「保留 / 合并 / 丢弃」三列之一，丢弃项必须写理由；
3. 关系 → branch 的映射是满射：每个 branch 至少来自 1 条关系。

## R2 ID 规则

**决定：** ID 是稳定字符串，不用数组下标、不用 OSM id（OSM id 会因关系重建而变）。

| 实体 | 格式 | 示例 |
| --- | --- | --- |
| line | `<城市码>-line-<线号或制式>` | `sh-line-2`、`sh-line-18`、`sh-line-pujiang`、`sh-line-maglev` |
| branch | `<line_id>-main` / `<line_id>-b1` / `-b2` | `sh-line-2-main`、`sh-line-10-b1` |
| station | `<城市码>-station-<拼音 slug>`，冲突加 `-2`、`-3` | `sh-station-renmin-guangchang`、`sh-station-xinzhuang` |
| segment | `<branch_id>-<三位序号>` | `sh-line-2-main-014` |
| transfer | `<station_a>--<station_b>`（按字典序） | `sh-station-shanghainan--sh-station-shanghainanzhan-2` |

写法约定：

- 拼音 slug 全小写、连写、不带声调，`ü` 写 `v`（如「绿」→ `lv`），非汉字字符的站点（机场名）用官方英文名小写连字符。
- 城市码固定表：`sh` 上海、`nj` 南京、`hz` 杭州、`sz` 苏州、`hf` 合肥、`jn` 济南、`qd` 青岛，其余 P1 时补。
- **跨城同名站必须在 ID 上分裂**：上海 18 号线「迎春路」是 `sh-station-yingchunlu`，昆山 11 号线的同名站是 `sz-station-yingchunlu`（实测相距 86.7 km，见探测 5）。
- OSM 关系 id 只作为 `source_ref` 字段保留，供回溯。

判据：全库 ID 唯一；同一站群内不存在两个 ID 指向距离 ≤150 m 的站；`source_ref` 覆盖率 100%。

## R3 环线

**决定：** 环线是一个 line + 一个 `is_loop: true` 的 branch，**不设 from/to**，站序首尾相接。

- 起点站由人工指定并写入 `loop_start`（4 号线取「宜山路」），仅用于生成 segment 的序号；`from` / `to` 字段一律 `null`。
- segment 的第 1 段从 `loop_start` 出发，最后一段回到 `loop_start`，即 `segments.length == stations.length`（直线线路是 `stations.length - 1`）。
- `loop_evidence` 保留 S1 判据原文（`from == to` 或站序首尾同名且 ≥3 站）。

判据：环线 branch 的首末站 ID 相同；segment 数 = 站数；首末 segment 的端点接得上。

## R4 车站合并

**决定：** 同名站按距离三档处理，**只把 ≤150 m 的合并成一站**，更远的用 `transfer` 表达，不合并。

| 站群内最大站距 d | 处理 | 记录要求 |
| --- | --- | --- |
| d ≤ 150 m | 合并为一个 `station`，`lines[]` 多值 | 写进「合并表」，记成员 OSM 节点 |
| 150 < d ≤ 300 m | 合并，但**必须人工确认** | `needs_review: true` + 判定依据 |
| d > 300 m | **不合并**，建 `transfer` | 逐条定案，写明类型与站距 |
| 跨城同名 | **一律不合并**，各自成站 | 记 ID 分裂 |
| 无站名的节点 | 单独成站，`name` 为 `null` | 进待确认清单 |

实测基准（探测 5，93 个多线站名）：≤150 m 47 个、150–300 m 30 个、300–500 m 13 个、500–800 m 2 个、>800 m 2 个。其中 16 个 >300 m 的站群必须逐条人工定案。

站名字段口径：

- `name` 存**不带「站」字**的官方写法（「人民广场」「一大会址·黄陂南路」），UI 统一加「站」；
- `name_en` 优先 OSM `name:en`，缺失用官图英文名；
- `name_pinyin` 由 `pypinyin` 生成后人工校对，**不依赖运行时转换**（多音字难例：西藏南路、莘庄、五角场、真如、南翔、北新泾、上海南站、曹杨路、颛桥、龙阳路）；
- 同站异名（如曾有「黄陂南路」→「一大会址·黄陂南路」）在 `aliases[]` 保留旧名。

判据：合并后站名去重数（S1 实测 **509**）与最终站数的差额 ≤15，且每一处差额都能在合并表里解释。

## R4.1 站的可乘降口径（P1a-4 补）

OSM 关系的成员节点里，`role=inactive_stop` 表示**尚未开通或已停用**的站（合肥 7 号线的天津路、
巢湖南路、义城，上海快照里邻市的未开通站都属于此类）。这类节点：

- **不计入** `lines.json` 的站序、`station.json` 的站、`segment.geojson` 的区间；
- 判定实现在 `pipeline/04_track.py` 的 `stop_names` 过滤，`02` 仍保留原始节点以备查。

理由：本项目的口径是「只画已开通的城市轨道交通」，未开通站出现在站序里会让里程与站数虚高，
且 09 与 04 的站数口径会打架（广州、合肥都踩到过）。

## R5 换乘与出站换乘

**决定：** `transfer` 只表达**没有合并的两站之间的关系**；合并后的同站换乘不需要 transfer（看 `station.lines[]` 即可）。

| `type` | 判定 | 已知实例 |
| --- | --- | --- |
| `同站` | 同一站体内换乘（合并后即同站，一般不产生 transfer 记录） | — |
| `通道` | 有付费区通道、但站体不同 | 上海火车站（1 号线与 3/4 号线） |
| `出站换乘` | 需出闸再进闸，计费连续 | 上海南站（15 号线与 1/3 号线，实测 436 m） |

- `walk_minutes` 未知填 `null`，**禁止估算**填数字。
- 每条 transfer 必须带 `source` 与 `evidence`（站距 + 依据：OSM 节点 / 官图 / 人工）。
- **`type` 允许低置信度**（S2-5 实测后补充，2026-11-01）：OSM 的站内通道制图稀疏，
  且「连通」无法区分站内通道与出站换乘（上海火车站在图上连通但实为出站换乘），
  故 `type` 只能人工判定。每条 transfer 记 `type_confidence`（`high` / `medium` / `low`）
  与 `type_note`；**`medium` / `low` 一律标 `needs_review: true`**，留待人工或后续权威数据复核。

判据：transfer 双向成对（A→B 与 B→A 都存在）；每条都有 `evidence`；`walk_minutes` 只有 `null` 或带来源的整数。

## R6 颜色

**决定：** **官图采样为准，OSM `colour` 兜底**，两条都缺时人工指定并标 `manual`。

- 采样方法：官方线路图 JPEG（`https://www.shmetro.com/u/cms/www/metroViewImg/metroView.jpg`，5497×7693，Last-Modified 2025-12-26）中线带内高饱和像素取 RGB 中位数；每线样本量 <200 像素视为不可信，改人工。
- 冲突记录：OSM 与官图欧氏距离 >30 时，取官图值，并把两者写进 `data/processed/shanghai/colors.md`。已知：2 号线 OSM `#97D700` vs 官图 `#81BE23`（差约 48，须以官图为准）；12 号线两者吻合（`#007A5E` / `#007B5F`）。
- 颜色一律 `#RRGGBB` 大写十六进制 sRGB。

判据：20 条线颜色全部匹配 `^#[0-9A-F]{6}$`；每条线在 `colors.md` 里有「采样 / OSM / 最终值 / 来源」四列。

## R7 属性补全

**决定：** `opened` / `operator` / `length_km` 用**人工维护的 20 行表**，不写抓取脚本。

- 表的位置：`data/manual/shanghai-lines.csv`（进仓库，人工编辑），列为 `line_id,opened,operator,length_km_official,source,as_of`。
- 来源优先级：官方公告 > 维基百科（中文）> 协会年报。每条都要写 `source` 与 `as_of`。
- `length_km` 双轨：`length_km` 存**几何实测值**（UTM 51N 投影后求和），`length_km_official` 存官方值；两者差异 >5% 的线在 `docs/conflicts.md` 里列出，不强行对齐。
- 未知一律 `null`，不得用 0 或空串占位。

判据：20 条线的 `opened`、`operator` 均有值或有 `null` + 理由；`length_km` 与 `length_km_official` 都有值或都有 `null`；差异 >5% 的线已列入冲突文档。

## R7.1 线级里程口径（2026-11-05 修订）

`line.length_km` 采用 **按无序站对去重后累加**：同一对相邻站（方向无关）只计一次，取最短的那条几何。

- 不再用「各 branch 几何并集」：OSM 常把同一段轨道画成上下行两套不共形的 way，`unary_union` 消不掉重；支线交路会把主干重复计入。
- 实测影响（均为修复）：上海 5 号线 43.85 → **32.72**（官方 32.70）、10 号线 79.82 → **45.29**（官方 46.00）、11 号线 135.64 → **80.86**（官方 82.80）；成都 1 号线 63.60 → **40.20**（官方 41.00）。
- 同时保留 `length_km_union`（旧并集口径）与 `length_km_sum`（逐段相加）供对照；`length_km_method` 记录口径。
- 例外：与其它线**共线运营**的区段仍计入实测（如成都 19 号线含与 18 号线共线的天府站—天府机场北段，99.25 vs 官方 63.31），差异在 `lines.csv` 的 `note` 里逐条说明，不视为错误。

## R8 校验（S2-7 执行）

八项硬校验，任一不过即停：

1. line 数 = 20，每条 line ≥2 站，每条 line 有且只有一个 `is_main` branch；
2. 每个 station 的 `coord` 落在上海包围盒 `[120.8, 30.6, 122.2, 31.9]` 内，或命中白名单（花桥段 3 站：兆丰路、光明路、花桥，属苏州）；
3. 每个 station 的 `lines[]` 非空，且引用的 line 都存在；
4. 环线：`stops` 不重复首站，segment 数 = 站数，且**末段 `to_station` 等于首段 `from_station`**（`is_loop_close: true`）；非环线 segment 数 = 站数 − 1；
5. 每个 segment 的 `from_station` / `to_station` 都在 station 表里，两侧站序差 1；
6. transfer 双向成对，站距与 `evidence` 一致；
7. 颜色匹配 `^#[0-9A-F]{6}$`，`name_pinyin` 非空；
8. 两次运行同一快照，产物内容（除时间戳）逐字节一致。

## 后果

- **正面**：每步处理都有判据，不再逐线临时决策；`branch` / `transfer` / 颜色冲突都有明确的落点。
- **代价**：需要维护三份人工材料 —— 关系映射表（S2-2）、合并决策表（S2-3）、20 行属性表（S2-6）。这是有意的：这三处正是自动化不可靠的地方。
- **后续**：P1 扩城时本 ADR 基本不变，只需为每城补关系映射表与属性表；若某城的官方线路图不是位图（有 SVG/PDF），R6 的采样方法可以升级。
