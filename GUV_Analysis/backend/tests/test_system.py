from fastapi.testclient import TestClient

def test_system_stats(client: TestClient):
    response = client.get("/api/system/stats")
    assert response.status_code == 200
    data = response.json()
    assert "cpu" in data
    assert "percent" in data["cpu"]
    assert "memory" in data
    assert "percent" in data["memory"]

def test_system_config_crud(client: TestClient):
    # Create
    config_data = {
        "key": "test.config",
        "value": "123",
        "description": "Test Config"
    }
    response = client.post("/api/system/config", json=config_data)
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "test.config"
    assert data["value"] == "123"

    # Read
    response = client.get("/api/system/config")
    assert response.status_code == 200
    configs = response.json()
    assert len(configs) >= 1
    assert any(c["key"] == "test.config" for c in configs)

    # Update
    update_data = {
        "value": "456",
        "description": "Updated"
    }
    response = client.put("/api/system/config/test.config", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "456"

    # Delete
    response = client.delete("/api/system/config/test.config")
    assert response.status_code == 200
    
    # Verify Delete
    response = client.get("/api/system/config")
    configs = response.json()
    assert not any(c["key"] == "test.config" for c in configs)
