/* PETs Transformer web app. One state object, one render per step; every number comes from the local API. */
"use strict";

const S = {
  step: "data", cat: null, sessions: [], session: null, scan: null, plan: null, results: null, history: [],
  viewing: null, picked: [], cmp: null, tradeoff: null, compare: null, table: null, textView: "after",
  receiverChoice: null, custom: null, busy: "", mask: true, play: "", tabs: { scan: "tables", plan: "tradeoff", release: "records" },
};
const STEPS = [
  ["data", "Data"], ["scan", "Risk scan"], ["plan", "Receiver & plan"], ["approve", "Review & approve"], ["release", "Release & proof"],
];
const ROLE_LABEL = {
  direct_identifier: "identifies a person", quasi_identifier: "outsider may know it", sensitive_attribute: "sensitive fact",
  technical_identifier: "link / code", record_key: "row key", free_text: "free text", non_sensitive: "harmless",
};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = n => Number(n).toLocaleString("en-US");
const pct = (x, d = 0) => x == null ? "–" : (100 * x).toFixed(d) + "%";
const when = iso => iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const plural = (n, word) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
const $ = sel => document.querySelector(sel);

/* personal values are masked on screen by default (screen sharing, demos); the data itself is untouched */
const maskValue = v => String(v ?? "").replace(/[\p{L}\p{N}]+/gu, w => w[0] + "•".repeat(Math.min(w.length - 1, 6)));
const roleOf = (table, column) => (S.scan?.detections.columns.find(d => d.table === table && d.column === column) || {}).privacy_role || "";
const MASKED_ROLES = ["direct_identifier", "free_text"];  // free text often holds names (signatures, relatives)
const shown = (table, column, v) => {
  if (!S.mask) return String(v ?? "");
  if (!S.scan) return /^[\d\s.,:+\-/]*$/.test(String(v ?? "")) ? String(v ?? "") : maskValue(v);  // roles unknown until the scan
  return MASKED_ROLES.includes(roleOf(table, column)) ? maskValue(v) : String(v ?? "");
};
const clip = (v, n = 120) => { const t = String(v ?? ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };

/* ---------------------------------------------------------------- api */
async function api(path, opts = {}) {
  const init = { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), headers: {} };
  if (opts.form) init.body = opts.form;
  else if (opts.body) { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || `request failed (${res.status})`);
  return data;
}
async function act(label, fn) {
  S.busy = label; render();
  try { await fn(); } catch (e) { toast(e.message, true); } finally { S.busy = ""; render(); }
}
function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), err ? 7000 : 3500);
}
const sid = () => S.session.id;
function remember() { try { localStorage.setItem("pets.session", S.session ? sid() : ""); } catch (e) { /* storage off */ } }

/* ---------------------------------------------------------------- shell */
function stepsDone() {
  return { data: !!S.session, scan: !!S.scan, plan: !!S.plan, approve: !!S.plan?.plan.approved, release: !!S.results };
}
function canOpen(step) {
  const d = stepsDone();
  return { data: true, scan: d.data, plan: d.scan, approve: d.plan, release: d.approve || d.release }[step];
}
function render() {
  const done = stepsDone();
  $("#steps").innerHTML = STEPS.map(([k, label], i) =>
    `<button data-step="${k}" ${k === S.step ? 'aria-current="step"' : ""} class="${done[k] && k !== S.step ? "done" : ""}" ${canOpen(k) ? "" : "disabled"}>
      <span class="n">${done[k] && k !== S.step ? "✓" : i + 1}</span>${label}</button>`).join("");
  renderTicker();
  $("#page").innerHTML = VIEWS[S.step]() + nextBar();
  wire();
}
function renderTicker() {
  const t = $("#ticker"), worst = worstTable();
  t.hidden = !worst;
  if (!worst) return;
  const after = S.results?.summary;
  t.innerHTML = `<span class="eyebrow">People singled out</span>
    <div class="tick risk"><span>Raw data</span><b>${pct(worst.unique_share)}</b><div class="meter"><b style="width:${100 * worst.unique_share}%"></b></div></div>
    ${after && after.singled_out_after != null ? `<div class="tick safe"><span>Release</span><b>${pct(after.singled_out_after)}</b><div class="meter safe"><b style="width:${Math.max(1, 100 * after.singled_out_after)}%"></b></div></div>` : ""}`;
}
function go(step) { if (canOpen(step)) { S.step = step; render(); window.scrollTo(0, 0); } }
const busy = label => S.busy === label ? ` <span class="busy" aria-label="working"></span>` : "";
const head = (n, title, lede) => `<div class="head"><span class="eyebrow">Step ${n} of 5</span><h1>${title}</h1>${lede ? `<p class="lede">${lede}</p>` : ""}</div>`;
const kpi = (cls, v, l) => `<div class="kpi ${cls}"><div class="v">${v}</div><div class="l">${l}</div></div>`;
function tabs(group, items) {
  const cur = items.some(i => i[0] === S.tabs[group]) ? S.tabs[group] : items[0][0];
  S.tabs[group] = cur;
  return `<div class="tabs" role="tablist">${items.map(([k, label, count]) => `<button role="tab" data-tab="${group}:${k}" aria-selected="${k === cur}">${label}${count != null ? `<span class="count">${count}</span>` : ""}</button>`).join("")}</div>`;
}
const worstTable = () => S.scan ? [...S.scan.risk.tables].sort((a, b) => b.unique_share - a.unique_share)[0] : null;

