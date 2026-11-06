import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { fmt, reducedMotion } from "../api.js";
import { useWidth } from "../hooks.js";

// Log-scale funnel: one row per clue, a label above each bar and the count at the right.
// tone: "risk" (attacker wins) or "safe" (our release holds) colours the last row.
export default function Funnel({ rows, tone = "risk" }) {
  const [wrapRef, width] = useWidth(560);
  const svgRef = useRef(null);
  const prev = useRef(new Map());

  useEffect(() => {
    if (!rows || !rows.length) return;
    const numW = 78;
    const rowH = 46;
    const barH = 14;
    const W = Math.max(240, width);
    const H = rows.length * rowH;
    const max = rows[0][1] || 1;
    const x = d3.scaleLog().domain([1, max + 1]).range([0, W - numW - 12]).clamp(true);
    const barW = (n) => Math.max(4, x(n + 1));
    const dur = reducedMotion() ? 0 : 500;

    const svg = d3.select(svgRef.current).attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H);
    const data = rows.map(([label, n], i) => ({ key: `${i}:${label}`, label, n, i, last: i === rows.length - 1 }));

    const g = svg
      .selectAll("g.frow")
      .data(data, (d) => d.key)
      .join((enter) => {
        const e = enter.append("g").attr("class", "frow");
        e.append("text").attr("class", "flabel").attr("x", 0).attr("y", 13);
        e.append("rect").attr("class", "ftrack").attr("x", 0).attr("y", 20).attr("rx", 4).attr("height", barH);
        e.append("rect").attr("class", "ffill").attr("x", 0).attr("y", 20).attr("rx", 4).attr("height", barH)
          .attr("width", (d) => prev.current.get(d.i) ?? 0);
        e.append("text").attr("class", "fnum").attr("text-anchor", "end").attr("y", 32);
        return e;
      });

    g.attr("transform", (d) => `translate(0, ${d.i * rowH})`);
    g.select("text.flabel").text((d) => d.label);
    g.select("rect.ftrack").attr("width", W - numW - 12);
    g.select("rect.ffill")
      .attr("class", (d) => `ffill${d.last ? ` last ${tone}` : ""}`)
      .transition()
      .duration(dur)
      .ease(d3.easeCubicOut)
      .attr("width", (d) => barW(d.n));
    g.select("text.fnum")
      .attr("x", W)
      .attr("class", (d) => `fnum${d.last ? ` last ${tone}` : ""}`)
      .text((d) => fmt(d.n));

    prev.current = new Map(data.map((d) => [d.i, barW(d.n)]));
  }, [rows, width, tone]);

  return (
    <div className="funnel" ref={wrapRef}>
      <svg ref={svgRef} role="img" aria-label={rows?.map(([l, n]) => `${l}: ${n}`).join("; ")} />
    </div>
  );
}
