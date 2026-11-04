"""S1-4 底图要素抽取：上海各级行政界 + 黄浦江/吴淞江/淀山湖/长江口/海岸线。

依据 S1-4 探查结论设计：
1. PBF 对象顺序为 nodes -> ways -> relations，**先扫关系收集 way id，再扫 way 取几何**；
   单遍 handler 里 relation() 收集、way() 匹配会命中 0。
2. fr extract 按省界裁切，跨省要素必须多文件并集（淀山湖 1122227、长江中心线 9392345 的成员 way
   分散在 shanghai 与 jiangsu 两份里）。
3. **不产出陆地填充面**：OSM 的上海市 L4 与各区界**含海域**，16 区并集 16,204.7 km²，是官方陆地
   6,340.5 km² 的 2.56 倍（崇明区 6,470.9、浦东新区 5,016.3 均海陆合并）；用 130 段 coastline 反推
   陆地也拼不出闭合岸线。故 P0 底图 = 单色背景（背景即陆地）+ 水面 + 行政界线，不画假海岸。
4. 黄浦江水面关系 197357 只有 1 个成员 way、2.73 km²（上游一段），不代表整条江 → 只取中心线；
   长江口同理，用长江中心线 9392345 的江口段（裁到 SCENE_BBOX）+ coastline，不伪造江面多边形。
5. 长江水面关系 1999842 的几何在 119.68–120.01 / 31.97–32.34（江阴—南通上游），不在上海视野内，
   由 SCENE_BBOX 过滤掉，不留无用要素。

产物：data/processed/basemap/shanghai-basemap.geojson
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import osmium
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon, box, mapping
from shapely.ops import polygonize, unary_union

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
if CFG.code != "sh":
    raise SystemExit(
        f"底图（S1-4）目前只做上海（P0 的精细底图：16 区界 + 淀山湖 + 长江/吴淞江/黄浦江 + 海岸线）。"
        f"当前城市 {CFG.code} 未定义水系与区界关系清单，按计划留给 P1b（见 docs/decisions/0004-city-config.md 的 D4）。"
    )

SNAPSHOT = P.snapshot_dir(CFG.snapshot)
SH_PBF = P.pbf("shanghai", CFG.snapshot)
JS_PBF = P.pbf("jiangsu", CFG.snapshot)
OUT = P.basemap_geojson

SHANGHAI_L4 = CFG.city_admin_id
SHANGHAI_DISTRICTS = {
    1673543: "嘉定区", 3292751: "奉贤区", 3292750: "崇明区", 1278188: "徐汇区",
    398886: "普陀区", 398350: "杨浦区", 3293722: "松江区", 398348: "浦东新区",
    398351: "虹口区", 3292756: "金山区", 398899: "长宁区", 1278189: "闵行区",
    3292760: "青浦区", 398353: "静安区", 371650: "黄浦区", 398374: "宝山区",
}
WATER_RELS = {1122227: ("淀山湖", "lake", 0.05)}  # 关系 id -> (名, 类型, 最小部件 km²)
CENTERLINE_RELS = {9392345: "长江", 9064903: "吴淞江"}  # waterway 关系，取成员 way 拼中心线
SCENE_BBOX = CFG.scene_bbox_tuple
SIMPLIFY_M = 25.0      # 面要素简化容差（米）
LINE_SIMPLIFY_M = 8.0  # 线要素容差更小，避免窄河道出现锯齿

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)


def log(msg: str) -> None:
    print(msg, flush=True)


class RelationScan(osmium.SimpleHandler):
    def __init__(self, boundaries: bool) -> None:
        super().__init__()
        self.boundaries = boundaries
        self.ways: dict[int, set[int]] = {}

    def relation(self, r) -> None:
        if r.id in WATER_RELS or r.id in CENTERLINE_RELS:
            self.ways[r.id] = {m.ref for m in r.members if m.type == "w"}
            return
        if not self.boundaries:
            return
        if r.id != SHANGHAI_L4 and r.id not in SHANGHAI_DISTRICTS:
            return
        self.ways[r.id] = {m.ref for m in r.members if m.type == "w"}


class WayScan(osmium.SimpleHandler):
    def __init__(self, want: set[int], match_tags: bool) -> None:
        super().__init__()
        self.want = want
        self.match_tags = match_tags
        self.geom: dict[int, list[tuple[float, float]]] = {}
        self.wusong: list[list[tuple[float, float]]] = []
        self.coast: list[list[tuple[float, float]]] = []
        self.huangpu_line: list[list[tuple[float, float]]] = []

    def way(self, w) -> None:
        need = w.id in self.want
        if not need and not self.match_tags:
            return
        tags = {t.k: t.v for t in w.tags}
        name = tags.get("name") or ""
        want_coast = self.match_tags and tags.get("natural") == "coastline"
        want_hp = self.match_tags and tags.get("waterway") == "river" and name == "黄浦江"
        if not (need or want_coast or want_hp):
            return
        coords = [(n.lon, n.lat) for n in w.nodes]  # locations=True 时须就地取用
        if len(coords) < 2:
            return
        if need:
            self.geom[w.id] = coords
        if want_coast:
            self.coast.append(coords)
        if want_hp:
            self.huangpu_line.append(coords)


def assemble(way_ids: set[int], geoms: list[dict[int, list]], label: str, min_part_km2: float = 0.0):
    lines = []
    missing = 0
    for wid in way_ids:
        cs = None
        for g in geoms:
            cs = g.get(wid)
            if cs:
                break
        if cs:
            lines.append(LineString(cs))
        else:
            missing += 1
    info = {"ways": len(way_ids), "missing": missing}
    if not lines:
        info["error"] = "无可用线"
        return None, info
    polys = list(polygonize(lines))
    if not polys:
        info["error"] = "polygonize 无法闭合"
        return None, info
    parts = [shapely.make_valid(p) for p in polys if not p.is_empty]
    merged = unary_union(parts)
    if merged.is_empty:
        info["error"] = "并集为空"
        return None, info
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    if min_part_km2 > 0:
        keep = [g for g in merged.geoms if area_km2(g) >= min_part_km2]
        merged = MultiPolygon(keep) if keep else merged
    info.update({"polygonized": len(polys), "kept_parts": len(merged.geoms), "valid": bool(merged.is_valid)})
    log(f"   [{label}] {info}")
    return merged, info


def project(geom):
    return shapely.transform(geom, lambda c: np.stack(TO_UTM.transform(c[..., 0], c[..., 1]), axis=-1))


def unproject(geom):
    return shapely.transform(geom, lambda c: np.stack(TO_WGS.transform(c[..., 0], c[..., 1]), axis=-1))


def area_km2(geom) -> float:
    return project(geom).area / 1e6


def length_km(geom) -> float:
    return project(geom).length / 1000.0


def simp(geom, tol_m: float = SIMPLIFY_M):
    return unproject(project(geom).simplify(tol_m, preserve_topology=True))


def feature(geom, layer: str, name: str, extra: dict | None = None, simplify_m: float = SIMPLIFY_M) -> dict:
    props = {
        "layer": layer,
        "name": name,
        "source": "OpenStreetMap，download.openstreetmap.fr 省级 extract（shanghai/jiangsu）",
        "source_license": "ODbL-1.0",
        "as_of": "2026-11-01",
        "simplify_m": simplify_m,
    }
    if extra:
        props.update(extra)
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


def main() -> int:
    t0 = time.time()
    for p in (SH_PBF, JS_PBF):
        if not p.exists():
            log(f"[FATAL] 缺快照文件 {p}")
            return 1
    scene = box(*SCENE_BBOX)

    log("== pass 1：shanghai 扫关系 ==")
    rsh = RelationScan(boundaries=True)
    rsh.apply_file(str(SH_PBF), locations=False)
    others = sorted(k for k in rsh.ways if k not in SHANGHAI_DISTRICTS and k != SHANGHAI_L4)
    log(f"   省界 {'命中' if SHANGHAI_L4 in rsh.ways else '缺失'}；区界 {len(set(SHANGHAI_DISTRICTS) & set(rsh.ways))}/16；水系/中心线关系 {others}")

    log("== pass 1b：jiangsu 扫水系关系 ==")
    rjs = RelationScan(boundaries=False)
    rjs.apply_file(str(JS_PBF), locations=False)
    log(f"   水系/中心线关系 {sorted(rjs.ways)}")

    extra_ways: dict[int, set[int]] = {}
    for src in (rsh.ways, rjs.ways):
        for rid, ways in src.items():
            if rid in WATER_RELS or rid in CENTERLINE_RELS:
                extra_ways.setdefault(rid, set()).update(ways)

    want: set[int] = set()
    for rid, ways in rsh.ways.items():
        want |= ways
    for ways in extra_ways.values():
        want |= ways

    log("== pass 2：shanghai 取 way 几何 ==")
    wsh = WayScan(want, match_tags=True)
    wsh.apply_file(str(SH_PBF), locations=True)
    log(f"   需要 {len(want)}，取到 {len(wsh.geom)}；吴淞江 {len(wsh.wusong)}；黄浦江 {len(wsh.huangpu_line)}；海岸线 {len(wsh.coast)}")

    log("== pass 3：jiangsu 补齐跨省要素 ==")
    all_extra = set().union(*extra_ways.values()) if extra_ways else set()
    wjs = WayScan(all_extra, match_tags=False)
    wjs.apply_file(str(JS_PBF), locations=True)
    log(f"   取到 {len(wjs.geom)}")
    geoms = [wsh.geom, wjs.geom]

    feats: list[dict] = []

    # --- 区界（D3：入库存线，不渲染）
    dis_ok = 0
    for rid, dname in SHANGHAI_DISTRICTS.items():
        lines = [LineString(wsh.geom[w]) for w in rsh.ways.get(rid, set()) if w in wsh.geom]
        if not lines:
            log(f"   [区界缺失] {dname}")
            continue
        ring = unary_union([shapely.make_valid(x) for x in lines])
        dis_ok += 1
        feats.append(feature(simp(ring), "district_boundary", dname,
                             {"source_id": f"relation/{rid}", "length_km": round(length_km(ring), 1)}))
    log(f"[区界] {dis_ok}/16")

    # --- 省界轮廓（含海域边界）
    l4 = [LineString(wsh.geom[w]) for w in rsh.ways.get(SHANGHAI_L4, set()) if w in wsh.geom]
    if l4:
        province = unary_union([shapely.make_valid(x) for x in l4])
        feats.append(feature(simp(province, LINE_SIMPLIFY_M), "province_boundary", "上海市",
                             {"source_id": f"relation/{SHANGHAI_L4}", "length_km": round(length_km(province), 1),
                              "note": "含海域边界；该关系多边形并集 16,204.7 km²，不是陆地面积"},
                             simplify_m=LINE_SIMPLIFY_M))
        log(f"[省界] {len(l4)} 段，{length_km(province):,.1f} km")

    # --- 水面多边形
    for rid, (wname, kind, minp) in WATER_RELS.items():
        poly, info = assemble(extra_ways.get(rid, set()), geoms, wname, min_part_km2=minp)
        if poly is None:
            log(f"   [跳过] {wname}：{info.get('error')}")
            continue
        if not poly.intersects(scene):
            log(f"   [跳过] {wname}：不在上海视野内（bounds {[round(v, 3) for v in poly.bounds]}）")
            continue
        feats.append(feature(simp(poly), "water", wname,
                             {"kind": kind, "source_id": f"relation/{rid}",
                              "area_km2": round(area_km2(poly), 2), "kept_parts": len(poly.geoms)}))

    # --- 跨省中心线（长江口）
    for rid, cname in CENTERLINE_RELS.items():
        parts = [LineString(geoms[0][w]) for w in extra_ways.get(rid, set()) if w in geoms[0]]
        parts += [LineString(geoms[1][w]) for w in extra_ways.get(rid, set()) if w in geoms[1]]
        if not parts:
            log(f"   [跳过] {cname}：无几何")
            continue
        merged = unary_union([shapely.make_valid(p) for p in parts]).intersection(scene)
        if merged.is_empty:
            log(f"   [跳过] {cname}：裁剪后为空")
            continue
        extra = {"kind": "river_centerline", "source_id": f"relation/{rid}",
                 "parts": len(parts), "length_km": round(length_km(merged), 1)}
        if cname == "长江":
            extra["note"] = "只取上海视野内的江口段"
        elif cname == "吴淞江":
            extra["alias"] = "苏州河"
            extra["note"] = "OSM 中苏州河的正式名称为吴淞江；主干在 waterway 关系 9064903"
        feats.append(feature(simp(merged, LINE_SIMPLIFY_M), "water_line", cname, extra, LINE_SIMPLIFY_M))
        log(f"[{cname}] {len(parts)} 段，视野内 {length_km(merged):.1f} km")

    # --- 河道中心线
    if wsh.huangpu_line:
        merged = unary_union([LineString(c) for c in wsh.huangpu_line])
        feats.append(feature(simp(merged, LINE_SIMPLIFY_M), "water_line", "黄浦江",
                             {"kind": "river_centerline", "parts": len(wsh.huangpu_line),
                              "length_km": round(length_km(merged), 1), "note": "水面按样式加粗，不伪造江面多边形"},
                             simplify_m=LINE_SIMPLIFY_M))
        log(f"[黄浦江] {len(wsh.huangpu_line)} 段，{length_km(merged):.1f} km")

    # --- 海岸线
    if wsh.coast:
        merged = unary_union([shapely.make_valid(LineString(c)) for c in wsh.coast])
        feats.append(feature(simp(merged, LINE_SIMPLIFY_M), "coastline", "海岸线",
                             {"kind": "coastline", "parts": len(wsh.coast), "length_km": round(length_km(merged), 1)},
                             simplify_m=LINE_SIMPLIFY_M))
        log(f"[海岸线] {len(wsh.coast)} 段，{length_km(merged):,.1f} km")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "name": "shanghai-basemap", "features": feats}
    OUT.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size
    log(f"\n== 写出 {OUT} ==")
    log(f"   features {len(feats)}，{size:,} B（{size / 1024 / 1024:.2f} MB），判据 <5 MB：{'通过' if size < 5 * 1024 * 1024 else '超限'}")
    by_layer: dict[str, int] = {}
    for f in feats:
        by_layer[f["properties"]["layer"]] = by_layer.get(f["properties"]["layer"], 0) + 1
    log(f"   分层 {by_layer}")
    log(f"   总耗时 {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
