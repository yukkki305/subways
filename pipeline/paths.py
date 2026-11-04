"""路径层：所有「文件放哪儿」的唯一出处（P1a-1.2）。

P0 的 13 个脚本各自把路径写成字符串常量（`data/processed/shanghai/lines.json`、
`E:\\subway-data\\snapshots\\20261101\\shanghai-latest.osm.pbf` 之类）。P1a 要加城，
若每条路径都要在每个脚本里改一遍，必然漏。这个模块把这些路径收敛成函数，
P1a-1.3 只把脚本里的字符串换成函数调用。

设计约束
--------
1. **不改现有文件位置**：上海（`sh`）的产物仍留在 P0 的位置 ——
   `data/processed/attribution-report.json`、`data/processed/relation-index.json`、
   `data/processed/basemap/*.geojson` 都是共享位置，不是 `data/processed/shanghai/` 下的。
   这是为了让 P1a-1.6 的「上海产物逐字节不变」能成立。其它城按城分目录。
2. **仓库外的大文件**：PBF 与快照元数据在 `E:\\subway-data\\snapshots\\<key>\\`，
   用环境变量 `SUBWAY_SNAPSHOTS` 覆盖根目录（默认就是那个路径）。
3. **纯函数**：不做 IO（除了 `ensure_dir`），不读配置文件以外的状态；
   这样单元测试和 `--show` 都不会有副作用。
4. **缺失可见**：`--show` 会逐项标 `[有]` / `[缺]`，P1a-1.3 改造时可当检查表用。

用法
----
    from cityconfig import load_city
    from paths import Paths

    p = Paths(load_city("sh"))
    p.lines_json          # E:\\subway\\data\\processed\\shanghai\\lines.json
    p.segment_geojson
    p.basemap_geojson
    p.pbf("shanghai", "20261101")

命令行
------
    python pipeline/paths.py --show sh      # 列出一个城市的全部派生路径
    python pipeline/paths.py --show gz
    python pipeline/paths.py --check        # 校验上海（回归基准）的产物是否都在
    python pipeline/paths.py --roots        # 打印各根目录
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cityconfig import CityConfig, list_codes, load_city

# ---------------------------------------------------------------------------
# 根目录
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent

DATA = REPO / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
PROCESSED = DATA / "processed"
MANUAL = DATA / "manual"
BASEMAP = PROCESSED / "basemap"
SNAPSHOT_META = DATA / "snapshots"

WEB = REPO / "web"
WEB_PUBLIC_DATA = WEB / "public" / "data"

DOCS = REPO / "docs"
DOCS_MAPPINGS = DOCS / "mappings"

# 仓库外：PBF 与快照的原始文件
EXTERNAL_ROOT = Path(os.environ.get("SUBWAY_DATA_ROOT", r"E:\subway-data"))
SNAPSHOTS = Path(os.environ.get("SUBWAY_SNAPSHOTS", str(EXTERNAL_ROOT / "snapshots")))

# P0 留下的共享位置：这些产物现在是「全局」的，不属于某个城市的子目录。
# 上海沿用它们；其余城市按 <PROCESSED>/<code>/ 分目录。
LEGACY_HOME = "sh"

# 人工核对表的文件名前缀（P0 是 shanghai-*，其余城按全名）
MANUAL_SLUG = {
    "sh": "shanghai",
    "gz": "guangzhou",
    "cd": "chengdu",
    "hf": "hefei",
}


def ensure_dir(path: Path) -> Path:
    """建目录（幂等），返回同一个 Path。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


