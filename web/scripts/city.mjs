/**
 * 前端脚本的「城市解析」公共层（P1a-1.5）。
 *
 * 为什么单独一份：sync-data / test-search / verify-build 三个脚本原来都把上海
 * 写死在路径与断言里。多城之后它们都要回答同样三个问题：
 *   1. 这次跑的是哪座城？
 *   2. 该城的产物在哪、有哪些？
 *   3. 该城的视野框、线路清单是什么？
 * 统一读 `pipeline/cities/<code>.json`（数据管道的单一事实源），
 * 前端脚本不再各自维护一份城市常量。
 *
 * 用法（三个脚本一致）：
 *   node scripts/xxx.mjs --city gz       # 显式指定
 *   SUBWAY_WEB_CITY=gz node scripts/xxx.mjs
 *   不指定时默认 sh（保持 P0 的默认行为不变）
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const WEB = resolve(__dirname, "..");
export const REPO = resolve(WEB, "..");
export const CITIES_DIR = join(REPO, "pipeline", "cities");
export const DEFAULT_CITY = "sh";

/** 仓库里已配置的城市 code 列表 */
export function listCityCodes() {
  if (!existsSync(CITIES_DIR)) return [];
  return readdirSync(CITIES_DIR)
    .filter((n) => n.endsWith(".json"))
    .map((n) => n.slice(0, -5))
    .sort();
}

/**
 * 从 argv 里取 `--city <code>`，返回 `{ city, rest }`（rest 是不含该参数的其余参数）。
 * 没有 --city 时看环境变量 SUBWAY_WEB_CITY，再没有就用 DEFAULT_CITY。
 */
export function parseCityArg(argv) {
  const rest = [];
  let city = process.env.SUBWAY_WEB_CITY || DEFAULT_CITY;
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--city") {
      const v = argv[i + 1];
      if (!v) throw new Error("--city 后面要跟城市 code，例如 --city gz");
      city = v;
      i += 1;
    } else if (a.startsWith("--city=")) {
      city = a.slice("--city=".length);
    } else {
      rest.push(a);
    }
  }
  return { city, rest };
}

/** 读某城的配置，并对前端用到的字段做最小校验 */
export function loadCity(code) {
  const file = join(CITIES_DIR, `${code}.json`);
  if (!existsSync(file)) {
    const known = listCityCodes().join(" / ") || "(无)";
    throw new Error(`没有城市配置 pipeline/cities/${code}.json。已配置：${known}`);
  }
  const cfg = JSON.parse(readFileSync(file, "utf8"));
  if (cfg.code !== code) {
    throw new Error(`${file} 里的 code 是「${cfg.code}」，与文件名「${code}」不一致`);
  }
  for (const key of ["data_dir", "line_ids", "bbox", "scene_bbox", "web"]) {
    if (!cfg[key]) throw new Error(`${file} 缺少字段 ${key}`);
  }
  return cfg;
}

/** 该城要同步给前端的产物：返回 [{ rel, name, optional }]，顺序即产物顺序 */
export function dataSources(cfg) {
  const dir = cfg.data_dir;
  const list = [
    { rel: `${dir}/lines.json`, name: "lines.json" },
    { rel: `${dir}/station.json`, name: "station.json" },
    { rel: `${dir}/transfer.json`, name: "transfer.json" },
    { rel: `${dir}/segment.geojson`, name: "segment.geojson" },
  ];
  // 底图与海面：上海是 P0 精细版（共享目录），其它城为可选（<data_dir>/basemap|sea.geojson）
  if (cfg.code === "sh") {
    list.push({ rel: "data/processed/basemap/shanghai-basemap.geojson", name: "shanghai-basemap.geojson" });
    list.push({ rel: "data/processed/basemap/shanghai-sea.geojson", name: "sea.geojson" });
  } else {
    list.push({ rel: `${dir}/basemap.geojson`, name: "basemap.geojson", optional: true });
    list.push({ rel: `${dir}/sea.geojson`, name: "sea.geojson", optional: true });
  }
  return list;
}

/** 城市显示名（前端标题用），例如 上海 / 广州 */
export function cityLabel(cfg) {
  return cfg.web?.city_label || cfg.name || cfg.code;
}

/** 视野框（校验坐标用），没配 scene_bbox 时退回 bbox */
export function sceneBbox(cfg) {
  const b = cfg.scene_bbox || cfg.bbox;
  return { west: b[0], south: b[1], east: b[2], north: b[3] };
}
