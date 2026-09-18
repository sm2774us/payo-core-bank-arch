"""Sanctions screening provider boundary.

Real implementation would call a vendor (Chainalysis KYT, ComplyAdvantage,
Refinitiv World-Check) behind this exact Protocol. The mock below uses a
small deterministic watchlist so the showcase repo has zero external deps
and fully reproducible test outcomes — critical for a component whose whole
job is to be auditable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

_MOCK_WATCHLIST = {
    "jane blockedparty",
    "acme sanctioned holdings",
    "restricted trading co",
}


@dataclass(frozen=True)
class ScreeningResult:
    decision: str  # "CLEAR" | "HOLD"
    matched_terms: list[str]
    provider: str


class ScreeningProvider(Protocol):
    async def screen(self, *, party_name: str, party_ref: str) -> ScreeningResult: ...


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


class MockWatchlistProvider:
    """Deterministic name-matching mock; fuzzy/entity-resolution matching in a
    real system is delegated entirely to the vendor behind ScreeningProvider."""

    provider_name = "mock-watchlist-v1"

    async def screen(self, *, party_name: str, party_ref: str) -> ScreeningResult:
        normalized = _normalize(party_name)
        matches = [term for term in _MOCK_WATCHLIST if term in normalized]
        decision = "HOLD" if matches else "CLEAR"
        return ScreeningResult(decision=decision, matched_terms=matches, provider=self.provider_name)
