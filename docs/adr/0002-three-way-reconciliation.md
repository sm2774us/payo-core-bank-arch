# ADR-0002: Three-Way Reconciliation as a Pure Function Over Immutable Inputs

## Status
Accepted

## Context
PAYO-USD's integrity depends on three independent numbers agreeing:
1. The fiat subledger's RESERVE account balance (what the bank's books say is
   held at the reserve custodian).
2. The ledger's ONCHAIN_MIRROR balance (what the bank's books say was
   minted/burned on-chain).
3. The actual on-chain token supply (`CustodyClient.on_chain_supply()`).

## Decision
Reconciliation (`app/api/reconciliation.py::three_way_reconciliation`) is a
**pure read** over these three sources — it computes and reports both
pairwise breaks (`reserve_vs_mirror_break`, `mirror_vs_onchain_break`)
explicitly, rather than a single opaque pass/fail. `reconciliation-worker`
runs this on a schedule and wraps the result in a **signed evidence bundle**
(`services/reconciliation-worker/app/evidence.py`) binding the exact inputs,
the computed breaks, a timestamp, and an attribution to a cryptographic
signature.

## Alternatives considered
- **Reconciling via a nightly batch diff of exported CSVs.** Rejected: no
  binding between the export and the moment it was taken; trivially
  vulnerable to a stale or partial export being mistaken for current state.
- **Only checking a single aggregate "total supply == total reserves"
  number.** Rejected: collapses two independent failure modes (a reserve
  break vs. a mint/burn sync break) into one signal, which is exactly the
  ambiguity an examiner will push back on.

## Consequences
- A break is always reported with the two specific numbers that disagree,
  never just "reconciliation failed" — actionable from the first alert.
- The evidence bundle is independently verifiable by a third party who has
  the (rotatable) verification key, without needing write access to
  production — a requirement for external audit review.
