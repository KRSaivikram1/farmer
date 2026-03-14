"""
Farmer Alert – FastAPI Application
===================================
Core API server providing sensor data ingestion and dashboard retrieval
endpoints for the farm monitoring platform.
"""
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import sessionmaker, Session
from auth import verify_password, get_password_hash, create_access_token
from models import engine, Reading, Sensor, User, Hub  # <-- Added Hub here!
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from auth import SECRET_KEY, ALGORITHM
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import List
import asyncio
import os

# ---------------------------------------------------------------------------
# Database session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

# ---------------------------------------------------------------------------
# Pydantic schemas (request / response)
# ---------------------------------------------------------------------------
class IngestPayload(BaseModel):
    device_eui: str = Field(..., description="Unique Device EUI of the SenseCAP sensor")
    moisture_pct: float = Field(..., description="Soil moisture percentage")
    temperature_c: float = Field(..., description="Temperature in Celsius")
    battery_volts: float = Field(..., description="Battery voltage of the sensor")

class UserCreate(BaseModel):
    username: str
    password: str
    phone_number: str

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_eui: str
    timestamp: datetime
    moisture_pct: float
    temperature_c: float
    battery_volts: float

class IngestResponse(BaseModel):
    status: str
    reading_id: int
    device_eui: str

# --- NEW ADMIN SCHEMAS ---
class HubCreate(BaseModel):
    name: str
    location: str = None

class SensorCreate(BaseModel):
    device_eui: str
    name: str
    hub_id: int

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Farmer Alert API",
    description="Sensor data ingestion and dashboard retrieval for farm monitoring.",
    version="0.1.0",
)

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
origins = allowed_origins_raw.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===========================================================================
# WEBSOCKET MANAGER (Real-Time Enterprise Upgrade)
# ===========================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """The open pipeline for the frontend to listen to."""
    await manager.connect(websocket)
    try:
        while True:
            # We just keep the line open. The frontend doesn't need to speak, just listen.
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def notify_clients():
    """Helper function to shout down the pipeline."""
    await manager.broadcast("NEW_DATA")

# ===========================================================================
# ADMIN ENDPOINTS (Hub & Sensor Management)
# ===========================================================================

