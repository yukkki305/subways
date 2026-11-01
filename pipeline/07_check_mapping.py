#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S2-2 第二步的校验器：检查人工填好的关系映射表是否满足 ADR R1 的判据。

校验项（任一不过则以非零码退出）：
1. CSV 行数与 S1-5 的上海子集一致（65 行）
2. `decide` 只允许 `保留` / `合并` / `丢弃`，或留空（留空 = 待决策，仅计入 pending）
3. 期望的 20 条线路都在，且每条 line 恰好有一个 `保留` 且 `target_branch` 以 `-main` 结尾
4. 每条 `丢弃` 都有 `note`（写理由）
5. 每条 `合并` 指向一个真实存在的 `保留` branch，且其站序是该 branch 站序的子集
6. 每个 branch 至少来自 1 条 `保留` 关系

用法：
    $env:PYTHONUTF8 = '1'
    E:\\subway-data\\venv\\Scripts\\python.exe pipeline\\07_check_mapping.py
    # 指定别的表
    ... pipeline\\07_check_mapping.py --csv data\\manual\\shanghai-relation-mapping.csv --allow-pending
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSV_DEFAULT = REPO / "data" / "manual" / "shanghai-relation-mapping.csv"
MD_OUT = REPO / "docs" / "mappings" / "shanghai-relations.md"
INDEX = REPO / "data" / "processed" / "relation-index.json"

EXPECTED_LINES = [f"sh-line-{i}" for i in range(1, 19)] + ["sh-line-pujiang", "sh-line-maglev"]
DECIDES = {"保留", "合并", "丢弃"}

# ref → line id：只用于把「待决策」的行归到线路上（11 号线待用户定，故也在此表）
REF_TO_LINE = {str(i): f"sh-line-{i}" for i in range(1, 19)}
REF_TO_LINE.update({"浦江": "sh-line-pujiang", "磁浮": "sh-line-maglev"})


