import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# This is the foundation class that all our tables will build upon
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # A User can own multiple Farms
    farms = relationship("Farm", back_populates="owner")

class Farm(Base):
    __tablename__ = 'farms'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE')) 
    farm_name = Column(String, nullable=False) 
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    owner = relationship("User", back_populates="farms")
    sensors = relationship("Sensor", back_populates="farm")

class Sensor(Base):
    __tablename__ = 'sensors'
    
    # The Device EUI from your SenseCAP is unique, so it acts as our main ID
    device_eui = Column(String, primary_key=True, index=True)
    farm_id = Column(Integer, ForeignKey('farms.id', ondelete='CASCADE')) 
    name = Column(String, default='Unnamed Field')
    
    # Allows clients to set custom alert thresholds per sensor
    moisture_threshold = Column(Integer, default=20) 
    
    # The magic "Soft Delete" toggle
    is_active = Column(Boolean, default=True) 
    installed_at = Column(DateTime, default=datetime.utcnow)
    last_alert_sent = Column(DateTime, nullable=True)

    farm = relationship("Farm", back_populates="sensors")
    readings = relationship("Reading", back_populates="sensor")

class Reading(Base):
    __tablename__ = 'readings'
    
    id = Column(Integer, primary_key=True, index=True)
    device_eui = Column(String, ForeignKey('sensors.device_eui', ondelete='CASCADE')) 
    timestamp = Column(DateTime, default=datetime.utcnow)
    moisture_pct = Column(Float, nullable=False)
    temperature_c = Column(Float)
    
    # Keeping this so your hardware payload doesn't break!
    battery_volts = Column(Float) 

    sensor = relationship("Sensor", back_populates="readings")

# ===========================================================================
# THE CLOUD-READY BUILDER
# ===========================================================================

# 1. Look for a Cloud Vault URL first. If not found, use the local SQLite file.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./farm_data.db")

# 2. Render sometimes uses "postgres://" but SQLAlchemy requires "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. Connect to the Database
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Base.metadata.create_all(bind=engine)