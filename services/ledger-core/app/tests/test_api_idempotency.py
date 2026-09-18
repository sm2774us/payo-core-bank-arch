import pytest


@pytest.mark.asyncio
async def test_create_account_and_transaction_flow(client):
    fiat = (
        await client.post("/accounts", json={"name": "cust-1", "account_type": "CUSTOMER_FIAT"})
    ).json()
    reserve = (
        await client.post("/accounts", json={"name": "reserve-1", "account_type": "RESERVE"})
    ).json()

    body = {
        "reference": "dep-100",
        "description": "test deposit",
        "legs": [
            {"account_id": fiat["id"], "direction": "DEBIT", "amount": "250"},
            {"account_id": reserve["id"], "direction": "CREDIT", "amount": "250"},
        ],
    }
    resp1 = await client.post(
        "/transactions", json=body, headers={"Idempotency-Key": "key-abc"}
    )
    assert resp1.status_code == 201
    txn1 = resp1.json()
    assert txn1["state"] == "PENDING_SCREENING"

    # Replaying the SAME key + SAME body must return the original result, not
    # create a second transaction (exactly-once).
    resp2 = await client.post(
        "/transactions", json=body, headers={"Idempotency-Key": "key-abc"}
    )
    assert resp2.status_code == 201
    assert resp2.json()["id"] == txn1["id"]

    from decimal import Decimal

    balance = await client.get(f"/accounts/{fiat['id']}/balance")
    assert Decimal(balance.json()["balance"]) == Decimal("-250")


@pytest.mark.asyncio
async def test_reused_idempotency_key_with_different_body_is_rejected(client):
    fiat = (
        await client.post("/accounts", json={"name": "cust-2", "account_type": "CUSTOMER_FIAT"})
    ).json()
    reserve = (
        await client.post("/accounts", json={"name": "reserve-2", "account_type": "RESERVE"})
    ).json()

    def body(amount: str) -> dict:
        return {
            "reference": f"dep-{amount}",
            "legs": [
                {"account_id": fiat["id"], "direction": "DEBIT", "amount": amount},
                {"account_id": reserve["id"], "direction": "CREDIT", "amount": amount},
            ],
        }

    r1 = await client.post(
        "/transactions", json=body("10"), headers={"Idempotency-Key": "shared-key"}
    )
    assert r1.status_code == 201

    r2 = await client.post(
        "/transactions", json=body("99"), headers={"Idempotency-Key": "shared-key"}
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_unbalanced_transaction_is_rejected(client):
    fiat = (
        await client.post("/accounts", json={"name": "cust-3", "account_type": "CUSTOMER_FIAT"})
    ).json()
    reserve = (
        await client.post("/accounts", json={"name": "reserve-3", "account_type": "RESERVE"})
    ).json()

    body = {
        "reference": "bad-dep",
        "legs": [
            {"account_id": fiat["id"], "direction": "DEBIT", "amount": "100"},
            {"account_id": reserve["id"], "direction": "CREDIT", "amount": "50"},
        ],
    }
    resp = await client.post(
        "/transactions", json=body, headers={"Idempotency-Key": "unbalanced-1"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_screening_gate_must_pass_before_posted(client):
    fiat = (
        await client.post("/accounts", json={"name": "cust-4", "account_type": "CUSTOMER_FIAT"})
    ).json()
    reserve = (
        await client.post("/accounts", json={"name": "reserve-4", "account_type": "RESERVE"})
    ).json()
    body = {
        "reference": "dep-200",
        "legs": [
            {"account_id": fiat["id"], "direction": "DEBIT", "amount": "300"},
            {"account_id": reserve["id"], "direction": "CREDIT", "amount": "300"},
        ],
    }
    created = (
        await client.post("/transactions", json=body, headers={"Idempotency-Key": "scr-1"})
    ).json()
    assert created["state"] == "PENDING_SCREENING"

    decided = await client.post(
        f"/transactions/{created['id']}/screening-decision",
        json={"decision": "CLEAR", "screened_by": "compliance-officer-1"},
    )
    assert decided.status_code == 200
    assert decided.json()["state"] == "POSTED"

    # Cannot re-screen a transaction that has already left PENDING_SCREENING.
    re_decided = await client.post(
        f"/transactions/{created['id']}/screening-decision",
        json={"decision": "CLEAR", "screened_by": "compliance-officer-1"},
    )
    assert re_decided.status_code == 409


@pytest.mark.asyncio
async def test_screening_hold_path(client):
    fiat = (
        await client.post("/accounts", json={"name": "cust-5", "account_type": "CUSTOMER_FIAT"})
    ).json()
    reserve = (
        await client.post("/accounts", json={"name": "reserve-5", "account_type": "RESERVE"})
    ).json()
    body = {
        "reference": "dep-300",
        "legs": [
            {"account_id": fiat["id"], "direction": "DEBIT", "amount": "1000"},
            {"account_id": reserve["id"], "direction": "CREDIT", "amount": "1000"},
        ],
    }
    created = (
        await client.post("/transactions", json=body, headers={"Idempotency-Key": "hold-1"})
    ).json()

    decided = await client.post(
        f"/transactions/{created['id']}/screening-decision",
        json={"decision": "HOLD", "screened_by": "compliance-officer-2", "rationale": "watchlist hit"},
    )
    assert decided.json()["state"] == "SCREENED_HOLD"
