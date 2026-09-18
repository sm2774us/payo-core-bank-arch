from decimal import Decimal

import pytest

from app.domain.ledger import PostingLeg, post_transaction
from app.domain.models import Account, AccountType, EntryDirection
from app.infra.custody_client import MockCustodyClient
from app.infra.outbox import InMemoryPublisher, relay_once


@pytest.mark.asyncio
async def test_three_way_reconciliation_detects_break(client, session_factory):
    reserve = Account(name="reserve-x", account_type=AccountType.RESERVE)
    mirror = Account(name="mirror-x", account_type=AccountType.ONCHAIN_MIRROR)
    async with session_factory() as session:
        session.add_all([reserve, mirror])
        await session.flush()
        await post_transaction(
            session,
            reference="fund-reserve",
            description=None,
            legs=[
                PostingLeg(mirror.id, EntryDirection.DEBIT, Decimal("1000")),
                PostingLeg(reserve.id, EntryDirection.CREDIT, Decimal("1000")),
            ],
        )
        await session.commit()

    # custody client (mock) has minted nothing yet -> mirror/reserve show 1000
    # but actual on-chain supply is 0 -> a break must be reported, not hidden.
    resp = await client.get("/reconciliation/three-way")
    report = resp.json()
    assert Decimal(report["reserve_balance"]) == Decimal("1000")
    assert Decimal(report["onchain_actual_supply"]) == Decimal("0")
    assert report["is_balanced"] is False


@pytest.mark.asyncio
async def test_mock_custody_client_mint_and_burn_round_trip():
    custody = MockCustodyClient()
    await custody.mint(amount=Decimal("500"), reference="mint-1")
    assert await custody.on_chain_supply() == Decimal("500")
    await custody.burn(amount=Decimal("200"), reference="burn-1")
    assert await custody.on_chain_supply() == Decimal("300")

    with pytest.raises(ValueError, match="Cannot burn more"):
        await custody.burn(amount=Decimal("10_000"), reference="burn-2")


@pytest.mark.asyncio
async def test_outbox_relay_marks_events_relayed_and_is_idempotent_to_rerun(session_factory):
    async with session_factory() as session:
        a = Account(name="relay-a", account_type=AccountType.CUSTOMER_FIAT)
        b = Account(name="relay-b", account_type=AccountType.SUSPENSE)
        session.add_all([a, b])
        await session.flush()
        await post_transaction(
            session,
            reference="relay-txn-1",
            description=None,
            legs=[
                PostingLeg(a.id, EntryDirection.DEBIT, Decimal("42")),
                PostingLeg(b.id, EntryDirection.CREDIT, Decimal("42")),
            ],
        )
        await session.commit()

    publisher = InMemoryPublisher()
    relayed_first = await relay_once(publisher)
    assert relayed_first == 1
    assert len(publisher.published) == 1

    # Second run finds nothing new to relay — already-relayed events are never
    # re-published, which is what prevents duplicate mint/burn instructions.
    relayed_second = await relay_once(publisher)
    assert relayed_second == 0
    assert len(publisher.published) == 1
