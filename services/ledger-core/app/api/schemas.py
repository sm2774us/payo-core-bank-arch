from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.domain.models import AccountType, EntryDirection, TransactionState


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    account_type: AccountType
    currency: str = Field(default="USD", min_length=3, max_length=10)
    owner_ref: str | None = None


class AccountOut(BaseModel):
    id: str
    name: str
    account_type: AccountType
    currency: str

    model_config = {"from_attributes": True}


class LegIn(BaseModel):
    account_id: str
    direction: EntryDirection
    amount: Decimal = Field(gt=0)

    @field_validator("amount")
    @classmethod
    def quantize(cls, v: Decimal) -> Decimal:
        return v.normalize()


class TransactionCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=200)
    description: str | None = None
    legs: list[LegIn] = Field(min_length=2)


class TransactionOut(BaseModel):
    id: str
    reference: str
    state: TransactionState
    description: str | None

    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    account_id: str
    balance: Decimal


class ScreeningDecisionIn(BaseModel):
    decision: str = Field(pattern="^(CLEAR|HOLD)$")
    screened_by: str
    rationale: str | None = None
