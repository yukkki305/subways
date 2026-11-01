#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S1 一站式编排：把「原始 PBF → 可提交产物」跑完。

用法（在仓库根目录）：

    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\run_s1.py
    # 只跑某一步
    ... pipeline\\run_s1.py --only S1-5
    # 从某一步往后跑
    ... pipeline\\run_s1.py --from S1-4
    # 看步骤表
    ... pipeline\\run_s1.py --list

设计取舍：
- **不并发**。S1-2 下载 327 MB、S1-3 扫三个 PBF，并发只会让下载与解析互相抢带宽/内存。
- **不缓存中间结果**。每一步都幂等，重跑覆盖；要对比就先 `git diff`。
- **失败即停**。任何一步非零退出就停下并打印「上一步的产物路径 + 该查什么」，不自动重试
  （下载重试在 01 内部做，推送重试是 git 的事，见 AGENTS.md 第 11 节）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

# (步骤号, 脚本, 一句话说明, 产物「存在即说明跑过」的路径)
STEPS: list[tuple[str, str | None, str, Path | None]] = [
    ("S1-1", None, "目录与环境（.gitignore / .gitkeep / 本 README）", None),
    ("S1-2", "01_fetch_snapshot.py", "下载五省 PBF 并写 manifest + sha256", REPO / "data" / "snapshots"),
    ("S1-3", "02_extract_transit.py", "扫关系/way/节点，抽轨道关系", REPO / "data" / "raw" / "transit-relations.json"),
    ("S1-4", "03_extract_basemap.py", "抽上海底图要素（行政界 / 水系 / 海岸线）", REPO / "data" / "processed" / "basemap" / "shanghai-basemap.geojson"),
    ("S1-5", "04_track.py", "生成关系清单与三重指纹", REPO / "data" / "processed" / "relation-index.json"),
    ("S1-6", "05_attribution.py", "点面判定归属，回填 city / province", REPO / "data" / "processed" / "attribution-report.json"),
    ("S1-7", None, "汇总与提交（人工：核对 data/README.md 三问表 + 提交）", REPO / "data" / "README.md"),
]

RUNNABLE = [s for s in STEPS if s[1]]


def show_list() -> None:
    print(f"{'步骤':<6}{'脚本':<28}{'说明'}")
    print("-" * 88)
    for sid, script, desc, out in STEPS:
        mark = "（人工）" if script is None else ""
        print(f"{sid:<6}{(script or '—'):<28}{desc}{mark}")
        if out is not None and out.exists():
            print(f"{'':<34}└ 产物已存在：{out}")


def pick_steps(only: str | None, frm: str | None) -> list[tuple[str, str, str, Path | None]]:
    if only and frm:
        sys.exit("--only 与 --from 不能同时用")
    if only:
        hit = [s for s in RUNNABLE if s[0].lower() == only.lower()]
        if not hit:
            sys.exit(f"没有这一步：{only}（可跑的是 {', '.join(s[0] for s in RUNNABLE)}）")
        return hit  # type: ignore[return-value]
    if frm:
        ids = [s[0] for s in RUNNABLE]
        if frm not in ids:
            sys.exit(f"没有这一步：{frm}（可跑的是 {', '.join(ids)}）")
        return [s for s in RUNNABLE if ids.index(s[0]) >= ids.index(frm)]  # type: ignore[misc]
    return RUNNABLE  # type: ignore[return-value]


def run_one(sid: str, script: str, desc: str) -> float:
    path = REPO / "pipeline" / script
    if not path.exists():
        sys.exit(f"脚本不存在：{path}")
    print(f"\n=== {sid} {desc} ===")
    print(f"$ {PY} {path.relative_to(REPO)}")
    t0 = time.perf_counter()
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"  # 否则 Windows 控制台中文乱码
    proc = subprocess.run([PY, str(path)], cwd=str(REPO), env=env)
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        sys.stderr.write(
            f"\n[失败] {sid} 退出码 {proc.returncode}，耗时 {dt:.1f} s。\n"
            f"  先看这一步的报错，再看 {path.name} 顶部的注释；\n"
            f"  修复后从这一步重跑：run_s1.py --only {sid}\n"
        )
        sys.exit(proc.returncode)
    print(f"--- {sid} 完成，{dt:.1f} s ---")
    return dt


def main() -> int:
    ap = argparse.ArgumentParser(description="S1 一站式编排")
    ap.add_argument("--only", help="只跑这一步，如 S1-5")
    ap.add_argument("--from", dest="frm", help="从这一步往后跑，如 S1-4")
    ap.add_argument("--list", action="store_true", help="列出步骤表与产物状态")
    args = ap.parse_args()

    if args.list:
        show_list()
        return 0

    steps = pick_steps(args.only, args.frm)
    print(f"解释器：{PY}")
    print(f"仓库：{REPO}")
    print(f"计划执行：{', '.join(s[0] for s in steps)}")

    total = 0.0
    for sid, script, desc, _out in steps:
        total += run_one(sid, script, desc)  # type: ignore[arg-type]

    print(f"\n全部完成，总耗时 {total:.1f} s。")
    print("接下来（S1-7）：核对 data/README.md 三问表的数字与日期，然后")
    print("  git add -A && git commit -m \"data(S1): 重建快照与产物\" && git push origin main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
