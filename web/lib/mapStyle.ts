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

/** 把线数据里的 colour 拼成 MapLibre 的 match 表达式 */
function colorExpression(lineColors: LineColors): unknown {
  const pairs = lineColors.flatMap(([id, color]) => [id, color]);
  return ["match", ["get", "line_id"], ...pairs, "#999999"];
}

export function buildStyle(
  basemap: GeoJSON.FeatureCollection,
  segments: GeoJSON.FeatureCollection,
  lineColors: LineColors,
): StyleSpecification {
  return {
    version: 8,
    // 不给 glyphs：中文由本机 TinySDF 渲染（AGENTS.md 第 6 节，探测 7 实测）
    sources: {
      basemap: { type: "geojson", data: basemap, attribution: "© OpenStreetMap contributors (ODbL-1.0)" },
      segments: { type: "geojson", data: segments },
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
