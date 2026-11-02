"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import { boundsOf, buildStyle, type LineColors } from "@/lib/mapStyle";

// Next 打包会把 maplibre 的 worker URL 算错（浏览器报 "Worker failed to load"），
// 这里指向 sync-data 拷进 public/vendor 的原文件。
maplibregl.setWorkerUrl("/vendor/maplibre-gl-worker.mjs");

type LinesFile = {
  lines: Array<{ id: string; name: string; colour: string }>;
};

type MetaFile = {
  snapshot_date: string;
  data_as_of?: string;
  counts?: { stations?: number; slots?: number; multi_line_stations?: number };
};

async function loadJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${url} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

export default function MapView() {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("正在加载底图与线路…");
  const [meta, setMeta] = useState<MetaFile | null>(null);
  const [lineCount, setLineCount] = useState<number | null>(null);

  useEffect(() => {
    let disposed = false;
    let map: maplibregl.Map | null = null;

    async function boot() {
      try {
        const [basemap, segments, linesFile, metaFile] = await Promise.all([
          loadJson<GeoJSON.FeatureCollection>("/data/shanghai-basemap.geojson"),
          loadJson<GeoJSON.FeatureCollection>("/data/segment.geojson"),
          loadJson<LinesFile>("/data/lines.json"),
          loadJson<MetaFile>("/data/meta.json").catch(() => null),
        ]);
        if (disposed || !boxRef.current) return;

        const lineColors: LineColors = linesFile.lines.map((l) => [l.id, l.colour]);
        if (disposed) return;
        setLineCount(linesFile.lines.length);

        map = new maplibregl.Map({
          container: boxRef.current,
          style: buildStyle(basemap, segments, lineColors),
          center: [121.47, 31.23],
          zoom: 10.4,
          minZoom: 8.5,
          maxZoom: 17,
          dragRotate: false,
          pitchWithRotate: false,
          attributionControl: { compact: true },
        });

        map.touchZoomRotate.disableRotation();
        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

        map.on("load", () => {
          const b = boundsOf(segments);
          if (b) map?.fitBounds(b, { padding: { top: 72, bottom: 96, left: 48, right: 48 }, duration: 0 });
          map?.resize();
          setMeta(metaFile);
          setStatus("ready");
          setMessage("");
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
      map?.remove();
      map = null;
    };
  }, []);

  return (
    <div className="map-shell">
      <div ref={boxRef} className="map-canvas" />

      <header className="map-title">
        <h1>中国铁路图鉴 · 上海</h1>
      </header>

      {status !== "ready" && (
        <div className={`map-status ${status === "error" ? "is-error" : ""}`}>
          {status === "loading" ? "正在加载底图与线路…" : `加载失败：${message}`}
        </div>
      )}

      <footer className="map-footer">
        <span>
          {meta
            ? `${lineCount ?? "?"} 条线路 · ${meta.counts?.stations ?? "?"} 站 · 数据截止 ${meta.data_as_of ?? meta.snapshot_date}`
            : "上海城市轨道交通"}
          <i>·</i> 数据 © OpenStreetMap contributors（ODbL-1.0）
          <i>·</i> 个人作品集项目，数据仅供参考
        </span>
      </footer>
    </div>
  );
}
