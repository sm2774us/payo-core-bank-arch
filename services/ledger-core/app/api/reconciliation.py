from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ledger import account_balance
from app.domain.models import AccountType
from app.infra.custody_client import CustodyClient, MockCustodyClient
from app.infra.db import get_session
from sqlalchemy import select

from app.domain.models import Account

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

_custody_singleton = MockCustodyClient()


def get_custody_client() -> CustodyClient:
    return _custody_singleton


class ReconciliationReport(BaseModel):
    reserve_balance: Decimal
    onchain_mirror_balance: Decimal
    onchain_actual_supply: Decimal
    reserve_vs_mirror_break: Decimal
    mirror_vs_onchain_break: Decimal
    is_balanced: bool


@router.get("/three-way", response_model=ReconciliationReport)
async def three_way_reconciliation(
    session: AsyncSession = Depends(get_session),
    custody: CustodyClient = Depends(get_custody_client),
) -> ReconciliationReport:
    """Compares three independent sources of truth:
      1. RESERVE account balance   — fiat subledger's view of reserve custodian funds
      2. ONCHAIN_MIRROR balance    — ledger's record of what it believes was minted/burned
      3. custody.on_chain_supply() — the actual on-chain token supply

    A non-zero break in either comparison is exactly the signal an OCC examiner
    or auditor would want surfaced, with the two numbers that disagree named
    explicitly (never "reconciliation failed" with no numbers)."""
    reserve_accounts = (
        (
            await session.execute(
                select(Account.id).where(Account.account_type == AccountType.RESERVE)
            )
        )
        .scalars()
        .all()
    )
    mirror_accounts = (
        (
            await session.execute(
                select(Account.id).where(Account.account_type == AccountType.ONCHAIN_MIRROR)
            )
        )
        .scalars()
        .all()
    )

    reserve_balance = Decimal("0")
    for acc_id in reserve_accounts:
        reserve_balance += await account_balance(session, acc_id)

    mirror_balance = Decimal("0")
    for acc_id in mirror_accounts:
        mirror_balance += await account_balance(session, acc_id)

    onchain_supply = await custody.on_chain_supply()

    return ReconciliationReport(
        reserve_balance=reserve_balance,
        onchain_mirror_balance=mirror_balance,
        onchain_actual_supply=onchain_supply,
        reserve_vs_mirror_break=reserve_balance - mirror_balance,
        mirror_vs_onchain_break=mirror_balance - onchain_supply,
        is_balanced=(reserve_balance == mirror_balance == onchain_supply),
    )
