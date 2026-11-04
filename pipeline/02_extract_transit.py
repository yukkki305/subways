#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S1-3 轨道关系抽取。

职责：从省级 PBF 里抽出全部城市轨道交通关系（route=subway|monorail|light_rail|tram），
连同成员顺序、stop 节点（含坐标与标签）、way 几何，落成一份 JSON 供 S2 建模使用。

不做：不产 line/station/segment，不做同名站合并，不定颜色。

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\02_extract_transit.py
    ... 02_extract_transit.py --provinces shanghai
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import osmium

ROUTE_KINDS = ("subway", "monorail", "light_rail", "tram")
# 只统计不产出（AGENTS 第 2 节：市域/城际不进 v1 主线）
STATS_ONLY_KINDS = ("train", "tram_stop")
REPO = Path(r"E:\subway")
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
SNAP = P.snapshot_dir(CFG.snapshot)
OUT_DEFAULT = REPO / "data" / "raw" / "transit-relations.json"

# 站名优先级：name:zh > name > name:en
NAME_KEYS = ("name:zh", "name", "name:en")


def tags_of(obj) -> dict[str, str]:
    return {t.k: t.v for t in obj.tags}


def pick_name(tags: dict[str, str]) -> str | None:
    for key in NAME_KEYS:
        if tags.get(key):
            return tags[key]
    return None


class RelationPass(osmium.SimpleHandler):
    """第一遍：只收关系，记下需要回查的 node / way。"""

    def __init__(self) -> None:
        super().__init__()
        self.relations: dict[int, dict] = {}
        self.route_counter: Counter[str] = Counter()
        self.want_nodes: set[int] = set()
        self.want_ways: set[int] = set()

    def relation(self, rel) -> None:
        tags = tags_of(rel)
        route = tags.get("route")
        if route:
            self.route_counter[route] += 1
        if route not in ROUTE_KINDS:
            return
        members = []
        for index, member in enumerate(rel.members):
            members.append({"index": index, "type": member.type, "ref": member.ref, "role": member.role or ""})
            if member.type == "n":
                self.want_nodes.add(member.ref)
            elif member.type == "w":
                self.want_ways.add(member.ref)
        self.relations[rel.id] = {"id": rel.id, "route": route, "tags": tags, "members": members}


class WayPass(osmium.SimpleHandler):
    """第二遍：回查 way 的节点序列。"""

    def __init__(self, want: set[int], node_sink: set[int]) -> None:
        super().__init__()
        self.want = want
        self.node_sink = node_sink
        self.ways: dict[int, dict] = {}

    def way(self, way) -> None:
        if way.id not in self.want:
            return
        refs = [node.ref for node in way.nodes]
        self.node_sink.update(refs)
        self.ways[way.id] = {"refs": refs, "tags": tags_of(way)}


class NodePass(osmium.SimpleHandler):
    """第三遍：回查节点坐标与标签。"""

    def __init__(self, want: set[int]) -> None:
        super().__init__()
        self.want = want
        self.nodes: dict[int, dict] = {}

    def node(self, node) -> None:
        if node.id not in self.want:
            return
        self.nodes[node.id] = {
            "id": node.id,
            "lon": round(node.location.lon, 7),
            "lat": round(node.location.lat, 7),
            "tags": tags_of(node),
        }


def run_pass(handler, path: Path, label: str) -> float:
    started = time.time()
    handler.apply_file(str(path), locations=False)
    elapsed = time.time() - started
    print(f"    {label:<12} {elapsed:6.2f}s", flush=True)
    return elapsed


def extract(province: str, path: Path) -> dict:
    print(f"  [{province}] {path.name} {path.stat().st_size / 1048576:.2f} MB")

    rel_pass = RelationPass()
    run_pass(rel_pass, path, "关系扫描")

    way_pass = WayPass(rel_pass.want_ways, rel_pass.want_nodes)
    run_pass(way_pass, path, "way 几何")

    node_pass = NodePass(rel_pass.want_nodes)
    run_pass(node_pass, path, "节点坐标")

    return {
        "province": province,
        "relations": rel_pass.relations,
        "ways": way_pass.ways,
        "nodes": node_pass.nodes,
        "route_counter": rel_pass.route_counter,
    }


