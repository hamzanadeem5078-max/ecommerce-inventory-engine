from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from config import settings
from sqlalchemy.ext.declarative import declarative_base
from dependencies import correlation_id_var  # <-- IMPORT CONTEXT VAR

DATABASE_URL = f"postgresql://{settings.database_username}:{settings.database_password}@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"

engine = create_engine(DATABASE_URL)

# --- DAY 82: DEFENSIVE PROPAGATION LISTENER ---
@event.listens_for(engine, "before_cursor_execute", retval=True)
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    Intercepts every outbound query and stamps it with the active Correlation ID.
    Requires retval=True so we can modify and return the new statement.
    """
    corr_id = correlation_id_var.get(None)
    if corr_id:
        # Stamp the query with a trace ID comment for DBA monitoring
        statement = f"/* trace_id:{corr_id} */\n{statement}"
    
    return statement, parameters
# ----------------------------------------------

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()