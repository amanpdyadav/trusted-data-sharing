"""From one social post to a full profile: the re-identification chain across every dataset. Synthetic data.

Two views: a step-by-step presenter mode for the demo video (one clue per click, a link graph that lights up
as each dataset is joined) and an explorer with the full funnel, link table and dossier for any post.
"""
import math
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pets import reid_chain as rc  # noqa: E402

st.set_page_config(page_title="From one post · PETs Transformer", layout="wide")

RISK, SAFE, INK, MUTED, LINE = "#b4521a", "#0f6b5c", "#17201e", "#8a948f", "#d5dbd8"
st.markdown(f"""<style>
.block-container {{padding-top: 2rem; max-width: 1280px}}
.kicker {{font: 600 .75rem/1.3 ui-monospace, Menlo, monospace; letter-spacing: .1em; text-transform: uppercase; color: {RISK}}}
.kicker.safe {{color: {SAFE}}}
.step-title {{font-size: 1.9rem; font-weight: 700; line-height: 1.2; margin: .35rem 0 .5rem}}
.step-body {{font-size: 1.1rem; opacity: .8; max-width: 60ch}}
.bignum {{font-size: 4.2rem; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; color: {RISK}}}
.bignum.safe {{color: {SAFE}}}
.bignum-label {{color: {MUTED}; font-size: .95rem; margin-top: .2rem}}
.shrink {{height: 10px; background: rgba(127,127,127,.15); border-radius: 5px; overflow: hidden; margin: .8rem 0 .2rem; max-width: 34rem}}
.shrink > div {{height: 100%; background: {RISK}; border-radius: 5px; transition: width .6s ease}}
.shrink.safe > div {{background: {SAFE}}}
.post-card {{border: 1px solid {LINE}; border-radius: 14px; padding: 1.1rem 1.3rem; max-width: 34rem}}
.post-card .who {{font-weight: 700}} .post-card .who span {{color: {MUTED}; font-weight: 400}}
.post-card .txt {{font-size: 1.35rem; line-height: 1.4; margin: .4rem 0}}
.post-card .meta {{color: {MUTED}; font-size: .85rem}}
.dossier h4 {{font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: {MUTED}; margin: .9rem 0 .25rem; padding: 0}}
.chip {{display: inline-block; border: 1px solid {LINE}; border-radius: 999px; padding: .15rem .65rem; margin: 0 .3rem .35rem 0;
        font-size: .88rem}}
.chip.new {{border-color: {RISK}; background: rgba(180,82,26,.12); animation: pop .5s ease}}
@keyframes pop {{from {{transform: scale(.9); opacity: .3}} to {{transform: scale(1); opacity: 1}}}}
@media (prefers-reduced-motion: reduce) {{.chip.new {{animation: none}} .shrink > div {{transition: none}}}}
.identity {{font-size: 2.2rem; font-weight: 800; line-height: 1.1}}
.identity small {{display: block; font-size: 1rem; font-weight: 400; color: {MUTED}; margin-top: .3rem}}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Running the attack on all 948 posts…")
def survey() -> pd.DataFrame:
    return rc.survey()


@st.cache_data(show_spinner=False)
def chain(post_id: str):
    ch = rc.run_chain(post_id)
    return ch, rc.protected_funnel(ch)


s = survey()
posts = rc._load()["posts"].set_index("adv_row_id")
featured = s[s.correct].sort_values(["named", "datasets_joined", "steps"], ascending=False)
labels = {p: f"{p} · {posts.at[p, 'display_name'] or 'anonymous'}: {posts.at[p, 'text'][:60]}" for p in posts.index}

st.title("From one social post to a full profile")
st.caption("Every dataset is released the way most organisations do it: names, ID codes, phone numbers and street "
           "addresses removed. All people and data are synthetic.")

# ---------------------------------------------------------------- the story, as a list of steps
DATASETS = [("Bank", "bank"), ("Energy company", "energy"), ("Public transport", "transport"), ("School register", "school")]
LINK_TITLES = {"Bank": "The bank knows their money", "Energy company": "The energy company knows their home",
               "Public transport": "The travel card knows where they go",
               "School register": "The school register knows where they study"}


def _linked(ch) -> set[str]:
    return {node for name, node in DATASETS if next(l for l in ch.links if l["Dataset"] == name)["Matches"] == 1}


def build_story(ch, protected) -> list[dict]:
    """One dict per click: what is revealed, the candidate count and which graph nodes are lit."""
    steps = [{"kind": "post", "kicker": "The starting point", "title": "Someone posts from the emergency room",
              "body": "A public post with a name, a home town, a time and a symptom. Nothing a moderator would remove.",
              "lit": {"post"}, "facts": {}}]
    total = ch.funnel[0].candidates
    steps.append({"kind": "count", "kicker": "Hospital release · names removed", "title": "The hospital publishes its ED visits",
                  "body": "Names, ID codes, phone numbers and street addresses are removed. Birth date, sex, postcode, "
                          "arrival time and diagnosis stay in.",
                  "n": total, "total": total, "lit": {"post", "hospital"}, "facts": {}})
    for f in ch.funnel[1:]:
        steps.append({"kind": "count", "kicker": f"Clue from: {f.source}", "title": f.clue[0].upper() + f.clue[1:],
                      "body": "", "n": f.candidates, "total": total, "lit": {"post", "hospital"}, "facts": {}})
    v, h = ch.visit, ch.dossier["Health"]
    steps.append({"kind": "match", "kicker": "One patient left", "title": "The post is now a medical record",
                  "body": "This visit row was meant to be anonymous. It carries the birth date and postcode, which "
                          "most other organisations also hold.",
                  "lit": {"post", "hospital", "person"},
                  "facts": {"Health": [f"born {h['Birth date']}", {"F": "female", "M": "male"}.get(h["Sex"], h["Sex"]),
                                       f"postcode {h['Postcode']}", h["Diagnosis"], f"triage {h['Triage']}",
                                       ] + ([f"stayed {int(float(v['los_minutes']))} min"] if v["los_minutes"] else [])
                            + ([f"labs: {h['Lab tests']}"] if h["Lab tests"] != "none" else [])}})
    for name, node in DATASETS:
        if node not in _linked(ch):
            continue
        d = ch.dossier[name]
        steps.append({"kind": "link", "kicker": f"Join on birth date + postcode → {name}", "title": LINK_TITLES[name],
                      "body": f"Exactly one {name.lower()} record has the same birth date and postcode.",
                      "lit": {"post", "hospital", "person", node},
                      "facts": {name: [f"{k.lower()}: {val}" for k, val in d.items() if k not in ("Card number", "Meter ID")]}})
    if "Identity" in ch.dossier:
        i = ch.dossier["Identity"]
        steps.append({"kind": "identity", "kicker": "Public phone directory", "title": "And now they have a name",
                      "body": "The directory matches the name and postcode, and gives a street address.",
                      "lit": {"post", "hospital", "person", "directory"} | _linked(ch), "identity": i,
                      "facts": {"Identity": [i["Name"], i["Street address"], i["City"]]}})
    if protected:
        steps.append({"kind": "defence", "kicker": "Same post · our HEALTH-S1 release",
                      "title": "With our protection, the chain breaks at the first link",
                      "body": "Arrival hour only, no date. No sex, birth date or postcode. Small towns merged. "
                              "The attacker is left with a crowd and nothing to join to other datasets.",
                      "n": protected[-1].candidates, "total": protected[0].candidates, "lit": {"post", "ours"}, "facts": {}})
    seen: dict = {}  # facts accumulate; each step marks its own as new
    for step in steps:
        step["known"] = {k: [(x, False) for x in vals] for k, vals in seen.items()}
        for k, vals in step["facts"].items():
            step["known"].setdefault(k, []).extend((x, True) for x in vals)
            seen.setdefault(k, []).extend(vals)
        if step["kind"] == "defence":
            step["known"] = {}
    return steps


def graph(ch, step: dict) -> str:
    """DOT source for the link graph: lit nodes in colour, the rest waiting in grey."""
    lit, linked = step["lit"], _linked(ch)
    defence = step["kind"] == "defence"

    def node(key, label, colour=RISK):
        on = key in lit
        fill = ("#f8eadf" if colour == RISK else "#e2f0ec") if on else "#f4f6f5"
        return (f'{key} [label="{label}", shape=box, style="filled,rounded", fillcolor="{fill}", '
                f'color="{colour if on else LINE}", fontcolor="{INK if on else MUTED}", penwidth={2.2 if on else 1}];')

    def edge(a, b, label, on):
        return (f'{a} -> {b} [label="  {label}  ", color="{RISK if on else LINE}", fontcolor="{INK if on else MUTED}", '
                f'penwidth={2.2 if on else 1}, style={"solid" if on else "dashed"}];')

    who = ch.dossier.get("Identity", {}).get("Name", "?") if "directory" in lit else ("1 patient" if "person" in lit else "?")
    out = ['digraph G { rankdir=LR; bgcolor="transparent"; nodesep=0.3; ranksep=0.55;',
           'node [fontname="Helvetica", fontsize=15, margin="0.22,0.1"]; edge [fontname="Helvetica", fontsize=12, arrowsize=0.8];',
           node("post", "Social post"), node("hospital", "Hospital ED visits\\n(names removed)"),
           node("person", who), node("directory", "Phone directory")]
    names = {"bank": "Bank", "energy": "Energy company", "transport": "Travel card", "school": "School register"}
    out += [node(k, names[k]) for _, k in DATASETS if k in linked]
    out.append(edge("post", "hospital", "time · town · sex · symptoms", "hospital" in lit and not defence))
    out.append(edge("hospital", "person", "1 match", "person" in lit))
    out += [edge("person", k, "birth date + postcode", k in lit) for _, k in DATASETS if k in linked]
    out.append(edge("person", "directory", "name + postcode", "directory" in lit))
    if defence:
        out.append(node("ours", "Our release", SAFE))
        out.append(f'post -> ours [label="  {step["n"]:,} still fit  ", color="{SAFE}", fontcolor="{SAFE}", penwidth=2.2];')
    return "\n".join(out + ["}"])


def shrink_bar(n, total, safe=False):
    w = 100 * math.log10(max(n, 1) + 1) / math.log10(total + 1)
    return f'<div class="shrink{" safe" if safe else ""}"><div style="width:{max(w, 1.5):.1f}%"></div></div>'


def post_card(p):
    meta = [p["posted_ts"][:16]] + ([f"📍 {p['place_tag']}"] if p["place_tag"] else []) + \
           ([f"🏠 {p['profile_city']}"] if p["profile_city"] else [])
    return (f'<div class="post-card"><div class="who">{p["display_name"] or "anonymous"} <span>· @{p["handle"]} · '
            f'{p["platform"]}</span></div><div class="txt">{p["text"]}</div><div class="meta">{" · ".join(meta)}</div></div>')


def render_step(ch, step, i, n_steps):
    _render_columns(ch, step, i, n_steps)
    with st.container(border=True):
        st.caption("How the datasets link up")
        st.graphviz_chart(graph(ch, step), width="stretch")


def _render_columns(ch, step, i, n_steps):
    left, right = st.columns([5, 4], gap="large")
    with left:
        st.markdown(f'<div class="kicker{" safe" if step["kind"] == "defence" else ""}">Step {i + 1} of {n_steps} · '
                    f'{step["kicker"]}</div><div class="step-title">{step["title"]}</div>'
                    + (f'<div class="step-body">{step["body"]}</div>' if step["body"] else ""), unsafe_allow_html=True)
        st.write("")
        if step["kind"] == "post":
            st.markdown(post_card(ch.post), unsafe_allow_html=True)
        elif step["kind"] in ("count", "defence"):
            safe, n = step["kind"] == "defence", step["n"]
            word = ("visits still fit" if safe else "visits, names removed" if n == step["total"]
                    else "possible patient" if n == 1 else "possible patients")
            st.markdown(f'<div class="bignum{" safe" if safe else ""}">{n:,}</div><div class="bignum-label">{word} · '
                        f'out of {step["total"]:,}</div>' + shrink_bar(n, step["total"], safe), unsafe_allow_html=True)
        elif step["kind"] == "match":
            st.markdown(f'<div class="bignum">1</div><div class="bignum-label">patient · ground truth: '
                        f'{"✅ the right person" if ch.person_correct else "❌ the wrong person"}</div>', unsafe_allow_html=True)
        elif step["kind"] == "identity":
            i_ = step["identity"]
            st.markdown(f'<div class="identity">{i_["Name"]}<small>{i_["Street address"]}, {i_["City"]}</small></div>',
                        unsafe_allow_html=True)
    with right:
        if step["kind"] == "defence":
            st.markdown("**What the attacker knows from our release**")
            st.markdown(post_card(ch.post), unsafe_allow_html=True)
            st.caption("Still only the post. No single visit, no birth date or postcode to join on, no name.")
            return
        st.markdown("**What the attacker knows so far**")
        if not step["known"]:
            st.caption("Only the post. Click Next to start linking.")
            return
        html = '<div class="dossier">'
        for k in ["Identity", "Health", "Bank", "Energy company", "Public transport", "School register"]:
            if k in step["known"]:
                html += f"<h4>{k}</h4>" + "".join(f'<span class="chip{" new" if new else ""}">{x}</span>'
                                                  for x, new in step["known"][k])
        st.markdown(html + "</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- page
story_tab, explore_tab = st.tabs(["▶ Story (presenter mode)", "Explore any post"])

with story_tab:
    def reset_step():
        st.session_state.step = 0

    post_id = st.selectbox("Post", list(featured.post), format_func=labels.get, key="story_post",
                           on_change=reset_step, label_visibility="collapsed")
    ch, protected = chain(post_id)
    story = build_story(ch, protected)
    st.session_state.setdefault("step", 0)
    st.session_state.step = min(st.session_state.step, len(story) - 1)

    nav = st.container(horizontal=True)
    if nav.button("◀ Back", disabled=st.session_state.step == 0):
        st.session_state.step -= 1
        st.rerun()
    if nav.button("Next ▶", type="primary", disabled=st.session_state.step == len(story) - 1):
        st.session_state.step += 1
        st.rerun()
    if nav.button("↺ Restart"):
        st.session_state.step = 0
        st.rerun()
    st.progress((st.session_state.step + 1) / len(story))
    render_step(ch, story[st.session_state.step], st.session_state.step, len(story))

with explore_tab:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Public posts read", f"{len(s)}")
    m2.metric("Narrowed to exactly one patient", f"{s.correct.sum()}", f"{s.correct.mean():.0%} of posts, verified", delta_color="off")
    m3.metric("Linked to another organisation", f"{(s.correct & (s.datasets_joined > 0)).sum()}",
              "bank, energy, transport or school", delta_color="off")
    m4.metric("Name and home address found", f"{s.named.sum()}", "verified against ground truth", delta_color="off")

    c1, c2 = st.columns([3, 1])
    with c2:
        only_hits = st.toggle("Only posts that lead to a person", value=True)
    with c1:
        ex_id = st.selectbox("Pick a post", list(featured.post) if only_hits else list(posts.index), format_func=labels.get)
    ex, ex_prot = chain(ex_id)

    def funnel_fig(steps, colour):
        fig = go.Figure(go.Bar(x=[max(x.candidates, 1) for x in steps], y=list(range(len(steps))), orientation="h",
                               marker_color=colour, width=0.45, text=[f"<b>{x.candidates:,}</b>" for x in steps],
                               textposition="outside", cliponaxis=False, hovertext=[x.source for x in steps], hoverinfo="text+x"))
        for i, x in enumerate(steps):
            fig.add_annotation(x=0, xref="paper", y=i, yshift=17, text=f"{i + 1}. {x.clue}  <i>· {x.source}</i>",
                               showarrow=False, xanchor="left", font=dict(size=12))
        fig.update_layout(yaxis=dict(autorange="reversed", showticklabels=False, showgrid=False),
                          xaxis=dict(type="log", range=[-0.35, 5.1], tickvals=[1, 10, 100, 1000, 10000, 100000],
                                     ticktext=["1", "10", "100", "1k", "10k", "100k"], title="possible patients (log scale)"),
                          height=80 + 62 * len(steps), margin=dict(l=4, r=56, t=24, b=40), showlegend=False)
        return fig

    f1, f2 = st.columns(2)
    with f1:
        st.markdown("**Names-removed release**")
        st.plotly_chart(funnel_fig(ex.funnel, RISK), width="stretch")
        if ex.identified:
            st.error(f"Exactly one patient fits. Ground truth: {'✅ the right person' if ex.person_correct else '❌ the wrong person'}.")
        else:
            st.success(f"{ex.funnel[-1].candidates} patients still fit, so the attacker cannot pick one.")
    with f2:
        st.markdown("**Our HEALTH-S1 release**")
        if ex_prot:
            st.plotly_chart(funnel_fig(ex_prot, SAFE), width="stretch")
            st.success(f"{ex_prot[-1].candidates:,} visits still fit. Nothing to join to other datasets.")
        else:
            st.info("Build our release first: `.venv/bin/python scripts/build_health_s1.py`")
    if ex.identified:
        links = pd.DataFrame(ex.links)
        links["Result"] = links.Matches.map(lambda m: "no record" if m == 0 else (f"{m} candidates" if m > 1 else "1 person"))
        links["Ground truth"] = links.Correct.map({True: "✅ same person", False: "❌ different person"}).fillna("–")
        st.dataframe(links[["Dataset", "Joined on", "Result", "Ground truth"]], hide_index=True, width="stretch")
        note = ex.dossier["Health"].get("Doctor's note")
        if note and note != "none":
            with st.expander("Doctor's note for this visit (free text, released unredacted)"):
                st.text(note)

st.caption("Method: the attacker uses only the post, a public phone directory and first-name statistics, plus releases "
           "with direct identifiers removed. Arrival window 16 h before to 1 h after the post. The ground truth is used "
           "only to check each step, never for matching.")
