import requests
import time
import random

# Point this directly to your FastAPI Ingestion Endpoint
API_URL = "http://127.0.0.1:8000/api/ingest"

# Let's set up 3 simulated sensors with starting values
sensors = {
    "SENSOR_A_001": {"moisture": 50.0, "temp": 24.0, "battery": 3.7},
    "SENSOR_B_002": {"moisture": 35.0, "temp": 25.5, "battery": 3.8},
    "SENSOR_C_003": {"moisture": 25.0, "temp": 22.0, "battery": 4.1}, 
}

print("🌱 Starting Farmer Alert IoT Simulator...")
print("Press Ctrl+C to stop.\n")

while True:
    for device_id, state in sensors.items():
        # 1. Simulate the sun drying out the soil (drops by 0.5% to 2.0% each tick)
        state["moisture"] -= random.uniform(0.5, 2.0)
        
        # Prevent it from going below 0%
        if state["moisture"] < 0:
            state["moisture"] = 0.0
            
        # 2. Add slight random fluctuations for temperature and battery decay
        state["temp"] += random.uniform(-0.5, 0.5)
        state["battery"] -= random.uniform(0.001, 0.005)

        # 3. Package it into the exact JSON shape your API expects
        payload = {
            "device_eui": device_id,
            "moisture_pct": round(state["moisture"], 1),
            "temperature_c": round(state["temp"], 1),
            "battery_volts": round(state["battery"], 2)
        }

        # 4. Fire it over the internet to your backend!
        try:
            response = requests.post(API_URL, json=payload)
            if response.status_code == 201:
                print(f"[SUCCESS] {device_id} reported Moisture: {payload['moisture_pct']}%")
            else:
                print(f"[ERROR] {device_id} rejected: {response.text}")
        except Exception as e:
            print(f"[CONNECTION ERROR] Is your FastAPI server running? ({e})")

    # Wait 10 seconds before the next reading. 
    # (In real life, this would be 300 seconds for a 5-minute interval)
    print("\nWaiting 10 seconds before next broadcast...\n")
    time.sleep(10)