def assemble(per_province: list[dict]) -> tuple[dict[int, dict], list[dict]]:
    """按关系 id 合并跨省重复（花桥这类边界关系会在两份 extract 里各出现一次）。

    节点与 way 必须用**三省并集**回查：跨省关系常被保留在 A 省那份，
    但它的站节点落在 B 省 extract 里，只在 A 省里查会误报「未解析」。
    """
    all_nodes: dict[int, dict] = {}
    all_ways: dict[int, dict] = {}
    for chunk in per_province:
        for node_id, node in chunk["nodes"].items():
            all_nodes.setdefault(node_id, node)
        for way_id, way in chunk["ways"].items():
            all_ways.setdefault(way_id, way)

    merged: dict[int, dict] = {}
    duplicates: list[dict] = []
    for chunk in per_province:
        province = chunk["province"]
        for rid, rel in chunk["relations"].items():
            members = rel["members"]
            stop_refs = [m["ref"] for m in members if m["type"] == "n"]
            way_refs = [m["ref"] for m in members if m["type"] == "w"]

            # 同一节点可能以不同角色出现（stop / stop_entry_only / platform …），角色要留痕：
            # role=platform* 是站台不是车站，S2 建模必须能区分。
            roles_by_node: dict[int, list[str]] = {}
            for member in members:
                if member["type"] == "n":
                    roles_by_node.setdefault(member["ref"], []).append(member["role"] or "")

            stops = []
            for ref in dict.fromkeys(stop_refs):
                node = all_nodes.get(ref)
                roles = roles_by_node.get(ref, [])
                if node is None:
                    stops.append({"node": ref, "resolved": False, "name": None, "roles": roles})
                    continue
                tags = node["tags"]
                stops.append(
                    {
                        "node": ref,
                        "resolved": True,
                        "name": pick_name(tags),
                        "name_en": tags.get("name:en"),
                        "lon": node["lon"],
                        "lat": node["lat"],
                        "roles": roles,
                        "tags": tags,
                    }
                )

            ways = []
            for ref in dict.fromkeys(way_refs):
                way = all_ways.get(ref)
                if way is None:
                    ways.append({"ref": ref, "resolved": False, "geometry": None})
                    continue
                geometry = []
                for nid in way["refs"]:
                    node = all_nodes.get(nid)
                    if node is not None:
                        geometry.append([node["lon"], node["lat"]])
                ways.append({"ref": ref, "resolved": True, "nodes": way["refs"], "geometry": geometry})

            entry = {
                "id": rid,
                "route": rel["route"],
                "tags": rel["tags"],
                "members": members,
                "stops": stops,
                "ways": ways,
                "stats": {
                    "members": len(members),
                    "stop_members": len(stop_refs),
                    "unique_stops": len(stops),
                    "stop_nodes_resolved": sum(1 for s in stops if s["resolved"]),
                    "named_stops": sum(1 for s in stops if s["name"]),
                    "stop_role_nodes": sum(1 for s in stops if any(r.startswith("stop") for r in s.get("roles", []))),
                    "platform_nodes": sum(1 for s in stops if any(r.startswith("platform") for r in s.get("roles", []))),
                    "ways": len(way_refs),
                    "has_stops": bool(stop_refs),
                },
                "provinces": [province],
            }

            previous = merged.get(rid)
            if previous is None:
                merged[rid] = entry
                continue

            # 取成员更全的那份，并记下重复来源
            previous["provinces"].append(province)
            duplicates.append(
                {
                    "id": rid,
                    "name": entry["tags"].get("name") or previous["tags"].get("name"),
                    "kept": previous["provinces"][0],
                    "also_in": province,
                    "members": [previous["stats"]["members"], entry["stats"]["members"]],
                }
            )
            if entry["stats"]["members"] > previous["stats"]["members"]:
                entry["provinces"] = previous["provinces"]
                merged[rid] = entry
    return merged, duplicates


