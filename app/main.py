"""TamangSahod web app (FastAPI): four payroll calculators and a question box.

Everything the owner types arrives in a POST body, so amounts and questions never
land in URLs, access logs or analytics. Forms and the question flow live in
app/forms.py, shared with the Streamlit front end.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import calc, forms
from app.forms import FORMS

HERE = Path(__file__).resolve().parent

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals.update(
    goatcounter=os.environ.get("GOATCOUNTER_CODE", ""),
    sources=forms.SOURCES,
    peso=lambda d: f"₱{d:,.2f}",
)


EXAMPLES = [
    "Magkano ang 13th month ng nag-resign noong June?",
    "Holiday pay kung pumasok sa Dec 30?",
    "SSS, PhilHealth at Pag-IBIG ng 20,000 na sweldo",
]


def render(request: Request, name: str, **context) -> HTMLResponse:
    context = {"holidays": forms.holiday_choices(), "months": forms.month_choices(), "steps": forms.steps,
               "examples": EXAMPLES, **context}
    return templates.TemplateResponse(request, name, context)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html", forms=FORMS)


@app.get("/calc/{topic}", response_class=HTMLResponse)
def calculator(request: Request, topic: str):
    if topic not in FORMS:
        return RedirectResponse("/", status_code=303)
    return render(request, "calc.html", topic=topic, form=FORMS[topic], values=forms.form_values(topic))


@app.post("/calc/{topic}", response_class=HTMLResponse)
async def calculate(request: Request, topic: str):
    if topic not in FORMS:
        return RedirectResponse("/", status_code=303)
    submitted = {k: str(v) for k, v in (await request.form()).items()}
    values = forms.form_values(topic, submitted)
    for f in FORMS[topic].fields:  # unticked checkboxes are absent from the POST
        if f.kind == "switch" and f.name not in submitted:
            values.pop(f.name, None)
    try:
        result, heading = forms.compute(topic, values)
    except (ValueError, calc.NotCovered) as e:
        return render(request, "calc.html", topic=topic, form=FORMS[topic], values=values, error=str(e))
    return render(request, "calc.html", topic=topic, form=FORMS[topic], values=values, result=result, heading=heading)


@app.post("/ask", response_class=HTMLResponse)
async def ask(request: Request):
    data = await request.form()
    question = (str(data.get("q", "")).strip() or str(data.get("example", "")).strip())[:500]
    if not question:
        return RedirectResponse("/", status_code=303)
    a = forms.answer(question)
    if a.topic:
        return render(request, "calc.html", topic=a.topic, form=FORMS[a.topic], values=a.values,
                      question=question, passages=a.passages)
    return render(request, "answer.html", question=question, passages=a.passages, topics=a.topics, forms=FORMS)


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request):
    return render(request, "sources.html")


@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"
