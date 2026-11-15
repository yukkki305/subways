"""P1b 阶段 0.4：从台账 + 行政区数据生成 50 座城的配置骨架。

为什么批量生成：`pipeline/cities/<code>.json` 是 15 个脚本的唯一输入，50 城手写容易
在 bbox / admin id / network 上打错字，而且错了要等到跑完 10 分钟才发现。

生成什么（能自动推的才推，推不出来的留空并打印出来让人补）：
  code / id_prefix / name / city / province / data_dir / web.city_label   ← 台账
  province_l4 / city_admin_id / city_admin_level                          ← 台账
  bbox / scene_bbox                                                       ← 0.4 的 18b 算出的行政面 bbox
  km_per_deg                                                              ← bbox 中心纬度
  pbfs / pbf_provinces / snapshot                                         ← 省份 → extract 名
  province_face                                                           ← 已知拼不闭合的省用 l5_union
  network                                                                 ← admin-ids 里含城市名的 network
  line_count_expected                                                     ← 台账公开线路数

不生成（留给做该城时填）：line_ids、loop_start、line_names、ref_to_line、
worksheet_cities、stop_bbox_whitelist、province_l5_union、required_provinces。

用法：
  python pipeline/21_gen_city_configs.py            # 只生成缺的
  python pipeline/21_gen_city_configs.py --force    # 覆盖已存在的（小心上海回归）
  python pipeline/21_gen_city_configs.py --only nj su
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from cityconfig import validate

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "data" / "cities-ledger.csv"
ADMIN = REPO / "data" / "admin-ids.json"
CITIES = REPO / "pipeline" / "cities"

# 省份全名 → download.openstreetmap.fr 的 extract 名（28 个省，与 0.2 的快照一致）
PROVINCE_PBF = {
    "安徽省": "anhui",
    "北京市": "beijing",
    "重庆市": "chongqing",
    "福建省": "fujian",
    "甘肃省": "gansu",
    "广东省": "guangdong",
    "广西壮族自治区": "guangxi",
    "贵州省": "guizhou",
    "海南省": "hainan",
    "河北省": "hebei",
    "黑龙江省": "heilongjiang",
    "河南省": "henan",
    "湖北省": "hubei",
    "湖南省": "hunan",
    "内蒙古自治区": "inner_mongolia",
    "江苏省": "jiangsu",
    "江西省": "jiangxi",
    "吉林省": "jilin",
    "辽宁省": "liaoning",
    "陕西省": "shaanxi",
    "山东省": "shandong",
    "上海市": "shanghai",
    "山西省": "shanxi",
    "四川省": "sichuan",
    "天津市": "tianjin",
    "新疆维吾尔自治区": "xinjiang",
    "云南省": "yunnan",
    "浙江省": "zhejiang",
}

# 已知省面在单个 extract 里拼不闭合（P1a 实测），只好用「省内地级市并集」当省面：
# 只能硬编码省内地级市清单——admin-ids.json 里没有「市属于哪个省」的父子关系。
UNCLOSED_PROVINCES: dict[str, list[str]] = {
    "广东省": [
        "广州市", "深圳市", "珠海市", "汕头市", "佛山市", "韶关市", "湛江市", "肇庆市",
        "江门市", "茂名市", "惠州市", "梅州市", "汕尾市", "河源市", "阳江市", "清远市",
        "东莞市", "中山市", "潮州市", "揭阳市", "云浮市",
    ],
    "江苏省": [
        "南京市", "无锡市", "徐州市", "常州市", "苏州市", "南通市", "连云港市",
        "淮安市", "盐城市", "扬州市", "镇江市", "泰州市", "宿迁市",
    ],
}

MUNICIPALITIES = {"北京市", "上海市", "天津市", "重庆市"}

SNAPSHOT = "p1b-20261113"


def norm(name: str) -> str:
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "市", "盟", "县"):
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            name = name[: -len(suffix)]
    return name


def find_admin(index: dict, city: str, level: int) -> dict | None:
    """按（去后缀名, 级别）找行政面；找不到返回 None。"""
    return index.get((norm(city), level))


def guess_networks(nets: list[str], city: str) -> list[str]:
    key = norm(city)
    # 有轨电车（D3 排除）与市郊/市域/城际铁路（v1 不进主线）都不算主线网络
    drop = ("有轨", "市郊", "市域", "城际", "捷运")
    hits = [n for n in nets if key and key in n and not any(d in n for d in drop)]
    return hits or [city]


def km_per_deg(bbox: list[float]) -> list[float]:
    lat = (bbox[1] + bbox[3]) / 2
    return [round(111.32 * math.cos(math.radians(lat)), 1), 111.0]


def expand(bbox: list[float], pad: float) -> list[float]:
    w, s, e, n = bbox
    return [round(max(w - pad, -180), 4), round(max(s - pad, -90), 4), round(min(e + pad, 180), 4), round(min(n + pad, 90), 4)]


def build_config(row: dict, admin: dict, index: dict, prov_cities: dict[str, list[str]]) -> dict | None:
    city = row["city"]
    province = row["province"]
    pbf = PROVINCE_PBF.get(province)
    if not pbf:
        print(f"[跳过] {city}：省份「{province}」没有对应的 extract（需补下载）")
        return None
    bucket = admin["provinces"].get(pbf)
    if not bucket:
        print(f"[跳过] {city}：admin-ids.json 里没有 {pbf}")
        return None

    level = 4 if province in MUNICIPALITIES else 5
    entry = find_admin(index, city, level)
    if entry is None or not entry.get("bbox"):
        print(f"[跳过] {city}：找不到带 bbox 的 L{level} 行政面（0.4 的 18b 是否跑过？）")
        return None

    bbox = entry["bbox"]
    city_full = entry["name"] if entry["name"].endswith(("市", "盟", "自治州", "地区")) else f"{city}市"
    nets = list(bucket.get("networks", {}))

    cfg: dict = {
        "schema_version": 1,
        "code": row["slug"],
        "name": city_full,
        "id_prefix": row["slug"],
        "province": province,
        "province_l4": int(row["province_admin_id"]),
        "province_face": {"mode": "l4"},
        "city": city_full,
        "city_admin_level": level,
        "city_admin_id": int(row["city_admin_id"]),
        "city_names_fallback": [],
        "pbfs": [pbf],
        "pbf_provinces": {pbf: province},
        "network": guess_networks(nets, city),
        "route_scope": {
            "routes": ["subway", "light_rail", "monorail"],
            "ref_overrides": {},
            "exclude_refs": [],
        },
        "bbox": expand(bbox, 0.12),
        "scene_bbox": expand(bbox, 0.35),
        "km_per_deg": km_per_deg(bbox),
        "line_count_expected": int(row["lines_public"]),
        "line_ids": None,
        "data_dir": f"data/processed/{row['slug']}",
        "web": {"city_label": city},
        "snapshot": SNAPSHOT,
        "ref_to_line": {},
        "stop_bbox_whitelist": [],
        "worksheet_cities": [],
    }

    if province in UNCLOSED_PROVINCES:
        names = UNCLOSED_PROVINCES[province]
        cfg["province_face"] = {"mode": "l5_union", "names": names}
        cfg["province_l5_union"] = {province: [c for c in names if norm(c) != norm(city)]}
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    rows = list(csv.DictReader(LEDGER.open(encoding="utf8")))
    admin = json.loads(ADMIN.read_text("utf8"))

    index: dict[tuple[str, int], dict] = {}
    prov_cities: dict[str, list[str]] = {}
    for pbf, bucket in admin["provinces"].items():
        for key, level in (("l4", 4), ("l5", 5)):
            for entry in bucket.get(key, []):
                for cand in {entry.get("name", ""), entry.get("name_zh", "")}:
                    if cand:
                        index.setdefault((norm(cand), level), entry)
        # 该 extract 覆盖的省名（用于「省 → 地级市清单」）
        for entry in bucket.get("l4", []):
            prov = entry.get("name", "")
            if prov:
                prov_cities.setdefault(prov, [c.get("name", "") for c in bucket.get("l5", []) if c.get("name")])

    made, skipped, failed = [], [], []
    for row in rows:
        if row["status"] != "pending":
            continue
        if args.only and row["slug"] not in set(args.only):
            continue
        path = CITIES / f"{row['slug']}.json"
        if path.exists() and not args.force:
            skipped.append(row["city"])
            continue
        cfg = build_config(row, admin, index, prov_cities)
        if cfg is None:
            failed.append(row["city"])
            continue
        errors = validate(cfg, source=str(path))
        if errors:
            failed.append(row["city"])
            print(f"[校验失败] {row['city']}：" + "；".join(errors[:3]))
            continue
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", "utf8")
        made.append((row["city"], row["slug"], cfg["line_count_expected"], cfg["km_per_deg"][0], cfg["network"][0]))

    print(f"\n生成 {len(made)} 个配置｜已存在跳过 {len(skipped)}｜失败 {len(failed)}")
    if made:
        print(f"{'城市':<6}{'code':<6}{'线路':<4}{'km/deg':<8}network")
        for city, code, lines, km, net in made:
            print(f"{city:<6}{code:<6}{lines:<4}{km:<8}{net}")
    if failed:
        print("\n需要人工处理：" + "、".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
