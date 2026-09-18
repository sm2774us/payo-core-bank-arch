# ADR-0001: Double-Entry, Append-Only Ledger (Derived Balances)

## Status
Accepted

## Context
The core ledger is the system of record for every dollar of PAYO-USD in
circulation. It must be provably correct to an external auditor and an OCC
examiner, not merely "correct in practice."

## Decision
- `ledger_entries` rows are **append-only** — never updated, never deleted.
- Every transaction posts a set of entries whose signed amounts **sum to
  exactly zero** (`app/domain/ledger.py::assert_balanced`).
- Account balances are **always derived** (`SUM(credits) - SUM(debits)`),
  never stored as a mutable column.

## Alternatives considered
1. **Single mutable `balance` column per account, updated via `UPDATE ... SET
   balance = balance + ?`.** Rejected: race conditions under concurrent
   writes require row-level locking that doesn't scale, and — critically for
   audit purposes — a stored balance can silently drift from its transaction
   history with no way to detect *when* it drifted.
2. **Event-sourced ledger with periodic snapshots.** Considered for very
   high-volume ledgers; deferred for this scope because derived-balance
   double-entry already gives us the audit properties we need at a fraction
   of the operational complexity, and query-time aggregation is fast enough
   at expected PDB transaction volumes.

## Consequences
- Reading a balance costs an aggregation query instead of a point read —
  acceptable given the audit-integrity trade-off; a materialized summary
  table can be added later purely as a read-side cache, re-derivable at any
  time from `ledger_entries`.
- Every historical statement, examiner request, or dispute can be answered by
  replaying entries — there is no "what was the balance to explain."
