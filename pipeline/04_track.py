"""S1-5 关系清单与指纹：给每个线路关系建档，并对上一份清单做变更检测。

为什么要这一步（探测 4 的结论）：
1. Overpass / PBF 的**对象顺序不稳定**，原始字节的 SHA-256 每次都不同（实测三次三值）。
   所以快照可复现性必须比**规范化指纹**：成员按 `type|role|ref|lon6|lat6` 排序后再哈希。
2. 关系数会变，但**不等于线路增减**：2026-06-01 是 54 条、今天是 52 条，差的 2 条是嘉兴市域铁路
   被改回 `route=train` 标签（19161306 / 20159126）。所以必须按**关系 id** 建档，逐次记录
   标签变化，而不是只比总数。
3. 关系会改标签（改名、改色、改 operator）、会调整成员（加站、改走线），这两类变化要分开记，
   否则「站序变了」和「只是改了个名字」混在一起，没法排查。

产物：data/processed/relation-index.json（提交进仓库，是 S1-6 归属校验的输入）

用法：
    python pipeline/04_track.py                # 与已有的 relation-index.json 比对
    python pipeline/04_track.py --prev X.json  # 与指定清单比对
    python pipeline/04_track.py --no-prev      # 只建档，不做变更检测
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY = os.environ.get("SUBWAY_CITY", "sh")  # 由 --city / 环境变量覆盖；只有上海沿用 P0 的全局清单位置
CFG = load_city(CITY)
P = Paths(CFG)
RAW = P.raw_transit()
OUT = P.relation_index_global() if CFG.code == "sh" else P.relation_index()  # 全局清单只归上海

# OSM 的 route 值 -> 本项目的制式（AGENTS.md 第 8 节枚举 + 轨道制式外的两种单列）
ROUTE_TO_TYPE = {
    "subway": "metro",
    "light_rail": "lrt",
    "monorail": "monorail",
    "tram": "tram",
}
# 按 ref 单条覆盖：来自城市配置（上海：磁浮是独立制式、浦江线是胶轮捷运）
REF_TO_TYPE = dict(CFG.ref_overrides)
# 这些标签变化属于「噪音」，不进 tag_hash，避免每次快照都报变更
NOISE_TAG_PREFIXES = ("payment:", "opening_", "check_")


def log(msg: str) -> None:
    print(msg, flush=True)


def canon_tags(tags: dict) -> dict:
    """去掉噪音标签，按 key 排序，用于稳定哈希与变更比对。"""
    return {
        k: tags[k]
        for k in sorted(tags)
        if not k.startswith(NOISE_TAG_PREFIXES)
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def member_fingerprint(rel: dict) -> str:
    """规范化成员指纹：与输出顺序无关。

    格式：`type|role|ref`，节点若已解析出坐标则追加 `|lon6|lat6`。
    排序后逐行拼接再哈希 —— 这样只要成员集合与坐标不变，指纹就不变。
    """
    coord = {s["node"]: (s["lon"], s["lat"]) for s in rel["stops"] if s.get("resolved")}
    lines = []
    for m in rel["members"]:
        line = f"{m['type']}|{m.get('role') or ''}|{m['ref']}"
        if m["type"] == "n" and m["ref"] in coord:
            lon, lat = coord[m["ref"]]
            line += f"|{lon:.6f}|{lat:.6f}"
        lines.append(line)
    return sha256_text("\n".join(sorted(lines)))


def stops_fingerprint(rel: dict) -> str:
    """站序指纹：按成员顺序取站名，站序或站名变化都会被检出。"""
    seq = [s.get("name") or f"node/{s['node']}" for s in rel["stops"] if s.get("resolved")]
    return sha256_text("\n".join(seq))


def transit_type(rel: dict) -> str:
    tags = rel["tags"]
    ref = (tags.get("ref") or "").strip()
    if ref in REF_TO_TYPE:
        return REF_TO_TYPE[ref]
    name = tags.get("name") or ""
    for key, val in REF_TO_TYPE.items():
        if key in name:
            return val
    return ROUTE_TO_TYPE.get(rel["route"], "unclassified")


def build_record(rel: dict, snapshot_date: str, prev: dict | None) -> dict:
    tags = canon_tags(rel["tags"])
    stop_names = [s.get("name") or "" for s in rel["stops"] if s.get("resolved")]
    # 环线判据（OSM 里没有 "loop" 标签，只有两种写法）：
    #   a) from == to（上海 4 号线：from=to=宜山路，name=内圈/外圈）
    #   b) 站序首尾同名（松江有轨电车 2 号线：松江大学城 -> … -> 松江大学城）
    # 注意「没有 from/to」不等于环线 —— 苏州 7 号线、高新有轨都没有 from/to，但首末站不同，
    # 上海地铁 1 号线母关系 6800211 连一个站都没有。
    f, t = tags.get("from"), tags.get("to")
    loop_evidence = None
    if f and t and f == t:
        loop_evidence = "from_to_same"
    elif len(stop_names) >= 3 and stop_names[0] == stop_names[-1]:
        loop_evidence = "stops_ring"
    is_loop = loop_evidence is not None
    rec = {
        "id": rel["id"],
        "name": tags.get("name") or tags.get("name:zh") or "",
        "transit_type": transit_type(rel),
        "route": rel["route"],
        "ref": tags.get("ref"),
        "colour": tags.get("colour"),
        "operator": tags.get("operator"),
        "network": tags.get("network"),
        "from": tags.get("from"),
        "to": tags.get("to"),
        "is_loop": is_loop,
        "loop_evidence": loop_evidence,
        "provinces": rel["provinces"],
        "stats": {
            "members": rel["stats"]["members"],
            "ways": rel["stats"]["ways"],
            "stop_members": rel["stats"]["stop_members"],
            "unique_stops": rel["stats"]["unique_stops"],
            "named_stops": rel["stats"]["named_stops"],
            "has_stops": rel["stats"]["has_stops"],
        },
        "stop_names": stop_names,
        "fingerprint": member_fingerprint(rel),
        "stops_hash": stops_fingerprint(rel),
        "tag_hash": sha256_text(json.dumps(tags, ensure_ascii=False, sort_keys=True)),
        "tags": tags,
        # 城市归属由 S1-6 填，这里不猜（bbox 与粗边界都不可靠，探测 10 已证）
        "city": None,
        "first_seen": snapshot_date,
        "last_seen": snapshot_date,
        "status": "active",
    }
    if prev:
        rec["first_seen"] = prev.get("first_seen") or snapshot_date
        if prev.get("tag_hash") == rec["tag_hash"]:
            rec["tags"] = prev.get("tags", rec["tags"])  # 未变就不改写，省 diff 噪音
    return rec


def diff_index(prev_rel: dict, new_rel: dict) -> dict:
    """逐关系比对，返回变更条目（空 dict 表示无变化）。"""
    changes = {}
    if prev_rel.get("fingerprint") != new_rel["fingerprint"]:
        changes["members"] = {
            "members": [prev_rel["stats"]["members"], new_rel["stats"]["members"]],
            "unique_stops": [prev_rel["stats"]["unique_stops"], new_rel["stats"]["unique_stops"]],
        }
    if prev_rel.get("stops_hash") != new_rel["stops_hash"]:
        old = prev_rel.get("stop_names") or []
        new = new_rel["stop_names"]
        changes["stops"] = {
            "stops": [len(old), len(new)],
            "added": [s for s in new if s not in old],
            "removed": [s for s in old if s not in new],
        }
    if prev_rel.get("tag_hash") != new_rel["tag_hash"]:
        old_tags = prev_rel.get("tags") or {}
        new_tags = new_rel["tags"]
        keys = sorted(set(old_tags) | set(new_tags))
        delta = {}
        for k in keys:
            if old_tags.get(k) != new_tags.get(k):
                delta[k] = [old_tags.get(k), new_tags.get(k)]
        changes["tags"] = delta
    if prev_rel.get("transit_type") != new_rel["transit_type"]:
        changes["transit_type"] = [prev_rel.get("transit_type"), new_rel["transit_type"]]
    return changes


def main() -> int:
    global CFG, P, RAW, OUT, REF_TO_TYPE
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(RAW), help="S1-3 产物路径（默认 data/raw/transit-relations.json）")
    ap.add_argument("--out", default=str(OUT), help="输出的清单路径")
    ap.add_argument("--prev", default=str(OUT), help="上一份清单路径（默认读 OUT 自身）")
    ap.add_argument("--no-prev", action="store_true", help="不做变更检测")
    ap.add_argument("--city", default=CITY, help="城市码（默认 sh，见 pipeline/cities/*.json）")
    args = ap.parse_args()

    if args.city != CITY:
        CFG = load_city(args.city)
        P = Paths(CFG)
        RAW = P.raw_transit()
        OUT = P.relation_index_global() if CFG.code == "sh" else P.relation_index()
        REF_TO_TYPE = dict(CFG.ref_overrides)

    raw_path = Path(args.raw)
    if not raw_path.exists():
        log(f"缺少 S1-3 产物：{raw_path}，先跑 pipeline/02_extract_transit.py")
        return 2

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    snapshot_date = raw["snapshot_date"]

    prev_map: dict[int, dict] = {}
    prev_path = Path(args.prev)
    if not args.no_prev and prev_path.exists():
        try:
            prev_raw = json.loads(prev_path.read_text(encoding="utf-8"))
            prev_map = {r["id"]: r for r in prev_raw.get("relations", [])}
            log(f"上一份清单：{prev_path}（{len(prev_map)} 条关系，快照 {prev_raw.get('snapshot_date')}）")
        except json.JSONDecodeError:
            log(f"上一份清单无法解析，按「无上一份」处理：{prev_path}")

    records = []
    changes = {"added": [], "removed": [], "tag_changed": [], "stops_changed": [], "members_changed": []}

    for rel in raw["relations"]:
        rec = build_record(rel, snapshot_date, prev_map.get(rel["id"]))
        if prev_map:
            prev_rel = prev_map.get(rel["id"])
            if prev_rel is None:
                changes["added"].append(rec["id"])
                rec["status"] = "added"
            else:
                delta = diff_index(prev_rel, rec)
                if delta:
                    rec["changes"] = delta
                    if "tags" in delta:
                        changes["tag_changed"].append(rec["id"])
                    if "stops" in delta:
                        changes["stops_changed"].append(rec["id"])
                    if "members" in delta:
                        changes["members_changed"].append(rec["id"])
        records.append(rec)

    # 上一份里有、这一份没有的关系：保留档案，标记 removed，便于回溯「哪条线消失了」
    new_ids = {r["id"] for r in records}
    for rid, prev_rel in prev_map.items():
        if rid in new_ids:
            continue
        gone = dict(prev_rel)
        gone["status"] = "removed"
        gone["last_seen"] = prev_rel.get("last_seen") or prev_rel.get("first_seen")
        records.append(gone)
        changes["removed"].append(rid)

    records.sort(key=lambda r: r["id"])

    by_type = Counter(r["transit_type"] for r in records if r["status"] != "removed")
    by_prov = Counter()
    for r in records:
        if r["status"] == "removed":
            continue
        for p in r["provinces"]:
            by_prov[p] += 1
    loop_ids = [r["id"] for r in records if r["is_loop"] and r["status"] != "removed"]
    no_stops = [r["id"] for r in records if not r["stats"]["has_stops"] and r["status"] != "removed"]

    # 整表指纹：只对 id + 指纹对排序后哈希，不含 generated_at，保证同输入可复现
    index_fingerprint = sha256_text(
        "\n".join(sorted(f"{r['id']}:{r['fingerprint']}" for r in records if r["status"] != "removed"))
    )

    out = {
        "snapshot_date": snapshot_date,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": raw["source"],
        "license": raw["license"],
        "attribution": raw["attribution"],
        "algorithm": {
            "fingerprint": "sha256 over sorted lines of `type|role|ref[|lon6|lat6]`，节点坐标仅在已解析时参与",
            "stops_hash": "sha256 over 按成员顺序的站名序列",
            "tag_hash": "sha256 over 按键排序的标签（排除 payment:* / opening_* / check_*）",
            "index_fingerprint": "sha256 over sorted `id:fingerprint`，不含 generated_at",
        },
        "counts": {
            "relations_active": sum(1 for r in records if r["status"] != "removed"),
            "relations_removed": sum(1 for r in records if r["status"] == "removed"),
            "by_transit_type": dict(sorted(by_type.items())),
            "by_province": dict(sorted(by_prov.items())),
            "loop_relations": len(loop_ids),
            "relations_without_stops": len(no_stops),
        },
        "changes": changes,
        "relations": records,
        "index_fingerprint": index_fingerprint,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    size = out_path.stat().st_size

    log("== 关系清单 ==")
    log(f"  有效 {out['counts']['relations_active']} 条，已消失 {out['counts']['relations_removed']} 条")
    log(f"  按制式 {out['counts']['by_transit_type']}")
    log(f"  按省份 {out['counts']['by_province']}")
    log(f"  环线 {len(loop_ids)} 条：{loop_ids}")
    log(f"  无 stop 成员（无站序）{len(no_stops)} 条：{no_stops}")
    if prev_map:
        log("== 变更 ==")
        for key, ids in changes.items():
            log(f"  {key}: {len(ids)} {ids[:8]}{' ...' if len(ids) > 8 else ''}")
    log(f"== 写出 {out_path} ==")
    log(f"   字节 {size:,}，index_fingerprint {index_fingerprint[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
