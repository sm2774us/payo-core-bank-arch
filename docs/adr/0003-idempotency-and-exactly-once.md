# ADR-0003: Idempotency-Key Enforcement for Exactly-Once Semantics

## Status
Accepted

## Context
Upstream systems (payment rails, custody webhooks, retried client requests)
will, under normal network conditions, occasionally send the same mutating
request more than once. In a ledger, a duplicate that is not caught is a
duplicate posting — real money moved twice.

## Decision
Every mutating `ledger-core` endpoint requires an `Idempotency-Key` header.
The key, together with a hash of the request body, is stored
(`idempotency_keys`, primary-key on `key`) in the **same database
transaction** as the ledger posting it guards. A replay with the same key and
body returns the original stored response; a replay with the same key and a
*different* body is rejected with `409 Conflict` (a client-side bug, not
silently accepted).

## Alternatives considered
- **Client-side de-duplication only (trust the caller not to retry).**
  Rejected outright for a banking ledger — the whole point of the control is
  to not depend on every caller getting retry logic right.
- **Idempotency at the message-queue layer only (Kafka consumer
  offsets).** Insufficient alone: doesn't cover synchronous HTTP callers, and
  consumer-offset semantics don't naturally extend to "return the client the
  original response," which several callers of this API depend on.

## Consequences
- Every mutating endpoint has one extra required header and one extra
  DB round-trip; negligible cost against the alternative of double-posted
  transactions.
- The pattern generalizes directly to the sanctions-screening decision
  endpoint and to future mutating endpoints — new endpoints don't need to
  reinvent this.
