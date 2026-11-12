"use client";

/**
 * P1a-6.3：城市切换器。
 *
 * 形态：不新增悬浮控件，直接把标题里的城市名做成按钮（「中国铁路图鉴 · 上海 ▾」）。
 * 理由：页头已经有标题胶囊，再放一个下拉会挤占地图；城市名本来就是用户想看的东西。
 *
 * 交互：点开 → 四个城市的菜单（当前项高亮并标 aria-current），Esc 关闭并把焦点还给按钮，
 * 点外部关闭。城市之间是真实链接（`next/link` 会自动加 basePath），不是客户端状态切换——
 * 每座城是独立静态页，换城等于换页，这样 SEO 与分享都成立。
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { CityLink } from "@/lib/cities";

type Props = {
  current: string;
  cities: CityLink[];
};

export default function CitySwitcher({ current, cities }: Props) {
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);

  const here = cities.find((c) => c.code === current) ?? cities[0];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="city-switch" ref={boxRef}>
      <button
        ref={btnRef}
        type="button"
        className="city-switch__btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`当前城市：${here?.label ?? current}，切换城市`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="city-switch__name">{here?.label ?? current}</span>
        <svg className="city-switch__chev" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <ul className="city-switch__menu" role="menu">
          {cities.map((c) => {
            const active = c.code === current;
            return (
              <li key={c.code} role="none">
                <Link
                  role="menuitem"
                  href={c.href}
                  className={`city-switch__item${active ? " is-current" : ""}`}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setOpen(false)}
                >
                  <span className="city-switch__item-name">{c.label}</span>
                  <span className="city-switch__item-meta">
                    {c.lines} 条{c.stations ? ` · ${c.stations} 站` : ""}
                  </span>
                </Link>
              </li>
            );
          })}
          {/* 总览入口（UX 阶段 3）：菜单底部单独一格，与上面的城市项区分开 */}
          <li role="none" className="city-switch__all">
            <Link role="menuitem" href="/cities/" onClick={() => setOpen(false)}>
              全部城市 →
            </Link>
          </li>
        </ul>
      )}
    </div>
  );
}
