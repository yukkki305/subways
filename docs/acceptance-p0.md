# P0 验收签字表

- 日期：2026-11-03
- 验收对象：上海单城打样（`AGENTS.md` §12 九项）
- 线上地址：<https://yukkki305.github.io/subways/>
- 数据快照：20261101（OSM 省级 PBF 五省）

| # | 验收项（§12） | 证据文件 | 关键数字 | 结论 |
| --- | --- | --- | --- | --- |
| 1 | 线路数量与官方口径一致，缺口为零或逐条记录 | `data/processed/shanghai/lines.json`、`docs/conflicts.md` | **20 条线**（metro 1–18 + 浦江线 + 磁浮线）/ 23 个 branch | ✅ |
| 2 | 城市归属以台账为准，用 `admin_level=4`（`913067`）交叉校验 | `data/processed/attribution-report.json`、`docs/conflicts.md` | 上海 60 条关系；关系内 1129 站在市内、6 站在界外（全部为 11 号线花桥段 3 站 ×2 方向，已定案为苏州市） | ✅ |
| 3 | 坐标校验：与已知地标叠加无明显偏移 | `docs/probe/`、S1-6、S6-2 线上截图 | 全链路 WGS-84；人民广场/陆家嘴/外滩叠加与底图一致；GZUPA 因 GCJ-02 已排除（`docs/decisions/0002-gzupa-datum.md`） | ✅ |
| 4 | 每条线路颜色与官方线路图一致，并记录取色来源 | `docs/colors.md` | 20 条全有 hex；16 条与官图采样一致、4 条官图采样替代 OSM、4 条官图无法分辨标 `colour_verified=false` | ✅（4 条已注明） |
| 5 | 每个换乘站能对应到正确线路，无孤立站 | `data/processed/shanghai/station.json`、`transfer.json`、`pipeline/13_validate.py` | 423 站 / 592 站次；`is_transfer=true` **100**；transfer **12** 条；`13_validate` 第 6 项全过 | ✅ |
| 6 | 站名已用「OSM ↔ GZUPA 2020 + 百度百科」比对并产出差异清单；12 组同名多站逐组定案 | `docs/name-diff.md`、`docs/split-groups-review.md`、`docs/decisions/0003-split-group-merges.md` | 417 同名 / 47 仅 OSM / 16 仅 GZUPA / 4 疑似改名；12 组中 4 组合并、8 组走 transfer | ✅（17 号线改名留 P1） |
| 7 | 页面能按城市/线路/站名检索（含拼音） | `docs/validation-s5.md`、`web/lib/search.ts` | 索引 443 条（423 站 + 20 线）；22 条用例全过；p50 **0.039 ms**；「按城市」在单城阶段等同空操作（§12 脚注） | ✅（城市检索见脚注） |
| 8 | 首屏可用、无控制台报错、静态导出可构建 | `docs/validation-s3.md`、`docs/validation-s4.md`、`docs/validation-s6.md` | `npm run verify` **21 项全过**；产物 4.05 MB（gzip ≈ 0.91 MB）；线上 17 资源 0 个 ≥400、JS 错误 0；首屏 4,073,741 B → gzip 897,582 B | ✅ |
| 9 | 所有数据文件标注来源、许可、截止日期 | `data/README.md` | 6 个进仓库的数据文件逐行三问；ODbL 四条义务已写入 | ✅ |

## 交付物清单（§12 四项）

1. 数据：`data/processed/shanghai/{lines,station,transfer}.json` + `segment.geojson` + `data/processed/basemap/{shanghai-basemap,shanghai-sea}.geojson`
2. 三问表：`data/README.md`
3. 页面：<https://yukkki305.github.io/subways/>（底图 + 线路 + 车站 + 点击详情 + 检索）
4. 可重跑管道：`python pipeline/run_s1.py --from S1-3`（S1-3 → S1-6），S2 侧 `08→13` 六个脚本按序跑

## 遗留（不阻塞 P0 签字，记入 P1）

| 项 | 影响 | 去向 |
| --- | --- | --- |
| 17 号线「国家会展中心」应为「诸光路」 | 站名、站序、S2-5 那条 793 m 换乘 | P1 改名并重跑 S2-3→S2-7 |
| 12 条换乘中 9 条 `needs_review` | 换乘类型（通道/出站）为人工判定 | P1 核官方口径 |
| 山东 39 条 + 南通 4 条关系未定城市 | 省面无闭合 | P1 下载河北/河南后重跑 S1-6 |
| 江苏省面用 11 个地级市并集（缺南通、盐城） | 江苏城市归属覆盖面 | P1 补齐 |
| 底图为 P0 极简版（无 POI、无道路） | 视觉信息量 | P1 换自托管 PMTiles |
| 4 条线颜色 `colour_verified=false` | 颜色可能与官图有偏差 | P1 复核 |

## 时间盒

- 计划 2–3 周；实际从 S0 探测（2026-11-01）到 S6 上线（2026-11-03），**3 个日历日**（含夜间连续作业），未超时。
