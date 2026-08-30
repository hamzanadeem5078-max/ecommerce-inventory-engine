from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from database import get_db
import models
import redis_db
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




@router.get("/health/cache-db-sync/{product_id}", status_code=status.HTTP_200_OK)
async def verify_cache_db_consistency(
    product_id: int,
    db: Session = Depends(get_db)
):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
     raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Product not found"
    )
    cache_key = f"product:{product_id}:stock"
    cached_stock_raw = redis_db.redis_client.get(cache_key)
    if cached_stock_raw is not None:
      cached_stock = int(cached_stock_raw)

    else:
      cached_stock = None

    return {
    "product_id": product_id,
    "db_stock": db_product.stock,
    "cache_stock": cached_stock,
    "is_consistent": db_product.stock == cached_stock,
    "status": "SYNCED" if db_product.stock == cached_stock else "DRIFT_DETECTED"
}