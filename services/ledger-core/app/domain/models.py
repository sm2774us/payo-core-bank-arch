"""Append-only double-entry ledger schema.

Design invariant (enforced in app/domain/ledger.py and re-verified by
reconciliation-worker): for every transaction_id, SUM(entry.signed_amount) == 0.
Account balances are NEVER stored — they are always derived by summing entries.
This eliminates an entire class of "balance drifted from history" bugs.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AccountType(str, enum.Enum):
    CUSTOMER_FIAT = "CUSTOMER_FIAT"
    RESERVE = "RESERVE"  # fiat held at reserve custodian, backing PAYO-USD
    ONCHAIN_MIRROR = "ONCHAIN_MIRROR"  # ledger-side mirror of on-chain token supply
    FEE_REVENUE = "FEE_REVENUE"
    SUSPENSE = "SUSPENSE"  # holding account for screening holds / breaks


class TransactionState(str, enum.Enum):
    INITIATED = "INITIATED"
    PENDING_SCREENING = "PENDING_SCREENING"
    SCREENED_CLEAR = "SCREENED_CLEAR"
    SCREENED_HOLD = "SCREENED_HOLD"
    ESCALATED = "ESCALATED"
    POSTED = "POSTED"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"


class EntryDirection(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    owner_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="account")

    __table_args__ = (UniqueConstraint("name", name="uq_accounts_name"),)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[TransactionState] = mapped_column(
        Enum(TransactionState), nullable=False, default=TransactionState.INITIATED
    )
    reference: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    screening_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    screening_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction")

    __table_args__ = (UniqueConstraint("reference", name="uq_transactions_reference"),)


class LedgerEntry(Base):
    """One leg of a double-entry posting. Never updated or deleted post-creation."""

    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("transactions.id"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("accounts.id"), nullable=False, index=True
    )
    direction: Mapped[EntryDirection] = mapped_column(Enum(EntryDirection), nullable=False)
    amount: Mapped[Numeric] = mapped_column(Numeric(20, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    transaction: Mapped[Transaction] = relationship(back_populates="entries")
    account: Mapped[Account] = relationship(back_populates="entries")

    __table_args__ = (CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),)


class IdempotencyKey(Base):
    """Guarantees exactly-once processing for mutating API calls.

    A (key, request_hash) pair is unique-constrained; a replayed request with the
    same key and same body returns the stored response instead of re-executing.
    A replayed key with a *different* body is a client bug and is rejected (409).
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[str] = mapped_column(String, nullable=False)
    status_code: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OutboxEvent(Base):
    """Transactional outbox: written in the SAME DB transaction as the ledger
    posting, then relayed to Kafka by a separate relay process. This is what
    guarantees the ledger write and the mint/burn instruction never diverge —
    there is no window where one happens without the other.
    """

    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(String, nullable=False)  # JSON-encoded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    relayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
