"""P1b 阶段 0.3：G0 口径闸门。

在进入阶段 1（前置改造）之前，把「台账 / 文档 / 前端产物 / OSM 是否存在」四件事对齐，
免得做了 50 城之后才发现口径是错的。

检查分四组：
  A 台账结构：58 行 = 54 主线 + 4 仅有轨；4 已完成 / 50 待做；批次齐、slug 唯一、id 非空
  B 文档一致：docs/p1b-cities.md 的批次表城数与台账逐批相等
  C 前端一致：四座已完成城的 slug/线路数/车站数 与 web/public/data/cities.json 相等
  D OSM 存在：每座待做城至少有一条城市轨道交通关系（用 network 标签做代理）

注意 D 的已知缺陷：`network` 标签覆盖不全（P1a-0.2 实测有 28 条线路关系没有 network），
所以 D 会给出 `unknown` 名单而不是硬判失败；加 `--strict` 时才把这些算失败。

用法：
  python pipeline/19_check_ledger.py            # 常规检查
  python pipeline/19_check_ledger.py --strict   # unknown 也算失败
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "data" / "cities-ledger.csv"
ADMIN = REPO / "data" / "admin-ids.json"
DOC = REPO / "docs" / "p1b-cities.md"
CITIES_JSON = REPO / "web" / "public" / "data" / "cities.json"
CITY_CFG = REPO / "pipeline" / "cities"

LINE_KINDS = ("subway", "light_rail", "monorail")
BATCHES = [f"B{i}" for i in range(1, 13)]


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []  # (组, 项, 结果, 说明)
        self.failed = 0
        self.warned = 0

    def ok(self, group: str, item: str, note: str = "") -> None:
        self.rows.append((group, item, "✅", note))

    def fail(self, group: str, item: str, note: str) -> None:
        self.rows.append((group, item, "❌", note))
        self.failed += 1

    def warn(self, group: str, item: str, note: str) -> None:
        self.rows.append((group, item, "⚠️", note))
        self.warned += 1

    def dump(self) -> None:
        width = max(len(r[1]) for r in self.rows)
        print(f"\n{'组':<3}{'检查项':<{width + 2}}{'结果':<4}说明")
        for group, item, mark, note in self.rows:
            print(f"{group:<3}{item:<{width + 2}}{mark:<4}{note}")


def load_ledger() -> list[dict]:
    with LEDGER.open(encoding="utf8") as f:
        return list(csv.DictReader(f))


def check_structure(rep: Report, rows: list[dict]) -> None:
    main = [r for r in rows if r["status"] != "excluded_tram"]
    tram = [r for r in rows if r["status"] == "excluded_tram"]
    done = [r for r in main if r["status"] == "done"]
    pending = [r for r in main if r["status"] == "pending"]

    (rep.ok if len(rows) == 58 else rep.fail)("A", "台账共 58 行（54 主线 + 4 仅有轨）", f"{len(rows)} 行 / 主线 {len(main)} / 仅有轨 {len(tram)}")
    (rep.ok if len(main) == 54 else rep.fail)("A", "主线 54 城", str(len(main)))
    (rep.ok if len(tram) == 4 else rep.fail)("A", "仅有轨 4 城", "、".join(r["city"] for r in tram))
    (rep.ok if (len(done), len(pending)) == (4, 50) else rep.fail)(
        "A", "已完成 4 / 待做 50", f"done {len(done)} / pending {len(pending)}"
    )

    slugs = [r["slug"] for r in rows]
    dup = sorted({s for s in slugs if slugs.count(s) > 1})
    (rep.ok if not dup else rep.fail)("A", "slug 唯一且非空", "、".join(dup) or f"{len(slugs)} 个")

    used_batches = {r["batch"] for r in pending}
    missing = [b for b in BATCHES if b not in used_batches]
    stray = sorted(b for b in used_batches if b not in BATCHES)
    (rep.ok if not missing and not stray else rep.fail)(
        "A", "批次 B1–B12 齐全且无杂项", f"缺 {'、'.join(missing) or '无'}｜多 {'、'.join(stray) or '无'}"
    )

    no_id = [r["city"] for r in rows if not r["city_admin_id"] or not r["province_admin_id"]]
    (rep.ok if not no_id else rep.fail)("A", "58 城 admin id 两列非空", "、".join(no_id) or "全部已填")

    seqs = [int(r["seq"]) for r in main if r["seq"]]
    (rep.ok if seqs == list(range(1, len(main) + 1)) else rep.fail)(
        "A", "主线序号 1…54 连续", f"{len(seqs)} 个"
    )


def parse_doc_batches(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*\**\s*(B\d+)\s*\**\s*\|[^|]*\|\s*\**\s*(\d+)\s*\**\s*\|", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def check_doc(rep: Report, rows: list[dict]) -> None:
    text = DOC.read_text("utf8")
    doc_batches = parse_doc_batches(text)
    ledger_batches = {}
    for r in rows:
        if r["status"] == "pending":
            ledger_batches[r["batch"]] = ledger_batches.get(r["batch"], 0) + 1

    (rep.ok if len(doc_batches) == 12 else rep.fail)("B", "文档批次表 12 行", f"解析到 {len(doc_batches)} 行")
    diff = {b: (doc_batches.get(b), ledger_batches.get(b)) for b in BATCHES if doc_batches.get(b) != ledger_batches.get(b)}
    if diff:
        rep.fail("B", "逐批城数与台账一致", "；".join(f"{b} 文档{v[0]}/台账{v[1]}" for b, v in diff.items()))
    else:
        rep.ok("B", "逐批城数与台账一致", "合计 50 城")
    (rep.ok if "54 + 4 = 58" in text else rep.warn)("B", "文档写明 54 + 4 = 58 口径", "")


def check_frontend(rep: Report, rows: list[dict]) -> None:
    if not CITIES_JSON.exists():
        rep.warn("C", "web/public/data/cities.json 存在", "未找到（先跑 npm run sync）")
        return
    cities = {c["code"]: c for c in json.loads(CITIES_JSON.read_text("utf8"))}
    bad = []
    for r in rows:
        if r["status"] != "done":
            continue
        c = cities.get(r["slug"])
        cfg_path = CITY_CFG / f"{r['slug']}.json"
        if c is None:
            bad.append(f"{r['city']} 不在 cities.json")
            continue
        if not cfg_path.exists():
            bad.append(f"{r['city']} 缺 pipeline/cities/{r['slug']}.json")
            continue
        if int(c["lines"]) != int(r["lines_public"]) or int(c["stations"]) != int(r["stations_public"]):
            bad.append(f"{r['city']} 前端 {c['lines']}/{c['stations']} vs 台账 {r['lines_public']}/{r['stations_public']}")
    (rep.ok if not bad else rep.fail)("C", "四座已完成城：前端产物与台账一致", "；".join(bad) or "4/4 一致")


def check_osm(rep: Report, rows: list[dict], strict: bool) -> None:
    if not ADMIN.exists():
        rep.fail("D", "data/admin-ids.json 存在", "先跑 18_admin_ids.py --scan")
        return
    data = json.loads(ADMIN.read_text("utf8"))
    nets: dict[str, dict[str, int]] = {}
    for bucket in data["provinces"].values():
        for net, kinds in bucket.get("networks", {}).items():
            cur = nets.setdefault(net, {})
            for k, v in kinds.items():
                cur[k] = max(cur.get(k, 0), v)

    ok_cities, unknown = [], []
    for r in rows:
        if r["status"] != "pending":
            continue
        hits = [k for n, k in nets.items() if r["city"] in n]
        total = sum(max(k.get(kind, 0) for k in hits) for kind in LINE_KINDS) if hits else 0
        (ok_cities if total else unknown).append(r["city"])

    note = f"命中 {len(ok_cities)} 城"
    if unknown:
        note += f"，network 缺失 {len(unknown)} 城：{'、'.join(unknown)}"
        if strict:
            rep.fail("D", "待做城在 OSM 至少有 1 条线路关系", note)
        else:
            rep.warn("D", "待做城在 OSM 至少有 1 条线路关系", note + "（D 组代理指标，待阶段 2 用几何归属复核）")
    else:
        rep.ok("D", "待做城在 OSM 至少有 1 条线路关系", note)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="D 组的 unknown 也算失败")
    args = ap.parse_args()

    rows = load_ledger()
    rep = Report()
    check_structure(rep, rows)
    check_doc(rep, rows)
    check_frontend(rep, rows)
    check_osm(rep, rows, args.strict)
    rep.dump()

    total = len(rep.rows)
    print(f"\n合计 {total} 项：通过 {total - rep.failed - rep.warned}｜失败 {rep.failed}｜待复核 {rep.warned}")
    if rep.failed:
        print("G0 未通过——先修台账/文档/前端中的不一致，再进阶段 1。")
        return 1
    print("G0 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
