# data：数据文件清单与授权

本目录的每个文件都必须能回答三个问题：**来自哪里、什么许可、数据截止到哪一天**。新增或替换文件时，先改本表，再改数据。

- 质量与缺口以 `docs/conflicts.md` 为准，本表只管「来源 / 许可 / 截止日期」。
- 原始 PBF 与中间 JSON 不进仓库（见 `.gitignore`），本表用「仓库外路径」标注它们的位置。

## 一、清单

| 文件 | 内容 | 来源 | 许可 | 数据截止（`as_of`） | 生成脚本 |
| --- | --- | --- | --- | --- | --- |
| `data/processed/basemap/shanghai-basemap.geojson` | 上海底图 22 个要素：16 个区界、市界、淀山湖、长江口/吴淞江/黄浦江中心线、海岸线 | OSM，经 `download.openstreetmap.fr` 五省省级 extract（关系 `913067` `1122227` `9392345` `9064903` + `waterway=river` 与 `natural=coastline` 的 way） | **ODbL-1.0** © OpenStreetMap contributors | **2026-11-01** 00:27–00:28 GMT | `pipeline/03_extract_basemap.py` |
| `data/processed/basemap/shanghai-sea.geojson` | S4-4 海面：五省 PBF 的 `natural=coastline`（上海 130 / 江苏 42 / 浙江 433 条视野内）polygonize 后取反，24,829.3 km²、1 个面、76 个岛洞 | OSM，`pipeline/14_extract_sea.py` | **ODbL-1.0** | 2026-11-01 00:27–00:28 GMT | `pipeline/14_extract_sea.py` |
| `data/processed/relation-index.json` | 287 条轨道关系的清单与三重指纹（标签 / 成员 / 站序），含 `city` `province` 归属回填 | 同上，取自关系标签与成员节点 | **ODbL-1.0** | 2026-11-01 | `pipeline/04_track.py` |
| `data/processed/attribution-report.json` | 归属判定报告：每省的省面来源与面积、每个关系的逐站归属、未命中计数、flags | 由上面两份派生（OSM 几何 + OSM 关系） | **ODbL-1.0** | 2026-11-01 | `pipeline/05_attribution.py` |
| `data/snapshots/20261101/manifest.json` | 快照元数据：五个 PBF 的 URL、字节数、sha256、`Last-Modified`、下载时间 | 直接记录 `download.openstreetmap.fr` 的响应头与文件哈希 | **ODbL-1.0** | 2026-11-01 00:27–00:28 GMT | `pipeline/01_fetch_snapshot.py` |
| `data/snapshots/20261101/*.osm.pbf.sha256` | 五个 PBF 的校验和（每份一行） | 本地计算，用于复核快照未被替换 | — | 2026-11-01 | `pipeline/01_fetch_snapshot.py` |
| `docs/conflicts.md` | 归属冲突与待定项：跨省关系逐站列表、46 条未定关系明细 | 由 `attribution-report.json` 渲染 | **ODbL-1.0** | 2026-11-01 | `pipeline/05_attribution.py` |
| `data/processed/hefei/relation-index.json` | 合肥 28 条关系清单与指纹（含 10 条外市/外省线） | `anhui-latest.osm.pbf`（2026-11-05 上游日更） | ODbL-1.0 | 2026-11-05 | `pipeline/04_track.py` |
| `data/processed/hefei/attribution-report.json` | 合肥 18 关系逐站归属（419 站次，0 越省） | 同上 | ODbL-1.0 | 2026-11-05 | `pipeline/05_attribution.py` |
| `data/processed/guangzhou/lines.json` | 广州 19 条线 / 22 branch | 省级 PBF `guangdong-latest.osm.pbf`（2026-11-03）+ `data/manual/guangzhou/` 人工表 | ODbL-1.0 | 2026-11-03 | `pipeline/08_build_lines.py` |
| `data/processed/guangzhou/station.json` | 广州 320 站 / 414 站次 | 同上 | ODbL-1.0 | 2026-11-03 | `pipeline/09_build_stations.py` |
| `data/processed/guangzhou/segment.geojson` | 广州 393 段区间 | 同上 | ODbL-1.0 | 2026-11-03 | `pipeline/10_build_segments.py` |
| `data/processed/guangzhou/transfer.json` | 广州 3 条换乘 | 同上 + `data/manual/guangzhou/transfers.json` | ODbL-1.0 | 2026-11-03 | `pipeline/11_build_transfers.py` |
| `data/processed/guangzhou/relation-index.json` | 广州 91 条关系清单与指纹 | 同上 | ODbL-1.0 | 2026-11-03 | `pipeline/04_track.py` |
| `data/processed/guangzhou/attribution-report.json` | 广州逐站归属（含佛山 22 站） | 同上 | ODbL-1.0 | 2026-11-03 | `pipeline/05_attribution.py` |
| `data/manual/guangzhou/lines.csv` | 广州 19 条线路的开通日期、官方里程、运营单位、色名 | 百度百科信息框（开通日期/全长/运营机构/标志色） | 事实性字段，随 ODbL 衍生物使用；10 号线开通日期与 OSM `start_date` 互证 | 2026-11-04 | 人工整理 |
| `data/manual/guangzhou/colours.json` | 广州 19 条线路的颜色口径与英文名 | 百度百科「标志色」字段 + OSM `colour` | 事实性字段，按 ODbL 与 OSM 一致；色名来自百科 | 2026-11-04 | 人工整理 |
| `data/manual/hefei/lines.csv` | 合肥 8 条线路的开通日期、官方里程、运营单位、色名 | 百度百科信息框（开通日期/线路长度/运营机构/标志色） | 事实性字段，随 ODbL 衍生物使用 | 2026-11-05 | `09`/`12` 读取 |
| `data/manual/hefei/colours.json` | 合肥 8 条线路的颜色口径（7 条经百科色名核对、5 号线存疑）与英文名 | 百度百科「标志色」+ OSM `colour` | 事实性字段，按 ODbL 与 OSM 一致 | 2026-11-05 | `12` 读取 |
| `data/manual/hefei/relation-mapping.csv` | 合肥 18 条关系的判定（保留 8 / 合并 8 / 丢弃 2） | `06_export_mapping.py` 生成骨架 + 人工判定 | 数据判定，无第三方许可问题 | 2026-11-05 | `07`/`08` 读取 |
| `data/manual/hefei/transfers.json` | 合肥换乘类型表（本城 0 条，仅占位） | 人工判定 | — | 2026-11-05 | `11` 读取（缺失时回退上海字面量） |
| `data/processed/chengdu/relation-index.json` | 成都 55 条关系清单与指纹（成都市 49 / 资阳 S3 2 / 未定 4） | `sichuan-latest.osm.pbf`（2026-11-03 00:18:13Z 上游） | ODbL-1.0 | 2026-11-05 | `05` 回填归属 |
| `data/processed/chengdu/attribution-report.json` | 成都逐站归属（成都市 1,108 站次 / 资阳市 10） | 同上 + `admin_level=5` 城市面 | ODbL-1.0 | 2026-11-05 | `05` 产出 |
| `data/processed/chengdu/lines.json` | 成都 16 线 17 branch（470 站次） | OSM 省级 PBF（快照 p1a-20261103） | ODbL-1.0 | 2026-11-03 | 数据管道 |
| `data/processed/chengdu/station.json` | 成都 364 站（80 多线站、31 待复核、2 组拆分） | OSM 省级 PBF（快照 p1a-20261103） | ODbL-1.0 | 2026-11-03 | 数据管道 |
| `data/processed/chengdu/segment.geojson` | 成都 454 段 / 726.68 km（其中 8 段为站间直线兜底，标 geometry_source） | OSM 省级 PBF（快照 p1a-20261103） | ODbL-1.0 | 2026-11-03 | 数据管道 |
| `data/processed/chengdu/transfer.json` | 成都 4 条换乘（均通道，medium） | OSM 省级 PBF（快照 p1a-20261103） | ODbL-1.0 | 2026-11-03 | 数据管道 |
| `data/manual/chengdu/transfers.json` | 成都换乘类型人工表 | OSM 省级 PBF（快照 p1a-20261103） | ODbL-1.0 | 2026-11-03 | 数据管道 |
| `data/manual/chengdu/relation-mapping.csv` | 成都 49 条关系判定（保留 17 / 合并 23 / 丢弃 9），16 线 17 branch | `06_export_mapping.py` 骨架 + 人工判定 | 数据判定，无第三方许可问题 | 2026-11-05 | `07`/`08` 读取 |
| `docs/conflicts-cd.md` | 成都归属冲突台账（S3 资阳线跨市 2 条、4 条无已解析站） | 同上 | ODbL-1.0 | 2026-11-05 | `05` 产出 |
| `data/manual/shanghai-relation-mapping.csv` | S2-2 的关系映射表：上海子集 65 条关系 + 人工判定列（`decide` / `target_line` / `target_branch` / `note`） | 前 12 列由 `relation-index.json` 导出；后 4 列人工填写；`hint` 列是机器提示 | **ODbL-1.0**（OSM 衍生） | 数据基准 2026-11-01；判定日期见 `note` | `pipeline/06_export_mapping.py` |
| `docs/mappings/shanghai-relations.md` | 上面那份 CSV 的人可读视图（判定汇总 + 待决策 + 丢弃理由 + 全部明细） | 由 CSV 渲染 | **ODbL-1.0** | 同 CSV | `pipeline/07_check_mapping.py --write-md` |
| `data/processed/shanghai/lines.json` | S2-2 骨架 + S2-6 属性回填：20 条 line / 23 个 branch，含有序站名、环线起点、来源关系 id、服务等级、逐站归属、`colour`/`opened`/`length_km`(实测)/`length_km_official`/`operator`/`name_en` | 由 `shanghai-relation-mapping.csv` + `relation-index.json` 派生 | **ODbL-1.0** | 2026-11-01 | `pipeline/08_build_lines.py` |
| `data/processed/shanghai/station.json` | S2-3 产物：423 个站（592 个站次；S6-4 合并 4 组同名枢纽后），含稳定 id、拼音 slug、WGS-84 坐标、所属线路/支线、`is_transfer`、三档合并口径与 22 条换乘候选 | 由 `lines.json` 的权威站序 + `transit-relations.json` 的 `stop*` 节点派生；城市归属来自 `attribution-report.json` | **ODbL-1.0** | 2026-11-01 | `pipeline/09_build_stations.py` |
| `docs/mappings/station-merge-decisions.md` | S2-3 的合并判定表：133 个同名多站次组的跨度、口径、站数与换乘候选 | 由脚本渲染 | **ODbL-1.0** | 2026-11-01 | `pipeline/09_build_stations.py` |
| `data/processed/shanghai/segment.geojson` | S2-4 产物：570 段区间几何（23 条 branch 全覆盖），每段含起终站（`from_station`/`to_station` 存 station id，另带 `from_name`）、实测长度与环路末段标记 | 由 `lines.json` 的站序 + `station.json` 的车站节点 + 代表关系的成员 way 求最短路切分 | **ODbL-1.0** | 2026-11-01 | `pipeline/10_build_segments.py` |
| `data/processed/hefei/lines.json` | 合肥 8 线 / 8 branch 的站序与线路属性 | 省级 PBF（安徽 20261101，实际内容 2026-11-05 上游日更）+ `data/manual/hefei/relation-mapping.csv` | ODbL-1.0 | 2026-11-05 |
| `data/processed/hefei/station.json` | 合肥 195 站 / 215 站次（合并规则见 ADR R4） | 同上 | ODbL-1.0 | 2026-11-05 |
| `data/processed/hefei/segment.geojson` | 合肥 207 段区间 / 275.64 km | 同上（OSM way 几何） | ODbL-1.0 | 2026-11-05 |
| `data/processed/hefei/transfer.json` | 合肥 0 条换乘（无 >300 m 同名站组） | 同上 | ODbL-1.0 | 2026-11-05 |
| `data/processed/shanghai/transfer.json` | S2-5 产物：12 条换乘（8 组同名多站；S6-4 后），含两站 id、站距、`type`（通道/出站换乘）、`type_confidence`、`type_note`、`needs_review`、`walk_minutes`(null) | 两站坐标与站距来自 `station.json`（OSM 几何）；**换乘类型为人工判定**，见 `docs/mappings/transfer-decisions.md` | **ODbL-1.0** | 2026-11-01 | `pipeline/11_build_transfers.py` |
| `docs/mappings/transfer-decisions.md` | S2-5 换乘判定表：口径、统计、按站距降序的 12 条明细、待人工确认清单 | 由 `transfer.json` 渲染 | **ODbL-1.0** | 2026-11-01 | `pipeline/11_build_transfers.py` |
| `data/manual/shanghai-lines.csv` | S2-6 人工属性表：20 条线路的开通日、官方里程、运营机构、官方色名，含 `source`/`source_url`/`note` | **百度百科**词条的结构化字段（`dateOfOpening` / `lineLength` / `operatingOrganization` / 标志色）；仅取事实性字段，不转载条目正文 | 各词条版权归百度百科；本项目只保存事实性字段并逐条标注 URL | 2026-11-01 | 人工维护（初稿脚本 `E:\subway-data\probe16\mk_manual_lines.py`，仓库外） |
| `docs/colors.md` | S2-6 线路配色表：最终色、官图色名、来源三态、与 OSM 的欧氏距离、未核实原因 | 颜色来源 = 官方线路图 JPEG 采样（`shmetro.com`，2025-12-26）与 OSM `colour` 标签 | ODbL-1.0（OSM 部分）；官方线路图仅提取色值，不搬运图形 | 2026-11-01（图 2025-12-26） | `pipeline/12_build_attributes.py` |
| `data/processed/name-diff.json` | S5-4 追补：OSM（2026-11）↔ GZUPA（2020-12）的 **站名集合**差异，18 条线、同名 417 / 仅 OSM 47 / 仅 GZUPA 16 / 疑似改名 4 | OSM 部分同上；GZUPA 部分取自 `GZUPA/subway-traffic-data-set` 的 `shanghai_Layer_2020.shp`，**只取站名，不用其坐标**（`x/y` 是 GCJ-02、`wgs84_*` 偏移约 900 m，见 `docs/decisions/0002-gzupa-datum.md`） | ODbL-1.0（OSM）+ GZUPA 仓库许可 | OSM 2026-11-01；GZUPA 2020-12-31 | `pipeline/15_compare_names.py` |
| `docs/name-diff.md` | 上面那份差异清单的人可读视图（逐线表格 + 疑似改名表 + 仅单边有站列表） | 由 `name-diff.json` 渲染 | 同上 | 同上 | `pipeline/15_compare_names.py` |

