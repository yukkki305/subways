"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type { Line, Station } from "@/lib/dataset";
import { buildIndex, search, type SearchHit } from "@/lib/search";

type Props = {
  stations: Station[];
  lines: Line[];
  /** 选中一条结果（S5-2 只负责唤起，怎么定位由 MapView 决定） */
  onPick: (hit: SearchHit) => void;
};

/** 把命中片段包成 <mark>：中文查中文、拼音查副行 */
function Highlighted({ text, query }: { text: string; query: string }) {
  const q = query.trim();
  if (!q) return <>{text}</>;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  );
}

export default function SearchBox({ stations, lines, onPick }: Props) {
  const index = useMemo(() => buildIndex(stations, lines), [stations, lines]);
  const [query, setQuery] = useState("");
  /** 真正拿去检索的文本：输入法组合期间不更新，避免拼音打到一半就乱搜 */
  const [committed, setCommitted] = useState("");
  // 用 ref 而不是 state：compositionstart 与随后的 input 可能在同一帧里连续到达，
  // state 还没重渲染，闭包里读到的仍是 false（真机 IME 上表现为拼到一半就搜）。
  const composingRef = useRef(false);
  /** 下拉是否对用户可见：聚焦或刚输入过。注意不能用「DOM 焦点」判断——
   *  选完一条后输入框仍持有焦点，再 focus() 不会触发 onFocus，下拉就再也弹不出来。 */
  const [active, setActive] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const hits = useMemo(() => (committed.trim() ? search(index, committed) : []), [index, committed]);
  const showList = active && committed.trim().length > 0;

  // 点面板外面收起下拉
  useEffect(() => {
    if (!showList) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setActive(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [showList]);

  const clear = () => {
    setQuery("");
    setCommitted("");
    // 不在这里关活动态：清空后 committed 为空，下拉本来就隐藏；
    // 保留活动态，用户接着打字还能立刻看到结果。
  };

  const pick = (hit: SearchHit) => {
    onPick(hit);
    clear();
  };

  return (
    <div className="search" ref={rootRef}>
      <div className={`search__box${active ? " is-focused" : ""}`}>
        <span className="search__icon" aria-hidden="true">
          ⌕
        </span>
        <input
          ref={inputRef}
          className="search__input"
          type="text"
          value={query}
          placeholder="搜索站名 / 拼音 / 线路"
          aria-label="搜索站名、拼音或线路"
          aria-controls="search-results"
          aria-expanded={showList}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            setActive(true);
            setQuery(e.target.value);
            if (!composingRef.current) setCommitted(e.target.value);
          }}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={(e) => {
            composingRef.current = false;
            setCommitted(e.currentTarget.value);
          }}
          onFocus={() => setActive(true)}
          onBlur={() => setActive(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              // 第一下只清搜索，别把正在看的抽屉一起关掉
              e.stopPropagation();
              if (query || committed) {
                // 注意：这里不能 setFocused(false)。输入框仍然持有 DOM 焦点，
                // 再 focus() 不会触发 onFocus，列表就再也弹不出来了。
                setQuery("");
                setCommitted("");
              } else {
                setActive(false);
                inputRef.current?.blur();
              }
              return;
            }
            if (e.key === "Enter" && hits.length > 0) {
              e.preventDefault();
              pick(hits[0]);
            }
          }}
        />
        {query && (
          <button className="search__clear" type="button" aria-label="清空搜索" onClick={clear}>
            ×
          </button>
        )}
      </div>

      {showList && (
        <ul className="search__list" id="search-results" role="listbox" aria-label="搜索结果">
          {hits.map((hit) => (
            <li key={hit.id} role="option" aria-selected={false}>
              <button
                className="search__item"
                type="button"
                // mousedown 先于 blur，阻止默认行为才能让点击真正落在这条上
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(hit)}
              >
                <span className="search__dots" aria-hidden="true">
                  {hit.dots.map((d) => (
                    <i key={d.id} style={{ background: d.colour }} title={d.name} />
                  ))}
                </span>
                <span className="search__text">
                  <span className="search__title">
                    <Highlighted text={hit.title} query={committed} />
                  </span>
                  <span className="search__sub">
                    <Highlighted text={hit.subtitle} query={committed} />
                  </span>
                </span>
                {hit.kind === "line" && <span className="search__kind">线路</span>}
              </button>
            </li>
          ))}
          {hits.length === 0 && (
            <li className="search__empty">未找到「{committed.trim()}」，试试站名、拼音首字母或线路号</li>
          )}
        </ul>
      )}
    </div>
  );
}
