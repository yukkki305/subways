# 0004 城市配置：把「城市」从代码里抽出来

- 状态：**已实施（P1a-1.0 盘点 / P1a-1.1 配置层落地，2026-11-04）**
- 日期：2026-11-04
- 背景：P0 只做上海，多个脚本把「上海」「sh-」「shanghai」写死在常量里。P1a 要做广州 / 成都 / 合肥三城，若不先抽配置，每加一城都要改 13 个脚本。
- 目标：**新增一个城市 = 只加一份配置 JSON，不改代码**；且上海现有产物逐字节不变。

## 一、现状盘点（实测，含行号）

统计口径：`PROVINCES` / `SH_PBF` / `SCENE_BBOX` / `BBOX` / `LOOP_START` / `FORCE_MERGE` / `GROUP_TYPES` / `REF_TO_LINE` / `LINE_MAP` / `EXPECTED_LINES` / `CITY` / `CITY_DEFAULT` / `PROVINCE_TO_CITY` / `PROVINCE_L4` / `PBFS` / `REQUIRED_PROVINCES` / `JIANGSU_CITY_NAMES` / `COLOUR_*` / `NAME_EN` / `OFFICIAL_KM`，以及 `data/processed/shanghai/...` 路径。

| 文件:行 | 常量 | 现值（摘要） | 城市相关性 |
| --- | --- | --- | --- |
| `01_fetch_snapshot.py:28` | `PROVINCES` | `["shanghai","jiangsu","zhejiang","anhui","shandong"]` | 省份集合 |
| `02_extract_transit.py:158` | `chunk["province"]` | 来自任务分块 | 省份集合 |
| `03_extract_basemap.py:34` | `SH_PBF` | `SNAPSHOT / "shanghai-latest.osm.pbf"` | 城市 PBF |
| `03_extract_basemap.py:36` | `OUT` | `data/processed/basemap/shanghai-basemap.geojson` | 产物路径 |
| `03_extract_basemap.py:47` | `SCENE_BBOX` | `(120.70, 30.55, 123.40, 31.95)` | 视野框 |
| `04_track.py:30` | `OUT` | `data/processed/relation-index.json` | 全局（跨省） |
| `05_attribution.py:39` | `PBFS` | 5 省 PBF 字典 | 省份集合 |
| `05_attribution.py:53` | `PROVINCE_L4` | `{913067:上海市, 913012:江苏省, 553302:浙江省, 913011:安徽省, 913006:山东省}` | 省面 id |
| `05_attribution.py:61` | `REQUIRED_PROVINCES` | `("上海市","江苏省","浙江省")` | 必需省面 |
| `05_attribution.py:66` | `JIANGSU_CITY_NAMES` | 江苏 13 地级市白名单 | L5 兜底白名单 |
| `05_attribution.py:70` | `KM` | `95.3 * 111.0`（31°N 近似） | 纬度相关（广州 23°N 需改） |
| `06_export_mapping.py:26` | `INDEX` | `data/processed/relation-index.json` | 全局 |
| `06_export_mapping.py:30` | `CITY` | `"上海市"` | 城市名 |
| `06_export_mapping.py:76` | 城市过滤 | `rec.get("city")` 与 `CITY` 比较 | 城市名 |
| `07_check_mapping.py:31` | `INDEX` | 同上全局 | 全局 |
| `07_check_mapping.py:33` | `EXPECTED_LINES` | `sh-line-1..18 + pujiang + maglev` | 线路清单（20 条） |
| `07_check_mapping.py:37` | `REF_TO_LINE` | `{str(i): f"sh-line-{i}"}` + 浦江/磁浮 | 线路清单 |
| `08_build_lines.py:29/30` | `INDEX` / `OUT` | `data/processed/shanghai/lines.json` | 产物路径 |
| `08_build_lines.py:32` | `CITY` | `"上海市"` | 城市名 |
| `08_build_lines.py:36` | `LOOP_START` | `{"sh-line-4": "宜山路"}` | 环线起点（人工） |
| `08_build_lines.py:40` | 线名覆盖 | `浦江线` / `磁浮线` | 特殊线名 |
| `09_build_stations.py:35/36/37/38` | 四个路径 | `shanghai/lines.json`、`raw/transit-relations.json`、`attribution-report.json`、`shanghai/station.json` | 产物路径 |
| `09_build_stations.py:41` | `CITY_DEFAULT` | `"上海市"` | 城市名 |
| `09_build_stations.py:48` | `FORCE_MERGE` | `{静安寺, 南京西路, 徐家汇, 宜山路}` | 合并白名单（人工） |
| `09_build_stations.py:51` | `PROVINCE_TO_CITY` | 江苏→苏州、浙江→嘉兴、安徽→宣城 | 跨省落地级市 |
| `10_build_segments.py:28/29/30` | 三个路径 | `shanghai/*` | 产物路径 |
| `10_build_segments.py:38` | `OFFICIAL_KM` | `2/4/10 号线` 对照值 | 里程对照（人工） |
| `11_build_transfers.py:35/36` | 路径 | `shanghai/station.json`、`shanghai/transfer.json` | 产物路径 |
| `11_build_transfers.py:43` | `GROUP_TYPES` | 12 组换乘类型表 | 换乘类型（人工） |
| `12_build_attributes.py:37/38/39` | 路径 | `shanghai/lines.json`、`segment.geojson`、`manual/shanghai-lines.csv` | 产物路径 |
| `12_build_attributes.py:44` | `COLOUR_OVERRIDE` | 4 条官图采样色 | 颜色（人工采样） |
| `12_build_attributes.py:51` | `COLOUR_UNVERIFIED` | 4 条未核实说明 | 颜色 |
| `12_build_attributes.py:58` | `NAME_EN` | `sh-line-maglev` / `sh-line-pujiang` | 英文名 |
| `13_validate.py:24` | `SH` | `data/processed/shanghai` | 产物路径 |
| `13_validate.py:31` | `BBOX` | `(120.8, 30.6, 122.2, 31.9)` | 视野框 |
| `14_extract_sea.py:30` | `OUT` | `basemap/shanghai-sea.geojson` | 产物路径 |
| `14_extract_sea.py:32` | `PROVINCES` | 5 省 | 省份集合 |
| `14_extract_sea.py:33` | `SCENE_BBOX` | 同 03 | 视野框 |
| `15_compare_names.py:26/30` | 路径 | `shanghai/lines.json`、`name-diff.json` | 产物路径 |
| `15_compare_names.py:33` | `LINE_MAP` | `line1..line18` → `sh-line-N` | 线路清单 |
| `run_s1.py:40–42` | `STEPS` 表 | 每步的产物路径 | 产物路径 |
| `web/scripts/sync-data.mjs:25–30,110` | `FILES` / 计数读取 | 6 个 `data/processed/shanghai/...` | 前端数据 |
| `web/scripts/test-search.mjs:17` | `dataDir` | `data/processed/shanghai` | 前端数据 |
| `web/scripts/verify-build.mjs:55` | `dataFiles` | 期望文件名 | 前端数据 |

