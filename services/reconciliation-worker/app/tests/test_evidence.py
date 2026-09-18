from decimal import Decimal

from app.evidence import build_evidence_bundle, verify_evidence_bundle

SECRET = b"test-secret-key"


def test_balanced_reconciliation_produces_verifiable_bundle():
    bundle = build_evidence_bundle(
        run_id="run-1",
        reserve_balance=Decimal("1000"),
        onchain_mirror_balance=Decimal("1000"),
        onchain_actual_supply=Decimal("1000"),
        generated_by="reconciliation-worker@v0.1.0",
        secret_key=SECRET,
    )
    assert bundle.is_balanced is True
    assert bundle.reserve_vs_mirror_break == Decimal("0")
    assert verify_evidence_bundle(bundle, SECRET) is True


def test_unbalanced_reconciliation_reports_exact_break_amounts():
    bundle = build_evidence_bundle(
        run_id="run-2",
        reserve_balance=Decimal("1000"),
        onchain_mirror_balance=Decimal("950"),
        onchain_actual_supply=Decimal("900"),
        generated_by="reconciliation-worker@v0.1.0",
        secret_key=SECRET,
    )
    assert bundle.is_balanced is False
    assert bundle.reserve_vs_mirror_break == Decimal("50")
    assert bundle.mirror_vs_onchain_break == Decimal("50")


def test_tampering_with_bundle_invalidates_signature():
    bundle = build_evidence_bundle(
        run_id="run-3",
        reserve_balance=Decimal("500"),
        onchain_mirror_balance=Decimal("500"),
        onchain_actual_supply=Decimal("500"),
        generated_by="reconciliation-worker@v0.1.0",
        secret_key=SECRET,
    )
    assert verify_evidence_bundle(bundle, SECRET) is True

    from dataclasses import replace

    tampered = replace(bundle, reserve_vs_mirror_break=Decimal("999"))
    assert verify_evidence_bundle(tampered, SECRET) is False


def test_verification_fails_with_wrong_key():
    bundle = build_evidence_bundle(
        run_id="run-4",
        reserve_balance=Decimal("10"),
        onchain_mirror_balance=Decimal("10"),
        onchain_actual_supply=Decimal("10"),
        generated_by="reconciliation-worker@v0.1.0",
        secret_key=SECRET,
    )
    assert verify_evidence_bundle(bundle, b"wrong-key") is False
