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

`run_s1.py` 编排 S1 的 7 个步骤，每一步可单独重跑（`--only <步骤名>`）。**当前状态：S1-1～S1-4 完成，`run_s1.py` 尚未落地（S1-7 时补）。**

## S1 步骤与脚本映射

| 步骤 | 脚本 | 输入 | 输出 | 状态 |
| --- | --- | --- | --- | --- |
| S1-1 目录与环境 | —（本文件 + `.gitignore`） | — | 目录骨架 | ✅ 完成 |
| S1-2 快照下载与归档 | `01_fetch_snapshot.py` | `download.openstreetmap.fr/extracts/asia/china/` | `E:\subway-data\snapshots\<date>\*.osm.pbf`；`data/snapshots/<date>/{*.sha256,manifest.json}` | ✅ 完成（20261101：上海 29.7 MB / 江苏 89.4 MB / 浙江 99.0 MB） |
| S1-3 轨道关系抽取 | `02_extract_transit.py` | 上一步的 PBF | `data/raw/transit-relations.json`（不提交） | ✅ 完成（三省 225 条关系 / 上海子集 65 条 / 4,540 个 stop 节点） |
| S1-4 底图要素抽取 | `03_extract_basemap.py` | 同 PBF | `data/processed/basemap/shanghai-basemap.geojson`（提交，目标 <5 MB） | ✅ 完成（22 要素 / 0.47 MB / 46.6 s） |
| S1-5 关系清单与指纹 | `04_track.py` | S1-3 产物 | `data/processed/relation-index.json`（提交） | 待建 |
| S1-6 归属校验 | `05_attribution.py` | S1-3 产物 + 边界 | `data/processed/attribution-report.json`、`docs/conflicts.md` | 待建 |
| S1-7 汇总与提交 | —（人工） | 以上全部 | `data/README.md` 三问表 + 两次提交 | 待建 |

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


## 目录分工

| 目录 | 内容 | 是否提交 |
| --- | --- | --- |
| `data/raw/` | 抓下来的中间 JSON（关系、节点、几何） | ❌ |
| `data/cache/` | 可重建的缓存 | ❌ |
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
