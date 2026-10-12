"""TamangSahod on Streamlit Community Cloud.

Same calculators, rules and search as the FastAPI app: everything below the page
layout lives in app/forms.py. Run locally with `uv run streamlit run streamlit_app.py`.
"""

import re
from datetime import date

import streamlit as st

from app import calc, forms, search
from app.forms import FORMS

st.set_page_config(page_title="TamangSahod: payroll answers", page_icon="₱", layout="centered")


@st.cache_resource(show_spinner="Loading the rule search. The first visit after a quiet spell takes a minute.")
def ensure_index() -> None:
    if not (search.INDEX / "passages.lance").exists():
        search.build()


def peso(amount) -> str:
    return f"₱{amount:,.2f}"


def plain(text: str) -> str:
    """Show text as written: escape Markdown, keep line breaks."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!<>|~])", r"\\\1", text).replace("\n", "  \n")


def source_link(key: str, where: str = "") -> str:
    s = forms.SOURCES[key]
    page = f"#page={where[3:]}" if where.startswith("p. ") else ""
    return f"[{s['title']}]({s['url']}{page})"


# --- widgets <-> form strings -------------------------------------------------

def to_widget(f: forms.Field, value: str):
    if f.kind == "date":
        return date.fromisoformat(value) if value else None
    if f.kind == "check":
        return bool(value)
    return value


def from_widget(f: forms.Field, value) -> str | None:
    if f.kind == "date":
        return value.isoformat() if value else ""
    if f.kind == "check":
        return "on" if value else None  # absent when unticked, as in an HTML form
    return str(value or "")


def fill(topic: str, values: dict) -> None:
    for f in FORMS[topic].fields:
        st.session_state[f"{topic}.{f.name}"] = to_widget(f, values.get(f.name, ""))


def widget(topic: str, f: forms.Field) -> None:
    key = f"{topic}.{f.name}"
    if key not in st.session_state:
        st.session_state[key] = to_widget(f, forms.form_values(topic)[f.name])
    if f.kind == "date":
        st.date_input(f.label, key=key, format="YYYY-MM-DD")
    elif f.kind == "select":
        st.selectbox(f.label, [k for k, _ in f.options], format_func=dict(f.options).get, key=key)
    elif f.kind == "yesno":
        st.radio(f.label, ["yes", "no"], format_func=str.capitalize, horizontal=True, key=key)
    elif f.kind == "check":
        st.checkbox(f.label, key=key)
    else:
        st.text_input(f.label, key=key, placeholder="YYYY-MM" if f.kind == "month" else "")
    if f.hint:
        st.caption(f.hint)


def submitted(topic: str) -> dict:
    values = {}
    for f in FORMS[topic].fields:
        value = from_widget(f, st.session_state.get(f"{topic}.{f.name}"))
        if value is not None:
            values[f.name] = value
    return values


def show_result(result: calc.Result, heading: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{plain(heading)}**")
        st.markdown(f"# {peso(result.total)}")
        if result.parts:
            st.markdown(f"Deduct from pay **{peso(result.parts['employee'])}** · "
                        f"Employer adds **{peso(result.parts['employer'])}**")
        rows = "\n".join(f"| {plain(label)} | {peso(amount)} |" for label, amount in result.lines)
        st.markdown(f"| | |\n|:--|--:|\n{rows}")
        for note in result.notes:
            st.markdown(f"- {plain(note)}")
        st.caption("Rules used: " + "; ".join(source_link(k) for k in dict.fromkeys(result.sources)))


def show_passages(passages: list[dict]) -> None:
    for p in passages:
        with st.container(border=True):
            st.markdown(f"**{plain(p['title'])}**")
            st.markdown(plain(p["text"]))
            st.caption(f"Source: {source_link(p['source'], p['where'])}, {plain(p['where'])}")


def open_calculator(topic: str) -> None:
    st.session_state["topic"] = topic


# --- page -----------------------------------------------------------------------

st.title("Payroll answers you can check")
st.caption("For small businesses in the Philippines. Every amount shows the official rule it follows.")

with st.form("ask"):
    st.text_area("Ask a payroll question", key="question", max_chars=500,
                 placeholder="e.g. Magkano ang bayad kung pumasok sa Dec 30?")
    asked = st.form_submit_button("Ask", type="primary")

if asked and st.session_state.question.strip():
    question = st.session_state.question.strip()
    ensure_index()
    a = forms.answer(question)
    st.session_state["answer"] = (question, a)
    if a.topic:
        st.session_state["topic"] = a.topic
        fill(a.topic, a.values)

if "answer" in st.session_state:
    question, a = st.session_state["answer"]
    st.caption(f"You asked: “{plain(question)}”")
    if a.topic:
        st.info("We filled in what your question said. Check each field in the calculator below, then compute.")
        if a.passages:
            with st.expander("Related rules"):
                show_passages(a.passages)
    elif a.passages:
        st.subheader("What the rules say")
        st.caption("Quoted word for word from the official source.")
        show_passages(a.passages)
        for topic in a.topics:
            st.button(f"Work it out: {FORMS[topic].title}", on_click=open_calculator, args=(topic,), key=f"open-{topic}")
    else:
        st.warning("Not covered yet. TamangSahod answers 13th month pay, holiday pay, final pay and government "
                   "contributions. For anything else, call the DOLE hotline 1349.")

st.divider()
st.session_state.setdefault("topic", "thirteenth")
topic = st.radio("Calculator", list(FORMS), format_func=lambda t: FORMS[t].title, horizontal=True, key="topic")
form = FORMS[topic]
st.subheader(form.title)
st.caption(form.blurb)

with st.form(f"calc-{topic}"):
    for f in form.fields:
        if not f.more:
            widget(topic, f)
    if any(f.more for f in form.fields):
        with st.expander("More options"):
            for f in form.fields:
                if f.more:
                    widget(topic, f)
    go = st.form_submit_button("Compute", type="primary", use_container_width=True)

if go:
    try:
        result, heading = forms.compute(topic, submitted(topic))
    except (ValueError, calc.NotCovered) as e:
        st.error(str(e))
    else:
        show_result(result, heading)

st.divider()
st.caption("**A guide, not legal advice.** For your own case, call the DOLE hotline 1349. "
           "No login; what you type is not stored. Sources: "
           + "; ".join(f"[{s['title']}]({s['url']})" for s in forms.SOURCES.values()))
