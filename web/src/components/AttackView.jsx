import { useCallback, useEffect, useMemo, useState } from "react";
import { fmt, getJSON } from "../api.js";
import ChainRail from "./ChainRail.jsx";
import Funnel from "./Funnel.jsx";

const MODES = [
  { id: "raw", label: "Raw data shared" },
  { id: "names", label: "Names removed" },
  { id: "ours", label: "Our release" },
];
const KIND = {
  public: { cls: "public", rail: "public", card: "public source" },
  leaked: { cls: "leaked", rail: "if shared", card: "dataset, if shared raw" },
  release: { cls: "leaked", rail: "names removed", card: "release, names removed" },
};
const PLAY_MS = 1800;

function ApiError({ error }) {
  return (
    <div className="card error" role="alert">
      <h2>Can’t reach the API</h2>
      <p className="how">{String(error.message || error)}</p>
      <p className="how">
        Start it from the repo root with <code>.venv/bin/uvicorn api.main:app --port 8000</code>, then reload.
      </p>
    </div>
  );
}

export default function AttackView() {
  const [summary, setSummary] = useState(null);
  const [list, setList] = useState(null);
  const [featured, setFeatured] = useState([]);
  const [caseId, setCaseId] = useState(null);
  const [cases, setCases] = useState({});
  const [mode, setMode] = useState("raw");
  const [cur, setCur] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [flash, setFlash] = useState(false);
  const [error, setError] = useState(null);

  // Load the summary, the case list and the featured cases once.
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [s, l] = await Promise.all([getJSON("/api/summary"), getJSON("/api/cases?limit=60")]);
        if (!live) return;
        setSummary(s);
        setList(l);
        const feat = l.filter((c) => c.featured);
        const full = await Promise.all(feat.map((c) => getJSON(`/api/cases/${c.id}`)));
        if (!live) return;
        setFeatured(full);
        setCases(Object.fromEntries(full.map((c) => [c.id, c])));
        if (full.length) pickCase(full[0]);
      } catch (e) {
        if (live) setError(e);
      }
    })();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const C = caseId ? cases[caseId] : null;
  const steps = useMemo(() => {
    if (!C) return [];
    if (mode === "ours") return C.modes.names || C.modes.raw || [];
    return C.modes[mode] || [];
  }, [C, mode]);

  const stop = useCallback(() => setPlaying(false), []);

  function pickCase(c) {
    stop();
    const m = c.modes.raw ? "raw" : "names";
    setMode(m);
    setCaseId(c.id);
    setCur((c.modes[m] || []).length - 1);
    setFlash(false);
  }

  async function pickById(id) {
    stop();
    if (cases[id]) return pickCase(cases[id]);
    try {
      const c = await getJSON(`/api/cases/${id}`);
      setCases((prev) => ({ ...prev, [id]: c }));
      pickCase(c);
    } catch (e) {
      setError(e);
    }
  }

  function chooseMode(m) {
    stop();
    if (!C || (m !== "ours" && !C.modes[m]) || (m === "ours" && !C.modes.ours)) return;
    setMode(m);
    setFlash(true);
    if (m !== "ours") setCur(C.modes[m].length - 1);
  }

  const next = useCallback(() => {
    stop();
    if (mode === "ours" || cur >= steps.length - 1) return;
    setFlash(true);
    setCur(cur + 1);
  }, [mode, cur, steps.length, stop]);

  const prev = useCallback(() => {
    stop();
    if (mode === "ours" || cur === 0) return;
    setFlash(false);
    setCur(cur - 1);
  }, [mode, cur, stop]);

  // Play all: advance one link every PLAY_MS until the end of the chain.
  useEffect(() => {
    if (!playing) return undefined;
    if (cur >= steps.length - 1) {
      setPlaying(false);
      return undefined;
    }
    const t = setTimeout(() => {
      setFlash(true);
      setCur((c) => c + 1);
    }, PLAY_MS);
    return () => clearTimeout(t);
  }, [playing, cur, steps.length]);

  function play() {
    if (playing) return stop();
    if (!C) return;
    const m = mode === "ours" ? (C.modes.raw ? "raw" : "names") : mode;
    setMode(m);
    setCur(0);
    setFlash(true);
    setPlaying(true);
  }

  // ArrowLeft / ArrowRight step through the chain.
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      if (t && (t.tagName === "SELECT" || t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") prev();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [next, prev]);

  const onPickNode = useCallback(
    (i) => {
      stop();
      if (mode === "ours") {
        setMode(C && C.modes.raw ? "raw" : "names");
      }
      setFlash(true);
      setCur(i);
    },
    [mode, C, stop],
  );

  // Rail: in "ours" mode the chain breaks after the source, at our release.
  const rail = useMemo(() => {
    if (!steps.length) return { nodes: [], links: [] };
    if (mode === "ours") {
      const nodes = steps.map((s, i) => ({
        key: `${C.id}-${s.id}-${i}`,
        kicker: i === 0 ? KIND[s.kind].rail : i === 1 ? "our release" : "not reachable",
        label: i === 1 ? "Hospital ED, protected" : s.dataset,
        state: i === 0 ? "done" : i === 1 ? "safe" : "dim",
      }));
      const links = steps.slice(1).map((_, i) => ({ state: i === 0 ? "broken" : "off" }));
      return { nodes, links };
    }
    const nodes = steps.map((s, i) => ({
      key: `${C.id}-${s.id}-${i}`,
      kicker: KIND[s.kind]?.rail || s.kind,
      label: s.dataset,
      state: i < cur ? "done" : i === cur ? "current" : "idle",
    }));
    const links = steps.slice(1).map((_, i) => ({ state: i + 1 <= cur ? "on" : "off" }));
    return { nodes, links };
  }, [steps, mode, cur, C]);

  // Dossier: everything revealed up to the current step.
  const dossier = useMemo(() => {
    if (!C || !steps.length) return { who: "", known: false, facts: [] };
    if (mode === "ours") {
      const src = steps[0];
      const facts = [
        ...Object.entries(src.revealed).map(([k, v]) => ({ k, v, src: src.dataset, isNew: false })),
        ...Object.entries(C.modes.ours.revealed).map(([k, v]) => ({ k, v, src: "Our release", isNew: flash })),
      ];
      const named = src.revealed.Name;
      return { who: named || "Unknown person", known: Boolean(named), facts };
    }
    const upto = steps.slice(0, cur + 1);
    const facts = upto.flatMap((s, gi) =>
      Object.entries(s.revealed).map(([k, v]) => ({ k, v, src: s.dataset, isNew: flash && gi === upto.length - 1 })),
    );
    const nameStep = upto.find((s) => s.revealed && s.revealed.Name);
    const fallback = C.source === "news" ? "Unknown person" : steps[0].quote?.who || "Unknown person";
    return { who: nameStep ? nameStep.revealed.Name : fallback, known: Boolean(nameStep), facts };
  }, [C, steps, cur, mode, flash]);

  const step = steps[cur];
  const ours = C?.modes.ours;
  const sumTags = summary
    ? [
        `${fmt(summary.post?.one_patient)} of ${fmt(summary.post?.tested)} posts → one patient, verified`,
        `${fmt(summary.news?.one_patient)} of ${fmt(summary.news?.tested)} news clips → one patient, verified`,
      ]
    : [];

  return (
    <div className="wrap">
      <header>
        <div className="eyebrow">Beyond Syntax · mosaic attack</div>
        <h1>From one public scrap to a full profile</h1>
        <p className="lede">
          Pick a case and step through how an attacker reaches diagnosis, home, income and employer. Then switch to{" "}
          <b>Our release</b> to replay the same scrap against our protected hospital data.
        </p>
        <div className="tags">
          <span className="tag ok">Every link verified against ground truth</span>
          {sumTags.map((t) => (
            <span className="tag risk" key={t}>
              {t}
            </span>
          ))}
          <span className="tag">Synthetic data · TrustED PETs Proving Ground 2026</span>
          <span className="tag">Identifiers partly masked</span>
        </div>
      </header>

      {error && <ApiError error={error} />}
      {!error && !C && (
        <div className="card loading" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p className="how">
            Loading cases. The first request runs the attack on all 1,168 posts and news clips, which takes about 20
            seconds.
          </p>
        </div>
      )}

      {C && (
        <>
          <div className="cases" role="group" aria-label="Case">
            {featured.map((c, i) => (
              <button key={c.id} className="case" aria-pressed={caseId === c.id} onClick={() => pickCase(c)}>
                <span className="c-k">
                  Case {i + 1} · {c.kicker}
                </span>
                <span className="c-t">{c.title}</span>
                <span className="c-d">{c.desc}</span>
              </button>
            ))}
          </div>

          {list && (
            <div className="more">
              <label htmlFor="case-select">More cases</label>
              <select
                id="case-select"
                value={featured.some((f) => f.id === caseId) ? "" : caseId}
                onChange={(e) => e.target.value && pickById(e.target.value)}
              >
                <option value="">Choose another post or news clip…</option>
                {list
                  .filter((c) => !c.featured)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id} · {c.label}
                    </option>
                  ))}
              </select>
            </div>
          )}

          <div className="bar">
            <div className="seg" role="group" aria-label="What was shared">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  aria-pressed={mode === m.id}
                  className={m.id === "ours" ? "ours" : ""}
                  disabled={m.id === "ours" ? !C.modes.ours : !C.modes[m.id]}
                  onClick={() => chooseMode(m.id)}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <div className="nav">
              <button className="btn" onClick={prev} disabled={mode === "ours" || cur === 0}>
                Back
              </button>
              <button className="btn primary" onClick={next} disabled={mode === "ours" || cur >= steps.length - 1}>
                Next link
              </button>
              <button className="btn" onClick={play}>
                {playing ? "Stop" : "Play all"}
              </button>
            </div>
          </div>

          <ChainRail nodes={rail.nodes} links={rail.links} onPick={onPickNode} />

          <div className="board">
            <section className="card" aria-live="polite">
              {mode === "ours" && ours ? (
                <OursCard ours={ours} src={steps[0]} />
              ) : (
                step && <StepCard step={step} index={cur} />
              )}
            </section>
            <aside className="card dossier">
              <h3>What the attacker now knows</h3>
              <p className={`who${dossier.known ? "" : " unknown"}`}>{dossier.who}</p>
              <dl className="facts">
                {dossier.facts.map((f, i) => (
                  <div className={`fact${f.isNew ? " new" : ""}`} key={`${caseId}-${mode}-${cur}-${i}`}>
                    <dt>{f.k}</dt>
                    <dd>
                      {f.v}
                      <span className="src">{f.src}</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </aside>
          </div>
        </>
      )}

      <h2 className="section-title">What this means for our build</h2>
      <div className="lessons">
        <div className="lesson">
          <h3>Names are the least of it</h3>
          <p>
            With names removed, the clues in one post or clip still single out one verified patient
            {summary
              ? ` for ${fmt(summary.post.one_patient)} of ${fmt(summary.post.tested)} posts and ${fmt(
                  summary.news.one_patient,
                )} of ${fmt(summary.news.tested)} news clips`
              : ""}
            . Time, town, sex, age, symptoms and length of stay must be protected together.
          </p>
        </div>
        <div className="lesson">
          <h3>Measure against what attackers know</h3>
          <p>
            The <a href="#audit">release audit</a> replays all 1,168 posts and news clips against our release and{" "}
            shows how small a group each one can narrow it to, and where we still fall short.
          </p>
        </div>
        <div className="lesson">
          <h3>Every release, its own protection</h3>
          <p>
            Once a name is known, any unprotected dataset opens up. Each release gets its own plan and its own pseudonym
            key, so releases can’t be joined.
          </p>
        </div>
      </div>

      <p className="foot">
        Computed live by <code>pets/reid_chain.py</code> and <code>pets/mosaic.py</code> through the API, on the raw
        tables, the public adversary files and our HEALTH-S1 release (<code>outputs/health/ed_visits.csv</code>).
        Ground-truth files are read only to confirm each match. “Names removed” means every organisation drops names, ID
        codes, phones and addresses but keeps birth date and postcode.
      </p>
    </div>
  );
}

function Verified({ v }) {
  if (v === true) return <span className="badge ok">✓ verified against ground truth</span>;
  if (v === false) return <span className="badge risk">✗ wrong person (ground truth)</span>;
  return null;
}

function StepCard({ step, index }) {
  const k = KIND[step.kind] || KIND.leaked;
  const last = step.funnel.length ? step.funnel[step.funnel.length - 1][1] : null;
  return (
    <>
      <div className="card-head">
        <span className={`kind ${k.cls}`}>{k.card}</span>
        <Verified v={step.verified} />
      </div>
      <h2>
        {index}. {step.title}
      </h2>
      <div className="file">{step.file}</div>
      <p className="how">{step.how}</p>
      {step.quote ? (
        <div className="post">
          <div className="who">{step.quote.who}</div>
          <div className="when">{step.quote.when}</div>
          <blockquote>“{step.quote.text}”</blockquote>
        </div>
      ) : (
        <>
          <Funnel rows={step.funnel} tone="risk" />
          <div className="verdict">
            {last === 1 ? (
              <>
                <b>1 match</b> out of {fmt(step.rows_total)} rows. Link confirmed.
              </>
            ) : (
              <>
                <b>{fmt(last)} candidates</b> left out of {fmt(step.rows_total)} rows. The chain stops here.
              </>
            )}
          </div>
        </>
      )}
    </>
  );
}

function OursCard({ ours, src }) {
  return (
    <>
      <div className="card-head">
        <span className="kind safe">our release</span>
      </div>
      <h2>Same scrap, our protected hospital table</h2>
      <div className="file">outputs/health/ed_visits.csv</div>
      <p className="how">
        Date, sex, birth date, postcode and names are not released. Small towns are merged and age is in 10-year bands.
        The attacker still has everything in the {src?.dataset === "Local news" ? "news clip" : "post"}.
      </p>
      <Funnel rows={ours.funnel} tone={ours.holds ? "safe" : "risk"} />
      <div className={`verdict ${ours.holds ? "safe" : ""}`}>
        <b>{fmt(ours.candidates)}</b> {ours.candidates === 1 ? "visit fits" : "visits fit"}. {ours.verdict}
      </div>
    </>
  );
}
