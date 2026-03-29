"""API tests for analysis and rates endpoints."""

from __future__ import annotations

import pytest


async def _create_property(client) -> str:
    """Helper: create a property and return its ID."""
    r = await client.post("/api/v1/properties", json={
        "address": {
            "street": "555 Analysis Test Ln",
            "city": "Fairfax",
            "state": "VA",
            "zip_code": "22030",
        },
        "property_type": "single_family",
    })
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.asyncio
async def test_financial_analysis_endpoint(client):
    """POST financial analysis with valid data returns 200 and expected structure."""
    prop_id = await _create_property(client)

    r = await client.post(f"/api/v1/properties/{prop_id}/analysis/financial", json={
        "list_price": 550_000,
        "hoa_monthly": 100.0,
    })
    assert r.status_code == 200
    data = r.json()

    # Verify top-level keys
    assert "scenarios" in data
    assert "payment_breakdowns" in data
    assert "closing_costs" in data
    assert "cash_needed_at_closing" in data

    # Verify scenarios were generated
    assert len(data["scenarios"]) >= 2
    for scenario in data["scenarios"]:
        assert "name" in scenario
        assert "loan_amount" in scenario
        assert scenario["loan_amount"] > 0

    # Verify closing costs sum
    cc = data["closing_costs"]
    assert cc["total"] > 0


@pytest.mark.asyncio
async def test_financial_analysis_404(client):
    """POST financial analysis with a nonexistent property_id returns 404."""
    r = await client.post(
        "/api/v1/properties/nonexistent-uuid/analysis/financial",
        json={
            "list_price": 500_000,
        },
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rates_endpoint(client):
    """GET /rates/mortgage returns current mortgage rates."""
    r = await client.get("/api/v1/rates/mortgage")
    assert r.status_code == 200
    data = r.json()

    assert "rate_30yr" in data
    assert "rate_15yr" in data
    assert data["rate_30yr"] > 0
    assert data["rate_15yr"] > 0
    # 15-year rate should typically be lower than 30-year
    assert data["rate_15yr"] <= data["rate_30yr"]
