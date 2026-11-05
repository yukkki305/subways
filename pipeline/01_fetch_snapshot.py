#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S1-2 快照下载与归档。

职责：探测体积 -> 下载省级 PBF -> 校验 -> 写 manifest.json 与 .sha256。
原始 PBF 落仓库外（E:\\subway-data\\snapshots\\<date>\\），git 只收 .sha256 + manifest.json。

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\01_fetch_snapshot.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://download.openstreetmap.fr/extracts/asia/china/"
# 2026-11-01 扩到 5 省：江苏省 L4 省界与山东/安徽共边的 11 个 way 只在那两份 extract 里，
# 少了它们江苏省面永远拼不闭合（自拼只有 309.4 km² / 23 个碎片）；顺带让宁滁线、宁马线等
# 跨省线路能判到安徽一侧。范围只加这 2 省，不扩到长三角全部（用户 M01450 定）。
# D1 决策：单份超过 200 MB 就只下上海，其余按需再补
MAX_BYTES_PER_FILE = 200 * 1024 * 1024
REPO = Path(r"E:\subway")
sys.path.insert(0, str(Path(__file__).parent))
from cityconfig import load_city  # noqa: E402
from paths import Paths  # noqa: E402

CITY_CODE = os.environ.get("SUBWAY_CITY", "sh")
CFG = load_city(CITY_CODE)
P = Paths(CFG)
PROVINCES = list(CFG.pbfs)   # 该城需要的省级 extract，来自城市配置
SNAPSHOT_DATE = CFG.snapshot
RAW_DIR = P.snapshot_dir(SNAPSHOT_DATE)
STAMP_DIR = REPO / "data" / "snapshots" / SNAPSHOT_DATE
TZ = timezone(timedelta(hours=8))
CHUNK = 1 << 20


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def probe(url: str) -> tuple[int | None, str | None]:
    """先 HEAD，失败再用 Range 探测总长度。"""
    try:
        r = requests.head(url, allow_redirects=True, timeout=(15, 30))
        if r.status_code in (200, 206) and r.headers.get("Content-Length"):
            return int(r.headers["Content-Length"]), r.headers.get("Last-Modified")
    except requests.RequestException:
        pass
    try:
        with requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=(15, 30)) as r:
            content_range = r.headers.get("Content-Range", "")
            total = int(content_range.rsplit("/", 1)[-1]) if "/" in content_range else None
            return total, r.headers.get("Last-Modified")
    except requests.RequestException as exc:
        print(f"  ! 探测失败：{exc}", file=sys.stderr)
        return None, None


def download(url: str, dest: Path) -> tuple[int, float]:
    tmp = dest.with_name(dest.name + ".part")
    started = time.time()
    written = 0
    with requests.get(url, stream=True, timeout=(20, 120)) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(CHUNK):
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
    elapsed = time.time() - started
    tmp.replace(dest)
    return written, elapsed


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.2f} GB"


