# -*- coding: utf-8 -*-
"""S2-4 区间切分：把每条 branch 的轨道几何按车站节点切开，产出 segment.geojson

做法：
1. 取 branch 的代表关系（relation_ids.kept），用它全部成员 way 的节点序列拼成一张无向图
   （节点 = OSM 节点 id，边权 = 两点大圆距离）。这样不必关心 way 的先后与方向。
2. 对相邻两个车站节点求最短路，最短路经过的节点序列就是该区间的轨道几何。
   车站节点都在 way 节点集合里（S2-4 探查：2/10/4 号线 0 缺失），所以逐段都走得通；
   若某段不通，该段记为 gap 并在报告里列出，不伪造几何。
3. 环线（ADR R3）：末段从最后一座站回到 loop_start，所以区间数 = 站数。

用法：
    python pipeline/10_build_segments.py                # 全部 23 条 branch
    python pipeline/10_build_segments.py --only sh-line-2-main sh-line-4-main
"""
from __future__ import annotations

import argparse
import heapq
import json
import sys
import os
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
RAW = P.raw_transit()
LINES = P.lines_json
STATIONS = P.station_json
OUT = P.segment_geojson

R_EARTH = 6371008.8
SOURCE = "OpenStreetMap（省级 PBF）"
LICENSE = "ODbL-1.0"

# 官方里程（公里），只用于报告里的量级对照，不进产物
OFFICIAL_KM = {
    "sh-line-2-main": 64.0,
    "sh-line-4-main": 33.6,
    "sh-line-10-main": 40.6,

}


def hav_m(a, b) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def build_graph(rel):
    """返回 (adj, coord)：节点邻接表与坐标表"""
    adj = defaultdict(list)
    coord = {}
    for w in rel["ways"]:
        nodes = w["nodes"]
        geom = w["geometry"]
        if not nodes:
            continue
        for nid, c in zip(nodes, geom):
            coord.setdefault(nid, c)
        for u, v in zip(nodes, nodes[1:]):
            if u == v:
                continue
            d = hav_m(coord[u], coord[v])
            adj[u].append((v, d))
            adj[v].append((u, d))
    return adj, coord


def shortest_path(adj, start, goal):
    """Dijkstra，返回节点序列；不可达返回 None"""
    dist = {start: 0.0}
    prev = {}
    pq = [(0.0, start)]
    seen = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        if u == goal:
            path = [u]
            while path[-1] != start:
                path.append(prev[path[-1]])
            return path[::-1]
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="只处理这些 branch id")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    raw = {str(r["id"]): r for r in json.loads(RAW.read_text(encoding="utf-8"))["relations"]}
    lines = json.loads(LINES.read_text(encoding="utf-8"))
    st = json.loads(STATIONS.read_text(encoding="utf-8"))

    # 站名 + branch → 节点 id / 站点 id
    node_of: dict[tuple[str, str], int] = {}
    id_of: dict[tuple[str, str], str] = {}
    coord_of_node: dict[int, list[float]] = {}
    for s in st["stations"]:
        for sl in s["slots"]:
            node_of[(s["name"], sl["branch"])] = sl["node"]
            id_of[(s["name"], sl["branch"])] = s["id"]
            coord_of_node[sl["node"]] = sl["coord"]

    feats = []
    report = []
    gaps = []
    total_km = 0.0

    for ln in lines["lines"]:
        for br in ln["branches"]:
            bid = br["id"]
            if args.only and bid not in args.only:
                continue
            rid = str(br["relation_ids"]["kept"])
            rel = raw[rid]
            adj, coord = build_graph(rel)

            names = list(br["stops"])
            loop = bool(br["is_loop"])
            nodes = []
            for nm in names:
                key = (nm, bid)
                if key not in node_of:
                    raise SystemExit(f"[错误] {bid} 的站「{nm}」没有对应节点")
                nodes.append(node_of[key])
            if loop:
                nodes_chain = nodes + [nodes[0]]
            else:
                nodes_chain = nodes

            br_km = 0.0
            br_seg = 0
            for seq in range(len(nodes_chain) - 1):
                u, v = nodes_chain[seq], nodes_chain[seq + 1]
                path = shortest_path(adj, u, v)
                if path is None:
                    gaps.append({"branch": bid, "seq": seq + 1, "from": names[seq],
                                 "to": names[(seq + 1) % len(names)], "reason": "最短路不通"})
                    continue
                pts = [coord[n] for n in path]
                length = sum(hav_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
                br_km += length
                br_seg += 1
                feats.append({
                    "type": "Feature",
                    "properties": {
                        "id": f"{bid}-{seq + 1:03d}",
                        "line_id": ln["id"],
                        "branch_id": bid,
                        "seq": seq + 1,
                        # ADR R2：实体之间用稳定 id 引用，人名不参与连接（站名另有字段）
                        "from_station": id_of[(names[seq], bid)],
                        "to_station": id_of[(names[(seq + 1) % len(names)], bid)],
                        "from_name": names[seq],
                        "to_name": names[(seq + 1) % len(names)],
                        "length_m": round(length, 1),
                        "node_count": len(path),
                        "is_loop_close": bool(loop and seq == len(nodes) - 1),
                        "source": SOURCE,
                        "source_license": LICENSE,
                        "as_of": st["snapshot_date"],
                    },
                    "geometry": {"type": "LineString", "coordinates": [[round(x, 7), round(y, 7)] for x, y in pts]},
                })
            total_km += br_km / 1000.0
            report.append({
                "branch": bid, "relation": rid, "stations": len(names), "loop": loop,
                "segments": br_seg, "km": round(br_km / 1000, 2),
                "official_km": OFFICIAL_KM.get(bid), "ways": len(rel["ways"]),
            })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "type": "FeatureCollection",
        "name": "shanghai-segments",
        "snapshot_date": st["snapshot_date"],
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rules": "ADR R2（segment id = <branch_id>-<三位序号>）、R3（环线末段回到 loop_start）",
        "counts": {"segments": len(feats), "branches": len(report), "km": round(total_km, 2)},
        "features": feats,
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'branch':22s} {'rel':10s} {'站':>3s} {'段':>3s} {'实测km':>8s} {'官方km':>7s} {'way':>4s}")
    for r in report:
        off = f"{r['official_km']:.1f}" if r["official_km"] else "-"
        print(f"{r['branch']:22s} {r['relation']:10s} {r['stations']:3d} {r['segments']:3d} "
              f"{r['km']:8.2f} {off:>7s} {r['ways']:4d}")
    print(f"\n总计 段 {len(feats)}｜km {total_km:.2f}｜写出 {out}（{out.stat().st_size:,} B）")
    if gaps:
        print(f"[警告] 有 {len(gaps)} 段不通：")
        for g in gaps:
            print("   ", g)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
