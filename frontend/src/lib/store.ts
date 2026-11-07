// The app's state and everything the user can do. Screens read from here and call these actions; all data comes
// from the local API. Errors are shown as toasts in one place (`busy`).
import { toast } from "sonner";
import { create } from "zustand";
import {
  api, download, upload, type Attack, type Catalogue, type Compare, type Example, type PlanCompare, type PlanVersions, type PlanView, type ReleaseSummary,
  type Results, type Scan, type SessionListItem, type SessionOverview, type Tradeoff,
} from "./api";
import { fmt, mb, plural } from "./format";

export type Step = "data" | "scan" | "plan" | "approve" | "release";
export const STEPS: [Step, string][] = [["data", "Data"], ["scan", "Risk scan"], ["plan", "Receiver & plan"], ["approve", "Review & approve"], ["release", "Release & proof"]];
export type Progress = { title: string; detail: string; pct: number | null; started: number; checks?: string[] };
export type Theme = "light" | "dark" | "system";

interface State {
  step: Step; cat: Catalogue | null; sessions: SessionListItem[]; session: SessionOverview | null;
  scan: Scan | null; plan: PlanView | null; results: Results | null; history: ReleaseSummary[]; viewing: string | null;
  tradeoff: Tradeoff | null; example: Example | null; compare: Compare | null; versions: PlanVersions | null;
  busy: string; progress: Progress | null; play: "" | "scan" | "release"; mask: boolean; theme: Theme; receiverChoice: string | null;
  publishAsk: boolean;  // a statistics download waits for a yes
}

const empty = { session: null, scan: null, plan: null, results: null, history: [], viewing: null, tradeoff: null, example: null, compare: null, versions: null, receiverChoice: null };
const sid = () => useApp.getState().session!.id;
const remember = (id: string) => { try { localStorage.setItem("pets.session", id); } catch { /* storage off */ } };
const set = (p: Partial<State>) => useApp.setState(p);

export const useApp = create<State>(() => ({
  step: "data", cat: null, sessions: [], ...empty, busy: "", progress: null, play: "", mask: true, publishAsk: false,
  theme: (() => { try { return (localStorage.getItem("pets.theme") as Theme) || "light"; } catch { return "light"; } })(),
}));

/** Run an action with a busy marker; failures become an error toast. */
async function busy<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
  set({ busy: label });
  try { return await fn(); } catch (e) { toast.error((e as Error).message); return undefined; } finally { set({ busy: "" }); }
}
/** Long waits show a progress card instead of a spinner. */
async function withProgress(title: string, detail: string, fn: () => Promise<void>, checks?: string[]) {
  set({ progress: { title, detail, pct: null, started: Date.now(), checks } });
  try { await fn(); } catch (e) { toast.error((e as Error).message); } finally { set({ progress: null }); window.scrollTo(0, 0); }
}
const setProgress = (pct: number | null, detail: string) => { const p = useApp.getState().progress; if (p) set({ progress: { ...p, pct, detail } }); };

/** The attack replay animates once; redraws later show it settled. */
export function play(which: "scan" | "release") {
  set({ play: "" });
  requestAnimationFrame(() => { set({ play: which }); setTimeout(() => useApp.getState().play === which && set({ play: "" }), 5600); });
}

export const can = (step: Step) => {
  const s = useApp.getState();
  return { data: true, scan: !!s.session, plan: !!s.scan, approve: !!s.plan, release: !!s.plan?.plan.approved || !!s.results }[step];
};
export function go(step: Step) { if (can(step)) { set({ step }); window.scrollTo(0, 0); } }

