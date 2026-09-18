# ADR-0006: Multi-AZ as the Infrastructure Floor, Not an Upgrade

## Status
Accepted

## Context
"Resilience & Observability... multi-region availability, failover targets"
is an explicit JD requirement, and an unplanned single-AZ outage of the
ledger is the kind of incident that ends up in an exam report.

## Decision
Every stateful or scaled component is multi-AZ by default in
`infra/terraform`, not as a prod-only upgrade path:
- VPC: one NAT gateway **per AZ**, not a single shared NAT (`modules/vpc`).
- EKS node group: `node_min_size = 3` across 3 AZs even in `dev`
  (`environments/dev/main.tf`).
- RDS: `multi_az = true` unconditionally (`modules/rds/main.tf`).
- MSK: broker count equals subnet (AZ) count (`modules/msk/main.tf`).
- Kubernetes: `topologySpreadConstraints` on `ledger-core` plus a
  `PodDisruptionBudget` requiring `minAvailable: 2`
  (`infra/k8s/base/ledger-core-deployment.yaml`).

## Alternatives considered
- **Single-AZ dev, multi-AZ prod only.** Rejected: multi-AZ failure modes
  (subnet routing, security group scoping, PDB behavior) are exactly the
  things you want exercised continuously in dev/staging, not discovered for
  the first time during a prod incident.

## Consequences
- Higher baseline cost in dev than a single-AZ setup would have; accepted
  as the cost of catching multi-AZ-specific bugs long before they reach
  production or an examiner's environment walkthrough.
