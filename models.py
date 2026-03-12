import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# This is the foundation class that all our tables will build upon
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    phone_number = Column(String)

    # A User can now own multiple Hubs (instead of direct sensors)
    hubs = relationship("Hub", back_populates="owner")

class Hub(Base):
    __tablename__ = 'hubs'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String) # e.g., "North Farm Gateway"
    location = Column(String, nullable=True)
    
    # Links back to the User who owns this hub
    user_id = Column(Integer, ForeignKey('users.id')) 

    owner = relationship("User", back_populates="hubs")
    sensors = relationship("Sensor", back_populates="hub")

class Sensor(Base):
    __tablename__ = 'sensors'
    
    # The Device EUI from your SenseCAP is unique, so it acts as our main ID here
    device_eui = Column(String, primary_key=True, index=True)
    name = Column(String)
    
    # The magic "Soft Delete" toggle. Defaults to True.
    is_active = Column(Boolean, default=True) 
    last_alert_sent = Column(DateTime, nullable=True)

    # Links back to the Hub this sensor is connected to
    hub_id = Column(Integer, ForeignKey('hubs.id')) 

    hub = relationship("Hub", back_populates="sensors")
    readings = relationship("Reading", back_populates="sensor")

class Reading(Base):
    __tablename__ = 'readings'
    
    id = Column(Integer, primary_key=True, index=True)
    device_eui = Column(String, ForeignKey('sensors.device_eui')) # Links to the Sensor table
    timestamp = Column(DateTime, default=datetime.utcnow)
    moisture_pct = Column(Float)
    temperature_c = Column(Float)
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

# 3. Connect to the Database (SQLite needs a special rule, Postgres doesn't)
if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Base.metadata.create_all(bind=engine)