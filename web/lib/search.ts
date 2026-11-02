/**
 * 站名 / 线路名的最小检索内核（S5-1）。
 *
 * 设计取舍：
 * - 430 座站 + 20 条线，全部放进内存数组，线性打分足够；不引第三方检索库。
 * - 四种匹配：中文子串、拼音全拼、拼音首字母、英文/线路别名。
 * - 排序：分数优先，同分时换乘站优先、线路多者优先、名字短者优先。
 * - 纯函数、无 DOM 依赖，`scripts/test-search.mjs` 直接用 node 跑同一份逻辑。
 *
 * 注意：同名多站的「(2)(3)」后缀规则与 `dataset.ts` 的 displayNames 必须一致，
 * 这里刻意复制了一份十行实现，避免检索内核在 node 里 import 到前端模块（Node 不支持无扩展名相对导入）。
 */

import type { Line, Station } from "./dataset";

export type SearchKind = "station" | "line";

export type SearchDot = { id: string; name: string; colour: string };

export type SearchHit = {
  kind: SearchKind;
  id: string;
  /** 显示名：站名带 (2)(3) 后缀；线路名原样 */
  title: string;
  /** 副行：拼音 · 英文（线路则是类型与区间） */
  subtitle: string;
  /** 结果行上的线路色点 */
  dots: SearchDot[];
  coord?: [number, number];
  score: number;
};

type Entry = {
  kind: SearchKind;
  id: string;
  title: string;
  subtitle: string;
  dots: SearchDot[];
  coord?: [number, number];
  /** 中文检索形式（去空格、去分隔符） */
  zh: string;
  /** 额外中文别名（带后缀的显示名等） */
  zhExtra: string[];
  /** 拉丁别名（小写、去调、去分隔符）：拼音全拼、首字母、英文名、线路号变体 */
  latin: string[];
  isTransfer: boolean;
  lineCount: number;
};

export type SearchIndex = { entries: Entry[] };

const TONE_MARKS = /\p{M}+/gu;

/** 去掉声调符号：ài → ai */
export function stripTones(input: string): string {
  return input.normalize("NFD").replace(TONE_MARKS, "");
}

