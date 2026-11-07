/* PETs Transformer web app. One state object, one render per step; every number comes from the local API. */
"use strict";

const S = {
  step: "data", cat: null, session: null, scan: null, plan: null, results: null, tradeoff: null, compare: null,
  table: null, textView: "after", receiverChoice: null, custom: null, busy: "",
};
const STEPS = [
  ["data", "Data"], ["scan", "Risk scan"], ["plan", "Receiver & plan"], ["approve", "Review & approve"], ["release", "Release & proof"],
];
const ROLE_LABEL = {
  direct_identifier: "identifies a person", quasi_identifier: "outsider may know it", sensitive_attribute: "sensitive fact",
  technical_identifier: "link / code", record_key: "row key", free_text: "free text", non_sensitive: "harmless",
};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = n => Number(n).toLocaleString("en-US");
const pct = (x, d = 0) => x == null ? "–" : (100 * x).toFixed(d) + "%";
const $ = sel => document.querySelector(sel);

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
  return { data: true, scan: d.data, plan: d.scan, approve: d.plan, release: d.approve }[step];
}
function render() {
  const done = stepsDone();
  $("#steps").innerHTML = STEPS.map(([k, label], i) =>
    `<button data-step="${k}" ${k === S.step ? 'aria-current="step"' : ""} class="${done[k] && k !== S.step ? "done" : ""}" ${canOpen(k) ? "" : "disabled"}>
      <span class="n">${done[k] && k !== S.step ? "✓" : i + 1}</span>${label}</button>`).join("");
  $("#page").innerHTML = VIEWS[S.step]();
  wire();
}
function go(step) { if (canOpen(step)) { S.step = step; render(); window.scrollTo(0, 0); } }
const busy = label => S.busy === label ? ` <span class="busy" aria-label="working"></span>` : "";

