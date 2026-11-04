# -*- coding: utf-8 -*-
"""S2-6 属性补全：把线路层的属性补齐到 lines.json

数据来源与口径（ADR R6 / R7）：
- `length_km`          ← `segment.geojson` 的几何实测（按线取**并集**后再量，避免支线重叠重复计）
- `length_km_sum`      ← 同一线各 branch 直接相加（含重复段），仅作参考
- `length_km_official` ← `data/manual/shanghai-lines.csv`（人工表，来源见该表 source_url）
- `opened`             ← 同上人工表（首个区段开通日）
- `operator`           ← 优先人工表，缺失时回退 OSM
- `colour`             ← ADR R6：官图为准，OSM 兜底。官图 JPEG 采样得到的高频色簇与 OSM
                          颜色欧氏距离 ≤30 视为一致、沿用 OSM；>30 且簇可信时改用官图色；
                          官图无法分辨的（细线/灰线/色相重叠）保留 OSM 并标 `colour_verified=false`
- `name_en`            ← 归一成 "Line N" / "Maglev Line" / "Pujiang Line"，原路线描述存 `name_en_route`
"""
from __future__ import annotations

import csv
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

TF = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)


def to_metric(geom):
    """WGS-84 经纬度 → UTM 51N 米制，供量长度用（与底图脚本同一投影）。"""
    return shapely.transform(
        geom, lambda c: np.stack(TF.transform(c[..., 0], c[..., 1]), axis=-1))

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
LINES = P.lines_json
SEGS = P.segment_geojson
MANUAL = P.manual_lines_csv
DOC = (P.docs_colors_md if CFG.code == "sh"
       else P.doc(f"colors-{CFG.code}.md"))

# 官图采样结果（%TEMP%\shmetro-map 的 metroView.jpg，5497×7693，2025-12-26）
# 每条：官图色、采样像素数、与 OSM 的欧氏距离
COLOUR_OVERRIDE = {
    "sh-line-2":  ("#80BE23", 52203, 48.1),
    "sh-line-4":  ("#451D83", 56296, 38.0),
    "sh-line-5":  ("#944D9A", 44290, 48.5),
    "sh-line-14": ("#62601F", 38143, 49.0),
}
# 官图上分辨不出来的线（细线、灰色、或与其它线色相重叠）：保留 OSM 并标记未核实
COLOUR_UNVERIFIED = {
    "sh-line-10": "淡紫在官图上面积太小，色簇与 13 号线粉、4 号线紫混在一起",
    "sh-line-16": "水绿细线，采样簇落到 8 号线蓝上",
    "sh-line-maglev": "青绿短直线，与 12 号线深绿难分",
    "sh-line-pujiang": "灰色线，与站名/底图灰无法区分",
}

NAME_EN = {"sh-line-maglev": "Maglev Line", "sh-line-pujiang": "Pujiang Line"}


