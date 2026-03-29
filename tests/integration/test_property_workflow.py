"""Integration tests for end-to-end property workflows using the async test client."""

from __future__ import annotations

import pytest


SAMPLE_ADDRESS = {
    "street": "9876 Integration Test Dr",
    "city": "Fairfax",
    "state": "VA",
    "zip_code": "22030",
}


async def _create_property(client, address=None) -> dict:
    """Helper to create a property and return the response dict."""
    r = await client.post("/api/v1/properties", json={
        "address": address or SAMPLE_ADDRESS,
        "property_type": "single_family",
    })
    assert r.status_code == 201
    return r.json()


@pytest.mark.asyncio
async def test_create_and_analyze_property(client):
    """Create a property, run financial analysis, and verify results."""
    # Step 1: Create property
    prop = await _create_property(client)
    prop_id = prop["id"]
    assert prop["property_type"] == "single_family"

    # Step 2: Run financial analysis
    r = await client.post(f"/api/v1/properties/{prop_id}/analysis/financial", json={
        "list_price": 650_000,
        "hoa_monthly": 150.0,
        "down_payment_pcts": [0.10, 0.20],
        "term_years": [30],
    })
    assert r.status_code == 200
    data = r.json()

    # Step 3: Verify financial analysis results
    assert "scenarios" in data
    assert len(data["scenarios"]) == 2  # 2 down payment pcts * 1 term
    assert "payment_breakdowns" in data
    assert "closing_costs" in data
    assert data["closing_costs"]["total"] > 0

    for scenario in data["scenarios"]:
        name = scenario["name"]
        assert name in data["payment_breakdowns"]
        breakdown = data["payment_breakdowns"][name]
        assert breakdown["total"] > 0
        assert breakdown["hoa"] == pytest.approx(150.0, abs=0.01)


@pytest.mark.asyncio
async def test_watchlist_workflow(client):
    """Create a property, add to watchlist, and change stage."""
    # Step 1: Create property
    prop = await _create_property(client)
    prop_id = prop["id"]

    # Step 2: Add to watchlist
    r = await client.post("/api/v1/watchlist", json={
        "property_id": prop_id,
        "stage": "researching",
        "priority": 1,
    })
    assert r.status_code == 201
    entry = r.json()
    assert entry["property_id"] == prop_id
    assert entry["stage"] == "researching"
    entry_id = entry["id"]

    # Step 3: Change stage
    r = await client.patch(f"/api/v1/watchlist/{entry_id}", json={
        "stage": "touring",
    })
    assert r.status_code == 200
    updated = r.json()
    assert updated["stage"] == "touring"

    # Step 4: Verify it appears in filtered list
    r = await client.get("/api/v1/watchlist", params={"stage": "touring"})
    assert r.status_code == 200
    entries = r.json()
    assert any(e["id"] == entry_id for e in entries)


@pytest.mark.asyncio
async def test_notes_workflow(client):
    """Create a property, add a note, and list notes."""
    # Step 1: Create property
    prop = await _create_property(client)
    prop_id = prop["id"]

    # Step 2: Add a note
    r = await client.post(f"/api/v1/properties/{prop_id}/notes", json={
        "content": "Toured the property. Kitchen needs updating but great yard.",
        "note_type": "showing",
    })
    assert r.status_code == 201
    note = r.json()
    assert note["property_id"] == prop_id
    assert note["content"] == "Toured the property. Kitchen needs updating but great yard."
    assert note["note_type"] == "showing"

    # Step 3: Add another note
    r = await client.post(f"/api/v1/properties/{prop_id}/notes", json={
        "content": "Seller is motivated — may accept below asking.",
        "note_type": "general",
    })
    assert r.status_code == 201

    # Step 4: List notes
    r = await client.get(f"/api/v1/properties/{prop_id}/notes")
    assert r.status_code == 200
    notes = r.json()
    assert len(notes) == 2

    # Notes should be newest first
    assert notes[0]["note_type"] == "general"
    assert notes[1]["note_type"] == "showing"
