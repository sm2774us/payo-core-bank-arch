from decimal import Decimal

import pytest

from app.domain.ledger import (
    LedgerInvariantError,
    PostingLeg,
    account_balance,
    assert_balanced,
    post_transaction,
    transaction_nets_to_zero,
)
from app.domain.models import Account, AccountType, EntryDirection


def test_assert_balanced_accepts_zero_sum_legs():
    legs = [
        PostingLeg("a", EntryDirection.DEBIT, Decimal("100")),
        PostingLeg("b", EntryDirection.CREDIT, Decimal("100")),
    ]
    assert_balanced(legs)  # should not raise


def test_assert_balanced_rejects_unbalanced_legs():
    legs = [
        PostingLeg("a", EntryDirection.DEBIT, Decimal("100")),
        PostingLeg("b", EntryDirection.CREDIT, Decimal("99")),
    ]
    with pytest.raises(LedgerInvariantError, match="Unbalanced posting"):
        assert_balanced(legs)


def test_assert_balanced_rejects_non_positive_amount():
    legs = [
        PostingLeg("a", EntryDirection.DEBIT, Decimal("0")),
        PostingLeg("b", EntryDirection.CREDIT, Decimal("0")),
    ]
    with pytest.raises(LedgerInvariantError, match="must be positive"):
        assert_balanced(legs)


@pytest.mark.asyncio
async def test_post_transaction_creates_balanced_entries_and_updates_balances(session):
    fiat = Account(name="customer-1-fiat", account_type=AccountType.CUSTOMER_FIAT)
    reserve = Account(name="reserve-pool", account_type=AccountType.RESERVE)
    session.add_all([fiat, reserve])
    await session.flush()

    txn = await post_transaction(
        session,
        reference="dep-001",
        description="Customer deposit",
        legs=[
            PostingLeg(fiat.id, EntryDirection.DEBIT, Decimal("500")),
            PostingLeg(reserve.id, EntryDirection.CREDIT, Decimal("500")),
        ],
    )
    await session.commit()

    assert await transaction_nets_to_zero(session, txn.id) is True
    assert await account_balance(session, fiat.id) == Decimal("-500")
    assert await account_balance(session, reserve.id) == Decimal("500")


@pytest.mark.asyncio
async def test_post_transaction_rejects_unknown_account(session):
    with pytest.raises(LedgerInvariantError, match="Unknown account"):
        await post_transaction(
            session,
            reference="bad-001",
            description=None,
            legs=[
                PostingLeg("does-not-exist-1", EntryDirection.DEBIT, Decimal("10")),
                PostingLeg("does-not-exist-2", EntryDirection.CREDIT, Decimal("10")),
            ],
        )


@pytest.mark.asyncio
async def test_post_transaction_writes_outbox_event(session):
    a = Account(name="a", account_type=AccountType.CUSTOMER_FIAT)
    b = Account(name="b", account_type=AccountType.SUSPENSE)
    session.add_all([a, b])
    await session.flush()

    txn = await post_transaction(
        session,
        reference="outbox-001",
        description=None,
        legs=[
            PostingLeg(a.id, EntryDirection.DEBIT, Decimal("1")),
            PostingLeg(b.id, EntryDirection.CREDIT, Decimal("1")),
        ],
    )
    await session.commit()

    from sqlalchemy import select

    from app.domain.models import OutboxEvent

    result = await session.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == txn.id))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "ledger.transaction.posted"
    assert events[0].relayed_at is None