def load_manifest() -> dict:
    """读已有 manifest（同快照键）。多城依次跑 S1-2 时，各自只带自己需要的省，
    必须按文件名合并，不能整体覆盖，否则先跑的省的记录会丢。"""
    path = STAMP_DIR / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STAMP_DIR.mkdir(parents=True, exist_ok=True)
    prev = load_manifest()
    prev_files = {f["name"]: f for f in prev.get("files", [])}
    refresh = "--refresh" in sys.argv

    print(f"快照日期 {SNAPSHOT_DATE}  原始目录 {RAW_DIR}")
    print(f"源 {BASE}\n")

    print("— 体积探测 —")
    plan: list[dict] = []
    for prov in PROVINCES:
        url = f"{BASE}{prov}-latest.osm.pbf"
        size, last_mod = probe(url)
        if size is None:
            print(f"  {prov:<10} 探测失败（停止，不擅自换源）")
            return 2
        oversized = size > MAX_BYTES_PER_FILE and prov != PROVINCES[0]
        print(f"  {prov:<10} {human(size):>10}  Last-Modified={last_mod}  {'→ 跳过（>200MB，按 D1 只下上海）' if oversized else ''}")
        plan.append({"province": prov, "url": url, "bytes": size, "last_modified": last_mod, "skip": oversized})

    print("\n— 下载 —")
    files: list[dict] = []
    skipped: list[dict] = []
    for item in plan:
        if item["skip"]:
            skipped.append({k: item[k] for k in ("province", "url", "bytes", "last_modified")})
            continue
        dest = RAW_DIR / f"{item['province']}-latest.osm.pbf"
        disk_sha = sha256_of(dest) if dest.exists() else None
        recorded = prev_files.get(dest.name)
        same_as_record = bool(recorded and disk_sha and recorded.get("sha256") == disk_sha)
        if dest.exists() and same_as_record:
            written = dest.stat().st_size
            elapsed = 0.0
            print(f"  {dest.name:<32} 已存在且 sha256 与 manifest 一致，复用")
        elif dest.exists() and not refresh:
            # 上游日更会把同一文件名换成新内容；此时**不覆盖**同快照键下的旧字节，
            # 只记录磁盘现值并在 manifest 里标明 upstream_changed。
            written = dest.stat().st_size
            elapsed = 0.0
            print(f"  {dest.name:<32} 已存在但与 manifest 记录的 sha256 不同：不覆盖，按磁盘现值记录"
                  f"（如需换成上游最新版，请换快照键或加 --refresh）")
        else:
            print(f"  {dest.name:<32} 下载中 …", end="", flush=True)
            written, elapsed = download(item["url"], dest)
            print(f"\r  {dest.name:<32} {human(written):>10}  {elapsed:6.1f}s  {human(written / elapsed) if elapsed else '-'}/s", flush=True)
            if written != item["bytes"]:
                print(f"  ! 体积不符：声明 {item['bytes']} 实际 {written}", file=sys.stderr)
                return 3
        digest = sha256_of(dest)
        entry_note = None
        if recorded and recorded.get("sha256") and recorded["sha256"] != digest:
            entry_note = (f"上游日更导致内容变化：manifest 旧记录 {recorded['sha256'][:16]}…，"
                          f"磁盘现值 {digest[:16]}…（{recorded.get('last_modified')} → {item['last_modified']}）")
        files.append(
            {
                "name": dest.name,
                "upstream_changed": bool(entry_note),
                "note": entry_note,
                "province": item["province"],
                "url": item["url"],
                "bytes": written,
                "sha256": digest,
                "last_modified": item["last_modified"],
                "downloaded_at": now_iso(),
                "elapsed_s": round(elapsed, 2),
                "avg_bytes_per_s": int(written / elapsed) if elapsed else None,
                "local_path": str(dest),
            }
        )
        (STAMP_DIR / f"{dest.name}.sha256").write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
        print(f"  {'':<32} sha256 {digest[:16]}…  已写 {dest.name}.sha256")

    merged = dict(prev_files)
    for f in files:
        old_entry = prev_files.get(f["name"]) or {}
        # 上游换过内容这件事要留痕：后来某次跑若发现「磁盘与 manifest 已一致」，
        # 不能把之前的 previous_sha256 / note 抹掉。
        if old_entry.get("upstream_changed") and not f.get("upstream_changed"):
            f["upstream_changed"] = True
            f["previous_sha256"] = old_entry.get("previous_sha256")
            f["note"] = old_entry.get("note")
        merged[f["name"]] = f
    all_files = sorted(merged.values(), key=lambda f: f["name"])
    manifest = {
        "snapshot_date": SNAPSHOT_DATE,
        "generated_at": now_iso(),
        "source": BASE,
        "source_notes": "download.openstreetmap.fr 省级 extract，日更；整档非增量",
        "license": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "as_of": all_files[0]["last_modified"] if all_files else None,
        "files": all_files,
        "skipped_by_size_rule": skipped,
    }
    manifest_path = STAMP_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n— 归档 —\n  {manifest_path}")
    for f in files:
        print(f"  {STAMP_DIR / (f['name'] + '.sha256')}")
    if skipped:
        print("\n  跳过的省级文件（>200 MB，需要时再补）：")
        for s in skipped:
            print(f"    {s['province']}  {human(s['bytes'])}")
    print(f"\n总计 {len(files)} 个文件，{human(sum(f['bytes'] for f in files))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
