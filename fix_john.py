from sqlalchemy.orm import sessionmaker
from models import engine, User
from auth import get_password_hash

# 1. Create a direct session just for this script
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

# 2. Find John
john = db.query(User).filter(User.email == "john@waynefarms.com").first()

if john:
    print(f"Found {john.full_name}!")
    
    # 3. Hash 'password123' perfectly and update his account
    new_hash = get_password_hash("password123")
    john.password_hash = new_hash
    db.commit()
    
    print("Success! John's password is now 'password123'.")
else:
    print("Could not find John in the database.")

db.close()