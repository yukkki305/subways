"use client";

import { useEffect, useRef } from "react";

const REPO = "https://github.com/yukkki305/subways";
const LIVE = "https://yukkki305.github.io/subways/";

type Props = {
  onClose: () => void;
  /** 城市简称，例如「上海」「广州」 */
  cityLabel: string;
  lines: number | null;
  stations: number | null;
  segments: number | null;
  transfers: number | null;
  /** 数据截止日（YYYYMMDD 或 ISO 日期原样显示） */
  snapshot: string | null;
};

/** 把 20261101 这类紧凑日期显示成 2026-11-01；其它格式原样返回 */
function prettyDate(raw: string | null): string {
  if (!raw) return "未知";
  const m = /^(\d{4})(\d{2})(\d{2})$/.exec(raw.trim());
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  return raw;
}

export default function AboutPanel({ onClose, cityLabel, lines, stations, segments, transfers, snapshot }: Props) {
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // 不做程序化聚焦：避免卡片上出现一圈 focus 环；Esc 由 document 捕获
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const scale = [
    lines ? `${lines} 条线路` : null,
    stations ? `${stations} 站` : null,
    segments ? `${segments} 个区间` : null,
    transfers !== null ? `${transfers} 条换乘` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const asOf = prettyDate(snapshot);

  return (
    <div className="about-mask" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className="about"
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        tabIndex={-1}
        ref={boxRef}
      >
        <header className="about__head">
          <h2 id="about-title">关于这张地图</h2>
          <button type="button" className="about__close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>

        <p className="about__lead">
          把{cityLabel} {lines ?? "?"} 条城市轨道交通线路按真实地理走向画在地图上；点车站可看线路、站序与换乘。
        </p>

        <dl className="about__kv">
          <dt>数据</dt>
          <dd>
            OpenStreetMap 省级 PBF（快照 <b>{asOf}</b>，ODbL-1.0）；站名另用 GZUPA 2020 属性表与百度百科线路表自动比对。
          </dd>
          <dt>规模</dt>
          <dd>{scale || "计数待补"}</dd>
          <dt>口径</dt>
          <dd>
            只含地铁、轻轨、单轨与自动旅客捷运；不含市域铁路、城际与高铁。站名不带「站」字，由界面统一加。
          </dd>
          <dt>地图</dt>
          <dd>
            底图为自建极简底图（行政界 + 主水系 + 海面），不使用任何第三方瓦片；全程 WGS-84，不含 GCJ-02 数据。
          </dd>
          <dt>已知局限</dt>
          <dd>
            数据为 {asOf} 快照、非实时；换乘类型只能人工判定，部分仍待核对；站名以 OSM 为主，与官方口径的差异记在
            `docs/conflicts-*.md`。
          </dd>
          <dt>许可</dt>
          <dd>
            数据 © OpenStreetMap contributors（ODbL-1.0），衍生数据同许可；代码 MIT。个人作品集项目，数据仅供参考。
          </dd>
        </dl>

        <footer className="about__foot">
          <a href={LIVE} target="_blank" rel="noreferrer">
            线上站点
          </a>
          <a href={REPO} target="_blank" rel="noreferrer">
            源码与数据管道
          </a>
        </footer>
      </div>
    </div>
  );
}
