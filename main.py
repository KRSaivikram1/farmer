"""
Farmer Alert – FastAPI Application
===================================
Core API server providing sensor data ingestion and dashboard retrieval
endpoints for the farm monitoring platform.
"""
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import sessionmaker, Session
from auth import verify_password, get_password_hash, create_access_token
from models import engine, Reading, Sensor, User
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from auth import SECRET_KEY, ALGORITHM

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

# This tells FastAPI where the login door is
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """The Bouncer: Checks the JWT token and returns the logged-in user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the digital keycard
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except Exception:
        # If the token is fake, expired, or tampered with, kick them out
        raise credentials_exception
    
    # Look up the farmer in the database
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
        
    return user
# ---------------------------------------------------------------------------
# Pydantic schemas (request / response)
# ---------------------------------------------------------------------------
class IngestPayload(BaseModel):
    """Schema for the incoming sensor reading payload."""
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
# Endpoint 1 – Ingestion (FIXED REGISTRATION BUG)
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
    # 2. SENSOR REGISTRATION (Moved outside the threshold check!)
    # ---------------------------------------------------------
    # Check if this sensor is registered in our database
    sensor = db.query(Sensor).filter(Sensor.device_eui == payload.device_eui).first()
    
    # Auto-register for testing purposes if it doesn't exist
    if not sensor:
        sensor = Sensor(device_eui=payload.device_eui, name="Test Field Sensor")
        db.add(sensor)
        db.commit()
        db.refresh(sensor)

    # ---------------------------------------------------------
    # 3. THE ALERTING ENGINE
    # ---------------------------------------------------------
    THRESHOLD = 20.0
    COOLDOWN_HOURS = 4

    # Only run the complex checks if the moisture is critically low
    if payload.moisture_pct <= THRESHOLD:
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
# Endpoint 2 – Get 72-Hour History for a Single Sensor (Updated for Modal)
# ---------------------------------------------------------------------------
@app.get("/api/sensors/{device_eui}/readings", summary="Get last 72 hours of readings for a specific sensor")
def get_sensor_readings(device_eui: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetches the last 72 hours of raw readings for a specific device."""
    
    seventy_two_hours_ago = (datetime.utcnow() - timedelta(hours=72)).isoformat()
    
    readings = db.query(Reading).filter(
        Reading.device_eui == device_eui,
        Reading.timestamp >= seventy_two_hours_ago
    ).order_by(Reading.timestamp.desc()).all()
    
    return readings
# ---------------------------------------------------------------------------
# Endpoint 3 – User Registration (Temporary for MVP Setup)
# ---------------------------------------------------------------------------
@app.post("/api/register", summary="Create a new farmer account")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    """Hashes the password and saves the new user to the database."""
    # Check if username is already taken
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pw = get_password_hash(user.password)
    
    new_user = User(
        username=user.username, 
        password_hash=hashed_pw, 
        phone_number=user.phone_number
    )
    db.add(new_user)
    db.commit()
    return {"message": f"Farmer '{user.username}' successfully registered!"}

# # ---------------------------------------------------------------------------
# Endpoint 4 – The Login Vault (UPDATED FOR OAUTH2 FORMS)
# ---------------------------------------------------------------------------
@app.post("/api/login", response_model=TokenResponse, summary="Log in to get access token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Verifies credentials and returns a secure JWT token."""
    # 1. Find the user in the database (Notice we use form_data.username now)
    db_user = db.query(User).filter(User.username == form_data.username).first()
    
    # 2. Check if user exists AND if the password matches the hash
    if not db_user or not verify_password(form_data.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # 3. Success! Generate the digital keycard
    access_token = create_access_token(data={"sub": db_user.username})
    return {"access_token": access_token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Endpoint 5 – Dashboard Summary (Multi-Sensor)
# ---------------------------------------------------------------------------
@app.get("/api/dashboard", summary="Get the latest reading for all sensors")
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Returns an array of sensors with their most recent data point."""
    sensors = db.query(Sensor).all()
    dashboard_data = []
    
    for sensor in sensors:
        # Grab only the most recent reading for this specific sensor
        latest = db.query(Reading).filter(Reading.device_eui == sensor.device_eui).order_by(Reading.timestamp.desc()).first()
        
        if latest:
            dashboard_data.append({
                "device_eui": sensor.device_eui,
                "name": sensor.name or "Unknown Field",
                "moisture_pct": latest.moisture_pct,
                "temperature_c": latest.temperature_c,
                "battery_volts": latest.battery_volts
            })
            
    return dashboard_data


# ---------------------------------------------------------------------------
# Endpoint 6 – 72-Hour Farm Average Chart Data (Updated for Pagination)
# ---------------------------------------------------------------------------
@app.get("/api/dashboard/chart", summary="Get hourly farm averages for the last 72 hours")
def get_chart_data(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetches 72 hours of data, groups it by hour, and calculates the farm-wide average."""
    
    # 1. Calculate the cutoff time for 3 DAYS ago (72 hours)
    seventy_two_hours_ago = (datetime.utcnow() - timedelta(hours=72)).isoformat()
    
    # 2. Grab every single reading from every sensor in that time window
    readings = db.query(Reading).filter(Reading.timestamp >= seventy_two_hours_ago).all()
    
    # 3. Group the readings into hourly buckets
    hourly_data: dict[datetime, list[float]] = {}
    for r in readings:
        # Clean up the string (remove 'Z' if present for Python 3.9 compatibility)
        time_str = str(r.timestamp).replace("Z", "")
        
        # Convert the string into an actual Python datetime object!
        dt_obj = datetime.fromisoformat(time_str)
        
        # Now we can safely chop off the minutes and seconds
        hour_bucket = dt_obj.replace(minute=0, second=0, microsecond=0)
        
        # Convert moisture to a float so Python knows it's a number for math
        hourly_data.setdefault(hour_bucket, []).append(float(r.moisture_pct))
        
    # 4. Calculate the average for each hour bucket
    chart_points = []
    for hour, values in hourly_data.items():
        if len(values) > 0:
            avg: float = sum(values) / len(values)
            rounded_avg: float = int(avg * 10) / 10
            chart_points.append({
                "timestamp": hour.isoformat() + "Z",
                "avg_moisture": rounded_avg
            })
        
    # 5. Sort them chronologically (oldest to newest)
    chart_points.sort(key=lambda x: x["timestamp"])
    
    return chart_points