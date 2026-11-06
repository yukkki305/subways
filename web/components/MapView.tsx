"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AboutPanel from "@/components/AboutPanel";
import SearchBox from "@/components/SearchBox";
import StationPanel from "@/components/StationPanel";
import { boundsOf, buildStyle, type LineColors } from "@/lib/mapStyle";
import type { SearchHit } from "@/lib/search";
import { FONT_STACK_CSS } from "../lib/typography";
import {
  displayNames,
  stationsToGeoJSON,
  type Dataset,
  type Line,
  type Station,
  type Transfer,
} from "@/lib/dataset";

// Next 打包会把 maplibre 的 worker URL 算错（浏览器报 "Worker failed to load"），
// 这里指向 sync-data 拷进 public/vendor 的原文件。
/**
 * S6-1：站点发布在 GitHub Pages 的项目子路径下（`/subways/`），
 * 所有运行时请求都必须带此前缀，否则线上 404。
 */
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/**
 * P1a-6.1：数据产物按城市分目录（`public/data/<code>/`）。
 * 6.2 已把城市改成页面传入的 props（见下方组件签名）。
 */

maplibregl.setWorkerUrl(`${BASE}/vendor/maplibre-gl-worker.mjs`);

type LinesFile = { lines: Line[] };
type StationFile = { stations: Station[] };
type TransferFile = { transfers: Transfer[] };
type MetaFile = {
  snapshot_date: string;
  data_as_of?: string;
  counts?: {
    stations?: number;
    slots?: number;
    multi_line_stations?: number;
    lines?: number;
    segments?: number;
    transfers?: number;
  };
};

/** 可点击的图层：换乘站优先，其次普通站，最后两层站名 */
const PICK_LAYERS = [
  "station-dot-transfer",
  "station-transfer-halo",
  "station-dot",
  "station-label-bilingual",
  "station-label-major",
  "station-label-minor",
  "station-label-bilingual",
  "station-label-long-zh",
  "station-label-bilingual-long",
];

async function loadJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

/**
 * P1a-6.1/6.2：数据产物按城市分目录（`public/data/<code>/`），
 * 城市由页面（`/` 与 `/<code>/`）在构建期决定，不再写死。
 */
type Props = {
  cityCode: string;
  /** 界面显示用的城市简称，例如「上海」「广州」 */
  cityLabel: string;
  /** 初始视野（真正贴合范围的 fitBounds 在数据加载后做） */
  center: [number, number];
  zoom: number;
};

export default function MapView({ cityCode, cityLabel, center, zoom }: Props) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const segmentsRef = useRef<GeoJSON.FeatureCollection | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [meta, setMeta] = useState<MetaFile | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [aboutOpen, setAboutOpen] = useState(false);

  const selected = useMemo(
    () => dataset?.stations.find((s) => s.id === selectedId) ?? null,
    [dataset, selectedId],
  );
  const names = useMemo(() => (dataset ? displayNames(dataset.stations) : new Map<string, string>()), [dataset]);

  /** 选中态写进 selected 源，地图上画一个外圈 */
  const paintSelection = useCallback((station: Station | null) => {
    const src = mapRef.current?.getSource("selected") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData({
      type: "FeatureCollection",
      features: station
        ? [{ type: "Feature", geometry: { type: "Point", coordinates: station.coord }, properties: {} }]
        : [],
    } as GeoJSON.FeatureCollection);
  }, []);

  useEffect(() => {
    paintSelection(selected);
  }, [selected, paintSelection]);

  const pickStation = useCallback(
    (stationId: string, fly = true) => {
      setSelectedId(stationId);
      const map = mapRef.current;
      const s = dataset?.stations.find((x) => x.id === stationId);
      if (fly && map && s) map.easeTo({ center: s.coord, zoom: Math.max(map.getZoom(), 12.5), duration: 450 });
    },
    [dataset],
  );

  /** 线路结果：把视野框到那条线（S5-3 会把站点定位换成 flyTo 动画） */
  const focusLine = useCallback((lineId: string) => {
    const map = mapRef.current;
    const fc = segmentsRef.current;
    if (!map || !fc) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const f of fc.features) {
      if (f.properties?.line_id !== lineId || f.geometry.type !== "LineString") continue;
      for (const [x, y] of f.geometry.coordinates as [number, number][]) {
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
    if (!Number.isFinite(minX)) return;
    map.fitBounds(
      [
        [minX, minY],
        [maxX, maxY],
      ],
      { padding: { top: 96, bottom: 96, left: 64, right: 64 }, duration: 600 },
    );
  }, []);

  const onSearchPick = useCallback(
    (hit: SearchHit) => {
      if (hit.kind === "line") {
        // 跳到整条线时把站点抽屉收掉，否则面板还停在上一站，看起来像没响应
        setSelectedId(null);
        focusLine(hit.id);
      } else {
        pickStation(hit.id);
      }
    },
    [focusLine, pickStation],
  );

  useEffect(() => {
    let disposed = false;

    async function boot() {
      try {
        // 底图与海面目前只有上海有（6.4 补其余城市），缺文件时退化为空图层而不是整页失败
        const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
        const [basemap, sea, segments, linesFile, stationFile, transferFile, metaFile] = await Promise.all([
          loadJson<GeoJSON.FeatureCollection>(`${BASE}/data/${cityCode}/basemap.geojson`).catch(() => empty),
          loadJson<GeoJSON.FeatureCollection>(`${BASE}/data/${cityCode}/sea.geojson`).catch(() => empty),
          loadJson<GeoJSON.FeatureCollection>(`${BASE}/data/${cityCode}/segment.geojson`),
          loadJson<LinesFile>(`${BASE}/data/${cityCode}/lines.json`),
          loadJson<StationFile>(`${BASE}/data/${cityCode}/station.json`),
          loadJson<TransferFile>(`${BASE}/data/${cityCode}/transfer.json`),
          loadJson<MetaFile>(`${BASE}/data/${cityCode}/meta.json`).catch(() => null),
        ]);
        if (disposed || !boxRef.current) return;

        const lineColors: LineColors = linesFile.lines.map((l) => [l.id, l.colour]);
        const lineTypes = linesFile.lines.map((l) => [l.id, l.type] as [string, string]);
        const stationCollection = stationsToGeoJSON(stationFile.stations);

        const map = new maplibregl.Map({
          container: boxRef.current,
          style: buildStyle(basemap, segments, stationCollection, lineColors, lineTypes, sea),
          center,
          zoom,
        // 中文与西文都走本机渲染（不请求 glyph PBF），字体栈统一在 lib/typography.ts
        localIdeographFontFamily: FONT_STACK_CSS,
          minZoom: 8.5,
          maxZoom: 17,
          dragRotate: false,
          pitchWithRotate: false,
          // 版权信息统一放在页脚胶囊里，避免右下角控件与页脚在窄屏重叠
          attributionControl: false,
        });
        mapRef.current = map;
        segmentsRef.current = segments;

        map.touchZoomRotate.disableRotation();
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

        map.on("load", () => {
          // 容器尺寸必须先生效，否则 fitBounds 会按 0 高度算缩放（曾出现一进页面就跳到 z15）
          map.resize();
          const fit = () => {
            const b = boundsOf(segments);
            if (!b) return;
            if (map.getCanvas().clientWidth < 10 || map.getCanvas().clientHeight < 10) {
              requestAnimationFrame(fit);
              return;
            }
            map.fitBounds(b, { padding: { top: 72, bottom: 96, left: 48, right: 48 }, duration: 0 });
          };
          requestAnimationFrame(fit);

          // 悬停：变手型 + 在圆点上方浮出站名（点击前先确认点的是哪个站）
          const clearHover = () => {
            const src = map.getSource("hover") as maplibregl.GeoJSONSource | undefined;
            src?.setData({ type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection);
          };
          for (const layer of PICK_LAYERS) {
            map.on("mouseenter", layer, () => {
              map.getCanvas().style.cursor = "pointer";
            });
            map.on("mouseleave", layer, () => {
              map.getCanvas().style.cursor = "";
              clearHover();
            });
          }
          map.on("mousemove", (e) => {
            const hit = map.queryRenderedFeatures(e.point, { layers: PICK_LAYERS })[0];
            const src = map.getSource("hover") as maplibregl.GeoJSONSource | undefined;
            if (!hit || !src) return;
            src.setData({
              type: "FeatureCollection",
              features: [
                {
                  type: "Feature",
                  geometry: hit.geometry,
                  properties: { name_display: hit.properties?.name_display ?? hit.properties?.name ?? "" },
                },
              ],
            } as GeoJSON.FeatureCollection);
          });

          // 点击：命中站点点位或站名 → 打开详情
          map.on("click", (e) => {
            const hits = map.queryRenderedFeatures(e.point, { layers: PICK_LAYERS });
            const id = hits[0]?.properties?.id as string | undefined;
            if (id) setSelectedId(id);
            else setSelectedId(null);
          });

          setDataset({
            lines: linesFile.lines,
            stations: stationFile.stations,
            transfers: transferFile.transfers,
          });
          setMeta(metaFile);
          setStatus("ready");
        });

        map.on("error", (e) => {
          // 缺 glyph 不算错误（本机渲染），其它错误打到控制台便于排查
          console.warn("[maplibre]", e.error?.message ?? e);
          const w = window as unknown as { __mapErrors?: string[] };
          w.__mapErrors = [...(w.__mapErrors ?? []), String(e.error?.message ?? e)];
        });

        // 自查用：E2E 脚本通过 window.__map 读相机与图层状态
        (window as unknown as { __map?: maplibregl.Map }).__map = map;
      } catch (err) {
        if (disposed) return;
        setStatus("error");
        setMessage(err instanceof Error ? err.message : String(err));
      }
    }

    void boot();

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // 城市在构建期就确定，页面之间是整页跳转，这里不会中途换城
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Esc 关闭详情
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (aboutOpen) {
        setAboutOpen(false);
        return;
      }
      setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, aboutOpen]);

  return (
    <div className="map-shell">
      <div ref={boxRef} className="map-canvas" />

      <header className="map-title">
        <h1>中国铁路图鉴 · {cityLabel}</h1>
      </header>

      {dataset && <SearchBox stations={dataset.stations} lines={dataset.lines} onPick={onSearchPick} />}

      {(status === "loading" || status === "error") && (
        <div
          className={`map-loading${status === "error" ? " is-error" : ""}`}
          {...(status === "error" ? { role: "alert" } : { "aria-hidden": true })}
        >
          <div className="map-loading__card">
            <span className="map-loading__dot" />
            <p className="map-loading__title">
              {status === "error" ? "地图加载失败" : `正在铺开${cityLabel}地铁图`}
            </p>
            <p className="map-loading__hint">
              {status === "error" ? message : `${cityLabel}城市轨道交通 · 首次加载约 1 秒`}
            </p>
          </div>
        </div>
      )}

      {selected && dataset && (
        <StationPanel
          station={selected}
          displayName={names.get(selected.id) ?? selected.name}
          lines={dataset.lines}
          stations={dataset.stations}
          transfers={dataset.transfers}
          names={names}
          onClose={() => setSelectedId(null)}
          onPick={(id) => pickStation(id)}
        />
      )}

      {aboutOpen && (
        <AboutPanel
          onClose={() => setAboutOpen(false)}
          cityLabel={cityLabel}
          lines={dataset?.lines.length ?? meta?.counts?.lines ?? null}
          stations={dataset?.stations.length ?? meta?.counts?.stations ?? null}
          segments={meta?.counts?.segments ?? null}
          transfers={dataset?.transfers.length ?? meta?.counts?.transfers ?? null}
          snapshot={meta?.data_as_of ?? meta?.snapshot_date ?? null}
        />
      )}

      <footer className="map-footer">
        <span>
          {meta
            ? `${dataset?.lines.length ?? "?"} 条线路 · ${dataset?.stations.length ?? meta.counts?.stations ?? "?"} 站 · 数据截止 ${meta.data_as_of ?? meta.snapshot_date}`
            : `${cityLabel}城市轨道交通`}
          <i>·</i> 数据 © OpenStreetMap contributors（ODbL-1.0）
          <i>·</i> 个人作品集项目，数据仅供参考
        </span>
        <button
          type="button"
          className="about-button"
          onClick={() => setAboutOpen(true)}
          aria-label="关于这张地图与数据说明"
        >
          关于
        </button>
      </footer>
    </div>
  );
}