class Paths:
    """一个城市的全部路径。构造时不做 IO。"""

    def __init__(self, cfg: CityConfig) -> None:
        self.cfg = cfg
        self.code = cfg.code
        self.legacy = cfg.code == LEGACY_HOME

    # --- 根 ---------------------------------------------------------------

    @property
    def repo(self) -> Path:
        return REPO

    @property
    def data(self) -> Path:
        return DATA

    @property
    def processed(self) -> Path:
        return PROCESSED

    @property
    def raw(self) -> Path:
        return RAW

    @property
    def cache(self) -> Path:
        return CACHE

    @property
    def manual(self) -> Path:
        return MANUAL

    @property
    def snapshots(self) -> Path:
        return SNAPSHOTS

    # --- 产物目录 ---------------------------------------------------------

    @property
    def city_dir(self) -> Path:
        """`data/processed/<dir>`，目录名取配置里的 `data_dir` 末段。"""
        return PROCESSED / Path(self.cfg.data_dir).name

    @property
    def basemap_dir(self) -> Path:
        return BASEMAP if self.legacy else self.city_dir / "basemap"

    @property
    def raw_dir(self) -> Path:
        return RAW

    @property
    def cache_dir(self) -> Path:
        return CACHE / self.cfg.code

    # --- S1：快照与原始数据 ------------------------------------------------

    def snapshot_dir(self, key: str) -> Path:
        """`E:\\subway-data\\snapshots\\<key>`"""
        return SNAPSHOTS / key

    def pbf(self, province: str, key: str) -> Path:
        """`<snapshots>/<key>/<province>-latest.osm.pbf`"""
        return self.snapshot_dir(key) / f"{province}-latest.osm.pbf"

    def pbfs(self, key: str) -> list[Path]:
        """本城需要的全部 PBF（按配置顺序）。"""
        return [self.pbf(p, key) for p in self.cfg.pbfs]

    def snapshot_manifest(self, key: str) -> Path:
        """快照元数据（进 git）在仓库内：`data/snapshots/<key>/manifest.json`。

        注意：PBF 本体在仓库外（`E:\\subway-data\\snapshots\\<key>\\`），
        清单与 sha256 在仓库内，两者用同一个 key 对齐。
        """
        return SNAPSHOT_META / key / "manifest.json"

    def snapshot_sha(self, province: str, key: str) -> Path:
        return SNAPSHOT_META / key / f"{province}-latest.osm.pbf.sha256"

    def raw_transit(self) -> Path:
        """S1-3 的中间产物（不进 git）。

        上海沿用 P0 的单文件 `transit-relations.json`；其它城按城分文件，
        避免多城互相覆盖。
        """
        if self.legacy:
            return RAW / "transit-relations.json"
        return RAW / f"transit-relations-{self.code}.json"

    # --- S1：清单与归属 ----------------------------------------------------

    def relation_index_global(self) -> Path:
        """全局审计用的关系清单（跨省，含全部城）。"""
        return PROCESSED / "relation-index.json"

    def relation_index(self) -> Path:
        """本城子集（P1a-1.3 起生成；上海暂时与全局同一份）。"""
        if self.legacy:
            return PROCESSED / "relation-index.json"
        return self.city_dir / "relation-index.json"

    def attribution_report_global(self) -> Path:
        return PROCESSED / "attribution-report.json"

    def attribution_report(self) -> Path:
        if self.legacy:
            return PROCESSED / "attribution-report.json"
        return self.city_dir / "attribution-report.json"

    def name_diff(self) -> Path:
        if self.legacy:
            return PROCESSED / "name-diff.json"
        return self.city_dir / "name-diff.json"

    # --- S2：线路 / 车站 / 区间 / 换乘 --------------------------------------

    @property
    def lines_json(self) -> Path:
        return self.city_dir / "lines.json"

    @property
    def station_json(self) -> Path:
        return self.city_dir / "station.json"

    @property
    def transfer_json(self) -> Path:
        return self.city_dir / "transfer.json"

    @property
    def segment_geojson(self) -> Path:
        return self.city_dir / "segment.geojson"

    # --- 底图与海面 -------------------------------------------------------

    @property
    def basemap_geojson(self) -> Path:
        """底图要素。上海沿用 `data/processed/basemap/shanghai-basemap.geojson`。"""
        return self.basemap_dir / f"{Path(self.cfg.data_dir).name}-basemap.geojson"

    @property
    def sea_geojson(self) -> Path:
        """海面。上海沿用 `data/processed/basemap/shanghai-sea.geojson`。"""
        return self.basemap_dir / f"{Path(self.cfg.data_dir).name}-sea.geojson"

    # --- 人工核对表（data/manual） -----------------------------------------

    @property
    def manual_slug(self) -> str:
        return MANUAL_SLUG.get(self.code, Path(self.cfg.data_dir).name)

    @property
    def manual_dir(self) -> Path:
        """`data/manual/`，分城按子目录放（`data/manual/<slug>/`）。"""
        return MANUAL

    @property
    def manual_city_dir(self) -> Path:
        """`data/manual/<slug>/`：本城的人工核对表（合并白名单、换乘类型、颜色、官方里程）。"""
        return MANUAL / self.manual_slug

    def manual_city_file(self, name: str) -> Path:
        """`data/manual/<slug>/<name>`，如 `transfers.json`。"""
        return self.manual_city_dir / name

    def manual_file(self, suffix: str) -> Path:
        """`data/manual/<slug>-<suffix>`，如 `shanghai-lines.csv`。"""
        return MANUAL / f"{self.manual_slug}-{suffix}"

    @property
    def manual_lines_csv(self) -> Path:
        return self.manual_file("lines.csv")

    @property
    def manual_mapping_csv(self) -> Path:
        return self.manual_file("relation-mapping.csv")

    # --- 前端产物 ---------------------------------------------------------

    @property
    def web_data_dir(self) -> Path:
        return WEB_PUBLIC_DATA

    def web_file(self, name: str) -> Path:
        return WEB_PUBLIC_DATA / name

    # --- 文档产物 ---------------------------------------------------------

    @property
    def docs(self) -> Path:
        return DOCS

    def doc(self, name: str) -> Path:
        """`docs/<name>`，用于不带城市前缀的全局文档（colors.md / conflicts.md 等）。"""
        return DOCS / name

    @property
    def docs_relations_md(self) -> Path:
        """`docs/mappings/<slug>-relations.md`（07 渲染）。"""
        return DOCS_MAPPINGS / f"{self.manual_slug}-relations.md"

    @property
    def docs_station_merge_md(self) -> Path:
        """`docs/mappings/station-merge-decisions.md`（09 渲染）。

        注意：P0 是全局单文件，没有城市前缀；多城后应按城分文件，
        那是 P1a-1.3 之后的事，这里先保持 P0 路径不变。
        """
        return DOCS_MAPPINGS / "station-merge-decisions.md"

    @property
    def docs_transfer_md(self) -> Path:
        """`docs/mappings/transfer-decisions.md`（11 渲染）。"""
        return DOCS_MAPPINGS / "transfer-decisions.md"

    @property
    def docs_colors_md(self) -> Path:
        """`docs/colors.md`（12 渲染）。"""
        return DOCS / "colors.md"

    # --- 外部语料（只读） -------------------------------------------------

    def gzupa_shp(self, year: int = 2020) -> Path:
        """GZUPA 2020 站点 shapefile。根目录可用 `SUBWAY_GZUPA` 覆盖。"""
        root = Path(os.environ.get("SUBWAY_GZUPA", str(EXTERNAL_ROOT / "probe16" / "gzupa" / "out")))
        city = self.manual_slug
        return root / "1_subway_point" / city / f"{city}_Layer_{year}.shp"

    # --- 视图 -------------------------------------------------------------

    def all_paths(self) -> list[tuple[str, Path, bool]]:
        """(名字, 路径, 是否应已存在)，供 `--show` / `--check` 使用。"""
        return [
            ("城市目录", self.city_dir, True),
            ("lines.json", self.lines_json, True),
            ("station.json", self.station_json, True),
            ("transfer.json", self.transfer_json, True),
            ("segment.geojson", self.segment_geojson, True),
            ("basemap.geojson", self.basemap_geojson, True),
            ("sea.geojson", self.sea_geojson, False),
            ("relation-index（本城）", self.relation_index(), True),
            ("attribution-report（本城）", self.attribution_report(), True),
            ("name-diff", self.name_diff(), False),
            ("manual lines.csv", self.manual_lines_csv, True),
            ("manual relation-mapping.csv", self.manual_mapping_csv, True),
            ("docs <slug>-relations.md", self.docs_relations_md, True),
            ("docs station-merge-decisions.md", self.docs_station_merge_md, True),
            ("docs transfer-decisions.md", self.docs_transfer_md, True),
            ("docs colors.md", self.docs_colors_md, True),
            ("raw transit（中间）", self.raw_transit(), False),
            ("web 数据目录", self.web_data_dir, True),
        ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _fmt(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _show(code: str) -> int:
    cfg = load_city(code)
    p = Paths(cfg)
    print(f"# {cfg.code} {cfg.name}（{cfg.province}）")
    print(f"{'项':32}{'状态':6}路径")
    missing_required = 0
    for name, path, required in p.all_paths():
        exists = path.exists()
        if exists:
            status = "[有]"
        elif required:
            status = "[缺]"
            missing_required += 1
        else:
            status = "[—]"
        print(f"{name:32}{status:6}{_fmt(path)}")

    print("\n# 快照（键 = 快照目录名）")
    keys = sorted(
        {x.name for x in SNAPSHOTS.glob("*") if x.is_dir()}
        | {x.name for x in SNAPSHOT_META.glob("*") if x.is_dir()}
    )
    for key in keys:
        marks = []
        for province in cfg.pbfs:
            have_pbf = p.pbf(province, key).exists()
            have_sha = p.snapshot_sha(province, key).exists()
            marks.append(f"{province}{'✓' if have_pbf else '✗'}{'/sha✓' if have_sha else '/sha✗'}")
        manifest = p.snapshot_manifest(key)
        if not marks:
            continue
        print(f"{key:32}{'[有]' if manifest.exists() else '[缺]':6}{', '.join(marks)}  PBF:{p.snapshot_dir(key)}")

    print()
    if missing_required:
        print(f"缺 {missing_required} 个必需产物（该城可能还没跑到对应步骤）")
    return 0


def _check(codes: list[str] | None = None) -> int:
    targets = codes or [LEGACY_HOME]
    failures = 0
    for code in targets:
        cfg = load_city(code)
        p = Paths(cfg)
        miss = [(n, path) for n, path, req in p.all_paths() if req and not path.exists()]
        if miss:
            failures += 1
            print(f"[失败] {code} 缺 {len(miss)} 项：")
            for name, path in miss:
                print(f"        {name:32}{_fmt(path)}")
        else:
            print(f"[通过] {code} {cfg.name}：必需产物齐全（{len([1 for _, _, r in p.all_paths() if r])} 项）")
    if failures:
        print(f"\n{failures} 个城市缺产物")
        return 1
    print(f"\n全部通过：{len(targets)} 个城市")
    return 0


def _roots() -> int:
    pairs = [
        ("仓库", REPO),
        ("data/", DATA),
        ("data/raw/", RAW),
        ("data/processed/", PROCESSED),
        ("data/manual/", MANUAL),
        ("data/processed/basemap/", BASEMAP),
        ("data/snapshots/（元数据）", SNAPSHOT_META),
        ("web/public/data/", WEB_PUBLIC_DATA),
        ("外部根（PBF 等大文件）", EXTERNAL_ROOT),
        ("外部快照目录", SNAPSHOTS),
    ]
    for name, path in pairs:
        mark = "有" if path.exists() else "缺"
        print(f"{name:28}{mark:4}{_fmt(path) if path.is_relative_to(REPO) else path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="路径层：唯一出处（P1a-1.2）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--show", metavar="CODE", help="列出该城市的全部派生路径")
    group.add_argument("--check", nargs="*", metavar="CODE", help="校验产物是否齐全（默认 sh）")
    group.add_argument("--roots", action="store_true", help="打印各根目录")
    args = parser.parse_args(argv)

    if not (args.show or args.check is not None or args.roots):
        parser.error("需要 --show CODE / --check [CODE] / --roots 之一")

    if args.roots:
        return _roots()
    if args.show:
        return _show(args.show)
    return _check(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
