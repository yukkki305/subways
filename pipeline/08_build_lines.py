#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S2-2 第三步：把人工判定好的映射表转成 `lines.json`（线路 + 支线骨架）。

输入：
  `data/manual/shanghai-relation-mapping.csv`（S2-2 第一/二步的人工判定）
  `data/processed/relation-index.json`（S1-5，取站序、颜色、标签）
输出：
  `data/processed/shanghai/lines.json`

只产出**线路与支线**这一层；站点实体、区间几何、换乘、属性和里程分别由 S2-3…S2-6 补。
站序暂时存站名（S2-3 再把站名解析成 OSM 节点并分配 stable id）。

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\08_build_lines.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
CSV_PATH = P.manual_mapping_csv
INDEX = P.relation_index_global() if CFG.code == "sh" else P.relation_index()  # 全局清单只归上海，其它城读本城子集
OUT = P.lines_json

CITY = CFG.city

# 环线的起点站由人工指定（ADR R3）；站序会旋转到从 loop_start 开始
LOOP_START = dict(CFG.loop_start)

# 线路名固定写法：站名不带「站」，线路名不带城市前缀（AGENTS.md 第 9 节）
NAME_OVERRIDE = {
    "sh-line-pujiang": "浦江线",
    "sh-line-maglev": "磁浮线",
    # 广州 12 号线在 OSM 里按区段命名为「12号线东段」；我们建的是整条 12 号线（东段 + 西北段支线）
    "gz-line-12": "12号线",
}

# OSM 关系名里混着服务等级（「16号线普通车」），线路名要剥掉
SERVICE_WORDS = ("普通车", "大站车", "直达车", "大站快车", "区间车")

# OSM 里各城线路名前缀不统一（广州「地铁 1号线」、成都「成都地铁1号线」），
# 按 AGENTS.md 第 9 节，线路名不带城市前缀，统一剥掉
CITY_SHORT = CFG.city[:-1] if CFG.city.endswith("市") else CFG.city
NAME_PREFIXES = ("地铁", "轨道交通", "轻轨", CFG.name, CFG.city, CITY_SHORT)


def norm_name(raw: str) -> str:
    """把 OSM 的线路名收敛成「N号线」。

    三种写法都要处理：`地铁1号线`、`合肥轨道交通1号线: 九联圩→张洼`、`6号线-上行`。
    """
    s = (raw or "").replace("：", ":").split(":")[0].strip()
    for w in SERVICE_WORDS:
        s = s.replace(w, "")
    changed = True
    while changed:  # 「合肥」+「轨道交通」要剥两层
        changed = False
        for pfx in NAME_PREFIXES:
            if pfx and s.startswith(pfx):
                s = s[len(pfx):].strip()
                changed = True
    return re.sub(r"[-－]?(上行|下行)$", "", s).strip()


def sort_lines_key(line_id: str) -> tuple:
    """1…18 按数字排，浦江/磁浮这类放最后。"""
    pfx = CFG.line_id_prefix  # 已经是「<code>-line-」，不要再拼一次
    tail = line_id[len(pfx):] if line_id.startswith(pfx) else line_id
    return (0, int(tail), "") if tail.isdigit() else (1, 0, tail)


def rd(d: dict, key: str):
    v = (d.get(key) or "").strip()
    return v or None


