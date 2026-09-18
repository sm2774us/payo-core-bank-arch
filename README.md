# PAYO Core Bank — Ledger ⇄ Stablecoin Reconciliation Platform

Reference architecture for **PAYO Digital Bank, N.A.**'s core transactional backbone: the
system of record reconciling **fiat reserves**, **on-chain PAYO-USD token supply**, and
**customer balances** with bank-grade accuracy, idempotency, and auditability.

Built as a showcase for the Senior Staff Engineer role's core mandate: architecture that a
regulator (OCC/FFIEC) or external auditor can examine and trust.

## 1. Why this design (for senior management / audit review)

| Decision | Choice | Why (defensible to auditors/execs) |
|---|---|---|
| Ledger model | **Double-entry, append-only** (`ledger_entries`); balances are *derived*, never stored/mutated | Immutable audit trail; a balance is provably the sum of its entries — no `UPDATE balance` race conditions, no silent drift |
| Consistency | **Exactly-once via idempotency keys** on every mutating endpoint, enforced by a DB unique constraint | Retries from upstream (custody webhooks, payment rails) cannot double-post — the #1 cause of real-world ledger breaks |
| Reconciliation | **Three-way reconciliation** (fiat subledger vs. reserve custodian statement vs. on-chain mint/burn log) as a pure function over immutable inputs | Any of the three sources can be replayed independently for an examiner; discrepancies are data, not opinions |
| Event backbone | **Transactional outbox → Kafka**, not direct HTTP calls between ledger and mint/burn engine | Guarantees the ledger write and the "instruction to mint/burn" commit atomically — no lost or duplicated on-chain actions |
| Compliance hook | Sanctions screening is a **required, auditable gate** in the transaction state machine (`PENDING_SCREENING`), not a side-call | A transaction cannot reach `SETTLED` without a persisted, timestamped screening decision — the first thing an OCC examiner asks for |
| Language/runtime | Python 3.11+/FastAPI for services | Pydantic-validated, self-documenting APIs (OpenAPI → regulator-facing contract); fast to review, fast to test |
| Infra | Terraform (VPC, EKS, RDS Multi-AZ, MSK, KMS), Kubernetes/Kustomize | Standard, auditable IaC; multi-AZ/multi-region failover targets declared in code, not tribal knowledge |
| CI gate | GitHub Actions: pre-commit → unit → integration (real Postgres service container) → build | "Green CI" is itself an audit artifact — proof every merged change passed the same bar |

## 2. Repository layout

```
payo-core-bank/
├── services/
│   ├── ledger-core/            # FastAPI: double-entry ledger, transaction state machine, reconciliation API
│   ├── sanctions-screening/    # FastAPI: sanctions screening gate + case escalation
│   └── reconciliation-worker/  # Scheduled worker: 3-way reconciliation + signed evidence bundles
├── infra/
│   ├── terraform/               # VPC, EKS, RDS (Multi-AZ), MSK, KMS — modules + dev/prod envs
│   └── k8s/                     # base + kustomize overlays (dev/prod)
├── docs/adr/                    # Architecture Decision Records (regulator-ready justification)
├── .github/workflows/           # CI: pre-commit, test, build, terraform validate
├── docker-compose.yml           # Full local stack (Postgres, Kafka, both services)
└── .pre-commit-config.yaml
```

## 3. Core domain model (`ledger-core`)

- `Account` — one row per ledger account (customer fiat, reserve, on-chain-mirror, fee, suspense).
- `LedgerEntry` — append-only `(account_id, amount, direction, transaction_id)`. Balance = `SUM(credits) - SUM(debits)` per account, always computed, never stored.
- `Transaction` — the unit of work; state machine:
  `INITIATED → PENDING_SCREENING → SCREENED_CLEAR → POSTED → SETTLED`
  (or `SCREENED_HOLD → ESCALATED`, or `REJECTED` at any gate).
- Every mutating call requires an `Idempotency-Key` header; the key + request hash is stored (`idempotency_keys`, unique-constrained) so a retried request returns the original result instead of re-executing.
- **Double-entry invariant** (`sum(entries) per transaction == 0`) is enforced at the application layer in `domain/ledger.py` and independently re-verified by the reconciliation worker and by an integration test that queries raw Postgres state — mirroring the "audit service correctness directly against DB state" practice from production experience.