// ---------------------------------------------------------------- start, theme, mask
export async function init() {
  applyTheme(useApp.getState().theme);
  try { set({ cat: await api<Catalogue>("/api/catalogue"), sessions: await api<SessionListItem[]>("/api/sessions") }); }
  catch (e) { toast.error((e as Error).message); }
  let saved = ""; try { saved = localStorage.getItem("pets.session") || ""; } catch { /* storage off */ }
  if (useApp.getState().sessions.some(x => x.id === saved)) await reopen(saved);
}
export function applyTheme(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  try { localStorage.setItem("pets.theme", theme); } catch { /* storage off */ }
  set({ theme });
}
export const setMask = (mask: boolean) => set({ mask });

// ---------------------------------------------------------------- datasets
const refreshSessions = async () => set({ sessions: await api<SessionListItem[]>("/api/sessions") });
const refreshHistory = async () => set({ history: await api<ReleaseSummary[]>(`/api/sessions/${sid()}/releases`) });

function opened(s: SessionOverview) {
  set({ ...empty, session: s, step: "data" });
  remember(s.id);
  refreshSessions(); refreshHistory();
}
export function newDataset() { set({ ...empty, step: "data" }); remember(""); refreshSessions(); window.scrollTo(0, 0); }

export const openSample = (name: string) =>
  withProgress(`Opening the ${name.replace(/_/g, " ")} example`, "Copying the tables into your workspace and reading them…",
    async () => opened(await api<SessionOverview>("/api/sessions/sample", { body: { name } })));

function formOf(files: FileList | File[], name?: string) {
  const form = new FormData(), list = [...files];
  list.forEach(f => form.append("files", f));
  if (name !== undefined) form.append("name", name || "my-data");
  return { form, list, size: list.reduce((n, f) => n + f.size, 0) };
}
const sending = (size: number) => ({
  progress: (sent: number, total: number) => setProgress(sent / total, `${mb(sent)} of ${mb(total)} MB copied`),
  sent: () => setProgress(null, "Reading your tables: counting rows and columns…"),
  start: () => setProgress(0, `0 of ${mb(size)} MB copied`),
});

export function uploadFiles(files: FileList | File[], name: string) {
  const { form, list, size } = formOf(files, name), s = sending(size);
  return withProgress(`Uploading ${plural(list.length, "file")} (${mb(size)} MB)`, "Starting…", async () => {
    s.start(); opened(await upload<SessionOverview>("/api/sessions/upload", form, s.progress, s.sent));
  });
}

/** The tables changed: the scan and plan built on them start over. */
async function dataChanged(s: SessionOverview, message: string) {
  const hadScan = !!useApp.getState().scan;
  set({ ...empty, session: s, step: "data" });
  await refreshSessions();
  toast.success(message, { description: hadScan ? "Scan again to see the new risks." : undefined });
}
export function addTables(files: FileList) {
  const { form, list, size } = formOf(files), s = sending(size);
  return withProgress(`Adding ${plural(list.length, "file")} to ${useApp.getState().session!.name}`, "Starting…", async () => {
    s.start(); await dataChanged(await upload<SessionOverview>(`/api/sessions/${sid()}/tables`, form, s.progress, s.sent), `Added ${list.map(f => f.name).join(", ")}.`);
  });
}
export const removeTable = (table: string) => busy("confirm", async () =>
  dataChanged(await api<SessionOverview>(`/api/sessions/${sid()}/tables/${encodeURIComponent(table)}`, { method: "DELETE" }), `Removed ${table}.`));

export const SCAN_CHECKS = [
  "what each column holds: names, ID codes (with checksums), phones, addresses, dates, codes",
  "which facts an outsider could already know, and how many people they single out",
  "which keys join the tables, so one match unlocks the rest",
  "an attack on one person, the way an outsider would do it",
];

