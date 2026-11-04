#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S2-2 第一步：导出「关系 → 线路」映射表骨架。

输入：`data/processed/relation-index.json`（S1-5 产物，含上海子集 65 条关系）
输出：`data/manual/shanghai-relation-mapping.csv`（65 行 × 16 列，后 4 列留空供人工填）

本脚本**只生成骨架，不判断归属**。已填过判定的表默认拒绝覆盖（加 `--force` 才重建）。

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\06_export_mapping.py
    ... pipeline\\06_export_mapping.py --force     # 确实要重建（会清空人工判定）
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
INDEX = P.relation_index_global() if CFG.code == "sh" else P.relation_index()  # 全局清单只归上海，其它城读本城子集
OUT_CSV = P.manual_mapping_csv

PROVINCE_KEY = CFG.pbfs[0]
CITY = CFG.city

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
    for kw in ("普通车", "大站车", "直达车", "大站快车", "区间"):
        if kw in name:
            hints.append("?服务变体")
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已有的人工判定")
    args = ap.parse_args()

    if not INDEX.exists():
        raise SystemExit(f"缺少 {INDEX}，先跑 S1-5（pipeline/04_track.py）")

    if OUT_CSV.exists() and not args.force:
        existing = list(csv.DictReader(OUT_CSV.open(encoding="utf-8")))
        filled = sum(1 for r in existing if (r.get("decide") or "").strip())
        if filled:
            sys.exit(
                f"{OUT_CSV.relative_to(REPO)} 里已有 {filled} 行人工判定，拒绝覆盖。\n"
                "  只想校验/重渲文档请用 pipeline/07_check_mapping.py；确实要重建骨架请加 --force"
            )

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    # 映射表只覆盖「本城 + 跨城对端市」的关系：
    # 上海取 上海市 + 苏州市（11 号线花桥段），广州取 广州市 + 佛山市（广佛线 / 7 号线顺德段）。
    # 省内其它城市（深圳、东莞…）由各自的城市任务处理，不在这里出现。
    allowed = {CITY, *CFG.worksheet_cities}
    in_prov = [r for r in index["relations"] if PROVINCE_KEY in (r.get("provinces") or [])]

    def _nets(rec: dict) -> set[str]:
        raw = rec.get("network")
        if isinstance(raw, str):
            return {raw}
        return set(raw or [])

    attributed = [r for r in in_prov if (r.get("city") or "")]
    if not attributed:
        # 过渡规则：归属步骤还没给本城回填 city 时（上海目前的状况），
        # 退回「省面内全收」的老行为，避免把该要的关系漏掉。
        rels = in_prov
        if len(in_prov):
            print(f"   [过滤] {PROVINCE_KEY} 内 {len(in_prov)} 条，city 尚未回填 → 全收")
    else:
        rels = [
            r
            for r in in_prov
            if (r.get("city") or "") in allowed
            or (not (r.get("city") or "") and _nets(r) & set(CFG.network))
        ]
        print(
            f"   [过滤] {PROVINCE_KEY} 内 {len(in_prov)} 条，保留 {len(rels)} 条"
            f"（{', '.join(sorted(allowed))}）"
        )
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

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 无 BOM（AGENTS.md 第 7 节）；用 Excel 打开请按 UTF-8 导入
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    by_type = Counter(r["transit_type"] for r in rows)
    print(f"写出 {OUT_CSV.relative_to(REPO)}：{len(rows)} 行 × {len(FIELDS)} 列（后 4 列留空）")
    print("按制式：" + "、".join(f"{TYPE_LABEL.get(t, t)} {n}" for t, n in by_type.items()))
    print("按归属市：" + "、".join(f"{k} {v}" for k, v in Counter(r["city"] or "(空)" for r in rows).most_common()))
    print(f"有孪生提示的行：{len(twin)}；待填 {len(rows)} 行 × 4 列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