@app.post("/api/admin/hubs", summary="Create a new Hub for the farmer")
def create_hub(hub: HubCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Creates a logical grouping (like 'North Field Gateway') owned by this user."""
    new_hub = Hub(name=hub.name, location=hub.location, user_id=current_user.id)
    db.add(new_hub)
    db.commit()
    db.refresh(new_hub)
    return {"message": f"Hub '{new_hub.name}' created with ID: {new_hub.id}"}

@app.post("/api/admin/sensors", summary="Register a new hardware sensor to a Hub")
def register_sensor(sensor: SensorCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Links a physical sensor (device_eui) to a specific Hub."""
    # Security check: Does this hub actually belong to the logged-in user?
    hub = db.query(Hub).filter(Hub.id == sensor.hub_id, Hub.user_id == current_user.id).first()
    if not hub:
        raise HTTPException(status_code=404, detail="Hub not found or you don't own it.")
    
    new_sensor = Sensor(device_eui=sensor.device_eui, name=sensor.name, hub_id=hub.id, is_active=True)
    db.add(new_sensor)
    db.commit()
    return {"message": f"Sensor '{sensor.name}' assigned to Hub '{hub.name}'"}

@app.put("/api/admin/sensors/{device_eui}/deactivate", summary="Soft Delete a broken sensor")
def deactivate_sensor(device_eui: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Flips is_active to False. Keeps historical data, but hides from dashboard widgets."""
    # Find sensor through the user's hub to ensure they have permission to delete it
    sensor = db.query(Sensor).join(Hub).filter(Sensor.device_eui == device_eui, Hub.user_id == current_user.id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found.")
    
    sensor.is_active = False
    db.commit()
    return {"message": f"Sensor {device_eui} successfully deactivated."}

# ===========================================================================
# CORE ENDPOINTS
# ===========================================================================

@app.post("/api/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_reading(payload: IngestPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # NO MORE AUTO-REGISTRATION! The Bouncer checks the guest list.
    sensor = db.query(Sensor).filter(Sensor.device_eui == payload.device_eui).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="Unknown hardware. Please register sensor first.")
    if not sensor.is_active:
        raise HTTPException(status_code=400, detail="This sensor has been deactivated.")

    new_reading = Reading(
        device_eui=payload.device_eui,
        moisture_pct=payload.moisture_pct,
        temperature_c=payload.temperature_c,
        battery_volts=payload.battery_volts,
    )
    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)

    # Alerting Engine
    THRESHOLD = 20.0
    if payload.moisture_pct <= THRESHOLD:
        now = datetime.utcnow()
        if sensor.last_alert_sent is None or (now - sensor.last_alert_sent) >= timedelta(hours=4):
            print("\n" + "="*60)
            print(f"🚨 MOCK SMS SENT TO FARMER 🚨")
            print(f"CRITICAL: Sensor {payload.device_eui} reports soil moisture at {payload.moisture_pct}%!")
            print("="*60 + "\n")
            sensor.last_alert_sent = now
            db.commit()
    # ---------------------------------------------------------
    # ENTERPRISE PUSH: Tell all connected browsers to update!
    # ---------------------------------------------------------
    background_tasks.add_task(notify_clients)

    return IngestResponse(status="ok", reading_id=new_reading.id, device_eui=new_reading.device_eui)


@app.get("/api/sensors/{device_eui}/readings")
def get_sensor_readings(device_eui: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    seventy_two_hours_ago = (datetime.utcnow() - timedelta(hours=72)).isoformat()
    readings = db.query(Reading).filter(
        Reading.device_eui == device_eui,
        Reading.timestamp >= seventy_two_hours_ago
    ).order_by(Reading.timestamp.desc()).all()
    return readings

@app.post("/api/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    new_user = User(username=user.username, password_hash=get_password_hash(user.password), phone_number=user.phone_number)
    db.add(new_user)
    db.commit()
    return {"message": f"Farmer '{user.username}' successfully registered!"}

@app.post("/api/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == form_data.username).first()
    if not db_user or not verify_password(form_data.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": db_user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/dashboard")
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetches widgets ONLY for the current user's ACTIVE sensors."""
    # 3-Tier Join: Get Sensors linked to a Hub that belongs to current_user
    sensors = db.query(Sensor).join(Hub).filter(
        Hub.user_id == current_user.id, 
        Sensor.is_active == True
    ).all()
    
    dashboard_data = []
    for sensor in sensors:
        latest = db.query(Reading).filter(Reading.device_eui == sensor.device_eui).order_by(Reading.timestamp.desc()).first()
        if latest:
            dashboard_data.append({
                "device_eui": sensor.device_eui,
                "name": sensor.name,
                "moisture_pct": latest.moisture_pct,
                "temperature_c": latest.temperature_c,
                "battery_volts": latest.battery_volts
            })
    return dashboard_data

@app.get("/api/dashboard/chart")
def get_chart_data(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Calculates averages using ONLY the current user's sensors."""
    seventy_two_hours_ago = (datetime.utcnow() - timedelta(hours=72)).isoformat()
    
    # 3-Tier Join: Get Readings from Sensors linked to a Hub owned by the user
    readings = db.query(Reading).join(Sensor).join(Hub).filter(
        Hub.user_id == current_user.id,
        Reading.timestamp >= seventy_two_hours_ago
    ).all()
    
    hourly_data: dict[datetime, list[float]] = {}
    for r in readings:
        time_str = str(r.timestamp).replace("Z", "")
        dt_obj = datetime.fromisoformat(time_str)
        hour_bucket = dt_obj.replace(minute=0, second=0, microsecond=0)
        hourly_data.setdefault(hour_bucket, []).append(float(r.moisture_pct))
        
    chart_points = []
    for hour, values in hourly_data.items():
        if len(values) > 0:
            avg: float = sum(values) / len(values)
            rounded_avg: float = int(avg * 10) / 10
            chart_points.append({"timestamp": hour.isoformat() + "Z", "avg_moisture": rounded_avg})
        
    chart_points.sort(key=lambda x: x["timestamp"])
    return chart_points