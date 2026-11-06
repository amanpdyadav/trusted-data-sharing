"""Mosaic attack: from one public scrap (a post or a news clip) to a full profile, in three modes.

Follows the team's problem demo page (case picker, chain rail, step card with funnel, attacker dossier,
lessons) and adds a third mode, "Our release". All data comes from the PETs Transformer API. Synthetic data.
"""
import html
import math
import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api_client import cached  # noqa: E402

st.set_page_config(page_title="Mosaic attack · PETs Transformer", layout="wide")

MODE_LABELS = {"raw": "Raw data shared", "names": "Names removed", "ours": "Our release"}
KIND = {"public": ("public", "public"), "leaked": ("if shared", "leaked"), "release": ("release", "leaked")}
esc = html.escape

st.markdown("""
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@100,600;100,800;125,800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root { --bg:#EDF0F3; --surface:#FAFBFC; --ink:#0F1B26; --muted:#4E5D6A; --line:#D2D9E0; --risk:#B93E0B; --risk-soft:#FBE7DC;
  --safe:#1F4FCF; --safe-soft:#E1E9FB; --ok:#1E7A4C; --ok-soft:#DDF1E6;
  --display:"Archivo","Arial Narrow",Arial,sans-serif; --body:"IBM Plex Sans","Segoe UI",Arial,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace; }
.stApp { background: var(--bg); }
.block-container { max-width: 1180px; padding-top: 2.2rem; }
.stApp, .stMarkdown { font-family: var(--body); color: var(--ink); }
.eyebrow { font: 600 13px/1 var(--body); letter-spacing: .14em; text-transform: uppercase; color: var(--risk); }
.h1 { font: 800 clamp(34px, 5vw, 58px)/1.02 var(--display); font-stretch: 125%; letter-spacing: -.01em; margin: 10px 0 12px; text-wrap: balance; }
.lede { color: var(--muted); font-size: 18px; max-width: 64ch; margin: 0; }
.tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.tag { font: 500 12px/1 var(--mono); padding: 7px 10px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); }
.tag.ok { color: var(--ok); border-color: currentColor; } .tag.risk { color: var(--risk); border-color: currentColor; }
.rail-scroll { overflow-x: auto; padding: 4px 4px 6px; }
.rail { display: flex; align-items: stretch; min-width: 720px; }
.node { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; padding: 12px; border: 1px solid var(--line);
  border-radius: 12px; background: var(--surface); color: var(--muted); }
.node .k { font: 500 11px/1 var(--mono); text-transform: uppercase; letter-spacing: .08em; }
.node .n { font: 600 14px/1.25 var(--body); color: var(--ink); }
.node.done { border-color: var(--risk); background: var(--risk-soft); } .node.done .k { color: var(--risk); }
.node.current { outline: 2px solid var(--risk); outline-offset: 2px; }
.node.safe { border-color: var(--ok); background: var(--ok-soft); } .node.safe .k { color: var(--ok); }
.node.cut { opacity: .45; border-style: dashed; }
.link { width: 26px; flex: none; align-self: center; height: 2px; background: var(--line); position: relative; }
.link.on { background: var(--risk); }
.link.on::after { content: ""; position: absolute; right: -1px; top: -4px; border: 5px solid transparent; border-left-color: var(--risk); border-right: 0; }
.link.broken { background: repeating-linear-gradient(90deg, var(--ok) 0 4px, transparent 4px 8px); }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 24px; min-width: 0; }
.card h2 { font: 800 28px/1.1 var(--display); margin: 6px 0 4px; text-wrap: balance; padding: 0; }
.file { font: 400 13px var(--mono); color: var(--muted); overflow-wrap: anywhere; }
.how { margin: 14px 0 18px; }
.kind { display: inline-block; font: 600 11px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; padding: 5px 8px; border-radius: 6px; }
.kind.public { background: var(--safe-soft); color: var(--safe); } .kind.leaked { background: var(--risk-soft); color: var(--risk); }
.kind.ok { background: var(--ok-soft); color: var(--ok); }
.check { font: 500 12px var(--mono); color: var(--ok); margin-left: 8px; }
.post { border-left: 3px solid var(--risk); padding: 6px 0 6px 16px; margin: 12px 0 0; }
.post .who { font-weight: 600; } .post .when { font: 400 13px var(--mono); color: var(--muted); }
.post blockquote { margin: 8px 0 0; font-size: 20px; line-height: 1.4; border: 0; padding: 0; color: var(--ink); }
.funnel { display: flex; flex-direction: column; gap: 10px; }
.frow { display: grid; grid-template-columns: minmax(0, 1fr) 72px; gap: 4px 12px; align-items: center; }
.flabel { font-size: 14px; color: var(--muted); grid-column: 1 / -1; }
.ftrack { height: 14px; background: var(--bg); border-radius: 4px; overflow: hidden; }
.ffill { height: 100%; background: var(--muted); border-radius: 4px; transition: width .5s ease; }
.frow:last-child .ffill { background: var(--risk); }
.fnum { font: 500 15px var(--mono); text-align: right; font-variant-numeric: tabular-nums; }
.frow:last-child .fnum { color: var(--risk); font-weight: 600; }
.funnel.safe .frow:last-child .ffill { background: var(--ok); } .funnel.safe .frow:last-child .fnum { color: var(--ok); }
.verdict { margin-top: 18px; padding: 12px 14px; border-radius: 10px; background: var(--risk-soft); font-weight: 500; }
.verdict.safe { background: var(--ok-soft); }
.dossier h3 { font: 600 13px/1 var(--body); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin: 0 0 14px; padding: 0; }
.dossier .who { font: 800 26px/1.1 var(--display); margin: 0 0 16px; } .dossier .who.unknown { color: var(--muted); }
.facts { display: flex; flex-direction: column; margin: 0; }
.fact { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 12px; padding: 9px 0; border-top: 1px solid var(--line); }
.fact dt { font-size: 13px; color: var(--muted); } .fact dd { margin: 0; font-size: 15px; overflow-wrap: anywhere; }
.fact .src { display: block; font: 400 11px var(--mono); color: var(--muted); margin-top: 2px; }
.fact.new { animation: flash 1.2s ease; } @keyframes flash { from { background: var(--risk-soft); } to { background: transparent; } }
.lessons { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
@media (max-width: 860px) { .lessons { grid-template-columns: 1fr; } }
.lesson { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 20px; }
.lesson h3 { font: 800 19px/1.2 var(--display); margin: 0 0 8px; padding: 0; } .lesson p { margin: 0; color: var(--muted); font-size: 15px; }
.section-title { font: 800 26px/1.1 var(--display); margin: 8px 0 0; }
.foot { font-size: 13px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 16px; }
div[data-testid="stButton"] button[kind="secondary"] { background: var(--surface); }
div[data-testid="stButton"] button p { white-space: normal; text-align: left; overflow: visible; text-overflow: clip; }
div[data-testid="stButton"] button div { overflow: visible; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
</style>""", unsafe_allow_html=True)

