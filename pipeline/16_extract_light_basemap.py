"""P1a-6.4 轻底图：给非上海城市抽一份「市界 + 邻市界 + 主要河道 + 大水面」的底图。

为什么另写一份，而不是把 03 改成通用：
  03 是为上海 P0 精修过的（16 个区界 id、淀山湖/长江口/黄浦江/吴淞江逐个点名、
  海面单独一份），其中的关系 id 都是上海专属。硬塞进循环只会把 03 变成一堆 if。

轻底图的目标是最小可用的「地理参照」，不是完整地图：
  - `province_boundary`：本市中心城区所属的市界（用 city_admin_id 那条关系，视觉重量同省界）
  - `district_boundary`：视野内其它地级市界（提供周边参照，浅一档）
  - `water_line`：主要河道中心线（waterway=river/canal，按长度截取）
  - `water`：面积 ≥ 1 km² 的湖库/polygon 型水面
  - `coastline`：视野内海岸线（只有靠海的广州需要）

产物：`data/processed/<slug>/basemap.geojson`（与 web/scripts/city.mjs 的约定一致）。
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
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import polygonize, unary_union

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "gz")
CFG = load_city(CITY_CODE)
P = Paths(CFG)

SCENE_BBOX = CFG.scene_bbox_tuple
PAD = 0.06  # 视野外扩一点，避免边界处要素被硬切
SCENE = box(SCENE_BBOX[0] - PAD, SCENE_BBOX[1] - PAD, SCENE_BBOX[2] + PAD, SCENE_BBOX[3] + PAD)

OUT = P.city_dir / "basemap.geojson"

POLY_SIMPLIFY_M = 90.0
LINE_SIMPLIFY_M = 40.0
MIN_WATER_KM2 = 3.0
MAX_WATER = 20
MIN_RIVER_KM = 12.0
MAX_RIVERS = 24
MAX_NEIGHBOURS = 10
MIN_COAST_KM = 5.0
MAX_COAST = 20
BOUNDARY_SIMPLIFY_M = 150.0  # 边界只当参照：z9 时 1 px ≈ 150 m，更细的顶点纯浪费
COORD_DECIMALS = 5  # ≈1 m，再细前端也画不出来，纯占字节

# 中国境内 UTM 51N 覆盖 120–126E；广州/成都/合肥都落在 48–51N 区间，按经度取带
UTM_ZONE = int(((SCENE_BBOX[0] + SCENE_BBOX[2]) / 2 + 180) // 6) + 1
TO_UTM = Transformer.from_crs("EPSG:4326", f"EPSG:326{UTM_ZONE:02d}", always_xy=True)
TO_WGS = Transformer.from_crs(f"EPSG:326{UTM_ZONE:02d}", "EPSG:4326", always_xy=True)


def log(msg: str) -> None:
    print(msg, flush=True)


def project(geom):
    return shapely.transform(geom, lambda c: np.stack(TO_UTM.transform(c[..., 0], c[..., 1]), axis=-1))


def unproject(geom):
    return shapely.transform(geom, lambda c: np.stack(TO_WGS.transform(c[..., 0], c[..., 1]), axis=-1))


def area_km2(geom) -> float:
    return project(geom).area / 1e6


def length_km(geom) -> float:
    return project(geom).length / 1000.0


def simp(geom, tol_m: float):
    g = unproject(project(geom).simplify(tol_m, preserve_topology=True))
    # 坐标量化到 1e-5°（≈1 m）：轻底图不需要更细，省下的是实打实的字节
    return shapely.transform(g, lambda c: np.round(c, COORD_DECIMALS))


def as_of() -> str:
    import re

    m = re.search(r"(\d{8})$", CFG.snapshot or "")
    if not m:
        return CFG.snapshot or ""
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


AS_OF = as_of()
SOURCES = "OpenStreetMap，download.openstreetmap.fr 省级 extract（" + "/".join(CFG.pbfs) + "）"


def feature(geom, layer: str, name: str, simplify_m: float, extra: dict | None = None) -> dict:
    props = {
        "layer": layer,
        "name": name,
        "source": SOURCES,
        "source_license": "ODbL-1.0",
        "as_of": AS_OF,
        "simplify_m": simplify_m,
    }
    if extra:
        props.update(extra)
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


class RelationScan(osmium.SimpleHandler):
    """收三类关系：本省市界、其它地级市界、水面（natural=water multipolygon）。"""

    def __init__(self) -> None:
        super().__init__()
        self.city: dict[int, set[int]] = {}
        self.neighbours: dict[int, tuple[set[int], str]] = {}
        self.water: dict[int, tuple[set[int], str]] = {}

    def relation(self, r) -> None:
        tags = {t.k: t.v for t in r.tags}
        ways = {m.ref for m in r.members if m.type == "w" and (m.role in ("outer", "", None))}
        if not ways:
            return
        if r.id == CFG.city_admin_id:
            self.city[r.id] = ways
            return
        level = tags.get("admin_level")
        if level in ("5", "6") and tags.get("boundary") == "administrative":
            self.neighbours[r.id] = (ways, tags.get("name") or tags.get("name:zh") or f"relation/{r.id}")
            return
        if tags.get("natural") == "water" and tags.get("type") == "multipolygon" and len(ways) <= 400:
            self.water[r.id] = (ways, tags.get("name") or tags.get("name:zh") or "水面")


class WayScan(osmium.SimpleHandler):
    """取需要的 way 几何：关系成员 + 按标签匹配的河道/海岸线/闭合水面。"""

    def __init__(self, want: set[int]) -> None:
        super().__init__()
        self.want = want
        self.geom: dict[int, list[tuple[float, float]]] = {}
        self.rivers: list[tuple[list[tuple[float, float]], str, str]] = []
        self.coast: list[list[tuple[float, float]]] = []
        self.lakes: list[tuple[list[tuple[float, float]], str]] = []
        self.broken = 0

    def way(self, w) -> None:
        need = w.id in self.want
        tags = {t.k: t.v for t in w.tags} if (need or not need) else {}
        ww = tags.get("waterway")
        natural = tags.get("natural")
        want_river = ww in ("river", "canal")
        want_coast = natural == "coastline"
        want_lake = natural == "water" and tags.get("water") != "river"
        if not (need or want_river or want_coast or want_lake):
            return
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            # 省级 extract 在边界处会缺节点坐标；这条 way 只能放弃。
            # （关系型要素由成员并集与 polygonize 兜住，缺一两条不影响闭合判定。）
            self.broken += 1
            return
        if len(coords) < 2:
            return
        if need:
            self.geom[w.id] = coords
        name = tags.get("name") or tags.get("name:zh") or ""
        if want_river and len(coords) >= 2:
            self.rivers.append((coords, name, ww))
        elif want_coast:
            self.coast.append(coords)
        elif want_lake and len(coords) >= 4 and coords[0] == coords[-1]:
            self.lakes.append((coords, name))


def assemble(ways: set[int], geoms: list[dict[int, list]], label: str):
    lines = []
    for wid in ways:
        for g in geoms:
            cs = g.get(wid)
            if cs:
                lines.append(LineString(cs))
                break
    if not lines:
        return None
    polys = [shapely.make_valid(p) for p in polygonize(lines) if not p.is_empty]
    if not polys:
        return None
    merged = unary_union(polys)
    if merged.is_empty:
        return None
    if isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    return merged


def main() -> int:
    t0 = time.time()
    pbfs = P.pbfs(CFG.snapshot)
    for p in pbfs:
        if not p.exists():
            log(f"[FATAL] 缺快照文件 {p}")
            return 1
    log(f"== {CFG.code} {CFG.name}｜视野 {SCENE_BBOX}｜UTM {UTM_ZONE}N ==")

    rel = RelationScan()
    for p in pbfs:
        rel.apply_file(str(p), locations=False)
    log(
        f"== 关系：本省市界 {'有' if rel.city else '缺'}；邻市 {len(rel.neighbours)}；水面 {len(rel.water)} =="
    )

    want: set[int] = set()
    for ways in rel.city.values():
        want |= ways
    for ways, _ in rel.neighbours.values():
        want |= ways
    for ways, _ in rel.water.values():
        want |= ways
    log(f"== 需要 way {len(want)} 条，开始扫几何 ==")

    ws = WayScan(want)
    for p in pbfs:
        ws.apply_file(str(p), locations=True)
    geoms = [ws.geom]
    log(
        f"== 取到关系成员 {len(ws.geom)}/{len(want)}；河道候选 {len(ws.rivers)}；"
        f"海岸线 {len(ws.coast)}；闭合水面 {len(ws.lakes)}；坐标缺失跳过 {ws.broken} =="
    )

    feats: list[dict] = []

    # 1) 本省市界：用市界关系拼出的面 → 取外环线，并按视野裁剪
    city_parts = []
    for rid, ways in rel.city.items():
        merged = assemble(ways, geoms, f"市界 {rid}")
        if merged is None:
            log(f"   [市界] {rid} 无法闭合，跳过")
            continue
        clipped = merged.intersection(SCENE)
        if clipped.is_empty:
            continue
        city_parts.append(clipped)
        rings = clipped.boundary
        if not rings.is_empty:
            feats.append(feature(simp(rings, BOUNDARY_SIMPLIFY_M), "province_boundary", CFG.name, BOUNDARY_SIMPLIFY_M))
    log(f"   [市界] 保留 {len(city_parts)} 个面")

    # 2) 邻市界：只保留与视野相交的大块，浅一档
    nb = []
    for rid, (ways, name) in rel.neighbours.items():
        merged = assemble(ways, geoms, f"邻市 {rid}")
        if merged is None:
            continue
        clipped = merged.intersection(SCENE)
        if clipped.is_empty:
            continue
        km2 = area_km2(clipped)
        if km2 < 20:
            continue
        nb.append((km2, name, clipped))
    nb.sort(key=lambda x: -x[0])
    for km2, name, geom in nb[:MAX_NEIGHBOURS]:
        feats.append(
            feature(
                simp(geom.boundary, BOUNDARY_SIMPLIFY_M),
                "district_boundary",
                name,
                BOUNDARY_SIMPLIFY_M,
                {"area_km2": round(km2, 1)},
            )
        )
    log(f"   [邻市界] 候选 {len(nb)}，保留 {min(len(nb), MAX_NEIGHBOURS)}")

    # 3) 河道中心线：只留够长的，按长度排序截取
    rivers = []
    for coords, name, kind in ws.rivers:
        line = LineString(coords)
        if not line.intersects(SCENE):
            continue
        clipped = line.intersection(SCENE)
        if clipped.is_empty or clipped.geom_type not in ("LineString", "MultiLineString"):
            continue
        km = length_km(clipped)
        if km < MIN_RIVER_KM:
            continue
        rivers.append((km, name or ("河道" if kind == "river" else "运河"), clipped))
    rivers.sort(key=lambda r: -r[0])
    for km, name, geom in rivers[:MAX_RIVERS]:
        feats.append(
            feature(
                simp(geom, LINE_SIMPLIFY_M),
                "water_line",
                name,
                LINE_SIMPLIFY_M,
                {"length_km": round(km, 2)},
            )
        )
    log(f"   [河道] 候选 {len(rivers)}，保留 {min(len(rivers), MAX_RIVERS)}")

    # 4) 水面：关系型 + 闭合 way 型，合并后按面积过滤，只留最大的若干块
    water_parts = []
    for rid, (ways, name) in rel.water.items():
        merged = assemble(ways, geoms, f"水面 {rid}")
        if merged is None:
            continue
        clipped = merged.intersection(SCENE)
        if clipped.is_empty:
            continue
        km2 = area_km2(clipped)
        if km2 < MIN_WATER_KM2:
            continue
        water_parts.append((km2, name, clipped))
    for coords, name in ws.lakes:
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = shapely.make_valid(poly)
        clipped = poly.intersection(SCENE)
        if clipped.is_empty:
            continue
        km2 = area_km2(clipped)
        if km2 < MIN_WATER_KM2:
            continue
        water_parts.append((km2, name or "水面", clipped))
    water_parts.sort(key=lambda x: -x[0])
    for km2, name, geom in water_parts[:MAX_WATER]:
        feats.append(
            feature(
                simp(geom, POLY_SIMPLIFY_M),
                "water",
                name,
                POLY_SIMPLIFY_M,
                {"area_km2": round(km2, 2)},
            )
        )
    log(f"   [水面] 候选 {len(water_parts)}，保留 {min(len(water_parts), MAX_WATER)}（≥{MIN_WATER_KM2} km²）")

    # 5) 海岸线：拼成多段线，只留与视野相交且够长的（珠江口碎段极多，逐条保留会爆体积）
    coast_parts = []
    for coords in ws.coast:
        line = LineString(coords)
        if not line.intersects(SCENE):
            continue
        clipped = line.intersection(SCENE)
        if clipped.is_empty:
            continue
        for part in getattr(clipped, "geoms", [clipped]):
            if part.geom_type != "LineString" or part.length == 0:
                continue
            km = length_km(part)
            if km < MIN_COAST_KM:
                continue
            coast_parts.append((km, part))
    coast_parts.sort(key=lambda x: -x[0])
    for km, part in coast_parts[:MAX_COAST]:
        feats.append(
            feature(simp(part, LINE_SIMPLIFY_M), "coastline", "海岸线", LINE_SIMPLIFY_M, {"length_km": round(km, 1)})
        )
    log(f"   [海岸线] 候选 {len(coast_parts)}，保留 {min(len(coast_parts), MAX_COAST)}（≥{MIN_COAST_KM} km）")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "features": feats}
    OUT.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size
    layers: dict[str, int] = {}
    for f in feats:
        layers[f["properties"]["layer"]] = layers.get(f["properties"]["layer"], 0) + 1
    log(f"== 写出 {OUT.relative_to(REPO)}：{len(feats)} 要素 / {size:,} B / {layers} / {time.time() - t0:.1f}s ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