**结论**：13 个 Python 脚本 + 3 个 web 脚本，约 **30 处**城市相关常量；其中「人工表」（`FORCE_MERGE` / `GROUP_TYPES` / `COLOUR_*` / `OFFICIAL_KM` / `LOOP_START`）是逐城核对结果，不应与「城市元数据」混在同一份配置里。

## 二、决策（D1–D5，已按建议采纳，m05674 授权执行）

| # | 决策 | 采纳结果 | 理由 |
| --- | --- | --- | --- |
| D1 | 配置格式 | **JSON 文件**（`pipeline/cities/<code>.json`）+ Python 加载器做校验 | 非程序员也能改；校验能把「缺 `network`」这类错误挡在跑数之前 |
| D2 | `relation-index.json` 是否按城拆 | **保留全局一份**（`data/processed/relation-index.json`，跨省审计）+ 每城物化子集 `data/processed/<code>/relation-index.json` | 全局是 S1 的审计产物；城市视图是 S2 的输入 |
| D3 | 上海是否与其它城同构 | **是**，上海也进 `cities/sh.json`（文件名 = `code`）；但 basemap 保留精细版 | 上海是回归基准，同构才能验证「不改代码加城」 |
| D4 | basemap / sea 通用化程度 | sea 全城通用（`<code>-sea.geojson`）；basemap 只有上海精细（16 区界 + 水系），其它城先做「市面轮廓 + 主水系」 | 底图不是 P1a 的重点，先用最小可用集 |
| D5 | web 侧这轮改不改行为 | **不改**，只把路径抽到 `web/lib/city.ts` | 多城 UI 属 P1a-7，避免两件事混在一个提交里 |

## 三、配置字段（草案）

