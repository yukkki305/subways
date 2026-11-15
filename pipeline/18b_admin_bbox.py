"""P1b 阶段 0.4：给每个省 / 地级市面补一个 bbox。

为什么需要它：`21_gen_city_configs.py` 要一次性生成 50 座城的配置骨架，而配置里的
`bbox` / `scene_bbox` 现在只能靠人眼看地图估。估小了会漏站（02 按 bbox 过滤 stop），
估大了会把邻市线路吃进来。

为什么不在 18_admin_ids.py 里顺手做：pyosmium 的 `RelationMember` 在 `SimpleHandler`
里**没有 `.way` 属性**（实测 AttributeError），要拿成员 way 的坐标只能两遍扫：
  第一遍（只读 tags，快）：关系 id → 成员 way id 集合
  第二遍（`locations=True`）：只算这些 way 的节点包围盒
两遍加起来 1.74 GB 约 5 分钟，所以单独成一个脚本，结果合并回 `data/admin-ids.json`
（给每个 l4 / l5 条目加 `bbox: [w, s, e, n]`），可重跑、幂等。

用法：
  python pipeline/18b_admin_bbox.py            # 全部 28 省
  python pipeline/18b_admin_bbox.py --only hainan jiangsu   # 只算几个（调试用）
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import osmium

REPO = Path(__file__).resolve().parent.parent
SNAP = Path(r"E:\subway-data\snapshots\p1b-20261113")
ADMIN = REPO / "data" / "admin-ids.json"

LEVELS = ("4", "5")


class MemberScan(osmium.SimpleHandler):
    """第一遍：关系 id → 成员 way id（只要 tags，不要坐标）。"""

    def __init__(self) -> None:
        super().__init__()
        self.ways: dict[int, list[int]] = {}
        self.tags: dict[int, dict] = {}

    def relation(self, rel) -> None:  # noqa: ANN001
        tags = rel.tags
        if tags.get("boundary") != "administrative":
            return
        if tags.get("admin_level", "") not in LEVELS:
            return
        self.ways[rel.id] = [m.ref for m in rel.members if m.type == "w"]
        self.tags[rel.id] = {
            "name": tags.get("name", ""),
            "level": int(tags["admin_level"]),
        }


class WayBBoxScan(osmium.SimpleHandler):
    """第二遍：只算 wanted 里那些 way 的节点包围盒。"""

    def __init__(self, wanted: set[int]) -> None:
        super().__init__()
        self.wanted = wanted
        self.box: dict[int, tuple[float, float, float, float]] = {}

    def node(self, node) -> None:  # noqa: ANN001
        # 必须有 node() 回调，pyosmium 才会读节点并建位置索引；
        # 否则 `w.nodes` 拿不到坐标（这一条踩了我一小时）。
        pass

    def way(self, way) -> None:  # noqa: ANN001
        if way.id not in self.wanted:
            return
        w = s = 200.0
        e = n = -200.0
        for nd in way.nodes:
            # 省级 extract 是按边界裁的：跨界的 way 会引用文件里没有的节点，
            # 取坐标时抛 InvalidLocationError。逐节点 try，不要放弃整条 way。
            try:
                lon, lat = nd.lon, nd.lat
            except osmium.InvalidLocationError:
                continue
            if lon < -180 or lat < -90:  # 缺失坐标
                continue
            if lon < w:
                w = lon
            if lon > e:
                e = lon
            if lat < s:
                s = lat
            if lat > n:
                n = lat
        if w < 200:
            self.box[way.id] = (w, s, e, n)


def merge_box(boxes: list[tuple[float, float, float, float]]):
    if not boxes:
        return None
    w = min(b[0] for b in boxes)
    s = min(b[1] for b in boxes)
    e = max(b[2] for b in boxes)
    n = max(b[3] for b in boxes)
    return [round(w, 4), round(s, 4), round(e, 4), round(n, 4)]


def run(only: list[str] | None) -> None:
    data = json.loads(ADMIN.read_text("utf8"))
    pbfs = sorted(SNAP.glob("*-latest.osm.pbf"))
    if only:
        pbfs = [p for p in pbfs if p.name.removesuffix("-latest.osm.pbf") in set(only)]

    total_t = time.time()
    for pbf in pbfs:
        key = pbf.name.removesuffix("-latest.osm.pbf")
        if key not in data["provinces"]:
            print(f"[skip] {key} 不在 admin-ids.json 里")
            continue
        t0 = time.time()
        scan1 = MemberScan()
        scan1.apply_file(str(pbf))
        wanted = {wid for ids in scan1.ways.values() for wid in ids}
        scan2 = WayBBoxScan(wanted)
        scan2.apply_file(str(pbf), locations=True, idx="flex_mem")

        by_level: dict[str, list[dict]] = defaultdict(list)
        for rid, ids in scan1.ways.items():
            box = merge_box([scan2.box[i] for i in ids if i in scan2.box])
            meta = scan1.tags[rid]
            by_level[str(meta["level"])].append({"id": rid, "name": meta["name"], "bbox": box})
        # 把 bbox 合并回 admin-ids.json 的 l4 / l5 条目
        for level_key, level in (("l4", "4"), ("l5", "5")):
            boxes = {item["id"]: item["bbox"] for item in by_level.get(level, [])}
            hit = 0
            for entry in data["provinces"][key][level_key]:
                box = boxes.get(entry["id"])
                if box:
                    entry["bbox"] = box
                    hit += 1
            print(
                f"{key:<16} {level_key} {hit:4d}/{len(data['provinces'][key][level_key]):4d} 有 bbox"
                f"  way {len(wanted):6d}  耗时 {time.time() - t0:5.1f}s",
                flush=True,
            )
        # 每个省跑完就落盘：28 省要十几分钟，中途挂掉不该白跑
        ADMIN.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf8")

    print(f"写入 {ADMIN.relative_to(REPO)}，总耗时 {time.time() - total_t:.0f}s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="只处理这些 extract 名")
    args = ap.parse_args()
    run(args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
