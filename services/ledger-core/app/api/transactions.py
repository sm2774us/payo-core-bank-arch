from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ScreeningDecisionIn, TransactionCreate, TransactionOut
from app.domain.ledger import LedgerInvariantError, PostingLeg, post_transaction
from app.domain.models import Transaction, TransactionState
from app.infra.db import get_session
from app.infra.idempotency import (
    IdempotencyConflict,
    get_cached_response,
    hash_body,
    store_response,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut, status_code=201)
async def create_transaction(
    body: TransactionCreate,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> TransactionOut:
    body_hash = hash_body(body.model_dump(mode="json"))

    try:
        cached = await get_cached_response(session, idempotency_key, body_hash)
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc

    if cached is not None:
        status_code, response_body = cached
        return TransactionOut.model_validate_json(response_body)

    legs = [PostingLeg(account_id=leg.account_id, direction=leg.direction, amount=leg.amount)
            for leg in body.legs]
    try:
        txn = await post_transaction(
            session, reference=body.reference, description=body.description, legs=legs
        )
    except LedgerInvariantError as exc:
        raise HTTPException(422, str(exc)) from exc

    result = TransactionOut.model_validate(txn)
    await store_response(session, idempotency_key, body_hash, 201, result.model_dump_json())
    await session.commit()
    return result


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    transaction_id: str, session: AsyncSession = Depends(get_session)
) -> Transaction:
    txn = await session.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(404, "Transaction not found")
    return txn


@router.post("/{transaction_id}/screening-decision", response_model=TransactionOut)
async def apply_screening_decision(
    transaction_id: str,
    body: ScreeningDecisionIn,
    session: AsyncSession = Depends(get_session),
) -> Transaction:
    """The compliance gate. A transaction MUST pass through here — with a
    persisted, timestamped, attributable decision — before it can be POSTED.
    This is the auditable hook the JD calls out explicitly."""
    txn = await session.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(404, "Transaction not found")
    if txn.state != TransactionState.PENDING_SCREENING:
        raise HTTPException(
            409, f"Transaction is in state {txn.state}, not PENDING_SCREENING"
        )

    txn.screening_decision = body.decision
    txn.screening_decided_at = datetime.now(timezone.utc)
    txn.state = (
        TransactionState.SCREENED_CLEAR
        if body.decision == "CLEAR"
        else TransactionState.SCREENED_HOLD
    )
    if txn.state == TransactionState.SCREENED_CLEAR:
        txn.state = TransactionState.POSTED

    await session.commit()
    await session.refresh(txn)
    return txn
