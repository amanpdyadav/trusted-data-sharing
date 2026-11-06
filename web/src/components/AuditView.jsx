import { useEffect, useState } from "react";
import { fmt, getJSON, pct } from "../api.js";
import { AttackBars, PoolHistogram, UtilityBars } from "./charts.jsx";

const SCORE_KEYS = [
  ["privacy", "Privacy"],
  ["utility", "Utility"],
  ["composite", "Composite"],
];

export default function AuditView() {
  const [a, setA] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    getJSON("/api/audit/health").then((d) => live && setA(d)).catch((e) => live && setError(e));
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="wrap">
      <header>
        <div className="eyebrow">Beyond Syntax · release audit</div>
        <h1>Release audit · HEALTH-S1</h1>
        <p className="lede">
          {a
            ? `${a.release.recipient}. Purpose: ${a.release.purpose}.`
            : "Who the release is for, what was done to each column, how it was measured, and what risk is left."}
        </p>
        <div className="tags">
          <span className="tag">Scores are the pets-eval self-assessment, not the official judging score</span>
          <span className="tag">Synthetic data</span>
        </div>
      </header>

      {error && (
        <div className="card error" role="alert">
          <h2>Can’t load the audit</h2>
          <p className="how">{String(error.message || error)}</p>
          <p className="how">
            Start the API with <code>.venv/bin/uvicorn api.main:app --port 8000</code> and build the release with{" "}
            <code>.venv/bin/python scripts/build_health_s1.py</code>.
          </p>
        </div>
      )}
      {!error && !a && (
        <div className="card loading" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p className="how">Replaying every post and news clip against the release. This takes about 20 seconds the first time.</p>
        </div>
      )}
      {a && <Audit a={a} />}
    </div>
  );
}

