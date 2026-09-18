# ADR-0005: Sanctions Screening as a Required Transaction-State Gate

## Status
Accepted

## Context
The JD calls out "compliance in the transaction path" explicitly — screening
must be an enforced part of the transaction lifecycle, not a best-effort
side-call a future engineer could accidentally bypass.

## Decision
`PENDING_SCREENING` is a first-class state in the `Transaction` state
machine. A transaction cannot reach `POSTED` without an explicit call to
`POST /transactions/{id}/screening-decision` that persists a decision, a
timestamp, and (in the sanctions-screening service) an attributable
`screened_by` identity. A `HOLD` decision opens a traceable case
(`services/sanctions-screening/app/main.py::_cases`) rather than silently
blocking the transaction with no record of why.

## Alternatives considered
- **Screening as an async side-effect / best-effort check after posting.**
  Rejected: this is precisely the pattern that lets a sanctioned-party
  transaction slip through if the side-effect fails silently or is skipped
  under load.
- **Screening logic embedded directly in ledger-core.** Rejected: keeping it
  a separate service behind a stable interface (`ScreeningProvider`) means a
  vendor swap (Chainalysis, ComplyAdvantage, Refinitiv) never touches ledger
  code, and the compliance team can own its service's deploy cadence
  independently of the ledger's.

## Consequences
- One additional required API call in the transaction lifecycle; this is the
  point — the friction is intentional and matches what an OCC examiner
  expects to find enforced in code, not just in a runbook.
