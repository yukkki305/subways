#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S2-2 第一步：导出「关系 → 线路」映射表骨架。

输入：`data/processed/relation-index.json`（S1-5 产物，含上海子集 65 条关系）
输出：
  - `data/manual/shanghai-relation-mapping.csv`  机器可读，供人工填判定列
  - `docs/mappings/shanghai-relations.md`        同样的内容，人可读版

本脚本**不判断任何归属**，只做三件事：筛选上海子集、按制式排序、给每条关系填一个
「机器提示」（hint），提示一律带问号前缀，必须人工确认后才算数。

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\06_export_mapping.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "data" / "processed" / "relation-index.json"
OUT_CSV = REPO / "data" / "manual" / "shanghai-relation-mapping.csv"
OUT_MD = REPO / "docs" / "mappings" / "shanghai-relations.md"

PROVINCE_KEY = "shanghai"          # 记录的 provinces 里含它就属于上海 extract
CITY = "上海市"

TYPE_ORDER = ["metro", "apm", "maglev", "lrt", "tram", "monorail"]
TYPE_LABEL = {
    "metro": "地铁",
    "apm": "自动旅客捷运",
    "maglev": "磁浮",
    "lrt": "轻轨 / 有轨",
    "tram": "有轨电车",
    "monorail": "单轨",
}

FIELDS = [
    "relation_id",
    "name",
    "transit_type",
    "ref",
    "colour",
    "from",
    "to",
    "unique_stops",
    "is_loop",
    "province",
    "city",
    "hint",
    "decide",          # 人工填：保留 / 合并 / 丢弃
    "target_line",     # 人工填：如 sh-line-11
    "target_branch",   # 人工填：如 sh-line-11-main / -b1
    "note",            # 人工填：理由、依据
]


def sort_key(rec: dict) -> tuple:
    t = TYPE_ORDER.index(rec["transit_type"]) if rec["transit_type"] in TYPE_ORDER else len(TYPE_ORDER)
    ref = rec.get("ref") or ""
    # ref 多为 "11" "浦江" "磁浮"；数字优先，按数值排
    try:
        ref_key = (0, int(ref))
    except (TypeError, ValueError):
        ref_key = (1, str(ref))
    stops = -(rec.get("stats", {}).get("unique_stops") or 0)
    return (t, ref_key, stops, rec.get("name") or "")


def hint_for(rec: dict, ref_count: dict, twin: dict) -> str:
    """机器提示：只给线索，不下结论。"""
    stops = rec.get("stats", {}).get("unique_stops") or 0
    city = rec.get("city") or ""
    name = rec.get("name") or ""
    hints: list[str] = []
    if stops == 0:
        hints.append("?母关系：0 站")
    if city and city != CITY:
        hints.append(f"?非上海：{city}")
    for kw, why in (
        ("普通车", "服务变体"),
        ("大站车", "服务变体"),
        ("直达车", "服务变体"),
        ("大站快车", "服务变体"),
        ("区间", "服务变体"),
    ):
        if kw in name:
            hints.append(f"?{why}")
            break
    if rec.get("is_loop"):
        hints.append("?环线")
    ref = rec.get("ref")
    if ref and ref_count.get(ref, 0) > 2 and stops > 0:
        hints.append(f"?同线多交路（ref={ref} 共 {ref_count[ref]} 条）")
    partner = twin.get(rec["id"])
    if partner:
        hints.append(f"?同站集：{partner}")
    return " ".join(hints)


