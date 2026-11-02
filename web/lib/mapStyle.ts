import type { LayerSpecification, StyleSpecification } from "maplibre-gl";

/** 底图与线路的视觉常量（颜色只在 lib 里定义一次，组件不硬编码） */
import { FONT_STACK } from "./typography";

export const PALETTE = {
  paper: "#F4F1EA", // 背景＝陆地（P0 不画陆地填充面，见探测 8 决策）
  water: "#D7E4EF",
  waterLine: "#C6D8E8",
  coastline: "#BFC9D2",
  district: "#DBD5C8",
  province: "#B4AC9C",
  ink: "#2B2B2B",
} as const;

export type LineColors = Array<[string, string]>;

/** 把线数据里的 colour 拼成 MapLibre 的 match 表达式 */
function colorExpression(lineColors: LineColors): unknown {
  const pairs = lineColors.flatMap(([id, color]) => [id, color]);
  return ["match", ["get", "line_id"], ...pairs, "#999999"];
}

/** 中英双语站名图层（S4-2）：中文一行 + 英文小字一行，靠 format 的第二段调字号和颜色 */
function bilingualLabel(
  id: string,
  minzoom: number,
  lengthFilter: unknown,
  opts: { withEn?: boolean; maxzoom?: number } = {},
): LayerSpecification {
  const withEn = opts.withEn !== false;
  return {
    id,
    type: "symbol",
    source: "stations",
    minzoom,
    ...(opts.maxzoom ? { maxzoom: opts.maxzoom } : {}),
    // 没有英文名的站（爱辉路/长江西路/通南路）只出中文
    filter: withEn
      ? ["all", ["has", "name_en"], ["!=", ["get", "name_en"], ""], lengthFilter]
      : ["all", ["has", "name_en"], lengthFilter],
    layout: {
      "text-font": FONT_STACK,
      "text-field": withEn
        ? [
            "format",
            ["get", "name_display"],
            { "font-scale": 1 },
            "\n",
            ["get", "name_en"],
            { "font-scale": 0.66, "text-color": "#6E6E6E" },
          ]
        : ["get", "name_display"],
      "text-size": ["interpolate", ["linear"], ["zoom"], 13, 12, 15, 13.5, 17, 15.5],
      "text-line-height": 1.02,
      "text-anchor": "left",
      "text-justify": "left",
      "text-offset": [0.85, 0],
      "text-padding": 3,
      "text-max-width": 16,
      "text-allow-overlap": false,
      "text-ignore-placement": false,
      "symbol-sort-key": ["get", "line_count"],
    },
    paint: {
      "text-color": "#222222",
      "text-halo-color": "rgba(244, 241, 234, 0.95)",
      "text-halo-width": 1.8,
      "text-halo-blur": 0.2,
    },
  } as unknown as LayerSpecification;
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
      selected: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
      hover: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
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
      // ——— 线路：先画「纸色描边」再压彩色，交叉处才有留白（S3-6） ———
      {
        id: "metro-line-casing",
        type: "line",
        source: "segments",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": PALETTE.paper,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 3.4, 10, 4.6, 12, 6.0, 14, 7.6, 17, 11.5],
          "line-opacity": 0.95,
        },
      },
      {
        id: "metro-line",
        type: "line",
        source: "segments",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": colorExpression(lineColors) as never,
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.4, 10, 2.0, 12, 3.0, 14, 4.2, 17, 7],
          "line-opacity": 1,
        },
      },

      // ——— 车站：换乘站在低缩放就出现，普通站 z11 起，避免全城图糊成一片 ———
      {
        id: "station-dot",
        type: "circle",
        source: "stations",
        minzoom: 11,
        filter: ["!=", ["get", "is_transfer"], true],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 1.8, 13, 2.8, 15, 4.0, 17, 5.0],
          "circle-color": "#FFFFFF",
          "circle-stroke-color": "#5A5A5A",
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 11, 0.8, 14, 1.2, 17, 1.6],
        },
      },
      {
        id: "station-dot-transfer",
        type: "circle",
        source: "stations",
        minzoom: 9.5,
        filter: ["==", ["get", "is_transfer"], true],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 9.5, 1.8, 10, 2.4, 12, 3.4, 14, 4.8, 17, 6.6],
          "circle-color": "#FFFFFF",
          "circle-stroke-color": "#2B2B2B",
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 10, 1.2, 14, 1.8, 17, 2.4],
        },
      },

      // ——— 选中站：外圈加粗描边，压在标签下面 ———
      {
        id: "station-selected",
        type: "circle",
        source: "selected",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 6, 14, 10, 17, 13],
          "circle-color": "rgba(0, 0, 0, 0)",
          "circle-stroke-color": PALETTE.ink,
          "circle-stroke-width": 2.4,
        },
      },

      // ——— 悬停：圆点上方浮一个站名，点击前先确认点的是哪个站 ———
      {
        id: "station-hover-label",
        type: "symbol",
        source: "hover",
        // 只在常驻站名还没出现的缩放区间起作用，避免和大图上的标签重复
        maxzoom: 12.55,
        layout: {
          "text-font": FONT_STACK,
          "text-field": ["get", "name_display"],
          "text-size": 12,
          "text-anchor": "bottom",
          "text-offset": [0, -0.9],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": PALETTE.ink,
          "text-halo-color": "rgba(255, 255, 255, 0.95)",
          "text-halo-width": 2,
        },
      },

      // ——— 站名两层：z11 只标换乘站（重要站），z12.6 再放开普通站 ———
      {
        id: "station-label-major",
        type: "symbol",
        source: "stations",
        minzoom: 11,
        // z13 起换成中英双语层
        maxzoom: 13,
        filter: ["==", ["get", "is_transfer"], true],
        layout: {
          "text-font": FONT_STACK,
          "text-field": ["get", "name_display"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 11, 11, 14, 13, 17, 15],
          "text-anchor": "left",
          "text-offset": [0.8, 0],
          "text-padding": 3,
          "text-max-width": 12,
          "text-allow-overlap": false,
          "text-ignore-placement": false,
          "symbol-sort-key": ["get", "line_count"],
        },
        paint: {
          "text-color": "#222222",
          "text-halo-color": "rgba(244, 241, 234, 0.95)",
          "text-halo-width": 1.8,
          "text-halo-blur": 0.2,
        },
      },
      {
        id: "station-label-minor",
        type: "symbol",
        source: "stations",
        minzoom: 12.6,
        maxzoom: 13,
        filter: ["!=", ["get", "is_transfer"], true],
        layout: {
          "text-font": FONT_STACK,
          "text-field": ["get", "name_display"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 12.6, 10.5, 15, 12, 17, 13],
          "text-anchor": "left",
          "text-offset": [0.75, 0],
          "text-padding": 3,
          "text-max-width": 12,
          "text-allow-overlap": false,
          "text-ignore-placement": false,
        },
        paint: {
          "text-color": "#4A4A4A",
          "text-halo-color": "rgba(244, 241, 234, 0.9)",
          "text-halo-width": 1.5,
          "text-halo-blur": 0.2,
        },
      },
      // ——— z13 起：中文站名 + 英文副行（S4-2）———
      // 中英放在同一个 label 里（format 第二段降字号、换灰色），这样碰撞检测算作一个整体，
      // 不会出现「中文留下了、英文被挤掉」的情况。
      // 英文名长短差异极大（「人民广场 / People's Square」对「一大会址·黄陂南路 /
      // Site of the First CPC National Congress·South Huangpi Road」），
      // 所以按长度分两层：短的 z13 就出，长的压到 z15 才出，避免市中心一屏全是折行的英文。
      bilingualLabel("station-label-bilingual", 13, ["<=", ["length", ["get", "name_en"]], 30]),
      // 长英文名在 z13–15 之间只出中文，避免一屏全是折行的英文；z15 起再补英文副行
      bilingualLabel("station-label-long-zh", 13, [">", ["length", ["get", "name_en"]], 30], {
        withEn: false,
        maxzoom: 15,
      }),
      bilingualLabel("station-label-bilingual-long", 15, [">", ["length", ["get", "name_en"]], 30]),
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