def main() -> int:
    lines = json.loads(LINES.read_text(encoding="utf-8"))
    segs = json.loads(SEGS.read_text(encoding="utf-8"))
    manual = {}
    with MANUAL.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            manual[row["line_id"]] = row

    # 1) 几何长度：按线取并集
    by_line: dict[str, list] = {}
    for f in segs["features"]:
        by_line.setdefault(f["properties"]["line_id"], []).append(shape(f["geometry"]))

    stats = {"adopted": 0, "verified": 0, "unverified": 0}
    for ln in lines["lines"]:
        lid = ln["id"]
        geoms = by_line.get(lid, [])
        metric = [to_metric(g) for g in geoms]
        union = unary_union(metric) if metric else None
        ln["length_km"] = round(union.length / 1000, 2) if union is not None else None
        ln["length_km_sum"] = round(sum(g.length for g in metric) / 1000, 2)
        ln["length_km_method"] = "并集（各 branch 几何 dissolve 后量长）"

        m = manual.get(lid, {})
        off = m.get("length_km_official")
        ln["length_km_official"] = float(off) if off else None
        if ln["length_km"] and ln["length_km_official"]:
            ln["length_diff_pct"] = round(
                (ln["length_km"] - ln["length_km_official"]) / ln["length_km_official"] * 100, 1)
        else:
            ln["length_diff_pct"] = None

        ln["opened"] = m.get("opened") or None
        ln["operator_official"] = m.get("operator") or None
        if m.get("operator"):
            ln["operator"] = m["operator"]
            ln["operator_source"] = m.get("source_url")
        else:
            ln["operator_source"] = "OSM（人工表未提供）"

        ln["colour_official_name"] = m.get("colour_name") or None
        ln["colour"] = (ln["colour"] or "").upper()
        if lid in COLOUR_OVERRIDE:
            hexs, px, dist = COLOUR_OVERRIDE[lid]
            ln["colour_osm"] = ln["colour"]
            ln["colour"] = hexs
            ln["colour_source"] = "官图采样（替代 OSM）"
            ln["colour_sample_px"] = px
            ln["colour_osm_dist"] = dist
            ln["colour_verified"] = True
            stats["adopted"] += 1
        elif lid in COLOUR_UNVERIFIED:
            ln["colour_source"] = "OSM（官图未核实）"
            ln["colour_verified"] = False
            ln["colour_note"] = COLOUR_UNVERIFIED[lid]
            stats["unverified"] += 1
        else:
            ln["colour_source"] = "OSM（与官图采样一致）"
            ln["colour_verified"] = True
            stats["verified"] += 1

        ln["name_en_route"] = ln.get("name_en")
        ln["name_en"] = NAME_EN.get(lid) or "Line " + ln["name"].replace("号线", "")

    lines["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines["attribute_rules"] = "ADR R6（颜色官图为准）/ R7（里程双轨、属性走人工表）"
    LINES.write_text(json.dumps(lines, ensure_ascii=False, indent=1), encoding="utf-8")

    # 2) 人可读的颜色表
    def sort_key(l):
        digits = "".join(c for c in l["name"] if c.isdigit())
        return (l["type"] != "metro", int(digits) if digits else 99, l["name"])

    rows = sorted(lines["lines"], key=sort_key)
    out = [
        "# 线路颜色（S2-6）",
        "",
        "> 由 `pipeline/12_build_attributes.py` 生成。口径见 ADR R6：**官图为准，OSM 兜底**；",
        "> 官图采样自 `shmetro.com` 的官方线路图 JPEG（5497×7693，`Last-Modified: 2025-12-26 14:45:39 GMT`），",
        "> 取高饱和像素的色簇，与 OSM 颜色比欧氏距离，>30 视为不一致。",
        "",
        "| 线路 | 最终色 | 官图色名 | 来源 | 与 OSM 距离 | 备注 |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for ln in rows:
        dist = ln.get("colour_osm_dist")
        out.append(f'| {ln["name"]} | `{ln["colour"]}` | {ln.get("colour_official_name") or "—"} | '
                   f'{ln["colour_source"]} | {dist if dist is not None else "—"} | {ln.get("colour_note") or ""} |')
    out += ["", f"**统计**：官图替代 {stats['adopted']} 条、与官图一致 {stats['verified']} 条、"
                f"官图无法分辨 {stats['unverified']} 条（保留 OSM 并标 `colour_verified=false`）。"]
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("\n".join(out) + "\n", encoding="utf-8")

    # 3) 校验 + 报告
    errs = []
    for ln in lines["lines"]:
        for k in ("colour", "opened", "length_km", "length_km_official", "name_en"):
            if ln.get(k) in (None, ""):
                errs.append(f'{ln["id"]} 缺 {k}')
        if ln["colour"] and not ln["colour"].startswith("#"):
            errs.append(f'{ln["id"]} colour 非 hex')
    def fmt(v, spec="7.2f"):
        return format(v, spec) if isinstance(v, (int, float)) else "—".rjust(len(spec.split(".")[-1]) + 4)

    print(f"{'线路':10s} {'开通':12s} {'实测km':>8s} {'官方km':>8s} {'差%':>7s} {'颜色':9s} 来源")
    for ln in rows:
        print(f'{ln["name"]:10s} {str(ln["opened"] or "—"):12s} {fmt(ln["length_km"]):>8s} '
              f'{fmt(ln["length_km_official"]):>8s} {fmt(ln["length_diff_pct"], "7.1f"):>7s} '
              f'{ln["colour"]:9s} {ln["colour_source"]}')
    print(f"\n统计: {json.dumps(stats, ensure_ascii=False)}")
    if errs:
        print("[失败] 缺字段:", errs)
        return 1
    print("[通过] 20 条线路属性齐全")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
