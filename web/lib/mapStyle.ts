import type { StyleSpecification } from "maplibre-gl";

/** 底图与线路的视觉常量（颜色只在 lib 里定义一次，组件不硬编码） */
export const PALETTE = {
  paper: "#F4F1EA", // 背景＝陆地（P0 不画陆地填充面，见探测 8 决策）
  water: "#D7E4EF",
  waterLine: "#C6D8E8",
  coastline: "#BFC9D2",
  district: "#DBD5C8",
  province: "#B4AC9C",
} as const;

export type LineColors = Array<[string, string]>;

/** 站点数据的原始形状（只列用到的字段） */
export type StationRecord = {
  id: string;
  name: string;
  name_en: string | null;
  coord: [number, number];
  lines: string[];
  is_transfer: boolean;
  merge?: { method?: string; spread_m?: number; needs_review?: boolean };
};

/** 站点对象数组 → GeoJSON（MapLibre 只吃 FeatureCollection） */
export function stationsToGeoJSON(stations: StationRecord[]): GeoJSON.FeatureCollection {
  // 同名多站（ADR R4 中 >300 m 不合并的那些）在地图上会显示成两个一样的名字，
  // 加 (1)(2) 后缀区分；只改显示名，name 字段保持 OSM 原值。
  const groups = new Map<string, StationRecord[]>();
  for (const s of stations) {
    const list = groups.get(s.name) ?? [];
    list.push(s);
    groups.set(s.name, list);
  }
  const display = new Map<string, string>();
  for (const [name, list] of groups) {
    if (list.length === 1) {
      display.set(list[0].id, name);
      continue;
    }
    // 按经度排序，保证每次渲染的编号一致
    [...list]
      .sort((a, b) => a.coord[0] - b.coord[0] || a.coord[1] - b.coord[1])
      .forEach((s, i) => display.set(s.id, `${name}(${i + 1})`));
  }

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
        lines: s.lines.join(" "),
        needs_review: s.merge?.needs_review ?? false,
      },
    })),
  } as GeoJSON.FeatureCollection;
}

/** 把线数据里的 colour 拼成 MapLibre 的 match 表达式 */
function colorExpression(lineColors: LineColors): unknown {
  const pairs = lineColors.flatMap(([id, color]) => [id, color]);
  return ["match", ["get", "line_id"], ...pairs, "#999999"];
}

export function buildStyle(
  basemap: GeoJSON.FeatureCollection,
  segments: GeoJSON.FeatureCollection,
  stations: GeoJSON.FeatureCollection,
  lineColors: LineColors,
): StyleSpecification {
  return {
    version: 8,
    // 不给 glyphs：中文由本机 TinySDF 渲染（AGENTS.md 第 6 节，探测 7 实测）
    sources: {
      basemap: { type: "geojson", data: basemap, attribution: "© OpenStreetMap contributors (ODbL-1.0)" },
      segments: { type: "geojson", data: segments },
      stations: { type: "geojson", data: stations },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": PALETTE.paper },
      },
      {
        id: "water-fill",
        type: "fill",
        source: "basemap",
        filter: ["==", ["get", "layer"], "water"],
        paint: { "fill-color": PALETTE.water, "fill-opacity": 1 },
      },
      {
        id: "coastline",
        type: "line",
        source: "basemap",
        filter: ["==", ["get", "layer"], "coastline"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": PALETTE.coastline,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 12, 0.9, 16, 1.6],
        },
      },
      {
        id: "water-line",
        type: "line",
        source: "basemap",
        filter: ["==", ["get", "layer"], "water_line"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": PALETTE.waterLine,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.8, 11, 1.6, 14, 3.4, 17, 7],
        },
      },
      {
        id: "district-line",
        type: "line",
        source: "basemap",
        filter: ["==", ["get", "layer"], "district_boundary"],
        paint: {
          "line-color": PALETTE.district,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.4, 12, 0.8, 16, 1.2],
        },
      },
      {
        id: "province-line",
        type: "line",
        source: "basemap",
        filter: ["==", ["get", "layer"], "province_boundary"],
        paint: {
          "line-color": PALETTE.province,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.0, 12, 1.7, 16, 2.4],
          "line-dasharray": [4, 2],
        },
      },
      {
        id: "metro-line",
        type: "line",
        source: "segments",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": colorExpression(lineColors) as never,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 10, 1.8, 12, 2.6, 14, 3.6, 17, 6],
          "line-opacity": 1,
        },
      },

      // ——— 车站：圆点在线的上面，换乘站更大更重 ———
      {
        id: "station-dot",
        type: "circle",
        source: "stations",
        minzoom: 10,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 1.6, 12, 2.4, 14, 3.4, 17, 4.6],
          "circle-color": "#FFFFFF",
          "circle-stroke-color": "#5A5A5A",
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 10, 0.8, 14, 1.2, 17, 1.6],
        },
      },
      {
        id: "station-dot-transfer",
        type: "circle",
        source: "stations",
        minzoom: 10,
        filter: ["==", ["get", "is_transfer"], true],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2.6, 12, 3.6, 14, 5.0, 17, 6.6],
          "circle-color": "#FFFFFF",
          "circle-stroke-color": "#2B2B2B",
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 10, 1.3, 14, 1.9, 17, 2.4],
        },
      },

      // ——— 站名：zoom≥11 才出现，碰撞自动避让 ———
      {
        id: "station-label",
        type: "symbol",
        source: "stations",
        minzoom: 11,
        layout: {
          "text-field": ["get", "name_display"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 11, 10.5, 14, 12.5, 17, 14],
          "text-anchor": "left",
          "text-offset": [0.75, 0],
          "text-padding": 3,
          "text-max-width": 8,
          "text-allow-overlap": false,
          "text-ignore-placement": false,
          "symbol-sort-key": ["get", "line_count"],
        },
        paint: {
          "text-color": "#2E2E2E",
          "text-halo-color": "rgba(244, 241, 234, 0.92)",
          "text-halo-width": 1.6,
          "text-halo-blur": 0.2,
        },
      },
    ],
  };
}

/** 只用线路数据算出视野（不含底图，底图范围比线路大得多） */
export function boundsOf(segments: GeoJSON.FeatureCollection): [[number, number], [number, number]] | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const visit = (coords: unknown): void => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === "number" && typeof coords[1] === "number") {
      const [x, y] = coords as [number, number];
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
      return;
    }
    for (const c of coords) visit(c);
  };
  for (const f of segments.features) if (f.geometry && "coordinates" in f.geometry) visit(f.geometry.coordinates);
  if (!Number.isFinite(minX)) return null;
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}
