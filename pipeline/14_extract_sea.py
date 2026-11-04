"""S4-4：从省级 PBF 里拼出「海面」，供底图填色用。

为什么单独一个脚本：S1-4 的 03_extract_basemap.py 只读上海 + 江苏两份，
而海面必须用五省的 coastline 才能闭合（S4-0 探测结论）。

做法：
1. 五份 PBF 各扫一遍，收集 natural=coastline 的 way 几何
2. 用视野 bbox 裁掉省界外的部分
3. 海岸线 + bbox 边框一起 polygonize，得到被切开的若干「面」
4. 含测试海点的面就是海面；岛屿是独立的面，天然不算在海里

产物：data/processed/basemap/shanghai-sea.geojson（只含 1 个面）
"""

from __future__ import annotations

import json
import sys
import os
import time
from pathlib import Path

import osmium
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import polygonize, unary_union
from shapely import transform as shp_transform

REPO = Path(r"E:\subway")
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
SNAP = P.snapshot_dir(CFG.snapshot)
OUT = P.sea_geojson

PROVINCES = list(CFG.pbfs)
SCENE_BBOX = CFG.scene_bbox_tuple  # lon_min, lat_min, lon_max, lat_max
SIMPLIFY_M = 60.0
AS_OF = "20261101"

# 判定「哪一面是海」的测试点。
# 只用毫无歧义的外海点：长江口北支水域在 OSM 里由河岸而非 coastline 围成，
# 加测试点会让整块陆地被误判成海（S4-4 实测）。
SEA_TEST_POINTS = [
    (122.30, 31.40),  # 长江口外
    (122.90, 31.20),  # 东海外海
    (122.10, 30.75),  # 杭州湾口
]


class CoastScan(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[LineString] = []

    def way(self, w: osmium.osm.Way) -> None:  # noqa: D401
        if w.tags.get("natural") != "coastline":
            return
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(coords) >= 2:
            self.lines.append(LineString(coords))


def to_metric(geom):
    tf = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    return shp_transform(geom, lambda c: np.stack(tf.transform(c[..., 0], c[..., 1]), axis=-1))


def from_metric(geom):
    tf = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)
    return shp_transform(geom, lambda c: np.stack(tf.transform(c[..., 0], c[..., 1]), axis=-1))


def main() -> None:
    t0 = time.time()
    scene = box(*SCENE_BBOX)

    all_lines: list[LineString] = []
    for prov in PROVINCES:
        pbf = SNAP / f"{prov}-latest.osm.pbf"
        if not pbf.exists():
            raise SystemExit(f"缺少快照文件：{pbf}")
        scan = CoastScan()
        scan.apply_file(str(pbf), locations=True)
        kept = 0
        for ln in scan.lines:
            if scene.intersects(ln):
                clipped = ln.intersection(scene)
                if not clipped.is_empty:
                    all_lines.append(clipped)
                    kept += 1
        print(f"  {prov}: coastline way {len(scan.lines)} 条，视野内 {kept} 条")

    if not all_lines:
        raise SystemExit("没有取到任何海岸线，检查快照与 bbox")

    merged = unary_union(all_lines)
    # bbox 边框参与 polygonize，海面才能被切出来
    ring = Polygon(
        [
            (SCENE_BBOX[0], SCENE_BBOX[1]),
            (SCENE_BBOX[2], SCENE_BBOX[1]),
            (SCENE_BBOX[2], SCENE_BBOX[3]),
            (SCENE_BBOX[0], SCENE_BBOX[3]),
        ]
    ).exterior
    faces = list(polygonize(unary_union([merged, ring])))
    print(f"  polygonize 得到 {len(faces)} 个面")

    def in_sea(geom) -> bool:
        return any(geom.contains(box(p[0] - 1e-6, p[1] - 1e-6, p[0] + 1e-6, p[1] + 1e-6)) for p in SEA_TEST_POINTS)

    # polygonize 出来的面把 bbox 内部铺满，且互不重叠：海 = bbox - 全部陆地
    land_faces = [f for f in faces if not in_sea(f)]
    sea_faces = [f for f in faces if in_sea(f)]
    print(f"  海面相关面 {len(sea_faces)} 个，陆地相关面 {len(land_faces)} 个")
    if not sea_faces:
        raise SystemExit("没有面命中测试海点，海岸线可能没闭合")

    sea = scene.difference(unary_union(land_faces))
    area_km2 = to_metric(sea).area / 1e6
    print(f"  bbox 减陆地后：面积 {area_km2:,.1f} km²")

    sea_m = to_metric(sea)
    area_km2 = sea_m.area / 1e6

    # 扔掉面积过小的洞（海岸线碎段造成的针孔），保留真正的岛
    teardrops = 0
    polys = []
    for poly in (sea_m.geoms if sea_m.geom_type == "MultiPolygon" else [sea_m]):
        keep = [r for r in poly.interiors if Polygon(r).area >= 50_000]
        teardrops += len(poly.interiors) - len(keep)
        polys.append(Polygon(poly.exterior, keep))
    sea_m = unary_union(polys)
    print(f"  清掉 {teardrops} 个 <0.05 km² 的针孔洞")

    simplified = from_metric(sea_m.simplify(SIMPLIFY_M, preserve_topology=True))

    def count_vertices(g) -> int:
        if g.geom_type == "Polygon":
            return len(g.exterior.coords) + sum(len(r.coords) for r in g.interiors)
        return sum(count_vertices(p) for p in g.geoms)

    feature = {
        "type": "Feature",
        "geometry": mapping(simplified),
        "properties": {
            "layer": "sea",
            "name": "海面",
            "area_km2": round(area_km2, 2),
            "simplify_m": SIMPLIFY_M,
            "source": "OpenStreetMap（省级 PBF，coastline）",
            "source_license": "ODbL-1.0",
            "as_of": AS_OF,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": [feature]}, ensure_ascii=False),
        encoding="utf-8",
    )

    size = OUT.stat().st_size
    print(f"  顶点 {count_vertices(simplified):,} 个；写出 {OUT}")
    print(f"  {size:,} B（{size / 1024 / 1024:.2f} MB），耗时 {time.time() - t0:.1f} s")
    if size > 3 * 1024 * 1024:
        print("  [警告] 海面文件超过 3 MB，考虑提高简化容差")


if __name__ == "__main__":
    main()