**仓库外、不进 git：**

| 路径 | 内容 | 来源 | 许可 | 数据截止 |
| --- | --- | --- | --- | --- |
| `E:\subway-data\snapshots\20261101\*.osm.pbf` | 五省原始 PBF，合计 327.42 MB | `download.openstreetmap.fr/extracts/asia/china/` | ODbL-1.0 | 2026-11-01 |
| `data/raw/transit-relations.json` | S1-3 的中间产物（16.03 MB），可由 PBF 重建 | 由 PBF 派生 | ODbL-1.0 | 2026-11-01 |

## 二、授权义务（ODbL-1.0，必须遵守）

1. **署名**：页面与仓库都要出现 `© OpenStreetMap contributors`，并链接到 <https://www.openstreetmap.org/copyright>。
2. **相同方式共享**：本目录的派生数据（GeoJSON / JSON）属于 ODbL 的衍生数据库，必须继续以 ODbL 提供；不得改成更严格的许可。
3. **不得混入非 ODbL 数据**：高德 / 百度 / 腾讯的瓦片与 POI 不得进入本目录或任何产物（见 `AGENTS.md` 第 5 节）。
4. 官方线路图（上海地铁官网 JPEG）只用于人工核对站名与取色，**不进仓库**；其页面上提取的客观事实（站名、颜色十六进制、站序）不构成对图形的复制。

## 三、怎么重建

一条命令（需要 `E:\subway-data\venv`，见 `pipeline/README.md`）：

```powershell
$env:PYTHONUTF8 = '1'
E:\subway-data\venv\Scripts\python.exe pipeline\run_s1.py
```

只重跑某一步用 `--only S1-5`。重跑会覆盖本目录的产物；覆盖前请确认快照日期没变——**数据文件的 `as_of` 必须与 `data/snapshots/<date>/manifest.json` 的 `as_of` 一致**，不一致说明产物是旧快照的，需要整链重跑。

## 四、已知局限

- 底图的市界/省界**含海域**（上海 16,229.5 km² vs 官方陆地 6,340 km²），这是 OSM 边界关系的口径，不是错误；前端不画陆地填充，所以不影响观感。
- 海岸线不闭合（130 段、884.4 km，只覆盖岛屿与部分岸段），因此**没有**陆地填充面。
- 江苏省的省面拼不闭合（374 个 way 全在，仍差与山东/安徽共边的节点），城市归属用 13 个地级市面并集代替；山东 39 条、南通 4 条关系因此未定，明细见 `docs/conflicts.md`。
- 底图只覆盖**上海**；其他城市的底图在 P1 按同一脚本扩 `SCENE_BBOX` 生成。
