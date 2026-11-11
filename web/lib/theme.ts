/**
 * 主题与调色板（UX-2 深色模式的地基）
 *
 * 这里只放「数据」：两套调色板 + 主题模式与解析函数。组件与地图样式都从这里取色，
 * 不允许在 mapStyle.ts / globals.css 之外再出现十六进制字面量。
 *
 * 硬约束（用户决策 D6）：**线路颜色不在这里定义、也不做任何提亮**。
 * 线路色来自数据（`lines.json` 的 `colour`，即官方色）；深色下若某条深色线路
 * 与背景贴近，只能靠 `casing`（深色描边）制造留白，不改官图色。
 */

/** 用户可选的三态：跟随系统 / 强制浅色 / 强制深色 */
export type ThemeMode = "system" | "light" | "dark";

/** 实际生效的两态（由 mode + 系统偏好算出） */
export type ResolvedTheme = "light" | "dark";

/** localStorage 键名（阶段 1 的注水脚本与切换器都读它） */
export const THEME_STORAGE_KEY = "subways-theme";

/**
 * 地图调色板。字段与 `lib/mapStyle.ts` 的图层一一对应，
 * 新增图层时必须在这里补字段，否则深色下会留下浅色残块。
 */
export interface Palette {
  /** 页面底色 = 陆地底色（P0 不画陆地填充面，见探测 8 决策） */
  paper: string;
  /** 海面（五省 coastline 拼出的面，仅上海有） */
  sea: string;
  /** 湖库水面 */
  water: string;
  /** 河道中心线 */
  waterLine: string;
  /** 海岸线 */
  coastline: string;
  /** 邻市界 */
  district: string;
  /** 省/市界 */
  province: string;
  /** 线路描边：交叉处留白靠它，深色下必须等于底色系 */
  casing: string;
  /** 主文字（换乘站名、悬停站名、选中圈） */
  ink: string;
  /** 站名主层文字（比 ink 略深，S3-6 定稿值） */
  labelPrimary: string;
  /** 次文字（普通站名） */
  labelSecondary: string;
  /** 副行文字（英文名） */
  labelSubtle: string;
  /** 站名光晕：主层 */
  haloPrimary: string;
  /** 站名光晕：普通站层 */
  haloSecondary: string;
  /** 悬停标签光晕 */
  hoverHalo: string;
  /** 站点填充（普通站与换乘站共用白心） */
  dotFill: string;
  /** 普通站环色 */
  dotRing: string;
  /** 换乘站环色 */
  dotRingTransfer: string;
  /** 线路色缺失时的兜底色（数据问题，正常不出现） */
  lineFallback: string;
}

/**
 * 浅色盘：与 UX-1 之前的所有取色**逐字节一致**（阶段 0 的重构只搬家，不改值）。
 * 改动这里等于改视觉，必须同时截图自证。
 */
export const LIGHT: Palette = {
  paper: "#F4F1EA",
  sea: "#DCE6EF",
  water: "#D7E4EF",
  waterLine: "#C6D8E8",
  coastline: "#BFC9D2",
  district: "#DBD5C8",
  province: "#B4AC9C",
  casing: "#F4F1EA",
  ink: "#2B2B2B",
  labelPrimary: "#222222",
  labelSecondary: "#4A4A4A",
  labelSubtle: "#6E6E6E",
  haloPrimary: "rgba(244, 241, 234, 0.95)",
  haloSecondary: "rgba(244, 241, 234, 0.9)",
  hoverHalo: "rgba(255, 255, 255, 0.95)",
  dotFill: "#FFFFFF",
  dotRing: "#6E6E6E",
  dotRingTransfer: "#2B2B2B",
  lineFallback: "#999999",
};

/**
 * 深色盘：暖黑而不是纯黑（与「纸色」的审美同一族），
 * 亮度层级按「底图最暗 → 站名最亮」排，保证线路是画面唯一主体。
 */
export const DARK: Palette = {
  paper: "#1A1A18",
  sea: "#121C24",
  water: "#16222B",
  waterLine: "#233642",
  coastline: "#3A4650",
  district: "#2B2B28",
  province: "#4C4C45",
  casing: "#1A1A18",
  ink: "#E9E6DF",
  labelPrimary: "#F0EDE6",
  labelSecondary: "#BDB8AF",
  labelSubtle: "#8F8A81",
  haloPrimary: "rgba(26, 26, 24, 0.92)",
  haloSecondary: "rgba(26, 26, 24, 0.88)",
  hoverHalo: "rgba(26, 26, 24, 0.95)",
  dotFill: "#F2F0EB",
  dotRing: "#8A8A83",
  dotRingTransfer: "#E9E6DF",
  lineFallback: "#6E6E6E",
};

export function paletteFor(theme: ResolvedTheme): Palette {
  return theme === "dark" ? DARK : LIGHT;
}

/** 三态 + 系统偏好 → 实际生效的两态（纯函数，阶段 1 的切换器与注水脚本共用语义） */
export function resolveTheme(mode: ThemeMode, systemPrefersDark: boolean): ResolvedTheme {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  return systemPrefersDark ? "dark" : "light";
}

/** 三态在按钮上的顺序：跟随系统 → 浅色 → 深色 → 跟随系统… */
export const THEME_CYCLE: ThemeMode[] = ["system", "light", "dark"];

/** 三态的中文标签（按钮 aria-label 与无障碍播报用） */
export const THEME_LABEL: Record<ThemeMode, string> = {
  system: "跟随系统",
  light: "浅色",
  dark: "深色",
};

/** 下一个模式（仅供切换器使用，纯函数便于测试） */
export function nextMode(mode: ThemeMode): ThemeMode {
  const i = THEME_CYCLE.indexOf(mode);
  return THEME_CYCLE[(i + 1) % THEME_CYCLE.length];
}