/* ---------------------------------------------------------------- 1 data */
function dataView() {
  if (S.progress && S.step === "data") return `${head(1, "Bring the data you want to share")}${progressCard()}`;
  if (S.session) return `${readyPanel()}${tablesPanel(S.session.tables)}
    <details class="switcher" ${S.switchOpen ? "open" : ""}><summary><span>Load different data or reopen earlier work</span><span class="small">${plural(S.sessions.length, "dataset")} in your workspace</span></summary>
      <div class="page">${loaders()}${workspacePanel()}</div></details>`;
  return `${head(1, "Bring the data you want to share", "Drop the tables as CSV files (or one ZIP), pick an example, or reopen earlier work. Files are copied into a local folder on this computer; nothing is uploaded anywhere.")}
    ${loaders()}${workspacePanel()}`;
}
function loaders() {
  const samples = S.cat?.samples || [];
  return `<div class="grid2">
    <div class="panel"><h2>Your files</h2>
      <label class="field">Dataset name<input type="text" id="dsname" value="my-data"></label>
      <div class="drop" id="drop" tabindex="0" role="button" aria-label="Choose CSV or ZIP files">
        <span class="icon" aria-hidden="true">↑</span><b>Drop CSV or ZIP files here</b><span class="small">or click to choose. One file per table; the file name becomes the table name.</span>
        <input type="file" id="files" accept=".csv,.zip" multiple hidden></div></div>
    <div class="panel"><h2>Or try an example</h2><p class="small">Synthetic datasets from the TrustED challenge package.</p>
      <div class="cards">${samples.map(x => `<button class="choice" data-sample="${esc(x.name)}"><span class="k">${x.tables.length} tables</span><b>${esc(x.name.replace(/_/g, " "))}</b><span class="small">${esc(x.tables.slice(0, 4).join(", "))}${x.tables.length > 4 ? "…" : ""}</span></button>`).join("") || `<p class="small">No sample folder found (set PETS_PACKAGE_ROOT).</p>`}</div></div>
  </div>`;
}
function readyPanel() {
  const T = S.session.tables, rows = T.reduce((n, t) => n + t.rows, 0), cols = T.reduce((n, t) => n + t.columns.length, 0);
  const mb = (S.sessions.find(x => x.id === S.session.id) || {}).bytes;
  return `<div class="panel ready"><div class="spread"><div class="head"><span class="eyebrow">Step 1 of 5 · dataset ready</span><h1>${esc(S.session.name)}</h1></div>
      <button class="btn primary lg" data-go="scan">Scan for risks →</button></div>
    <div class="facts4"><div><b>${fmt(T.length)}</b><span>tables</span></div><div><b>${fmt(rows)}</b><span>rows</span></div><div><b>${fmt(cols)}</b><span>columns</span></div>${mb ? `<div><b>${(mb / 2 ** 20).toFixed(1)} MB</b><span>on this computer</span></div>` : ""}</div>
    <p class="small">Next, the scan reads every column, finds what identifies people and how the tables connect, and replays an attack on one person.</p></div>`;
}
/* one progress card for every long wait: real percentages for uploads, elapsed time for server work */
function progressCard() {
  const P = S.progress;
  return `<div class="panel progresscard"><div class="spread"><h2>${esc(P.title)}</h2><span class="small mono" id="elapsed">${Math.round((Date.now() - P.started) / 1000)} s</span></div>
    <div class="progress ${P.pct == null ? "indet" : ""}"><b id="pbar" style="width:${P.pct == null ? 35 : Math.round(100 * P.pct)}%"></b></div>
    <p class="small" id="pdetail">${esc(P.detail)}</p>
    ${P.checks ? `<ul class="checks">${P.checks.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}</div>`;
}
function startProgress(title, detail, extra = {}) { S.progress = { title, detail, pct: null, started: Date.now(), ...extra }; render(); }
function setProgress(pct, detail) {
  if (!S.progress) return;
  Object.assign(S.progress, { pct, detail });
  const bar = $("#pbar"), d = $("#pdetail");
  if (bar) { bar.parentElement.classList.toggle("indet", pct == null); bar.style.width = (pct == null ? 35 : Math.round(100 * pct)) + "%"; }
  if (d) d.textContent = detail;
}
setInterval(() => { const e = $("#elapsed"); if (e && S.progress) e.textContent = Math.round((Date.now() - S.progress.started) / 1000) + " s"; }, 1000);
/* the next action, always in reach at the bottom of the screen */
function nextBar() {
  const bar = (info, action) => `<div class="nextbar"><div class="small">${info}</div>${action}</div>`;
  if (S.progress) return "";
  if (S.step === "data" && S.session) return bar(`<b>${esc(S.session.name)}</b> · ${plural(S.session.tables.length, "table")} loaded`, `<button class="btn primary" data-go="scan">Scan for risks →</button>`);
  if (S.step === "scan" && S.scan) { const w = worstTable(); return bar(`${pct(w.unique_share)} of <b>${esc(w.table)}</b> can be singled out today`, `<button class="btn primary" data-go="plan">Choose a receiver →</button>`); }
  if (S.step === "plan" && S.plan) return bar(`Plan for <b>${esc(S.plan.scenario?.recipient || S.plan.plan.scenario_id)}</b>${S.plan.reviews.length ? ` · ${plural(S.plan.reviews.length, "item")} to check` : ""}`, `<button class="btn primary" data-go="approve">Review & approve →</button>`);
  if (S.step === "plan") return bar("Pick who receives the data above.", "");
  if (S.step === "approve") return S.plan.plan.approved ? bar(`Approved by <b>${esc(S.plan.plan.approved_by)}</b>`, `<button class="btn primary" data-go="release">Create the release →</button>`) : bar("Type your name and approve the plan to continue.", "");
  if (S.step === "release" && S.results) return bar(`<b>${esc(S.results.release_id)}</b> · ${S.results.files.map(f => esc(f.name)).join(", ")} + manifest`, `<a class="btn safe" href="/api/sessions/${sid()}/releases/${encodeURIComponent(S.results.release_id)}/release.zip" data-download>Download release (.zip)</a>`);
  return "";
}
function workspacePanel() {
  if (!S.sessions.length) return "";
  return `<div class="panel"><div class="spread"><h2>Your workspace</h2><span class="small">${plural(S.sessions.length, "dataset")} · kept in the local output folder</span></div>
    <div class="list">${S.sessions.map(x => {
      const r = x.last_release, st = x.steps;
      return `<div class="item ${S.session?.id === x.id ? "current" : ""}">
        <div><b>${esc(x.name)}</b><span class="small">${plural(x.tables.length, "table")} · ${(x.bytes / 2 ** 20).toFixed(1)} MB · ${esc(when(x.created_at))}</span></div>
        <div class="dots" title="scanned, planned, approved, released"><i class="${st.scanned ? "on" : ""}"></i><i class="${st.planned ? "on" : ""}"></i><i class="${st.approved ? "on" : ""}"></i><i class="${x.releases ? "on" : ""}"></i><span>${x.releases ? plural(x.releases, "release") : st.planned ? "planned" : st.scanned ? "scanned" : "new"}</span></div>
        <div class="small">${r ? `Last: <b>${esc(r.recipient)}</b> · ${r.singled_out_after != null ? `singled out ${pct(r.singled_out_before)} → <b>${pct(r.singled_out_after)}</b>` : r.epsilon != null ? `statistics, ε ${r.epsilon}` : ""}` : esc(x.receiver || "")}</div>
        <button class="btn small" data-open="${esc(x.id)}">${S.session?.id === x.id ? "Open ✓" : "Open"}</button></div>`;
    }).join("")}</div></div>`;
}
function tablesPanel(tables) {
  const t = tables.find(x => x.name === S.table) || tables[0];
  return `<div class="panel"><div class="spread"><h2>What is inside</h2><span class="small">first rows of each table${S.mask && !S.scan ? " · text hidden until the scan knows which columns are personal" : ""}</span></div>
    <div class="pills">${tables.map(x => `<button data-table="${esc(x.name)}" aria-pressed="${x.name === t.name}">${esc(x.name)} · ${fmt(x.rows)}</button>`).join("")}</div>
    ${grid(t.preview, t.columns, t.name)}</div>`;
}
function grid(rows, columns, table) {
  const cols = columns || Object.keys(rows[0] || {});
  return `<div class="tablewrap"><table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(r =>
    `<tr>${cols.map(c => { const v = table ? shown(table, c, r[c]) : String(r[c] ?? ""); return `<td class="${table ? "c-" + roleOf(table, c) : ""}" title="${esc(clip(v, 600))}">${esc(clip(v))}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>`;
}

/* ---------------------------------------------------------------- 2 risk scan */
function scanView() {
  if (!S.scan) return `${head(2, "What could go wrong if this data were shared as it is")}${S.progress ? progressCard() : `<div class="row"><button class="btn primary lg" data-scan>Scan for risks</button></div>`}`;
  const R = S.scan.risk, det = S.scan.detections.columns, worst = worstTable();
  const outside = R.tables.flatMap(t => t.outside_links.map(c => `${t.table}.${c}`));
  const joined = new Set(R.links.flatMap(l => [l.from_table, l.to_table])).size;
  const special = R.tables.filter(t => t.special_category).map(t => t.table);
  return `${head(2, "What could go wrong if this data were shared as it is", "Found from the data itself: which columns identify people, what outsiders could match, and how the tables connect.")}
  <div class="kpis">
    ${kpi(worst.unique_share >= 0.5 ? "risk" : "warn", pct(worst.unique_share), `of rows in <b>${esc(worst.table)}</b> can be singled out on facts an outsider may know`)}
    ${kpi(outside.length ? "risk" : "ok", fmt(outside.length), "columns match public registers, social media or leaked lists")}
    ${kpi(joined ? "warn" : "ok", fmt(joined), joined ? `tables joined by shared keys: one match unlocks the rest` : "tables joined: each table stands alone")}
    ${kpi(special.length ? "warn" : "ok", special.length ? "Art. 9" : "none", special.length ? `special category data (GDPR) in ${esc(special.join(", "))}` : "special category data (GDPR)")}
  </div>
  ${S.scan.attack ? attackRaw(S.scan.attack.before) : ""}
  <div class="panel"><div class="spread"><h2>How your data connects</h2><div class="legend"><span><i style="background:var(--line-strong)"></i>joined by a shared key</span><span><i style="background:var(--risk)"></i>matchable from outside sources</span></div></div><div class="mapwrap">${connectionMap(R)}</div></div>
  <div class="panel">${tabs("scan", [["tables", "Exposure per table", R.tables.length], ["person", "One person's file", Object.values(R.person || {}).reduce((s, r) => s + r.length, 0)], ["columns", "What each column is", det.length]])}
    ${S.tabs.scan === "tables" ? `<div class="cards">${R.tables.map(exposureCard).join("")}</div>` : ""}
    ${S.tabs.scan === "person" ? personCard(R.person) : ""}
    ${S.tabs.scan === "columns" ? `<div class="spread"><p class="small">Found from column names and values (ID-code checksums, IBAN and card check digits, phone formats, name shapes, dates, code sets). Wrong? Change it; the plan follows your correction.</p><a class="btn small" href="/api/sessions/${sid()}/download/detection.json">Download detection.json</a></div>${detectionTable(det)}` : ""}</div>
`;
}
function factList(obj, table, cls = "") {
  return Object.entries(obj).map(([k, v]) => `<div class="fact"><span>${esc(k)}</span><b class="${cls}">${esc(shown(table, k, v)) || "–"}</b></div>`).join("");
}
function attackRaw(A) {
  const hit = A.outcome === "identified", linked = Object.entries(A.linked || {});
  const total = linked.reduce((s, [, n]) => s + n, 0);
  return `<div class="panel attack raw ${S.play === "scan" ? "play" : ""}">
    <div class="spread"><div><span class="eyebrow">Attack replay on your data</span><h2>How an outsider re-identifies one person</h2></div>
      <button class="btn risk" data-play="scan">▶ Play the attack</button></div>
    <div class="chain">
      <div class="stage"><span class="sn">The outsider knows</span>${factList(A.known, A.table)}<span class="small">from a public register, social media or a leaked list</span></div>
      <div class="stage ${hit ? "hit" : ""}"><span class="sn">Searches ${esc(A.table)}</span><span class="big">${hit ? "1 person" : plural(A.matches, "person").replace("persons", "people")}</span><span class="small">of ${fmt(A.rows)} records fit all ${Object.keys(A.known).length} facts</span></div>
      <div class="stage ${hit ? "hit" : ""}"><span class="sn">Learns who it is</span>${Object.keys(A.revealed).length ? factList(A.revealed, A.table, "risk") : `<span class="small">No single person: the facts fit ${fmt(A.matches)} people.</span>`}</div>
      <div class="stage ${hit && total ? "hit" : ""}"><span class="sn">Unlocks through keys</span>${hit ? `<span class="big">${fmt(total)}</span><span class="small">records about this person</span>${linked.map(([t, n]) => `<div class="fact"><span>${esc(t)}</span><b>${fmt(n)}</b></div>`).join("")}` : `<span class="small">Nothing certain to unlock.</span>`}</div>
    </div>
    ${hit ? `<div class="verdict risk"><span class="badge">Re-identified</span><span>${Object.keys(A.known).length} everyday facts are enough to name this person and open ${plural(total, "record")} across ${plural(linked.length, "table")}. This is the mosaic effect, and it is why the data cannot be shared as it is.</span></div>`
      : `<div class="verdict safe"><span class="badge">Not singled out</span><span>On these facts the person hides among ${fmt(A.matches)} people. Other columns may still expose them; see the tables below.</span></div>`}
  </div>`;
}
function connectionMap(R) {
  const tables = R.tables.map(t => t.table), n = tables.length, cols = Math.min(n, 4);
  const W = 960, nodeW = 200, nodeH = 74, top = 120, gapY = 70, rows = Math.ceil(n / cols);
  const H = top + rows * (nodeH + gapY) + 24;
  const pos = {};
  tables.forEach((t, i) => {
    const r = Math.floor(i / cols), c = i % cols, inRow = Math.min(cols, n - r * cols);
    const span = W / inRow;
    pos[t] = { x: span * c + span / 2, y: top + 40 + r * (nodeH + gapY) };
  });
  const out = { x: W / 2, y: 34 };
  const exp = Object.fromEntries(R.tables.map(t => [t.table, t]));
  const edges = R.links.map((l, i) => {
    const a = pos[l.from_table], b = pos[l.to_table];
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 + (a.y === b.y ? 46 + 14 * i : 0);
    return `<path class="edge" d="M${a.x},${a.y + nodeH / 2} Q${mx},${my + nodeH} ${b.x},${b.y + nodeH / 2}"/>
      <rect class="lab" x="${mx - 58}" y="${my + nodeH / 2 - 11}" width="116" height="22" rx="11"/><text x="${mx}" y="${my + nodeH / 2 + 4}" text-anchor="middle" font-size="11">${esc(l.from_column)}</text>`;
  }).join("");
  const outs = R.tables.filter(t => t.outside_links.length).map(t => {
    const p = pos[t.table];
    return `<path class="edge out" d="M${out.x},${out.y + 22} C${out.x},${(out.y + p.y) / 2} ${p.x},${(out.y + p.y) / 2} ${p.x},${p.y - nodeH / 2}"/>
      <text x="${p.x}" y="${p.y - nodeH / 2 - 8}" text-anchor="middle" font-size="11" class="muted">${esc(t.outside_links.slice(0, 3).join(", "))}${t.outside_links.length > 3 ? "…" : ""}</text>`;
  }).join("");
  const nodes = tables.map(t => {
    const p = pos[t], e = exp[t], hot = e.unique_share >= 0.5 || e.direct_identifiers.length > 0;
    return `<rect class="node ${hot ? "hot" : ""}" x="${p.x - nodeW / 2}" y="${p.y - nodeH / 2}" width="${nodeW}" height="${nodeH}" rx="12"/>
      <text x="${p.x}" y="${p.y - 12}" text-anchor="middle" font-size="14" font-weight="600">${esc(t)}</text>
      <text x="${p.x}" y="${p.y + 6}" text-anchor="middle" font-size="12" class="muted">${fmt(e.rows)} rows</text>
      <text x="${p.x}" y="${p.y + 24}" text-anchor="middle" font-size="12" style="fill:${e.unique_share >= 0.5 ? "var(--risk)" : "var(--muted)"}">${e.quasi_identifiers.length ? pct(e.unique_share) + " singled out" : "no quasi-identifiers"}</text>`;
  }).join("");
  return `<svg class="map" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tables, the keys that join them, and the columns that link to outside sources">
    ${outs}${edges}<rect class="outside" x="${out.x - 230}" y="${out.y - 22}" width="460" height="44" rx="22"/>
    <text x="${out.x}" y="${out.y + 5}" text-anchor="middle" font-size="13" font-weight="600">Outside world: public registers, social media, leaked lists</text>${nodes}</svg>`;
}
function exposureCard(t) {
  const chips = (cols, cls) => cols.map(c => `<span class="tag ${cls}">${esc(c)}</span>`).join(" ");
  return `<div class="panel flat ${t.unique_share >= 0.5 ? "risk" : ""}"><div class="spread"><h3 class="mono">${esc(t.table)}</h3>${t.special_category ? `<span class="tag risk">GDPR Art. 9</span>` : ""}</div>
    <div><div class="spread"><span class="small">singled out on quasi-identifiers</span><b class="num">${pct(t.unique_share)}</b></div><div class="meter"><b style="width:${100 * t.unique_share}%"></b></div></div>
    ${t.direct_identifiers.length ? `<div class="small">Identifies a person: ${chips(t.direct_identifiers, "risk")}</div>` : ""}
    ${t.quasi_identifiers.length ? `<div class="small">An outsider may know: ${chips(t.quasi_identifiers, "warn")}</div>` : ""}
    ${t.sensitive.length ? `<div class="small">Sensitive: ${chips(t.sensitive, "safe")}</div>` : ""}
    ${t.free_text.length ? `<div class="small">Free text: ${chips(t.free_text, "risk")}</div>` : ""}</div>`;
}
function personCard(person) {
  const tables = Object.keys(person || {});
  if (!tables.length) return `<p class="small">No person key found, so records cannot be gathered per person.</p>`;
  return `<p class="small">One person picked the way an attacker would: someone with several records. Everything below is linked through the keys on the map. Red identifies, amber is what an outsider may already know, blue is sensitive.</p>
    ${tables.map(t => `<div class="head"><span class="eyebrow">${esc(t)} · ${plural(person[t].length, "record")}</span>
      ${person[t].map(r => `<div class="record">${Object.entries(r).map(([k, v]) => `<span class="c-${roleOf(t, k)}"><b>${esc(k)}</b>${esc(shown(t, k, String(v).slice(0, 160)))}</span>`).join("")}</div>`).join("")}</div>`).join("")}`;
}
function detectionTable(det) {
  const roles = S.cat.roles, subs = S.cat.subtypes;
  return `<div class="tablewrap"><table><thead><tr><th>Column</th><th>What it is</th><th>Type</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>${det.map((c, i) => `<tr>
    <td class="col">${esc(c.table)}.${esc(c.column)}</td>
    <td><select data-override="${i}" data-field="privacy_role" aria-label="Role of ${esc(c.column)}">${roles.map(r => `<option value="${r}" ${r === c.privacy_role ? "selected" : ""}>${ROLE_LABEL[r] || r}</option>`).join("")}</select></td>
    <td><select data-override="${i}" data-field="subtype" aria-label="Type of ${esc(c.column)}">${subs.map(r => `<option ${r === c.subtype ? "selected" : ""}>${r}</option>`).join("")}</select></td>
    <td class="num">${c.confidence.toFixed(2)}</td><td class="small">${c.evidence.slice(0, 2).map(e => esc(e.detail)).join("<br>")}</td></tr>`).join("")}</tbody></table></div>`;
}

/* ---------------------------------------------------------------- 3 receiver & plan */
const TIME_UNITS = ["week", "month", "day", "hour", "time_of_day"];
function detailOptions(c, forStatistics) {
  if (["TIMESTAMP", "DATE"].includes(c.subtype)) return TIME_UNITS;
  if (c.subtype === "BIRTH_DATE") return ["age_band"];
  if (forStatistics && c.subtype === "DIAGNOSIS_CODE" && S.cat.codelists.includes("diagnosis_group")) return ["diagnosis_group"];
  return [""];
}
function planView() {
  const recv = S.cat.receivers;
  const custom = S.receiverChoice === "custom";
  return `${head(3, "Who gets the data, and for what?", "The receiver decides the protection. A research group under contract can get coded rows; the public gets noisy statistics only. Pick one, or describe your own.")}
  <div class="cards">${recv.map(r => `<button class="choice" data-receiver="${esc(r.id)}" aria-pressed="${S.receiverChoice === r.id}"><span class="k">${esc(r.trust_level.replace(/_/g, " "))} · ${r.kind === "statistics" ? "statistics only" : "rows"}</span><b>${esc(r.recipient)}</b><span class="small">${esc(r.purpose)}</span><span class="small mono">${esc(r.id)}</span></button>`).join("")}
    <button class="choice" data-receiver="custom" aria-pressed="${custom}"><span class="k">your own</span><b>Describe a receiver</b><span class="small">Who they are, how far they are trusted, and which columns they need.</span></button></div>
  ${custom ? customForm() : ""}${busy("plan")}
  ${S.plan ? planPanel() : ""}`;
}
function customForm() {
  const C = S.custom, det = S.scan.detections.columns.filter(c => c.privacy_role !== "record_key");
  const pub = C.trust_level === "public";
  return `<div class="panel"><h2>Describe the receiver</h2>
    <div class="grid3"><label class="field">Receiver<input type="text" data-c="recipient" value="${esc(C.recipient)}"></label>
      <label class="field">Purpose<input type="text" data-c="purpose" value="${esc(C.purpose)}"></label>
      <label class="field">How far they are trusted<select data-c="trust_level">${S.cat.trust_levels.map(t => `<option value="${t}" ${t === C.trust_level ? "selected" : ""}>${t.replace(/_/g, " ")}</option>`).join("")}</select></label></div>
    ${pub ? statisticsBuilder(det) : `<p class="small">Tick what they need. Everything else stays here (data minimisation). Each person must look like at least <input type="text" data-c="k" value="${C.k}" size="2" aria-label="k"> others on what an outsider may know.</p>
    <div class="tablewrap"><table><thead><tr><th></th><th>Column</th><th>What it is</th><th>Resolution</th></tr></thead><tbody>${det.map(c => {
      const key = c.table + "." + c.column, opts = detailOptions(c, false), need = C.needs[key];
      return `<tr><td><input type="checkbox" data-need="${esc(key)}" ${need !== undefined ? "checked" : ""} aria-label="Needs ${esc(key)}"></td><td class="col">${esc(key)}</td><td class="c-${c.privacy_role}">${ROLE_LABEL[c.privacy_role]}</td>
        <td>${opts.length > 1 || opts[0] ? `<select data-detail="${esc(key)}">${opts.map(o => `<option ${o === need ? "selected" : ""}>${o}</option>`).join("")}</select>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div>`}
    <div class="row"><button class="btn primary" data-make="custom">Make the plan</button></div></div>`;
}
function statisticsBuilder(det) {
  const C = S.custom, usable = det.filter(c => ["quasi_identifier", "sensitive_attribute", "non_sensitive"].includes(c.privacy_role));
  return `<p class="small">Public receivers get statistics only: counts with noise added (differential privacy). No rows leave. Budget ε per release <input type="text" data-c="epsilon" value="${C.epsilon}" size="4" aria-label="epsilon">, at most <input type="text" data-c="rows_per_person" value="${C.rows_per_person}" size="2" aria-label="rows per person"> records per person counted.</p>
    ${C.stats.map((st, i) => `<div class="row"><span class="small">Table ${i + 1}: count by</span>${[0, 1, 2].map(j => `<select data-stat="${i}" data-pos="${j}" aria-label="Group ${j + 1}"><option value="">—</option>${usable.map(c => {
      const key = c.table + "." + c.column; return `<option value="${esc(key)}" ${st[j] === key ? "selected" : ""}>${esc(key)}</option>`; }).join("")}</select>`).join("")}</div>`).join("")}
    <div class="row"><button class="btn" data-addstat>Add a table</button></div>`;
}
const planTables = P => [...new Set(P.actions.map(a => a.table))];
function techniqueCounts(P) {
  const counts = {};
  P.actions.forEach(a => (counts[a.technique] = (counts[a.technique] || 0) + 1));
  return Object.entries(counts).map(([t, n]) => `<span class="tech ${t}">${n} ${t}</span>`).join(" ");
}
function planPanel() {
  const P = S.plan.plan;
  const rows = P.actions.map(a => {
    const c = S.scan.detections.columns.find(d => d.table === a.table && d.column === a.column), role = c?.privacy_role || "";
    return `<tr class="${a.reason.startsWith("REVIEW") ? "review" : ""}"><td class="col">${esc(a.table)}.${esc(a.column)}</td><td class="c-${role}">${ROLE_LABEL[role] || ""}</td>
    <td>${techniqueSelect(a, c)}</td><td class="small">${esc(a.reason)}</td></tr>`;
  }).join("");
  const stats = P.aggregates.length ? `<div class="panel flat"><h3>Published statistics · ε ${P.epsilon} per release, ${P.differential_privacy.max_rows_per_unit} records per person, one person = one ${esc(P.differential_privacy.unit)}</h3>
    <div class="stack">${P.aggregates.map((a, i) => `<div style="flex:${a.epsilon};background:${i % 2 ? "var(--ink)" : "var(--safe)"}" title="${esc(a.name)}">${a.epsilon}</div>`).join("")}</div>
    <div class="tablewrap"><table><thead><tr><th>Table</th><th>Counted by</th><th>ε</th><th>Why</th></tr></thead><tbody>${P.aggregates.map(a => `<tr><td class="col">${esc(a.name)}</td><td>${a.dimensions.map(d => esc(d.name || d.column)).join(" × ")}</td><td class="num">${a.epsilon}</td><td class="small">${esc(a.reason)}</td></tr>`).join("")}</tbody></table></div></div>` : "";
  const qis = Object.entries(P.quasi_identifiers);
  return `<div class="panel safe"><div class="spread"><div><span class="eyebrow">The plan</span><h2>${esc(S.plan.scenario?.recipient || P.scenario_id)}</h2></div>
      <div class="row"><a class="btn" href="/api/sessions/${sid()}/download/plan.yaml">Download plan.yaml</a><button class="btn primary" data-go="approve">Review & approve →</button></div></div>
    <div class="row">${techniqueCounts(P)}${P.aggregates.length ? `<span class="tech statistics">${P.aggregates.length} statistics tables</span>` : ""}</div>
    ${S.plan.reviews.length ? `<div class="callout warn">Needs a person's decision: ${esc(S.plan.reviews.join(", "))}</div>` : ""}
    ${S.plan.withheld_tables.length ? `<p class="small">Tables that stay here entirely: ${esc(S.plan.withheld_tables.join(", "))}.</p>` : ""}
    ${qis.length ? `<p class="small">Checked together so that every row has at least <b>${P.k_target - 1}</b> look-alikes: ${qis.map(([t, q]) => `${esc(t)} (${esc(q.join(", "))})`).join("; ")}.</p>` : ""}
    ${rows ? `<div class="tablewrap"><table><thead><tr><th>Column</th><th>What it is</th><th>Protection</th><th>Why</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="small">No rows are released.</p>`}</div>
  ${stats}
  <div class="panel">${tabs("plan", [["tradeoff", "Privacy versus usefulness"], ["receivers", "Same data, other receivers"]])}
    ${S.tabs.plan === "tradeoff" ? tradeoffPanel() : comparePanel()}</div>`;
}
function techniqueSelect(a, c) {
  const opts = [["keep", {}], ["drop", {}], ["pseudonymise", { length: 16 }]];
  const sub = c?.subtype || "";
  if (["TIMESTAMP", "DATE"].includes(sub)) TIME_UNITS.forEach(u => opts.push([`generalise:${u}`, { to: "time", unit: u }]));
  if (sub === "BIRTH_DATE") opts.push(["generalise:age_band", { ...a.params, to: "age_band", width: 10, top: 80, rename_to: "age" }]);
  if (["DIAGNOSIS_CODE", "POSTCODE"].includes(sub)) opts.push(["generalise:truncate 3", { to: "truncate", length: 3 }]);
  if (c?.privacy_role === "free_text") opts.push(["redact_text", a.technique === "redact_text" ? a.params : {}]);
  const current = a.technique === "generalise" ? `generalise:${a.params.to === "time" ? a.params.unit : a.params.to === "truncate" ? "truncate 3" : a.params.to}` : a.technique;
  if (!opts.some(o => o[0] === current)) opts.push([current, a.params]);
  return `<select class="tech ${a.technique}" data-action="${esc(a.table)}|${esc(a.column)}" aria-label="Protection of ${esc(a.column)}">${opts.map(([k, p]) => `<option value="${esc(k)}" data-params='${esc(JSON.stringify(p))}' ${k === current ? "selected" : ""}>${esc(k.replace(":", " → "))}</option>`).join("")}</select>`;
}
function lineChart(points, xKey, series, xLabel) {
  const W = 460, H = 200, L = 40, B = 34, T = 12, Rm = 12, n = points.length;
  const x = i => L + (i * (W - L - Rm)) / Math.max(1, n - 1), y = v => T + (1 - v) * (H - T - B);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(v => `<line class="grid" x1="${L}" x2="${W - Rm}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v * 100}%</text>`).join("");
  const xs = points.map((p, i) => `<text x="${x(i)}" y="${H - B + 16}" text-anchor="middle">${p[xKey]}</text>`).join("");
  const now = points.findIndex(p => p.current);
  const lines = series.map(([key, cls]) => {
    const pts = points.map((p, i) => [x(i), y(Math.min(1, p[key] ?? 0))]);
    return `<polyline class="l${cls}" points="${pts.map(p => p.join(",")).join(" ")}"/>${pts.map((p, i) => `<circle class="p${cls}" cx="${p[0]}" cy="${p[1]}" r="4"><title>${points[i][xKey]}: ${pct(points[i][key], 1)}</title></circle>`).join("")}`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Trade-off chart">${ticks}${now >= 0 ? `<line class="now" x1="${x(now)}" x2="${x(now)}" y1="${T}" y2="${H - B}"/>` : ""}${lines}${xs}<text x="${(W + L) / 2}" y="${H - 2}" text-anchor="middle">${xLabel}</text></svg>`;
}
function tradeoffPanel() {
  const T = S.tradeoff;
  if (!T) return `<p class="small">See how privacy and usefulness move before you choose, computed on your data without releasing anything.</p><div class="row"><button class="btn" data-tradeoff>Show the trade-off</button>${busy("tradeoff")}</div>`;
  const k = T.k.length ? `<div class="legend"><span><i style="background:var(--risk)"></i>attacker's chance to pick the right person</span><span><i style="background:var(--safe)"></i>values kept</span></div>
    ${lineChart(T.k, "k", [["guess_chance", 1], ["cells_kept", 2]], "k: each person looks like at least k-1 others")}
    <div class="row"><span class="small">Use k =</span>${T.k.map(p => `<button class="btn small" data-setk="${p.k}" ${p.current ? "disabled" : ""}>${p.k}</button>`).join("")}${busy("tradeoff")}</div>` : "";
  const e = T.epsilon.length ? `<div class="legend"><span><i style="background:var(--risk)"></i>average error of published numbers</span></div>
    ${lineChart(T.epsilon, "epsilon", [["mean_error", 1]], "ε per release: more budget, less noise, more privacy loss")}` : "";
  return `<div class="grid2" style="align-items:start"><div>${k}${e}</div><div class="callout safe small">Computed on your data without releasing anything. The dashed line is the current plan. Click a value of k to use it; the plan then needs approval again.</div></div>`;
}
function comparePanel() {
  const C = S.compare;
  if (!C) return `<p class="small">Compare what each receiver would get from the same columns.</p><div class="row"><button class="btn" data-compare>Compare receivers</button>${busy("compare")}</div>`;
  const ids = C.receivers.map(r => r.id);
  const rows = C.rows.filter(r => ids.some(i => r[i] !== "withheld"));
  return `<div class="tablewrap"><table><thead><tr><th>Column</th>${C.receivers.map(r => `<th>${esc(r.recipient)}</th>`).join("")}</tr></thead><tbody>
    ${rows.map(r => `<tr><td class="col">${esc(r.table)}.${esc(r.column)}</td>${ids.map(i => `<td><span class="tech ${r[i]}">${esc(r[i])}</span></td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

/* ---------------------------------------------------------------- 4 approve */
function approveView() {
  const P = S.plan.plan, rev = S.plan.reviews;
  return `${head(4, "Review and approve", "Nothing leaves until a named person approves the plan. The approval is written into the plan and into every release manifest.")}
  <div class="grid3">
    <div class="panel"><span class="eyebrow">Receiver</span><b>${esc(S.plan.scenario?.recipient || P.scenario_id)}</b><span class="small">${esc(S.plan.scenario?.purpose || "")}</span></div>
    <div class="panel"><span class="eyebrow">What leaves</span><div class="row">${techniqueCounts(P)}</div><span class="small">${planTables(P).length ? `Tables: ${esc(planTables(P).join(", "))}` : ""}${P.aggregates.length ? ` ${P.aggregates.length} statistics tables, ε ${P.epsilon}` : ""}</span></div>
    <div class="panel ${rev.length ? "risk" : "safe"}"><span class="eyebrow">Open questions</span><b>${rev.length ? rev.length + " to check" : "none"}</b><span class="small">${esc(rev.join(", "))}</span></div></div>
  <div class="panel">${P.approved ? `<div class="callout ok">Approved by <b>${esc(P.approved_by)}</b>.</div>` : ""}
    <div class="row"><label class="field">Approved by<input type="text" id="approver" value="${esc(S.approver ?? P.approved_by ?? "")}" placeholder="Your name"></label>
    ${rev.length ? `<label class="row small"><input type="checkbox" id="confirmrev" ${S.confirmReview ? "checked" : ""}> I checked the open questions</label>` : ""}
    <button class="btn primary" data-approve>${P.approved ? "Approve again" : "Approve the plan"}</button>${busy("approve")}</div></div>
  ${P.approved ? `<div class="row"><button class="btn primary" data-go="release">Create the release →</button></div>` : ""}`;
}

/* ---------------------------------------------------------------- 5 release & proof */
/* usefulness: how much of the released columns survives (dropping unrequested columns is minimisation, not loss) */
function valuesKept(R) {
  const ch = R.tables.flatMap(t => t.changes).filter(c => c.technique !== "drop");
  const before = ch.reduce((s, c) => s + c.filled_before, 0);
  return before ? ch.reduce((s, c) => s + c.filled_after, 0) / before : null;
}
function releaseView() {
  const R = S.results, approved = S.plan?.plan.approved;
  const create = approved && !S.viewing ? `<div class="panel"><div class="row"><label class="field">Receiver name (selects their own key)<input type="text" id="receiver" value="${esc(S.lastReceiver || "receiver")}"></label>
    <button class="btn primary" data-run>${R ? "Create again" : "Create the release"}</button>${busy("run")}</div>
    <p class="small">Each receiver gets codes from a different key, so two receivers cannot join their copies. Every release is kept below for download and comparison.</p></div>` : "";
  if (!R) return `${head(5, "Release and proof")}${create}`;
  const m = R.summary, kept = valuesKept(R), A = R.attack;
  const banner = S.viewing ? `<div class="banner"><span>Viewing an earlier release: <b>${esc(m.release_id)}</b>, made ${esc(when(m.created_at))}.</span>${S.history[0] && S.history[0].release_id !== m.release_id ? `<button class="btn small" data-view="${esc(S.history[0].release_id)}">Open the latest</button>` : ""}</div>` : "";
  return `${head(5, "Release and proof", `<b>${esc(m.release_id)}</b> for ${esc(m.recipient)} · approved by ${esc(m.approved_by || "–")} · ${esc(when(m.created_at))}`)}
  ${banner}${create}
  <div class="kpis">
    ${m.singled_out_after != null ? kpi("safe", `${pct(m.singled_out_after)} <s>${pct(m.singled_out_before)}</s>`, "of people singled out on what an outsider knows (raw value struck through)") : ""}
    ${m.guess_chance_after != null ? kpi("safe", pct(m.guess_chance_after, 1), "average chance an attacker picks the right person") : ""}
    ${kept != null ? kpi(kept >= 0.8 ? "ok" : "warn", pct(kept, 1), "of values in the released columns survive (the rest blanked for k)") : ""}
    ${m.epsilon != null ? kpi("safe", `ε ${m.epsilon}`, "privacy budget spent by the published statistics") : ""}
    ${A?.after ? kpi(A.after.outcome === "identified" ? "risk" : "safe", attackHeadline(A.after), "the replayed attack on the same person") : ""}
  </div>
  ${A?.after ? attackDuel(A.before, A.after) : ""}
  <div class="panel">${tabs("release", [
    ["records", "Records before → after", R.tables.length ? null : 0], ["columns", "Column changes"], ["attacker", "Attacker's view", R.attacker.length],
    ...(R.text.length ? [["text", "Free text", R.text.length]] : []), ...(R.statistics.length ? [["stats", "Statistics", R.statistics.length]] : []),
    ["risks", "Remaining risks", R.residual_risks.length], ["history", "History & compare", S.history.length],
  ])}
    ${({ records: recordsTab, columns: columnsTab, attacker: attackerTab, text: textTab, stats: statsTab, risks: risksTab, history: historyTab })[S.tabs.release](R)}</div>
  <div class="panel safe"><div class="spread"><div><span class="eyebrow">Download</span><h2>${R.files.map(f => esc(f.name)).join(", ")} + manifest</h2></div>
    <div class="row"><a class="btn safe" href="/api/sessions/${sid()}/releases/${encodeURIComponent(R.release_id)}/release.zip" data-download>Download release (.zip)</a><a class="btn" href="/api/sessions/${sid()}/download/plan.yaml">Approved plan</a></div></div>
    <p class="small">The zip holds only what may be shared. Row maps stay in the private folder on this computer. ${m.epsilon != null ? `Downloading publishes the statistics and records ε ${m.epsilon} in the privacy budget ledger${R.published ? " (already recorded)" : ""}.` : ""}</p></div>`;
}
function attackHeadline(a) {
  if (a.outcome === "withheld") return "no rows";
  if (a.outcome === "removed") return "row removed";
  return a.outcome === "identified" ? "found" : `1 in ${fmt(a.matches)}`;
}
function attackDuel(b, a) {
  const linked = Object.entries(b.linked || {}), total = linked.reduce((s, [, n]) => s + n, 0);
  const failed = a.outcome !== "identified";
  const afterFits = a.outcome === "withheld" ? "no rows" : a.outcome === "removed" ? "not there" : a.matches === 1 ? "1 person" : `${fmt(a.matches)} people`;
  const afterFitsNote = a.outcome === "withheld" ? `${esc(a.table)} is not released at all` : a.outcome === "removed" ? "the row was removed to reach k" : `fit what is left of the facts: ${a.usable.length ? esc(a.usable.join(", ")) : "nothing to match on"}`;
  const hiddenList = Object.entries(a.hidden || {}).map(([c, t]) => `<div class="fact"><span>${esc(c)}</span><b class="safe">${t === "pseudonymise" ? "keyed code" : t === "drop" ? "dropped" : esc(t)}</b></div>`).join("");
  return `<div class="panel attack rel ${S.play === "release" ? "play" : ""}">
    <div class="spread"><div><span class="eyebrow">The same attack, replayed on the release</span><h2>Same outsider, same facts, same person</h2></div><button class="btn safe" data-play="release">▶ Replay</button></div>
    <div class="duel">
      <div class="side raw"><span class="eyebrow">Raw data</span>
        <div class="stagev"><span class="eyebrow">Knows</span><div>${factList(b.known, b.table)}</div></div>
        <div class="stagev ${b.outcome === "identified" ? "hit" : ""}"><span class="eyebrow">Fits</span><div><span class="big">${b.matches === 1 ? "1 person" : `${fmt(b.matches)} people`}</span><span class="small">of ${fmt(b.rows)} records</span></div></div>
        <div class="stagev ${b.outcome === "identified" ? "hit" : ""}"><span class="eyebrow">Learns</span><div>${Object.keys(b.revealed).length ? factList(b.revealed, b.table, "risk") : `<span class="small">nothing certain</span>`}</div></div>
        <div class="stagev ${total ? "hit" : ""}"><span class="eyebrow">Unlocks</span><div><span class="big">${fmt(total)}</span><span class="small">linked records</span></div></div>
      </div>
      <div class="side rel"><span class="eyebrow">Release</span>
        <div class="stagev"><span class="eyebrow">Knows</span><div>${factList(a.known, a.table)}</div></div>
        <div class="stagev ${failed ? "miss" : ""}"><span class="eyebrow">Fits</span><div><span class="big">${afterFits}</span><span class="small">${afterFitsNote}</span></div></div>
        <div class="stagev ${failed ? "miss" : ""}"><span class="eyebrow">Learns</span><div>${Object.keys(a.revealed).length ? factList(a.revealed, a.table, "risk") : hiddenList || `<span class="small">no identifiers in the release</span>`}</div></div>
        <div class="stagev ${failed ? "miss" : ""}"><span class="eyebrow">Unlocks</span><div><span class="big">${failed ? "0" : fmt(Object.values(a.linked).reduce((s, n) => s + n, 0))}</span><span class="small">${failed ? (a.outcome === "one_in_n" ? `certain records; only a guess with a 1 in ${fmt(a.matches)} chance` : "records") : "records reachable"}</span></div></div>
      </div>
    </div>
    <div class="verdict ${failed ? "safe" : "risk"}"><span class="badge">${failed ? "Attack fails" : "Still found"}</span><span>${failed
      ? `The outsider who named this person in the raw data ${a.outcome === "one_in_n" ? `now faces ${fmt(a.matches)} equally likely people and no name, ID code or contact detail` : a.outcome === "withheld" ? "finds no rows to search: only statistics leave" : "cannot find their row: it was removed to protect them"}.`
      : "The release still singles this person out. Raise k, drop or coarsen a quasi-identifier, and release again."}</span></div>
  </div>`;
}
function recordsTab(R) {
  const withPairs = R.tables.filter(t => t.pairs?.length);
  if (!withPairs.length) return R.tables.length ? R.tables.map(t => `<div class="grid2"><div><span class="eyebrow">Raw (stays here)</span>${grid(t.raw_preview, null, t.name)}</div><div><span class="eyebrow">Released</span>${grid(t.preview)}</div></div>`).join("") : `<p class="small">No rows are released: only statistics.</p>`;
  const t = withPairs.find(x => x.name === S.table) || withPairs[0];
  const renamed = Object.fromEntries(t.changes.map(c => [c.column, c.released_as || c.column]));
  const cols = Object.keys(t.pairs[0].raw);
  const tech = c => R.techniques[`${t.name}.${c}`] || "keep";
  const cell = (pair, c) => {
    const k = tech(c), base = k.split(":")[0];
    if (base === "drop" || base === "withheld") return `<td class="d-drop"></td>`;
    const v = pair.released[renamed[c]];
    return v === "" || v == null ? `<td class="d-blank"></td>` : `<td class="d-${base}" title="${esc(v)}">${esc(v)}</td>`;
  };
  return `<div class="spread"><p class="small">The same records, raw and released, matched on this computer through the private row map (which never leaves). Read each pair top to bottom.</p>
      ${withPairs.length > 1 ? `<div class="pills">${withPairs.map(x => `<button data-table="${esc(x.name)}" aria-pressed="${x.name === t.name}">${esc(x.name)}</button>`).join("")}</div>` : ""}</div>
    <div class="tablewrap"><table class="diff"><thead><tr><th></th>${cols.map(c => `<th>${esc(c)}<br><span class="tech ${tech(c).split(":")[0]}">${esc(tech(c))}</span></th>`).join("")}</tr></thead><tbody>
      ${t.pairs.map(p => `<tr class="rawrow"><td class="who">raw</td>${cols.map(c => `<td class="c-${roleOf(t.name, c)}" title="${esc(shown(t.name, c, p.raw[c]))}">${esc(shown(t.name, c, p.raw[c]))}</td>`).join("")}</tr>
        <tr class="relrow"><td class="who">released</td>${cols.map(c => cell(p, c)).join("")}</tr>`).join("")}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--risk)"></i>dropped</span><span><i style="background:var(--safe)"></i>coded or coarsened</span><span><i style="background:var(--warn)"></i>blanked so every row has look-alikes</span><span><i style="background:var(--line-strong)"></i>kept as is</span></div>`;
}
function columnsTab(R) {
  if (!R.tables.length) return `<p class="small">No rows are released.</p>`;
  return R.tables.map(t => {
    const ch = t.changes, blanked = t.suppression ? Object.values(t.suppression.cells_blanked).reduce((s, x) => s + x, 0) : 0;
    return `<div class="spread"><h3 class="mono">${esc(t.name)}: ${fmt(t.rows_in)} rows in, ${fmt(t.rows_out)} out</h3>${t.suppression ? `<span class="small">${fmt(t.suppression.rows_removed)} rows removed, ${fmt(blanked)} values blanked to reach k</span>` : ""}</div>
    <div class="tablewrap"><table><thead><tr><th>Column</th><th>Protection</th><th>Values</th><th>Distinct</th><th>Released values</th></tr></thead><tbody>${ch.map(c => `<tr>
      <td class="col">${esc(c.column)}${c.released_as && c.released_as !== c.column ? ` → ${esc(c.released_as)}` : ""}</td><td><span class="tech ${c.technique}">${esc(c.technique)}</span></td>
      <td class="num">${fmt(c.filled_before)} → ${fmt(c.filled_after)}</td><td class="num">${fmt(c.distinct_before)} → ${fmt(c.distinct_after)}</td>
      <td>${c.top_after.slice(0, 5).map(([v, s]) => `<div class="hbar"><span class="mono">${esc(v)}</span><div class="meter safe"><b style="width:${100 * s}%"></b></div><span>${pct(s)}</span></div>`).join("")}</td></tr>`).join("")}</tbody></table></div>`;
  }).join("");
}
function bucketBar(b) {
  const colors = { alone: "var(--risk)", "2-4": "var(--warn)", "5-9": "var(--safe)", "10-49": "var(--safe)", "50+": "var(--muted)" };
  return `<div class="stack">${Object.entries(b).filter(([, v]) => v > 0).map(([k, v]) => `<div style="flex:${v};background:${colors[k]}" title="${k}: ${pct(v, 1)}">${v > 0.08 ? `${k} ${pct(v)}` : ""}</div>`).join("")}</div>`;
}
function attackerTab(R) {
  if (!R.attacker.length) return `<p class="small">No table was checked for look-alikes (statistics only, or no quasi-identifiers).</p>`;
  return R.attacker.map(v => `<h3>${esc(v.table)}: someone who knows ${esc(v.known.join(", "))}</h3>
    <div class="grid2"><div class="panel flat risk"><span class="eyebrow">Before</span><span class="big num" style="color:var(--risk)">${pct(v.before.unique_share)}</span><span class="small">of ${fmt(v.before.rows)} rows have no look-alike: found with certainty</span>${bucketBar(v.before.buckets)}</div>
      <div class="panel flat safe"><span class="eyebrow">After</span><span class="big num" style="color:var(--safe)">${pct(v.after.unique_share)}</span><span class="small">have no look-alike; an attacker's chance to pick the right person is ${pct(v.after.guess_chance, 1)}</span>${bucketBar(v.after.buckets)}</div></div>`).join("") +
    `<div class="legend"><span><i style="background:var(--risk)"></i>alone</span><span><i style="background:var(--warn)"></i>2–4 look-alikes</span><span><i style="background:var(--safe)"></i>5–49</span><span><i style="background:var(--muted)"></i>50 or more</span></div>`;
}
function textTab(R) {
  const after = S.textView === "after";
  return R.text.map(t => `<div class="spread"><h3 class="mono">${esc(t.column)}</h3>
    <div class="pills"><button data-textview="before" aria-pressed="${!after}">Found</button><button data-textview="after" aria-pressed="${after}">Released</button></div></div>
    <div class="grid2">${t.samples.map(parts => `<div class="sample">${parts.map(p => !p.label ? esc(p.t) : after ? `<span class="tagged">[${esc(p.label)}]</span>` : `<mark title="${esc(p.label)}">${esc(S.mask ? maskValue(p.t) : p.t)}</mark>`).join("")}</div>`).join("")}</div>`).join("");
}
function statsTab(R) {
  const acc = Object.fromEntries(R.accuracy.map(a => [a.name, a]));
  return `<p class="small">Noisy published numbers against the exact numbers (cells with at least 10 records). The exact numbers never leave.</p>
    ${R.statistics.map(s => { const a = acc[s.name] || {}; return `<div class="hbar"><span class="mono">${esc(s.name)}</span><div class="meter safe"><b style="width:${100 * (a.within_10pct || 0)}%"></b></div><span>${pct(a.within_10pct)}</span></div>`; }).join("")}
    <p class="small">Bar: share of cells within 10% of the true value. ε ${R.epsilon} spent in this release.</p>
    <div class="grid2">${R.statistics.slice(0, 2).map(s => `<div><span class="eyebrow">${esc(s.name)} · ${fmt(s.cells)} cells</span>${grid(s.preview)}</div>`).join("")}</div>`;
}
const risksTab = R => `<p class="small">As written in the manifest that travels with the data.</p><ul class="plain">${R.residual_risks.map(r => `<li>${esc(r)}</li>`).join("")}</ul>`;
function historyTab() {
  const H = S.history;
  if (!H.length) return `<p class="small">No releases yet.</p>`;
  const cur = S.results?.release_id;
  return `<p class="small">Every release made from this dataset is kept here. Tick two to compare them.</p>
    <div class="list">${H.map(h => `<div class="item ${h.release_id === cur ? "current" : ""}">
      <div><b class="mono">${esc(h.release_id)}</b><span class="small">${esc(when(h.created_at))} · for ${esc(h.recipient)} · approved by ${esc(h.approved_by || "–")}</span></div>
      <div class="small">${h.k != null ? `k ${h.k}` : ""}${h.epsilon != null ? ` ε ${h.epsilon}` : ""} · ${plural(h.files.length, "file")}</div>
      <div class="small">${h.singled_out_after != null ? `singled out ${pct(h.singled_out_before)} → <b>${pct(h.singled_out_after)}</b>, guess ${pct(h.guess_chance_after, 1)}` : "statistics only"}</div>
      <div class="row"><label class="switch"><input type="checkbox" data-pick="${esc(h.release_id)}" ${S.picked.includes(h.release_id) ? "checked" : ""}> compare</label>
        ${h.release_id === cur ? `<span class="tag ok">open</span>` : `<button class="btn small" data-view="${esc(h.release_id)}">Open</button>`}</div></div>`).join("")}</div>
    ${busy("cmp")}${S.cmp ? compareReleases(S.cmp) : S.picked.length === 1 ? `<p class="small">Tick one more release to compare.</p>` : ""}`;
}
function compareReleases([a, b]) {
  const A = a.summary, B = b.summary;
  const metric = (label, va, vb, show, lowerIsBetter) => {
    const d = va != null && vb != null && va !== vb ? vb - va : null;
    const cls = d == null ? "" : (d < 0) === lowerIsBetter ? "better" : "worse";
    return `<tr><td>${label}</td><td class="num">${va == null ? "–" : show(va)}</td><td class="num">${vb == null ? "–" : show(vb)}</td><td>${d == null ? "" : `<span class="delta ${cls}">${d > 0 ? "+" : ""}${show(d)}</span>`}</td></tr>`;
  };
  const cols = [...new Set([...Object.keys(a.techniques), ...Object.keys(b.techniques)])];
  const changed = cols.filter(c => a.techniques[c] !== b.techniques[c]);
  return `<div class="grid2">
    <div class="head"><h3>Headline numbers</h3><p class="small">A = ${esc(A.release_id)} · B = ${esc(B.release_id)}</p><div class="tablewrap free"><table class="metrics"><thead><tr><th></th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody>
      <tr><td>Receiver</td><td>${esc(A.recipient)}</td><td>${esc(B.recipient)}</td><td></td></tr>
      ${metric("k", A.k, B.k, v => fmt(v), false)}${metric("ε", A.epsilon, B.epsilon, v => (+v).toFixed(2), true)}
      ${metric("Singled out", A.singled_out_after, B.singled_out_after, v => pct(v, 1), true)}
      ${metric("Guess chance", A.guess_chance_after, B.guess_chance_after, v => pct(v, 1), true)}
      ${metric("Values kept", valuesKept(a), valuesKept(b), v => pct(v, 1), false)}
      ${metric("Attack: people to choose from", A.attack_matches, B.attack_matches, v => fmt(v), false)}
    </tbody></table></div></div>
    <div class="head"><h3>Columns treated differently <span class="small">(${changed.length} of ${cols.length})</span></h3>${changed.length ? `<div class="tablewrap free"><table><thead><tr><th>Column</th><th>A</th><th>B</th></tr></thead><tbody>
      ${changed.map(c => `<tr class="changed"><td class="col">${esc(c)}</td><td><span class="tech ${(a.techniques[c] || "withheld").split(":")[0]}">${esc(a.techniques[c] || "withheld")}</span></td><td><span class="tech ${(b.techniques[c] || "withheld").split(":")[0]}">${esc(b.techniques[c] || "withheld")}</span></td></tr>`).join("")}</tbody></table></div>` : `<p class="small">Every column is treated the same way; only k or ε differ.</p>`}</div></div>`;
}

const VIEWS = { data: dataView, scan: scanView, plan: planView, approve: approveView, release: releaseView };

/* ---------------------------------------------------------------- events */
function wire() {
  const page = $("#page");
  document.querySelectorAll("[data-step]").forEach(b => (b.onclick = () => go(b.dataset.step)));
  page.querySelectorAll("[data-go]").forEach(b => (b.onclick = () => { go(b.dataset.go); if (b.dataset.go === "scan" && !S.scan) runScan(); }));
  page.querySelectorAll("[data-tab]").forEach(b => (b.onclick = () => {
    const [group, key] = b.dataset.tab.split(":"); S.tabs[group] = key; render();
    if (group === "plan" && key === "receivers" && !S.compare) loadCompare();
  }));
  page.querySelectorAll("[data-play]").forEach(b => (b.onclick = () => { S.play = ""; render(); requestAnimationFrame(() => play(b.dataset.play)); }));
  page.querySelectorAll("[data-table]").forEach(b => (b.onclick = () => { S.table = b.dataset.table; render(); }));
  page.querySelectorAll("[data-sample]").forEach(b => (b.onclick = () => withProgress(`Opening the ${b.dataset.sample.replace(/_/g, " ")} example`, "Copying the tables into your workspace and reading them…",
    async () => openSession(await api("/api/sessions/sample", { body: { name: b.dataset.sample } })))));
  page.querySelectorAll("[data-scan]").forEach(b => (b.onclick = runScan));
  page.querySelectorAll("details.switcher").forEach(d => (d.ontoggle = () => (S.switchOpen = d.open)));
  page.querySelectorAll("[data-open]").forEach(b => (b.onclick = () => reopen(b.dataset.open)));
  const drop = $("#drop"), input = $("#files");
  if (drop) {
    drop.onclick = () => input.click();
    drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") input.click(); };
    drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = e => { e.preventDefault(); upload(e.dataTransfer.files); };
    input.onchange = () => upload(input.files);
  }
  page.querySelectorAll("[data-override]").forEach(sel => (sel.onchange = () => {
    const c = S.scan.detections.columns[+sel.dataset.override];
    const body = { table: c.table, column: c.column, privacy_role: c.privacy_role, subtype: c.subtype, [sel.dataset.field]: sel.value };
    act("scan", async () => {
      const col = await api(`/api/sessions/${sid()}/detections`, { body });
      S.scan.detections.columns[+sel.dataset.override] = col; S.plan = null; S.results = null; S.tradeoff = null; S.compare = null;
      toast(`${c.column} is now "${ROLE_LABEL[col.privacy_role]}". Make the plan again to use it.`);
    });
  }));
  page.querySelectorAll("[data-receiver]").forEach(b => (b.onclick = () => {
    S.receiverChoice = b.dataset.receiver;
    if (S.receiverChoice === "custom") { if (!S.custom) S.custom = newCustom(); render(); return; }
    makePlan({ scenario_id: S.receiverChoice });
  }));
  page.querySelectorAll("[data-c]").forEach(inp => (inp.onchange = () => { S.custom[inp.dataset.c] = inp.value; if (inp.dataset.c === "trust_level") render(); }));
  page.querySelectorAll("[data-need]").forEach(cb => (cb.onchange = () => {
    const key = cb.dataset.need, sel = page.querySelector(`[data-detail="${CSS.escape(key)}"]`);
    if (cb.checked) S.custom.needs[key] = sel ? sel.value : ""; else delete S.custom.needs[key];
  }));
  page.querySelectorAll("[data-detail]").forEach(sel => (sel.onchange = () => { if (sel.dataset.detail in S.custom.needs) S.custom.needs[sel.dataset.detail] = sel.value; }));
  page.querySelectorAll("[data-stat]").forEach(sel => (sel.onchange = () => { S.custom.stats[+sel.dataset.stat][+sel.dataset.pos] = sel.value; }));
  page.querySelectorAll("[data-addstat]").forEach(b => (b.onclick = () => { S.custom.stats.push(["", "", ""]); render(); }));
  page.querySelectorAll("[data-make]").forEach(b => (b.onclick = () => act("plan", async () => {
    S.plan = await api(`/api/sessions/${sid()}/plan`, { body: { custom: customScenario() } }); planChanged(); S.compare = null;
  })));
  page.querySelectorAll("[data-action]").forEach(sel => (sel.onchange = () => {
    const [table, column] = sel.dataset.action.split("|"), opt = sel.selectedOptions[0];
    const body = { table, column, technique: opt.value.split(":")[0], params: JSON.parse(opt.dataset.params || "{}") };
    act("plan", async () => { S.plan = await api(`/api/sessions/${sid()}/plan/action`, { body }); planChanged(); });
  }));
  page.querySelectorAll("[data-tradeoff]").forEach(b => (b.onclick = () => act("tradeoff", async () => { S.tradeoff = await api(`/api/sessions/${sid()}/tradeoff`); })));
  page.querySelectorAll("[data-setk]").forEach(b => (b.onclick = () => act("tradeoff", async () => {
    S.plan = await api(`/api/sessions/${sid()}/plan/k`, { body: { k: +b.dataset.setk } }); planChanged();
    S.tradeoff = await api(`/api/sessions/${sid()}/tradeoff`);
  })));
  page.querySelectorAll("[data-compare]").forEach(b => (b.onclick = loadCompare));
  // typed values live in S, so the redraws done by act() (busy spinner, errors) keep them
  const approver = $("#approver"), confirmrev = $("#confirmrev"), receiver = $("#receiver");
  if (approver) approver.oninput = () => (S.approver = approver.value);
  if (confirmrev) confirmrev.onchange = () => (S.confirmReview = confirmrev.checked);
  if (receiver) receiver.oninput = () => (S.lastReceiver = receiver.value);
  page.querySelectorAll("[data-approve]").forEach(b => (b.onclick = () => {
    const body = { by: (S.approver ?? approver.value).trim(), confirm_review: !!S.confirmReview };
    act("approve", async () => {
      S.plan = await api(`/api/sessions/${sid()}/approve`, { body });
      toast(`Approved by ${S.plan.plan.approved_by}.`);
    });
  }));
  page.querySelectorAll("[data-run]").forEach(b => (b.onclick = () => {
    S.lastReceiver = receiver.value.trim();
    act("run", async () => {
      S.results = await api(`/api/sessions/${sid()}/run`, { body: { receiver: S.lastReceiver } });
      S.viewing = null; S.cmp = null; S.picked = [];
      await refreshHistory();
      play("release", false);
      toast(`Release ${S.results.release_id} created.`);
    });
  }));
  page.querySelectorAll("[data-view]").forEach(b => (b.onclick = () => act("cmp", async () => {
    S.results = await api(`/api/sessions/${sid()}/releases/${encodeURIComponent(b.dataset.view)}`);
    S.viewing = S.history[0]?.release_id === b.dataset.view ? null : b.dataset.view;
    window.scrollTo(0, 0);
  })));
  page.querySelectorAll("[data-pick]").forEach(cb => (cb.onchange = () => {
    const id = cb.dataset.pick;
    S.picked = cb.checked ? [...S.picked.filter(x => x !== id), id].slice(-2) : S.picked.filter(x => x !== id);
    S.cmp = null;
    if (S.picked.length === 2) act("cmp", async () => {
      const ordered = S.history.filter(h => S.picked.includes(h.release_id)).reverse();  // older first
      S.cmp = await Promise.all(ordered.map(h => api(`/api/sessions/${sid()}/releases/${encodeURIComponent(h.release_id)}`)));
    }); else render();
  }));
  page.querySelectorAll("[data-textview]").forEach(b => (b.onclick = () => { S.textView = b.dataset.textview; render(); }));
  page.querySelectorAll("[data-download]").forEach(a => (a.onclick = async e => {
    e.preventDefault();
    const res = await fetch(a.href);
    if (!res.ok) { toast((await res.json()).error || "download refused", true); return; }
    const blob = await res.blob(), url = URL.createObjectURL(blob), tmp = document.createElement("a");
    tmp.href = url; tmp.download = (res.headers.get("Content-Disposition") || "").split('filename="')[1]?.replace('"', "") || "release.zip";
    tmp.click(); URL.revokeObjectURL(url); S.results.published = true; render();
  }));
}
function planChanged() { S.confirmReview = false; S.results = null; S.viewing = null; S.tradeoff = null; }
function loadCompare() {
  act("compare", async () => { S.compare = await api(`/api/sessions/${sid()}/compare`, { body: { scenario_ids: S.cat.receivers.map(r => r.id) } }); });
}
const mb = n => (n / 2 ** 20).toFixed(n < 10 * 2 ** 20 ? 1 : 0);
function uploadWithProgress(form) {  // XMLHttpRequest reports upload progress; fetch does not
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/sessions/upload");
    x.upload.onprogress = e => { if (e.lengthComputable) setProgress(e.loaded / e.total, `${mb(e.loaded)} of ${mb(e.total)} MB copied`); };
    x.upload.onload = () => setProgress(null, "Reading your tables: counting rows and columns…");
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch (e) { /* not JSON */ } x.status < 300 ? resolve(d) : reject(new Error(d.error || `upload failed (${x.status})`)); };
    x.onerror = () => reject(new Error("the upload was interrupted"));
    x.send(form);
  });
}
async function upload(files) {
  if (!files?.length) return;
  const form = new FormData(), list = [...files], size = list.reduce((n, f) => n + f.size, 0);
  list.forEach(f => form.append("files", f));
  form.append("name", $("#dsname").value || "my-data");
  await withProgress(`Uploading ${plural(list.length, "file")} (${mb(size)} MB)`, "Starting…", async () => {
    setProgress(0, `0 of ${mb(size)} MB copied`);
    openSession(await uploadWithProgress(form));
  });
}
async function withProgress(title, detail, fn, extra) {
  startProgress(title, detail, extra);
  try { await fn(); } catch (e) { toast(e.message, true); } finally { S.progress = null; render(); window.scrollTo(0, 0); }
}
async function refreshHistory() {
  S.history = S.session ? await api(`/api/sessions/${sid()}/releases`) : [];
  S.sessions = await api("/api/sessions");
}
function reopen(id) {
  const name = (S.sessions.find(x => x.id === id) || {}).name || "your dataset";
  S.step = "data";
  return withProgress(`Reopening ${name}`, "Reading the tables, the saved scan, the plan and earlier releases…", () => openExisting(id));
}
function openSession(s) {
  Object.assign(S, { step: "data", switchOpen: false, session: s, scan: null, plan: null, results: null, history: [], viewing: null, picked: [], cmp: null, tradeoff: null, compare: null, table: null, receiverChoice: null, custom: null });
  remember(); refreshHistory().then(render);
}
/* reopen earlier work: scan, plan and the latest release come back as they were left */
async function openExisting(id) {
  const s = await api(`/api/sessions/${id}`);
  Object.assign(S, { session: s, scan: null, plan: null, results: null, viewing: null, picked: [], cmp: null, tradeoff: null, compare: null, table: null, custom: null });
  remember();
  if (s.steps.scanned) S.scan = await api(`/api/sessions/${id}/scan`, { method: "POST" });
  if (s.steps.planned) { S.plan = await api(`/api/sessions/${id}/plan`); S.receiverChoice = S.plan.plan.scenario_id; }
  await refreshHistory();
  if (S.history.length) S.results = await api(`/api/sessions/${id}/releases/${encodeURIComponent(S.history[0].release_id)}`);
  S.step = S.results ? "release" : S.plan ? "plan" : S.scan ? "scan" : "data";
}
const SCAN_CHECKS = ["what each column holds: names, ID codes (with checksums), phones, addresses, dates, codes",
  "which facts an outsider could already know, and how many people they single out",
  "which keys join the tables, so one match unlocks the rest", "an attack on one person, the way an outsider would do it"];
function runScan() {
  S.step = "scan";
  const rows = S.session.tables.reduce((n, t) => n + t.rows, 0);
  return withProgress("Scanning for risks", `Reading ${fmt(rows)} rows in ${plural(S.session.tables.length, "table")}. Large data can take a minute; the result is saved.`, async () => {
    S.scan = await api(`/api/sessions/${sid()}/scan`, { method: "POST" }); play("scan", false);
  }, { checks: SCAN_CHECKS });
}
/* the attack replay animates once; later redraws (tabs, inputs) show it settled */
function play(which, now = true) {
  S.play = which;
  if (now) render();
  setTimeout(() => { if (S.play === which) S.play = ""; }, 3600);
}
function makePlan(body) {
  act("plan", async () => { S.plan = await api(`/api/sessions/${sid()}/plan`, { body }); planChanged(); S.compare = null; });
}
function newCustom() {
  return { recipient: "Partner organisation", purpose: "Analysis agreed in the data-sharing contract", trust_level: "contractual", k: 5, needs: {}, epsilon: 1, rows_per_person: 3, stats: [["", "", ""]] };
}
function customScenario() {
  const C = S.custom, det = S.scan.detections.columns;
  const id = "CUSTOM-" + (C.recipient.toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 24) || "RECEIVER");
  const base = { id, title: C.purpose, recipient: C.recipient, purpose: C.purpose, trust_level: C.trust_level, threat_model: "Outsider linking with public, social and leaked sources" };
  if (C.trust_level === "public") {
    const statistics = C.stats.map(st => st.filter(Boolean)).filter(st => st.length).map((st, i) => {
      const by = st.map(key => { const [table, column] = key.split("."); const c = det.find(d => d.table === table && d.column === column); return { table, column, detail: detailOptions(c, true)[0] || null }; });
      return { name: `table_${i + 1}_by_` + by.map(b => b.column.toLowerCase().replace(/[^a-z0-9]+/g, "_")).join("_"), table: by[0].table, by: by.map(({ column, detail }) => ({ column, detail })) };
    });
    if (!statistics.length) throw new Error("choose at least one column to count by");
    return { ...base, statistics, targets: { epsilon: +C.epsilon, rows_per_person: +C.rows_per_person } };
  }
  const needs = Object.entries(C.needs).map(([key, detail]) => { const [table, column] = key.split("."); return { table, column, detail: detail || null }; });
  if (!needs.length) throw new Error("tick at least one column the receiver needs");
  return { ...base, needs, targets: { k: +C.k } };
}

/* ---------------------------------------------------------------- start */
(async () => {
  const mask = $("#mask");
  mask.onchange = () => { S.mask = mask.checked; render(); };
  render();  // draw at once; reopening earlier work follows and may take a while on large data
  try {
    S.cat = await api("/api/catalogue");
    S.sessions = await api("/api/sessions");
  } catch (e) { toast(e.message, true); }
  render();
  let saved = ""; try { saved = localStorage.getItem("pets.session") || ""; } catch (e) { /* storage off */ }
  if (S.sessions.some(x => x.id === saved)) reopen(saved);
})();
