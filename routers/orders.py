from datetime import datetime
import logging
from typing import List, Optional
import traceback

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import redis_lock_guard  # Day 47 Distributed Lock
import models
from redis_db import get_redis_client      # Redis client dependency
import schemas
from event_producer import EventProducer   # Day 51 Event Producer

router = APIRouter(prefix="/orders", tags=["Orders"])
logger = logging.getLogger(__name__)


# Helper function for background notifications
def send_order_notification(order_id: int, email: str):
    try:
        print(f"Processing notification for Order #{order_id} to {email}")
    except Exception as exc:
        logger.error(f"Background task failed for order id {order_id}: {str(exc)}", exc_info=True)


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.OrderResponse)
async def create_order(
    order: schemas.OrderCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    # Enforce Redis Distributed Lock at the entry boundary before touching PostgreSQL
    with redis_lock_guard(order.product_id, redis_client):
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
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="Product not found"
                )

            # 2. Verify sufficient stock is available
            if order.quantity > product.inventory:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Insufficient stock"
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

            # 6. Commit all changes to the database while lock is active
            db.commit()
            db.refresh(new_order)

            # 7. Queue non-blocking notification task
            background_tasks.add_task(send_order_notification, new_order.id, "customer@example.com")

            # 8. Day 51: Non-blocking event emission to Redis Stream
            try:
                producer = EventProducer(redis_client=redis_client)
                await producer.publish_event(
                    stream_name="orders:events",
                    event_type="order.created",
                    payload={
                        "order_id": new_order.id,
                        "product_id": new_order.product_id,
                        "quantity": new_order.quantity,
                        "total_price": float(new_order.total_price),
                        "status": new_order.status
                    }
                )
            except Exception as ev_exc:
                # Event publishing failure must never fail the committed DB transaction
                logger.error(f"[Event Emission Error] Order #{new_order.id}: {str(ev_exc)}")

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
async def cancel_order(
    order_id: int, 
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    try:
        # 1. Lock the order row first
        order = (
            db.query(models.Order)
            .filter(models.Order.id == order_id)
            .with_for_update()
            .first()
        )

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Order not found"
            )

        # 2. Check cancellation eligibility
        if order.status == "CANCELLED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Order is already cancelled"
            )

        # 3. Protect product restocking with Redis Distributed Lock
        with redis_lock_guard(order.product_id, redis_client):
            product = (
                db.query(models.Product)
                .filter(models.Product.id == order.product_id)
                .with_for_update()
                .first()
            )

            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="Associated product not found"
                )

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

            # 7. Day 51: Non-blocking cancellation event emission
            try:
                producer = EventProducer(redis_client=redis_client)
                await producer.publish_event(
                    stream_name="orders:events",
                    event_type="order.cancelled",
                    payload={
                        "order_id": order.id,
                        "product_id": order.product_id,
                        "restocked_quantity": order.quantity,
                        "status": order.status
                    }
                )
            except Exception as ev_exc:
                logger.error(f"[Event Emission Error] Cancellation Order #{order.id}: {str(ev_exc)}")

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


@router.post("/checkout", status_code=status.HTTP_201_CREATED)
async def checkout(
    order_data: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    # Route delegate into the main locked create_order workflow
    return await create_order(order=order_data, background_tasks=background_tasks, db=db, redis_client=redis_client)