def load_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    rows = load_rows()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    rels = {str(r["id"]): r for r in index["relations"]}

    keeps = [r for r in rows if r["decide"] == "保留"]
    merges = [r for r in rows if r["decide"] == "合并"]

    merged_by_branch: dict[str, list[dict]] = defaultdict(list)
    for r in merges:
        merged_by_branch[r["target_branch"]].append(r)

    by_line: dict[str, list[dict]] = defaultdict(list)
    for r in keeps:
        by_line[r["target_line"]].append(r)

    errors: list[str] = []
    lines: list[dict] = []

    for line_id in sorted(by_line, key=sort_lines_key):
        branches: list[dict] = []
        for r in sorted(by_line[line_id], key=lambda x: (x["target_branch"] != f"{line_id}-main", x["target_branch"])):
            branch_id = r["target_branch"]
            rec = rels.get(r["relation_id"])
            if rec is None:
                errors.append(f"{line_id} 的来源关系 {r['relation_id']} 不在 relation-index 里")
                continue
            stops = list(rec.get("stop_names") or [])
            is_loop = r["is_loop"] == "true"
            loop_start = LOOP_START.get(line_id) if is_loop else None
            if is_loop and loop_start:
                if loop_start not in stops:
                    errors.append(f"{branch_id} 的 loop_start「{loop_start}」不在站序里")
                else:
                    k = stops.index(loop_start)
                    stops = stops[k:] + stops[:k]
            merged = merged_by_branch.get(branch_id, [])
            base_name = norm_name(rec.get("name"))
            kept_service = (rec.get("name") or "").split("：")[0].replace(base_name, "").strip()
            service_levels = sorted(
                {
                    (rels[m["relation_id"]].get("name") or "").split("：")[0].replace(base_name, "").strip()
                    for m in merged
                    if m["relation_id"] in rels
                }
                - {"", base_name, kept_service}
            )
            branches.append(
                {
                    "id": branch_id,
                    "is_main": branch_id == f"{line_id}-main",
                    "is_loop": is_loop,
                    "loop_start": loop_start,
                    # 广州等地 OSM 关系常没有 from/to 标签，用站序首末站兜底（环线仍为 None）
                    "from": None if is_loop else (rd(rec, "from") or stops[0]),
                    "to": None if is_loop else (rd(rec, "to") or stops[-1]),
                    "ref": rd(rec, "ref"),
                    "stop_count": len(stops),
                    "stops": stops,
                    "stops_by_city": (rec.get("attribution") or {}).get("stops_by_city"),
                    "relation_ids": {
                        "kept": r["relation_id"],
                        "merged": sorted(m["relation_id"] for m in merged),
                    },
                    "service_levels": service_levels,
                }
            )

        mains = [b for b in branches if b["is_main"]]
        if len(mains) != 1:
            errors.append(f"{line_id} 的 main branch 数是 {len(mains)}")

        main_rec = rels[mains[0]["relation_ids"]["kept"]] if mains else {}
        tags = main_rec.get("tags") or {}
        name = NAME_OVERRIDE.get(line_id) or norm_name(main_rec.get("name")) or line_id
        all_stops = {s for b in branches for s in b["stops"]}
        lines.append(
            {
                "id": line_id,
                "city": CITY,
                "name": name,
                "name_en": rd(tags, "name:en"),
                "colour": rd(main_rec, "colour"),
                "colour_source": "osm",
                "type": main_rec.get("transit_type"),
                "operator": rd(main_rec, "operator"),
                "opened": None,
                "length_km": None,
                "length_km_official": None,
                "branch_count": len(branches),
                "stop_count_total": len(all_stops),
                "branches": branches,
                "source": "OpenStreetMap（省级 PBF）",
                "source_license": "ODbL-1.0",
                "as_of": index.get("snapshot_date"),
            }
        )

    # ---- 结构校验 ----
    seen_line = set()
    seen_branch = set()
    for ln in lines:
        if ln["id"] in seen_line:
            errors.append(f"line id 重复：{ln['id']}")
        seen_line.add(ln["id"])
        for b in ln["branches"]:
            if b["id"] in seen_branch:
                errors.append(f"branch id 重复：{b['id']}")
            seen_branch.add(b["id"])
            if b["stop_count"] != len(b["stops"]):
                errors.append(f"{b['id']} 的 stop_count 与站序长度不符")
            if b["is_loop"] and (b["from"] or b["to"]):
                errors.append(f"{b['id']} 是环线但 from/to 非空")
            if not b["stops"]:
                errors.append(f"{b['id']} 没有站")

    out = {
        "city": CITY,
        "city_code": CITY_CODE,
        "snapshot_date": index.get("snapshot_date"),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rules": "docs/decisions/0001-modeling-rules.md（R1 线路与支线、R2 ID、R3 环线）",
        "mapping_table": "data/manual/shanghai-relation-mapping.csv",
        "counts": {
            "lines": len(lines),
            "branches": sum(ln["branch_count"] for ln in lines),
            "stations_sum_by_branch": sum(b["stop_count"] for ln in lines for b in ln["branches"]),
            "stations_unique_by_line": sum(ln["stop_count_total"] for ln in lines),
        },
        "lines": lines,
    }

    # ---- 报表 ----
    print(f"{'线路':<16}{'名称':<8}{'branch':<20}{'站数':>5}  区间")
    print("-" * 74)
    for ln in lines:
        for b in ln["branches"]:
            span = "环线（起于 {}）".format(b["loop_start"]) if b["is_loop"] else f"{b['from']} ↔ {b['to']}"
            print(f"{ln['id']:<16}{ln['name']:<8}{b['id']:<20}{b['stop_count']:>5}  {span}")
    print()
    print(
        f"lines {out['counts']['lines']}｜branches {out['counts']['branches']}｜"
        f"按 branch 累计站次 {out['counts']['stations_sum_by_branch']}｜按线路去重 {out['counts']['stations_unique_by_line']}"
    )

    if errors:
        print()
        print(f"[失败] {len(errors)} 项：")
        for e in errors:
            print(f"  - {e}")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    size = OUT.stat().st_size
    print(f"\n写出 {OUT.relative_to(REPO)}：{size:,} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
