"""
Farmer Alert – FastAPI Application
===================================
Core API server providing sensor data ingestion and dashboard retrieval
endpoints for the farm monitoring platform.
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta

from models import engine, Reading, Sensor

# ---------------------------------------------------------------------------
# Database session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Yield a SQLAlchemy session for the lifetime of a single request,
    then close it automatically – even if the request raises an error.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pydantic schemas (request / response)
# ---------------------------------------------------------------------------
class IngestPayload(BaseModel):
    """Schema for the incoming sensor reading payload."""
    device_eui: str = Field(..., description="Unique Device EUI of the SenseCAP sensor")
    moisture_pct: float = Field(..., description="Soil moisture percentage")
    temperature_c: float = Field(..., description="Temperature in Celsius")
    battery_volts: float = Field(..., description="Battery voltage of the sensor")


class ReadingOut(BaseModel):
    """Schema returned for each stored reading."""
    id: int
    device_eui: str
    timestamp: datetime
    moisture_pct: float
    temperature_c: float
    battery_volts: float

    class Config:
        from_attributes = True          # allows direct ORM → Pydantic conversion


class IngestResponse(BaseModel):
    """Acknowledgement returned after a successful ingestion."""
    status: str
    reading_id: int
    device_eui: str


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Farmer Alert API",
    description="Sensor data ingestion and dashboard retrieval for farm monitoring.",
    version="0.1.0",
)

# Allow a local frontend (e.g. React/Vite on port 5173 or plain HTML on 3000)
# to communicate with this API without CORS errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoint 1 – Ingestion (UPGRADED WITH ALERTING ENGINE)
# ---------------------------------------------------------------------------
@app.post(
    "/api/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a new sensor reading and trigger alerts",
)
def ingest_reading(payload: IngestPayload, db: Session = Depends(get_db)):
    # 1. Save the reading to the database
    new_reading = Reading(
        device_eui=payload.device_eui,
        moisture_pct=payload.moisture_pct,
        temperature_c=payload.temperature_c,
        battery_volts=payload.battery_volts,
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

    # ---------------------------------------------------------
    # THE ALERTING ENGINE
    # ---------------------------------------------------------
    THRESHOLD = 20.0
    COOLDOWN_HOURS = 4

    # Only run the complex checks if the moisture is critically low
    if payload.moisture_pct <= THRESHOLD:
        
        # Check if this sensor is registered in our database
        sensor = db.query(Sensor).filter(Sensor.device_eui == payload.device_eui).first()
        
        # Auto-register for testing purposes if it doesn't exist
        if not sensor:
            sensor = Sensor(device_eui=payload.device_eui, name="Test Field Sensor")
            db.add(sensor)
            db.commit()
            db.refresh(sensor)

        now = datetime.utcnow()
        send_alert = False

        # Check the cooldown timer
        if sensor.last_alert_sent is None:
            send_alert = True  # Never sent an alert before
        else:
            time_since_last = now - sensor.last_alert_sent
            if time_since_last >= timedelta(hours=COOLDOWN_HOURS):
                send_alert = True # Cooldown has expired
            else:
                print(f"[-] Alert suppressed for {payload.device_eui}. Cooldown active.")

        # Trigger the Mock SMS
        if send_alert:
            print("\n" + "="*60)
            print(f"🚨 MOCK SMS SENT TO FARMER 🚨")
            print(f"CRITICAL: Sensor {payload.device_eui} reports soil moisture at {payload.moisture_pct}%!")
            print("="*60 + "\n")
            
            # Update the database so it knows we just sent a text
            sensor.last_alert_sent = now
            db.commit()

    return IngestResponse(
        status="ok",
        reading_id=new_reading.id,
        device_eui=new_reading.device_eui,
    )


# ---------------------------------------------------------------------------
# Endpoint 2 – Dashboard (recent readings)
# ---------------------------------------------------------------------------
@app.get(
    "/api/sensors/{device_eui}/readings",
    response_model=list[ReadingOut],
    summary="Get recent readings for a sensor",
)
def get_sensor_readings(device_eui: str, db: Session = Depends(get_db)):
    """
    Return the **last 50 readings** for the sensor identified by `device_eui`,
    ordered from newest to oldest.

    Raises 404 if no readings exist for the given device.
    """
    readings = (
        db.query(Reading)
        .filter(Reading.device_eui == device_eui)
        .order_by(Reading.timestamp.desc())
        .limit(50)
        .all()
    )

    if not readings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No readings found for device '{device_eui}'.",
        )

    return readings
