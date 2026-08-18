from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload
from database import get_db
import models
from schemas import (
    ProductSchema,
    ProductUpdate,
    ProductResponse,
    StockTransactionCreate,
    StockTransactionResponse,
)

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def set_product(payload: ProductSchema, db: Session = Depends(get_db)):
    category = (
        db.query(models.Category)
        .filter(models.Category.id == payload.category_id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {payload.category_id} does not exist",
        )
    
    try:
        new_product = models.Product(**payload.model_dump())

        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        db.refresh(new_product, attribute_names=["category"])
        return new_product
    except Exception as e:
        db.rollback()
        raise e


@router.get("/", response_model=list[ProductResponse])
def get_products(
    category_id: int | None = None,
    db: Session = Depends(get_db),
    skip: int = Query(0, description="Number of records to skip for pagination"),
    limit: int = Query(10, le=100, description="Max number of records to return"),
    search: str | None = Query(None, description="Optional filter keyword"),
    sortBy: str = Query("created_at", description="Field to sort by"),
    order: str = Query("asc", description="Sort order: asc or desc"),
):
    query = db.query(models.Product).options(joinedload(models.Product.category))

    if category_id is not None:
        query = query.filter(models.Product.category_id == category_id)

    if search:
        query = query.filter(models.Product.name.contains(search))

    sort_column = getattr(models.Product, sortBy, models.Product.id)
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    products = query.offset(skip).limit(limit).all()
    return products


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    db_product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(
            status_code=404, detail=f"Product with id {product_id} not found"
        )

    return db_product

@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)
):
    db_product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "category_id" in update_data and update_data["category_id"] is not None:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == update_data["category_id"])
            .first()
        )
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id {update_data['category_id']} does not exist",
            )

    try:
        for key, value in update_data.items():
            setattr(db_product, key, value)

        db.commit()
        db.refresh(db_product)
        return db_product

    except Exception as e:
        db.rollback()
        raise e


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product_check = db.get(models.Product, product_id)

    if not product_check:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        db.delete(product_check)
        db.commit()
        return {"message": "Product successfully deleted"}
    except Exception as e:
        db.rollback()
        raise e


@router.post(
    "/{product_id}/transactions", response_model=StockTransactionResponse
)

def create_stock_transaction(
    product_id: int,
    transaction: StockTransactionCreate,
    db: Session = Depends(get_db),
):
    product = (
        db.query(models.Product).filter(models.Product.id == product_id).with_for_update().first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        product.inventory += transaction.quantity_change

        new_transaction = models.StockTransaction(
            product_id=product_id,
            quantity_change=transaction.quantity_change,
            transaction_type=transaction.transaction_type,
        )

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)
        db.refresh(product)
        return new_transaction

    except Exception as e:
        db.rollback()
        raise e


@router.get("/{product_id}/history", response_model=list[StockTransactionResponse])
def get_history(
    product_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    transaction_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    try:
        query = db.query(models.StockTransaction).filter(
            models.StockTransaction.product_id == product_id
        )

        if transaction_type:
            query = query.filter(models.StockTransaction.transaction_type == transaction_type)

        if start_date:
            query = query.filter(models.StockTransaction.timestamp >= start_date)

        if end_date:
            query = query.filter(models.StockTransaction.timestamp <= end_date)

        return query.offset(offset).limit(limit).all()

    except Exception as e:
        db.rollback()
        raise e