summary = cached("/api/summary")
cases = cached("/api/cases?limit=200")
p, n = summary["post"], summary["news"]

st.markdown(f"""
<div class="eyebrow">Beyond Syntax · mosaic attack</div>
<div class="h1">From one public scrap to a full profile</div>
<p class="lede">Start from a social post or a news clip. Step through how an attacker reaches diagnosis, home, income and
employer. Then switch the mode to see what names removed does, and what our release does.</p>
<div class="tags">
  <span class="tag risk">{p['one_patient']} of {p['tested']} posts → one patient</span>
  <span class="tag risk">{n['one_patient']} of {n['tested']} news clips → one patient</span>
  <span class="tag ok">Every link verified against ground truth</span>
  <span class="tag">Identifiers partly masked</span>
  <span class="tag">Synthetic data · TrustED PETs Proving Ground 2026</span>
</div>""", unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- case picker
ss = st.session_state
ss.setdefault("case", cases[0]["id"])
ss.setdefault("mode", "raw")
ss.setdefault("cur", 0)
ss.setdefault("playing", False)


def pick(case_id):
    ss.case, ss.cur, ss.playing = case_id, 0, False


featured = [c for c in cases if c["featured"]]
fcols = st.columns(len(featured))
for col, c in zip(fcols, featured):
    data = cached(f"/api/cases/{c['id']}")
    with col:
        st.button(f"**{data['kicker']} · {data['title']}**  \n{data['desc']}", key=f"pick-{c['id']}", width="stretch",
                  type="primary" if ss.case == c["id"] else "secondary", on_click=pick, args=(c["id"],))
others = {c["id"]: c["label"] for c in cases}
choice = st.selectbox("More cases", list(others), index=list(others).index(ss.case), format_func=lambda i: f"{i} · {others[i]}")
if choice != ss.case:
    pick(choice)
    st.rerun()

case = cached(f"/api/cases/{ss.case}")
modes = [m for m in MODE_LABELS if m in case["modes"]]
if ss.mode not in modes:
    ss.mode = modes[0]

# ---------------------------------------------------------------- controls
c1, c2 = st.columns([3, 2])
with c1:
    new_mode = st.segmented_control("Mode", modes, format_func=MODE_LABELS.get, default=ss.mode,
                                    label_visibility="collapsed", key=f"mode-{ss.case}")
    if new_mode and new_mode != ss.mode:
        ss.mode, ss.cur, ss.playing = new_mode, 0, False
        st.rerun()
steps = case["modes"][ss.mode] if ss.mode != "ours" else None
last = len(steps) - 1 if steps else 0
with c2:
    nav = st.container(horizontal=True, horizontal_alignment="right")
    if nav.button("Back", disabled=ss.mode == "ours" or ss.cur == 0):
        ss.cur, ss.playing = ss.cur - 1, False
        st.rerun()
    if nav.button("Next link", type="primary", disabled=ss.mode == "ours" or ss.cur >= last):
        ss.cur += 1
        st.rerun()
    if nav.button("Stop" if ss.playing else "Play all", disabled=ss.mode == "ours"):
        ss.playing = not ss.playing
        if ss.playing and ss.cur >= last:
            ss.cur = 0
        st.rerun()


# ---------------------------------------------------------------- rendering helpers
def rail_html(chain, cur, ours=False):
    out = []
    for i, s in enumerate(chain):
        if i:
            cls = "link broken" if ours and i == 1 else ("link on" if (not ours and i <= cur) else "link")
            out.append(f'<div class="{cls}"></div>')
        k = KIND.get(s["kind"], ("", ""))[0]
        if ours:
            cls = "node safe current" if i == 0 else "node cut"
        else:
            cls = "node" + (" done" if i <= cur else "") + (" current" if i == cur else "")
        out.append(f'<div class="{cls}"><span class="k">{esc(k)}</span><span class="n">{esc(s["dataset"])}</span></div>')
    return f'<div class="rail-scroll"><div class="rail">{"".join(out)}</div></div>'


def funnel_html(f, safe=False):
    top = math.log10(f[0][1] + 1)
    rows = "".join(
        f'<div class="frow"><span class="flabel">{esc(lab)}</span><div class="ftrack"><div class="ffill" '
        f'style="width:{max(2, 100 * math.log10(v + 1) / top):.1f}%"></div></div><span class="fnum">{v:,}</span></div>'
        for lab, v in f)
    return f'<div class="funnel{" safe" if safe else ""}">{rows}</div>'


def quote_html(q):
    return (f'<div class="post"><div class="who">{esc(q["who"])}</div><div class="when">{esc(q["when"])}</div>'
            f'<blockquote>{esc(q["text"])}</blockquote></div>')


def step_html(s):
    label, cls = KIND.get(s["kind"], ("", ""))
    check = '<span class="check">✓ verified against ground truth</span>' if s.get("verified") else ""
    body = quote_html(s["quote"]) if s.get("quote") else funnel_html(s["funnel"]) if s["funnel"] else ""
    return (f'<div class="card"><span class="kind {cls}">{esc(label)}</span>{check}<h2>{esc(s["title"])}</h2>'
            f'<div class="file">{esc(s["file"])}</div><p class="how">{esc(s["how"])}</p>{body}</div>')


def dossier_html(chain, cur, who):
    facts, seen = [], set()
    for i, s in enumerate(chain[:cur + 1]):
        for k, v in s["revealed"].items():
            if k in seen:
                continue
            seen.add(k)
            new = " new" if i == cur else ""
            facts.append(f'<div class="fact{new}"><dt>{esc(k)}</dt><dd>{esc(v)}<span class="src">{esc(s["dataset"])}</span></dd></div>')
    name = next((s["revealed"].get("Name") for s in chain[:cur + 1] if s["revealed"].get("Name")), None)
    who_html = f'<p class="who">{esc(name)}</p>' if name else '<p class="who unknown">Unknown person</p>'
    return f'<div class="card dossier"><h3>What the attacker now knows</h3>{who_html}<dl class="facts">{"".join(facts)}</dl></div>'


# ---------------------------------------------------------------- board
board = st.empty()


def draw():
    with board.container():
        if ss.mode == "ours":
            o = case["modes"]["ours"]
            chain = case["modes"].get("names") or case["modes"]["raw"]
            st.markdown(rail_html(chain, 0, ours=True), unsafe_allow_html=True)
            left, right = st.columns([1.35, 1], gap="medium")
            with left:
                st.markdown(
                    f'<div class="card"><span class="kind ok">our release</span><h2>Same scrap, our HEALTH-S1 release</h2>'
                    f'<div class="file">outputs/health/ed_visits.csv</div><p class="how">Arrival hour only, no date. No sex, '
                    f'birth date, postcode or name. Small towns merged. Keyed pseudonym per release.</p>'
                    f'{funnel_html(o["funnel"], safe=o["holds"])}'
                    f'<div class="verdict{" safe" if o["holds"] else ""}">{esc(o["verdict"])}</div></div>', unsafe_allow_html=True)
            with right:
                facts = "".join(f'<div class="fact"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in o["revealed"].items())
                st.markdown(f'<div class="card dossier"><h3>What the attacker now knows</h3><p class="who unknown">'
                            f'{o["candidates"]:,} possible visits</p><dl class="facts">{facts}</dl></div>', unsafe_allow_html=True)
            return
        chain = case["modes"][ss.mode]
        cur = min(ss.cur, len(chain) - 1)
        st.markdown(rail_html(chain, cur), unsafe_allow_html=True)
        left, right = st.columns([1.35, 1], gap="medium")
        left.markdown(step_html(chain[cur]), unsafe_allow_html=True)
        right.markdown(dossier_html(chain, cur, case.get("person")), unsafe_allow_html=True)


draw()
if ss.playing and steps:
    if ss.cur < last:
        time.sleep(1.8)
        ss.cur += 1
        st.rerun()
    else:
        ss.playing = False

# ---------------------------------------------------------------- lessons
st.markdown(f"""
<p class="section-title">What this means for our build</p>
<div class="lessons">
  <div class="lesson"><h3>Names are the least of it</h3><p>With names removed, a few clues (time, town, sex, age, symptoms,
  length of stay) still single out one patient for {p['one_patient']} of {p['tested']} posts and {n['one_patient']} of
  {n['tested']} news clips. Quasi-identifiers must be protected together.</p></div>
  <div class="lesson"><h3>Measure against what attackers know</h3><p>Our audit replays every post and news clip against the
  release and reports the smallest group each one reaches, with the real person checked against ground truth.</p></div>
  <div class="lesson"><h3>Every release, its own protection</h3><p>Birth date + postcode joins the hospital to the bank, energy,
  transport and school data. Our release drops both and keys its pseudonym per release, so releases can't be joined.</p></div>
</div>
<p class="foot">Computed live by <code>pets/reid_chain.py</code> and <code>pets/mosaic.py</code> through the PETs Transformer API.
Ground-truth files are read only to confirm each match. "Names removed" means every organisation drops names, ID codes,
phones and street addresses. "Our release" is <code>outputs/health</code> built by <code>scripts/build_health_s1.py</code>.</p>
""", unsafe_allow_html=True)
