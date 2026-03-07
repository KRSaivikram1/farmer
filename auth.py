from datetime import datetime, timedelta
from passlib.context import CryptContext
import jwt

# This is the master lock for your tokens. In a production environment, 
# this is hidden in a .env file, but we will hardcode it for the MVP.
SECRET_KEY = "super_secret_farm_key_do_not_share"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # The token stays valid for 1 week

# This tells Passlib to use the bcrypt algorithm for hashing passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Checks if the typed password matches the scrambled one in the database."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Takes a plain text password and scrambles it."""
    return pwd_context.hash(password)

def create_access_token(data: dict):
    """Generates the digital keycard (JWT) for the user."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    # This mathematically signs the token so hackers can't forge it
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt