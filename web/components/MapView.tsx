"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import StationPanel from "@/components/StationPanel";
import { boundsOf, buildStyle, type LineColors } from "@/lib/mapStyle";
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
maplibregl.setWorkerUrl("/vendor/maplibre-gl-worker.mjs");

type LinesFile = { lines: Line[] };
type StationFile = { stations: Station[] };
type TransferFile = { transfers: Transfer[] };
type MetaFile = {
  snapshot_date: string;
  data_as_of?: string;
  counts?: { stations?: number; slots?: number; multi_line_stations?: number };
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

export default function MapView() {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [meta, setMeta] = useState<MetaFile | null>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  useEffect(() => {
    let disposed = false;

    async function boot() {
      try {
        const [basemap, sea, segments, linesFile, stationFile, transferFile, metaFile] = await Promise.all([
          loadJson<GeoJSON.FeatureCollection>("/data/shanghai-basemap.geojson"),
          loadJson<GeoJSON.FeatureCollection>("/data/sea.geojson"),
          loadJson<GeoJSON.FeatureCollection>("/data/segment.geojson"),
          loadJson<LinesFile>("/data/lines.json"),
          loadJson<StationFile>("/data/station.json"),
          loadJson<TransferFile>("/data/transfer.json"),
          loadJson<MetaFile>("/data/meta.json").catch(() => null),
        ]);
        if (disposed || !boxRef.current) return;

        const lineColors: LineColors = linesFile.lines.map((l) => [l.id, l.colour]);
        const lineTypes = linesFile.lines.map((l) => [l.id, l.type] as [string, string]);
        const stationCollection = stationsToGeoJSON(stationFile.stations);

        const map = new maplibregl.Map({
          container: boxRef.current,
          style: buildStyle(basemap, segments, stationCollection, lineColors, lineTypes, sea),
          center: [121.47, 31.23],
          zoom: 10.4,
        // 中文与西文都走本机渲染（不请求 glyph PBF），字体栈统一在 lib/typography.ts
        localIdeographFontFamily: FONT_STACK_CSS,
          minZoom: 8.5,
          maxZoom: 17,
          dragRotate: false,
          pitchWithRotate: false,
          attributionControl: { compact: true },
        });
        mapRef.current = map;

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
  }, []);

  // Esc 关闭详情
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  return (
    <div className="map-shell">
      <div ref={boxRef} className="map-canvas" />

      <header className="map-title">
        <h1>中国铁路图鉴 · 上海</h1>
      </header>

      {(status === "loading" || status === "error") && (
        <div
          className={`map-loading${status === "error" ? " is-error" : ""}`}
          {...(status === "error" ? { role: "alert" } : { "aria-hidden": true })}
        >
          <div className="map-loading__card">
            <span className="map-loading__dot" />
            <p className="map-loading__title">{status === "error" ? "地图加载失败" : "正在铺开上海地铁图"}</p>
            <p className="map-loading__hint">
              {status === "error" ? message : "20 条线路 · 430 站 · 首次加载约 1 秒"}
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

      <footer className="map-footer">
        <span>
          {meta
            ? `${dataset?.lines.length ?? "?"} 条线路 · ${dataset?.stations.length ?? meta.counts?.stations ?? "?"} 站 · 数据截止 ${meta.data_as_of ?? meta.snapshot_date}`
            : "上海城市轨道交通"}
          <i>·</i> 数据 © OpenStreetMap contributors（ODbL-1.0）
          <i>·</i> 个人作品集项目，数据仅供参考
        </span>
      </footer>
    </div>
  );
}
