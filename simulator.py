import requests
import time
import random
from datetime import datetime, timedelta

# Configuration
API_URL = "https://farmer-alert-api.onrender.com/api/ingest"

sensors = {
    "SENSOR_A_001": {"moisture": 65.0, "temp": 24.0, "battery": 3.7},
    "SENSOR_B_002": {"moisture": 45.0, "temp": 25.5, "battery": 3.8},
    "SENSOR_C_003": {"moisture": 35.0, "temp": 22.0, "battery": 4.1}, 
}

def send_reading(device_id, moisture, temp, battery, custom_time=None):
    payload = {
        "device_eui": device_id,
        "moisture_pct": round(moisture, 1),
        "temperature_c": round(temp, 1),
        "battery_volts": round(battery, 2)
    }
    # If we want to simulate the past, we'd need to change the API, 
    # but for now, we'll just send them fast to fill the current hour 
    # and then let the real-time loop create the "trend" forward.
    try:
        response = requests.post(API_URL, json=payload)
        return response.status_code == 201
    except Exception as e:
        print(f"Connection Error: {e}")
        return False

print("⏳ BACKFILL MODE: Generating 6 hours of historical trend...")

# We will simulate 36 points (one every 10 mins for 6 hours)
for i in range(36):
    for device_id, state in sensors.items():
        # Gradually dry out the soil
        state["moisture"] -= random.uniform(0.1, 0.4)
        state["temp"] += random.uniform(-0.2, 0.2)
        
        # In a real backfill, we'd send timestamps. 
        # Since our API auto-stamps 'now', we will just send these rapidly.
        # This will create a cluster of data that the graph will start to trend.
        send_reading(device_id, state["moisture"], state["temp"], state["battery"])
    
    # Small sleep so we don't overwhelm the API free tier
    time.sleep(0.5) 

print("\n✅ Backfill complete. Starting LIVE REAL-TIME mode...")
print("The graph will now grow a new point every few minutes.\n")

while True:
    for device_id, state in sensors.items():
        state["moisture"] -= random.uniform(0.01, 0.05)
        if state["moisture"] < 0: state["moisture"] = 0
        
        success = send_reading(device_id, state["moisture"], state["temp"], state["battery"])
        if success:
            print(f"[SUCCESS] {device_id}: {state['moisture']}%")
            
    time.sleep(60) # Increased to 60s to see the graph 'step' better