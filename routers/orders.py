from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from typing import List, Optional
from datetime import datetime


router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_order(order: schemas.OrderCreate, db: Session = Depends(get_db)):
  try:
    # 1. Query the product with a row-level lock to handle concurrency safely
    product = (
        db.query(models.Product)
        .filter(models.Product.id == order.product_id)
        .with_for_update()
        .first()
    )

    if not product:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
      )

    # 2. Verify sufficient stock is available
    if order.quantity > product.inventory:
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient stock"
      )

    # 3. Deduct inventory from the product
    product.inventory -= order.quantity

    # 4. Create the new order record
    new_order = models.Order(
        product_id=product.id,
        quantity=order.quantity,
        total_price=product.price * order.quantity,
    )
    db.add(new_order)

    # 5. Log the stock transaction in the ledger
    stock_transaction = models.StockTransaction(
        product_id=product.id,
        change_amount=-order.quantity,
        transaction_type="PURCHASE",
    )
    db.add(stock_transaction)

    # 6. Commit all changes to the database
    db.commit()
    db.refresh(new_order)

    return new_order

  except HTTPException as he:
    db.rollback()
    raise he
  except Exception as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"An error occurred while processing the order: {str(e)}",
    )




@router.post("/{order_id}/cancel", response_model=schemas.OrderResponse, status_code=status.HTTP_200_OK)
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    # 1. Fetch order and validate existence
    order = db.query(models.Order).filter(models.Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    # 2. Check cancellation eligibility
    if order.status == "CANCELLED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is already cancelled")

    try:
        # 3. Lock target product row for update
        product = db.query(models.Product).filter(models.Product.id == order.product_id).with_for_update().first()

        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated product not found")

        # 4. Restore stock & mutate order state
        product.inventory += order.quantity
        order.status = "CANCELLED"

        # 5. Create immutable audit ledger log
        restock_log = models.StockTransaction(
            product_id=product.id,
            quantity_change=order.quantity,
            transaction_type=schemas.TransactionTypeEnum.RESTOCK
        )
        db.add(restock_log)

        # 6. Commit atomic transaction
        db.commit()
        db.refresh(order)
        return order

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process cancellation"
        )