```jsonc
{
  "code": "sh",                    // 产物目录与 id 前缀
  "name": "上海",                  // 数据里的 city / province 用全称
  "id_prefix": "sh",
  "province": "上海市",
  "province_l4_id": 913067,
  "pbfs": ["shanghai"],
  "network": ["上海地铁"],          // 归属唯一可靠字段
  "route_scope": {
    "subway": true,
    "light_rail_refs": ["浦江"],     // 按 ref 收 lrt
    "maglev_refs": ["磁浮"],
    "monorail_refs": []
  },
  "bbox": [120.70, 30.55, 123.40, 31.95],
  "scene_bbox": [120.70, 30.55, 123.40, 31.95],
  "city_admin_level": 4,           // 上海市面即省面；广州/成都/合肥用 5
  "city_names_fallback": null,     // 江苏式 L5 白名单；广州需要
  "km_per_deg": [95.3, 111.0],     // 依纬度，广州/成都需改
  "line_count_expected": 20,
  "loop_start": { "sh-line-4": "宜山路" },
  "line_names": { "sh-line-pujiang": "浦江线", "sh-line-maglev": "磁浮线" },
  "web": { "data_dir": "shanghai", "subpath": "/" }
}
```

**不进配置、仍留脚本内的**（逐城人工核对结果，P1a-1 只把它们搬进 `data/manual/<city>/`）：

| 人工表 | 现状 | 迁移目标 |
| --- | --- | --- |
| `FORCE_MERGE`（同名合并白名单） | `09:48` 硬编码集合 | `data/manual/<city>/force-merge.json` |
| `GROUP_TYPES`（换乘类型 12 组） | `11:43` 硬编码字典 | 已有 `transfer-decisions.md`；补 `data/manual/<city>/transfer-types.json` |
| `COLOUR_OVERRIDE` / `COLOUR_UNVERIFIED` / `NAME_EN` | `12:44/51/58` | 并入已有的 `data/manual/shanghai-lines.csv` → 通用 `<city>-lines.csv` |
| `OFFICIAL_KM`（里程对照） | `10:38` | 同上 CSV |
| `LOOP_START`（环线起点） | `08:36` | 留在配置（它属于城市元数据，不是逐行核对） |

## 四、迁移步骤与验收

| 步 | 内容 | 验收 |
| --- | --- | --- |
| P1a-1.0 | 本盘点 | 本文件 |
| P1a-1.1 | 配置层：`cities/*.json` + `cityconfig.py` | 删字段能报错；四份配置可加载 |
| P1a-1.2 | 路径层：`data/processed/<code>/`，旧路径 `git mv` | 旧文件保留 git 历史 |
| P1a-1.3 | 13 个脚本改读配置 | `typecheck` 无关；脚本 `--help` 正常 |
| P1a-1.4 | `run_city.py` | `--list` / `--only` / `--from` 可用 |
| P1a-1.5 | web 三脚本读 `web/lib/city.ts` | `npm run verify` 21 项 |
| P1a-1.6 | 上海回归 | 6 产物 sha256（去时间戳）一致；`13_validate` 8 项；`test:search` 22 条 |
| P1a-1.7 | 文档与提交 | 本 ADR 转「已实施」；`pipeline/README` 增配置节 |

**硬判据（不接受「差不多」）**：

1. 上海 `lines.json` / `station.json` / `segment.geojson` / `transfer.json` / `shanghai-basemap.geojson` / `shanghai-sea.geojson` 去掉 `generated_at` 后 **sha256 全部相等**；
2. `13_validate.py` 八项全过；
3. `web: npm run verify` 21 项、`npm run test:search` 22 条全过；
4. 只加一份 `cities/gz.json`（不改代码），`run_city.py --city gz --only S1-2` 能跑到归属阶段不崩（**不要求产物质量**）。

## 五、失败触发器

| 情况 | 处理 |
| --- | --- |
| 任一产物字节不等 | 停下定位，不放宽判据 |
| 迁移用 rm+新建导致历史丢失 | 禁止；只用 `git mv` |
| 广州配置在 S1 阶段就崩 | 允许，记录崩点并转 P1a-2，不算 P1a-1 失败 |
| 改动波及 web 运行行为 | 回退 web 部分，P1a-1 只做路径抽取 |

## 六、已知待定（P1a-2 处理，不在本步）