def main() -> int:
    parser = argparse.ArgumentParser()
    # 2026-11-01 扩到 5 省：江苏 L4 省界缺与山东/安徽共边的 way，且宁滁线、宁马线在安徽一侧
    parser.add_argument("--provinces", nargs="+",
                        default=["shanghai", "jiangsu", "zhejiang", "anhui", "shandong"])
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    snapshots = []
    for province in args.provinces:
        path = SNAP / f"{province}-latest.osm.pbf"
        if not path.exists():
            print(f"缺少快照文件：{path}", file=sys.stderr)
            return 2
        snapshots.append((province, path))

    print("— 逐省扫描 —")
    per_province = [extract(province, path) for province, path in snapshots]

    print("\n— 合并跨省重复 —")
    merged, duplicates = assemble(per_province)
    for dup in duplicates:
        print(f"  重复关系 {dup['id']} {dup['name']}  保留 {dup['kept']}（成员 {dup['members'][0]}），也见 {dup['also_in']}（成员 {dup['members'][1]}）")

    print("\n— route 取值统计（全量，含不产出的类型）—")
    for chunk in per_province:
        keys = ", ".join(f"{k}={v}" for k, v in sorted(chunk["route_counter"].items(), key=lambda kv: -kv[1])[:10])
        print(f"  {chunk['province']:<10} {keys}")

    by_route = Counter(rel["route"] for rel in merged.values())
    print("\n— 产出的轨道关系 —")
    for route, count in sorted(by_route.items(), key=lambda kv: -kv[1]):
        print(f"  {route:<12} {count}")

    masters = [rel for rel in merged.values() if not rel["stats"]["has_stops"]]
    print(f"\n  无 stop 成员（母关系，需在 S2 过滤）: {len(masters)}")
    for rel in masters:
        print(f"    {rel['id']}  {rel['tags'].get('name')}  members={rel['stats']['members']}")

    total_stops = sum(rel["stats"]["unique_stops"] for rel in merged.values())
    unresolved = sum(rel["stats"]["stop_members"] - rel["stats"]["stop_nodes_resolved"] for rel in merged.values())
    unnamed_resolved = sum(1 for rel in merged.values() for s in rel["stops"] if s["resolved"] and not s["name"])
    print(f"\n  唯一 stop 节点合计 {total_stops}；坐标未解析 {unresolved}；已解析但无站名 {unnamed_resolved}")

    role_counter: Counter[str] = Counter()
    for rel in merged.values():
        for stop in rel["stops"]:
            for role in stop.get("roles", []):
                role_counter[role or "(空)"] += 1
    print("  成员角色分布：" + ", ".join(f"{role}={count}" for role, count in role_counter.most_common()))
    stop_role_only = sum(1 for rel in merged.values() for s in rel["stops"] if any(r.startswith("stop") for r in s.get("roles", [])))
    print(f"  其中可作车站的（role 以 stop 开头）: {stop_role_only}；站台类（platform*）: {sum(rel['stats']['platform_nodes'] for rel in merged.values())}")

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "snapshot_date": SNAP.name,
        "source": "download.openstreetmap.fr/extracts/asia/china/<province>-latest.osm.pbf",
        "license": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "route_kinds": list(ROUTE_KINDS),
        "provinces": [{"province": p, "file": path.name, "bytes": path.stat().st_size} for p, path in snapshots],
        "route_counter": {chunk["province"]: dict(chunk["route_counter"]) for chunk in per_province},
        "duplicates_across_provinces": duplicates,
        "member_role_counter": dict(role_counter),
        "totals": {
            "relations": len(merged),
            "unique_stop_nodes": total_stops,
            "unresolved_stop_nodes": unresolved,
            "unnamed_resolved_stops": unnamed_resolved,
            "stop_role_nodes": stop_role_only,
            "platform_nodes": sum(rel["stats"]["platform_nodes"] for rel in merged.values()),
            "relations_without_stops": [rel["id"] for rel in merged.values() if not rel["stats"]["has_stops"]],
        },
        "relations": sorted(merged.values(), key=lambda rel: (rel["route"], rel["id"])),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n写出 {out}  {out.stat().st_size / 1048576:.2f} MB  {len(merged)} 条关系")
    return 0


if __name__ == "__main__":
    sys.exit(main())
