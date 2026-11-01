# -*- coding: utf-8 -*-
"""S2-5 换乘：把 S2-3 的 22 条换乘候选落成 transfer.json

判定口径（ADR R5）：
- 只表达**未合并**的两个站（合并成同一站的不产生 transfer）；
- `type` ∈ 同站 / 通道 / 出站换乘；
- `walk_minutes` 一律 `null`（ADR R7：无可靠来源不编数字）。

类型从哪来（重要）：
- OSM **没有**换乘类型字段，站内通道的制图也很稀疏（本次探查：候选站附近带
  tunnel/covered/indoor 的步行要素仅 113 条，多数候选 A 侧 0 节点），
  所以类型**不能从几何推导**。
- 因此 `TYPE_TABLE` 是**人工判定表**，逐条写在这里、写进 `docs/mappings/transfer-decisions.md`，
  并带 `confidence`：`high` 记为定案，`medium`/`low` 记 `needs_review=true`，等人工核对后改这张表。
- 改类型只改这张表，重跑脚本即可，不要手改产物。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATIONS = REPO / "data" / "processed" / "shanghai" / "station.json"
OUT = REPO / "data" / "processed" / "shanghai" / "transfer.json"
DOC = REPO / "docs" / "mappings" / "transfer-decisions.md"

TYPES = ("同站", "通道", "出站换乘")

# 键 = (站名, station_a 的 slug 前缀特征) → 该组的类型、置信度、依据
# 组内所有成对候选用同一判定；三站组会产生 3 对，四站组更多，都按组给同一条依据。
GROUP_TYPES: dict[str, dict] = {
    "静安寺": {"type": "通道", "confidence": "high",
             "note": "2/7/14 号线共用站体，站厅层与站台层之间为站内通道换乘"},
    "南京西路": {"type": "通道", "confidence": "high",
              "note": "2/12/13 号线站体相连，站内通道换乘"},
    "徐家汇": {"type": "通道", "confidence": "high",
             "note": "1/9/11 号线共用枢纽，站内通道换乘"},
    "宜山路": {"type": "通道", "confidence": "medium",
             "note": "3/4 号线与 9 号线之间为站内通道；通道较长，建议现场核对步行时间"},
    "曹杨路": {"type": "通道", "confidence": "medium",
             "note": "3/4/11 号线与 14 号线之间为站内通道；14 号线站体较深"},
    "桂林路": {"type": "通道", "confidence": "low",
             "note": "9 号线与 15 号线同名站，疑似站内通道，待核对是否需出站"},
    "上海火车站": {"type": "出站换乘", "confidence": "high",
               "note": "1 号线与 3/4 号线站体分离，需出站经地面换乘"},
    "上海南站": {"type": "出站换乘", "confidence": "medium",
              "note": "15 号线站体在北广场一侧，与 1/3 号线需出站；待核对是否有连通通道"},
    "陆家嘴": {"type": "出站换乘", "confidence": "medium",
             "note": "14 号线站体与 2 号线不连通，需出站换乘；待核对"},
    "娄山关路": {"type": "出站换乘", "confidence": "low",
              "note": "2 号线与 15 号线同名站相距约 445 m，疑似出站换乘，待核对"},
    "浦东南路": {"type": "出站换乘", "confidence": "low",
              "note": "2 号线与 14 号线同名站相距约 647 m，疑似出站换乘，待核对（也不排除 OSM 站位偏移）"},
    "国家会展中心": {"type": "出站换乘", "confidence": "low",
                "note": "2 号线与 17 号线同名站相距约 793 m，疑似出站换乘；OSM 里 17 号线该站官方名为诸光路，待核对站位与站名"},
}


def main() -> int:
    st = json.loads(STATIONS.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in st["stations"]}

    out = []
    stats = {"total": 0, "by_type": {}, "needs_review": 0}
    for c in st["transfer_candidates"]:
        name = c["name"]
        rule = GROUP_TYPES.get(name)
        if rule is None:
            raise SystemExit(f"[错误] 换乘候选「{name}」还没有类型判定，请先补 GROUP_TYPES")
        a, b = by_id[c["station_a"]], by_id[c["station_b"]]
        rec = {
            "id": f"{a['id']}--{b['id']}",
            "name": name,
            "station_a": a["id"],
            "station_b": b["id"],
            "lines_a": a["lines"],
            "lines_b": b["lines"],
            "coord_a": a["coord"],
            "coord_b": b["coord"],
            "dist_m": c["dist_m"],
            "type": rule["type"],
            "type_confidence": rule["confidence"],
            "type_note": rule["note"],
            "walk_minutes": None,
            "needs_review": rule["confidence"] != "high",
            "source": "人工判定（docs/mappings/transfer-decisions.md），几何距离来自 OSM",
            "source_license": "ODbL-1.0",
            "as_of": st["snapshot_date"],
        }
        if rec["type"] not in TYPES:
            raise SystemExit(f"[错误] 类型非法：{rec['type']}")
        out.append(rec)
        stats["total"] += 1
        stats["by_type"][rec["type"]] = stats["by_type"].get(rec["type"], 0) + 1
        if rec["needs_review"]:
            stats["needs_review"] += 1

    # 结构校验
    ids = [r["id"] for r in out]
    assert len(ids) == len(set(ids)), "transfer id 重复"
    for r in out:
        assert r["station_a"] != r["station_b"], "自环"
        assert r["station_a"] in by_id and r["station_b"] in by_id, "站不存在"
        assert r["dist_m"] > 0
    # 每条候选都被覆盖
    assert len(out) == len(st["transfer_candidates"])

    doc = {
        "city": "上海市",
        "city_code": "sh",
        "snapshot_date": st["snapshot_date"],
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rules": "ADR R5（只表达未合并两站；type ∈ 同站/通道/出站换乘）+ R7（walk_minutes 无来源填 null）",
        "stats": stats,
        "transfers": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    # 人可读表
    lines = [
        "# 换乘判定表（S2-5）",
        "",
        "> 由 `pipeline/11_build_transfers.py` 从 `station.json` 的换乘候选 + 脚本内的 `GROUP_TYPES` 渲染，**请勿手改**；",
        "> 要改类型，改脚本里的 `GROUP_TYPES` 后重跑。",
        "",
        "## 口径（ADR R5 / R7）",
        "",
        "- 只表达**未合并**的两个站；合并成一站的多线站不产生 transfer。",
        "- `type` ∈ 同站 / 通道 / 出站换乘；`walk_minutes` 无可靠来源，一律 `null`。",
        "- OSM 没有换乘类型字段，站内通道要素也很稀疏（本次探查候选站附近仅 113 条带 tunnel/covered/indoor 的步行要素），",
        "  所以类型是**人工判定**，置信度 `high` 视为定案，`medium`/`low` 标 `needs_review`。",
        "",
        "## 统计",
        "",
        f"| 项 | 值 |",
        f"| --- | --- |",
        f"| 换乘条数 | {stats['total']} |",
        f"| 待复核 | {stats['needs_review']} |",
    ]
    for t, n in sorted(stats["by_type"].items()):
        lines.append(f"| 类型：{t} | {n} |")
    lines += ["", "## 明细", "",
              "| 站名 | 站距 m | A 侧线路 | B 侧线路 | 类型 | 置信度 | 依据 |",
              "| --- | ---: | --- | --- | --- | --- | --- |"]
    for r in sorted(out, key=lambda x: (-x["dist_m"], x["name"])):
        la = "、".join(x.replace("sh-line-", "") for x in r["lines_a"])
        lb = "、".join(x.replace("sh-line-", "") for x in r["lines_b"])
        flag = "" if r["type_confidence"] == "high" else " ⚠️"
        lines.append(f"| {r['name']} | {r['dist_m']:.1f} | {la} | {lb} | {r['type']}{flag} | "
                     f"{r['type_confidence']} | {r['type_note']} |")
    lines += ["", "## 待人工确认清单", ""]
    pend = [r for r in out if r["needs_review"]]
    if not pend:
        lines.append("（无）")
    else:
        for r in sorted(pend, key=lambda x: (-x["dist_m"], x["name"])):
            lines.append(f"- **{r['name']}**（{r['dist_m']:.1f} m，{r['station_a']} ↔ {r['station_b']}）"
                         f" 现判 {r['type']} / {r['type_confidence']}：{r['type_note']}")
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"写出 {OUT}（{OUT.stat().st_size:,} B）与 {DOC}")
    print("统计:", json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
