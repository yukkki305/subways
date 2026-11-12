/**
 * UX 阶段 3：城市总览页的 SVG 网络轮廓缩略图（构建期生成，服务端专用）。
 *
 * 为什么是 SVG 而不是截图/瓦片：
 *   1. 每张只有几十 KB 的文本，gzip 后更小，而且天然矢量、任意缩放清晰；
 *   2. 不引入截图工具链，`next build` 时顺手算出来，产物可 diff；
 *   3. 只画线路几何（不画底图），与总览页「看网络形状」的目的一致。
 *
 * 投影：用等距圆柱（x=经度、y=-纬度）而不是墨卡托 —— 城市尺度（<1.5°）两者差别
 * 小于 0.5%，等距圆柱的好处是公式一眼能看懂、不需要引入投影库。
 * 每座城独立归一化到固定 viewBox，所以四个框里的城市看起来一样大。
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * 缩略图是 10:7 的横向框（卡片里 line-height 更紧凑），不是正方形：
 * 四座城的网络都横向铺开得比纵向长，正方形会在上下浪费大量留白。
 */
const VB_W = 1000;
const VB_H = 700;
const PAD = 34;

type SegmentFile = {
  features: Array<{
    geometry: { type: string; coordinates: number[][][] | number[][] } | null;
    properties: { line_id?: string; geometry_source?: string } | null;
  }>;
};

type LinesFile = { lines: Array<{ id: string; colour: string; name: string; type: string }> };

function readJson<T>(path: string): T | null {
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return null;
  }
}

type Pt = [number, number];

/**
 * 一条线 → 一个 path。
 * 两处降体积：①按「离上一个保留点 ≥ MIN_STEP 个 viewBox 单位」抽稀——缩略图只有
 * ~240 px 宽，1000 单位里的 2.5 单位连 1 px 都不到，抽掉看不出来；②坐标取整。
 * 4 条线合计从 890 KB 降到 ~60 KB 全在这两步。
 */
const MIN_STEP = 2.5;

function pathOf(rings: Pt[][], project: (p: Pt) => Pt): string {
  const out: string[] = [];
  for (const ring of rings) {
    if (ring.length < 2) continue;
    const pts: Pt[] = [];
    for (const p of ring) {
      const q = project(p);
      const last = pts[pts.length - 1];
      if (!last || Math.hypot(q[0] - last[0], q[1] - last[1]) >= MIN_STEP) pts.push(q);
    }
    // 端点总要在：抽稀可能把最后一个点丢掉，视觉上会少一截
    const tail = project(ring[ring.length - 1]);
    const last = pts[pts.length - 1];
    if (!last || Math.hypot(tail[0] - last[0], tail[1] - last[1]) > 1) pts.push(tail);
    if (pts.length < 2) continue;
    out.push(
      pts
        .map(([x, y], i) => `${i === 0 ? "M" : "L"}${Math.round(x)} ${Math.round(y)}`)
        .join(""),
    );
  }
  return out.join("");
}

export type ThumbLine = { id: string; colour: string; name: string; type: string; d: string };

export type CityThumb = {
  code: string;
  /** 每条线一个 path，颜色取官方色（D6：与地图同色，不另配色） */
  lines: ThumbLine[];
  /** 该城实际用于归一化的经纬跨度，调试与文档用 */
  span: [number, number];
};

/**
 * 读该城 segment.geojson + lines.json，输出可直接塞进 <svg> 的路径。
 *
 * 失败时返回 null（总览页显示占位块而不是让整页构建失败）：
 * 数据没同步、文件损坏都属于「可以晚点再修」，不该阻塞发布。
 */
export function cityThumb(code: string): CityThumb | null {
  const dir = join(process.cwd(), "public", "data", code);
  const seg = readJson<SegmentFile>(join(dir, "segment.geojson"));
  const linesFile = readJson<LinesFile>(join(dir, "lines.json"));
  if (!seg || !linesFile) return null;

  const colourOf = new Map(linesFile.lines.map((l) => [l.id, l.colour]));
  const metaOf = new Map(linesFile.lines.map((l) => [l.id, l]));

  // 1) 先收集包围盒，再归一化
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const byLine = new Map<string, Pt[][]>();

  for (const f of seg.features) {
    const lineId = f.properties?.line_id;
    const g = f.geometry;
    if (!lineId || !g || !("coordinates" in g)) continue;
    const rings: Pt[][] =
      g.type === "LineString" ? [(g.coordinates as number[][]).map((c) => [c[0], c[1]] as Pt)] : [];
    if (g.type === "MultiLineString") {
      for (const part of g.coordinates as number[][][]) rings.push(part.map((c) => [c[0], c[1]] as Pt));
    }
    if (rings.length === 0) continue;
    const exist = byLine.get(lineId);
    if (exist) exist.push(...rings);
    else byLine.set(lineId, rings);
    for (const ring of rings) {
      for (const [x, y] of ring) {
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (!Number.isFinite(minX)) return null;

  // 2) 等比缩放到 1000×700 的框里（保留形状，不拉伸）
  const spanX = Math.max(maxX - minX, 1e-6);
  const spanY = Math.max(maxY - minY, 1e-6);
  const scale = Math.min((VB_W - PAD * 2) / spanX, (VB_H - PAD * 2) / spanY);
  const offX = (VB_W - spanX * scale) / 2;
  const offY = (VB_H - spanY * scale) / 2;
  const project = (p: Pt): Pt => [offX + (p[0] - minX) * scale, offY + (maxY - p[1]) * scale];

  // 3) 稳定排序：先按线路 id，保证同样输入得到同样输出（便于 diff 与缓存）
  const lines: ThumbLine[] = [...byLine.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([id, rings]) => {
      const m = metaOf.get(id);
      const d = pathOf(rings, project);
      if (!d) return [];
      return [{ id, colour: colourOf.get(id) ?? "#999999", name: m?.name ?? id, type: m?.type ?? "metro", d }];
    });

  return { code, lines, span: [Number(spanX.toFixed(4)), Number(spanY.toFixed(4))] };
}
