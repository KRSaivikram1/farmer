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
from models import engine, Reading, Sensor, User, Farm  # <-- Swapped Hub for Farm!
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
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    
    # Check by email instead of username
    user = db.query(User).filter(User.email == email).first()
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

# Updated User Schema for B2B
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str

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

# --- UPDATED ADMIN SCHEMAS ---
class FarmCreate(BaseModel):
    farm_name: str
    location: str = None

class SensorCreate(BaseModel):
    device_eui: str
    name: str
    farm_id: int
    moisture_threshold: int = 20

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
# WEBSOCKET MANAGER
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
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def notify_clients():
    await manager.broadcast("NEW_DATA")

# ===========================================================================
# ADMIN ENDPOINTS (Farm & Sensor Management)
# ===========================================================================

@app.post("/api/admin/farms", summary="Create a new Farm for the client")
def create_farm(farm: FarmCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_farm = Farm(farm_name=farm.farm_name, location=farm.location, user_id=current_user.id)
    db.add(new_farm)
    db.commit()
    db.refresh(new_farm)
    return {"message": f"Farm '{new_farm.farm_name}' created!"}

@app.post("/api/admin/sensors", summary="Register a hardware sensor to a Farm")
def register_sensor(sensor: SensorCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Security check: Does this farm belong to the logged-in user?
    farm = db.query(Farm).filter(Farm.id == sensor.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found or unauthorized.")
    
    new_sensor = Sensor(device_eui=sensor.device_eui, name=sensor.name, farm_id=farm.id, moisture_threshold=sensor.moisture_threshold, is_active=True)
    db.add(new_sensor)
    db.commit()
    return {"message": f"Sensor '{sensor.name}' assigned to Farm '{farm.farm_name}'"}

@app.put("/api/admin/sensors/{device_eui}/deactivate", summary="Soft Delete a broken sensor")
def deactivate_sensor(device_eui: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Find sensor through the user's farm to ensure permission
    sensor = db.query(Sensor).join(Farm).filter(Sensor.device_eui == device_eui, Farm.user_id == current_user.id).first()
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

    # Use the dynamic threshold we added to the DB!
    if payload.moisture_pct <= sensor.moisture_threshold:
        now = datetime.utcnow()
        # Ensure we only send one text per 4 hours
        if not hasattr(sensor, 'last_alert_sent') or sensor.last_alert_sent is None or (now - sensor.last_alert_sent) >= timedelta(hours=4):
            print("\n" + "="*60)
            print(f"🚨 SMS SENT: Sensor {payload.device_eui} reports moisture at {payload.moisture_pct}% (Below {sensor.moisture_threshold}% Threshold)")
            print("="*60 + "\n")
            # Update alert logic here when added to DB model
            db.commit()

    background_tasks.add_task(notify_clients)
    return IngestResponse(status="ok", reading_id=new_reading.id, device_eui=new_reading.device_eui)

@app.get("/api/sensors/{device_eui}/readings")
def get_sensor_readings(device_eui: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    seventy_two_hours_ago = (datetime.utcnow() - timedelta(hours=72)).isoformat()
    readings = db.query(Reading).join(Sensor).join(Farm).filter(
        Reading.device_eui == device_eui,
        Farm.user_id == current_user.id, # STRICT SECURITY: Must own the farm
        Reading.timestamp >= seventy_two_hours_ago
    ).order_by(Reading.timestamp.desc()).all()
    return readings

@app.post("/api/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = User(email=user.email, password_hash=get_password_hash(user.password), full_name=user.full_name)
    db.add(new_user)
    db.commit()
    return {"message": f"Farmer '{user.full_name}' successfully registered!"}

@app.post("/api/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm always uses 'username' for the field name, but we pass the email into it
    db_user = db.query(User).filter(User.email == form_data.username).first()
    if not db_user or not verify_password(form_data.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/dashboard")
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetches widgets ONLY for the current user's ACTIVE sensors."""
    sensors = db.query(Sensor).join(Farm).filter(
        Farm.user_id == current_user.id, 
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
                "battery_volts": latest.battery_volts,
                "last_reading_time": latest.timestamp.isoformat() if latest.timestamp else None
            })
    return dashboard_data

@app.get("/api/dashboard/chart")
def get_chart_data(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Calculates averages using ONLY the current user's sensors."""
    seventy_two_hours_ago = (datetime.utcnow() - timedelta(hours=72)).isoformat()
    
    readings = db.query(Reading).join(Sensor).join(Farm).filter(
        Farm.user_id == current_user.id,
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