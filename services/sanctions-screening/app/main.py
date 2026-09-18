"""Sanctions screening service.

Exposes a single screening endpoint that ledger-core calls (or a human
compliance officer calls manually) before a transaction can leave
PENDING_SCREENING. Every decision is persisted (in-memory here; a real
deployment persists to its own audited datastore, never silently discarded)
so a HOLD decision always produces a traceable case for escalation.
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.screening import MockWatchlistProvider, ScreeningProvider

app = FastAPI(
    title="PAYO Sanctions Screening Gate",
    description="Auditable sanctions screening + case escalation for the transaction path.",
    version="0.1.0",
)

_provider: ScreeningProvider = MockWatchlistProvider()
_cases: dict[str, dict] = {}  # case_id -> case record (showcase: in-memory)


class ScreenRequest(BaseModel):
    transaction_id: str
    party_name: str
    party_ref: str


class ScreenResponse(BaseModel):
    transaction_id: str
    decision: str
    matched_terms: list[str]
    provider: str
    case_id: str | None
    screened_at: str


class CaseOut(BaseModel):
    case_id: str
    transaction_id: str
    party_name: str
    matched_terms: list[str]
    status: str
    created_at: str


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "sanctions-screening"}


@app.post("/screen", response_model=ScreenResponse)
async def screen(body: ScreenRequest) -> ScreenResponse:
    result = await _provider.screen(party_name=body.party_name, party_ref=body.party_ref)
    now = datetime.now(timezone.utc).isoformat()

    case_id = None
    if result.decision == "HOLD":
        case_id = str(uuid4())
        _cases[case_id] = {
            "case_id": case_id,
            "transaction_id": body.transaction_id,
            "party_name": body.party_name,
            "matched_terms": result.matched_terms,
            "status": "OPEN",
            "created_at": now,
        }

    return ScreenResponse(
        transaction_id=body.transaction_id,
        decision=result.decision,
        matched_terms=result.matched_terms,
        provider=result.provider,
        case_id=case_id,
        screened_at=now,
    )


@app.get("/cases/{case_id}", response_model=CaseOut)
async def get_case(case_id: str) -> CaseOut:
    case = _cases.get(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return CaseOut(**case)


@app.post("/cases/{case_id}/resolve", response_model=CaseOut)
async def resolve_case(case_id: str, resolution: str) -> CaseOut:
    case = _cases.get(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if resolution not in {"CLEARED", "CONFIRMED_MATCH"}:
        raise HTTPException(422, "resolution must be CLEARED or CONFIRMED_MATCH")
    case["status"] = resolution
    return CaseOut(**case)
