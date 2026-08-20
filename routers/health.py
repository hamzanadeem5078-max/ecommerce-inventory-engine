from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from database import get_db
# Adjust import path to match your project's database module



class HealthStatusResponse(BaseModel):
    status: str
    database: str


router = APIRouter(prefix="/health", tags=["System Health"])


@router.get(
    "/system",
    response_model=HealthStatusResponse,
    status_code=status.HTTP_200_OK,
)
def check_system_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database operational connection failed",
        )

    return {"status": "online", "database": "healthy"}