/* ---------------------------------------------------------------- 1 data */
function dataView() {
  const samples = S.cat?.samples || [];
  const loaded = S.session ? tablesPanel(S.session.tables) : "";
  return `<h1>Bring the data you want to share</h1>
  <p class="lede">Drop the tables as CSV files (or one ZIP). They are copied into a local folder on this computer and read here; nothing is uploaded to any server.</p>
  <div class="grid2">
    <div class="panel"><h2>Your files</h2>
      <label class="field">Dataset name<input type="text" id="dsname" value="my-data"></label>
      <div class="drop" id="drop" tabindex="0" role="button" aria-label="Choose CSV or ZIP files">
        <b>Drop CSV or ZIP files here</b><span class="small">or click to choose. One file per table; the file name becomes the table name.</span>
        <input type="file" id="files" accept=".csv,.zip" multiple hidden></div>${busy("upload")}</div>
    <div class="panel"><h2>Or try an example</h2><p class="small">Synthetic datasets from the TrustED challenge package.</p>
      <div class="cards">${samples.map(s => `<button class="choice" data-sample="${esc(s.name)}"><span class="k">${s.tables.length} tables</span><b>${esc(s.name.replace(/_/g, " "))}</b><span class="small">${esc(s.tables.join(", "))}</span></button>`).join("") || `<p class="small">No sample folder found (set PETS_PACKAGE_ROOT).</p>`}</div>${busy("sample")}</div>
  </div>${loaded}`;
}
function tablesPanel(tables) {
  const t = tables.find(x => x.name === S.table) || tables[0];
  return `<div class="panel"><div class="row" style="justify-content:space-between"><h2>${esc(S.session.name)}: ${tables.length} tables, ${fmt(tables.reduce((s, x) => s + x.rows, 0))} rows</h2>
    <button class="btn primary" data-go="scan">Scan for risks →</button></div>
    <div class="tabs">${tables.map(x => `<button data-table="${esc(x.name)}" aria-pressed="${x.name === t.name}">${esc(x.name)} · ${fmt(x.rows)}</button>`).join("")}</div>
    ${grid(t.preview, t.columns)}</div>`;
}
function grid(rows, columns, roleOf) {
  const cols = columns || Object.keys(rows[0] || {});
  return `<div class="tablewrap"><table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(r =>
    `<tr>${cols.map(c => `<td class="${roleOf ? "c-" + roleOf(c) : ""}">${esc(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

/* ---------------------------------------------------------------- 2 risk scan */
function scanView() {
  if (!S.scan) return `<h1>Risk scan</h1><p class="lede">Reading every column…${busy("scan")}</p>`;
  const R = S.scan.risk, det = S.scan.detections.columns;
  const worst = [...R.tables].sort((a, b) => b.unique_share - a.unique_share)[0];
  const outside = R.tables.flatMap(t => t.outside_links.map(c => `${t.table}.${c}`));
  const headline = worst && worst.unique_share > 0
    ? `In <b>${esc(worst.table)}</b>, <b>${pct(worst.unique_share)}</b> of ${fmt(worst.rows)} rows can be singled out by someone who knows ${esc(worst.quasi_identifiers.slice(0, 4).join(", "))}.`
    : "No table has quasi-identifiers that single people out.";
  return `<h1>What could go wrong if this data were shared as it is</h1>
  <div class="callout"><p>${headline} ${outside.length ? `<b>${outside.length}</b> columns can be matched with outside sources (${esc(outside.slice(0, 4).join(", "))}${outside.length > 4 ? "…" : ""}).` : ""}
    ${R.links.length ? `The tables connect through ${esc([...new Set(R.links.map(l => l.from_column))].join(", "))}, so one match unlocks everything linked to it.` : ""}</p></div>
  <div class="panel"><h2>How your data connects</h2>${connectionMap(R)}
    <div class="legend"><span><i style="background:var(--ink)"></i>tables joined by a shared key</span><span><i style="background:var(--risk)"></i>columns an outsider can match from public or leaked sources</span></div></div>
  <div class="cards">${R.tables.map(exposureCard).join("")}</div>
  ${personCard(R.person, det)}
  <div class="panel"><div class="row" style="justify-content:space-between"><h2>What each column is</h2><a class="btn" href="/api/sessions/${sid()}/download/detection.json">Download detection.json</a></div>
    <p class="small">Found from column names and values (ID-code checksums, IBAN and card check digits, phone formats, name shapes, dates, code sets). Wrong? Change it; the plan follows your correction.</p>
    ${detectionTable(det)}</div>
  <div class="row"><button class="btn primary" data-go="plan">Choose a receiver →</button></div>`;
}
function connectionMap(R) {
  const tables = R.tables.map(t => t.table), n = tables.length, cols = Math.min(n, 4);
  const W = 960, nodeW = 200, nodeH = 74, top = 120, gapY = 70, rows = Math.ceil(n / cols);
  const H = top + rows * (nodeH + gapY);
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
  return `<div class="panel ${t.unique_share >= 0.5 ? "risk" : ""}"><div class="row" style="justify-content:space-between"><h3>${esc(t.table)}</h3>${t.special_category ? `<span class="tag risk">special category (GDPR Art. 9)</span>` : ""}</div>
    <div><div class="row" style="justify-content:space-between"><span class="small">singled out on quasi-identifiers</span><b class="num">${pct(t.unique_share)}</b></div><div class="meter"><b style="width:${100 * t.unique_share}%"></b></div></div>
    ${t.direct_identifiers.length ? `<div class="small">Identifies a person: ${chips(t.direct_identifiers, "risk")}</div>` : ""}
    ${t.quasi_identifiers.length ? `<div class="small">An outsider may know: ${chips(t.quasi_identifiers, "warn")}</div>` : ""}
    ${t.sensitive.length ? `<div class="small">Sensitive: ${chips(t.sensitive, "safe")}</div>` : ""}
    ${t.free_text.length ? `<div class="small">Free text: ${chips(t.free_text, "risk")}</div>` : ""}</div>`;
}
function personCard(person, det) {
  const tables = Object.keys(person || {});
  if (!tables.length) return "";
  const role = (t, c) => (det.find(d => d.table === t && d.column === c) || {}).privacy_role || "";
  return `<div class="panel risk"><h2>What your files say about one person</h2>
    <p class="small">One person picked the way an attacker would: someone with several records. Everything below is linked through the keys above. Red identifies, amber is what an outsider may already know, blue is sensitive.</p>
    <div class="person">${tables.map(t => `<div><span class="eyebrow">${esc(t)} · ${person[t].length} record${person[t].length > 1 ? "s" : ""}</span>
      ${person[t].map(r => `<div class="record">${Object.entries(r).map(([k, v]) => `<span class="c-${role(t, k)}"><b>${esc(k)}</b>${esc(String(v).slice(0, 160))}</span>`).join("")}</div>`).join("")}</div>`).join("")}</div></div>`;
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
  return `<h1>Who gets the data, and for what?</h1>
  <p class="lede">The receiver decides the protection. A research group under contract can get coded rows; the public gets noisy statistics only. Pick one, or describe your own.</p>
  <div class="cards">${recv.map(r => `<button class="choice" data-receiver="${esc(r.id)}" aria-pressed="${S.receiverChoice === r.id}"><span class="k">${esc(r.trust_level.replace(/_/g, " "))} · ${r.kind === "statistics" ? "statistics only" : "rows"}</span><b>${esc(r.recipient)}</b><span class="small">${esc(r.purpose)}</span><span class="small mono">${esc(r.id)} · ${esc(r.dataset)} data</span></button>`).join("")}
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
function planPanel() {
  const P = S.plan.plan, det = S.scan.detections.columns;
  const role = (t, c) => (det.find(d => d.table === t && d.column === c) || {}).privacy_role || "";
  const rows = P.actions.map(a => `<tr class="${a.reason.startsWith("REVIEW") ? "review" : ""}"><td class="col">${esc(a.table)}.${esc(a.column)}</td><td class="c-${role(a.table, a.column)}">${ROLE_LABEL[role(a.table, a.column)] || ""}</td>
    <td>${techniqueSelect(a, det.find(d => d.table === a.table && d.column === a.column))}</td><td class="small">${esc(a.reason)}</td></tr>`).join("");
  const stats = P.aggregates.length ? `<div class="panel"><h3>Published statistics · ε ${P.epsilon} per release, ${P.differential_privacy.max_rows_per_unit} records per person, one person = one ${esc(P.differential_privacy.unit)}</h3>
    <div class="stack">${P.aggregates.map((a, i) => `<div style="flex:${a.epsilon};background:${i % 2 ? "var(--ink)" : "var(--safe)"}" title="${esc(a.name)}">${a.epsilon}</div>`).join("")}</div>
    <div class="tablewrap"><table><thead><tr><th>Table</th><th>Counted by</th><th>ε</th><th>Why</th></tr></thead><tbody>${P.aggregates.map(a => `<tr><td class="col">${esc(a.name)}</td><td>${a.dimensions.map(d => esc(d.name || d.column)).join(" × ")}</td><td class="num">${a.epsilon}</td><td class="small">${esc(a.reason)}</td></tr>`).join("")}</tbody></table></div></div>` : "";
  const qis = Object.entries(P.quasi_identifiers);
  return `<div class="panel safe"><div class="row" style="justify-content:space-between"><h2>The plan for ${esc(S.plan.scenario?.recipient || P.scenario_id)}</h2>
      <div class="row"><a class="btn" href="/api/sessions/${sid()}/download/plan.yaml">Download plan.yaml</a><button class="btn primary" data-go="approve">Review & approve →</button></div></div>
    ${S.plan.reviews.length ? `<div class="callout warn">Needs a person's decision: ${esc(S.plan.reviews.join(", "))}</div>` : ""}
    ${S.plan.withheld_tables.length ? `<p class="small">Tables that stay here entirely: ${esc(S.plan.withheld_tables.join(", "))}.</p>` : ""}
    ${qis.length ? `<p class="small">Checked together so that every row has at least <b>${P.k_target - 1}</b> look-alikes: ${qis.map(([t, q]) => `${esc(t)} (${esc(q.join(", "))})`).join("; ")}.</p>` : ""}
    ${rows ? `<div class="tablewrap"><table><thead><tr><th>Column</th><th>What it is</th><th>Protection</th><th>Why</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="small">No rows are released.</p>`}</div>
  ${stats}
  <div class="grid2">${tradeoffPanel()}${comparePanel()}</div>`;
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
    return `<polyline class="l${cls}" points="${pts.map(p => p.join(",")).join(" ")}"/>${pts.map(p => `<circle class="p${cls}" cx="${p[0]}" cy="${p[1]}" r="4"/>`).join("")}`;
  }).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Trade-off chart">${ticks}${now >= 0 ? `<line class="now" x1="${x(now)}" x2="${x(now)}" y1="${T}" y2="${H - B}"/>` : ""}${lines}${xs}<text x="${(W + L) / 2}" y="${H - 2}" text-anchor="middle">${xLabel}</text></svg>`;
}
function tradeoffPanel() {
  const T = S.tradeoff;
  if (!T) return `<div class="panel"><h3>Privacy versus usefulness</h3><p class="small">See how the result moves before you choose.</p><button class="btn" data-tradeoff>Show the trade-off</button>${busy("tradeoff")}</div>`;
  const k = T.k.length ? `<div class="legend"><span><i style="background:var(--risk)"></i>attacker's chance to pick the right person</span><span><i style="background:var(--safe)"></i>values kept</span></div>
    ${lineChart(T.k, "k", [["guess_chance", 1], ["cells_kept", 2]], "k: each person looks like at least k-1 others")}
    <div class="row"><span class="small">Use k =</span>${T.k.map(p => `<button class="btn" data-setk="${p.k}" ${p.current ? "disabled" : ""}>${p.k}</button>`).join("")}</div>` : "";
  const e = T.epsilon.length ? `<div class="legend"><span><i style="background:var(--risk)"></i>average error of published numbers</span></div>
    ${lineChart(T.epsilon, "epsilon", [["mean_error", 1]], "ε per release: more budget, less noise, more privacy loss")}` : "";
  return `<div class="panel"><h3>Privacy versus usefulness</h3>${k}${e}<p class="small">Computed on your data without releasing anything. The dashed line is the current plan.</p></div>`;
}
function comparePanel() {
  const C = S.compare;
  if (!C) return `<div class="panel"><h3>Same data, other receivers</h3><p class="small">Compare what each receiver would get.</p><button class="btn" data-compare>Compare receivers</button>${busy("compare")}</div>`;
  const ids = C.receivers.map(r => r.id);
  const rows = C.rows.filter(r => ids.some(i => r[i] !== "withheld"));
  return `<div class="panel"><h3>Same data, other receivers</h3><div class="tablewrap"><table><thead><tr><th>Column</th>${C.receivers.map(r => `<th>${esc(r.recipient)}</th>`).join("")}</tr></thead><tbody>
    ${rows.map(r => `<tr><td class="col">${esc(r.table)}.${esc(r.column)}</td>${ids.map(i => `<td><span class="tech ${r[i]}">${esc(r[i])}</span></td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`;
}

/* ---------------------------------------------------------------- 4 approve */
function approveView() {
  const P = S.plan.plan, rev = S.plan.reviews;
  const counts = {};
  P.actions.forEach(a => (counts[a.technique] = (counts[a.technique] || 0) + 1));
  return `<h1>Review and approve</h1><p class="lede">Nothing leaves until a named person approves the plan. The approval is written into the plan and into every release manifest.</p>
  <div class="grid3">
    <div class="panel"><span class="eyebrow">Receiver</span><b>${esc(S.plan.scenario?.recipient || P.scenario_id)}</b><span class="small">${esc(S.plan.scenario?.purpose || "")}</span></div>
    <div class="panel"><span class="eyebrow">Columns</span><div class="row">${Object.entries(counts).map(([t, n]) => `<span class="tech ${t}">${n} ${t}</span>`).join("")}</div>${P.aggregates.length ? `<span class="small">${P.aggregates.length} statistics tables, ε ${P.epsilon}</span>` : ""}</div>
    <div class="panel ${rev.length ? "risk" : "safe"}"><span class="eyebrow">Open questions</span><b>${rev.length ? rev.length + " to check" : "none"}</b><span class="small">${esc(rev.join(", "))}</span></div></div>
  <div class="panel">${P.approved ? `<div class="callout safe">Approved by <b>${esc(P.approved_by)}</b>.</div>` : ""}
    <div class="row"><label class="field">Approved by<input type="text" id="approver" value="${esc(P.approved_by || "")}" placeholder="Your name"></label>
    ${rev.length ? `<label class="row small"><input type="checkbox" id="confirmrev"> I checked the open questions</label>` : ""}
    <button class="btn primary" data-approve>${P.approved ? "Approve again" : "Approve the plan"}</button>${busy("approve")}</div></div>
  ${P.approved ? `<div class="row"><button class="btn primary" data-go="release">Create the release →</button></div>` : ""}`;
}

/* ---------------------------------------------------------------- 5 release & proof */
function releaseView() {
  const R = S.results;
  const head = `<h1>Release and proof</h1><div class="panel"><div class="row"><label class="field">Receiver name (selects their own key)<input type="text" id="receiver" value="${esc(S.lastReceiver || "receiver")}"></label>
    <button class="btn primary" data-run>${R ? "Create again" : "Create the release"}</button>${busy("run")}</div>
    <p class="small">Each receiver gets codes from a different key, so two receivers cannot join their copies.</p></div>`;
  if (!R) return head;
  const dl = `<div class="panel safe"><h2>Download</h2><div class="row">
      <a class="btn safe" href="/api/sessions/${sid()}/download/release.zip" data-download>Release (.zip): ${R.files.map(f => esc(f.name)).join(", ")} + manifest</a>
      <a class="btn" href="/api/sessions/${sid()}/download/plan.yaml">Approved plan</a></div>
    <p class="small">The zip holds only what may be shared. Row maps stay in the private folder on this computer. ${R.epsilon != null ? `Downloading publishes the statistics and records ε ${R.epsilon} in the privacy budget ledger${R.published ? " (already recorded)" : ""}.` : ""}</p></div>`;
  return `${head}${R.attacker.map(attackerPanel).join("")}${R.tables.map(tableResult).join("")}${R.text.map(textPanel).join("")}${statsResult(R)}
    <div class="panel"><h2>Remaining risks, as written in the manifest</h2><ul class="plain">${R.residual_risks.map(r => `<li>${esc(r)}</li>`).join("")}</ul></div>${dl}`;
}
function bucketBar(b, cls) {
  const colors = { alone: "var(--risk)", "2-4": "var(--warn)", "5-9": "var(--safe)", "10-49": "var(--safe)", "50+": "var(--ink)" };
  return `<div class="stack" aria-label="${cls}">${Object.entries(b).filter(([, v]) => v > 0).map(([k, v]) => `<div style="flex:${v};background:${colors[k]}" title="${k}: ${pct(v, 1)}">${v > 0.08 ? `${k} ${pct(v)}` : ""}</div>`).join("")}</div>`;
}
function attackerPanel(v) {
  return `<div class="panel"><h2>The attacker's view: ${esc(v.table)}</h2>
    <p class="small">Someone who knows a person's ${esc(v.known.join(", "))} looks for them in the data. How many people look the same?</p>
    <div class="grid2"><div class="panel risk"><span class="eyebrow">Before</span><div class="big risk num">${pct(v.before.unique_share)}</div><span class="small">of ${fmt(v.before.rows)} rows have no look-alike: found with certainty</span>${bucketBar(v.before.buckets, "before")}</div>
      <div class="panel safe"><span class="eyebrow">After</span><div class="big safe num">${pct(v.after.unique_share)}</div><span class="small">have no look-alike; an attacker's chance to pick the right person is ${pct(v.after.guess_chance, 1)}</span>${bucketBar(v.after.buckets, "after")}</div></div>
    <div class="legend"><span><i style="background:var(--risk)"></i>alone</span><span><i style="background:var(--warn)"></i>2–4 look-alikes</span><span><i style="background:var(--safe)"></i>5–49</span><span><i style="background:var(--ink)"></i>50 or more</span></div></div>`;
}
function tableResult(t) {
  const ch = t.changes;
  return `<div class="panel"><div class="row" style="justify-content:space-between"><h2>${esc(t.name)}: ${fmt(t.rows_in)} rows in, ${fmt(t.rows_out)} out</h2>
    ${t.suppression ? `<span class="small">${fmt(t.suppression.rows_removed)} rows removed, ${fmt(Object.values(t.suppression.cells_blanked).reduce((s, x) => s + x, 0))} values blanked to reach k</span>` : ""}</div>
    <div class="grid2"><div><span class="eyebrow">Raw (stays here)</span>${grid(t.raw_preview)}</div><div><span class="eyebrow">Released</span>${grid(t.preview)}</div></div>
    <div class="tablewrap"><table><thead><tr><th>Column</th><th>Protection</th><th>Values</th><th>Distinct</th><th>Released values</th></tr></thead><tbody>${ch.map(c => `<tr>
      <td class="col">${esc(c.column)}${c.released_as && c.released_as !== c.column ? ` → ${esc(c.released_as)}` : ""}</td><td><span class="tech ${c.technique}">${esc(c.technique)}</span></td>
      <td class="num">${fmt(c.filled_before)} → ${fmt(c.filled_after)}</td><td class="num">${fmt(c.distinct_before)} → ${fmt(c.distinct_after)}</td>
      <td>${c.top_after.slice(0, 6).map(([v, s]) => `<div class="hbar"><span class="mono">${esc(v)}</span><div class="meter safe"><b style="width:${100 * s}%"></b></div><span>${pct(s)}</span></div>`).join("")}</td></tr>`).join("")}</tbody></table></div></div>`;
}
function textPanel(t) {
  const after = S.textView === "after";
  return `<div class="panel"><div class="row" style="justify-content:space-between"><h2>Free text: ${esc(t.column)}</h2>
    <div class="tabs"><button data-textview="before" aria-pressed="${!after}">Found</button><button data-textview="after" aria-pressed="${after}">Released</button></div></div>
    <div class="grid2">${t.samples.map(parts => `<div class="sample">${parts.map(p => !p.label ? esc(p.t) : after ? `<span class="tagged">[${esc(p.label)}]</span>` : `<mark title="${esc(p.label)}">${esc(p.t)}</mark>`).join("")}</div>`).join("")}</div></div>`;
}
function statsResult(R) {
  if (!R.statistics.length) return "";
  const acc = Object.fromEntries(R.accuracy.map(a => [a.name, a]));
  return `<div class="panel"><h2>Published statistics: how accurate are they?</h2><p class="small">Noisy published numbers against the exact numbers (cells with at least 10 records). The exact numbers never leave.</p>
    ${R.statistics.map(s => { const a = acc[s.name] || {}; return `<div class="hbar"><span class="mono">${esc(s.name)}</span><div class="meter safe"><b style="width:${100 * (a.within_10pct || 0)}%"></b></div><span>${pct(a.within_10pct)}</span></div>`; }).join("")}
    <p class="small">Bar: share of cells within 10% of the true value. ε ${R.epsilon} spent in this release.</p>
    <div class="grid2">${R.statistics.slice(0, 2).map(s => `<div><span class="eyebrow">${esc(s.name)} · ${fmt(s.cells)} cells</span>${grid(s.preview)}</div>`).join("")}</div></div>`;
}

const VIEWS = { data: dataView, scan: scanView, plan: planView, approve: approveView, release: releaseView };

/* ---------------------------------------------------------------- events */
function wire() {
  const page = $("#page");
  document.querySelectorAll("[data-step]").forEach(b => (b.onclick = () => go(b.dataset.step)));
  page.querySelectorAll("[data-go]").forEach(b => (b.onclick = () => { go(b.dataset.go); if (b.dataset.go === "scan" && !S.scan) runScan(); }));
  page.querySelectorAll("[data-table]").forEach(b => (b.onclick = () => { S.table = b.dataset.table; render(); }));
  page.querySelectorAll("[data-sample]").forEach(b => (b.onclick = () => act("sample", async () => openSession(await api("/api/sessions/sample", { body: { name: b.dataset.sample } })))));
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
    S.plan = await api(`/api/sessions/${sid()}/plan`, { body: { custom: customScenario() } }); S.results = null; S.tradeoff = null; S.compare = null;
  })));
  page.querySelectorAll("[data-action]").forEach(sel => (sel.onchange = () => {
    const [table, column] = sel.dataset.action.split("|"), opt = sel.selectedOptions[0];
    const body = { table, column, technique: opt.value.split(":")[0], params: JSON.parse(opt.dataset.params || "{}") };
    act("plan", async () => { S.plan = await api(`/api/sessions/${sid()}/plan/action`, { body }); S.results = null; S.tradeoff = null; });
  }));
  page.querySelectorAll("[data-tradeoff]").forEach(b => (b.onclick = () => act("tradeoff", async () => { S.tradeoff = await api(`/api/sessions/${sid()}/tradeoff`); })));
  page.querySelectorAll("[data-setk]").forEach(b => (b.onclick = () => act("tradeoff", async () => {
    S.plan = await api(`/api/sessions/${sid()}/plan/k`, { body: { k: +b.dataset.setk } }); S.results = null;
    S.tradeoff = await api(`/api/sessions/${sid()}/tradeoff`);
  })));
  page.querySelectorAll("[data-compare]").forEach(b => (b.onclick = () => act("compare", async () => {
    S.compare = await api(`/api/sessions/${sid()}/compare`, { body: { scenario_ids: S.cat.receivers.map(r => r.id) } });
  })));
  page.querySelectorAll("[data-approve]").forEach(b => (b.onclick = () => act("approve", async () => {
    S.plan = await api(`/api/sessions/${sid()}/approve`, { body: { by: $("#approver").value, confirm_review: !!$("#confirmrev")?.checked } });
    toast(`Approved by ${S.plan.plan.approved_by}.`);
  })));
  page.querySelectorAll("[data-run]").forEach(b => (b.onclick = () => act("run", async () => {
    S.lastReceiver = $("#receiver").value;
    S.results = await api(`/api/sessions/${sid()}/run`, { body: { receiver: S.lastReceiver } });
    toast(`Release ${S.results.release_id} created.`);
  })));
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
async function upload(files) {
  if (!files?.length) return;
  const form = new FormData();
  [...files].forEach(f => form.append("files", f));
  form.append("name", $("#dsname").value || "my-data");
  await act("upload", async () => openSession(await api("/api/sessions/upload", { form })));
}
function openSession(s) {
  Object.assign(S, { session: s, scan: null, plan: null, results: null, tradeoff: null, compare: null, table: null, receiverChoice: null, custom: null });
  remember(); toast(`Loaded ${s.tables.length} tables.`);
}
function runScan() { act("scan", async () => { S.scan = await api(`/api/sessions/${sid()}/scan`, { method: "POST" }); }); }
function makePlan(body) {
  act("plan", async () => {
    S.plan = await api(`/api/sessions/${sid()}/plan`, { body }); S.results = null; S.tradeoff = null; S.compare = null;
  });
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
  try {
    S.cat = await api("/api/catalogue");
    let saved = ""; try { saved = localStorage.getItem("pets.session") || ""; } catch (e) { /* storage off */ }
    if (saved) { try { S.session = await api(`/api/sessions/${saved}`); } catch (e) { remember(); } }
  } catch (e) { toast(e.message, true); }
  render();
})();
