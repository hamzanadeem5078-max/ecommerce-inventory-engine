from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = f"postgresql://{settings.database_username}:{settings.database_password}@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
# we have all the hdmi cabels in our hand with this line

engine = create_engine(DATABASE_URL)
#so this line basically installs the 5 different coloured holes in our tv

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Pointing our remote control at our Smart Switch so it knows which wire to send user commands down later when a button like "Add Product" or "Buy Now" is pressed.
Base = declarative_base()
#so base is what gives our table its proper form no matter what table it is so postgres can read and act on it

def get_db():
    db = SessionLocal()
    try:
        yield db

    finally:
        db.close()