import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { reducedMotion } from "../api.js";
import { useWidth } from "../hooks.js";

// The chain of datasets as a rail of nodes. Links light up as the attacker reaches each dataset.
// nodes: [{ key, kicker, label, state }]  state: done | current | idle | safe | dim
// links: [{ state }]                        state: on | off | broken
export default function ChainRail({ nodes, links, onPick }) {
  const [wrapRef, width] = useWidth(900);
  const svgRef = useRef(null);

  useEffect(() => {
    const n = nodes.length;
    if (!n) return;
    const gap = 30;
    const H = 78;
    const W = Math.max(width, Math.max(720, n * 118));
    const nodeW = (W - (n - 1) * gap - 8) / n;
    const xAt = (i) => 4 + i * (nodeW + gap);
    const dur = reducedMotion() ? 0 : 300;

    const svg = d3.select(svgRef.current).attr("viewBox", `0 0 ${W} ${H + 8}`).attr("width", W).attr("height", H + 8);

    const defs = svg.selectAll("defs").data([0]).join("defs");
    ["on", "broken"].forEach((k) => {
      defs.selectAll(`marker#arrow-${k}`).data([k]).join((e) =>
        e.append("marker").attr("id", `arrow-${k}`).attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
          .attr("markerWidth", 7).attr("markerHeight", 7).attr("orient", "auto")
          .call((m) => m.append("path").attr("d", "M0,0 L10,5 L0,10 z").attr("class", `arrowhead ${k}`)));
    });

    // links
    const ly = H / 2 + 4;
    const lg = svg.selectAll("g.links").data([0]).join("g").attr("class", "links");
    lg.selectAll("g.link")
      .data(links, (_, i) => i)
      .join((e) => {
        const g = e.append("g").attr("class", "link");
        g.append("line").attr("class", "lline");
        g.append("line").attr("class", "lcut");
        return g;
      })
      .each(function (d, i) {
        const g = d3.select(this);
        const x1 = xAt(i) + nodeW + 2;
        const x2 = xAt(i + 1) - 3;
        g.select("line.lline")
          .attr("x1", x1).attr("x2", x2).attr("y1", ly).attr("y2", ly)
          .attr("marker-end", d.state === "on" ? "url(#arrow-on)" : null)
          .transition().duration(dur)
          .attr("class", `lline ${d.state}`);
        const mid = (x1 + x2) / 2;
        g.select("line.lcut")
          .attr("x1", mid - 4).attr("x2", mid + 4).attr("y1", ly - 9).attr("y2", ly + 9)
          .attr("class", `lcut ${d.state === "broken" ? "show" : ""}`);
      });

    // nodes
    const ng = svg.selectAll("g.nodes").data([0]).join("g").attr("class", "nodes");
    const node = ng
      .selectAll("g.rnode")
      .data(nodes, (d) => d.key)
      .join((e) => {
        const g = e.append("g").attr("class", "rnode").attr("tabindex", 0).attr("role", "button");
        g.append("rect").attr("class", "rbox").attr("rx", 12).attr("y", 4);
        g.append("rect").attr("class", "rring").attr("rx", 15).attr("y", 1);
        const fo = g.append("foreignObject").attr("y", 4);
        const div = fo.append("xhtml:div").attr("class", "rlabel");
        div.append("xhtml:span").attr("class", "k");
        div.append("xhtml:span").attr("class", "n");
        return g;
      });

    node
      .attr("transform", (_, i) => `translate(${xAt(i)}, 0)`)
      .attr("aria-label", (d, i) => `Step ${i + 1}: ${d.label}`)
      .attr("aria-current", (d) => (d.state === "current" || d.state === "safe" ? "step" : null))
      .on("click", (_, d) => onPick && onPick(nodes.indexOf(d)))
      .on("keydown", (ev, d) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          onPick && onPick(nodes.indexOf(d));
        }
      });
    node.select("rect.rbox").attr("width", nodeW).attr("height", H - 4)
      .transition().duration(dur).attr("class", (d) => `rbox ${d.state}`);
    node.select("rect.rring").attr("x", -3).attr("width", nodeW + 6).attr("height", H + 2)
      .attr("class", (d) => `rring ${d.state === "current" ? "current" : d.state === "safe" ? "safe" : ""}`);
    node.select("foreignObject").attr("width", nodeW).attr("height", H - 4);
    node.select(".rlabel").attr("class", (d) => `rlabel ${d.state}`);
    node.select("span.k").text((d) => d.kicker);
    node.select("span.n").text((d) => d.label);
  }, [nodes, links, width, onPick]);

  return (
    <div className="rail-scroll" ref={wrapRef}>
      <svg ref={svgRef} className="rail" aria-label="Chain of datasets the attacker links" />
    </div>
  );
}
