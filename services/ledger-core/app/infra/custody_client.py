"""Custody platform integration boundary (mint/burn on-chain actions).

Real implementation would wrap a Fireblocks / Anchorage / BitGo SDK client
behind this exact Protocol so the rest of the codebase (and its tests) never
depend on a specific vendor. Swapping vendors is a one-file change.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class MintBurnResult:
    on_chain_tx_hash: str
    confirmed: bool


class CustodyClient(Protocol):
    async def mint(self, *, amount: Decimal, reference: str) -> MintBurnResult: ...
    async def burn(self, *, amount: Decimal, reference: str) -> MintBurnResult: ...
    async def on_chain_supply(self) -> Decimal: ...


class MockCustodyClient:
    """Deterministic in-memory mock so the showcase repo runs with zero external
    dependencies. Tracks a running supply so reconciliation logic has something
    real to reconcile against."""

    def __init__(self) -> None:
        self._supply = Decimal("0")
        self._seq = 0

    async def mint(self, *, amount: Decimal, reference: str) -> MintBurnResult:
        self._supply += amount
        self._seq += 1
        return MintBurnResult(on_chain_tx_hash=f"0xMOCKMINT{self._seq:08d}", confirmed=True)

    async def burn(self, *, amount: Decimal, reference: str) -> MintBurnResult:
        if amount > self._supply:
            raise ValueError("Cannot burn more than current on-chain supply")
        self._supply -= amount
        self._seq += 1
        return MintBurnResult(on_chain_tx_hash=f"0xMOCKBURN{self._seq:08d}", confirmed=True)

    async def on_chain_supply(self) -> Decimal:
        return self._supply