/** Reopen earlier work: the scan, the plan and the latest release come back as they were left. */
export function reopen(id: string) {
  const name = useApp.getState().sessions.find(x => x.id === id)?.name ?? "your dataset";
  set({ step: "data" });
  return withProgress(`Reopening ${name}`, "Reading the tables, the saved scan, the plan and earlier releases…", async () => {
    const s = await api<SessionOverview>(`/api/sessions/${id}`);
    set({ ...empty, session: s }); remember(id);
    if (s.steps.scanned) set({ scan: await api<Scan>(`/api/sessions/${id}/scan`, { method: "POST" }) });
    if (s.steps.planned) { const plan = await api<PlanView>(`/api/sessions/${id}/plan`); set({ plan, receiverChoice: plan.plan.scenario_id }); planLoaded(); }
    await refreshHistory();
    const h = useApp.getState().history;
    if (h.length) set({ results: await api<Results>(`/api/sessions/${id}/releases/${encodeURIComponent(h[0].release_id)}`) });
    const st = useApp.getState();
    set({ step: st.results ? "release" : st.plan ? "plan" : st.scan ? "scan" : "data" });
  });
}

export const renameDataset = (id: string, name: string) => busy("rename", async () => {
  const d = await api<SessionOverview>(`/api/sessions/${id}/rename`, { body: { name } });
  if (useApp.getState().session?.id === id) set({ session: d });
  await refreshSessions(); toast.success(`Renamed to ${d.name}.`); return true;
});
export const duplicateDataset = (id: string, name: string) => busy("duplicate", async () => {
  const d = await api<SessionOverview>(`/api/sessions/${id}/duplicate`, { body: { name } });
  opened(d); toast.success(`Created ${d.name}.`, { description: "Add or remove tables, then scan." }); return true;
});
export const deleteDataset = (id: string) => busy("confirm", async () => {
  const name = useApp.getState().sessions.find(x => x.id === id)?.name;
  await api(`/api/sessions/${id}`, { method: "DELETE" });
  if (useApp.getState().session?.id === id) newDataset();
  await refreshSessions(); toast.success(`Deleted ${name}.`);
});

// ---------------------------------------------------------------- risk scan
export function runScan() {
  const s = useApp.getState().session!;
  set({ step: "scan" });
  return withProgress("Scanning for risks", `Reading ${fmt(s.tables.reduce((n, t) => n + t.rows, 0))} rows in ${plural(s.tables.length, "table")}. Large data can take a minute; the result is saved.`,
    async () => { set({ scan: await api<Scan>(`/api/sessions/${sid()}/scan`, { method: "POST" }) }); play("scan"); }, SCAN_CHECKS);
}
export const anotherPerson = () => busy("another", async () => {
  const attack = await api<Attack>(`/api/sessions/${sid()}/attack/another`, { body: {} });
  set({ scan: { ...useApp.getState().scan!, attack } }); play("scan");
});
export const correctColumn = (i: number, field: "privacy_role" | "subtype", value: string) => busy("scan", async () => {
  const scan = useApp.getState().scan!, c = scan.detections.columns[i];
  const col = await api<Scan["detections"]["columns"][number]>(`/api/sessions/${sid()}/detections`,
    { body: { table: c.table, column: c.column, privacy_role: c.privacy_role, subtype: c.subtype, [field]: value } });
  const columns = scan.detections.columns.map((x, j) => (j === i ? col : x));
  set({ scan: { ...scan, detections: { columns } }, plan: null, results: null, tradeoff: null, example: null, compare: null });
  toast.success(`${c.column} corrected.`, { description: "Make the plan again to use it." });
});

// ---------------------------------------------------------------- plan
/** A new or changed plan: the example record and the trade-off load by themselves. A later change wins; approving
 *  does not count as a change (it alters nothing the example or the trade-off depend on). */
