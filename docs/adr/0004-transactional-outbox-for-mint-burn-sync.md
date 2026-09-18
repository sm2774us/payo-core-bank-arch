# ADR-0004: Transactional Outbox for Ledger ⇄ Mint/Burn Event Sync

## Status
Accepted

## Context
When a ledger posting requires a corresponding on-chain mint or burn, the
ledger write and the "notify the custody platform" action must never diverge
— either both happen or neither does. A direct synchronous HTTP call from
the ledger transaction handler to the custody platform cannot guarantee this
(the ledger write could commit while the HTTP call fails, or vice versa).

## Decision
`post_transaction()` writes an `OutboxEvent` row in the **same DB
transaction** as the `Transaction` and its `LedgerEntry` rows
(`app/domain/ledger.py`). A separate relay process (`app/infra/outbox.py`)
polls unrelayed events and publishes them to Kafka **at-least-once**,
marking each event `relayed_at` only after a successful publish. The
mint/burn engine consuming this topic is expected to be an idempotent
consumer (keyed on `transaction_id`), so at-least-once delivery plus an
idempotent consumer together give exactly-once *effects* without requiring a
distributed transaction across Postgres and Kafka.

## Alternatives considered
- **Two-phase commit across Postgres and Kafka.** Rejected: Kafka does not
  support XA-style 2PC, and even where similar patterns exist, they add
  substantial operational complexity for a guarantee the outbox pattern
  already provides more simply.
- **Publish to Kafka first, then write the ledger entry.** Rejected: an
  on-chain mint/burn instruction could be sent for a ledger posting that then
  fails to commit — the more dangerous direction of divergence for a
  regulated ledger.

## Consequences
- Slight latency between a ledger commit and its downstream effect becoming
  visible (bounded by the relay's poll interval) — acceptable; the guarantee
  we need is "eventually and exactly once," not "synchronously."
- The relay is a separate, independently scalable/restartable process; a
  relay outage delays mint/burn sync but never causes it to be skipped or
  duplicated, since unrelayed events simply remain in the outbox table.
