/**
 * 字体：不用 glyph PBF，也不用字体文件（S4-1 决策 D1-A）。
 *
 * 依据（探测 7 + maplibre-gl 6.16.0 源码）：
 * - 样式里不写 `glyphs` 键时，GL JS 的 `!this.url` 分支会**全部走本机渲染**（TinySDF），
 *   中文和拉丁文都不发 glyph 请求。
 * - CJK 字符只有在 `text-font` 等于默认栈时才会用 `localIdeographFontFamily`；
 *   一旦显式写 `text-font`，就改用该栈本身当 CSS 字体串。
 *   所以这里两边都写上，保证中文和西文落到同一套系统字体上。
 *
 * 换字体只改这一处；D1-B（自托管 Noto Sans SC 子集，约 57 KB）将来走 `font-faces`，
 * 那时把 `text-font` 改成字体名即可，其余不动。
 */

/** MapLibre `text-font`：数组形式，内部会拼成 CSS 字体串 */
export const FONT_STACK = [
  "Microsoft YaHei UI",
  "Microsoft YaHei",
  "PingFang SC",
  "Hiragino Sans GB",
  "Noto Sans SC",
  "sans-serif",
];

/** 同一套字体，给 `localIdeographFontFamily` 和 CSS 用 */
export const FONT_STACK_CSS =
  '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif';
