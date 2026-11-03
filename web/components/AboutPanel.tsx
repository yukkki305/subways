"use client";

import { useEffect, useRef } from "react";

const REPO = "https://github.com/yukkki305/subways";
const LIVE = "https://yukkki305.github.io/subways/";

export default function AboutPanel({ onClose }: { onClose: () => void }) {
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
          把上海 20 条城市轨道交通线路按真实地理走向画在地图上；点车站可看线路、站序与换乘。
        </p>

        <dl className="about__kv">
          <dt>数据</dt>
          <dd>
            OpenStreetMap 省级 PBF（快照 <b>2026-11-01</b>，ODbL-1.0）；站名另用 GZUPA 2020 属性表与百度百科线路表自动比对。
          </dd>
          <dt>规模</dt>
          <dd>20 条线路 · 423 站 · 570 个区间 · 12 条换乘</dd>
          <dt>口径</dt>
          <dd>
            只含地铁、轻轨、单轨与自动旅客捷运（含磁浮线、浦江线）；不含市域铁路、城际与高铁。站名不带「站」字，由界面统一加。
          </dd>
          <dt>地图</dt>
          <dd>
            底图为自建极简底图（行政界 + 主水系 + 海面），不使用任何第三方瓦片；全程 WGS-84，不含 GCJ-02 数据。
          </dd>
          <dt>已知局限</dt>
          <dd>
            17 号线「国家会展中心」官方名为「诸光路」，待改；12 条换乘中 9 条的换乘类型待核对；数据为 2026-11-01 快照，非实时。
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
