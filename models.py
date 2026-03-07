from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
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

    # This creates a virtual link so we can easily find a user's sensors
    sensors = relationship("Sensor", back_populates="owner")

class Sensor(Base):
    __tablename__ = 'sensors'
    
    # The Device EUI from your SenseCAP is unique, so it acts as our main ID here
    device_eui = Column(String, primary_key=True, index=True)
    name = Column(String)
    user_id = Column(Integer, ForeignKey('users.id')) # Links to the User table
    last_alert_sent = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="sensors")
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

# --- THE BUILDER ---
# This tells SQLAlchemy to create a local SQLite file named 'farm_data.db' 
# and apply all the class structures we just defined above into it.
engine = create_engine('sqlite:///./farm_data.db', connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