let planRevision = 0;
function planLoaded() {
  const mine = ++planRevision, current = () => planRevision === mine;
  set({ results: null, viewing: null, tradeoff: null, example: null });
  loadVersions();
  api<Example>(`/api/sessions/${sid()}/plan/example`).then(e => current() && set({ example: e })).catch(() => {});
  api<Tradeoff>(`/api/sessions/${sid()}/tradeoff`).then(t => current() && set({ tradeoff: t })).catch(() => {});
}
export const makePlan = (body: { scenario_id?: string; custom?: unknown }, choice: string) => busy("plan", async () => {
  set({ receiverChoice: choice, compare: null });
  set({ plan: await api<PlanView>(`/api/sessions/${sid()}/plan`, { body }) }); planLoaded(); return true;
});
export const changeColumn = (table: string, column: string, technique: string, params: Record<string, unknown>) => busy("plan", async () => {
  set({ plan: await api<PlanView>(`/api/sessions/${sid()}/plan/action`, { body: { table, column, technique, params } }) }); planLoaded();
});
export const setK = (k: number) => busy("tradeoff", async () => {
  set({ plan: await api<PlanView>(`/api/sessions/${sid()}/plan/k`, { body: { k } }) }); planLoaded();
});
// ---------------------------------------------------------------- plan versions
export const loadVersions = () => api<PlanVersions>(`/api/sessions/${sid()}/plan/versions`).then(versions => set({ versions })).catch(() => {});
export const planYaml = (version?: number) => api<{ yaml: string }>(`/api/sessions/${sid()}/plan/yaml${version ? `?version=${version}` : ""}`).then(r => r.yaml);
export const comparePlans = (a: number, b: number) => api<PlanCompare>(`/api/sessions/${sid()}/plan/compare?a=${a}&b=${b}`);
export const useVersion = (version: number) => busy("plan", async () => {
  set({ plan: await api<PlanView>(`/api/sessions/${sid()}/plan/versions/${version}/restore`, { method: "POST" }) }); planLoaded();
  const p = useApp.getState().plan!.plan;
  toast.success(`Version ${version} is the plan again.`, { description: p.approved ? `It was approved by ${p.approved_by}: you can create a release from it.` : "Approve it before releasing." });
  return true;
});
export const loadCompare = () => busy("compare", async () => {
  set({ compare: await api<Compare>(`/api/sessions/${sid()}/compare`, { body: { scenario_ids: useApp.getState().cat!.receivers.map(r => r.id) } }) });
});

// ---------------------------------------------------------------- approve and release
export const approve = (by: string, confirmReview: boolean) => busy("approve", async () => {
  set({ plan: await api<PlanView>(`/api/sessions/${sid()}/approve`, { body: { by, confirm_review: confirmReview } }) }); loadVersions();
  toast.success(`Approved by ${useApp.getState().plan!.plan.approved_by}.`); return true;
});
export const createRelease = (receiver: string) => busy("run", async () => {
  set({ results: await api<Results>(`/api/sessions/${sid()}/run`, { body: { receiver } }), viewing: null, step: "release" });
  await refreshHistory(); await refreshSessions(); loadVersions(); play("release");
  toast.success(`Release ${useApp.getState().results!.release_id} created.`); return true;
});
export const viewRelease = (id: string) => busy("view", async () => {
  set({ results: await api<Results>(`/api/sessions/${sid()}/releases/${encodeURIComponent(id)}`), viewing: useApp.getState().history[0]?.release_id === id ? null : id });
  window.scrollTo(0, 0);
});
export const fetchRelease = (id: string) => api<Results>(`/api/sessions/${sid()}/releases/${encodeURIComponent(id)}`);
export const releaseHref = (id: string) => `/api/sessions/${sid()}/releases/${encodeURIComponent(id)}/release.zip`;
export const downloadRelease = (id: string) => busy("download", async () => {
  await download(releaseHref(id));
  const r = useApp.getState().results; if (r) set({ results: { ...r, published: true } });
});
/** Download the open release; publishing statistics spends privacy budget, so the first time asks first. */
export function askDownload() {
  const r = useApp.getState().results;
  if (!r) return;
  if (r.summary.epsilon != null && !r.published) set({ publishAsk: true });
  else downloadRelease(r.release_id);
}
export const planHref = () => `/api/sessions/${sid()}/download/plan.yaml`;
export const detectionHref = () => `/api/sessions/${sid()}/download/detection.json`;