## 4. Run instructions

### Local (no Docker)
```bash
cd services/ledger-core
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=sqlite+aiosqlite:///./local.db
uvicorn app.main:app --reload --port 8000
```
```bash
# in another shell — unit tests run against in-memory sqlite, no setup needed
pytest -q
```
Integration tests (`pytest -q -m integration`) require a local Postgres:
```bash
docker run -d --name payo-pg -e POSTGRES_PASSWORD=payo -e POSTGRES_DB=ledger -p 5432:5432 postgres:16
export DATABASE_URL=postgresql+asyncpg://postgres:payo@localhost:5432/ledger
pytest -q -m integration
```

### Docker (full stack: Postgres + Kafka + ledger-core + sanctions-screening)
```bash
docker compose up --build
curl http://localhost:8000/healthz
open http://localhost:8000/docs           # OpenAPI — the regulator-facing API contract
```

### Cloud (EKS via Terraform)
```bash
cd infra/terraform/environments/dev
terraform init
terraform plan  -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars

aws eks update-kubeconfig --name payo-core-dev --region us-east-1
kubectl apply -k ../../../k8s/overlays/dev
kubectl get pods -n payo-core
```

## 5. CI/CD (`.github/workflows/ci.yml`)

Runs on every PR, each step gating the next:
1. `pre-commit run --all-files` — ruff, black, mypy, terraform fmt/validate, hadolint, end-of-file/whitespace hygiene.
2. `pytest -q` unit tests, matrix over Python 3.11 / 3.12.
3. `pytest -q -m integration` against a real `postgres:16` **GitHub Actions service container** — not mocked, which is what makes the pipeline audit-credible.
4. `docker build` for every service — a non-zero exit fails the job; no image is ever pushed from a broken build.
5. `terraform fmt -check` and `terraform validate` for every environment.

All actions are pinned to a full commit SHA (not a floating tag) so the pipeline is reproducible — the answer to "how do you know what's reviewed is what's running in prod."

## 6. Candidate mapping — Shaikat Majumdar → this JD

| JD requirement | Demonstrated in this repo | Prior real-world basis (resume) |
|---|---|---|
| Core architecture ownership, OCC-grade docs | `services/ledger-core`, `docs/adr/*` | BAM: audit-grade system architecture documentation |
| Ledger ⇄ stablecoin reconciliation | `services/reconciliation-worker`, `docs/adr/0002-three-way-reconciliation.md` | BAM: idempotency & exactly-once processing across financial pipelines |
| Event messaging / mint-burn sync | Transactional outbox in `ledger-core/app/infra/outbox.py` | BAM & JPM: distributed event messaging endpoints |
| Technical leadership / review standards | `.pre-commit-config.yaml`, `CODEOWNERS`, ADR process | JPM/Highbridge: mentored senior engineers, enforced rigorous code review |
| Sanctions screening in transaction path | `services/sanctions-screening`, `PENDING_SCREENING` gate | JPM: IAM/compliance integration for sensitive transaction pipelines |
| Multi-region, K8s, IaC | `infra/terraform`, `infra/k8s` | Millburn: multi-region K8s; JPM: multi-cloud GCP/AWS |
| Audit readiness / evidence generation | `reconciliation-worker/app/evidence.py` | JPM: DR targets & risk in ADRs; BAM: DB-state-vs-log verification |

## 7. Intentionally scoped as a stub (with clear extension points)

This is a portfolio/showcase repo, not production PDB code:
- **On-chain custody** (`ledger-core/app/infra/custody_client.py`) — interface + deterministic mock; a real implementation swaps in a Fireblocks/Anchorage SDK client behind the same `CustodyClient` protocol.
- **Sanctions data source** (`sanctions-screening/app/screening.py`) — mock OFAC-style list; a real implementation swaps in a vendor (Chainalysis/ComplyAdvantage) behind the same `ScreeningProvider` protocol.
- **KMS** — `infra/terraform/modules/kms` declares the key + rotation policy; application-side envelope encryption has a defined interface boundary (`infra/crypto.py`) with a TODO for the vendor SDK.
