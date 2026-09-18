# PAYO Core Bank — Ledger ⇄ Stablecoin Reconciliation Platform

Reference architecture for **PAYO Digital Bank, N.A.**'s core transactional backbone: the
system of record reconciling **fiat reserves**, **on-chain PAYO-USD token supply**, and
**customer balances** with bank-grade accuracy, idempotency, and auditability.

Built as a showcase for the Senior Staff Engineer role's core mandate: architecture that a
regulator (OCC/FFIEC) or external auditor can examine and trust.

## Prerequisites

Install these before anything else in this README. Platform-specific steps below; all three end with `git`, `python3.12`, `docker`, `terraform`, and `kubectl` on your `PATH`.

| Tool | Why it's required |
|---|---|
| Git | clone the repo, run pre-commit hooks on `git commit` |
| Python 3.11/3.12 | run/test the three services |
| **Docker Desktop / Docker Engine** | `docker compose up` (local stack), `docker build` (CI parity), and the **`hadolint-docker`** pre-commit hook — it literally runs a container, so without Docker running, that hook fails with `Executable 'docker' not found` |
| Terraform (or OpenTofu) | `terraform_fmt` / `terraform_validate` pre-commit hooks, and `infra/terraform` itself |
| kubectl | deploying to EKS (§5, cloud) |

### Windows 11 — Docker Desktop

```powershell
winget install --id Docker.DockerDesktop -e
```
Launch Docker Desktop once after install and leave it running — every
`docker compose`, `docker build`, and `hadolint-docker` invocation needs its
engine up in the background. If you'll run pre-commit from WSL2 (recommended,
see the callout below), enable **Settings → Resources → WSL Integration →
(toggle your distro)** in Docker Desktop so `docker` is callable from inside
WSL too, without installing a second Docker engine there.

### Ubuntu (WSL2 or bare metal) — Docker Engine

If Docker Desktop's WSL integration (above) is already enabled, skip this —
`docker` is already available inside your WSL distro. Otherwise (bare-metal
Ubuntu, or a cloud VM):
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker        # or log out/in — refreshes your group membership
docker run hello-world   # sanity check
```

> ### ⚠️ Windows users: run `git commit` / `pre-commit` from WSL2, not native PowerShell/CMD/Git Bash
> The `terraform_fmt` and `terraform_validate` pre-commit hooks are Bash
> scripts. Native Windows Git Bash mangles Windows-style paths when invoking
> them (you'll see errors like `C:Userssm277.cachepre-commit...sh: No such
> file or directory` — the backslashes get silently dropped), which is a
> known incompatibility, not a bug in this repo. **The fix is to do all Git
> operations for this repo from inside WSL2 Ubuntu** (§4b/§4c above), where
> paths are native POSIX and the hooks run exactly as they do in CI:
> ```bash
> cd /mnt/c/SOFTWARE_ENGG_PROJECTS/PAYONEER/payo-core-bank-arch   # or, better, clone the repo directly under WSL's own filesystem (~/payo-core-bank) for much faster I/O
> git commit -m "..."
> ```
> If you'd rather stay on native Windows, drop the two Terraform hooks from
> `.pre-commit-config.yaml` and rely on the `terraform-validate` **CI job**
> (which runs on Linux) as your formatting/validation gate instead — you
> lose the local pre-commit check for Terraform specifically, everything
> else (ruff, mypy, hadolint, etc.) is unaffected and still runs natively.

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

## 4. Setup — Windows 11, Ubuntu (WSL), and Ubuntu (bare metal)

Pick your platform. All three end with the same repo cloned and dependencies ready.

### 4a. Windows 11 (native, PowerShell)

```powershell
# 1. Git
winget install --id Git.Git -e

# 2. Python 3.12
winget install --id Python.Python.3.12 -e

# 3. Docker Desktop (provides docker + docker compose)
winget install --id Docker.DockerDesktop -e

# 4. Terraform
winget install --id Hashicorp.Terraform -e

# 5. kubectl
winget install --id Kubernetes.kubectl -e

# 6. Clone and install
git clone https://github.com/<your-org>/payo-core-bank.git
cd payo-core-bank
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install pre-commit==3.8.0
```
> Native Windows works for editing, Docker Desktop, and `docker compose up`. For
> the Python test suites, WSL (4b) is recommended — the project targets Linux
> container runtimes and this avoids path/venv quirks on native Windows.

### 4b. Windows 11 with WSL2 (Ubuntu) — recommended

```powershell
# In PowerShell (Administrator): install WSL2 + Ubuntu, then reboot if prompted
wsl --install -d Ubuntu-24.04
```
Then open the **Ubuntu** app from the Start Menu and follow **4c** below inside it.
Docker Desktop for Windows, if installed, auto-integrates with WSL2 (enable
*Settings → Resources → WSL Integration → Ubuntu-24.04*) so `docker` works
inside WSL without a separate Linux Docker install.

### 4c. Ubuntu 24.04 (WSL or bare metal / cloud VM)

```bash
# 1. System packages
sudo apt update
sudo apt install -y git python3.12 python3.12-venv python3-pip curl unzip

# 2. Docker Engine (skip if using Docker Desktop's WSL integration)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # log out/in (or `newgrp docker`) for this to take effect

# 3. Terraform
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform

# 4. kubectl
curl -LO "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# 5. Clone and install
git clone https://github.com/<your-org>/payo-core-bank.git
cd payo-core-bank
python3.12 -m venv .venv
source .venv/bin/activate
pip install pre-commit==3.8.0
```

### 4d. Install the pre-commit git hook (all platforms, once venv above is active)

```bash
pre-commit install --install-hooks   # registers the hook in .git/hooks/pre-commit
pre-commit run --all-files           # optional: run once now against the whole repo
```
From then on, `git commit` automatically runs ruff, ruff-format, mypy,
terraform fmt/validate, hadolint, and basic hygiene checks (trailing
whitespace, large files, YAML/JSON syntax) on the changed files — the exact
same checks CI enforces, so a broken commit is caught locally before it ever
reaches a PR. To update hook versions later: `pre-commit autoupdate`. To run
a single hook ad hoc: `pre-commit run ruff --all-files`.

### 4e. Troubleshooting the pre-commit hook

**`Neither Terraform nor OpenTofu binary could be found` (Windows, during `git commit`)**
This means `terraform.exe` is not on the `PATH` of the shell/IDE that Git is
running the hook from — usually because Terraform was installed *after* the
current terminal (or VS Code / GitHub Desktop) was opened, and it hasn't
picked up the updated `PATH` yet.
```powershell
winget install --id Hashicorp.Terraform -e
# then CLOSE and REOPEN your terminal (and VS Code, if you commit from there), then verify:
terraform -v
```
If `terraform -v` still fails after reopening, install via Chocolatey instead
(and again open a fresh terminal afterward):
```powershell
choco install terraform -y
```
As a last resort, point the hook at an explicit binary path without touching
`PATH`, by adding `args: ["--tf-path=C:\path\to\terraform.exe"]` under the
`terraform_fmt` / `terraform_validate` hooks in `.pre-commit-config.yaml`.

**`hadolint-docker` fails or hangs**
This hook runs a Docker container, so **Docker Desktop must be running**
(and, on WSL, its *Settings → Resources → WSL Integration* must be enabled
for your distro). If Docker is unavailable in your environment, skip it for
that commit only: `SKIP=hadolint-docker git commit -m "..."` — CI still runs
it, so it isn't a way to permanently bypass the check.

**A hook modifies files and the commit is rejected**
This is expected pre-commit behavior for auto-fixing hooks (`ruff-format`,
`terraform_fmt`, whitespace/EOF fixers): the first run fixes the files and
exits non-zero so you can review the diff; `git add -A && git commit` again
immediately after succeeds since the files are now already compliant.

## 5. Run instructions

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

## 6. CI/CD (`.github/workflows/ci.yml`)

Runs on every PR, each step gating the next:
1. `pre-commit run --all-files` — ruff, black, mypy, terraform fmt/validate, hadolint, end-of-file/whitespace hygiene.
2. `pytest -q` unit tests, matrix over Python 3.11 / 3.12.
3. `pytest -q -m integration` against a real `postgres:16` **GitHub Actions service container** — not mocked, which is what makes the pipeline audit-credible.
4. `docker build` for every service — a non-zero exit fails the job; no image is ever pushed from a broken build.
5. `terraform fmt -check` and `terraform validate` for every environment.

All actions are pinned to a full commit SHA (not a floating tag) so the pipeline is reproducible — the answer to "how do you know what's reviewed is what's running in prod."

## 7. Candidate mapping — Shaikat Majumdar → this JD

| JD requirement | Demonstrated in this repo | Prior real-world basis (resume) |
|---|---|---|
| Core architecture ownership, OCC-grade docs | `services/ledger-core`, `docs/adr/*` | BAM: audit-grade system architecture documentation |
| Ledger ⇄ stablecoin reconciliation | `services/reconciliation-worker`, `docs/adr/0002-three-way-reconciliation.md` | BAM: idempotency & exactly-once processing across financial pipelines |
| Event messaging / mint-burn sync | Transactional outbox in `ledger-core/app/infra/outbox.py` | BAM & JPM: distributed event messaging endpoints |
| Technical leadership / review standards | `.pre-commit-config.yaml`, `CODEOWNERS`, ADR process | JPM/Highbridge: mentored senior engineers, enforced rigorous code review |
| Sanctions screening in transaction path | `services/sanctions-screening`, `PENDING_SCREENING` gate | JPM: IAM/compliance integration for sensitive transaction pipelines |
| Multi-region, K8s, IaC | `infra/terraform`, `infra/k8s` | Millburn: multi-region K8s; JPM: multi-cloud GCP/AWS |
| Audit readiness / evidence generation | `reconciliation-worker/app/evidence.py` | JPM: DR targets & risk in ADRs; BAM: DB-state-vs-log verification |

## 8. Intentionally scoped as a stub (with clear extension points)

This is a portfolio/showcase repo, not production PDB code:
- **On-chain custody** (`ledger-core/app/infra/custody_client.py`) — interface + deterministic mock; a real implementation swaps in a Fireblocks/Anchorage SDK client behind the same `CustodyClient` protocol.
- **Sanctions data source** (`sanctions-screening/app/screening.py`) — mock OFAC-style list; a real implementation swaps in a vendor (Chainalysis/ComplyAdvantage) behind the same `ScreeningProvider` protocol.
- **KMS** — `infra/terraform/modules/kms` declares the key + rotation policy; application-side envelope encryption has a defined interface boundary (`infra/crypto.py`) with a TODO for the vendor SDK.