def write_md(rows, by_line, branch_stops, pending, sh_total) -> Path:
    """把 CSV（含人工判定）重渲成人可读文档。单一事实来源仍是 CSV。"""
    keeps = [r for r in rows if r["decide"] == "保留"]
    merges = [r for r in rows if r["decide"] == "合并"]
    drops = [r for r in rows if r["decide"] == "丢弃"]
    merged_under: dict[str, list[dict]] = defaultdict(list)
    for r in merges:
        merged_under[r["target_branch"]].append(r)

    out: list[str] = [
        "# 上海关系映射表（S2-2）",
        "",
        "> 本文件由 `pipeline/07_check_mapping.py --write-md` 从 "
        "`data/manual/shanghai-relation-mapping.csv` 渲染，**请勿手改**；改 CSV 后重跑。",
        "",
        "## 汇总",
        "",
        f"- 上海子集关系 **{sh_total}** 条 → 保留 **{len(keeps)}**、合并 **{len(merges)}**、丢弃 **{len(drops)}**、待决策 **{len(pending)}**",
        f"- 产出 **{len(by_line)}** 条 line / **{sum(len(v) for v in by_line.values())}** 个 branch（含 `-main` 与支线）",
        "- 规则依据：`docs/decisions/0001-modeling-rules.md` 的 R1（线路与支线）、R2（ID）、R3（环线）",
        "",
        "### 线路 → branch",
        "",
        "| 线路 | branch | 来源关系 | 站数 | 并入的关系 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for lid in EXPECTED_LINES:
        for r in sorted(by_line.get(lid, []), key=lambda x: x["target_branch"]):
            b = r["target_branch"]
            under = merged_under.get(b) or []
            under_txt = "—"
            if under:
                ids = "、".join("`{}`".format(x["relation_id"]) for x in under)
                under_txt = f"{len(under)} 条（{ids}）"
            out.append(f"| `{lid}` | `{b}` | `{r['relation_id']}` | {len(branch_stops[b])} | {under_txt} |")

    if pending:
        out += ["", "### 待决策", "", "| 关系 | ref | 名称 | 站数 | 归属市 |", "| --- | --- | --- | --- | --- |"]
        for r in pending:
            out.append(f"| `{r['relation_id']}` | {r['ref']} | {r['name']} | {r['unique_stops']} | {r['city'] or '—'} |")

    out += ["", "## 丢弃关系", "", "| 关系 | 名称 | 理由 |", "| --- | --- | --- |"]
    for r in drops:
        out.append(f"| `{r['relation_id']}` | {r['name']} | {r['note']} |")

    out += [
        "",
        "## 全部关系明细",
        "",
        "| 关系 | 名称 | 制式 | ref | 站数 | 归属市 | 判定 | 目标 branch | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        out.append(
            f"| `{r['relation_id']}` | {r['name']} | {r['transit_type']} | {r['ref'] or '—'} | "
            f"{r['unique_stops']} | {r['city'] or '—'} | {r['decide'] or '**待定**'} | "
            f"{('`' + r['target_branch'] + '`') if r['target_branch'] else '—'} | {r['note'] or '—'} |"
        )

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    return MD_OUT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(CSV_DEFAULT))
    ap.add_argument("--allow-pending", action="store_true", help="允许留空的行（待决策）存在")
    ap.add_argument("--write-md", action="store_true", help="从 CSV 重渲 docs/mappings/shanghai-relations.md")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    sh = [r for r in index["relations"] if "shanghai" in (r.get("provinces") or [])]
    stops_of = {str(r["id"]): set(r.get("stop_names") or []) for r in sh}

    errors: list[str] = []
    warnings: list[str] = []

    # 1 行数
    if len(rows) != len(sh):
        errors.append(f"行数 {len(rows)} ≠ S1-5 上海子集 {len(sh)}")

    # 2 取值合法 + 待决策统计
    pending = [r for r in rows if not r["decide"].strip()]
    for r in rows:
        d = r["decide"].strip()
        if d and d not in DECIDES:
            errors.append(f"关系 {r['relation_id']} 的 decide 非法：{d!r}")
    if pending and not args.allow_pending:
        errors.append(f"还有 {len(pending)} 行未决策：" + "、".join(r["relation_id"] for r in pending))

    keeps = [r for r in rows if r["decide"] == "保留"]
    merges = [r for r in rows if r["decide"] == "合并"]
    drops = [r for r in rows if r["decide"] == "丢弃"]

    # 待决策的行涉及的线路：允许这些 line 暂时缺 main（--allow-pending 时不算失败）
    ref_to_line = {k: v for k, v in REF_TO_LINE.items()}
    pending_lines = {ref_to_line[r["ref"]] for r in pending if r["ref"] in ref_to_line}

    # 3 每条 line 恰好一个 main 保留
    by_line: dict[str, list[dict]] = defaultdict(list)
    for r in keeps:
        by_line[r["target_line"]].append(r)
    for lid in EXPECTED_LINES:
        got = by_line.get(lid, [])
        if lid in pending_lines and args.allow_pending:
            warnings.append(f"{lid} 尚无保留关系（待决策 {len(pending)} 行中的一部分）")
            continue
        if not got:
            errors.append(f"{lid} 没有任何保留关系")
        mains = [r for r in got if r["target_branch"].endswith("-main")]
        if len(mains) != 1:
            errors.append(f"{lid} 的 main branch 数量是 {len(mains)}，应为 1")
    extra = set(by_line) - set(EXPECTED_LINES)
    if extra:
        errors.append(f"出现未预期线路：{'、'.join(sorted(extra))}")

    # 4 丢弃必须有理由
    for r in drops:
        if not r["note"].strip():
            errors.append(f"关系 {r['relation_id']} 被丢弃但没写理由")

    # 5 合并指向真实 branch，且站序是子集
    branch_stops: dict[str, set] = defaultdict(set)
    branch_owner: dict[str, str] = {}
    for r in keeps:
        branch_stops[r["target_branch"]] |= stops_of.get(r["relation_id"], set())
        branch_owner[r["target_branch"]] = r["relation_id"]
    for r in merges:
        b = r["target_branch"]
        if b not in branch_stops:
            errors.append(f"关系 {r['relation_id']} 合并到 {b or '(空)'}，但该 branch 不存在")
            continue
        mine = stops_of.get(r["relation_id"], set())
        if mine and not mine <= branch_stops[b]:
            only = sorted(mine - branch_stops[b])
            errors.append(
                f"关系 {r['relation_id']} 的站序不是 {b} 的子集，多出 {len(only)} 站：{'、'.join(only[:5])}"
            )

    # 6 每个 branch 至少 1 条保留
    if any(not v for v in branch_owner.values()):
        errors.append("存在没有保留关系的 branch")

    # ---- 报表 ----
    print(f"表：{csv_path.relative_to(REPO) if csv_path.is_relative_to(REPO) else csv_path}")
    print(f"行数 {len(rows)}｜保留 {len(keeps)}｜合并 {len(merges)}｜丢弃 {len(drops)}｜待决策 {len(pending)}")
    print()
    print(f"{'线路':<16}{'branch':<26}{'来源':>5}{'站数':>6}")
    print("-" * 58)
    for lid in EXPECTED_LINES:
        for r in sorted(by_line.get(lid, []), key=lambda x: x["target_branch"]):
            b = r["target_branch"]
            print(f"{lid:<16}{b:<26}{r['relation_id']:>5}{len(branch_stops[b]):>6}")
    if pending:
        print()
        print("待决策：")
        for r in pending:
            print(f"  {r['relation_id']:>9}  ref={r['ref']:<4} {r['name']}  （{r['unique_stops']} 站，{r['city'] or '归属空'}）")

    if args.write_md:
        md_path = write_md(rows, by_line, branch_stops, pending, len(sh))
        print()
        print(f"重渲 {md_path.relative_to(REPO)}")

    print()
    if warnings:
        for w in warnings:
            print(f"[提示] {w}")
    if errors:
        print(f"[失败] {len(errors)} 项：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("[通过] 六项校验全部满足 ADR R1。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
