import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_clear_decision_for_unlisted_party(client):
    resp = await client.post(
        "/screen",
        json={"transaction_id": "t1", "party_name": "Ordinary Business LLC", "party_ref": "r1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "CLEAR"
    assert body["case_id"] is None


@pytest.mark.asyncio
async def test_hold_decision_opens_a_case(client):
    resp = await client.post(
        "/screen",
        json={
            "transaction_id": "t2",
            "party_name": "Acme Sanctioned Holdings Ltd",
            "party_ref": "r2",
        },
    )
    body = resp.json()
    assert body["decision"] == "HOLD"
    assert body["case_id"] is not None
    assert "acme sanctioned holdings" in body["matched_terms"]

    case = await client.get(f"/cases/{body['case_id']}")
    assert case.status_code == 200
    assert case.json()["status"] == "OPEN"


@pytest.mark.asyncio
async def test_case_resolution_lifecycle(client):
    screened = (
        await client.post(
            "/screen",
            json={
                "transaction_id": "t3",
                "party_name": "Restricted Trading Co",
                "party_ref": "r3",
            },
        )
    ).json()
    case_id = screened["case_id"]

    resolved = await client.post(f"/cases/{case_id}/resolve", params={"resolution": "CLEARED"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "CLEARED"

    bad = await client.post(f"/cases/{case_id}/resolve", params={"resolution": "NONSENSE"})
    assert bad.status_code == 422