function Audit({ a }) {
  const failing = a.checks.filter((c) => !c.pass);
  const r = a.release;
  const kb = a.k_anonymity.before;
  const ka = a.k_anonymity.after;
  return (
    <>
      {failing.length > 0 && (
        <div className="callout risk" role="status">
          <b>
            {failing.length} of {a.checks.length} checks {failing.length === 1 ? "fails" : "fail"}.
          </b>{" "}
          {failing.map((c) => `${c.name}: ${c.detail}.`).join(" ")}
        </div>
      )}

      <div className="audit-top">
        <section className="card">
          <h3 className="card-title">The release</h3>
          <dl className="facts">
            {[
              ["Scenario", r.id],
              ["Recipient", r.recipient],
              ["Purpose", r.purpose],
              ["Trust level", (r.trust_level || "").replace(/_/g, " ")],
              ["Built", r.created_utc ? new Date(r.created_utc).toLocaleString("en-GB") : "–"],
              ["Visits in → out", `${fmt(r.rows_in)} → ${fmt(r.rows_out)}`],
              ["Lab results", fmt(r.lab_rows)],
              ["k-anonymity", `k ≥ ${r.k} on ${r.qis.join(", ")}`],
              ["To reach k", Object.entries(r.k_enforcement || {}).map(([k, v]) => `${k}: ${fmt(v)}`).join(" · ")],
            ].map(([k, v]) => (
              <div className="fact" key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="card">
          <h3 className="card-title">Scores, ours vs baseline B2-k</h3>
          <div className="tiles">
            {SCORE_KEYS.map(([k, label]) => (
              <div className="tile" key={k}>
                <span className="tile-k">{label}</span>
                <span className="tile-v">{a.scores[k]?.toFixed(2)}</span>
                <span className="tile-b">baseline {a.baseline ? a.baseline[k]?.toFixed(2) : "–"}</span>
              </div>
            ))}
          </div>
          <p className="note">{a.scores.method}</p>
        </section>
      </div>

      <section className="card">
        <h3 className="card-title">Checks</h3>
        <ul className="checks">
          {[...a.checks].sort((x, y) => Number(x.pass) - Number(y.pass)).map((c) => (
            <li key={c.name} className={c.pass ? "" : "fail"}>
              <span className={`pill ${c.pass ? "ok" : "risk"}`}>{c.pass ? "pass" : "fail"}</span>
              <div>
                <div className="check-name">{c.name}</div>
                <div className="check-detail">{c.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="two">
        <section className="card">
          <h3 className="card-title">Official linkage attacks</h3>
          <p className="note">Share of targets re-identified by each attacker in the challenge pack.</p>
          <AttackBars attacks={a.attacks} />
        </section>
        <section className="card">
          <h3 className="card-title">One post or clip against our release</h3>
          <p className="note">
            {fmt(a.scrap_attack.tested)} scraps replayed ({fmt(a.scrap_attack.posts)} posts, {fmt(a.scrap_attack.news)} news
            clips). None narrows it to one visit; {fmt(a.scrap_attack.pool_2_4)} narrow it to 2–4, and{" "}
            {fmt(a.scrap_attack.pool_2_4_with_truth)} of those contain the real person. Median group:{" "}
            {fmt(a.scrap_attack.median_pool)}.
          </p>
          <PoolHistogram histogram={a.scrap_attack.histogram} />
        </section>
      </div>

      <div className="two">
        <section className="card">
          <h3 className="card-title">k-anonymity before and after</h3>
          <div className="tbl">
            <table>
              <thead>
                <tr>
                  <th />
                  <th>Before</th>
                  <th>After</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Quasi-identifiers", kb.qis.join(", "), ka.qis.join(", ")],
                  ["Rows", fmt(kb.n), fmt(ka.n)],
                  ["Groups", fmt(kb.n_classes), fmt(ka.n_classes)],
                  ["Smallest group", fmt(kb.min_k), fmt(ka.min_k)],
                  ["Median group", fmt(kb.median_k), fmt(ka.median_k)],
                  ["Rows in groups under 5", pct(kb.share_below["k<5"]), pct(ka.share_below["k<5"])],
                  ["Unique rows", pct(kb.sample_uniqueness, 1), pct(ka.sample_uniqueness, 1)],
                ].map(([k, b, f]) => (
                  <tr key={k}>
                    <th scope="row">{k}</th>
                    <td className="num">{b}</td>
                    <td className="num">{f}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {a.l_diversity?.evaluated && (
            <p className="note">
              l-diversity on {a.l_diversity.sensitive}: at least {a.l_diversity.min_distinct_l} distinct values in every group.
            </p>
          )}
        </section>
        <section className="card">
          <h3 className="card-title">Utility tasks</h3>
          <p className="note">What the research group needs, scored from 0 to 1 against the original data.</p>
          <UtilityBars tasks={a.utility} />
        </section>
      </div>

      <section className="card">
        <h3 className="card-title">What we did to each column, and why</h3>
        <div className="tbl">
          <table>
            <thead>
              <tr>
                <th>Column</th>
                <th>Technique</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {a.decisions.map((d) => (
                <tr key={d.column}>
                  <td className="mono">{d.column}</td>
                  <td>{d.technique}</td>
                  <td>{d.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3 className="card-title">Released files</h3>
        <div className="tbl">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Rows</th>
                <th>Size</th>
                <th>SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {a.files.map((f) => (
                <tr key={f.name}>
                  <td className="mono">{f.name}</td>
                  <td className="num">{fmt(f.rows)}</td>
                  <td className="num">{f.bytes ? `${(f.bytes / 1e6).toFixed(1)} MB` : "–"}</td>
                  <td className="mono hash" title={f.sha256}>
                    {f.sha256.slice(0, 16)}…{f.sha256.slice(-6)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">Row maps and the pseudonym key are never part of the release.</p>
      </section>

      <section className="card">
        <h3 className="card-title">Risks we still carry</h3>
        <ul className="risks">
          {a.residual_risks.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
