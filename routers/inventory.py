from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from typing import List, Optional
from datetime import datetime


router = APIRouter(
    prefix="/products",
    tags=["Inventory & Audit Logs"]
)


# 1. STATIC ROUTES FIRST
@router.get("/inventory/low-stock", response_model=List[schemas.InventoryResponse])
def get_low_stock_items(db: Session = Depends(get_db)):
    low_stock_items = (
        db.query(models.Product)
        .filter(models.Product.inventory <= models.Product.low_stock_threshold)
        .all()
    )
    return low_stock_items


# 2. DYNAMIC ROUTES FOLLOW
@router.post(
    "/{product_id}/transactions",
    response_model=schemas.StockTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_stock_transaction(
    product_id: int,
    transaction: schemas.StockTransactionCreate,
    db: Session = Depends(get_db),
):
    # Acquire an exclusive row-level lock to prevent concurrent race conditions
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
        .with_for_update()
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    try:
        product.inventory += transaction.quantity_change

        new_transaction = models.StockTransaction(
            product_id=product_id, 
            quantity_change=transaction.quantity_change,
            transaction_type=transaction.transaction_type
        )
        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)
        db.refresh(product)
        return new_transaction

    except Exception as e:
        db.rollback()
        raise e


@router.get("/{product_id}/audit-logs", response_model=List[schemas.StockTransactionResponse])
def get_product_audit_logs(
    product_id: int, 
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    transaction_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found"
        )

    query = (
        db.query(models.StockTransaction)
        .filter(models.StockTransaction.product_id == product_id)
    )

    if transaction_type:
        query = query.filter(models.StockTransaction.transaction_type == transaction_type)

    if start_date:
        query = query.filter(models.StockTransaction.timestamp >= start_date)

    if end_date:
        query = query.filter(models.StockTransaction.timestamp <= end_date)

    logs = (
        query.order_by(models.StockTransaction.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return logs