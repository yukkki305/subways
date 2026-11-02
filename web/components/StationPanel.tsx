"use client";

import type { Line, Station, Transfer } from "@/lib/dataset";
import { neighborsOf, transfersOf } from "@/lib/dataset";

type Props = {
  station: Station;
  displayName: string;
  lines: Line[];
  stations: Station[];
  transfers: Transfer[];
  names: Map<string, string>;
  onClose: () => void;
  onPick: (stationId: string) => void;
};

const TYPE_LABEL: Record<string, string> = {
  metro: "地铁",
  lrt: "轻轨",
  tram: "有轨电车",
  monorail: "单轨",
  apm: "自动旅客捷运",
  maglev: "磁浮",
};

const MERGE_LABEL: Record<string, string> = {
  auto_150: "≤150 m 自动合并",
  auto_review: "150–300 m 合并待复核",
  split_review: ">300 m 未合并，单独成站",
};

/** 合并方式的说明文字：只保留对读者有意义的部分 */
function mergeNote(merge: Station["merge"]): string {
  if (!merge?.method) return "—";
  const parts = [MERGE_LABEL[merge.method] ?? merge.method];
  if (merge.slot_count && merge.slot_count > 1) parts.push(`${merge.slot_count} 个站台节点`);
  if (merge.method === "auto_review" && typeof merge.spread_m === "number" && merge.spread_m > 0) {
    parts.push(`跨度 ${merge.spread_m.toFixed(1)} m`);
  }
  if (merge.needs_review && merge.method === "auto_review") parts.push("⚠️ 待复核");
  return parts.join("，");
}

export default function StationPanel({ station, displayName, lines, stations, transfers, names, onClose, onPick }: Props) {
  const lineById = new Map(lines.map((l) => [l.id, l]));
  const nb = neighborsOf(station, lines);
  const tr = transfersOf(transfers, station.id);

  return (
    <aside className="station-panel" aria-label="车站详情">
      <header className="station-panel__head">
        <div>
          <h2>{displayName}</h2>
          <p className="station-panel__sub">
            {station.name_pinyin}
            {station.name_en ? ` · ${station.name_en}` : ""}
          </p>
        </div>
        <button type="button" className="station-panel__close" onClick={onClose} aria-label="关闭详情">
          ×
        </button>
      </header>

      <div className="station-panel__body">
        <section>
          <h3>线路</h3>
          <ul className="chips">
            {station.lines.map((id) => {
              const l = lineById.get(id);
              return (
                <li key={id} className="chip">
                  <i style={{ background: l?.colour ?? "#999" }} />
                  {l?.name ?? id}
                  <em>{l ? (TYPE_LABEL[l.type] ?? l.type) : ""}</em>
                </li>
              );
            })}
          </ul>
        </section>

        <section>
          <h3>站序</h3>
          <table className="seq">
            <thead>
              <tr>
                <th>线路</th>
                <th>位置</th>
                <th>上一站</th>
                <th>下一站</th>
              </tr>
            </thead>
            <tbody>
              {nb.map((n) => (
                <tr key={`${n.branchId}-${n.seq}`}>
                  <td>{lineById.get(n.lineId)?.name ?? n.lineId}</td>
                  <td className="num">
                    {n.seq}/{n.total}
                    {n.isLoop ? " ↻" : ""}
                  </td>
                  <td>{n.prev ?? "—（起点）"}</td>
                  <td>{n.next ?? "—（终点）"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {tr.length > 0 && (
          <section>
            <h3>同站名换乘</h3>
            <ul className="transfers">
              {tr.map(({ t, otherId }) => (
                <li key={t.id}>
                  <button type="button" className="link" onClick={() => onPick(otherId)}>
                    {names.get(otherId) ?? otherId}
                  </button>
                  <span className="badge">{t.type}</span>
                  <span className={`badge conf-${t.type_confidence}`}>{t.type_confidence}</span>
                  <span className="num">{t.dist_m.toFixed(0)} m</span>
                  {t.type_note ? <p className="note">{t.type_note}</p> : null}
                </li>
              ))}
            </ul>
            <p className="note">步行时间无可靠来源，一律留空（ADR R5）。</p>
          </section>
        )}

        <section>
          <h3>数据</h3>
          <dl className="kv">
            <dt>站 id</dt>
            <dd>{station.id}</dd>
            <dt>所属城市</dt>
            <dd>{station.city}</dd>
            <dt>合并方式</dt>
            <dd>{mergeNote(station.merge)}</dd>
            <dt>OSM 节点</dt>
            <dd>{station.slots.map((s) => s.node).join("、")}</dd>
            <dt>来源</dt>
            <dd>
              {station.source}（{station.source_license}）
            </dd>
            <dt>数据截止</dt>
            <dd>{station.as_of}</dd>
          </dl>
        </section>
      </div>
    </aside>
  );
}
