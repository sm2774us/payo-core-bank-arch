"""Pure(ish) domain logic for posting double-entry transactions.

Kept free of FastAPI/HTTP concerns so it can be unit-tested in isolation and
reused by the reconciliation worker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Account,
    EntryDirection,
    LedgerEntry,
    OutboxEvent,
    Transaction,
    TransactionState,
)


class LedgerInvariantError(ValueError):
    """Raised when a proposed set of entries does not net to zero, or references
    an unknown account. Never allowed to reach the database."""


@dataclass(frozen=True)
class PostingLeg:
    account_id: str
    direction: EntryDirection
    amount: Decimal


def assert_balanced(legs: list[PostingLeg]) -> None:
    """The double-entry invariant: total debits == total credits for a transaction.

    This is checked here (fail fast, before any DB write) AND independently
    re-derivable from ledger_entries by the reconciliation worker — the two
    checks use different code paths so a bug in one doesn't mask a break.
    """
    total = Decimal("0")
    for leg in legs:
        if leg.amount <= 0:
            raise LedgerInvariantError(f"Leg amount must be positive, got {leg.amount}")
        total += leg.amount if leg.direction == EntryDirection.CREDIT else -leg.amount
    if total != Decimal("0"):
        raise LedgerInvariantError(f"Unbalanced posting: net {total} (must be exactly 0)")


async def post_transaction(
    session: AsyncSession,
    *,
    reference: str,
    description: str | None,
    legs: list[PostingLeg],
    emit_outbox_event: bool = True,
) -> Transaction:
    """Atomically create a Transaction + its LedgerEntry legs + an outbox event.

    All three writes happen in one DB transaction (the caller's session/commit
    boundary), which is exactly what makes the outbox pattern safe: either the
    ledger posting AND the "notify downstream" event both land, or neither does.
    """
    assert_balanced(legs)

    account_ids = {leg.account_id for leg in legs}
    existing = (
        (await session.execute(select(Account.id).where(Account.id.in_(account_ids))))
        .scalars()
        .all()
    )
    missing = account_ids - set(existing)
    if missing:
        raise LedgerInvariantError(f"Unknown account id(s): {sorted(missing)}")

    txn = Transaction(
        reference=reference,
        description=description,
        state=TransactionState.PENDING_SCREENING,
    )
    session.add(txn)
    await session.flush()  # populate txn.id

    for leg in legs:
        session.add(
            LedgerEntry(
                transaction_id=txn.id,
                account_id=leg.account_id,
                direction=leg.direction,
                amount=leg.amount,
            )
        )

    if emit_outbox_event:
        session.add(
            OutboxEvent(
                aggregate_id=txn.id,
                event_type="ledger.transaction.posted",
                payload=json.dumps(
                    {
                        "transaction_id": txn.id,
                        "reference": reference,
                        "legs": [
                            {
                                "account_id": leg.account_id,
                                "direction": leg.direction.value,
                                "amount": str(leg.amount),
                            }
                            for leg in legs
                        ],
                    }
                ),
            )
        )

    await session.flush()
    return txn


async def account_balance(session: AsyncSession, account_id: str) -> Decimal:
    """Derive a balance purely from history. Never trust a cached/stored value."""
    result = await session.execute(
        select(LedgerEntry.direction, LedgerEntry.amount).where(
            LedgerEntry.account_id == account_id
        )
    )
    balance = Decimal("0")
    for direction, amount in result.all():
        balance += amount if direction == EntryDirection.CREDIT else -amount
    return balance


async def transaction_nets_to_zero(session: AsyncSession, transaction_id: str) -> bool:
    """Independent re-verification of the double-entry invariant from stored
    entries — used by tests and the reconciliation worker as a second, DB-level
    check distinct from assert_balanced()."""
    result = await session.execute(
        select(LedgerEntry.direction, LedgerEntry.amount).where(
            LedgerEntry.transaction_id == transaction_id
        )
    )
    net = Decimal("0")
    for direction, amount in result.all():
        net += amount if direction == EntryDirection.CREDIT else -amount
    return net == Decimal("0")
