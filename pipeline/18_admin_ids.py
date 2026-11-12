"""P1b 阶段 0.2：从省级 PBF 里取行政区关系 id，回填城市台账。

做三件事：
1. 每个省的 PBF 扫一遍关系，收 `boundary=administrative` 且 `admin_level in {4,6}` 的
   省面与市面（只要 tags，不需要几何，所以不申请 location 索引，速度快）。
2. 顺带统计每个省的城市轨道交通关系数（route 在 subway / light_rail / monorail /
   tram / train 里），用来验证「关系数可以预判工作量」这个假设。
3. 用台账里的城市名匹配市面（直辖市匹配省面），把 id 写回 `data/cities-ledger.csv`
   的两列；匹配不到的留在 `data/admin-ids.json` 的 `unmatched` 里，人工处理。

用法：
  python 18_admin_ids.py --scan           # 扫 PBF，写 data/admin-ids.json
  python 18_admin_ids.py --fill           # 只按已存在的 admin-ids.json 回填台账
  python 18_admin_ids.py                  # 两步都做
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import osmium

REPO = Path(__file__).resolve().parent.parent
SNAP = Path(r"E:\subway-data\snapshots\p1b-20261113")
OUT_JSON = REPO / "data" / "admin-ids.json"
LEDGER = REPO / "data" / "cities-ledger.csv"

ROUTE_KINDS = {"subway", "light_rail", "monorail", "tram", "train"}
LEVELS = {"4", "5"}


class AdminScan(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.admins: list[dict] = []
        self.route_counts: Counter[str] = Counter()
        # 按 network 标签计数：多数中国城市轨道交通关系带 network="XX地铁"，
        # 用它可以在不读几何的前提下粗估「每城有多少条线路关系」。
        self.network_counts: Counter[tuple[str, str]] = Counter()

    def relation(self, rel) -> None:  # noqa: ANN001 - pyosmium 传入对象
        tags = rel.tags
        if tags.get("type") == "route":
            route = tags.get("route", "")
            if route in ROUTE_KINDS:
                self.route_counts[route] += 1
                network = tags.get("network", "") or "(无 network)"
                self.network_counts[(network, route)] += 1
            return
        if tags.get("boundary") != "administrative":
            return
        level = tags.get("admin_level", "")
        if level not in LEVELS:
            return
        self.admins.append(
            {
                "id": rel.id,
                "level": int(level),
                "name": tags.get("name", ""),
                "name_zh": tags.get("name:zh", ""),
                "name_en": tags.get("name:en", ""),
            }
        )


def scan() -> dict:
    provinces = sorted(SNAP.glob("*-latest.osm.pbf"))
    if not provinces:
        raise SystemExit(f"没找到 PBF：{SNAP}")

    out: dict = {"snapshot": SNAP.name, "provinces": {}, "generated_from": "18_admin_ids.py"}
    for pbf in provinces:
        prov = pbf.name.removesuffix("-latest.osm.pbf")
        scanr = AdminScan()
        scanr.apply_file(str(pbf), locations=False)
        provinces_l4 = [a for a in scanr.admins if a["level"] == 4]
        cities_l5 = [a for a in scanr.admins if a["level"] == 5]
        # network → {route_kind: n}
        nets: dict[str, dict[str, int]] = defaultdict(dict)
        for (net, kind), n in scanr.network_counts.items():
            nets[net][kind] = n
        out["provinces"][prov] = {
            "l4": sorted(provinces_l4, key=lambda a: a["name"]),
            "l5": sorted(cities_l5, key=lambda a: a["name"]),
            "routes": dict(sorted(scanr.route_counts.items(), key=lambda kv: -kv[1])),
            "networks": dict(sorted(nets.items(), key=lambda kv: -sum(kv[1].values()))),
        }
        print(
            f"{prov:<16} L4 {len(provinces_l4):3d}  L5 {len(cities_l5):4d}  "
            f"线路关系 {sum(scanr.route_counts.values()):4d}  {dict(scanr.route_counts)}",
            flush=True,
        )

    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf8")
    print(f"写入 {OUT_JSON.relative_to(REPO)}")
    return out


def norm(name: str) -> str:
    """去掉行政后缀，便于和台账里的「南京」「苏州」对上。"""
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "市", "盟", "县"):
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            name = name[: -len(suffix)]
    return name


def fill() -> None:
    data = json.loads(OUT_JSON.read_text("utf8"))
    # 全局索引：name / name:zh 的主名 → (province_file, id)
    index: dict[tuple[str, int], tuple[str, int]] = {}
    prov_ids: dict[str, int] = {}
    for prov, bucket in data["provinces"].items():
        for level_key, level in (("l4", 4), ("l5", 5)):
            for a in bucket[level_key]:
                for cand in {a["name"], a.get("name_zh", "")}:
                    if not cand:
                        continue
                    index.setdefault((norm(cand), level), (prov, a["id"]))
        for a in bucket["l4"]:
            # 部分省面名称带民族文字后缀（如「新疆维吾尔自治区 شىنجاڭ…」），
            # 所以按前缀建索引，而不是精确名。
            for key in {a["name"], a.get("name_zh", "")}:
                if key:
                    prov_ids.setdefault(key.split(" ")[0], a["id"])

    rows = list(csv.DictReader(LEDGER.open(encoding="utf8")))
    unmatched: list[str] = []
    for row in rows:
        row["city_admin_id"] = ""
        row["province_admin_id"] = str(prov_ids.get(row["province"], "") or "")
        city = row["city"]
        hit = index.get((city, 5)) or index.get((city, 4))
        if hit is None:
            # 少数民族自治州/带后缀的市面名：按前缀找，优先级别更高（5）且名字最短
            cands = sorted(
                ((k, v) for k, v in index.items() if k[0].startswith(city) and k[1] in (5, 4)),
                key=lambda kv: (kv[0][1] != 5, len(kv[0][0])),
            )
            if cands:
                hit = cands[0][1]
        if hit is None:
            unmatched.append(city)
            continue
        row["city_admin_id"] = str(hit[1])

    with LEDGER.open("w", encoding="utf8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    filled = sum(1 for r in rows if r["city_admin_id"])
    print(f"回填 city_admin_id：{filled}/{len(rows)}；未匹配 {len(unmatched)} 个：{'、'.join(unmatched) or '无'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--fill", action="store_true")
    args = ap.parse_args()
    do_scan = args.scan or not (args.scan or args.fill)
    do_fill = args.fill or not (args.scan or args.fill)
    if do_scan:
        scan()
    if do_fill and OUT_JSON.exists():
        fill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
