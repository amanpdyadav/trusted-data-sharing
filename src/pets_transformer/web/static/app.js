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
  $("#topbar").innerHTML = topBar();
  $("#page").innerHTML = VIEWS[S.step]();
  renderModal();
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
const head = (n, title, lede) => `<div class="head"><h1>${title}</h1>${lede ? `<p class="lede">${lede}</p>` : ""}</div>`;  // the step number is in the top bar
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
  const steps = guide(["Upload your files or pick an example", "Look at what is inside", "Scan for risks"], [!!S.session, !!S.session, !!S.scan]);
  if (S.session) return `${steps}${readyPanel()}${tablesPanel(S.session.tables)}
    <details class="switcher" ${S.switchOpen ? "open" : ""}><summary><span>Load different data or reopen earlier work</span><span class="small">${plural(S.sessions.length, "dataset")} in your workspace</span></summary>
      <div class="page">${loaders()}${workspacePanel()}</div></details>`;
  return `${head(1, "Bring the data you want to share", "Drop the tables as CSV files (or one ZIP), pick an example, or reopen earlier work. Files are copied into a local folder on this computer; nothing is uploaded anywhere.")}
    ${steps}${loaders()}${workspacePanel()}`;
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
  const frozen = S.session.released;
  return `<div class="panel ready"><div class="spread"><div class="head"><span class="eyebrow">${frozen ? "🔒 Released · data frozen" : "Dataset ready"}</span>
        <div class="row"><h1>${esc(S.session.name)}</h1><button class="btn small" data-modal="rename">✎ Rename</button><button class="btn small" data-modal="duplicate">⧉ Duplicate</button></div></div>
      <button class="btn primary lg" data-go="scan">${S.scan ? "See the risk scan →" : "Scan for risks →"}</button></div>
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
/* the step and its main action, pinned to the top of the screen on every step */
function topBar() {
  const n = STEPS.findIndex(([k]) => k === S.step), label = `Step ${n + 1} of 5 · ${STEPS[n][1]}`;
  const bar = (info, action = "") => `<div class="topbar-in"><div class="tb-text"><span class="eyebrow">${label}</span><span class="small">${info}</span></div><div class="row">${action}</div></div>`;
  const btn = (attrs, text, cls = "primary") => `<button class="btn ${cls}" ${attrs}>${text}</button>`;
  if (S.progress) return bar(`${esc(S.progress.title)}… <span class="busy"></span>`);
  if (S.busy && S.busy !== "tradeoff") return bar(`Working… <span class="busy"></span>`);
  const recipient = S.plan ? esc(S.plan.scenario?.recipient || S.plan.plan.scenario_id) : "";
  switch (S.step) {
    case "data": return S.session ? bar(`<b>${esc(S.session.name)}</b> · ${plural(S.session.tables.length, "table")} loaded`, btn("data-go=scan", "Scan for risks →"))
      : bar("Drop your tables, pick an example, or reopen earlier work.", btn("data-pick-files", "Choose files…"));
    case "scan": { if (!S.scan) return bar("Not scanned yet.", btn("data-scan", "Scan for risks"));
      const w = worstTable(); return bar(`${pct(w.unique_share)} of <b>${esc(w.table)}</b> can be singled out today`, btn("data-go=plan", "Choose a receiver →")); }
    case "plan": return S.plan ? bar(`Plan for <b>${recipient}</b>${S.plan.reviews.length ? ` · ${plural(S.plan.reviews.length, "item")} to check` : ""}`, btn("data-go=approve", "Review & approve →"))
      : bar("Pick who receives the data.", btn('data-receiver="custom"', "Describe your own…", ""));
    case "approve": return S.plan.plan.approved ? bar(`Approved by <b>${esc(S.plan.plan.approved_by)}</b>`, btn("data-go=release", "Create the release →"))
      : bar(`Plan for <b>${recipient}</b> waits for a named approval`, btn('data-focus="signoff"', "Sign off ↓"));
    case "release": return S.results ? bar(`<b>${esc(S.results.release_id)}</b> · ${plural(S.results.files.length, "file")} + manifest`,
      `${S.plan?.plan.approved && !S.viewing ? btn('data-modal="release"', "New release…", "") : ""}<a class="btn safe" href="/api/sessions/${sid()}/releases/${encodeURIComponent(S.results.release_id)}/release.zip" data-download>Download<span class="long"> release (.zip)</span></a>`)
      : bar(`Approved by <b>${esc(S.plan.plan.approved_by)}</b> · nothing released yet`, btn('data-modal="release"', "Create the release…"));
  }
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
        <div class="row wsactions"><button class="btn small ${S.session?.id === x.id ? "" : "primary"}" data-open="${esc(x.id)}">${S.session?.id === x.id ? "Open ✓" : "Open"}</button>
          <button class="btn small" data-modal-for="duplicate|${esc(x.id)}" title="Start again with the same tables">⧉ Duplicate</button>
          <button class="btn small" data-modal-for="rename|${esc(x.id)}">✎ Rename</button>
          <button class="btn small danger" data-delete-ds="${esc(x.id)}" ${x.released ? `disabled title="Released datasets stay as the record of their releases"` : ""}>🗑 Delete</button></div></div>`;
    }).join("")}</div></div>`;
}
function tablesPanel(tables) {
  const t = tables.find(x => x.name === S.table) || tables[0];
  const frozen = S.session.released, removable = !frozen && tables.length > 1;
  return `<div class="panel"><div class="spread"><div><h2>What is inside</h2><span class="small">${plural(tables.length, "table")} · first rows of each${S.mask && !S.scan ? " · text hidden until the scan knows which columns are personal" : ""}</span></div>
      ${frozen ? "" : `<button class="btn" data-add-tables>＋ Add tables</button><input type="file" id="addfiles" accept=".csv,.zip" multiple hidden>`}</div>
    ${frozen ? `<div class="callout safe">🔒 This dataset has releases, so its tables are frozen: each release must stay traceable to exactly this data. To change the tables, <button class="btn small" data-modal="duplicate">⧉ Duplicate it</button> and edit the copy.</div>` : ""}
    <div class="pills tablepills">${tables.map(x => `<span class="tpill ${x.name === t.name ? "on" : ""}"><button data-table="${esc(x.name)}" aria-pressed="${x.name === t.name}">${esc(x.name)} · ${fmt(x.rows)}</button>${removable ? `<button class="x" data-remove-table="${esc(x.name)}" aria-label="Remove ${esc(x.name)}" title="Remove this table">✕</button>` : ""}</span>`).join("")}</div>
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
  ${guide(["See how one person is found", "Follow the trail to see what leaks", "Fix any column labelled wrong, then choose a receiver"], [true, true, false])}
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
      <div class="row"><button class="btn" data-another>🎲 Another person</button><button class="btn risk" data-play="scan">▶ Play the attack</button>${busy("another")}</div></div>
    <div class="chain">
      <div class="stage"><span class="sn">The outsider knows</span>${factList(A.known, A.table)}<span class="small">from a public register, social media or a leaked list</span></div>
      <div class="stage ${hit ? "hit" : ""}"><span class="sn">Searches ${esc(A.table)}</span><span class="big">${hit ? "1 person" : plural(A.matches, "person").replace("persons", "people")}</span><span class="small">of ${fmt(A.rows)} records fit all ${Object.keys(A.known).length} facts</span></div>
      <div class="stage ${hit ? "hit" : ""}"><span class="sn">Learns who it is</span>${Object.keys(A.revealed).length ? factList(A.revealed, A.table, "risk") : `<span class="small">No single person: the facts fit ${fmt(A.matches)} people.</span>`}</div>
      <div class="stage ${hit && total ? "hit" : ""}"><span class="sn">Unlocks through keys</span>${hit ? `<span class="big">${fmt(total)}</span><span class="small">records about this person</span>${linked.map(([t, n]) => `<div class="fact"><span>${esc(t)}</span><b>${fmt(n)}</b></div>`).join("")}` : `<span class="small">Nothing certain to unlock.</span>`}</div>
    </div>
    ${hit ? `<div class="verdict risk"><span class="badge">Re-identified</span><span>${Object.keys(A.known).length} everyday facts are enough to name this person and open ${plural(total, "record")} across ${plural(linked.length, "table")}. This is the mosaic effect, and it is why the data cannot be shared as it is.</span></div>`
      : `<div class="verdict safe"><span class="badge">Not singled out</span><span>On these facts the person hides among ${fmt(A.matches)} people. Other columns may still expose them; see the tables below.</span></div>`}
    ${trailView(S.scan.attack)}
  </div>`;
}
/* the mosaic effect step by step: from the outsider's facts through each table, and what each one gives away */
function trailView(A) {
  const trail = A?.trail || [];
  if (!trail.length || A.before.outcome !== "identified") return "";
  const arrow = (label, sub) => `<div class="tarrow"><span class="mono">${esc(label)}</span><i aria-hidden="true"></i><span class="small">${esc(sub)}</span></div>`;
  const node = h => `<div class="tnode"><div class="spread"><b class="mono">${esc(h.table)}</b><span class="tag risk">${plural(h.rows, "record")}</span></div>
    ${Object.entries(h.learnt).map(([k, v]) => { const [, vals, more = ""] = v.match(/^(.*?)( \+\d+ more)?$/s);
      return `<div class="tl"><span>${esc(k)}</span><b class="c-${roleOf(h.table, k)}">${esc(shown(h.table, k, vals))}${esc(more)}</b></div>`; }).join("") || `<span class="small">nothing telling beyond the link</span>`}</div>`;
  return `<div class="trailwrap"><div class="spread"><h3>Follow the trail: what each table gives away</h3><span class="small">${plural(trail.length, "table")} · ${fmt(trail.reduce((n, h) => n + h.rows, 0))} records about one person</span></div>
    <div class="trail"><div class="tnode start"><b>The outsider</b>${factList(A.before.known, A.before.table)}</div>
      ${trail.map((h, i) => `${i === 0 ? arrow("search", "1 person fits") : arrow(`via ${h.via}`, `from ${h.from_table}`)}${node(h)}`).join("")}</div>
    <p class="small">Red identifies the person, blue is sensitive. Each arrow is a key shared by two tables: knowing one row opens the next table.</p></div>`;
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
    ${tables.map((t, ti) => acc(`pf:${t}`, `<b class="mono">${esc(t)}</b>`, `<span class="small">${plural(person[t].length, "record")}</span>`,
      person[t].map(r => `<div class="record">${Object.entries(r).map(([k, v]) => `<span class="c-${roleOf(t, k)}"><b>${esc(k)}</b>${esc(shown(t, k, String(v).slice(0, 160)))}</span>`).join("")}</div>`).join(""), ti === 0)).join("")}`;
}
function detectionTable(det) {
  const tables = [...new Set(det.map(c => c.table))];
  return `${tables.length > 1 ? `<div class="spread"><span></span>${accTools(tables.map(t => "dc:" + t))}</div>` : ""}` + tables.map((t, ti) => {
    const cols = det.map((c, i) => [c, i]).filter(([c]) => c.table === t);
    const ident = cols.filter(([c]) => c.privacy_role === "direct_identifier").length, qi = cols.filter(([c]) => c.privacy_role === "quasi_identifier").length;
    return acc(`dc:${t}`, `<b class="mono">${esc(t)}</b>`, `<span class="small">${plural(cols.length, "column")}${ident ? ` · <span class="c-direct_identifier">${ident} identify a person</span>` : ""}${qi ? ` · <span class="c-quasi_identifier">${qi} outsider may know</span>` : ""}</span>`,
      `<div class="tablewrap"><table><thead><tr><th>Column</th><th>What it is</th><th>Type</th><th>How sure</th><th></th></tr></thead><tbody>${cols.map(([c, i]) => `<tr class="clickable" data-col="${i}">
      <td class="col">${esc(c.column)}</td><td class="c-${c.privacy_role}">${ROLE_LABEL[c.privacy_role] || c.privacy_role}${c.evidence.some(e => e.kind === "manual") ? ` <span class="tag ok">corrected</span>` : ""}</td>
      <td class="mono small">${esc(c.subtype)}</td><td><div class="meter safe" style="width:80px"><b style="width:${100 * c.confidence}%"></b></div></td>
      <td><button class="btn small" data-col="${i}">Details</button></td></tr>`).join("")}</tbody></table></div>`, ti === 0);
  }).join("");
}

