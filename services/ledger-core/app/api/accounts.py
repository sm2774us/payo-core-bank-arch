from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AccountCreate, AccountOut, BalanceOut
from app.domain.ledger import account_balance
from app.domain.models import Account
from app.infra.db import get_session

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(
    body: AccountCreate, session: AsyncSession = Depends(get_session)
) -> Account:
    account = Account(
        name=body.name,
        account_type=body.account_type,
        currency=body.currency,
        owner_ref=body.owner_ref,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(account_id: str, session: AsyncSession = Depends(get_session)) -> Account:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    return account


@router.get("/{account_id}/balance", response_model=BalanceOut)
async def get_balance(account_id: str, session: AsyncSession = Depends(get_session)) -> BalanceOut:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    balance = await account_balance(session, account_id)
    return BalanceOut(account_id=account_id, balance=balance)
