import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { fmt, pct, reducedMotion } from "../api.js";
import { useWidth } from "../hooks.js";

const dur = () => (reducedMotion() ? 0 : 600);

// Each official linkage attack: re-identification rate before (names removed in the original) and after (our release).
export function AttackBars({ attacks }) {
  const [wrapRef, width] = useWidth(520);
  const svgRef = useRef(null);
  useEffect(() => {
    const W = Math.max(260, width);
    const labelH = 18;
    const barH = 14;
    const groupH = labelH + barH * 2 + 6 + 16;
    const H = attacks.length * groupH + 24;
    const right = 52;
    const x = d3.scaleLinear().domain([0, 1]).range([0, W - right]);
    const svg = d3.select(svgRef.current).attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H);
    svg.selectAll("*").remove();
    const g = svg.selectAll("g.grp").data(attacks).join("g").attr("class", "grp")
      .attr("transform", (_, i) => `translate(0, ${i * groupH})`);
    g.append("text").attr("class", "clabel").attr("y", 13).text((d) => d.adversary.replace(/_/g, " "));
    [["before", "bar-risk", 0], ["after", "bar-safe", 1]].forEach(([key, cls, j]) => {
      const y = labelH + j * (barH + 4);
      g.append("rect").attr("class", "ctrack").attr("x", 0).attr("y", y).attr("height", barH).attr("rx", 3).attr("width", W - right);
      g.append("rect").attr("class", cls).attr("x", 0).attr("y", y).attr("height", barH).attr("rx", 3).attr("width", 0)
        .transition().duration(dur()).attr("width", (d) => Math.max(d[key] > 0 ? 3 : 0, x(d[key] || 0)));
      g.append("text").attr("class", `cnum ${cls}`).attr("x", W).attr("y", y + 11).attr("text-anchor", "end")
        .text((d) => pct(d[key], d[key] && d[key] < 0.1 ? 1 : 0));
    });
    const legend = svg.append("g").attr("transform", `translate(0, ${H - 10})`);
    [["Names removed (original)", "bar-risk"], ["Our release", "bar-safe"]].forEach(([t, cls], i) => {
      const lg = legend.append("g").attr("transform", `translate(${i * 190}, 0)`);
      lg.append("rect").attr("class", cls).attr("width", 10).attr("height", 10).attr("y", -9).attr("rx", 2);
      lg.append("text").attr("class", "clegend").attr("x", 16).text(t);
    });
  }, [attacks, width]);
  return (
    <div ref={wrapRef} className="chart">
      <svg ref={svgRef} role="img"
        aria-label={attacks.map((a) => `${a.adversary}: ${pct(a.before)} before, ${pct(a.after)} after`).join("; ")} />
    </div>
  );
}

// How small a group each post or news clip narrows our release to. Bins under 5 are the risk.
export function PoolHistogram({ histogram }) {
  const [wrapRef, width] = useWidth(520);
  const svgRef = useRef(null);
  useEffect(() => {
    const W = Math.max(260, width);
    const H = 230;
    const m = { top: 22, right: 8, bottom: 46, left: 8 };
    const x = d3.scaleBand().domain(histogram.map((d) => d.bin)).range([m.left, W - m.right]).padding(0.18);
    const y = d3.scaleLinear().domain([0, d3.max(histogram, (d) => d.count) || 1]).nice().range([H - m.bottom, m.top]);
    const small = (bin) => bin === "0" || bin.startsWith("1–");
    const svg = d3.select(svgRef.current).attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H);
    svg.selectAll("*").remove();
    svg.append("g").selectAll("line").data(y.ticks(4)).join("line").attr("class", "cgrid")
      .attr("x1", m.left).attr("x2", W - m.right).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));
    svg.append("g").selectAll("rect").data(histogram).join("rect")
      .attr("class", (d) => (d.bin === "0" ? "bar-muted" : small(d.bin) ? "bar-risk" : "bar-safe"))
      .attr("x", (d) => x(d.bin)).attr("width", x.bandwidth()).attr("rx", 3)
      .attr("y", H - m.bottom).attr("height", 0)
      .transition().duration(dur()).attr("y", (d) => y(d.count)).attr("height", (d) => H - m.bottom - y(d.count));
    svg.append("g").selectAll("text").data(histogram).join("text").attr("class", "cnum").attr("text-anchor", "middle")
      .attr("x", (d) => x(d.bin) + x.bandwidth() / 2).attr("y", (d) => y(d.count) - 5).text((d) => fmt(d.count));
    svg.append("g").selectAll("text").data(histogram).join("text").attr("class", "ctick").attr("text-anchor", "middle")
      .attr("x", (d) => x(d.bin) + x.bandwidth() / 2).attr("y", H - m.bottom + 16)
      .text((d) => (d.bin.endsWith("–99999") ? `${d.bin.split("–")[0]}+` : d.bin));
    svg.append("text").attr("class", "clegend").attr("x", W / 2).attr("y", H - 8).attr("text-anchor", "middle")
      .text("visits that still fit one post or news clip");
  }, [histogram, width]);
  return (
    <div ref={wrapRef} className="chart">
      <svg ref={svgRef} role="img" aria-label={histogram.map((d) => `${d.bin}: ${d.count}`).join("; ")} />
    </div>
  );
}

// Utility tasks: score from 0 to 1, one bar each.
export function UtilityBars({ tasks }) {
  const [wrapRef, width] = useWidth(520);
  const svgRef = useRef(null);
  useEffect(() => {
    const W = Math.max(260, width);
    const rowH = 44;
    const H = tasks.length * rowH + 4;
    const right = 48;
    const x = d3.scaleLinear().domain([0, 1]).range([0, W - right]);
    const svg = d3.select(svgRef.current).attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H);
    svg.selectAll("*").remove();
    const g = svg.selectAll("g").data(tasks).join("g").attr("transform", (_, i) => `translate(0, ${i * rowH})`);
    g.append("text").attr("class", "clabel").attr("y", 13).text((d) => `${d.id} · ${d.description}`);
    g.append("rect").attr("class", "ctrack").attr("y", 20).attr("height", 12).attr("rx", 3).attr("width", W - right);
    g.append("rect").attr("class", (d) => (d.score >= 0.7 ? "bar-safe" : "bar-risk")).attr("y", 20).attr("height", 12)
      .attr("rx", 3).attr("width", 0).transition().duration(dur()).attr("width", (d) => x(d.score));
    g.append("text").attr("class", "cnum").attr("x", W).attr("y", 31).attr("text-anchor", "end").text((d) => d.score.toFixed(2));
  }, [tasks, width]);
  return (
    <div ref={wrapRef} className="chart">
      <svg ref={svgRef} role="img" aria-label={tasks.map((t) => `${t.id}: ${t.score.toFixed(2)}`).join("; ")} />
    </div>
  );
}
