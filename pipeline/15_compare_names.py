"""S5-4 追补：站名比对（OSM 2026-11 ↔ GZUPA 2020-12）。

★★ 重要发现（2026-11-03）：GZUPA 的坐标字段不能直接用 ★★
    - `x` / `y` 实际是 **GCJ-02**（与 OSM 点做 GCJ 变换后仅差 18–360 m）；
    - `wgs84_x` / `wgs84_y` 是**错的**，相对 OSM 系统性偏 700–930 m（方向相反）。
    按 `AGENTS.md` §4「禁止纠偏后使用 GCJ-02」，GZUPA **不能作几何来源**，
    只能用于站名与站序的**人工比对**。因此本脚本**不用坐标**配对，只比站名集合。

维基百科一侧在本机网络不可达（zh.wikipedia.org TCP 000），未纳入。

产出：
- data/processed/name-diff.json
- docs/name-diff.md
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import geopandas as gpd

REPO = Path(r"E:\subway")
LINES_JSON = REPO / "data" / "processed" / "shanghai" / "lines.json"
GZUPA_SHP = Path(
    r"E:\subway-data\probe16\gzupa\out\1_subway_point\shanghai\shanghai_Layer_2020.shp"
)
OUT_JSON = REPO / "data" / "processed" / "name-diff.json"
OUT_MD = REPO / "docs" / "name-diff.md"

LINE_MAP = {f"line{i}": f"sh-line-{i}" for i in range(1, 19)}
LINE_MAP["浦江线"] = "sh-line-pujiang"
LINE_MAP["磁悬浮"] = "sh-line-maglev"

PREFIXES = ("一大会址·", "一大会址", "中共一大纪念馆·")


def norm(name: str) -> str:
    """归一化：只用于「疑似改名」提示，不改变判定本身。"""
    s = name.strip()
    for p in PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = s.replace("站", "").replace("·", "").replace(" ", "")
    return s


def main() -> None:
    lines = json.loads(LINES_JSON.read_text(encoding="utf-8"))["lines"]
    per_line: dict[str, list[str]] = {}
    for line in lines:
        seen: list[str] = []
        for br in line["branches"]:
            for name in br["stops"]:
                if name not in seen:
                    seen.append(name)
        per_line[line["id"]] = seen

    gz = gpd.read_file(GZUPA_SHP, engine="pyogrio")
    gz_names: dict[str, list[str]] = defaultdict(list)
    for _, row in gz.iterrows():
        line_id = LINE_MAP.get(str(row["line"]).strip())
        if line_id:
            gz_names[line_id].append(str(row["station"]).strip())

    report: dict[str, dict] = {}
    totals: dict[str, int] = defaultdict(int)
    md = [
        "# 站名差异清单：OSM（2026-11）↔ GZUPA（2020-12）",
        "",
        "> 生成脚本：`pipeline/15_compare_names.py`。**只比站名集合，不比坐标** —— "
        "GZUPA 的 `x`/`y` 是 GCJ-02、`wgs84_*` 字段整体偏约 900 m，按 `AGENTS.md` §4 "
        "只能作人工比对，不能当几何来源（详见 `docs/decisions/0002-gzupa-datum.md`）。",
        ">",
        "> GZUPA 2020 覆盖 18 条线（line1–13、16、17、18 + 浦江线 + 磁悬浮，无 14、15 号线），其余 2 条线只有 OSM 单边数据。",
        "> 归一化（去「一大会址·」前缀 / 括号内容 / 「站」字）只用于标出**疑似改名**，不改变判定。",
        "",
        "| 线路 | OSM 站数 | GZUPA 站数 | 同名 | 仅 OSM | 仅 GZUPA |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for line_id in sorted(gz_names, key=lambda s: (len(s), s)):
        osm = per_line.get(line_id, [])
        gz_list = gz_names[line_id]
        gz_set = set(gz_list)
        osm_set = set(osm)

        same = osm_set & gz_set
        only_osm = [n for n in osm if n not in gz_set]
        only_gz = sorted(gz_set - osm_set)

        gz_norm: dict[str, list[str]] = {}
        for n in only_gz:
            gz_norm.setdefault(norm(n), []).append(n)
        rename_hints = []
        for n in only_osm:
            k = norm(n)
            if k in gz_norm:
                rename_hints.append({"osm": n, "gzupa": gz_norm[k][0]})

        report[line_id] = {
            "osm_count": len(osm),
            "gzupa_count": len(gz_list),
            "same_count": len(same),
            "only_osm": only_osm,
            "only_gzupa": only_gz,
            "rename_hints": rename_hints,
        }
        totals["same_count"] += len(same)
        totals["only_osm"] += len(only_osm)
        totals["only_gzupa"] += len(only_gz)
        totals["osm"] += len(osm)
        totals["gz"] += len(gz_list)
        totals["hints"] += len(rename_hints)

        md.append(
            f"| {line_id} | {len(osm)} | {len(gz_list)} | {len(same)} | "
            f"{len(only_osm)} | {len(only_gz)} |"
        )

    md += [
        "",
        f"合计（18 条线）：OSM {totals['osm']} 站次 / GZUPA {totals['gz']} 站次；"
        f"同名 {totals['same_count']}、仅 OSM {totals['only_osm']}、仅 GZUPA {totals['only_gzupa']}、"
        f"归一化后疑似同名不同写 {totals['hints']} 处。",
        "",
        "## 差异明细",
        "",
    ]

    for line_id, r in report.items():
        if not (r["only_osm"] or r["only_gzupa"] or r["rename_hints"]):
            continue
        md.append(f"### {line_id}")
        md.append("")
        if r["rename_hints"]:
            md.append("**疑似改名（归一化后一致，需人工定案）**")
            md.append("")
            md.append("| OSM 现名 | GZUPA 2020 |")
            md.append("| --- | --- |")
            for x in r["rename_hints"]:
                md.append(f"| {x['osm']} | {x['gzupa']} |")
            md.append("")
        if r["only_osm"]:
            md.append("**仅 OSM 有**：" + "、".join(r["only_osm"]))
            md.append("")
        if r["only_gzupa"]:
            md.append("**仅 GZUPA 有**：" + "、".join(r["only_gzupa"]))
            md.append("")

    OUT_JSON.write_text(
        json.dumps(
            {
                "sources": {
                    "osm": "省级 PBF 快照 20261101",
                    "gzupa": "GZUPA subway-traffic-data-set 2020-12-31（仅站名，坐标不可用）",
                },
                "coverage_lines": sorted(gz_names),
                "method": "站名集合比对；归一化仅用于疑似改名提示",
                "totals": dict(totals),
                "lines": report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(
        f"比对 {len(gz_names)} 条线：同名 {totals['same_count']}、"
        f"仅 OSM {totals['only_osm']}、仅 GZUPA {totals['only_gzupa']}、"
        f"疑似改名 {totals['hints']}"
    )
    print("写出", OUT_JSON, "与", OUT_MD)


if __name__ == "__main__":
    main()
