import json
from datetime import datetime
from typing import Optional,List
import logging
from redis.exceptions import RedisError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload
import logging
from database import get_db
import models
from redis_db import redis_client
from schemas import (
    ProductSchema,
    ProductUpdate,
    ProductResponse,
    StockTransactionCreate,
    StockTransactionResponse,
)

router = APIRouter(prefix="/products", tags=["Products"])
logger = logging.getLogger(__name__)

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(payload: ProductSchema, db: Session = Depends(get_db)):
    category = db.get(models.Category, payload.category_id)
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
        return new_product
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {str(e)}",
        )


@router.get("/", response_model=List[ProductResponse])
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Product).options(joinedload(models.Product.category))
    if category_id:
        query = query.filter(models.Product.category_id == category_id)

    products = query.offset(skip).limit(limit).all()
    return products


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    # Cache Read-Aside Logic
    cache_key = f"product:{product_id}"
    
    try:
        cached_product = await redis_client.get(cache_key)
        if cached_product:
            return ProductResponse.model_validate_json(cached_product)
    except RedisError as e:
        logger.warning(f"Redis cache read failed for key {cache_key}: {e}")

    # Database Fallback
    db_product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Repopulate Cache
    try:
        product_schema = ProductResponse.model_validate(db_product)
        await redis_client.set(cache_key, product_schema.model_dump_json(), ex=3600)
    except RedisError as e:
        logger.warning(f"Redis cache write failed for key {cache_key}: {e}")

    return db_product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
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

        # Write-Through Caching Pattern
        try:
            cached_data = json.dumps(
                {
                    "id": db_product.id,
                    "name": db_product.name,
                    "description": db_product.description,
                    "price": float(db_product.price),
                    "stock": db_product.stock,
                    "category_id": db_product.category_id,
                    "category": {
                        "id": db_product.category.id,
                        "name": db_product.category.name,
                    } if db_product.category else None,
                }
            )

            # Instantly update Redis cache with new state (5-min TTL margin)
            await redis_client.setex(
                f"product:{product_id}",
                300,
                cached_data,
            )
        except RedisError as e:
            logger.warning(
                f"Failed to update write-through cache for key product:{product_id}: {e}"
            )

        return db_product
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product: {str(e)}",
        )

@router.delete("/{product_id}")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    product_check = db.get(models.Product, product_id)

    if not product_check:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        db.delete(product_check)
        db.commit()

        # Resilient Cache Invalidation
        try:
            await redis_client.delete(f"product:{product_id}")
        except RedisError as e:
            logger.warning(
                f"Failed to invalidate cache key product:{product_id}: {e}"
            )

        return {"message": "Product successfully deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database deletion failed: {str(e)}",
        )


@router.post(
    "/{product_id}/stock",
    response_model=StockTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_transaction(
    product_id: int,
    payload: StockTransactionCreate,
    db: Session = Depends(get_db),
):
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
        .with_for_update()
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.transaction_type == models.TransactionType.OUT:
        if product.quantity < payload.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {product.quantity}, Requested: {payload.quantity}",
            )
        product.quantity -= payload.quantity
    elif payload.transaction_type == models.TransactionType.IN:
        product.quantity += payload.quantity

    try:
        new_transaction = models.StockTransaction(
            product_id=product_id,
            quantity=payload.quantity,
            transaction_type=payload.transaction_type,
            notes=payload.notes,
        )
        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)

        # Resilient Cache Invalidation (Quantity changed)
        try:
            await redis_client.delete(f"product:{product_id}")
        except RedisError as e:
            logger.warning(
                f"Failed to invalidate cache key product:{product_id}: {e}"
            )

        return new_transaction
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process stock transaction: {str(e)}",
        )