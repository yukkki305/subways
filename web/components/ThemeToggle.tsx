"use client";

import { useCallback, useEffect, useState } from "react";
import {
  THEME_CYCLE,
  THEME_LABEL,
  THEME_STORAGE_KEY,
  nextMode,
  resolveTheme,
  type ResolvedTheme,
  type ThemeMode,
} from "@/lib/theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function applyTheme(mode: ThemeMode): ResolvedTheme {
  const prefersDark = window.matchMedia(DARK_QUERY).matches;
  const resolved = resolveTheme(mode, prefersDark);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
  return resolved;
}

function Icon({ mode }: { mode: ThemeMode }) {
  if (mode === "light") {
    // 太阳
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <circle cx="8" cy="8" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
          <path d="M8 1.2v1.6M8 13.2v1.6M1.2 8h1.6M13.2 8h1.6M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M12.8 3.2l-1.1 1.1M4.3 11.7l-1.1 1.1" />
        </g>
      </svg>
    );
  }
  if (mode === "dark") {
    // 月亮
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M13 9.6A5.4 5.4 0 0 1 6.4 3 5.6 5.6 0 1 0 13 9.6Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  // 跟随系统：半明半暗
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="5.2" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 2.8a5.2 5.2 0 0 1 0 10.4Z" fill="currentColor" />
    </svg>
  );
}

/**
 * UX 阶段 1：页脚的三态主题按钮。
 * 三态之所以不给开关：单开关表达不了「跟随系统」，而系统态是默认且最省心的选择。
 * localStorage 里存的是模式（system/light/dark），不是解析后的主题，
 * 这样用户换系统主题时「跟随系统」仍然跟得上。
 */
export default function ThemeToggle() {
  const [mode, setMode] = useState<ThemeMode>("system");

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "system" || stored === "light" || stored === "dark") {
      setMode(stored);
    } else {
      applyTheme("system");
    }
  }, []);

  useEffect(() => {
    applyTheme(mode);
    if (mode !== "system") return;
    const mq = window.matchMedia(DARK_QUERY);
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [mode]);

  const onClick = useCallback(() => {
    setMode((prev) => {
      const next = nextMode(prev);
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
      return next;
    });
  }, []);

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onClick}
      aria-label={`切换配色主题（当前：${THEME_LABEL[mode]}）`}
      title={`配色：${THEME_LABEL[mode]}（点击切换到${THEME_LABEL[THEME_CYCLE[(THEME_CYCLE.indexOf(mode) + 1) % THEME_CYCLE.length]]}）`}
    >
      <Icon mode={mode} />
      <span>{THEME_LABEL[mode]}</span>
    </button>
  );
}
