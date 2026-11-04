#!/usr/bin/env python3
"""一条命令跑完某座城市的 S1 → S2（直到校验）。

与 run_s1.py 的分工：
    run_s1.py    只编排 S1（取数 → 归属），用于重建上海基线
    run_city.py  编排「某城的 S1 到 S2 全链路」，是加新城市时的总入口

用法：
    python pipeline/run_city.py --list                # 看步骤表
    python pipeline/run_city.py --city gz             # 广州全链路
    python pipeline/run_city.py --city sh --from S1-3 # 上海从 S1-3 起
    python pipeline/run_city.py --city gz --to S1-6   # 只跑到归属
    python pipeline/run_city.py --city gz --dry-run   # 只打印将执行的命令

两条与「人工闸门」有关的规则：
1. S2-2a（06_export_mapping.py）产出的映射表必须人工判定 `decide` 列。
   若表里还有空行，脚本会跑完 06 就停下，退出码 3，并打印「怎么填、填完怎么继续」。
2. 若映射表已经判定完（没有空 `decide`），默认**跳过** S2-2a 直接进 S2-2b，
   避免 06 的 `--force` 守卫把人工成果覆盖。要强制重出骨架加 `--with-skeleton`。

退出码：0 全部完成；1 参数错误 / 步骤失败；3 停在人工闸门。
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402


@dataclass(frozen=True)
class Step:
    sid: str
    script: str
    desc: str
    args: tuple[str, ...] = ()
    only_city: str | None = None  # 只在这些城市跑（"sh"）
    gate: bool = False


STEPS: list[Step] = [
    Step("S1-2", "01_fetch_snapshot.py", "下载该城所需 PBF，写 manifest + sha256"),
    Step("S1-3", "02_extract_transit.py", "扫关系/way/节点，抽轨道关系"),
    Step("S1-4", "03_extract_basemap.py", "抽底图要素（只做上海，其它城跳过）", only_city="sh"),
    Step("S1-5", "04_track.py", "关系清单与三重指纹"),
    Step("S1-6", "05_attribution.py", "点面判定归属，回填 city / province"),
    Step("S2-2a", "06_export_mapping.py", "生成关系映射骨架（人工填 decide 列）", gate=True),
    Step("S2-2b", "07_check_mapping.py", "校验映射表并渲染文档", ("--write-md",)),
    Step("S2-2c", "08_build_lines.py", "生成 lines.json（line / branch / 站序）"),
    Step("S2-3", "09_build_stations.py", "站点抽取与合并"),
    Step("S2-4", "10_build_segments.py", "区间几何切分"),
    Step("S2-5", "11_build_transfers.py", "换乘判定"),
    Step("S2-6", "12_build_attributes.py", "属性与颜色"),
    Step("S2-7", "13_validate.py", "八项校验（含重跑一致性）", ("--rerun",)),
]


# ---------------------------------------------------------------- 工具


def decide_status(csv_path: Path) -> tuple[int, int]:
    """返回 (总行数, 仍有空 decide 的行数)。文件不存在时返回 (0, 0)。"""
    if not csv_path.exists():
        return 0, 0
    total = 0
    empty = 0
    with csv_path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            total += 1
            if not (row.get("decide") or "").strip():
                empty += 1
    return total, empty


def pick(steps: list[Step], frm: str | None, to: str | None) -> list[Step]:
    ids = [s.sid for s in steps]
    if frm:
        hits = [i for i in ids if i.lower() == frm.lower()]
        if not hits:
            sys.exit(f"没有这一步：{frm}（可选：{', '.join(ids)}）")
        steps = steps[ids.index(hits[0]) :]
    if to:
        hits = [i for i in ids if i.lower() == to.lower()]
        if not hits:
            sys.exit(f"没有这一步：{to}（可选：{', '.join(ids)}）")
        steps = steps[: ids.index(hits[0]) + 1]
    if not steps:
        sys.exit("筛选后没有要执行的步骤")
    return steps


def show_list(city: str, cfg, csv_path: Path) -> None:
    total, empty = decide_status(csv_path)
    print(f"城市：{cfg.code} {cfg.city}（{cfg.province}）")
    print(f"PBF：{', '.join(cfg.pbfs)}｜快照键：{cfg.snapshot}")
    print(f"映射表：{csv_path}")
    if total:
        print(f"  └ {total} 行，其中 {empty} 行待判定")
    else:
        print("  └ 尚未生成")
    print()
    print(f"{'步骤':<7}{'脚本':<26}{'说明'}")
    print("-" * 92)
    for s in STEPS:
        mark = ""
        if s.only_city and s.only_city != cfg.code:
            mark = f"（仅 {s.only_city}，本城跳过）"
        if s.gate:
            mark += "（人工闸门）"
        print(f"{s.sid:<7}{s.script:<26}{s.desc}{mark}")


def run_step(step: Step, city: str, dry: bool) -> float:
    path = REPO / "pipeline" / step.script
    if not path.exists():
        sys.exit(f"脚本不存在：{path}")
    cmd = [PY, str(path), *step.args]
    print(f"\n=== {step.sid} {step.desc} ===")
    print("$ " + " ".join([Path(PY).name, f"pipeline/{step.script}", *step.args]))
    if dry:
        return 0.0
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["SUBWAY_CITY"] = city
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(REPO), env=env)
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        sys.stderr.write(
            f"\n[失败] {step.sid} 退出码 {proc.returncode}，耗时 {dt:.1f} s。\n"
            f"  看这一步的报错；修复后从这一步继续：\n"
            f"    python pipeline/run_city.py --city {city} --from {step.sid}\n"
        )
        sys.exit(proc.returncode)
    print(f"--- {step.sid} 完成，{dt:.1f} s ---")
    return dt


def gate_hint(city: str, cfg, csv_path: Path, empty: int, total: int) -> int:
    print(
        "\n" + "=" * 78 + "\n"
        f"停在人工闸门：映射表有 {empty}/{total} 行没有判定。\n"
        f"  文件：{csv_path}\n"
        "  要做的事：逐行填 `decide`（保留 / 合并 / 丢弃）与 `target_branch`，\n"
        "            `合并` 的行把 note 写清并入哪条；不确定的先留空。\n"
        "  填完继续：\n"
        f"    python pipeline/run_city.py --city {city} --from S2-2b\n"
        "  参考：上海那份是怎么填的 →  data/manual/shanghai/shanghai-relation-mapping.csv\n"
        "  （规则见 docs/decisions/0001-modeling-rules.md 的 R1）\n" + "=" * 78
    )
    return 3


def main() -> int:
    ap = argparse.ArgumentParser(description="某城 S1→S2 全链路编排")
    ap.add_argument("--city", default="sh", help="城市代码（sh/gz/cd/hf），默认 sh")
    ap.add_argument("--from", dest="frm", help="从这一步开始，如 S1-3 / S2-2b")
    ap.add_argument("--to", dest="to", help="跑到这一步为止，如 S1-6")
    ap.add_argument("--list", action="store_true", help="列出步骤表与映射表状态")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的命令")
    ap.add_argument(
        "--with-skeleton",
        action="store_true",
        help="即使映射表已判定，也重跑 06 生成骨架（会覆盖人工列，慎用）",
    )
    args = ap.parse_args()

    cfg = load_city(args.city)
    P = Paths(cfg)
    csv_path = P.manual_mapping_csv

    if args.list:
        show_list(cfg.code, cfg, csv_path)
        return 0

    steps = pick(STEPS, args.frm, args.to)
    total_rows, empty_rows = decide_status(csv_path)

    # 映射表已判定完 → 默认跳过骨架步骤，避免 --force 守卫中断整条链
    if total_rows and not empty_rows and not args.with_skeleton:
        steps = [s for s in steps if not s.gate]
    elif args.with_skeleton:
        print("注意：--with-skeleton 会重跑 06，已有 decide 列可能被覆盖。")

    print(f"解释器：{PY}")
    print(f"仓库：{REPO}")
    print(f"城市：{cfg.code} {cfg.city}（{cfg.province}）")
    print(f"计划执行：{', '.join(s.sid for s in steps)}")
    if args.dry_run:
        print("（--dry-run：只打印，不执行）")

    spent = 0.0
    for step in steps:
        if step.only_city and step.only_city != cfg.code:
            print(f"\n=== {step.sid} 跳过 === {step.desc}（仅 {step.only_city}）")
            continue
        spent += run_step(step, cfg.code, args.dry_run)
        if step.gate and not args.dry_run:
            total_rows, empty_rows = decide_status(csv_path)
            if empty_rows:
                return gate_hint(cfg.code, cfg, csv_path, empty_rows, total_rows)

    print(f"\n全部完成，总耗时 {spent:.1f} s。")
    print(f"产物目录：{P.city_dir}")
    print("提交前记得核对：data/README.md 三问表、docs/mappings/ 下的判定记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
