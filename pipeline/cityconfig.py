"""城市配置的加载与校验（P1a-1.1）。

这个模块是**唯一的配置入口**：业务脚本不再自己写死省份、PBF 名、城市面 id、
线路数量、环线起点这些东西，而是 `from cityconfig import load_city` 后取。

配置文件位置：`pipeline/cities/<code>.json`（每个城市一份）。

设计要点
--------
1. **配置 vs 人工表**：这里只放「机器能读的事实」（省份、行政 id、PBF 名、
   网络名、视野框、线路清单）。要人判断的东西（同名站合并白名单、换乘类型、
   颜色覆盖、官方里程）留在 `data/manual/<city>/`，不进配置。
   依据：`docs/decisions/0004-city-config.md`。
2. **严格校验**：未知字段直接报错，避免拼错 key 后静默失效；缺必填、类型错、
   枚举越界、矩形框不合法、线路清单与预期数量不一致，都在 `load_city()` 时抛出
   `ConfigError`，并且一次把所有错误列出来（不是遇到第一个就停）。
3. **可变部分留空**：`line_ids` 在关系映射（P1a-3）之前无法确定，允许为 `null`；
   此时只校验 `line_count_expected`。

用法
----
    from cityconfig import load_city
    sh = load_city("sh")
    sh.province            # "上海市"
    sh.province_l4         # 913067
    sh.pbfs                # ["shanghai"]
    sh.bbox_tuple          # (120.7, 30.55, 123.4, 31.95)
    sh.km_per_deg          # (95.3, 111.0)

命令行
------
    python pipeline/cityconfig.py --list           # 列出所有城市
    python pipeline/cityconfig.py --check          # 校验全部
    python pipeline/cityconfig.py --check sh gz    # 只校验指定城市
    python pipeline/cityconfig.py --show gz        # 打印某城配置（含派生字段）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CITIES_DIR = Path(__file__).resolve().parent / "cities"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# 字段定义：名字 -> (是否必填, 说明)
# ---------------------------------------------------------------------------

SCHEMA: dict[str, str] = {
    "schema_version": "配置格式版本，目前只支持 1",
    "code": "城市短码，用于 id 前缀与产物目录（sh/gz/cd/hf）",
    "name": "城市全名，如「广州市」",
    "id_prefix": "实体 id 前缀，如 sh → sh-line-2",
    "province": "省份全名，如「广东省」",
    "province_l4": "省份 admin_level=4 的关系 id",
    "province_face": "省份面的取法：{mode: l4|l5_union, names?: [地级市名]}",
    "extra_province_l4": "本城数据还涉及的其它省份 → 该省 admin_level=4 关系 id（归属与边界用）",
    "required_provinces": "归属检查里必须闭合的省份名清单（缺了直接报错；不给则只要求本省）",
    "city": "城市名（用于 OSM network / 归属判定），如「广州市」",
    "city_admin_level": "城市面的 admin_level（4=直辖市，5=地级市）",
    "city_admin_id": "城市面的关系 id",
    "city_names_fallback": "城市名兜底白名单（省面拼不闭合时用），可为空数组",
    "pbfs": "需要的省级 PBF 名（不含 .osm.pbf），按读取顺序",
    "pbf_provinces": "PBF 名 → 省份名（归属与边界用），键必须与 pbfs 一致",
    "province_l5_union": "某些省 L4 拼不闭合时，用这些地级市并集代替 {省名: [市名]}",
    "snapshot": "默认快照键（即 snapshots/<key> 与 data/snapshots/<key> 的目录名）",
    "ref_to_line": "非数字 ref → line_id 的映射（如 磁浮/浦江/APM/广佛线）；数字 ref 自动推导",
    "stop_bbox_whitelist": "允许落在 bbox 外的站名白名单（如跨省延伸段）",
    "network": "OSM network 标签取值，用于把关系筛到本城",
    "route_scope": "制式范围：{routes: [...], ref_overrides: {ref: type}, exclude_refs: [...]}",
    "bbox": "采集矩形框 [西, 南, 东, 北]",
    "scene_bbox": "出图视野框 [西, 南, 东, 北]",
    "km_per_deg": "该纬度下每度经/纬对应的公里数 [km_lon, km_lat]",
    "line_count_expected": "预期线路数（含 APM / 磁浮 / 跨城线）",
    "line_ids": "线路 id 清单（P1a-3 之前可为 null）",
    "loop_start": "环线起点站名 {line_id: 站名}",
    "line_names": "线路显示名的例外 {line_id: 名称}",
    "data_dir": "产物目录，相对仓库根，如 data/processed/shanghai",
    "worksheet_cities": "映射表要覆盖的其它城市（跨城线对端，如 苏州市 / 佛山市）",
    "web": "前端需要的信息 {city_label}",
}

REQUIRED = [
    "schema_version",
    "code",
    "name",
    "id_prefix",
    "province",
    "province_l4",
    "province_face",
    "city",
    "city_admin_level",
    "city_admin_id",
    "pbfs",
    "pbf_provinces",
    "network",
    "route_scope",
    "bbox",
    "scene_bbox",
    "km_per_deg",
    "line_count_expected",
    "data_dir",
    "web",
]

OPTIONAL_DEFAULTS: dict[str, Any] = {
    "city_names_fallback": [],
    "extra_province_l4": {},
    "required_provinces": None,
    "province_l5_union": {},
    "snapshot": "20261101",
    "ref_to_line": {},
    "stop_bbox_whitelist": [],
    "worksheet_cities": [],
    "line_ids": None,
    "loop_start": {},
    "line_names": {},
}

ALLOWED_ROUTES = {"subway", "light_rail", "monorail", "tram"}
ALLOWED_TYPES = {"metro", "lrt", "monorail", "apm", "maglev"}


class ConfigError(Exception):
    """配置内容不合法。消息里带文件路径与字段名。"""


# ---------------------------------------------------------------------------
# 校验小工具
# ---------------------------------------------------------------------------


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _reject(msg: str, errors: list[str]) -> None:
    errors.append(msg)


def _check_bbox(value: Any, field_name: str, errors: list[str]) -> None:
    if not isinstance(value, list) or len(value) != 4:
        _reject(f"{field_name}: 必须是 4 个数 [西, 南, 东, 北]", errors)
        return
    if not all(_is_num(v) for v in value):
        _reject(f"{field_name}: 4 个值都必须是数字", errors)
        return
    w, s, e, n = value
    if not (-180 <= w < e <= 180):
        _reject(f"{field_name}: 经度范围不合法（要 西 < 东，且在 ±180 内）", errors)
    if not (-90 <= s < n <= 90):
        _reject(f"{field_name}: 纬度范围不合法（要 南 < 北，且在 ±90 内）", errors)


def _check_km_per_deg(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or len(value) != 2:
        _reject("km_per_deg: 必须是 [km_lon, km_lat] 两个数", errors)
        return
    if not all(_is_num(v) and v > 0 for v in value):
        _reject("km_per_deg: 两个数都必须为正", errors)


def validate(raw: dict[str, Any], source: str = "<memory>") -> list[str]:
    """校验一份配置字典，返回错误列表（空表示通过）。"""
    errors: list[str] = []

    if not isinstance(raw, dict):
        return [f"{source}: 顶层必须是对象"]

    unknown = sorted(set(raw) - set(SCHEMA))
    if unknown:
        _reject(f"未知字段（拼错了？）：{', '.join(unknown)}", errors)

    _wc = raw.get("worksheet_cities")
    if _wc is not None and (
        not isinstance(_wc, list) or not all(isinstance(x, str) and x for x in _wc)
    ):
        _reject("worksheet_cities: 必须是非空城市名数组", errors)

    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        _reject(f"缺少必填字段：{', '.join(missing)}", errors)

    if errors:
        # 字段都不齐时后面的类型检查意义不大，先把结构问题报出去
        return [f"{source}: {e}" for e in errors]

    if raw["schema_version"] != SCHEMA_VERSION:
        _reject(f"schema_version: 只支持 {SCHEMA_VERSION}，实际 {raw['schema_version']}", errors)

    for key in ("code", "name", "id_prefix", "province", "city", "data_dir"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            _reject(f"{key}: 必须是非空字符串", errors)

    if not _is_int(raw["province_l4"]):
        _reject("province_l4: 必须是整数关系 id", errors)
    if not _is_int(raw["city_admin_id"]):
        _reject("city_admin_id: 必须是整数关系 id", errors)
    if raw["city_admin_level"] not in (4, 5):
        _reject("city_admin_level: 只能是 4 或 5", errors)

    # province_face
    pf = raw["province_face"]
    if not isinstance(pf, dict):
        _reject("province_face: 必须是对象", errors)
    else:
        extra = sorted(set(pf) - {"mode", "names"})
        if extra:
            _reject(f"province_face: 未知字段 {', '.join(extra)}", errors)
        mode = pf.get("mode")
        if mode not in ("l4", "l5_union"):
            _reject("province_face.mode: 只能是 l4 或 l5_union", errors)
        if mode == "l5_union":
            names = pf.get("names")
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
                _reject("province_face.names: l5_union 模式必须给非空的地级市名清单", errors)
        elif "names" in pf:
            _reject("province_face.names: 只有 l5_union 模式才允许给 names", errors)

    # city_names_fallback
    cnf = raw.get("city_names_fallback", [])
    if not isinstance(cnf, list) or not all(isinstance(n, str) and n for n in cnf):
        _reject("city_names_fallback: 必须是非空字符串数组（可为空数组）", errors)

    # extra_province_l4 / required_provinces
    extra_prov = raw.get("extra_province_l4", {})
    if not isinstance(extra_prov, dict):
        _reject("extra_province_l4: 必须是对象 {省名: 关系 id}", errors)
    else:
        for prov, pid in extra_prov.items():
            if not isinstance(prov, str) or not prov:
                _reject("extra_province_l4: 键必须是非空省份名", errors)
            elif not _is_int(pid) or pid <= 0:
                _reject(f"extra_province_l4[{prov}]: 必须是正整数关系 id", errors)
        if raw.get("province") in extra_prov:
            _reject("extra_province_l4: 不要重复本省（本省用 province_l4）", errors)

    req_prov = raw.get("required_provinces")
    if req_prov is not None:
        if not isinstance(req_prov, list) or not req_prov or not all(isinstance(n, str) and n for n in req_prov):
            _reject("required_provinces: 必须是非空省份名数组，或省略", errors)
        elif isinstance(extra_prov, dict):
            known = {raw.get("province")} | set(extra_prov)
            unknown = [n for n in req_prov if n not in known]
            if unknown:
                _reject(f"required_provinces: 这些省份没在 province / extra_province_l4 里出现：{', '.join(unknown)}", errors)

    # pbfs / network
    pbfs = raw["pbfs"]
    if not isinstance(pbfs, list) or not pbfs or not all(isinstance(p, str) and p for p in pbfs):
        _reject("pbfs: 至少要有一个非空字符串", errors)
    pbf_prov = raw.get("pbf_provinces", {})
    if not isinstance(pbf_prov, dict):
        _reject("pbf_provinces: 必须是对象 {pbf 名: 省份名}", errors)
    else:
        if isinstance(pbfs, list):
            missing = [p for p in pbfs if p not in pbf_prov]
            if missing:
                _reject(f"pbf_provinces: 这些 PBF 没给省份：{', '.join(missing)}", errors)
            extra_p = [k for k in pbf_prov if k not in pbfs]
            if extra_p:
                _reject(f"pbf_provinces: 这些 PBF 不在 pbfs 里：{', '.join(extra_p)}", errors)
        for k, v in pbf_prov.items():
            if not isinstance(v, str) or not v:
                _reject(f"pbf_provinces[{k}]: 必须是非空省份名", errors)

    l5u = raw.get("province_l5_union", {})
    if not isinstance(l5u, dict):
        _reject("province_l5_union: 必须是对象 {省名: [地级市名]}", errors)
    else:
        known_provs = {raw.get("province")} | set(extra_prov if isinstance(extra_prov, dict) else {})
        for prov, names in l5u.items():
            if prov not in known_provs:
                _reject(f"province_l5_union[{prov}]: 该省不在 province / extra_province_l4 里", errors)
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
                _reject(f"province_l5_union[{prov}]: 必须是非空地级市名数组", errors)

    snap = raw.get("snapshot")
    if not isinstance(snap, str) or not snap:
        _reject("snapshot: 必须是非空字符串（快照目录名）", errors)

    net = raw["network"]
    if not isinstance(net, list) or not net or not all(isinstance(p, str) and p for p in net):
        _reject("network: 至少要有一个非空字符串", errors)

    # route_scope
    rs = raw["route_scope"]
    if not isinstance(rs, dict):
        _reject("route_scope: 必须是对象", errors)
    else:
        extra = sorted(set(rs) - {"routes", "ref_overrides", "exclude_refs"})
        if extra:
            _reject(f"route_scope: 未知字段 {', '.join(extra)}", errors)
        routes = rs.get("routes")
        if not isinstance(routes, list) or not routes:
            _reject("route_scope.routes: 必须是非空的 route 取值数组", errors)
        else:
            bad = sorted(set(routes) - ALLOWED_ROUTES)
            if bad:
                _reject(f"route_scope.routes: 非法 route 取值 {', '.join(bad)}", errors)
        excluded = rs.get("exclude_refs", [])
        if not isinstance(excluded, list) or not all(isinstance(s, str) and s for s in excluded):
            _reject("route_scope.exclude_refs: 必须是非空字符串数组（可为空）", errors)
        overrides = rs.get("ref_overrides", {})
        if not isinstance(overrides, dict):
            _reject("route_scope.ref_overrides: 必须是对象 {ref: type}", errors)
        else:
            for ref, typ in overrides.items():
                if not isinstance(ref, str) or not ref:
                    _reject("route_scope.ref_overrides: 键必须是非空字符串", errors)
                if typ not in ALLOWED_TYPES:
                    _reject(f"route_scope.ref_overrides[{ref}]: 类型必须是 {sorted(ALLOWED_TYPES)}", errors)

    _check_bbox(raw["bbox"], "bbox", errors)
    _check_bbox(raw["scene_bbox"], "scene_bbox", errors)
    _check_km_per_deg(raw["km_per_deg"], errors)

    # 数量与清单
    lce = raw["line_count_expected"]
    if not _is_int(lce) or lce <= 0:
        _reject("line_count_expected: 必须是正整数", errors)
    line_ids = raw.get("line_ids")
    if line_ids is not None:
        if not isinstance(line_ids, list) or not all(isinstance(s, str) and s for s in line_ids):
            _reject("line_ids: 必须是字符串数组或 null", errors)
        elif len(set(line_ids)) != len(line_ids):
            _reject("line_ids: 有重复值", errors)
        elif _is_int(lce) and len(line_ids) != lce:
            _reject(f"line_ids: 共 {len(line_ids)} 条，与 line_count_expected={lce} 不一致", errors)
        else:
            prefix = f"{raw['id_prefix']}-line-"
            bad = [s for s in line_ids if not s.startswith(prefix)]
            if bad:
                _reject(f"line_ids: 这些不以 {prefix} 开头：{', '.join(bad[:5])}", errors)

    r2l = raw.get("ref_to_line", {})
    if not isinstance(r2l, dict):
        _reject("ref_to_line: 必须是对象 {ref: line_id}", errors)
    else:
        ids = set(line_ids or [])
        for ref, lid in r2l.items():
            if not isinstance(ref, str) or not ref:
                _reject("ref_to_line: 键必须是非空字符串", errors)
            if ids and lid not in ids:
                _reject(f"ref_to_line[{ref}]: {lid} 不在 line_ids 里", errors)

    wl = raw.get("stop_bbox_whitelist", [])
    if not isinstance(wl, list) or not all(isinstance(s, str) and s for s in wl):
        _reject("stop_bbox_whitelist: 必须是非空字符串数组（可为空）", errors)

    for key in ("loop_start", "line_names"):
        val = raw.get(key, {})
        if not isinstance(val, dict):
            _reject(f"{key}: 必须是对象", errors)
        else:
            for k, v in val.items():
                if not isinstance(k, str) or not k:
                    _reject(f"{key}: 键必须是非空字符串", errors)
                if not isinstance(v, str) or not v:
                    _reject(f"{key}[{k}]: 值必须是非空字符串", errors)

    # web
    web = raw["web"]
    if not isinstance(web, dict):
        _reject("web: 必须是对象", errors)
    else:
        extra = sorted(set(web) - {"city_label"})
        if extra:
            _reject(f"web: 未知字段 {', '.join(extra)}", errors)
        if not isinstance(web.get("city_label"), str) or not web["city_label"]:
            _reject("web.city_label: 必须是非空字符串", errors)

    return [f"{source}: {e}" for e in errors]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CityConfig:
    """一份已校验的城市配置。字段与 JSON 一一对应，非必填项填了默认值。"""

    schema_version: int
    code: str
    name: str
    id_prefix: str
    province: str
    province_l4: int
    province_face: dict[str, Any]
    city: str
    city_admin_level: int
    city_admin_id: int
    pbfs: list[str]
    network: list[str]
    route_scope: dict[str, Any]
    bbox: list[float]
    scene_bbox: list[float]
    km_per_deg: list[float]
    line_count_expected: int
    data_dir: str
    web: dict[str, Any]
    city_names_fallback: list[str] = field(default_factory=list)
    extra_province_l4: dict[str, int] = field(default_factory=dict)
    required_provinces: list[str] | None = None
    pbf_provinces: dict[str, str] = field(default_factory=dict)
    ref_to_line: dict[str, str] = field(default_factory=dict)
    stop_bbox_whitelist: list[str] = field(default_factory=list)
    province_l5_union: dict[str, list[str]] = field(default_factory=dict)
    worksheet_cities: list[str] = field(default_factory=list)
    snapshot: str = "20261101"
    line_ids: list[str] | None = None
    loop_start: dict[str, str] = field(default_factory=dict)
    line_names: dict[str, str] = field(default_factory=dict)
    source_path: str = ""

    # --- 便利属性 ---------------------------------------------------------

    @property
    def bbox_tuple(self) -> tuple[float, float, float, float]:
        return tuple(self.bbox)  # type: ignore[return-value]

    @property
    def scene_bbox_tuple(self) -> tuple[float, float, float, float]:
        return tuple(self.scene_bbox)  # type: ignore[return-value]

    @property
    def km_lon(self) -> float:
        return float(self.km_per_deg[0])

    @property
    def km_lat(self) -> float:
        return float(self.km_per_deg[1])

    @property
    def routes(self) -> list[str]:
        return list(self.route_scope["routes"])

    @property
    def ref_overrides(self) -> dict[str, str]:
        return dict(self.route_scope.get("ref_overrides") or {})

    @property
    def exclude_refs(self) -> list[str]:
        """按 ref 排除的关系（route 相同但制式不同的情况，如广州的有轨电车）。"""
        return list(self.route_scope.get("exclude_refs") or [])

    @property
    def province_faces(self) -> dict[int, str]:
        """admin_level=4 关系 id → 省份名（本省 + extra_province_l4 的并集）。"""
        faces = {int(self.province_l4): self.province}
        for prov, pid in self.extra_province_l4.items():
            faces[int(pid)] = prov
        return faces

    @property
    def must_close_provinces(self) -> list[str]:
        """归属检查里必须闭合的省份；默认只要求本省。"""
        return list(self.required_provinces or [self.province])

    @property
    def line_id_prefix(self) -> str:
        return f"{self.id_prefix}-line-"

    def pbf_filenames(self) -> list[str]:
        return [f"{p}-latest.osm.pbf" for p in self.pbfs]

    def raw(self) -> dict[str, Any]:
        """还原成 JSON 友好的字典（含默认值），用于 `--show` 与测试。"""
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "name": self.name,
            "id_prefix": self.id_prefix,
            "province": self.province,
            "province_l4": self.province_l4,
            "province_face": self.province_face,
            "city": self.city,
            "city_admin_level": self.city_admin_level,
            "city_admin_id": self.city_admin_id,
            "city_names_fallback": self.city_names_fallback,
            "extra_province_l4": self.extra_province_l4,
            "required_provinces": self.required_provinces,
            "pbfs": self.pbfs,
            "pbf_provinces": self.pbf_provinces,
            "province_l5_union": self.province_l5_union,
            "snapshot": self.snapshot,
            "ref_to_line": self.ref_to_line,
            "stop_bbox_whitelist": self.stop_bbox_whitelist,
            "network": self.network,
            "route_scope": self.route_scope,
            "bbox": self.bbox,
            "scene_bbox": self.scene_bbox,
            "km_per_deg": self.km_per_deg,
            "line_count_expected": self.line_count_expected,
            "line_ids": self.line_ids,
            "loop_start": self.loop_start,
            "line_names": self.line_names,
            "data_dir": self.data_dir,
            "web": self.web,
        }


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


def list_codes() -> list[str]:
    """返回 `pipeline/cities/` 下所有配置的城市短码（按文件名排序）。"""
    if not CITIES_DIR.is_dir():
        return []
    return sorted(p.stem for p in CITIES_DIR.glob("*.json"))


def load_city(code: str, *, strict: bool = True) -> CityConfig:
    """按短码加载并校验一个城市配置。"""
    path = CITIES_DIR / f"{code}.json"
    if not path.is_file():
        raise ConfigError(f"{path}: 找不到城市配置（可用: {', '.join(list_codes()) or '无'}）")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: JSON 解析失败 —— {exc}") from exc

    errors = validate(raw, source=str(path))
    if errors:
        raise ConfigError("配置校验失败：\n  " + "\n  ".join(errors))

    merged: dict[str, Any] = dict(OPTIONAL_DEFAULTS)
    merged.update(raw)
    merged["source_path"] = str(path)

    cfg = CityConfig(**merged)

    if strict and cfg.code != code:
        raise ConfigError(f"{path}: 文件名是 {code}，但 code 字段是 {cfg.code}")

    return cfg


def load_all() -> dict[str, CityConfig]:
    """加载全部城市配置（任一失败即抛错）。"""
    return {code: load_city(code) for code in list_codes()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_list() -> int:
    codes = list_codes()
    if not codes:
        print(f"(空) 没有在 {CITIES_DIR} 找到任何 *.json")
        return 0
    print(f"{'code':6}{'城市':10}{'省份':8}{'线路':6}{'PBF':28}{'城市面 id'}")
    for code in codes:
        cfg = load_city(code)
        print(
            f"{cfg.code:6}{cfg.name:10}{cfg.province:8}{cfg.line_count_expected:<6}"
            f"{','.join(cfg.pbfs):28}{cfg.city_admin_id}"
        )
    print(f"\n共 {len(codes)} 个城市（{CITIES_DIR}）")
    return 0


def _print_show(code: str) -> int:
    cfg = load_city(code)
    payload = cfg.raw()
    payload["_derived"] = {
        "line_id_prefix": cfg.line_id_prefix,
        "pbf_filenames": cfg.pbf_filenames(),
        "bbox_tuple": cfg.bbox_tuple,
        "scene_bbox_tuple": cfg.scene_bbox_tuple,
        "km_lon": cfg.km_lon,
        "km_lat": cfg.km_lat,
        "routes": cfg.routes,
        "ref_overrides": cfg.ref_overrides,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_check(codes: list[str] | None) -> int:
    targets = codes or list_codes()
    if not targets:
        print(f"(空) 没有在 {CITIES_DIR} 找到任何 *.json")
        return 0

    failures = 0
    for code in targets:
        try:
            cfg = load_city(code)
        except ConfigError as exc:
            failures += 1
            print(f"[失败] {code}\n{exc}")
            continue
        note = "" if cfg.line_ids else "（line_ids 未定，仅校验数量）"
        print(
            f"[通过] {cfg.code} {cfg.name}｜{cfg.province} L4={cfg.province_l4}"
            f"｜城市面 {cfg.city_admin_level}/{cfg.city_admin_id}"
            f"｜{cfg.line_count_expected} 线{note}"
        )

    if failures:
        print(f"\n{failures} 个城市校验失败")
        return 1
    print(f"\n全部通过：{len(targets)} 个城市")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="城市配置的加载与校验（P1a-1.1）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--list", action="store_true", help="列出所有城市")
    group.add_argument("--check", nargs="*", metavar="CODE", help="校验（不给 code 则全部）")
    group.add_argument("--show", metavar="CODE", help="打印某城的完整配置")
    parser.add_argument("--schema", action="store_true", help="打印字段说明")

    args = parser.parse_args(argv)

    if not (args.list or args.check is not None or args.show or args.schema):
        parser.error("需要 --list / --check / --show / --schema 之一")

    if args.schema:
        for key, desc in SCHEMA.items():
            mark = "*" if key in REQUIRED else " "
            print(f"{mark} {key:22}{desc}")
        print("\n* 表示必填")
        return 0

    try:
        if args.list:
            return _print_list()
        if args.check is not None:
            return _run_check(args.check)
        if args.show:
            return _print_show(args.show)
    except ConfigError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
