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
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = "https://download.openstreetmap.fr/extracts/asia/china/"
PROVINCES = ["shanghai", "jiangsu", "zhejiang"]
# D1 决策：单份超过 200 MB 就只下上海，其余按需再补
MAX_BYTES_PER_FILE = 200 * 1024 * 1024
SNAPSHOT_DATE = "20261101"
RAW_DIR = Path(r"E:\subway-data\snapshots") / SNAPSHOT_DATE
REPO = Path(r"E:\subway")
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


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STAMP_DIR.mkdir(parents=True, exist_ok=True)

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
        if dest.exists() and dest.stat().st_size == item["bytes"]:
            written = dest.stat().st_size
            elapsed = 0.0
            print(f"  {dest.name:<32} 已存在且体积一致，复用")
        else:
            print(f"  {dest.name:<32} 下载中 …", end="", flush=True)
            written, elapsed = download(item["url"], dest)
            print(f"\r  {dest.name:<32} {human(written):>10}  {elapsed:6.1f}s  {human(written / elapsed) if elapsed else '-'}/s", flush=True)
            if written != item["bytes"]:
                print(f"  ! 体积不符：声明 {item['bytes']} 实际 {written}", file=sys.stderr)
                return 3
        digest = sha256_of(dest)
        files.append(
            {
                "name": dest.name,
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

    manifest = {
        "snapshot_date": SNAPSHOT_DATE,
        "generated_at": now_iso(),
        "source": BASE,
        "source_notes": "download.openstreetmap.fr 省级 extract，日更；整档非增量",
        "license": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "as_of": files[0]["last_modified"] if files else None,
        "files": files,
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