| # | 事项 | 说明 |
| --- | --- | --- |
| 1 | 广州 11 号线「内环」`loop_start` | 2020 年后新线，环线起点需人工指定（上海 4 号线取宜山路） |
| 2 | 广州 `city_names_fallback` | 广东 L4 不闭合 → 用 L5 并集 + 11 个市名白名单（与江苏同构） |
| 3 | 成都 `km_per_deg` | 成都 30.6°N，KM 系数与上海（31°N）差约 0.3%，P1a-2 校一次即可 |
| 4 | 三城 `line_count_expected` | 广州 19 / 成都 16 / 合肥 8（P1a-0.2 已核对） |
| 5 | 合肥 basemap | 简化版只取市面轮廓 + 巢湖/南淝河；是否值得做，P1a-2 决定 |

## 七、实现（P1a-1.1 落地，2026-11-04）

新增两个东西，业务脚本此步**不改**（改造在 P1a-1.3）：

| 文件 | 作用 |
| --- | --- |
| `pipeline/cityconfig.py` | 配置加载 + schema 校验 + CLI（`--list` / `--check` / `--show` / `--schema`） |
| `pipeline/cities/{sh,gz,cd,hf}.json` | 四城配置（文件名 = `code`，可用 `load_city("sh")` 直接取） |

### 7.1 字段最终形态
在第三节草案基础上新增三个字段/子字段：

| 字段 | 用途 | 取值来源 |
| --- | --- | --- |
| `city_names_fallback` | 城市名兜底白名单（省面拼不闭合时用） | 广东用不上（广州 L5 自闭合）；江苏那份 13 市名单随 P1a-1.3 退役 |
| `province_face` | `{mode: "l4"}` 或 `{mode: "l5_union", names: [...]}` | 上海市/四川省/安徽省走 L4；广东省走 21 个地级市并集 |
| `route_scope.exclude_refs` | 按 `ref` 排除「route 相同但制式不同」的关系 | **广州必须有**：`THP1`/`THP2`/`THZ1` 三条有轨电车也是 `route=light_rail`、`network=广州地铁`，只能按 ref 排除 |

### 7.2 四城关键取值（实测）

| 城 | 省份 L4 | 城市面 | 面积 km² | 网络名 | 线路 | `km_per_deg` |
| --- | --- | --- | --- | --- | --- | --- |
| 上海 `sh` | 913067 | L4 `913067` | 16,229.5（含海域） | 上海地铁 | 20 | 95.2 / 111.0 |
| 广州 `gz` | **911844（194/197，不闭合）** | L5 `3287346` | 7,379.3 | 广州地铁 | 19 | 102.4 / 111.0 |
| 成都 `cd` | 913068（355/355 ✅） | L5 `2110264` | 14,326.4 | 成都地铁 | 16 | 95.8 / 111.0 |
| 合肥 `hf` | 913011（488/488 ✅） | L5 `3288965` | 11,435.4 | 合肥轨道交通 | 8 | 94.6 / 111.0 |

广州必须用「21 个地级市并集」当省面（广东 L4 缺 3 个跨省共边 way）；成都、合肥的 L4 在本机已验闭合，不需要兜底 —— 这比 P1a-0 的结论更乐观。

**`km_per_deg` 的偏差是真实存在的**：上海按 31.2°N 算得 95.2，广州按 23.1°N 算得 102.4，两者差 **7%**；旧代码写死 `95.3 * 111.0` 若直接用于广州，公里数会系统性偏小。

### 7.3 线路清单的口径
`line_ids` 与 `line_count_expected` 必须一致（校验器会查）。四城清单来自 P1a-0.2 的 `network` 归属：

- 上海：`sh-line-1`…`sh-line-18` + `sh-line-pujiang` + `sh-line-maglev`
- 广州：`gz-line-1`…`gz-line-14` + `18`/`21`/`22` + `gz-line-apm` + `gz-line-gfl`
- 成都：`cd-line-1`…`cd-line-10` + `13`/`17`/`18`/`19`/`27`/`30`
- 合肥：`hf-line-1`…`hf-line-8`

### 7.4 校验器行为（实测）
- 正例：四城全部 `[通过]`，`--list` 输出表格。
- 负例（10 条，全部报错且指出字段）：缺必填、未知字段、`bbox` 西>东、`line_ids` 与数量不符、非法 `route`、`ref_overrides` 类型错、`l5_union` 缺 `names`、`km_per_deg` 为负、`loop_start` 值非字符串、`web` 缺 `city_label`。
- CLI 级负例：往 `pipeline/cities/` 放一份缺 `km_per_deg` 的 `zz.json` → `--check zz` 退出码 **1** 并打印缺失字段；删除后恢复 4/4 通过。
- `--show` 额外输出派生字段（`line_id_prefix`、`pbf_filenames`、`bbox_tuple`、`km_per_deg` 换算值）。

