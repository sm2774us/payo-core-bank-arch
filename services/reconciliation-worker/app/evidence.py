"""Generates a signed, timestamped evidence bundle from a reconciliation run.

This is the artifact an examiner or auditor actually asks for: not "we ran a
reconciliation," but "here is the exact input snapshot, the computed result,
a hash binding them together, and who/what produced it."

The signature here is a placeholder HMAC over a canonical JSON encoding, with
a clearly marked seam (`sign()`) for swapping in a KMS-backed asymmetric
signature in a real deployment — see infra/terraform/modules/kms.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def _default_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ReconciliationInput:
    reserve_balance: Decimal
    onchain_mirror_balance: Decimal
    onchain_actual_supply: Decimal


@dataclass(frozen=True)
class EvidenceBundle:
    run_id: str
    generated_at: str
    inputs: ReconciliationInput
    reserve_vs_mirror_break: Decimal
    mirror_vs_onchain_break: Decimal
    is_balanced: bool
    generated_by: str
    signature: str = field(default="")

    def to_canonical_json(self) -> str:
        payload = {
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "inputs": {k: str(v) for k, v in asdict(self.inputs).items()},
            "reserve_vs_mirror_break": str(self.reserve_vs_mirror_break),
            "mirror_vs_onchain_break": str(self.mirror_vs_onchain_break),
            "is_balanced": self.is_balanced,
            "generated_by": self.generated_by,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign(payload: str, secret_key: bytes) -> str:
    """Placeholder HMAC-SHA256 signature.

    TODO(prod): replace with an asymmetric signature (e.g. ECDSA over a KMS
    key, see infra/terraform/modules/kms) so verification does not require
    possessing the signing secret — required for third-party auditor
    verification without extending trust to the signer's key material.
    """
    return hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()


def build_evidence_bundle(
    *,
    run_id: str,
    reserve_balance: Decimal,
    onchain_mirror_balance: Decimal,
    onchain_actual_supply: Decimal,
    generated_by: str,
    secret_key: bytes,
    generated_at: str | None = None,
) -> EvidenceBundle:
    bundle = EvidenceBundle(
        run_id=run_id,
        generated_at=generated_at or _default_now(),
        inputs=ReconciliationInput(
            reserve_balance=reserve_balance,
            onchain_mirror_balance=onchain_mirror_balance,
            onchain_actual_supply=onchain_actual_supply,
        ),
        reserve_vs_mirror_break=reserve_balance - onchain_mirror_balance,
        mirror_vs_onchain_break=onchain_mirror_balance - onchain_actual_supply,
        is_balanced=(
            reserve_balance == onchain_mirror_balance == onchain_actual_supply
        ),
        generated_by=generated_by,
    )
    signature = sign(bundle.to_canonical_json(), secret_key)
    return EvidenceBundle(
        **{**asdict(bundle), "inputs": bundle.inputs, "signature": signature}
    )


def verify_evidence_bundle(bundle: EvidenceBundle, secret_key: bytes) -> bool:
    expected = sign(bundle.to_canonical_json(), secret_key)
    return hmac.compare_digest(expected, bundle.signature)