/* ---------------------------------------------------------------- 3 receiver & plan */
const TIME_UNITS = ["week", "month", "day", "hour", "time_of_day"];
function detailOptions(c, forStatistics) {
  if (["TIMESTAMP", "DATE"].includes(c.subtype)) return TIME_UNITS;
  if (c.subtype === "BIRTH_DATE") return ["age_band"];
  if (forStatistics && c.subtype === "DIAGNOSIS_CODE" && S.cat.codelists.includes("diagnosis_group")) return ["diagnosis_group"];
  return [""];
}
/* plain words for each protection, used on the board, in dialogs and on the approve page */
const LANES = [
  ["keep", "✓", "Shared as is", "The receiver sees the real value."],
  ["generalise", "🔍", "Made less exact", "Rounded or grouped: a birth date becomes an age group, a time becomes an hour."],
  ["pseudonymise", "🔒", "Replaced by a code", "The same person always gets the same code; the real value stays here."],
  ["redact_text", "📝", "Personal details hidden", "Names, numbers and addresses inside the text are blacked out."],
  ["drop", "✂", "Removed", "Not shared at all."],
];
const LANE_SHOWN = 6;  // chips per lane before "+N more"
const laneOf = technique => LANES.find(l => l[0] === technique) || LANES[0];
const RECEIVER_ICON = { public: "🌍", controlled_research: "🎓", contractual: "🤝", internal: "🏢" };
/* a collapsible section that remembers whether the user opened or closed it */
function acc(key, title, right, body, open = false, cls = "") {
  const isOpen = S.accOpen?.[key] ?? open;
  return `<details class="acc ${cls}" data-acc="${esc(key)}" ${isOpen ? "open" : ""}><summary><span class="acc-title">${title}</span><span class="acc-right">${right}</span></summary><div class="acc-body">${body}</div></details>`;
}
const accTools = keys => `<span class="small"><button class="linkbtn" data-acc-all="${esc(keys.join("|"))}">Expand all</button> · <button class="linkbtn" data-acc-none="${esc(keys.join("|"))}">Collapse all</button></span>`;
function guide(steps, done) {
  const cur = steps.findIndex((_, i) => !done[i]);
  return `<ol class="guide">${steps.map((t, i) => `<li class="${done[i] ? "done" : i === cur ? "now" : ""}"><span>${done[i] ? "✓" : i + 1}</span>${t}</li>`).join("")}</ol>`;
}
function planView() {
  const recv = S.cat.receivers, P = S.plan;
  return `${head(3, "Who gets the data, and what will they see?", "Pick the receiver. The tool decides how each column is shared and shows you the result before anything leaves.")}
  ${guide(["Pick who gets the data", "Check what they will receive", "Change anything that looks wrong, then continue"], [!!P, !!P, false])}
  <div class="cards receivers">${recv.map(r => `<button class="choice" data-receiver="${esc(r.id)}" aria-pressed="${S.receiverChoice === r.id}">
      <span class="ricon" aria-hidden="true">${RECEIVER_ICON[r.trust_level] || "📦"}</span><b>${esc(r.recipient)}</b><span class="small">${esc(r.purpose)}</span>
      <span class="gets ${r.kind === "statistics" ? "stats" : ""}">${r.kind === "statistics" ? "Gets only counts, with a little noise" : "Gets individual records, protected"}</span></button>`).join("")}
    <button class="choice" data-receiver="custom" aria-pressed="${S.receiverChoice === "custom"}"><span class="ricon" aria-hidden="true">✏️</span><b>Someone else</b><span class="small">Describe who they are and tick what they need.</span><span class="gets">You choose the columns</span></button></div>
  ${busy("plan")}
  ${P ? planPanel() : ""}`;
}
function planPanel() {
  const P = S.plan.plan;
  return `${P.actions.length ? board(P) : ""}${P.aggregates.length ? statsBoard(P) : ""}
    ${P.actions.length ? exampleRecord() : ""}
    ${protectionLevel(P)}
    <details class="more"><summary>Compare with other receivers, or download the plan file</summary>
      <div class="row"><a class="btn small" href="/api/sessions/${sid()}/download/plan.yaml">Download plan.yaml</a></div>${comparePanel()}</details>`;
}
function board(P) {
  const reviews = new Set(S.plan.reviews);
  return `<div class="panel"><div class="spread"><div><span class="eyebrow">What ${esc(S.plan.scenario?.recipient || P.scenario_id)} will receive</span><h2>How each column is shared</h2></div>
      <div class="legend">${LANES.map(l => `<span>${l[1]} ${l[2]}</span>`).join("")}</div></div>
    ${S.plan.reviews.length ? `<div class="callout warn">⚠ <b>${plural(S.plan.reviews.length, "column")} need${S.plan.reviews.length === 1 ? "s" : ""} a person's decision</b>: click ${S.plan.reviews.length === 1 ? "it" : "them"} below and choose.</div>` : ""}
    ${planTables(P).length > 1 ? `<div class="spread"><span></span>${accTools(planTables(P).map(t => "pb:" + t))}</div>` : ""}
    ${planTables(P).map((t, ti) => {
      const acts = P.actions.filter(a => a.table === t), shared = acts.filter(a => a.technique !== "drop").length;
      const flagged = acts.some(a => reviews.has(`${a.table}.${a.column}`));
      return acc(`pb:${t}`, `<b class="mono">${esc(t)}</b>${flagged ? ` <span class="tag warn">⚠ needs a decision</span>` : ""}`, `<span class="small">${shared} of ${acts.length} columns shared</span>`, `
        <div class="lanes">${LANES.map(([tech, icon, name]) => {
          const inLane = acts.filter(a => a.technique === tech);
          return `<div class="lane l-${tech}"><div class="lhead"><span>${icon}</span>${name}<b>${inLane.length}</b></div>
            ${(S.openLanes?.[t + tech] ? inLane : inLane.slice(0, LANE_SHOWN)).map(a => `<button class="chip ${reviews.has(`${a.table}.${a.column}`) ? "review" : ""}" data-change="${esc(a.table)}|${esc(a.column)}" title="${esc(a.reason)}">${reviews.has(`${a.table}.${a.column}`) ? "⚠ " : ""}${esc(a.column)}</button>`).join("") || `<span class="small">none</span>`}
            ${inLane.length > LANE_SHOWN && !S.openLanes?.[t + tech] ? `<button class="chip more" data-lane="${esc(t + tech)}">+${inLane.length - LANE_SHOWN} more</button>` : ""}</div>`;
        }).join("")}</div>`, ti < 3 || flagged, "btable");
    }).join("")}
    ${S.plan.withheld_tables.length ? `<p class="small">Not shared at all: ${esc(S.plan.withheld_tables.join(", "))}.</p>` : ""}
    <p class="small">Click any column to see why, and to change how it is shared.</p></div>`;
}
function statsBoard(P) {
  return `<div class="panel"><span class="eyebrow">What ${esc(S.plan.scenario?.recipient || P.scenario_id)} will receive</span><h2>Only counts, never individual records</h2>
    <div class="cards">${P.aggregates.map(a => `<div class="panel flat"><span class="ricon" aria-hidden="true">📊</span><b>${esc(a.name.replace(/_/g, " "))}</b>
      <span class="small">Counted by ${a.dimensions.map(d => esc((d.name || d.column).replace(/_/g, " "))).join(" and ")}</span></div>`).join("")}</div>
    <p class="small">A little random noise is added to every number, so nobody can tell whether one particular person is in the data. Each person is counted at most ${P.differential_privacy.max_rows_per_unit} times.</p></div>`;
}
/* the attacked person's record (or the first rows), now and as the receiver will get it */
function exampleRecord() {
  const E = S.example;
  if (!E) return `<div class="panel"><h2>One record, now and as they will see it</h2><p class="small">Preparing an example… <span class="busy"></span></p></div>`;
  const T = E.tables.find(x => x.table === S.exTable) || E.tables[0];
  if (!T || !T.rows.length) return "";
  const i = Math.min(S.exRow || 0, T.rows.length - 1), r = T.rows[i], P = S.plan.plan;
  const techOf = c => P.actions.find(x => x.table === T.table && x.column === c)?.technique || "drop";
  const order = c => LANES.findIndex(l => l[0] === techOf(c));
  const rows = Object.keys(r.raw).sort((x, y) => order(x) - order(y)).map(c => {
    const tech = techOf(c), [, icon, name] = laneOf(tech);
    const after = tech === "drop" ? `<span class="gone">removed</span>` : esc(r.after[T.renamed[c] || c] ?? "");
    return `<tr class="t-${tech}"><td class="col">${esc(c)}</td><td class="c-${roleOf(T.table, c)}">${esc(clip(shown(T.table, c, r.raw[c]), 60))}</td><td class="arrow">→</td><td class="after">${after}</td><td class="small">${icon} ${name}</td></tr>`;
  }).join("");
  return `<div class="panel"><div class="spread"><div><span class="eyebrow">Example</span><h2>One record, now and as they will see it</h2></div>
      <div class="row">${E.tables.length > 1 ? `<div class="pills">${E.tables.map(x => `<button data-extable="${esc(x.table)}" aria-pressed="${x.table === T.table}">${esc(x.table)}</button>`).join("")}</div>` : ""}
      <button class="btn small" data-exrow="${(i + T.rows.length - 1) % T.rows.length}">←</button><span class="small">${i + 1} of ${T.rows.length}</span><button class="btn small" data-exrow="${(i + 1) % T.rows.length}">→</button></div></div>
    ${i === 0 && S.scan?.attack?.before.table === T.table ? `<p class="small">This is the person from the attack on the risk scan.</p>` : ""}
    <div class="tablewrap"><table class="example"><thead><tr><th>Column</th><th>Now (stays here)</th><th></th><th>They will see</th><th>How</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="small">Some values may also be blanked in the release, so that every person has look-alikes.</p></div>`;
}
/* k in plain words: a slider over the levels the trade-off computed */
function protectionLevel(P) {
  const T = S.tradeoff;
  if (!P.actions.length && !P.aggregates.length) return "";
  if (!T) return `<div class="panel"><h2>How strong is the protection?</h2><p class="small">Working it out on your data… <span class="busy"></span></p></div>`;
  if (T.k.length) {
    const cur = T.k.findIndex(p => p.current), i = S.kPick ?? Math.max(cur, 0), p = T.k[i];
    return `<div class="panel"><div class="spread"><div><span class="eyebrow">Protection level</span><h2>Each person hides among at least <span class="hl">${p.k}</span> people</h2></div>
        ${i !== cur ? `<button class="btn primary" data-setk="${p.k}">Use this level</button>` : `<span class="tag ok">current plan</span>`}${busy("tradeoff")}</div>
      <div class="slider"><div class="ends"><span>← Weaker: more details kept</span><span>Stronger: harder to find anyone →</span></div>
        <input type="range" min="0" max="${T.k.length - 1}" step="1" value="${i}" data-kpick aria-label="Protection level">
        <div class="ticks">${T.k.map((x, j) => `<span class="${j === cur ? "cur" : ""}">${x.k}</span>`).join("")}</div></div>
      <div class="grid2">
        <div class="gauge risk"><span>Chance an outsider picks the right person</span><b>${pct(p.guess_chance, 1)}</b><div class="meter"><b style="width:${Math.max(1, 100 * p.guess_chance)}%"></b></div></div>
        <div class="gauge safe"><span>Details kept for the receiver</span><b>${pct(p.cells_kept)}</b><div class="meter safe"><b style="width:${100 * p.cells_kept}%"></b></div></div></div>
      <p class="small">Stronger protection blanks more values. Computed on your data; nothing is released.</p></div>`;
  }
  if (T.epsilon.length) {
    const i = S.ePick ?? Math.max(T.epsilon.findIndex(x => x.current), 0), p = T.epsilon[i];
    return `<div class="panel"><span class="eyebrow">Noise level</span><h2>Published numbers are off by about <span class="hl">${pct(p.mean_error)}</span> on average</h2>
      <div class="slider"><div class="ends"><span>← More noise, more privacy</span><span>Less noise, more exact →</span></div>
        <input type="range" min="0" max="${T.epsilon.length - 1}" step="1" value="${i}" data-epick aria-label="Noise level"></div>
      <p class="small">Privacy budget ε ${p.epsilon}${p.current ? " (the receiver's agreement)" : ""}. The budget is set by the agreement with the receiver; this shows what a different budget would mean.</p></div>`;
  }
  return "";
}
/* change how one column is shared, in plain words */
function changeModal({ table, column }) {
  const a = S.plan.plan.actions.find(x => x.table === table && x.column === column);
  const c = S.scan.detections.columns.find(d => d.table === table && d.column === column);
  const opts = techniqueOptions(a, c), current = currentOption(a);
  const ex = S.example?.tables.find(x => x.table === table)?.rows[0];
  const review = S.plan.reviews.includes(`${table}.${column}`);
  return dialog(`<span class="mono">${esc(table)}.${esc(column)}</span>`, `
    <p><b>What it is:</b> ${esc(ROLE_LABEL[c?.privacy_role] || "")}${ex ? ` · for example <span class="mono">${esc(clip(shown(table, column, ex.raw[column]), 50))}</span>` : ""}</p>
    ${review ? `<p><b>Why it asks you:</b> the tool was not sure what this column holds, so a person should decide.</p>
      <details class="small"><summary>Details</summary>${esc(a.reason.replace(/^REVIEW:?\s*/, ""))}</details>`
      : `<p class="small"><b>Why:</b> ${esc(a.reason)}</p>`}
    ${review ? `<div class="callout warn">⚠ The tool could not decide this one on its own. Choose how it should be shared.</div>` : ""}
    <div class="options">${opts.map(([key, params]) => { const [tech, icon, name, help] = laneOf(key.split(":")[0]); const detail = key.includes(":") ? key.split(":")[1].replace(/_/g, " ") : "";
      return `<button class="option ${key === current ? "on" : ""}" data-choose="${esc(table)}|${esc(column)}|${esc(key)}" data-params='${esc(JSON.stringify(params))}'><span class="oicon">${icon}</span><span><b>${name}${detail ? `: ${esc(detail)}` : ""}</b><span class="small">${help}</span></span>${key === current ? `<span class="tag ok">now</span>` : ""}</button>`; }).join("")}</div>${busy("plan")}`,
  `<button class="btn primary" data-close>Done</button>`);
}
function techniqueOptions(a, c) {
  const opts = [["keep", {}], ["drop", {}], ["pseudonymise", { length: 16 }]];
  const sub = c?.subtype || "";
  if (["TIMESTAMP", "DATE"].includes(sub)) TIME_UNITS.forEach(u => opts.push([`generalise:${u}`, { to: "time", unit: u }]));
  if (sub === "BIRTH_DATE") opts.push(["generalise:age_band", { ...a.params, to: "age_band", width: 10, top: 80, rename_to: "age" }]);
  if (["DIAGNOSIS_CODE", "POSTCODE"].includes(sub)) opts.push(["generalise:truncate 3", { to: "truncate", length: 3 }]);
  if (c?.privacy_role === "free_text") opts.push(["redact_text", a.technique === "redact_text" ? a.params : {}]);
  const current = currentOption(a);
  if (!opts.some(o => o[0] === current)) opts.push([current, a.params]);
  return opts;
}
const currentOption = a => a.technique === "generalise" ? `generalise:${a.params.to === "time" ? a.params.unit : a.params.to === "truncate" ? "truncate 3" : a.params.to}` : a.technique;
function customForm() {
  const C = S.custom, det = S.scan.detections.columns.filter(c => c.privacy_role !== "record_key");
  const pub = C.trust_level === "public";
  return `<div class="grid3"><label class="field">Receiver<input type="text" data-c="recipient" value="${esc(C.recipient)}"></label>
      <label class="field">Purpose<input type="text" data-c="purpose" value="${esc(C.purpose)}"></label>
      <label class="field">How far they are trusted<select data-c="trust_level">${S.cat.trust_levels.map(t => `<option value="${t}" ${t === C.trust_level ? "selected" : ""}>${t.replace(/_/g, " ")}</option>`).join("")}</select></label></div>
    ${pub ? statisticsBuilder(det) : `<p class="small">Tick what they need. Everything else stays here (data minimisation). Each person must look like at least <input type="text" data-c="k" value="${C.k}" size="2" aria-label="k"> others on what an outsider may know.</p>
    <div class="tablewrap"><table><thead><tr><th></th><th>Column</th><th>What it is</th><th>Resolution</th></tr></thead><tbody>${det.map(c => {
      const key = c.table + "." + c.column, opts = detailOptions(c, false), need = C.needs[key];
      return `<tr><td><input type="checkbox" data-need="${esc(key)}" ${need !== undefined ? "checked" : ""} aria-label="Needs ${esc(key)}"></td><td class="col">${esc(key)}</td><td class="c-${c.privacy_role}">${ROLE_LABEL[c.privacy_role]}</td>
        <td>${opts.length > 1 || opts[0] ? `<select data-detail="${esc(key)}">${opts.map(o => `<option ${o === need ? "selected" : ""}>${o}</option>`).join("")}</select>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div>`}
`;
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
  const P = S.plan.plan, rev = S.plan.reviews, recipient = esc(S.plan.scenario?.recipient || P.scenario_id);
  const signed = P.approved && !S.reapprove;
  return `${head(4, "Check what leaves, then sign it off", "Nothing is shared until a named person approves. Your name is written into the plan and into the release.")}
  ${guide(["Check what leaves and what stays", "Tick the checks", "Type your name and approve"], [signed, signed, signed])}
  ${leavesStays(P, recipient)}
  ${signed ? `<div class="panel ready"><div class="spread"><div><span class="eyebrow">✓ Approved</span><h2>Signed off by ${esc(P.approved_by)}</h2><p class="small">Recorded in the plan and in every release.</p></div>
      <div class="row"><button class="btn" data-reapprove>Change approval</button><button class="btn primary lg" data-go="release">Create the release →</button></div></div></div>`
    : `<div class="panel signoff" id="signoff"><span class="eyebrow">Sign off</span><h2>Before you approve</h2>
      <label class="check"><input type="checkbox" data-check> <span><b>The receiver needs this data</b> for ${S.plan.scenario?.purpose ? esc(S.plan.scenario.purpose.toLowerCase()) : "the agreed purpose"}.</span></label>
      ${rev.length ? `<label class="check"><input type="checkbox" id="confirmrev" data-check ${S.confirmReview ? "checked" : ""}> <span><b>I checked the ${plural(rev.length, "column")} the tool could not decide:</b> <span class="mono">${esc(rev.join(", "))}</span> <button class="btn small" data-go="plan">Look again</button></span></label>` : ""}
      <label class="check"><input type="checkbox" data-check> <span><b>I am allowed to approve</b> sharing this data with ${recipient}.</span></label>
      <div class="row"><label class="field grow">Your full name<input type="text" id="approver" value="${esc(S.approver ?? "")}" placeholder="e.g. Maria Virtanen"></label>
        <button class="btn primary lg" data-approve disabled>Approve and continue</button>${busy("approve")}</div></div>`}`;
}

/* every table and field, and what happens to it: a list of tables on the left, their fields on the right */
function tableFates(P) {
  const det = S.scan.detections.columns, shared = new Set(planTables(P));
  const counted = new Map(P.aggregates.flatMap(g => g.dimensions.map(d => [`${g.table}.${d.column}`, g.name])));
  const names = [...new Set(det.map(c => c.table))];
  return names.map(t => {
    const cols = det.filter(c => c.table === t).map(c => c.column);
    let fields, kind;
    if (shared.has(t)) {
      kind = "shared";
      fields = cols.map(c => { const a = P.actions.find(x => x.table === t && x.column === c), tech = a?.technique || "drop", [, icon, name] = laneOf(tech);
        const as = a?.params?.rename_to; return { c, cls: tech, icon, fate: name + (as && tech !== "drop" ? ` → ${as}` : ""), why: a?.reason || "" }; });
    } else if (P.aggregates.some(g => g.table === t)) {
      kind = "counts";
      fields = cols.map(c => counted.has(`${t}.${c}`) ? { c, cls: "statistics", icon: "📊", fate: "Counted only", why: `used to count ${counted.get(`${t}.${c}`)}` } : { c, cls: "stays", icon: "🏠", fate: "Stays here", why: "" });
    } else {
      kind = "stays";
      fields = cols.map(c => ({ c, cls: "stays", icon: "🏠", fate: "Stays here", why: "the table is not shared" }));
    }
    const order = ["keep", "generalise", "pseudonymise", "redact_text", "statistics", "drop", "stays"];
    fields.sort((x, y) => order.indexOf(x.cls) - order.indexOf(y.cls));  // what leaves first, what stays last
    const out = fields.filter(f => f.cls !== "drop" && f.cls !== "stays").length;
    return { t, kind, fields, out, rank: { shared: 0, counts: 1, stays: 2 }[kind] };
  }).sort((x, y) => x.rank - y.rank || x.t.localeCompare(y.t));
}
function leavesStays(P, recipient) {
  const all = tableFates(P), sel = S.apSel || new Set(all.map(x => x.t)), q = (S.apQuery || "").toLowerCase(), kind = S.apKind || "all";
  const visible = all.filter(x => (kind === "all" || (kind === "shared" ? x.kind !== "stays" : x.kind === "stays")) && x.t.toLowerCase().includes(q));
  const leaving = all.filter(x => x.kind !== "stays"), staying = all.filter(x => x.kind === "stays");
  const fieldsOut = leaving.reduce((n, x) => n + x.out, 0), removed = leaving.reduce((n, x) => n + x.fields.length - x.out, 0);
  const badge = x => x.kind === "shared" ? `<span class="tag safe">${x.out} of ${x.fields.length} shared</span>` : x.kind === "counts" ? `<span class="tag ok">counts only</span>` : `<span class="tag">not shared</span>`;
  const shown = all.filter(x => sel.has(x.t));
  return `<div class="grid2 sumtiles">
      <div class="sumtile out"><span class="eyebrow">↗ Leaves your organisation</span><b>${plural(leaving.length, "table")}${P.aggregates.length && !planTables(P).length ? " as counts" : ""}, ${plural(fieldsOut, "field")}</b><span class="small">to ${recipient}${S.plan.scenario?.purpose ? ` · ${esc(S.plan.scenario.purpose)}` : ""}</span></div>
      <div class="sumtile stay"><span class="eyebrow">🏠 Stays on this computer</span><b>${plural(staying.length, "table")} not shared${removed ? `, ${plural(removed, "field")} removed` : ""}</b><span class="small">plus the original data, the row maps and the secret key</span></div></div>
    <div class="explorer">
      <div class="panel tlist"><div class="spread"><h3>Tables</h3><span class="small">${sel.size} of ${all.length} selected</span></div>
        ${all.length > 8 ? `<input type="text" placeholder="Search tables…" data-apquery value="${esc(S.apQuery || "")}" aria-label="Search tables">` : ""}
        <div class="pills">${[["all", "All"], ["shared", "Shared"], ["stays", "Not shared"]].map(([k, l]) => `<button data-apkind="${k}" aria-pressed="${kind === k}">${l}</button>`).join("")}</div>
        <div class="row small"><button class="linkbtn" data-apall>Select all</button>·<button class="linkbtn" data-apnone>None</button></div>
        <div class="tlist-items">${visible.map(x => `<label class="titem ${x.kind}"><input type="checkbox" data-apsel="${esc(x.t)}" ${sel.has(x.t) ? "checked" : ""}><span class="mono">${esc(x.t)}</span>${badge(x)}</label>`).join("") || `<p class="small">No table matches.</p>`}</div></div>
      <div class="fields">${shown.length ? `<div class="spread"><span class="small">${plural(shown.length, "table")} shown</span>${accTools(shown.map(x => "ap:" + x.t))}</div>` + shown.map(x => acc(`ap:${x.t}`, `<b class="mono">${esc(x.t)}</b>`, badge(x),
          x.kind === "stays" ? `<p class="small">This table is not shared. All ${plural(x.fields.length, "field")} stay here:</p><div class="row">${x.fields.map(f => `<span class="tag">${esc(f.c)}</span>`).join("")}</div>`
            : `<div class="frows">${x.fields.map(f => `<div class="frow f-${f.cls}" title="${esc(f.why)}"><span class="mono">${esc(f.c)}</span><span class="fate">${f.icon} ${esc(f.fate)}</span></div>`).join("")}</div>`,
          x.kind !== "stays", `fcard ${x.kind}`)).join("")
        : `<div class="panel"><p class="small">Select one or more tables on the left to see their fields.</p></div>`}</div>
    </div>`;
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
  if (!R) return `${head(5, "Release and proof")}<div class="panel ready"><div class="spread"><div><span class="eyebrow">Approved by ${esc(S.plan.plan.approved_by)}</span><h2>Create the release for ${esc(S.plan.scenario?.recipient || S.plan.plan.scenario_id)}</h2>
    <p class="small">The protected files are written, checked against the plan, and replayed against the same attacker.</p></div><button class="btn primary lg" data-modal="release">Create the release…</button></div>${busy("run")}</div>`;
  const create = approved && !S.viewing ? `<div class="row"><button class="btn" data-modal="release">New release…</button>${busy("run")}</div>` : "";
  const m = R.summary, kept = valuesKept(R), A = R.attack;
  const banner = S.viewing ? `<div class="banner"><span>Viewing an earlier release: <b>${esc(m.release_id)}</b>, made ${esc(when(m.created_at))}.</span>${S.history[0] && S.history[0].release_id !== m.release_id ? `<button class="btn small" data-view="${esc(S.history[0].release_id)}">Open the latest</button>` : ""}</div>` : "";
  return `${head(5, "Release and proof", `<b>${esc(m.release_id)}</b> for ${esc(m.recipient)} · approved by ${esc(m.approved_by || "–")} · ${esc(when(m.created_at))}`)}
  ${guide(["Create the release", "Check the proof: the same attack should now fail", "Download it and send it to the receiver"], [true, true, !!R.published])}
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
  return `<div class="spread"><p class="small">The same records, raw and released, matched on this computer through the private row map (which never leaves). Read each pair top to bottom; click one to see it in full.</p>
      ${withPairs.length > 1 ? `<div class="pills">${withPairs.map(x => `<button data-table="${esc(x.name)}" aria-pressed="${x.name === t.name}">${esc(x.name)}</button>`).join("")}</div>` : ""}</div>
    <div class="tablewrap"><table class="diff"><thead><tr><th></th>${cols.map(c => `<th>${esc(c)}<br><span class="tech ${tech(c).split(":")[0]}">${esc(tech(c))}</span></th>`).join("")}</tr></thead><tbody>
      ${t.pairs.map((p, i) => `<tr class="rawrow clickable" data-record="${esc(t.name)}|${i}"><td class="who">raw ↗</td>${cols.map(c => `<td class="c-${roleOf(t.name, c)}" title="${esc(shown(t.name, c, p.raw[c]))}">${esc(shown(t.name, c, p.raw[c]))}</td>`).join("")}</tr>
        <tr class="relrow"><td class="who">released</td>${cols.map(c => cell(p, c)).join("")}</tr>`).join("")}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--risk)"></i>dropped</span><span><i style="background:var(--safe)"></i>coded or coarsened</span><span><i style="background:var(--warn)"></i>blanked so every row has look-alikes</span><span><i style="background:var(--line-strong)"></i>kept as is</span></div>`;
}
function columnsTab(R) {
  if (!R.tables.length) return `<p class="small">No rows are released.</p>`;
  return R.tables.map(t => {
    const ch = t.changes, blanked = t.suppression ? Object.values(t.suppression.cells_blanked).reduce((s, x) => s + x, 0) : 0;
    return acc(`cc:${t.name}`, `<b class="mono">${esc(t.name)}</b> <span class="small">${fmt(t.rows_in)} rows in, ${fmt(t.rows_out)} out</span>`, t.suppression ? `<span class="small">${fmt(t.suppression.rows_removed)} rows removed, ${fmt(blanked)} values blanked for k</span>` : "", `
    <div class="tablewrap"><table><thead><tr><th>Column</th><th>Protection</th><th>Values</th><th>Distinct</th><th>Released values</th></tr></thead><tbody>${ch.map(c => `<tr>
      <td class="col">${esc(c.column)}${c.released_as && c.released_as !== c.column ? ` → ${esc(c.released_as)}` : ""}</td><td><span class="tech ${c.technique}">${esc(c.technique)}</span></td>
      <td class="num">${fmt(c.filled_before)} → ${fmt(c.filled_after)}</td><td class="num">${fmt(c.distinct_before)} → ${fmt(c.distinct_after)}</td>
      <td>${c.top_after.slice(0, 5).map(([v, s]) => `<div class="hbar"><span class="mono">${esc(v)}</span><div class="meter safe"><b style="width:${100 * s}%"></b></div><span>${pct(s)}</span></div>`).join("")}</td></tr>`).join("")}</tbody></table></div>`, R.tables.indexOf(t) === 0);
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
  return `<div class="spread"><p class="small">Every release made from this dataset is kept here. Tick two to compare them.</p>${S.cmp ? `<button class="btn small" data-modal="compare">Show the comparison</button>` : ""}</div>
    <div class="list">${H.map(h => `<div class="item ${h.release_id === cur ? "current" : ""}">
      <div><b class="mono">${esc(h.release_id)}</b><span class="small">${esc(when(h.created_at))} · for ${esc(h.recipient)} · approved by ${esc(h.approved_by || "–")}</span></div>
      <div class="small">${h.k != null ? `k ${h.k}` : ""}${h.epsilon != null ? ` ε ${h.epsilon}` : ""} · ${plural(h.files.length, "file")}</div>
      <div class="small">${h.singled_out_after != null ? `singled out ${pct(h.singled_out_before)} → <b>${pct(h.singled_out_after)}</b>, guess ${pct(h.guess_chance_after, 1)}` : "statistics only"}</div>
      <div class="row"><label class="switch"><input type="checkbox" data-pick="${esc(h.release_id)}" ${S.picked.includes(h.release_id) ? "checked" : ""}> compare</label>
        ${h.release_id === cur ? `<span class="tag ok">open</span>` : `<button class="btn small" data-view="${esc(h.release_id)}">Open</button>`}</div></div>`).join("")}</div>
    ${busy("cmp")}${S.picked.length === 1 ? `<p class="small">Tick one more release to compare.</p>` : ""}`;
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
      <tr><td>Receiver</td>${A.recipient === B.recipient ? `<td colspan="3">${esc(A.recipient)} <span class="small">(both)</span></td>` : `<td>${esc(A.recipient)}</td><td>${esc(B.recipient)}</td><td></td>`}</tr>
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

/* ---------------------------------------------------------------- dialogs: one native <dialog>, filled from S.modal */
function openModal(kind, data = {}) { S.modal = { kind, ...data }; render(); }
function closeModal() { S.modal = null; render(); }
const dialog = (title, body, actions = "") => `<div class="mhead"><h2>${title}</h2><button class="btn ghost" data-close aria-label="Close">✕</button></div>
  <div class="mbody">${body}</div>${actions ? `<div class="mfoot">${actions}</div>` : ""}`;
const WIDE = ["record", "compare", "receiver"];
function renderModal() {
  const d = $("#modal");
  if (!S.modal) { if (d.open) d.close(); return; }
  d.className = "modal" + (WIDE.includes(S.modal.kind) ? " wide" : "");
  d.innerHTML = MODALS[S.modal.kind](S.modal);
  if (!d.open) d.showModal();
}
function columnModal({ i }) {
  const c = S.scan.detections.columns[i], roles = S.cat.roles, subs = S.cat.subtypes;
  const table = S.session.tables.find(t => t.name === c.table), samples = (table?.preview || []).map(r => r[c.column]).filter(v => v !== "" && v != null).slice(0, 6);
  return dialog(`<span class="mono">${esc(c.table)}.${esc(c.column)}</span>`, `
    <div class="grid2"><label class="field">What it is<select data-override="${i}" data-field="privacy_role">${roles.map(r => `<option value="${r}" ${r === c.privacy_role ? "selected" : ""}>${ROLE_LABEL[r] || r}</option>`).join("")}</select></label>
      <label class="field">Type<select data-override="${i}" data-field="subtype">${subs.map(r => `<option ${r === c.subtype ? "selected" : ""}>${r}</option>`).join("")}</select></label></div>
    <div><span class="eyebrow">How sure</span><div class="spread"><div class="meter safe" style="flex:1"><b style="width:${100 * c.confidence}%"></b></div><b class="num">${c.confidence.toFixed(2)}</b></div></div>
    <div><span class="eyebrow">Why</span><ul class="plain">${c.evidence.map(e => `<li><span class="tag">${esc(e.kind)}</span> ${esc(e.detail)}</li>`).join("")}</ul></div>
    ${samples.length ? `<div><span class="eyebrow">Values from the first rows</span><div class="row">${samples.map(v => `<span class="tag">${esc(clip(shown(c.table, c.column, v), 40))}</span>`).join("")}</div></div>` : ""}
    <p class="small">A change here is kept as a reviewer's correction (with your name in the evidence) and the plan follows it.</p>${busy("scan")}`,
  `<button class="btn primary" data-close>Done</button>`);
}
function releaseModal() {
  const P = S.plan.plan;
  return dialog("Create the release", `
    <label class="field">Receiver name<input type="text" id="receiver" value="${esc(S.lastReceiver || "receiver")}" autofocus></label>
    <p class="small">The name selects the receiver's own key: each receiver gets different codes, so two receivers cannot join their copies.</p>
    <div><span class="eyebrow">Files</span><div class="row">${planTables(P).map(t => `<span class="tag safe">${esc(t)}.csv</span>`).join("")}${P.aggregates.map(a => `<span class="tag safe">${esc(a.name)}.csv</span>`).join("")}<span class="tag">manifest.json</span></div></div>
    <p class="small">Row maps (which released row came from which record) stay in the private folder on this computer.</p>${busy("run")}`,
  `<button class="btn" data-close>Cancel</button><button class="btn primary" data-run>Create the release</button>`);
}
function publishModal({ href }) {
  const m = S.results.summary;
  return dialog("Publish these statistics?", `
    <p>Downloading publishes <b>${plural(S.results.statistics.length, "statistics table")}</b> and spends <b>ε ${m.epsilon}</b> of the privacy budget for this receiver${m.budget_cap ? ` (cap ε ${m.budget_cap})` : ""}.</p>
    <p class="small">The spending is written to the privacy budget ledger once; downloading again later does not spend more.</p>`,
  `<button class="btn" data-close>Cancel</button><button class="btn safe" data-publish="${esc(href)}">Publish and download</button>`);
}
function recordModal({ table, i }) {
  const R = S.results, t = R.tables.find(x => x.name === table), p = t.pairs[i];
  const renamed = Object.fromEntries(t.changes.map(c => [c.column, c.released_as || c.column]));
  const rows = Object.keys(p.raw).map(c => {
    const k = R.techniques[`${table}.${c}`] || "keep", base = k.split(":")[0], v = p.released[renamed[c]];
    const after = base === "drop" || base === "withheld" ? `<span class="d-drop"></span>` : v === "" || v == null ? `<span class="d-blank"></span>` : `<span class="d-${base}">${esc(v)}</span>`;
    return `<tr><td class="col">${esc(c)}</td><td class="c-${roleOf(table, c)}">${esc(shown(table, c, p.raw[c]))}</td><td class="diff">${after}</td><td><span class="tech ${base}">${esc(k)}</span></td></tr>`;
  }).join("");
  return dialog(`One record of <span class="mono">${esc(table)}</span>, before and after`, `<div class="tablewrap free"><table><thead><tr><th>Column</th><th>Raw (stays here)</th><th>Released</th><th>Protection</th></tr></thead><tbody>${rows}</tbody></table></div>`,
    `<button class="btn" data-record="${esc(table)}|${(i + t.pairs.length - 1) % t.pairs.length}">← Previous</button><button class="btn" data-record="${esc(table)}|${(i + 1) % t.pairs.length}">Next →</button>`);
}
function datasetOf(m) { return S.sessions.find(x => x.id === (m.id || S.session?.id)) || S.session; }
function renameModal(m) {
  const d = datasetOf(m);
  return dialog("Rename the dataset", `<label class="field">Name<input type="text" id="dsrename" value="${esc(d.name)}" autofocus></label>
    <p class="small">Letters, digits, '-' and '_'; other characters become '_'.</p>${busy("rename")}`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" data-rename="${esc(d.id)}">Save</button>`);
}
function duplicateModal(m) {
  const d = datasetOf(m);
  return dialog("Duplicate the dataset", `<p>A new dataset with the same ${plural(d.tables.length, "table")} and your column corrections. You can add or remove tables, then scan, plan and release again.</p>
    <p class="small">The original${d.released ? " and its releases stay" : " stays"} exactly as ${d.released ? "they are" : "it is"}.</p>
    <label class="field">Name of the copy<input type="text" id="dsdupname" value="${esc(d.name)}-copy" autofocus></label>${busy("duplicate")}`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" data-duplicate="${esc(d.id)}">Create the copy and open it</button>`);
}
const confirmModal = m => dialog(m.title, `<p>${m.text}</p>${busy("confirm")}`, `<button class="btn" data-close>Cancel</button><button class="btn ${m.danger ? "risk" : "primary"}" data-confirm>${m.yes}</button>`);
const compareModal = () => dialog("Two releases side by side", compareReleases(S.cmp), `<button class="btn primary" data-close>Close</button>`);
const receiverModal = () => dialog("Describe the receiver", customForm(), `<button class="btn" data-close>Cancel</button><button class="btn primary" data-make="custom">Make the plan</button>${busy("plan")}`);
const MODALS = { rename: renameModal, duplicate: duplicateModal, confirm: confirmModal, column: columnModal, change: changeModal, release: releaseModal, publish: publishModal, record: recordModal, compare: compareModal, receiver: receiverModal };

/* ---------------------------------------------------------------- events */
function wire() {
  const page = document.body;  // the page and the open dialog
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
  page.querySelectorAll("[data-pick-files]").forEach(b => (b.onclick = () => $("#files")?.click()));
  page.querySelectorAll("[data-close]").forEach(b => (b.onclick = closeModal));
  page.querySelectorAll("details[data-acc]").forEach(d => d.addEventListener("toggle", () => { S.accOpen = { ...S.accOpen, [d.dataset.acc]: d.open }; }));
  page.querySelectorAll("[data-acc-all], [data-acc-none]").forEach(b => (b.onclick = () => {
    const open = "accAll" in b.dataset, keys = (b.dataset.accAll || b.dataset.accNone).split("|");
    S.accOpen = { ...S.accOpen, ...Object.fromEntries(keys.map(k => [k, open])) }; render();
  }));
  page.querySelectorAll("[data-new]").forEach(b => (b.onclick = newDataset));
  page.querySelectorAll("[data-modal-for]").forEach(b => (b.onclick = () => { const [kind, id] = b.dataset.modalFor.split("|"); openModal(kind, { id }); }));
  page.querySelectorAll("[data-confirm]").forEach(b => (b.onclick = () => { const run = S.modal.run; act("confirm", async () => { await run(); S.modal = null; }); }));
  // typed values are read before act() redraws the dialog
  page.querySelectorAll("[data-rename]").forEach(b => (b.onclick = () => { const name = $("#dsrename").value; act("rename", async () => {
    const d = await api(`/api/sessions/${b.dataset.rename}/rename`, { body: { name } });
    if (S.session?.id === d.id) S.session = d;
    S.sessions = await api("/api/sessions"); S.modal = null; toast(`Renamed to ${d.name}.`);
  }); }));
  page.querySelectorAll("[data-duplicate]").forEach(b => (b.onclick = () => { const name = $("#dsdupname").value; act("duplicate", async () => {
    const d = await api(`/api/sessions/${b.dataset.duplicate}/duplicate`, { body: { name } });
    S.modal = null; openSession(d); toast(`Created ${d.name}. Add or remove tables, then scan.`); window.scrollTo(0, 0);
  }); }));
  page.querySelectorAll("[data-add-tables]").forEach(b => (b.onclick = () => $("#addfiles").click()));
  page.querySelectorAll("#addfiles").forEach(inp => (inp.onchange = () => addTables(inp.files)));
  page.querySelectorAll("[data-remove-table]").forEach(b => (b.onclick = () => {
    const table = b.dataset.removeTable;
    openModal("confirm", { title: `Remove ${esc(table)}?`, yes: "Remove the table", danger: true,
      text: `<b>${esc(table)}</b> leaves this dataset (your original file is not touched). ${S.scan ? "The scan and plan start over, because the data changed." : ""}`,
      run: async () => dataChanged(await api(`/api/sessions/${sid()}/tables/${encodeURIComponent(table)}`, { method: "DELETE" }), `Removed ${table}.`) });
  }));
  page.querySelectorAll("[data-delete-ds]").forEach(b => (b.onclick = () => {
    const d = S.sessions.find(x => x.id === b.dataset.deleteDs);
    openModal("confirm", { title: `Delete ${esc(d.name)}?`, yes: "Delete it", danger: true,
      text: `The dataset's local copy, scan and plan are deleted from this computer. It was never released. This cannot be undone.`,
      run: async () => { await api(`/api/sessions/${d.id}`, { method: "DELETE" }); if (S.session?.id === d.id) newDataset(); S.sessions = await api("/api/sessions"); toast(`Deleted ${d.name}.`); } });
  }));
  page.querySelectorAll("[data-modal]").forEach(b => (b.onclick = () => openModal(b.dataset.modal)));
  page.querySelectorAll("[data-col]").forEach(b => (b.onclick = e => { e.stopPropagation(); openModal("column", { i: +b.dataset.col }); }));
  page.querySelectorAll("[data-record]").forEach(b => (b.onclick = () => { const [table, i] = b.dataset.record.split("|"); openModal("record", { table, i: +i }); }));
  page.querySelectorAll("[data-another]").forEach(b => (b.onclick = () => act("another", async () => {
    S.scan.attack = await api(`/api/sessions/${sid()}/attack/another`, { body: {} });
    play("scan", false);
  })));
  page.querySelectorAll("[data-publish]").forEach(b => (b.onclick = () => { closeModal(); download(b.dataset.publish); }));
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
    if (S.receiverChoice === "custom") { if (!S.custom) S.custom = newCustom(); openModal("receiver"); return; }
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
    S.plan = await api(`/api/sessions/${sid()}/plan`, { body: { custom: customScenario() } }); planChanged(); S.compare = null; S.modal = null;
  })));
  page.querySelectorAll("[data-change]").forEach(b => (b.onclick = () => { const [table, column] = b.dataset.change.split("|"); S.boardSeen = true; openModal("change", { table, column }); }));
  page.querySelectorAll("[data-choose]").forEach(b => (b.onclick = () => {
    const [table, column, key] = b.dataset.choose.split("|");
    const body = { table, column, technique: key.split(":")[0], params: JSON.parse(b.dataset.params || "{}") };
    act("plan", async () => { S.plan = await api(`/api/sessions/${sid()}/plan/action`, { body }); planChanged(); });
  }));
  page.querySelectorAll("[data-lane]").forEach(b => (b.onclick = () => { S.openLanes = { ...S.openLanes, [b.dataset.lane]: true }; render(); }));
  page.querySelectorAll("[data-extable]").forEach(b => (b.onclick = () => { S.exTable = b.dataset.extable; S.exRow = 0; render(); }));
  page.querySelectorAll("[data-exrow]").forEach(b => (b.onclick = () => { S.exRow = +b.dataset.exrow; render(); }));
  page.querySelectorAll("[data-kpick]").forEach(r => (r.oninput = () => { S.kPick = +r.value; render(); $("[data-kpick]")?.focus(); }));
  page.querySelectorAll("[data-epick]").forEach(r => (r.oninput = () => { S.ePick = +r.value; render(); $("[data-epick]")?.focus(); }));
  const fates = () => tableFates(S.plan.plan).map(x => x.t);
  page.querySelectorAll("[data-apsel]").forEach(c => (c.onchange = () => {
    const sel = new Set(S.apSel || fates()); c.checked ? sel.add(c.dataset.apsel) : sel.delete(c.dataset.apsel); S.apSel = sel; render();
  }));
  page.querySelectorAll("[data-apall]").forEach(b => (b.onclick = () => { S.apSel = null; render(); }));
  page.querySelectorAll("[data-apnone]").forEach(b => (b.onclick = () => { S.apSel = new Set(); render(); }));
  page.querySelectorAll("[data-apkind]").forEach(b => (b.onclick = () => { S.apKind = b.dataset.apkind; render(); }));
  page.querySelectorAll("[data-apquery]").forEach(i => (i.oninput = () => { S.apQuery = i.value; render(); const n = $("[data-apquery]"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }));
  page.querySelectorAll("[data-reapprove]").forEach(b => (b.onclick = () => { S.reapprove = true; render(); }));
  page.querySelectorAll("[data-focus]").forEach(b => (b.onclick = () => { const el = $("#" + b.dataset.focus); el?.scrollIntoView({ behavior: "smooth", block: "center" }); el?.querySelector("input[type=checkbox]")?.focus(); }));
  const signoff = $("#signoff");
  if (signoff) {  // approve unlocks when every check is ticked and a name is typed
    const ready = () => { const ok = [...signoff.querySelectorAll("[data-check]")].every(c => c.checked) && ($("#approver").value.trim().length > 1); signoff.querySelector("[data-approve]").disabled = !ok; };
    signoff.querySelectorAll("[data-check]").forEach(c => c.addEventListener("change", ready));
    $("#approver").addEventListener("input", ready);
    ready();
  }
  page.querySelectorAll("[data-setk]").forEach(b => (b.onclick = () => act("tradeoff", async () => {
    S.plan = await api(`/api/sessions/${sid()}/plan/k`, { body: { k: +b.dataset.setk } }); planChanged(); S.kPick = null;
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
      S.modal = null; S.reapprove = false;
      toast(`Approved by ${S.plan.plan.approved_by}.`);
    });
  }));
  page.querySelectorAll("[data-run]").forEach(b => (b.onclick = () => {
    S.lastReceiver = receiver.value.trim();
    act("run", async () => {
      S.results = await api(`/api/sessions/${sid()}/run`, { body: { receiver: S.lastReceiver } });
      S.viewing = null; S.cmp = null; S.picked = []; S.modal = null;
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
      S.modal = { kind: "compare" };
    }); else render();
  }));
  page.querySelectorAll("[data-textview]").forEach(b => (b.onclick = () => { S.textView = b.dataset.textview; render(); }));
  page.querySelectorAll("[data-download]").forEach(a => (a.onclick = e => {
    e.preventDefault();
    if (S.results?.summary.epsilon != null && !S.results.published) openModal("publish", { href: a.getAttribute("href") });  // spending ε needs a yes
    else download(a.getAttribute("href"));
  }));
}
async function download(href) {
  const res = await fetch(href);
  if (!res.ok) { toast((await res.json()).error || "download refused", true); return; }
  const blob = await res.blob(), url = URL.createObjectURL(blob), tmp = document.createElement("a");
  tmp.href = url; tmp.download = (res.headers.get("Content-Disposition") || "").split('filename="')[1]?.replace('"', "") || "release.zip";
  tmp.click(); URL.revokeObjectURL(url); S.results.published = true; render();
}
function planChanged() {
  S.apSel = null;
  S.confirmReview = false; S.results = null; S.viewing = null; S.tradeoff = null;
  const plan = S.plan;  // the example and the trade-off load by themselves; a newer plan wins
  S.example = null;
  api(`/api/sessions/${sid()}/plan/example`).then(e => { if (S.plan === plan) { S.example = e; render(); } }).catch(() => {});
  api(`/api/sessions/${sid()}/tradeoff`).then(t => { if (S.plan === plan) { S.tradeoff = t; render(); } }).catch(() => {});
}
function loadCompare() {
  act("compare", async () => { S.compare = await api(`/api/sessions/${sid()}/compare`, { body: { scenario_ids: S.cat.receivers.map(r => r.id) } }); });
}
const mb = n => (n / 2 ** 20).toFixed(n < 10 * 2 ** 20 ? 1 : 0);
function uploadWithProgress(form, url = "/api/sessions/upload") {  // XMLHttpRequest reports upload progress; fetch does not
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
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
async function addTables(files) {
  if (!files?.length) return;
  const form = new FormData(), list = [...files], size = list.reduce((n, f) => n + f.size, 0);
  list.forEach(f => form.append("files", f));
  await withProgress(`Adding ${plural(list.length, "file")} to ${S.session.name}`, "Starting…", async () => {
    setProgress(0, `0 of ${mb(size)} MB copied`);
    dataChanged(await uploadWithProgress(form, `/api/sessions/${sid()}/tables`), `Added ${list.map(f => f.name).join(", ")}.`);
  });
}
/* the tables changed: what was built on them starts over */
async function dataChanged(overview, message) {
  const hadScan = !!S.scan;
  Object.assign(S, { session: overview, scan: null, plan: null, results: null, tradeoff: null, example: null, compare: null, table: null, step: "data" });
  S.sessions = await api("/api/sessions");
  toast(message + (hadScan ? " Scan again to see the new risks." : ""));
}
/* start fresh from any step; the current work stays saved in the workspace */
function newDataset() {
  Object.assign(S, { session: null, scan: null, plan: null, results: null, history: [], viewing: null, picked: [], cmp: null, tradeoff: null, example: null, compare: null, table: null, receiverChoice: null, custom: null, modal: null, step: "data" });
  remember(); render(); window.scrollTo(0, 0);
  api("/api/sessions").then(x => { S.sessions = x; render(); }).catch(() => {});
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
  setTimeout(() => { if (S.play === which) S.play = ""; }, 5600);  // the trail finishes last
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

/* ---------------------------------------------------------------- theme: light (default), dark, or follow the system */
function applyTheme(theme) {
  if (theme === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("pets.theme", theme); } catch (e) { /* storage off: the choice lasts this visit */ }
  document.querySelectorAll("[data-theme-set]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.themeSet === theme)));
}
function wireTheme() {
  let theme = "light"; try { theme = localStorage.getItem("pets.theme") || "light"; } catch (e) { /* storage off */ }
  document.querySelectorAll("[data-theme-set]").forEach(b => (b.onclick = () => applyTheme(b.dataset.themeSet)));
  applyTheme(theme);
}

/* ---------------------------------------------------------------- start */
(async () => {
  const d = $("#modal");
  d.addEventListener("close", () => { if (S.modal) { S.modal = null; render(); } });  // Esc
  d.addEventListener("click", e => { if (e.target === d) closeModal(); });  // a click on the backdrop
  wireTheme();
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
