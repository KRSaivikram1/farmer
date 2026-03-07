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
@app.get("/api/sensors/{device_eui}/readings")
def get_sensor_readings(
    device_eui: str, 
    limit: int = 50, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # <-- THE BOUNCER IS NOW ACTIVE
):
    # (Leave the rest of your code inside this function exactly the same)
    readings = db.query(Reading).filter(Reading.device_eui == device_eui).order_by(Reading.timestamp.desc()).limit(limit).all()
    if not readings:
        raise HTTPException(status_code=404, detail="Sensor not found or no readings available")
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