/** 中文检索形式：小写、去空白、去「·」「・」「-」「_」「'」 */
export function normalizeZh(input: string): string {
  return input.toLowerCase().replace(/[\s·・\-_'’]/g, "");
}

/** 拉丁检索形式：去调、小写、只留 a-z0-9 */
export function normalizeLatin(input: string): string {
  return stripTones(input.toLowerCase()).replace(/[^a-z0-9]/g, "");
}

function pinyinParts(raw: string | null | undefined): { full: string; initials: string } {
  if (!raw) return { full: "", initials: "" };
  const syllables = stripTones(raw)
    .split(/\s+/)
    .map((s) => s.replace(/[^a-zA-Z]/g, ""))
    .filter(Boolean);
  return {
    full: syllables.join(""),
    initials: syllables.map((s) => s[0] ?? "").join(""),
  };
}

/** 与 dataset.ts 的 displayNames 同规则：同名多站按 id 后缀给 (1)(2) */
export function displayNameOf(station: Station, sameNameCount: number): string {
  if (sameNameCount <= 1) return station.name;
  const m = /-(\d+)$/.exec(station.id);
  return `${station.name}(${m ? m[1] : "1"})`;
}

function stationEntry(station: Station, linesById: Map<string, Line>, sameNameCount: number): Entry {
  const title = displayNameOf(station, sameNameCount);
  const py = pinyinParts(station.name_pinyin);
  const latin = [py.full, py.initials];
  if (station.name_en) latin.push(normalizeLatin(station.name_en));
  const dots: SearchDot[] = station.lines
    .map((id) => linesById.get(id))
    .filter((l): l is Line => Boolean(l))
    .map((l) => ({ id: l.id, name: l.name, colour: l.colour }));
  return {
    kind: "station",
    id: station.id,
    title,
    subtitle: [station.name_pinyin, station.name_en].filter(Boolean).join(" · "),
    dots,
    coord: station.coord,
    zh: normalizeZh(station.name),
    zhExtra: [normalizeZh(title)],
    latin: [...new Set(latin.filter(Boolean))],
    isTransfer: station.is_transfer,
    lineCount: station.lines.length,
  };
}

function lineEntry(line: Line): Entry {
  const digits = (line.name.match(/\d+/) ?? [])[0] ?? "";
  const latin = [normalizeLatin(line.name_en), normalizeLatin(line.name)];
  if (digits) {
    latin.push(digits, `line${digits}`, `l${digits}`, `${digits}hao`, `${digits}haoxian`);
  }
  const branchCount = line.branches?.length ?? 1;
  return {
    kind: "line",
    id: line.id,
    title: line.name,
    subtitle: [line.name_en, `${line.type} · ${branchCount} 条交路`].filter(Boolean).join(" · "),
    dots: [{ id: line.id, name: line.name, colour: line.colour }],
    zh: normalizeZh(line.name),
    zhExtra: digits ? [normalizeZh(digits)] : [],
    latin: [...new Set(latin.filter(Boolean))],
    isTransfer: false,
    lineCount: 0,
  };
}

export function buildIndex(stations: Station[], lines: Line[]): SearchIndex {
  const linesById = new Map(lines.map((l) => [l.id, l] as const));
  const sameName = new Map<string, number>();
  for (const s of stations) sameName.set(s.name, (sameName.get(s.name) ?? 0) + 1);

  const entries: Entry[] = [
    ...stations.map((s) => stationEntry(s, linesById, sameName.get(s.name) ?? 1)),
    ...lines.map(lineEntry),
  ];
  return { entries };
}

const HAS_CJK = /[\u3400-\u9fff]/;

function scoreAgainst(value: string, query: string, exact: number, prefix: number, contain: number): number {
  if (!value || !query) return 0;
  if (value === query) return exact;
  if (value.startsWith(query)) return prefix;
  if (value.includes(query)) return contain;
  return 0;
}

function scoreEntry(entry: Entry, qZh: string, qLatin: string): number {
  let best = 0;
  if (qZh) {
    best = Math.max(best, scoreAgainst(entry.zh, qZh, 120, 96, 74));
    for (const alias of entry.zhExtra) {
      best = Math.max(best, scoreAgainst(alias, qZh, 114, 92, 71));
    }
  }
  if (qLatin) {
    // 单字母查询不做包含匹配，否则 "a" 会把半座城翻出来
    const contain = qLatin.length >= 2 ? 58 : 0;
    for (const alias of entry.latin) {
      best = Math.max(best, scoreAgainst(alias, qLatin, 110, 88, contain));
    }
  }
  if (best === 0) return 0;
  // 同分时的优先级做成加数，避免额外比较分支
  if (entry.isTransfer) best += 8;
  best += Math.min(entry.lineCount, 4) * 2;
  return best;
}

function compare(a: SearchHit, b: SearchHit): number {
  if (b.score !== a.score) return b.score - a.score;
  if (a.kind !== b.kind) return a.kind === "station" ? -1 : 1;
  if (a.dots.length !== b.dots.length) return b.dots.length - a.dots.length;
  if (a.title.length !== b.title.length) return a.title.length - b.title.length;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

export function search(index: SearchIndex, rawQuery: string, limit = 8): SearchHit[] {
  const raw = (rawQuery ?? "").trim();
  if (!raw) return [];
  const qZh = normalizeZh(raw);
  const qLatin = HAS_CJK.test(raw) ? "" : normalizeLatin(raw);
  if (!qZh && !qLatin) return [];

  const hits: SearchHit[] = [];
  for (const entry of index.entries) {
    const score = scoreEntry(entry, qZh, qLatin);
    if (score <= 0) continue;
    hits.push({
      kind: entry.kind,
      id: entry.id,
      title: entry.title,
      subtitle: entry.subtitle,
      dots: entry.dots,
      coord: entry.coord,
      score,
    });
  }
  hits.sort(compare);
  return hits.slice(0, limit);
}
