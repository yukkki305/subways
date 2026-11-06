/**
 * P1a-6.2：城市列表与页面视图参数（服务端用，只在构建期跑）。
 *
 * 为什么读文件而不是把配置 import 进来：
 *   1. `pipeline/cities/<code>.json` 是数据管道的单一事实源，前端不应该再养一份；
 *   2. 它在 `web/` 目录之外，import 会越过打包根，静态导出容易踩到解析差异；
 *   3. 这些值全部在 `next build` 期间确定（generateStaticParams / generateMetadata），
 *      运行时不需要它们，所以读盘没有成本。
 *
 * 站点数等计数来自 `public/data/cities.json`（prebuild 的 sync 产物）；
 * 该文件缺失时退化为城市配置里的线路数，页面仍能构建。
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** 首页固定是上海（`/`），其它城市走 `/<code>/` */
export const HOME_CITY = "sh";

export type CitySummary = {
  code: string;
  /** 界面显示用的简称，例如「上海」「广州」 */
  label: string;
  /** 正式名，例如「广州市」 */
  name: string;
  center: [number, number];
  zoom: number;
  lines: number;
  stations: number | null;
  segments: number | null;
  transfers: number | null;
  /** 原始快照标识，例如 20261101 / p1a-20261103 */
  snapshot: string | null;
  /** 快照对应的日期（2026-11-01），用于 sitemap 的 lastModified 与页脚 */
  asOf: string | null;
  hasBasemap: boolean;
};

type RawConfig = {
  code: string;
  name?: string;
  web?: { city_label?: string };
  scene_bbox?: number[];
  line_count_expected?: number;
};

type IndexEntry = {
  code: string;
  label?: string;
  city?: string;
  lines?: number;
  stations?: number;
  segments?: number;
  transfers?: number;
  snapshot_date?: string;
  has_basemap?: boolean;
};

/** web/ 是构建工作目录，仓库根在上一级 */
function repoRoot(): string {
  return join(process.cwd(), "..");
}

function readJson<T>(path: string): T | null {
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function readConfig(code: string): RawConfig | null {
  return readJson<RawConfig>(join(repoRoot(), "pipeline", "cities", `${code}.json`));
}

function readIndex(): Map<string, IndexEntry> {
  const list = readJson<IndexEntry[]>(join(process.cwd(), "public", "data", "cities.json")) ?? [];
  return new Map(list.map((e) => [e.code, e]));
}

/**
 * 初始视野。真正贴合范围的 fitBounds 在数据加载完之后做，
 * 这里只负责「第一帧不要跑到天上去」：按场景框的经度跨度估一个 zoom。
 * zoom ≈ log2(1256px * 360 / 256 / 经度跨度)，1256 是桌面端典型视口宽。
 */
function viewOf(bbox: number[] | undefined): { center: [number, number]; zoom: number } {
  if (!bbox || bbox.length !== 4) return { center: [121.47, 31.23], zoom: 9.6 };
  const [west, south, east, north] = bbox;
  const center: [number, number] = [(west + east) / 2, (south + north) / 2];
  const span = Math.max(east - west, 0.2);
  const zoom = Math.min(11.2, Math.max(8, Math.log2((1256 * 360) / 256 / span)));
  return { center, zoom: Number(zoom.toFixed(2)) };
}

/**
 * 快照标识 → ISO 日期。上海是 20261101，p1a 批次是 p1a-20261103；
 * 只认尾部 8 位数字，认不出就返回 null（不猜）。
 */
function asOfOf(snapshot: string | null | undefined): string | null {
  if (!snapshot) return null;
  const m = /(\d{8})$/.exec(snapshot);
  if (!m) return null;
  const d = m[1];
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
}

export function citySummary(code: string): CitySummary {
  const cfg = readConfig(code);
  if (!cfg) throw new Error(`没有城市配置：pipeline/cities/${code}.json`);
  const idx = readIndex().get(code);
  const view = viewOf(cfg.scene_bbox);
  const snapshot = idx?.snapshot_date ?? null;
  return {
    code,
    label: idx?.label ?? cfg.web?.city_label ?? cfg.name ?? code,
    name: idx?.city ?? cfg.name ?? code,
    center: view.center,
    zoom: view.zoom,
    lines: idx?.lines ?? cfg.line_count_expected ?? 0,
    stations: idx?.stations ?? null,
    segments: idx?.segments ?? null,
    transfers: idx?.transfers ?? null,
    snapshot,
    asOf: asOfOf(snapshot),
    hasBasemap: idx?.has_basemap ?? code === HOME_CITY,
  };
}

/** 非首页的城市（首页是上海，避免 `/` 与 `/sh/` 重复收录） */
export function publicCityCodes(): string[] {
  const codes = ["gz", "cd", "hf"];
  return codes.filter((code) => readConfig(code) !== null);
}

/** 站点/换乘数在 metadata 与关于面板里用；缺计数时不编数字 */
export function countsText(c: CitySummary): string {
  const parts = [`${c.lines} 条线路`];
  if (c.stations) parts.push(`${c.stations} 站`);
  if (c.segments) parts.push(`${c.segments} 个区间`);
  if (c.transfers !== null) parts.push(`${c.transfers} 条换乘`);
  return parts.join(" · ");
}