## 八、路径层（P1a-1.2，2026-11-04）

新增 `pipeline/paths.py`：`Paths(load_city(code))` 给出该城全部 20 个路径，业务脚本
只调函数不拼字符串（改造在 P1a-1.3）。

| 能力 | 方法 | 备注 |
| --- | --- | --- |
| 城市产物 | `lines_json` / `station_json` / `transfer_json` / `segment_geojson` | `data/processed/<city>/` |
| 底图与海面 | `basemap_geojson` / `sea_geojson` | 上海走共享 `data/processed/basemap/`，其它城走 `<city>/basemap/` |
| 清单与归属 | `relation_index()` / `attribution_report()` / `name_diff()` | 上海沿用 P0 全局位置 |
| 人工表 | `manual_lines_csv` / `manual_mapping_csv` | `data/manual/<slug>-*.csv` |
| 文档产物 | `docs_relations_md` / `docs_station_merge_md` / `docs_transfer_md` / `docs_colors_md` | 全局文档不带城市前缀 |
| 快照 | `pbf(province, key)` / `pbfs(key)` / `snapshot_manifest(key)` / `snapshot_sha(province, key)` | PBF 在仓库外、清单在仓库内 |
| 外部语料 | `gzupa_shp(year)` | 可用 `SUBWAY_GZUPA` 覆盖 |

**为什么上海不搬目录**：`attribution-report.json`、`relation-index.json`、
`data/processed/basemap/*.geojson` 现在是全局位置。如果这一步就搬进
`data/processed/shanghai/`，P1a-1.6 的「产物逐字节不变」会变成「产物搬家」两件事混在一起，
没法判断回归是路径改了还是逻辑改了。所以先让 `Paths` 对上海返回原地路径，搬迁留到 P1b。

**实测**：`paths.py --check` 通过 15 项必需产物；20 个路径方法对上海全部命中已存在文件
（含 `docs/mappings/shanghai-relations.md`、`docs/colors.md`、GZUPA shapefile）。

## 九、脚本改造（P1a-1.3）

15 个编号脚本全部改成「配置驱动」：头部统一 `sys.path.insert` + `from cityconfig import load_city` + `from paths import Paths`，城市由 `SUBWAY_CITY` 环境变量（默认 `sh`）决定。业务逻辑一行未改，只把常量换成 `CFG.*` / `P.*` / `data/manual/<slug>/*.json`。

### 9.1 配置层新增的 7 个字段

| 字段 | 用途 | 上海取值 |
|---|---|---|
| `extra_province_l4` | 本城数据会碰到的邻省 L4 id | 江苏 913012 / 浙江 553302 / 安徽 913011 / 山东 913006 |
| `required_provinces` | 必须闭合的省（否则归属不可信） | 上海 / 江苏 / 浙江 |
| `pbf_provinces` | `pbfs` 的文件名 → 省名 | shanghai→上海市 … shandong→山东省 |
| `province_l5_union` | L4 拼不闭合时用「地级市并集」 | `{"江苏省": 13 个市}` |
| `snapshot` | 快照键 | `20261101` |
| `ref_to_line` | 非数字 ref → line_id | 磁浮→maglev、浦江→pujiang |
| `stop_bbox_whitelist` | 允许越出包围盒的站 | 兆丰路 / 光明路 / 花桥 |

### 9.2 人工核对表外置

`data/manual/<slug>/` 下四份 JSON，全部由脚本里原有常量**导出**生成（不手抄）：

- `merge.json`：`force_merge`（4 组同名枢纽）+ `province_to_city`
- `transfers.json`：`GROUP_TYPES`（12 组换乘类型与置信度）
- `colours.json`：`colour_override` / `colour_unverified` / `name_en`
- `official-km.json`：`OFFICIAL_KM`

### 9.3 上海回归（逐字节）

改完后重跑 02→15，全部产物与改造前**逐字节一致**（只有 `generated_at` 不同）：
transit-relations.json（287 关系）、shanghai-basemap.geojson（22 要素 / 495,983 B）、shanghai-sea.geojson（24,829.3 km² / 91,741 B）、relation-index.json、attribution-report.json、conflicts.md、lines.json（42,546 B）、station.json（434,587 B）、segment.geojson（570 段）、transfer.json（10,032 B）、name-diff.json（18 线 / 同名 417）、colors.md、station-merge-decisions.md、transfer-decisions.md。
`13_validate.py --rerun` 八项全过，其中第 8 项「重跑 5 个脚本后 4 份产物差异 0」。

