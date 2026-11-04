"""S1-6 归属校验：用 OSM 精确行政边界给每条关系判省与市。

依据（探测 10 + AGENTS.md 第 12/15 节 + S1-6 实测）：
1. **矩形 bbox 不能当城市边界**：上海矩形同时罩住苏州（花桥/东方之门）与嘉兴（嘉善/水乡客厅）。
   探测 1 在 52 个 route=subway 关系里混进 4 条苏州线；探测 4 还见过 2 条嘉兴市域铁路。
2. **粗略边界也不能单独定归属**：geoBoundaries 的全国省级简化边界（0.26 MB）把临港滴水湖（−4.91 km）、
   嘉定北（−0.81 km）、青浦西岑（−4.65 km）都判到界外，52 条关系里假阴性 12/52。
3. 本机 OSM 数据的实测限制（S1-6 探查）：
   - `admin_level=4` 拼接：**上海市 72/72 → 16,229.5 km² 成功**；浙江省需要跨 extract 并集才齐（241/241
     → 144,895.7 km²，含海域）；**江苏省永远差 11 个 way**（那些是与山东/安徽的共边，未下载的省里），
     自己拼只有 23 个小片、309.4 km²，不可用。
   - 所以江苏省改用**其 13 个地级市（L5）面并集**代表；每个地级市面在自己省内 extract 里是闭合的
     （苏州市 160/160 → 8,638 km²、嘉兴市 101/101、昆山市 53/53 → 934 km² 等，与官方面积吻合）。
   - 城市归属因此**直接用 L5 地级市面判定**，不再维护「区县 → 地级市」手写台账 —— OSM 里 L5 就是地级市，
     比人工映射表更不容易错。
4. 人工台账仍保留一处：`CITY_ALIAS` 只把 OSM 名称规整成对外统一写法（如「上海市」），不参与判定。

输入：三省 PBF（S1-2 快照）+ data/raw/transit-relations.json（S1-3）+ data/processed/relation-index.json（S1-5）
产物：data/processed/attribution-report.json、docs/conflicts.md，并回填 relation-index.json 的 city/province

用法：python pipeline/05_attribution.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import osmium
import shapely
from shapely import contains_xy
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY = os.environ.get("SUBWAY_CITY", "sh")  # 由 --city / 环境变量覆盖；上海沿用 P0 的全局产物位置
CFG = load_city(CITY)
P = Paths(CFG)

SNAPSHOT = P.snapshot_dir(CFG.snapshot)
# PBF 名 -> 省份名来自配置；PBFS 保留「省份名 -> 路径」的旧形状供扫描使用
PROVINCE_OF_EXTRACT = dict(CFG.pbf_provinces)
PBFS = {PROVINCE_OF_EXTRACT[pbf]: P.pbf(pbf, CFG.snapshot) for pbf in CFG.pbfs}
RAW = P.raw_transit()
_IS_LEGACY = CFG.code == "sh"  # 全局审计文件（关系清单 / 归属报告 / conflicts.md）只归上海
INDEX = P.relation_index_global() if _IS_LEGACY else P.relation_index()
OUT_REPORT = P.attribution_report_global() if _IS_LEGACY else P.attribution_report()
OUT_CONFLICTS = P.doc("conflicts.md") if _IS_LEGACY else P.doc(f"conflicts-{CFG.code}.md")

# 关系 id -> 省份名（L4），用 id 而不是名字匹配，避免同名歧义
PROVINCE_L4 = CFG.province_faces
# 必须在场且闭合的省面（否则无法给这一带的线路定归属）
REQUIRED_PROVINCES = tuple(CFG.must_close_provinces)
# 某些省 L4 拼不闭合时的兜底：用固定名称表里的地级市并集代表该省
L5_UNION_NAMES = {prov: tuple(names) for prov, names in CFG.province_l5_union.items()}
L5_UNION_PROVINCE = {name: prov for prov, names in L5_UNION_NAMES.items() for name in names}
KM = CFG.km_lon * CFG.km_lat  # 本纬度下 1°×(1°) 的平方公里数


def log(msg: str) -> None:
    print(msg, flush=True)


class AdminScan(osmium.SimpleHandler):
    """第一遍：收行政界关系（L4 三省 + 所有 L5 地级市 + 上海 16 区）。"""

    def __init__(self, province: str) -> None:
        super().__init__()
        self.province = province
        self.l4: dict[int, dict] = {}
        self.l5: dict[int, dict] = {}
        self.l6: dict[int, dict] = {}

    def relation(self, r) -> None:
        tags = dict(r.tags)
        if tags.get("boundary") != "administrative":
            return
        level = tags.get("admin_level")
        name = tags.get("name") or ""
        if not name:
            return
        outer, inner = [], []
        for m in r.members:
            if m.type != "w":
                continue
            (inner if m.role == "inner" else outer).append(m.ref)
        if not outer:
            return
        rec = {"id": r.id, "name": name, "ways": outer + inner, "level": level,
               "outer": len(outer), "inner": len(inner), "extract": self.province}
        if level == "4" and r.id in PROVINCE_L4:
            self.l4[r.id] = rec
        elif level == "5":
            self.l5.setdefault(r.id, rec)
        elif level == "6" and self.province == "shanghai":
            self.l6.setdefault(r.id, rec)


class WayGeomScan(osmium.SimpleHandler):
    def __init__(self, want: set[int]) -> None:
        super().__init__()
        self.want = want
        self.geom: dict[int, list[tuple[float, float]]] = {}

    def way(self, w) -> None:
        if w.id not in self.want:
            return
        try:
            self.geom[w.id] = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            pass


def assemble(rec: dict, geom: dict[int, list]) -> shapely.Geometry | None:
    rings = [LineString(geom[w]) for w in rec["ways"] if w in geom and len(geom[w]) >= 2]
    if len(rings) < 3:
        return None
    polys = [p for p in polygonize(unary_union([shapely.make_valid(r) for r in rings])) if p.area > 1e-9]
    if not polys:
        return None
    return unary_union(polys)


def area_km2(g) -> float:
    return g.area * KM


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    # ---------- 1. 扫五个 extract，合并 way 几何 ----------
    # 跨 extract 必须是 **way 并集**：同一个关系在不同 extract 里列出的成员 way 不同，
    # 取「way 数最多」那一份会用到残缺集合（S1-6 第一版就这么把南通判成未闭合）。
    scans: dict[str, AdminScan] = {}
    all_ids: dict[int, dict] = {}
    for prov, path in PBFS.items():
        sc = AdminScan(prov)
        sc.apply_file(str(path))
        scans[prov] = sc
        for table in (sc.l4, sc.l5, sc.l6):
            for rid, rec in table.items():
                prev = all_ids.get(rid)
                if prev is None:
                    all_ids[rid] = dict(rec)
                else:
                    prev["ways"] = sorted(set(prev["ways"]) | set(rec["ways"]))
                    prev["outer"] = max(prev["outer"], rec["outer"])
                    prev["inner"] = max(prev["inner"], rec["inner"])
                    if rec["extract"] not in prev["extract"]:
                        prev["extract"] = f"{prev['extract']}+{rec['extract']}"
        log(f"[{prov}] L4 {len(sc.l4)} / L5 {len(sc.l5)} / L6 {len(sc.l6)}")

    want = {w for rec in all_ids.values() for w in rec["ways"]}
    log(f"需要 way 几何 {len(want)} 个（跨五省并集）")
    geom: dict[int, list[tuple[float, float]]] = {}
    for prov, path in PBFS.items():
        ws = WayGeomScan(want)
        ws.apply_file(str(path), locations=True)
        for k, v in ws.geom.items():
            geom.setdefault(k, v)
        log(f"   [{prov}] 取到 {len(ws.geom)}，累计 {len(geom)}")

    # ---------- 2. 拼多边形 ----------
    built: dict[int, dict] = {}
    for rid, rec in all_ids.items():
        g = assemble(rec, geom)
        if g is None:
            log(f"   [跳过] {rec['name']}（{rid}, {rec['extract']}）：{len(rec['ways'])} 个 way 未闭合")
            continue
        built[rid] = {**rec, "geom": g, "closed": all(w in geom for w in rec["ways"])}

    # 省面：五个 L4 关系（江苏在缺邻省 way 时走地级市并集兜底）
    prov_geoms: dict[str, shapely.Geometry] = {}
    for rid, name in PROVINCE_L4.items():
        b = built.get(rid)
        if b is None:
            log(f"[省面] {name}（L4 {rid}）拼不出来，跳过")
            continue
        log(f"[省面] {name}（L4 {rid}）{area_km2(b['geom']):,.1f} km²，部件 "
            f"{len(getattr(b['geom'], 'geoms', [b['geom']]))}，way {len(b['ways'])}，闭合 {b['closed']}")
        if b["closed"]:
            prov_geoms[name] = b["geom"]

    for prov, names in L5_UNION_NAMES.items():
        if prov in prov_geoms:
            continue
        parts = [x for x in built.values()
                 if x.get("level") == "5" and x["closed"] and x["name"] in names]
        if parts:
            union = unary_union([x["geom"] for x in parts])
            prov_geoms[prov] = union
            have = {x["name"] for x in parts}
            log(f"[省面] {prov}（兜底：地级市并集 {len(parts)}/{len(names)} 个）"
                f"{area_km2(union):,.1f} km²；缺 {[n for n in names if n not in have]}")

    # 江苏只靠「地级市并集」会有缺口（南通、盐城的市面本身拼不闭合），
    # 所以江苏另配一份固定名称表：市名命中即判江苏省，不依赖省面几何。
    # 这份表只有 13 个名字，是行政区划事实，不是从几何里猜出来的。
    missing = [n for n in REQUIRED_PROVINCES if n not in prov_geoms]
    if missing:
        log(f"!! 省面缺失 {missing}，停下等用户决策")
        return 3

    # 市面：只取闭合的 L5 地级市；省份由「面落在哪个省面里」决定，江苏另按名称表兜底
    prov_items_sorted = sorted(prov_geoms.items())
    city_geoms: dict[str, dict] = {}
    for rid, b in built.items():
        if b.get("level") != "5" or not b["closed"]:
            continue  # 未闭合的市面不参与判定，避免假内/假外
        pt = shapely.point_on_surface(b["geom"])
        prov = next((pn for pn, pg in prov_items_sorted if pg.contains(pt)), None)
        if prov is None and b["name"] in L5_UNION_PROVINCE:
            prov = L5_UNION_PROVINCE[b["name"]]
        if prov is None:
            continue  # 落在五省之外（河南等）的市，本次不参与
        prev = city_geoms.get(b["name"])
        if prev is None or area_km2(b["geom"]) > area_km2(prev["geom"]):
            city_geoms[b["name"]] = {"geom": b["geom"], "province": prov, "id": rid}
    if CFG.city_admin_level == 4:
        # 直辖市：城市面就是省面
        city_geoms[CFG.city] = {"geom": prov_geoms[CFG.province], "province": CFG.province,
                                "id": CFG.city_admin_id}
    elif CFG.city not in city_geoms:
        log(f"!! 城市面 {CFG.city}（L5 {CFG.city_admin_id}）没拼出来，停下")
        return 4
    fallback_missing = [n for names in L5_UNION_NAMES.values() for n in names if n not in city_geoms]
    log(f"[市面] 可用市面 {len(city_geoms)} 个（含 {CFG.city}）；兜底名单里未用上的 {fallback_missing}")

    # ---------- 3. 逐关系归属 ----------
    city_items = sorted(city_geoms.items())
    prov_items = sorted(prov_geoms.items())
    relations, conflicts = [], []
    per_rel_stops: dict[int, list[dict]] = {}
    flags_counter: Counter[str] = Counter()

    for rel in raw["relations"]:
        rid = rel["id"]
        irec = next((x for x in index["relations"] if x["id"] == rid), {})
        stops = [s for s in rel["stops"] if s.get("resolved")]
        if not stops:
            flags_counter["no_resolved_stops"] += 1
            relations.append({"id": rid, "name": irec.get("name"), "transit_type": irec.get("transit_type"),
                              "province": None, "city": None, "stops_total": 0,
                              "stops_by_province": {}, "stops_by_city": {}, "stops_unmatched": 0,
                              "flags": ["no_resolved_stops"], "method": "none"})
            continue

        xs = np.array([s["lon"] for s in stops])
        ys = np.array([s["lat"] for s in stops])

        # 逐站先判市，再判省（市面判中即可推出省）
        stop_city, stop_prov, stop_attr = [], [], []
        for i in range(len(stops)):
            cx, cy = np.array([xs[i]]), np.array([ys[i]])
            city = province = None
            for name, rec in city_items:
                if contains_xy(rec["geom"], cx, cy)[0]:
                    city, province = name, rec["province"]
                    break
            if city is None:
                for name, g in prov_items:
                    if contains_xy(g, cx, cy)[0]:
                        province = name
                        break
            stop_city.append(city)
            stop_prov.append(province)
            stop_attr.append({"name": stops[i].get("name"), "lon": round(float(xs[i]), 5),
                              "lat": round(float(ys[i]), 5),
                              "city": city, "province": province})

        c_city = Counter(c for c in stop_city if c)
        c_prov = Counter(p for p in stop_prov if p)
        unmatched = sum(1 for c, p in zip(stop_city, stop_prov) if c is None and p is None)

        flags = []
        if unmatched:
            flags.append(f"stops_unmatched:{unmatched}")
        city = c_city.most_common(1)[0][0] if c_city else None
        province = c_prov.most_common(1)[0][0] if c_prov else None
        method = "l5_city" if c_city else ("l4_province" if c_prov else "none")
        if city is None and province is not None:
            flags.append("city_unknown_within_province")
            if len(c_prov) > 1:
                flags.append("cross_province")
        distinct_cities = {c for c in stop_city if c}
        distinct_provs = {p for p in stop_prov if p}
        if len(distinct_provs) > 1:
            flags.append("cross_province_mixed")
            conflicts.append({
                "type": "cross_province", "id": rid, "name": irec.get("name"),
                "by_province": dict(c_prov),
                "stops": [f"{s['name'] or '(无名)'} → {p or '(未命中)'}" for s, p in zip(stops, stop_prov)],
            })
        if len(distinct_cities) > 1 and not conflicts:
            conflicts.append({
                "type": "cross_city", "id": rid, "name": irec.get("name"),
                "by_city": dict(c_city),
                "stops": [f"{s['name'] or '(无名)'} → {c or '(未命中)'}" for s, c in zip(stops, stop_city)],
            })
        for f in flags:
            flags_counter[f.split(":")[0]] += 1

        per_rel_stops[rid] = stop_attr
        relations.append({
            "id": rid, "name": irec.get("name"), "transit_type": irec.get("transit_type"),
            "province": province, "city": city,
            "stops_total": len(stops),
            "stops_by_city": dict(c_city),
            "stops_by_province": dict(c_prov),
            "stops_unmatched": unmatched,
            "flags": flags, "method": method,
        })

    # ---------- 4. 汇总 ----------
    by_city = Counter(r["city"] or "(未定)" for r in relations)
    by_prov = Counter(r["province"] or "(未定)" for r in relations)
    log("\n== 归属汇总 ==")
    log(f"  关系 {len(relations)} 条；按省 {dict(by_prov)}")
    log(f"  按市（前 12）{dict(by_city.most_common(12))}")
    log(f"  标记 {dict(flags_counter)}")

    # 交叉校验（失败触发器）：上海关系里「落在上海市面之外，而且也没能判到任何市/省」的站。
    # 落在界外但已判到江苏（昆山 11 号线花桥段）、浙江的站是**正常**的，不算异常；
    # 只有「界外 + 未定」才说明边界缺部件或合并逻辑坏了。按站名+坐标去重，避免双向关系重复计数。
    sh_outside, sh_inside, sh_suspect = [], [], {}
    for att in relations:
        r_attr = per_rel_stops.get(att["id"], [])
        if att["stops_by_province"].get("上海市", 0) == 0:
            continue
        for s in r_attr:
            hit = contains_xy(prov_geoms["上海市"], np.array([s["lon"]]), np.array([s["lat"]]))[0]
            rec = (s["name"], s["lon"], s["lat"])
            if hit:
                sh_inside.append(rec)
            else:
                sh_outside.append(rec)
                if s["city"] is None and s["province"] is None:
                    sh_suspect[rec] = s
    sh_outside = sorted(set(sh_outside))
    sh_inside = sorted(set(sh_inside))
    log(f"[校验] 上海关系内的站：市内 {len(sh_inside)}，市外 {len(sh_outside)}，"
        f"其中「界外且未定」{len(sh_suspect)}")
    if sh_suspect:
        log(f"   界外且未定样例：{list(sh_suspect.items())[:6]}")
    if len(sh_suspect) > 5:
        log("!! 「界外且未定」站超过 5 个，触发失败触发器（边界可能缺部件），停下等用户决策")
        return 4

    # ---------- 5. 写出 ----------
    report = {
        "snapshot_date": raw["snapshot_date"],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "method": {
            "city": "admin_level=5 地级市面点面判定（上海用 admin_level=4 上海市面）",
            "province": "城市命中即得省；未命中城市时退回省面（上海/浙江/安徽用 L4，江苏 = 13 地级市并集）",
            "why_jiangsu_union": "江苏省 L4 关系 374 个 way 齐全但仍拼不闭合（自拼只有 309.4 km² / 23 个碎片），"
                                 "改用地级市（L5）并集 + 13 市固定名称表",
            "known_gaps": "南通市、盐城市的市面本身拼不闭合，两市内的站目前判不出归属（在 conflicts.md 列出）",
            "note": "几何只做判定，城市名来自 OSM L5 名称，不由几何发明；未命中一律 null + flag",
        },
        "boundaries": {
            name: {"area_km2": round(area_km2(g), 1),
                   "parts": len(getattr(g, "geoms", [g]))}
            for name, g in prov_geoms.items()
        },
        "city_polygons": {name: {"id": rec["id"], "province": rec["province"],
                                 "area_km2": round(area_km2(rec["geom"]), 1)}
                          for name, rec in city_geoms.items()},
        "checks": {
            "shanghai_stops_inside": len(sh_inside),
            "shanghai_stops_outside": len(sh_outside),
            "shanghai_stops_outside_sample": [list(x) for x in sh_outside[:12]],
            "shanghai_stops_outside_unattributed": len(sh_suspect),
        },
        "counts": {
            "relations_total": len(relations),
            "by_province": dict(by_prov),
            "by_city": dict(by_city),
            "flags": dict(flags_counter),
        },
        "conflicts": conflicts,
        "relations": relations,
    }
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    filled = 0
    for rec in index["relations"]:
        att = next((r for r in relations if r["id"] == rec["id"]), None)
        if att is None:
            continue
        rec["city"] = att["city"]
        rec["province"] = att["province"]
        rec["attribution"] = {
            "method": att["method"],
            "stops_total": att["stops_total"],
            "stops_by_city": att["stops_by_city"],
            "stops_by_province": att["stops_by_province"],
            "stops_unmatched": att["stops_unmatched"],
            "flags": att["flags"],
        }
        if att["city"] or att["province"]:
            filled += 1
    index["attribution_summary"] = report["counts"]
    index["attribution_generated_at"] = report["generated_at"]
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    write_conflicts(report)
    log(f"\n== 写出 {OUT_REPORT}（{OUT_REPORT.stat().st_size:,} B）==")
    log(f"== 回填 {INDEX}：{filled}/{len(index['relations'])} 条 ==")
    log(f"== 写出 {OUT_CONFLICTS} ==")
    return 0


def write_conflicts(report: dict) -> None:
    L = ["# 归属冲突与待定项（S1-6 产出）", ""]
    L.append(f"- 快照 {report['snapshot_date']}；生成 {report['generated_at']}")
    L.append(f"- 关系 {report['counts']['relations_total']} 条；按省 {report['counts']['by_province']}")
    L.append(f"- 按市（前 12）{dict(sorted(report['counts']['by_city'].items(), key=lambda kv: -kv[1])[:12])}")
    L.append(f"- 标记 {report['counts']['flags']}")
    L.append(f"- 上海关系内站点：市内 {report['checks']['shanghai_stops_inside']}，"
             f"市外 {report['checks']['shanghai_stops_outside']}"
             f"（其中界外且未定 {report['checks']['shanghai_stops_outside_unattributed']}）")
    L.append("")
    L.append("## 一、跨省关系")
    L.append("")
    cross = [c for c in report["conflicts"] if c["type"] == "cross_province"]
    if cross:
        L.append("| 关系 | 名称 | 各省站数 |")
        L.append("| --- | --- | --- |")
        for c in cross:
            L.append(f"| `{c['id']}` | {c['name']} | {c['by_province']} |")
        L.append("")
        for c in cross:
            L.append(f"### `{c['id']}` {c['name']}")
            for s in c["stops"]:
                L.append(f"- {s}")
            L.append("")
    else:
        L.append("无。")
        L.append("")
    L.append("## 二、跨市关系（同一关系跨地级市）")
    L.append("")
    crosscity = [c for c in report["conflicts"] if c["type"] == "cross_city"]
    if crosscity:
        L.append("| 关系 | 名称 | 各市站数 |")
        L.append("| --- | --- | --- |")
        for c in crosscity:
            L.append(f"| `{c['id']}` | {c['name']} | {c['by_city']} |")
        L.append("")
    else:
        L.append("无。")
        L.append("")
    L.append("## 三、未定城市的关系")
    L.append("")
    unknown = [r for r in report["relations"] if r["city"] is None and r["stops_total"] > 0]
    L.append(f"共 {len(unknown)} 条。")
    L.append("")
    if unknown:
        L.append("| 关系 | 名称 | 制式 | 省 | 站数 | 未命中 | flags |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in unknown[:60]:
            L.append(f"| `{r['id']}` | {r['name']} | {r['transit_type']} | {r['province']} | "
                     f"{r['stops_total']} | {r['stops_unmatched']} | {', '.join(r['flags'])} |")
    L.append("")
    L.append("## 四、无已解析站的关系")
    L.append("")
    for r in report["relations"]:
        if r["stops_total"] == 0:
            L.append(f"- `{r['id']}` {r['name']}：{', '.join(r['flags'])}")
    L.append("")
    L.append("## 五、口径")
    L.append("")
    L.append("- 市：`admin_level=5` 地级市面（上海用 `admin_level=4` 上海市面）点面判定，并用 `contains_xy` 批量算。")
    L.append("- 省：城市命中即得省；城市未命中时退回省面（上海/浙江 L4，江苏 = 13 地级市并集）。")
    L.append("- 江苏省 L4 关系缺 11 个与山东/安徽的共边 way（未下载那两省），自拼只有 309.4 km²，故改用并集。")
    L.append("- 未闭合的市面不参与判定（避免假内假外），这类城市在「未定城市」里列出。")
    L.append("- 上海 P0 只需上海市定案；苏浙其他城市已随 L5 自动得到，供 P1 使用。")
    # 生成段只覆盖「一～五」；「六、七…」是人工维护的台账，重跑时必须原样保留
    manual_tail = ""
    if OUT_CONFLICTS.exists():
        old_lines = OUT_CONFLICTS.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(old_lines):
            if line.startswith(("## 六", "## 七", "## 八", "## 九", "## 十")):
                manual_tail = "\n".join(old_lines[i:])
                break
    body = "\n".join(L).rstrip("\n")
    if manual_tail:
        body += "\n\n" + manual_tail
    OUT_CONFLICTS.parent.mkdir(parents=True, exist_ok=True)
    OUT_CONFLICTS.write_text(body + "\n", encoding="utf-8")
    if manual_tail:
        log(f"   （保留了人工维护段，{len(manual_tail.splitlines())} 行）")


if __name__ == "__main__":
    raise SystemExit(main())
