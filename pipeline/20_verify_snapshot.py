"""P1b 阶段 0.4：快照完整性核验。

`data/snapshots/<key>/manifest.json` 记了每个 PBF 的 URL、字节数、sha256，
但下载器（仓库外脚本）跑完只打印一行「完成」，没有回头校验。P1b 要到 50 城，
任何一次坏包都会在几天后以「某城少了一条线」的形式爆出来，所以先把它钉死：

  - manifest 里列的文件必须都在磁盘上
  - 字节数一致
  - sha256 一致（默认校验，`--no-hash` 只比大小，用于快速自检）

用法：
  python pipeline/20_verify_snapshot.py                       # 校验所有快照
  python pipeline/20_verify_snapshot.py --only p1b-20261113   # 只校验一个
  python pipeline/20_verify_snapshot.py --no-hash             # 只比字节数
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFESTS = REPO / "data" / "snapshots"
# PBF 本体不进仓库，落在仓库外；键 = 快照目录名。
# 老快照（20261101 / p1a-20261103）的文件在同一个根目录下，只是按省命名。
PBF_ROOTS = {
    "p1b-20261113": Path(r"E:\subway-data\snapshots\p1b-20261113"),
    "p1a-20261103": Path(r"E:\subway-data\snapshots\p1a-20261103"),
    "20261101": Path(r"E:\subway-data\snapshots\20261101"),
}


def manifest_entries(manifest: dict) -> list[dict]:
    """两种 manifest 形态都收：P1b 用 `provinces`（无 name），P1a/P0 用 `files`。"""
    if manifest.get("files"):
        return list(manifest["files"])
    out = []
    for item in manifest.get("provinces", []):
        prov = item.get("province", "")
        out.append({**item, "name": f"{prov}-latest.osm.pbf"})
    return out


def sha256_of(path: Path, chunk: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def verify(key: str, manifest_path: Path, do_hash: bool) -> tuple[int, int, list[str]]:
    manifest = json.loads(manifest_path.read_text("utf8"))
    files = manifest_entries(manifest)
    root = PBF_ROOTS.get(key)
    ok = bad = 0
    problems: list[str] = []

    for item in files:
        name = item.get("name") or item.get("file")
        if not name:
            problems.append(f"{key}: manifest 里有一条没有 name 的记录")
            bad += 1
            continue
        path = (root / name) if root else None
        if path is None or not path.exists():
            problems.append(f"{key}: 缺文件 {name}（找过 {root}）")
            bad += 1
            continue
        size = path.stat().st_size
        if int(item.get("bytes", -1)) != size:
            problems.append(f"{key}: {name} 字节 {size} ≠ manifest {item.get('bytes')}")
            bad += 1
            continue
        if do_hash:
            digest = sha256_of(path)
            want = item.get("sha256", "")
            if want and digest != want:
                problems.append(f"{key}: {name} sha256 不符（{digest[:16]}… ≠ {want[:16]}…）")
                bad += 1
                continue
        ok += 1

    # 反向：磁盘上多出来的 PBF（下载过但没进 manifest，多见于中断重跑）
    if root and root.exists():
        listed = {item.get("name") for item in files} | {f"{item.get('province')}-latest.osm.pbf" for item in files}
        extra = sorted(p.name for p in root.glob("*.osm.pbf") if p.name not in listed)
        if extra:
            problems.append(f"{key}: 磁盘上有 {len(extra)} 个 PBF 不在 manifest 里：{', '.join(extra[:6])}"
                            + ("…" if len(extra) > 6 else ""))
    return ok, bad, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--no-hash", action="store_true")
    args = ap.parse_args()

    keys = sorted(p.name for p in MANIFESTS.iterdir() if (p / "manifest.json").exists())
    if args.only:
        keys = [k for k in keys if k in set(args.only)]
    if not keys:
        print("没找到任何 manifest")
        return 1

    total_ok = total_bad = 0
    all_problems: list[str] = []
    for key in keys:
        path = MANIFESTS / key / "manifest.json"
        ok, bad, problems = verify(key, path, not args.no_hash)
        total_ok += ok
        total_bad += bad
        all_problems += problems
        print(f"{key:<16} 通过 {ok:3d}｜失败 {bad:3d}" + (f"｜{'；'.join(problems[:2])}" if problems else ""))

    print(f"\n合计 {len(keys)} 个快照：通过 {total_ok}｜失败 {total_bad}")
    if all_problems:
        print("\n明细：")
        for p in all_problems:
            print("  -", p)
        return 1
    print("全部一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
