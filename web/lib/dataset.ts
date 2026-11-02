/** 前端用到的数据形状（只列组件真正读的字段，多余字段不管） */

export type LineBranch = {
  id: string;
  is_main: boolean;
  is_loop: boolean;
  loop_start: string | null;
  from: string | null;
  to: string | null;
  stop_count: number;
  stops: string[];
  service_levels?: string[];
};

export type Line = {
  id: string;
  name: string;
  name_en: string;
  colour: string;
  type: string;
  operator: string | null;
  opened: string | null;
  length_km: number;
  length_km_official: number | null;
  colour_official_name: string | null;
  colour_source: string;
  branches: LineBranch[];
  source: string;
  source_license: string;
  as_of: string;
};

export type StationSlot = {
  line: string;
  branch: string;
  seq: number;
  node: number;
  coord: [number, number];
};

export type Station = {
  id: string;
  name: string;
  name_en: string | null;
  name_pinyin: string;
  city: string;
  coord: [number, number];
  lines: string[];
  branches: string[];
  is_transfer: boolean;
  slots: StationSlot[];
  merge?: { method?: string; slot_count?: number; spread_m?: number; needs_review?: boolean };
  source: string;
  source_license: string;
  as_of: string;
};

export type Transfer = {
  id: string;
  name: string;
  station_a: string;
  station_b: string;
  lines_a: string[];
  lines_b: string[];
  dist_m: number;
  type: string;
  type_confidence: string;
  type_note: string | null;
  walk_minutes: number | null;
  needs_review: boolean;
};

export type Dataset = {
  lines: Line[];
  stations: Station[];
  transfers: Transfer[];
};

export function linesById(lines: Line[]): Map<string, Line> {
  return new Map(lines.map((l) => [l.id, l]));
}

/** 某站的换乘记录（两侧都算），并给出「对面是哪个站」 */
export function transfersOf(transfers: Transfer[], stationId: string): Array<{ t: Transfer; otherId: string }> {
  const out: Array<{ t: Transfer; otherId: string }> = [];
  for (const t of transfers) {
    if (t.station_a === stationId) out.push({ t, otherId: t.station_b });
    else if (t.station_b === stationId) out.push({ t, otherId: t.station_a });
  }
  return out;
}

/** 该站在某 branch 站的上一站/下一站（站序来自 lines.json，1 基） */
export function neighborsOf(
  station: Station,
  lines: Line[],
): Array<{ lineId: string; branchId: string; seq: number; prev: string | null; next: string | null; total: number; isLoop: boolean }> {
  const byId = linesById(lines);
  const out: Array<{ lineId: string; branchId: string; seq: number; prev: string | null; next: string | null; total: number; isLoop: boolean }> = [];
  for (const slot of station.slots) {
    const line = byId.get(slot.line);
    const branch = line?.branches.find((b) => b.id === slot.branch);
    if (!line || !branch) continue;
    const stops = branch.stops;
    const i = slot.seq - 1;
    out.push({
      lineId: line.id,
      branchId: branch.id,
      seq: slot.seq,
      prev: i > 0 ? stops[i - 1] : branch.is_loop ? stops[stops.length - 1] : null,
      next: i < stops.length - 1 ? stops[i + 1] : branch.is_loop ? stops[0] : null,
      total: stops.length,
      isLoop: branch.is_loop,
    });
  }
  return out;
}

/** 同名多站时给「(2)(3)」后缀，规则与地图标签保持一致 */
export function displayNames(stations: Station[]): Map<string, string> {
  const groups = new Map<string, Station[]>();
  for (const s of stations) {
    const list = groups.get(s.name) ?? [];
    list.push(s);
    groups.set(s.name, list);
  }
  const out = new Map<string, string>();
  for (const [name, list] of groups) {
    if (list.length === 1) {
      out.set(list[0].id, name);
      continue;
    }
    // 编号跟着 id 走（-2/-3 是构建时加的），保证地图标签与站 id 说的同一个数字；
    // 未带后缀的那个就是 (1)。
    for (const s of list) {
      const m = /-(\d+)$/.exec(s.id);
      out.set(s.id, `${name}(${m ? m[1] : "1"})`);
    }
  }
  return out;
}

/** 站点 → GeoJSON；properties 里带 name_display，地图标签与详情面板共用同一套消歧规则 */
export function stationsToGeoJSON(stations: Station[]): GeoJSON.FeatureCollection {
  const display = displayNames(stations);
  return {
    type: "FeatureCollection",
    features: stations.map((s) => ({
      type: "Feature",
      id: s.id,
      geometry: { type: "Point", coordinates: s.coord },
      properties: {
        id: s.id,
        name: s.name,
        name_display: display.get(s.id) ?? s.name,
        name_en: s.name_en,
        is_transfer: s.is_transfer,
        line_count: s.lines.length,
        needs_review: s.merge?.needs_review ?? false,
      },
    })),
  } as GeoJSON.FeatureCollection;
}
