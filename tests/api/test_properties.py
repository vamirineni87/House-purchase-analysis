"""API tests for property CRUD endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Health endpoint returns ok."""
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_property(client):
    """POST /properties creates a property with address."""
    r = await client.post("/api/v1/properties", json={
        "address": {
            "street": "12345 Fairfax Blvd",
            "city": "Fairfax",
            "state": "VA",
            "zip_code": "22030",
        },
        "property_type": "single_family",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["property_type"] == "single_family"
    assert len(data["addresses"]) == 1
    assert data["addresses"][0]["county"] == "fairfax"
    assert data["addresses"][0]["is_current"] is True
    assert "FAIRFAX" in data["addresses"][0]["normalized_address"]


@pytest.mark.asyncio
async def test_create_loudoun_property(client):
    """County detection works for Loudoun addresses."""
    r = await client.post("/api/v1/properties", json={
        "address": {
            "street": "456 Ashburn Village Blvd",
            "city": "Ashburn",
            "state": "VA",
            "zip_code": "20147",
        },
    })
    assert r.status_code == 201
    assert r.json()["addresses"][0]["county"] == "loudoun"


@pytest.mark.asyncio
async def test_list_properties(client):
    """GET /properties returns list."""
    # Create two
    await client.post("/api/v1/properties", json={
        "address": {"street": "111 A St", "city": "Fairfax", "state": "VA", "zip_code": "22030"},
    })
    await client.post("/api/v1/properties", json={
        "address": {"street": "222 B St", "city": "Ashburn", "state": "VA", "zip_code": "20147"},
    })

    r = await client.get("/api/v1/properties")
    assert r.status_code == 200
    assert len(r.json()) >= 2


@pytest.mark.asyncio
async def test_get_property_by_id(client):
    """GET /properties/{id} returns full property."""
    r = await client.post("/api/v1/properties", json={
        "address": {"street": "333 C St", "city": "Fairfax", "state": "VA", "zip_code": "22030"},
    })
    prop_id = r.json()["id"]

    r = await client.get(f"/api/v1/properties/{prop_id}")
    assert r.status_code == 200
    assert r.json()["id"] == prop_id


@pytest.mark.asyncio
async def test_get_nonexistent_property(client):
    """GET /properties/{id} returns 404 for unknown ID."""
    r = await client.get("/api/v1/properties/nonexistent-uuid")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_property(client):
    """DELETE /properties/{id} removes property."""
    r = await client.post("/api/v1/properties", json={
        "address": {"street": "444 D St", "city": "Fairfax", "state": "VA", "zip_code": "22030"},
    })
    prop_id = r.json()["id"]

    r = await client.delete(f"/api/v1/properties/{prop_id}")
    assert r.status_code == 204

    r = await client.get(f"/api/v1/properties/{prop_id}")
    assert r.status_code == 404