### 9.4 三个真问题

1. `05` 原来直接覆盖 `docs/conflicts.md`，会冲掉人工追加的「六、七、」两节 → 改为写出前先把人工段原样拼回。
2. `Paths.manual_file()` 是旧的 `<slug>-<suffix>` 形态，与新的目录形态不同 → 补 `manual_city_file()`，`09` 改用后者；首版漏改使 `FORCE_MERGE` 白名单失效（站数 423→430）。
3. `km_per_deg` 若改成 31.2°N 的真值 95.2，上海面积会从 16,229.5 掉到 16,212.5 km²，与已发布的台账/文档数字不符 → 上海保留 P0 的 95.3，真值只给新城市用（广州 102.4）。

### 9.5 `run_s1.py --city`

新增 `--city`（默认 `sh`），透传 `SUBWAY_CITY`；非上海的 S1-4 直接跳过并打印理由（底图只做上海，见 D4）。实测：`run_s1.py --city gz --only S1-4` → 打印跳过、退出码 0。

## 十、全链路编排（P1a-1.4）

新增 `pipeline/run_city.py`：一条命令跑完某城的 S1 → S2，直到校验。

```
python pipeline/run_city.py --city gz             # 全链路
python pipeline/run_city.py --city sh --from S1-5 # 从某步起
python pipeline/run_city.py --city gz --to S1-6   # 只跑到归属
python pipeline/run_city.py --list                # 步骤表 + 映射表状态
```

步骤表 13 步：S1-2 / S1-3 / S1-4（仅上海）/ S1-5 / S1-6 / S2-2a / S2-2b / S2-2c / S2-3 / S2-4 / S2-5 / S2-6 / S2-7，每步注入 `SUBWAY_CITY`。

### 10.1 人工闸门

`S2-2a`（06 生成映射骨架）之后会检查 `data/manual/<slug>/relation-mapping.csv` 里还有多少行没填 `decide`：
有空白行就**停下**、退出码 3，并打印「填哪一列、填完用哪条命令继续」。
映射表已判定完时，默认**跳过** S2-2a，避免 06 的 `--force` 守卫覆盖人工成果（要强制重出骨架用 `--with-skeleton`）。

### 10.2 全局审计文件只归上海

跑广州时发现：04/05 会把 `data/processed/relation-index.json`、`attribution-report.json`、`docs/conflicts.md` 当成全局文件写，结果**上海基线被覆盖**（并把 287 条上海关系标成 removed）。
修法：这三个路径只在 `code == "sh"` 时用全局位置，其它城写本城子集：

| 产物 | 上海 | 其它城 |
|---|---|---|
| 关系清单 | `data/processed/relation-index.json` | `data/processed/<city>/relation-index.json` |
| 归属报告 | `data/processed/attribution-report.json` | `data/processed/<city>/attribution-report.json` |
| 冲突台账 | `docs/conflicts.md` | `docs/conflicts-<code>.md` |

06/07/08 读清单时同理（上海读全局，其它城读本城子集）。实测：跑完广州后上海三个文件的 sha256 不变。

### 10.3 映射表的城市范围

`06` 只导出「本城 + 跨城对端市」的关系，而不是整个省的关系。
新增配置字段 `worksheet_cities`（可选，城市名数组）：上海 = `["苏州市"]`，广州 = `["佛山市"]`，成都/合肥为空。
过滤规则：`city ∈ {本城, worksheet_cities}`，或 `city` 为空且 `network` 命中 `CFG.network`；
若整份清单还没有回填 `city`（上海目前的状况），退回「省面全收」，保证 65 行不变。

实测：广东省内 256 条 → 广州保留 **91 条**（广州市 79 + 佛山市 12），香港/深圳/东莞的全部被排除。

### 10.4 广州的省面取舍

广东省 L4（`911844`）194/197 way，缺广西/湖南/江西/福建共边，**永远拼不闭合**。
因此 gz 配置：不设 `required_provinces`（不要求省面闭合），改设
`province_l5_union: {"广东省": ["广州市", "佛山市"]}` —— 省名由市名表给出，归属判定只用这两个闭合的市面。
随之补了 `province_l5_union` 的空值语义：允许某省只登记目标市，不要求登记该省全部地级市。

### 10.5 上海回归

`run_city.py --city sh --from S1-5 --to S2-7` 全程 60.5 s，八项校验全过；
`data/processed` 与 `docs/` 下所有产物与基线只差时间戳（10 行增删）。
