"""Local FastAPI page and two JSON endpoints; no external services."""

from typing import Annotated
import pandas as pd
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from document_assistant import answer_question
from lead_scoring import ROOT, CATEGORICAL_FEATURES, prepare_features, score_lead

app = FastAPI(title="MGC Sales Assistant")
templates = Jinja2Templates(directory=ROOT / "templates")


def form_options():
    frame = prepare_features(pd.read_csv(ROOT / "leads.csv"))
    return {column: sorted(frame[column].dropna().unique()) for column in CATEGORICAL_FEATURES}


OPTIONS = form_options()


def page(request, **context):
    return templates.TemplateResponse(request=request, name="index.html",
                                      context={"options": OPTIONS, "values": {}, **context})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(request)


@app.post("/ask", response_class=HTMLResponse)
def ask(request: Request, question: Annotated[str, Form(max_length=2000)] = ""):
    return page(request, question=question, response=answer_question(question))


@app.post("/score", response_class=HTMLResponse)
async def score(request: Request):
    details = dict(await request.form())
    try:
        return page(request, probability=score_lead(details), values=details)
    except (ValueError, FileNotFoundError) as exc:
        return page(request, error=str(exc), values=details)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Lead(BaseModel):
    source: str | None = None
    city: str | None = None
    area: str | None = None
    property_type: str | None = None
    budget_pkr_lac: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    bedrooms: int | None = Field(default=None, ge=0, le=5)
    agent_experience_years: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    is_overseas: int | None = Field(default=None, ge=0, le=1)
    referred_by_existing_client: int | None = Field(default=None, ge=0, le=1)


@app.post("/api/ask")
def api_ask(payload: Question):
    return answer_question(payload.question)


@app.post("/api/score")
def api_score(payload: Lead):
    try:
        return {"probability": score_lead(payload.model_dump())}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
