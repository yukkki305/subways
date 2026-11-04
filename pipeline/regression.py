"""上海回归：重跑基线产物，与上一版逐文件比对（只忽略时间戳）。

为什么需要这个脚本：
  P1a 把 15 个脚本改成了配置驱动，最容易踩的坑是「改广州顺手把上海改坏」。
  人工跑一遍再肉眼比 git diff 不可靠（产物是 40 万字节级 JSON，diff 看不出语义差异），
  所以这里做机器判据：
    1) 把文件按「时间戳归一化」后取 sha256；
    2) 与 git 里上一版（默认 HEAD）的同名文件比；
    3) 不一致就打印第一处差异行，退出码 1。

时间戳归一化：把任何 ISO-8601 时间（2026-11-04T22:33:45+08:00）替换成 <TS>，
  另外把 `docs/validation-s2.md` 里的耗时行（"耗时 … s"）也归一，
  因为这两类数字每次跑都会变，与「产物是否被改坏」无关。

用法：
  python pipeline/regression.py                 # 只比对当前工作区 vs HEAD
  python pipeline/regression.py --run           # 先跑一遍上海管道再比对
  python pipeline/regression.py --run --from S1-2
  python pipeline/regression.py --baseline HEAD~1
  python pipeline/regression.py --list          # 只列出纳入回归的文件
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
# 校验报告里会写「耗时 45.2 s」「45.2s」这类数字
DURATION = re.compile(r"(耗时\s*)[\d.]+\s*(?:ms|s)\b")
# 体积/条数之类不进归一化，它们是产物的一部分，改了就该报出来


def normalize(text: str) -> str:
    text = ISO_TS.sub("<TS>", text)
    text = DURATION.sub(r"\1<DUR>", text)
    # Windows/Unix 换行、行尾空白不影响语义
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n"))


def digest(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


def first_diff(a: str, b: str) -> str:
    al, bl = normalize(a).split("\n"), normalize(b).split("\n")
    for i in range(min(len(al), len(bl))):
        if al[i] != bl[i]:
            return f"第 {i + 1} 行\n      当前: {al[i][:160]}\n      基线: {bl[i][:160]}"
    if len(al) != len(bl):
        return f"行数不同：当前 {len(al)} 行，基线 {len(bl)} 行"
    return "内容相同（差异应只来自归一化未覆盖的格式）"


def show(ref: str, rel: str) -> str | None:
    """从 git 里取历史版本；取不到（未跟踪/不存在）返回 None。"""
    r = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        cwd=REPO, capture_output=True,
    )
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def tracked_in_git(rel: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO, capture_output=True)
    return r.returncode == 0


def regression_files(code: str) -> list[tuple[str, Path]]:
    """纳入回归的产物：都在仓库内，且都由管道生成。"""
    cfg = load_city(code)
    p = Paths(cfg)
    items: list[tuple[str, Path]] = [
        ("data/raw/transit-relations.json", p.raw_transit()),
        ("relation-index", p.relation_index()),
        ("attribution-report", p.attribution_report()),
        ("lines.json", p.lines_json),
        ("station.json", p.station_json),
        ("transfer.json", p.transfer_json),
        ("segment.geojson", p.segment_geojson),
        ("basemap.geojson", p.basemap_geojson),
        ("sea.geojson", p.sea_geojson),
        ("docs/conflicts.md", p.doc("conflicts.md")),
        ("docs/validation-s2.md", p.doc("validation-s2.md")),
        ("docs/colors.md", p.docs_colors_md),
        ("docs/station-merge-decisions.md", p.docs_station_merge_md),
        ("docs/transfer-decisions.md", p.docs_transfer_md),
        ("docs/relations.md", p.docs_relations_md),
        ("name-diff.json", p.name_diff()),
        ("docs/name-diff.md", p.doc("name-diff.md")),
    ]
    return items


def rel_to_repo(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def main() -> int:
    ap = argparse.ArgumentParser(description="上海回归：产物与上一版比对（忽略时间戳）")
    ap.add_argument("--city", default="sh")
    ap.add_argument("--baseline", default="HEAD", help="git 参考点，默认 HEAD")
    ap.add_argument("--run", action="store_true", help="先跑一遍管道再比对")
    ap.add_argument("--from", dest="frm", default="S1-5")
    ap.add_argument("--to", dest="to", default="S2-7")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    cfg = load_city(args.city)
    items = regression_files(args.city)

    if args.list:
        print(f"{cfg.name}（{cfg.code}）纳入回归的产物：")
        for name, path in items:
            state = "在" if path.exists() else "缺"
            print(f"  [{state}] {rel_to_repo(path)}")
        return 0

    if args.run:
        print(f"=== 先跑 {cfg.name} 管道（{args.frm} → {args.to}）===")
        cmd = [sys.executable, str(Path(__file__).parent / "run_city.py"),
               "--city", args.city, "--from", args.frm, "--to", args.to]
        r = subprocess.run(cmd, cwd=REPO, env={**__import__("os").environ, "PYTHONUTF8": "1"})
        if r.returncode not in (0, 3):
            print(f"[失败] 管道退出码 {r.returncode}")
            return 1
        if r.returncode == 3:
            print("[失败] 管道停在人工闸门（退出码 3），回归无法进行")
            return 1

    print(f"=== 比对基线：{args.baseline} ===")
    bad = 0
    skip = 0
    for name, path in items:
        if not path.exists():
            print(f"[缺] {name}: {rel_to_repo(path)} 不存在")
            bad += 1
            continue
        rel = rel_to_repo(path)
        if not tracked_in_git(rel):
            print(f"[跳过] {name}: 未纳入 git")
            skip += 1
            continue
        base = show(args.baseline, rel)
        if base is None:
            print(f"[跳过] {name}: {args.baseline} 里没有")
            skip += 1
            continue
        cur = path.read_text(encoding="utf-8", errors="replace")
        if digest(cur) == digest(base):
            print(f"[一致] {name:28s} {rel}")
        else:
            bad += 1
            print(f"[不一致] {name:28s} {rel}")
            print(f"      {first_diff(cur, base)}")

    print()
    total = len(items)
    print(f"合计 {total} 项：一致 {total - bad - skip}｜不一致 {bad}｜跳过 {skip}")
    if bad:
        print("[失败] 产物与基线不一致（时间戳已被忽略，说明语义变了）")
        return 1
    print("[通过] 产物与基线逐字节一致（时间戳除外）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
