from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = f"postgresql://{settings.database_username}:{settings.database_password}@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
# we have all the hdmi cabels in our hand with this line

engine = create_engine(DATABASE_URL)
#so this line basically installs the 5 different coloured holes in our tv

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# where we actually install our wire + configuration into our console hdmi cabel the bind keyword is like plugging it in the holes of the tv

Base = declarative_base()
#so base is what gives our table its proper form no matter what table it is so postgres can read and act on it