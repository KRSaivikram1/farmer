from fastapi.testclient import TestClient
from main import app

# Create a mock client to talk to your API
client = TestClient(app)

def test_ingestion_endpoint_success():
    """Test that a valid sensor reading is accepted and returns 201."""
    payload = {
        "device_eui": "TEST_SENSOR_999",
        "moisture_pct": 45.0,
        "temperature_c": 22.5,
        "battery_volts": 3.7
    }
    
    # Send a fake POST request directly to the API
    response = client.post("/api/ingest", json=payload)
    
    # 1. Assert the server accepted it (201 Created)
    assert response.status_code == 201
    
    # 2. Assert the server responded with the correct data structure
    data = response.json()
    assert data["status"] == "ok"
    assert data["device_eui"] == "TEST_SENSOR_999"
    assert "reading_id" in data

def test_ingestion_endpoint_missing_data():
    """Test that the API cleanly rejects bad data (e.g., missing moisture)."""
    bad_payload = {
        "device_eui": "TEST_SENSOR_999",
        # Intentionally leaving out moisture_pct!
        "temperature_c": 22.5,
        "battery_volts": 3.7
    }
    
    response = client.post("/api/ingest", json=bad_payload)
    
    # Assert the server blocks it as a Bad Request (422 Unprocessable Entity)
    assert response.status_code == 422

def test_ingestion_critical_alert_threshold():
    """Test that the system accepts a critical reading (moisture <= 20%)."""
    payload = {
        "device_eui": "TEST_CRITICAL_001",
        "moisture_pct": 15.0,  # Below the 20% threshold!
        "temperature_c": 28.0,
        "battery_volts": 3.2
    }
    
    response = client.post("/api/ingest", json=payload)
    
    # The server should still accept the data (201) and process the alert behind the scenes
    assert response.status_code == 201
    assert response.json()["device_eui"] == "TEST_CRITICAL_001"

def test_dashboard_security_no_token():
    """Test that a user CANNOT access the dashboard without a valid JWT token."""
    # Attempting to fetch dashboard data without logging in
    response = client.get("/api/dashboard")
    
    # The Bouncer should block this and return 401 Unauthorized
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_chart_data_security_no_token():
    """Test that a user CANNOT access the 24-hour chart data without a token."""
    response = client.get("/api/dashboard/chart")
    
    assert response.status_code == 401