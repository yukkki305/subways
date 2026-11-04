# 换乘判定表（S2-5）

> 由 `pipeline/11_build_transfers.py` 从 `station.json` 的换乘候选 + 脚本内的 `GROUP_TYPES` 渲染，**请勿手改**；
> 要改类型，改脚本里的 `GROUP_TYPES` 后重跑。

## 口径（ADR R5 / R7）

- 只表达**未合并**的两个站；合并成一站的多线站不产生 transfer。
- `type` ∈ 同站 / 通道 / 出站换乘；`walk_minutes` 无可靠来源，一律 `null`。
- OSM 没有换乘类型字段，站内通道要素也很稀疏（本次探查候选站附近仅 113 条带 tunnel/covered/indoor 的步行要素），
  所以类型是**人工判定**，置信度 `high` 视为定案，`medium`/`low` 标 `needs_review`。

## 统计

| 项 | 值 |
| --- | --- |
| 换乘条数 | 3 |
| 待复核 | 3 |
| 类型：通道 | 3 |

## 明细

| 站名 | 站距 m | A 侧线路 | B 侧线路 | 类型 | 置信度 | 依据 |
| --- | ---: | --- | --- | --- | --- | --- |
| 白云文化广场 | 388.9 | gz-line-12 | gz-line-2 | 通道 ⚠️ | low | 2 号线与 12 号线同名站，OSM 站距 390 m；12 号线该段为新建站体，是否为站内通道、及是否已开通运营均待核 |
| 南村万博 | 352.8 | gz-line-18 | gz-line-7 | 通道 ⚠️ | medium | 7 号线与 18 号线同名站，OSM 站距 352 m；18 号线为深层站，两站经站内长通道连通。步行时间无可靠来源，按 ADR R5 留空 |
| 磨碟沙 | 336.3 | gz-line-18 | gz-line-8 | 通道 ⚠️ | medium | 8 号线与 18 号线同名站，OSM 站距 337 m；18 号线为深层站，经站内通道连通。待现场核对通道长度 |

## 待人工确认清单

- **白云文化广场**（388.9 m，gz-station-bai-yun-wen-hua-guang-chang ↔ gz-station-bai-yun-wen-hua-guang-chang-2） 现判 通道 / low：2 号线与 12 号线同名站，OSM 站距 390 m；12 号线该段为新建站体，是否为站内通道、及是否已开通运营均待核
- **南村万博**（352.8 m，gz-station-nan-cun-wan-bo ↔ gz-station-nan-cun-wan-bo-2） 现判 通道 / medium：7 号线与 18 号线同名站，OSM 站距 352 m；18 号线为深层站，两站经站内长通道连通。步行时间无可靠来源，按 ADR R5 留空
- **磨碟沙**（336.3 m，gz-station-mo-die-sha ↔ gz-station-mo-die-sha-2） 现判 通道 / medium：8 号线与 18 号线同名站，OSM 站距 337 m；18 号线为深层站，经站内通道连通。待现场核对通道长度
