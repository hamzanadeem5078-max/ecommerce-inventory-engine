import traceback
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from typing import List, Optional
from datetime import datetime
from fastapi import BackgroundTasks

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
        quantity_change=-order.quantity,
        transaction_type="SALE",
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
    try:
        # 1. Lock the order row first
        order = (
            db.query(models.Order)
            .filter(models.Order.id == order_id)
            .with_for_update()
            .first()
        )

        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

        # 2. Check cancellation eligibility
        if order.status == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order is already cancelled")

        # 3. Lock target product row
        product = (
            db.query(models.Product)
            .filter(models.Product.id == order.product_id)
            .with_for_update()
            .first()
        )

        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated product not found")

        # 4. Mutate states in memory
        order.status = "CANCELLED"
        product.inventory += order.quantity

        # 5. Append immutable audit log
        restock_log = models.StockTransaction(
            product_id=product.id,
            quantity_change=order.quantity,
            transaction_type=models.TransactionTypeEnum.RESTOCK
        )
        db.add(restock_log)

        # 6. Commit atomic unit of work
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




def send_order_notification(order_id: int, email: str):
    print(f"Processing notification for Order #{order_id} to {email}")

@router.post("/orders/checkout")
def checkout(
    order_data: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # Dynamic DB values represented as placeholders
    order_id = 101
    email = "customer@example.com"
    
    background_tasks.add_task(send_order_notification, order_id, email)
    
    return {"status": "Order placed successfully", "order_id": order_id}
