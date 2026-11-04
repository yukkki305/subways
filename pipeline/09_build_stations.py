#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S2-3：站点抽取与合并（ADB R4）。

输入：
  `data/processed/shanghai/lines.json`      —— 20 条 line / 23 个 branch 的有序站名
  `data/raw/transit-relations.json`         —— 每条关系的 stop 成员（节点 id + 坐标 + 中英文名）
  `data/processed/attribution-report.json`  —— 逐站归属（跨省关系的 `conflicts[].stops`）
输出：
  `data/processed/shanghai/station.json`    —— 站点实体 + 每站的 slot（哪条线哪一站）
  `docs/mappings/station-merge-decisions.md` —— 多线站名的合并/待复核/分裂决策表

合并口径（ADR R4）：
  ≤150 m             → 合并成一站（method=auto_150）
  150 m < 跨度 ≤300 m → 合并，但标 needs_review（method=auto_review）
  >300 m             → 不合并，拆成多个站，并登记 transfer 候选（method=split_review）
站名 + 城市一起作主键：跨城同名不合并（迎春路 86.7 km 的教训）。

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\09_build_stations.py
"""

from __future__ import annotations

import json
import sys
import os
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pypinyin import Style, lazy_pinyin

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
LINES = P.lines_json
RAW = P.raw_transit()
ATTR = P.attribution_report()
OUT = P.station_json
MD = (P.docs_station_merge_md if CFG.code == "sh"
      else P.doc(f"mappings/station-merge-decisions-{CFG.code}.md"))

CITY_DEFAULT = CFG.city

MERGE_M = 150.0      # 合并阈值
REVIEW_M = 300.0     # 超过即不合并

# 人工白名单：同一座车站/枢纽，跨度虽 >300 m 仍并成一站（决策见 docs/split-groups-review.md）
_merge_path = P.manual_city_file("merge.json")
_merge_cfg = json.loads(_merge_path.read_text(encoding="utf-8")) if _merge_path.exists() else {}
FORCE_MERGE = set(_merge_cfg.get("force_merge", []))

# 上海市外的站（当前只有 11 号线花桥支线 3 站），省 → 地级市
PROVINCE_TO_CITY = dict(_merge_cfg.get("province_to_city", {}))


def transfer_names() -> set[str]:
    """换乘站名清单，直接取 11_build_transfers.py 的 GROUP_TYPES，避免两处硬编码漂移。"""
    import importlib.util

    path = Path(__file__).resolve().parent / "11_build_transfers.py"
    spec = importlib.util.spec_from_file_location("build_transfers", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return set(mod.GROUP_TYPES)


# 换乘站名（S6-4 决策 D1：换乘样式 = 多线站 ∪ 有换乘记录的站）
TRANSFER_NAMES = transfer_names()


def hav_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """两点球面距离（米）。a/b = (lon, lat)。"""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def slug(name: str) -> str:
    parts = [p for p in lazy_pinyin(name, style=Style.NORMAL) if p]
    s = "-".join(parts).replace("ü", "v")
    return "".join(ch for ch in s if ch.isalnum() or ch == "-").strip("-") or "station"


def pinyin_tone(name: str) -> str:
    return " ".join(lazy_pinyin(name, style=Style.TONE))


class DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def per_stop_city(attr: dict) -> dict[str, dict[str, str]]:
    """从归属报告的 conflicts 里取「关系 → {站名: 省份}」；没冲突的关系整条属于 relation.city。"""
    out: dict[str, dict[str, str]] = {}
    for c in attr.get("conflicts") or []:
        rel_id = str(c.get("id"))
        mapping: dict[str, str] = {}
        for item in c.get("stops") or []:
            if "→" not in item:
                continue
            name, prov = (s.strip() for s in item.rsplit("→", 1))
            mapping[name] = prov
        out[rel_id] = mapping
    return out


def main() -> int:
    lines_doc = json.loads(LINES.read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    attr = json.loads(ATTR.read_text(encoding="utf-8"))

    rel_by_id = {str(r["id"]): r for r in raw["relations"]}
    attr_by_id = {str(r["id"]): r for r in attr["relations"]}
    conflict_city = per_stop_city(attr)

    errors: list[str] = []
    slots: list[dict] = []

    for ln in lines_doc["lines"]:
        for br in ln["branches"]:
            rel_id = br["relation_ids"]["kept"]
            rec = rel_by_id.get(rel_id)
            if rec is None:
                errors.append(f"{br['id']} 的 kept 关系 {rel_id} 不在 raw 里")
                continue
            # raw 里按成员顺序排好的 stop（只取 stop* 角色）
            raw_stops = [
                s for s in rec.get("stops") or []
                if any(str(r).startswith("stop") for r in (s.get("roles") or []))
            ]
            by_name: dict[str, list[dict]] = defaultdict(list)
            for s in raw_stops:
                by_name[s.get("name")].append(s)

            # lines.json 的站序是权威顺序（环线已旋转），按名字逐个取数
            for seq, name in enumerate(br["stops"], start=1):
                bucket = by_name.get(name)
                if not bucket:
                    errors.append(f"{br['id']} 第 {seq} 站「{name}」在 raw 里没有对应 stop 节点")
                    continue
                s = bucket.pop(0)
                if not s.get("resolved") or s.get("lon") is None:
                    errors.append(f"{br['id']} 第 {seq} 站「{name}」坐标未解析")
                    continue
                city = CITY_DEFAULT
                cmap = conflict_city.get(rel_id) or {}
                if name in cmap:
                    prov = cmap[name]
                    city = PROVINCE_TO_CITY.get(prov, prov)
                slots.append(
                    {
                        "line": ln["id"],
                        "line_name": ln["name"],
                        "branch": br["id"],
                        "seq": seq,
                        "name": name,
                        "name_en": s.get("name_en"),
                        "city": city,
                        "node": s.get("node"),
                        "coord": [round(s["lon"], 6), round(s["lat"], 6)],
                    }
                )

    # ---- 按（站名, 城市）分组，再按距离聚类 ----
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for sl in slots:
        groups[(sl["name"], sl["city"])].append(sl)

    stations: list[dict] = []
    transfer_candidates: list[dict] = []
    decisions: list[dict] = []
    used_ids: dict[str, int] = defaultdict(int)

    for (name, city), members in sorted(groups.items()):
        n = len(members)

        # 先算整体跨度，按 ADR R4 的三档决定怎么并
        spread_all = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                spread_all = max(spread_all, hav_m(members[i]["coord"], members[j]["coord"]))

        if name in FORCE_MERGE and n > 1:
            # 人工白名单优先：同站体跨长途也并成一座车站
            clusters = {0: list(range(n))}
            method, needs_review = "manual_merge", False
        elif spread_all <= MERGE_M:
            clusters = {0: list(range(n))}
            method, needs_review = "auto_150", False
        elif spread_all <= REVIEW_M:
            # 150–300 m：仍然并成一站，但标待复核
            clusters = {0: list(range(n))}
            method, needs_review = "auto_review", True
        else:
            # >300 m：不合并。组内按 150 m 连通分量拆站，并登记换乘候选
            dsu2 = DSU(n)
            for i in range(n):
                for j in range(i + 1, n):
                    if hav_m(members[i]["coord"], members[j]["coord"]) <= MERGE_M:
                        dsu2.union(i, j)
            clusters = defaultdict(list)
            for i in range(n):
                clusters[dsu2.find(i)].append(i)
            method, needs_review = "split_review", True

        made: list[str] = []
        for _, idxs in sorted(clusters.items(), key=lambda kv: min(kv[1])):
            ms = [members[i] for i in sorted(idxs)]
            lon = sum(m["coord"][0] for m in ms) / len(ms)
            lat = sum(m["coord"][1] for m in ms) / len(ms)
            base = slug(name)
            used_ids[base] += 1
            sid = f"{CITY_CODE}-station-{base}" + ("" if used_ids[base] == 1 else f"-{used_ids[base]}")
            lines_set = sorted({m["line"] for m in ms})
            clusters_spread = 0.0
            for a in range(len(ms)):
                for b in range(a + 1, len(ms)):
                    clusters_spread = max(clusters_spread, hav_m(ms[a]["coord"], ms[b]["coord"]))
            stations.append(
                {
                    "id": sid,
                    "name": name,
                    "name_en": next((m["name_en"] for m in ms if m.get("name_en")), None),
                    "name_pinyin": pinyin_tone(name),
                    "city": city,
                    "coord": [round(lon, 6), round(lat, 6)],
                    "lines": lines_set,
                    "branches": sorted({m["branch"] for m in ms}),
                    "is_transfer": len(lines_set) >= 2 or name in TRANSFER_NAMES,
                    "slots": [
                        {
                            "line": m["line"],
                            "branch": m["branch"],
                            "seq": m["seq"],
                            "node": m["node"],
                            "coord": m["coord"],
                        }
                        for m in ms
                    ],
                    "merge": {
                        "method": method,
                        "slot_count": len(ms),
                        "spread_m": round(clusters_spread, 1),
                        "needs_review": needs_review,
                    },
                    "source": "OpenStreetMap（省级 PBF）",
                    "source_license": "ODbL-1.0",
                    "as_of": lines_doc["snapshot_date"],
                }
            )
            made.append(sid)

        if len(made) > 1:
            for a in range(len(made)):
                for b in range(a + 1, len(made)):
                    sa = next(s for s in stations if s["id"] == made[a])
                    sb = next(s for s in stations if s["id"] == made[b])
                    transfer_candidates.append(
                        {
                            "station_a": sa["id"],
                            "station_b": sb["id"],
                            "name": name,
                            "dist_m": round(hav_m(sa["coord"], sb["coord"]), 1),
                            "reason": "同名但站距 >300 m，ADR R4 判为不合并，候选换乘",
                        }
                    )
        if n > 1:
            decisions.append(
                {
                    "name": name,
                    "city": city,
                    "slots": n,
                    "stations": len(made),
                    "spread_m": round(spread_all, 1),
                    "method": method,
                    "needs_review": needs_review,
                    "lines": sorted({m["line_name"] for m in members}),
                }
            )

    # ---- 校验 ----
    if len(slots) != sum(b["stop_count"] for ln in lines_doc["lines"] for b in ln["branches"]):
        errors.append("slot 数与 lines.json 的站次总数不符")
    assigned = sum(len(s["slots"]) for s in stations)
    if assigned != len(slots):
        errors.append(f"slot 分配不完整：{assigned}/{len(slots)}")
    empty = [s["id"] for s in stations if not s["slots"]]
    if empty:
        errors.append(f"有站没有 slot：{empty[:3]}")
    for s in stations:
        if not s["coord"][0] or not s["coord"][1]:
            errors.append(f"{s['id']} 坐标为空")

    out = {
        "city": CITY_DEFAULT,
        "city_code": CITY_CODE,
        "snapshot_date": lines_doc["snapshot_date"],
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rules": "docs/decisions/0001-modeling-rules.md（R4 车站合并、R2 ID）",
        "merge_policy": {
            "merge_m": MERGE_M,
            "review_m": REVIEW_M,
            "note": "站名 + 城市为主键；跨城同名不合并；>300 m 默认不合并改走 transfer；人工白名单（FORCE_MERGE）强制并站",
            "force_merge": sorted(FORCE_MERGE),
            "is_transfer_rule": "多线站 ∪ 有换乘记录的站（站名命中 11_build_transfers.py 的 GROUP_TYPES）",
        },
        "counts": {
            "stations": len(stations),
            "slots": len(slots),
            "transfer_style_stations": sum(1 for s in stations if s["is_transfer"]),
            "multi_line_stations": sum(1 for s in stations if len(s["lines"]) > 1),
            "needs_review": sum(1 for s in stations if s["merge"]["needs_review"]),
            "split_groups": sum(1 for d in decisions if d["stations"] > 1),
            "transfer_candidates": len(transfer_candidates),
            "name_groups_multi": len(decisions),
        },
        "transfer_candidates": sorted(transfer_candidates, key=lambda x: -x["dist_m"]),
        "stations": sorted(stations, key=lambda s: s["id"]),
    }

    # ---- 报表 ----
    c = out["counts"]
    print(
        f"站点 {c['stations']}｜slot {c['slots']}｜多线站 {c['multi_line_stations']}｜"
        f"待复核 {c['needs_review']}｜分裂组 {c['split_groups']}｜换乘候选 {c['transfer_candidates']}"
    )
    print()
    print("站名出现 ≥2 次的组：")
    print(f"{'站名':<14}{'城市':<8}{'slot':>5}{'站数':>5}{'跨度 m':>9}  {'口径':<14}换乘")
    for d in sorted(decisions, key=lambda x: -x["spread_m"]):
        print(
            f"{d['name']:<14}{d['city']:<8}{d['slots']:>5}{d['stations']:>5}{d['spread_m']:>9.1f}  "
            f"{d['method']:<14}{'是' if d['needs_review'] else '否'}"
        )

    if errors:
        print()
        print(f"[失败] {len(errors)} 项：")
        for e in errors[:20]:
            print(f"  - {e}")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- Markdown 决策表 ----
    lines_md = [
        "# 站点合并决策表（S2-3）",
        "",
        "> 由 `pipeline/09_build_stations.py` 从 `station.json` 渲染，**请勿手改**。",
        "",
        "## 口径（ADR R4）",
        "",
        f"- 合并阈值 **{MERGE_M:.0f} m**；跨度 **{MERGE_M:.0f}–{REVIEW_M:.0f} m** 合并但标 `needs_review`；**>{REVIEW_M:.0f} m** 不合并，拆站并登记换乘候选。",
        "- 主键是「站名 + 城市」，跨城同名一律不合并。",
        "",
        "## 统计",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        f"| 站点总数 | {c['stations']} |",
        f"| slot（线路×站次） | {c['slots']} |",
        f"| 多线站 | {c['multi_line_stations']} |",
        f"| 待复核站 | {c['needs_review']} |",
        f"| 同名分裂组 | {c['split_groups']} |",
        f"| 换乘候选 | {c['transfer_candidates']} |",
        "",
        "## 同名多站名的判定",
        "",
        "| 站名 | 城市 | slot | 合并后站数 | 最大跨度 (m) | 口径 | 待复核 | 涉及线路 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for d in sorted(decisions, key=lambda x: (-x["spread_m"])):
        lines_md.append(
            f"| {d['name']} | {d['city']} | {d['slots']} | {d['stations']} | {d['spread_m']:.1f} | "
            f"`{d['method']}` | {'是' if d['needs_review'] else '否'} | {'、'.join(d['lines'])} |"
        )
    lines_md += ["", "## 换乘候选（同名但未合并）", "", "| 站 A | 站 B | 距离 (m) | 理由 |", "| --- | --- | --- | --- |"]
    for t in out["transfer_candidates"]:
        lines_md.append(f"| `{t['station_a']}` | `{t['station_b']}` | {t['dist_m']:.1f} | {t['reason']} |")
    MD.parent.mkdir(parents=True, exist_ok=True)
    MD.write_text("\n".join(lines_md) + "\n", encoding="utf-8")

    print()
    print(f"写出 {OUT.relative_to(REPO)}（{OUT.stat().st_size:,} B）与 {MD.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
