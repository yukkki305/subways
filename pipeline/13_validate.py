# -*- coding: utf-8 -*-
"""S2-7 校验：执行 ADR R8 的八项硬校验

用法：
    python pipeline/13_validate.py            # 跑 1–7 项（纯校验，秒级）
    python pipeline/13_validate.py --rerun    # 追加第 8 项（重跑 S2-2～S2-6 比对确定性，约 2–3 分钟）

任一不过即停（退出码非 0）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyproj import Geod

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
PY = sys.executable
LINES = P.lines_json
STATIONS = P.station_json
SEGMENTS = P.segment_geojson
TRANSFERS = P.transfer_json
DOC = (P.doc("validation-s2.md") if CFG.code == "sh"
       else P.doc(f"validation-s2-{CFG.code}.md"))   # 每城一份，避免覆盖上海

BBOX = CFG.bbox_tuple                        # 采集矩形框（config 的 bbox）
EXPECTED_LINES = len(CFG.line_ids)            # 该城应有线路数（来自城市配置）
WHITELIST = set(CFG.stop_bbox_whitelist)    # 允许落在 bbox 外的站（跨省延伸段）
HEX = re.compile(r"^#[0-9A-F]{6}$")
GEOD = Geod(ellps="WGS84")


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


class Report:
    def __init__(self):
        self.rows = []
        self.failed = 0

    def add(self, no, name, ok, detail):
        self.rows.append((no, name, ok, detail))
        if not ok:
            self.failed += 1
        print(f"[{'通过' if ok else '失败'}] {no}. {name} —— {detail}")

    def markdown(self, extra_lines):
        out = ["# S2 校验报告（ADR R8 八项）", "",
               f"> 由 `pipeline/13_validate.py` 生成，{datetime.now().astimezone().isoformat(timespec='seconds')}",
               "", "| # | 校验项 | 结果 | 实测 |", "| --- | --- | --- | --- |"]
        for no, name, ok, detail in self.rows:
            out.append(f"| {no} | {name} | {'✅ 通过' if ok else '❌ 失败'} | {detail} |")
        out += ["", "## 口径与已知缺口", ""] + extra_lines
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text("\n".join(out) + "\n", encoding="utf-8")


def check_1(lines, rep):
    ls = lines["lines"]
    ok = len(ls) == EXPECTED_LINES
    bad = [l["id"] for l in ls if l.get("stop_count_total", 0) < 2]
    mains = {l["id"]: [b["id"] for b in l["branches"] if b["is_main"]] for l in ls}
    bad_main = {k: v for k, v in mains.items() if len(v) != 1}
    ok = ok and not bad and not bad_main
    rep.add(1, "line 数 / 站数 / 每线唯一 main",
            ok, f"line={len(ls)}（应为 {EXPECTED_LINES}）；站数<2 的 {len(bad)} 条；main 不唯一的 {len(bad_main)} 条")
    return ok


def check_2(stations, rep):
    bad = []
    for s in stations["stations"]:
        lon, lat = s["coord"]
        inside = BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]
        if not inside and s["name"] not in WHITELIST:
            bad.append((s["id"], s["name"], s["coord"]))
    rep.add(2, f"站坐标在{CFG.name}采集框内或命中白名单", not bad,
            f"越界且不在白名单 {len(bad)} 个{('：' + str(bad[:3])) if bad else ''}")
    return not bad


def check_3(stations, lines, rep):
    line_ids = {l["id"] for l in lines["lines"]}
    empty = [s["id"] for s in stations["stations"] if not s.get("lines")]
    dangling = [(s["id"], x) for s in stations["stations"] for x in s.get("lines", []) if x not in line_ids]
    ok = not empty and not dangling
    rep.add(3, "每站 lines[] 非空且引用有效", ok,
            f"lines 为空的 {len(empty)} 个；悬空引用 {len(dangling)} 处")
    return ok


def check_4(lines, segs, rep):
    """ADR R8-4：环线段数 = 站数且首尾相接（stops 不重复首站，靠闭合段回环）；
    非环线段数 = 站数 − 1。"""
    by_branch: dict[str, list] = {}
    for f in segs["features"]:
        by_branch.setdefault(f["properties"]["branch_id"], []).append(f)
    bad = []
    for l in lines["lines"]:
        for b in l["branches"]:
            feats = sorted(by_branch.get(b["id"], []), key=lambda f: f["properties"]["seq"])
            n_stop = b["stop_count"]
            if b["is_loop"]:
                if len(feats) != n_stop:
                    bad.append((b["id"], f"环线 段数={len(feats)} 期望={n_stop}"))
                    continue
                first, last = feats[0]["properties"], feats[-1]["properties"]
                if first["from_station"] != last["to_station"]:
                    bad.append((b["id"], f"环线未闭合 {first['from_station']} != {last['to_station']}"))
                if not last["is_loop_close"]:
                    bad.append((b["id"], "末段未标 is_loop_close"))
            else:
                if len(feats) != n_stop - 1:
                    bad.append((b["id"], f"段数={len(feats)} 期望={n_stop - 1}"))
    rep.add(4, "环线：段数=站数且首尾闭合；非环线：段数=站数−1", not bad,
            f"{sum(len(l['branches']) for l in lines['lines'])} 条 branch 逐条核对，不符 {len(bad)} 条" + (f"：{bad[:3]}" if bad else ""))
    return not bad


def check_5(stations, segs, lines, rep):
    """ADR R2：segment 用 station id 引用两端；两端在同一 branch 的 seq 必须相邻。"""
    by_station = {s["id"]: s for s in stations["stations"]}
    stop_count = {b["id"]: b["stop_count"] for l in lines["lines"] for b in l["branches"]}
    seq_of: dict[tuple[str, str], int] = {}
    for s in stations["stations"]:
        for slot in s["slots"]:
            seq_of[(slot["branch"], s["id"])] = slot["seq"]
    bad = []
    for f in segs["features"]:
        p = f["properties"]
        a, b = p["from_station"], p["to_station"]
        if a not in by_station or b not in by_station:
            bad.append((p["id"], "站点不存在", a, b))
            continue
        sa, sb = seq_of.get((p["branch_id"], a)), seq_of.get((p["branch_id"], b))
        if sa is None or sb is None:
            bad.append((p["id"], "缺该 branch 的 slot", a, b))
        elif a == b:
            if sa != sb:
                bad.append((p["id"], "闭合段两端应为同一站次", sa, sb))
        elif abs(sa - sb) != 1:
            # 环线闭合段：末站次 → 首站次，属正常回环
            n = stop_count.get(p["branch_id"])
            if p.get("is_loop_close") and n and sa == n and sb == 1:
                continue
            bad.append((p["id"], f"站序差 {abs(sa - sb)}", a, b))
    rep.add(5, "segment 两端站点存在、站序相邻（环线闭合段除外）", not bad,
            f"{len(segs['features'])} 段逐段核对，不符 {len(bad)} 段" + (f"：{bad[:3]}" if bad else ""))
    return not bad


def check_6(stations, transfers, rep):
    by_id = {s["id"]: s for s in stations["stations"]}
    pairs = {}
    bad = []
    for t in transfers["transfers"]:
        a, b = t["station_a"], t["station_b"]
        if a not in by_id or b not in by_id:
            bad.append((t["id"], "站点不存在"))
            continue
        key = tuple(sorted((a, b)))
        if key in pairs:
            bad.append((t["id"], "重复的对（应双向合一）"))
        pairs[key] = t
        lon1, lat1 = by_id[a]["coord"]
        lon2, lat2 = by_id[b]["coord"]
        _, _, d = GEOD.inv(lon1, lat1, lon2, lat2)
        if abs(d - t["dist_m"]) > 1.0:
            bad.append((t["id"], f"站距不符 {d:.1f} vs {t['dist_m']}"))
        if t["walk_minutes"] is not None:
            bad.append((t["id"], "walk_minutes 应为 null"))
        if not (t.get("type_note") and t.get("type_confidence")):
            bad.append((t["id"], "缺 type_confidence/type_note"))
    rep.add(6, "transfer 成对、站距与坐标一致、类型证据齐全", not bad,
            f"{len(transfers['transfers'])} 条换乘核对，问题 {len(bad)} 处" + (f"：{bad[:3]}" if bad else ""))
    return not bad


def check_7(lines, stations, rep):
    bad = []
    for l in lines["lines"]:
        if not HEX.match(l.get("colour") or ""):
            bad.append((l["id"], f"color={l.get('colour')}"))
    for s in stations["stations"]:
        if not (s.get("name_pinyin") or "").strip():
            bad.append((s["id"], "name_pinyin 为空"))
    rep.add(7, "颜色为 #RRGGBB、站名拼音非空", not bad,
            f"{len(lines['lines'])} 条线路 + {len(stations['stations'])} 站核对，问题 {len(bad)} 处" + (f"：{bad[:3]}" if bad else ""))
    return not bad


def strip_ts(obj):
    """去掉时间戳类字段，用于确定性比对。"""
    if isinstance(obj, dict):
        return {k: strip_ts(v) for k, v in obj.items()
                if k not in ("generated_at", "attribution_generated_at", "generated")}
    if isinstance(obj, list):
        return [strip_ts(x) for x in obj]
    return obj


def check_8(rep):
    """重跑 S2-2～S2-6 的生成脚本，比对除时间戳外的内容。"""
    products = {"lines.json": LINES, "station.json": STATIONS,
                "segment.geojson": SEGMENTS, "transfer.json": TRANSFERS}
    before = {k: strip_ts(load(p)) for k, p in products.items()}
    scripts = ["08_build_lines.py", "09_build_stations.py", "10_build_segments.py",
               "11_build_transfers.py", "12_build_attributes.py"]
    for sc in scripts:
        r = subprocess.run([PY, str(REPO / "pipeline" / sc)], cwd=str(REPO),
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            rep.add(8, "两次运行产物一致（除时间戳）", False, f"{sc} 重跑失败：{(r.stderr or '')[-300:]}")
            return False
    after = {k: strip_ts(load(p)) for k, p in products.items()}
    diff = [k for k in products if json.dumps(before[k], sort_keys=True, ensure_ascii=False)
            != json.dumps(after[k], sort_keys=True, ensure_ascii=False)]
    rep.add(8, "两次运行产物一致（除时间戳）", not diff,
            f"重跑 5 个脚本后比对 4 份产物，差异 {len(diff)} 份{'：' + str(diff) if diff else ''}")
    return not diff


def main() -> int:
    lines, stations, segs, transfers = load(LINES), load(STATIONS), load(SEGMENTS), load(TRANSFERS)
    rep = Report()
    check_1(lines, rep)
    check_2(stations, rep)
    check_3(stations, lines, rep)
    check_4(lines, segs, rep)
    check_5(stations, segs, lines, rep)
    check_6(stations, transfers, rep)
    check_7(lines, stations, rep)
    if "--rerun" in sys.argv:
        check_8(rep)
    else:
        print("[跳过] 8. 确定性比对 —— 加 --rerun 执行（会重跑 5 个脚本）")

    notes = [
        f"- 站数 {len(stations['stations'])}、站次 {sum(len(s['slots']) for s in stations['stations'])}、"
        f"区间 {len(segs['features'])}、换乘 {len(transfers['transfers'])}、线路 {len(lines['lines'])} / 支线 {sum(len(l['branches']) for l in lines['lines'])}。",
        "- 站坐标包围盒外的白名单：兆丰路、光明路、花桥（苏州 11 号线昆山段，属苏州市）。",
        "- `walk_minutes` 全为 `null`（ADR R7：无可靠来源不估算）；换乘类型为人工判定（ADR R5）。",
        "- 已知缺口：2 号线实测 61.69 vs 官方 66 km（−6.5%）、浦江线 −5.1%，按 ADR R7 只记录；"
        "10/16/磁浮/浦江四线颜色官图不可辨，保留 OSM 并标 `colour_verified=false`；"
        "18 号线运营方按百科原样记为磁浮公司（可疑，待核）。",
    ]
    rep.markdown(notes)
    print(f"\n共 {len(rep.rows)} 项，失败 {rep.failed} 项；报告写入 {DOC}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
