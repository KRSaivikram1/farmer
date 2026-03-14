import requests
import time
import math
import random

# Configuration
API_URL = "https://farmer-alert-api.onrender.com/api/ingest"

# Settings for the 3-hour cycle
TOTAL_STEPS = 180  # 180 minutes = 3 hours

sensors: dict[str, dict[str, float]] = {
    "SENSOR_A_001": {"base_m": 65.0, "temp": 24.0, "battery": 3.7},
    "SENSOR_B_002": {"base_m": 45.0, "temp": 25.5, "battery": 3.8},
    "SENSOR_C_003": {"base_m": 35.0, "temp": 22.0, "battery": 4.1}, 
}

def send_reading(device_id: str, moisture: float, temp: float, battery: float) -> bool:
    payload = {
        "device_eui": device_id,
        "moisture_pct": round(moisture, 1),
        "temperature_c": round(temp, 1),
        "battery_volts": round(battery, 2)
    }
    try:
        response = requests.post(API_URL, json=payload)
        return response.status_code == 201
    except Exception:
        return False

def main() -> None:
    print("🌊 STARTING 3-HOUR IRRIGATION CYCLE SIMULATION")
    print("Phase 1: Drying out... | Phase 2: Watering...")

    for current_step in range(TOTAL_STEPS + 1):
        # Use a cosine wave to create the "Down then Up" shape
        # The curve will hit its lowest point at step 90 (90 minutes in)
        curve_factor = math.cos(2 * math.pi * (current_step / TOTAL_STEPS))
        
        # This factor goes from 1.0 down to -1.0 and back to 1.0
        # We'll map it so the moisture drops by ~15-20% and then recovers
        offset = (1.0 - curve_factor) * 10.0 
        
        for device_id, state in sensors.items():
            # Calculate new moisture based on the curve
            current_moisture = state["base_m"] - offset + random.uniform(-0.5, 0.5)
            
            # Ensure we don't go below 0
            if current_moisture < 0: current_moisture = 0
            
            success = send_reading(device_id, current_moisture, state["temp"], state["battery"])
            
            if success:
                status = "📉 Drying" if current_step < 90 else "📈 Watering"
                print(f"[{status}] {device_id}: {round(current_moisture, 1)}% (Step {current_step}/180)")

        time.sleep(60) # Send one update every minute

if __name__ == "__main__":
    main()