def main() -> int:
    if not INDEX.exists():
        raise SystemExit(f"缺少 {INDEX}，先跑 S1-5（pipeline/04_track.py）")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    rels = [r for r in index["relations"] if PROVINCE_KEY in (r.get("provinces") or [])]
    rels.sort(key=sort_key)

    ref_count = Counter(r.get("ref") for r in rels if r.get("ref"))

    # 同站集配对：站名集合完全相同的两条关系（多为同一线路的双向）互为「孪生」
    by_stops: dict[tuple, list] = defaultdict(list)
    for r in rels:
        names = tuple(sorted(r.get("stop_names") or []))
        if len(names) >= 2:
            by_stops[names].append(r["id"])
    twin: dict = {}
    for _, ids in by_stops.items():
        if len(ids) == 2:
            twin[ids[0]] = ids[1]
            twin[ids[1]] = ids[0]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in rels:
        rows.append(
            {
                "relation_id": r["id"],
                "name": r.get("name") or "",
                "transit_type": r.get("transit_type") or "",
                "ref": r.get("ref") or "",
                "colour": r.get("colour") or "",
                "from": r.get("from") or "",
                "to": r.get("to") or "",
                "unique_stops": r.get("stats", {}).get("unique_stops") or 0,
                "is_loop": "true" if r.get("is_loop") else "false",
                "province": r.get("province") or "",
                "city": r.get("city") or "",
                "hint": hint_for(r, ref_count, twin),
                "decide": "",
                "target_line": "",
                "target_branch": "",
                "note": "",
            }
        )

    # CSV：UTF-8 无 BOM（AGENTS.md 第 7 节）；用 Excel 打开请按 UTF-8 导入
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    # Markdown：按制式分组，便于人读
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_type[row["transit_type"]].append(row)

    lines = [
        "# 上海关系映射表（S2-2 骨架，待人工判定）",
        "",
        f"- 来源：`data/processed/relation-index.json`（快照 {index.get('snapshot_date')}），筛选 `provinces` 含 `shanghai` 的关系",
        f"- 合计 **{len(rows)}** 条；按制式：" + "、".join(f"{TYPE_LABEL.get(t, t)} {len(v)}" for t, v in by_type.items()),
        "- 机器提示列带 `?` 前缀，**只是线索，不是结论**；`decide` / `target_line` / `target_branch` / `note` 四列由人工填",
        "- 填法：`decide` 取 `保留` / `合并` / `丢弃`；`合并` 表示这条关系不单独成 branch，但其站点必须出现在某条 branch 的站序里；`丢弃` 必须在 `note` 写理由",
        "",
        "> 规则依据：`docs/decisions/0001-modeling-rules.md` 的 R1（线路与支线划分）、R2（ID 规则）",
        "",
    ]

    for t in TYPE_ORDER + [k for k in by_type if k not in TYPE_ORDER]:
        group = by_type.get(t)
        if not group:
            continue
        lines.append(f"## {TYPE_LABEL.get(t, t)}（`{t}`，{len(group)} 条）")
        lines.append("")
        lines.append("| 关系 id | 名称 | 起 → 终 | ref | colour | 站数 | 环线 | 归属市 | 机器提示 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in group:
            endp = f"{row['from'] or '—'} → {row['to'] or '—'}"
            lines.append(
                f"| `{row['relation_id']}` | {row['name']} | {endp} | {row['ref'] or '—'} | "
                f"{row['colour'] or '—'} | {row['unique_stops']} | {'是' if row['is_loop'] == 'true' else ''} | "
                f"{row['city'] or '—'} | {row['hint'] or ''} |"
            )
        lines.append("")

    lines += [
        "## 待人工填写的四列",
        "",
        "1. `decide` —— 保留 / 合并 / 丢弃（65 行都要填，包括显然要丢的）",
        "2. `target_line` —— 如 `sh-line-11`；丢弃的填 `—`",
        "3. `target_branch` —— 如 `sh-line-11-main`、`sh-line-11-b1`",
        "4. `note` —— 理由；「合并/丢弃」必须写，且合并要写明并入哪条 branch",
        "",
        "判据（ADR R1）：20 条 line 各有且只有一个 `is_main`；65 条关系 100% 落在三列之一；每个 branch 至少来自 1 条关系。",
        "",
    ]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"写出 {OUT_CSV.relative_to(REPO)}（{len(rows)} 行）")
    print(f"写出 {OUT_MD.relative_to(REPO)}")
    print("\n按制式：" + "、".join(f"{TYPE_LABEL.get(t, t)} {len(v)}" for t, v in by_type.items()))
    print("按归属市：" + "、".join(f"{k} {v}" for k, v in Counter(r["city"] or "(空)" for r in rows).most_common()))
    hinted = Counter(r["hint"] for r in rows if r["hint"])
    if hinted:
        print("机器提示统计：")
        for k, v in hinted.most_common():
            print(f"  {v:>3}  {k}")
    print(f"待填 {len(rows)} 行 × 4 列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
