import json
import logging
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db, get_redis_client
from dependencies import enforce_rate_limit, redis_lock_guard
from event_producer import ResilientEventProducer
import models
import schemas

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


def send_order_notification(order_id: int, recipient_email: str):
    """
    Simulated non-blocking background notification worker task.
    """
    logger.info(f"[Background Task] Sending order confirmation email for Order ID #{order_id} to {recipient_email}")


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.OrderResponse,
    dependencies=[Depends(enforce_rate_limit)]
)
async def create_order(
    order: schemas.OrderCreate, 
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    """
    Creates a new order with row-level pessimistic locking on inventory.
    Publishes 'order.created' event via ResilientEventProducer.
    Falls back to Postgres outbox_events table if Redis Stream fails or Circuit Breaker is OPEN.
    """
    with redis_lock_guard(order.product_id, redis_client):
        try:
            # 1. Pessimistic Row Lock on Product Inventory
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

            # 2. Verify Available Stock
            if order.quantity > product.inventory:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Insufficient stock"
                )

            # 3. Deduct Stock & Instantiate Order Record
            product.inventory -= order.quantity

            new_order = models.Order(
                product_id=product.id,
                quantity=order.quantity,
                total_price=product.price * order.quantity,
            )
            db.add(new_order)

            # 4. Record Stock Transaction Ledger Entry
            stock_transaction = models.StockTransaction(
                product_id=product.id,
                quantity_change=-order.quantity,
                transaction_type="SALE",
            )
            db.add(stock_transaction)

            # 5. Flush to generate new_order.id before publishing payload
            db.flush()

            # 6. Resilient Event Publishing with Circuit Breaker + Outbox Fallback
            producer = ResilientEventProducer(redis_client=redis_client)
            published_to_stream = await producer.publish_with_fallback(
                db=db,
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

            if not published_to_stream:
                # Signal system degradation to client/gateway
                response.headers["X-System-Degraded"] = "true"

            # 7. Atomic Commit (Commits Order + StockTransaction + OutboxEvent if fallback occurred)
            db.commit()
            db.refresh(new_order)

            # 8. Asynchronous Non-blocking Notification
            background_tasks.add_task(send_order_notification, new_order.id, "customer@example.com")

            return new_order

        except HTTPException as he:
            db.rollback()
            raise he
        except Exception as e:
            db.rollback()
            logger.error(f"Error executing create_order: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred while processing the order: {str(e)}",
            )


@router.get(
    "/",
    response_model=List[schemas.OrderResponse],
    dependencies=[Depends(enforce_rate_limit)]
)
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Retrieves paginated list of orders.
    """
    orders = db.query(models.Order).offset(skip).limit(limit).all()
    return orders


@router.post(
    "/{order_id}/cancel",
    response_model=schemas.OrderResponse,
    dependencies=[Depends(enforce_rate_limit)]
)
async def cancel_order(
    order_id: int,
    response: Response,
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis_client)
):
    """
    Cancels an existing order, restores inventory stock, and logs a RESTOCK transaction.
    Publishes 'order.cancelled' event with Circuit Breaker and Outbox DB fallback.
    """
    try:
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Order not found"
            )

        if order.status == "CANCELLED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Order is already cancelled"
            )

        # 1. Update Order Status
        order.status = "CANCELLED"

        # 2. Restore Stock with Row Lock
        product = (
            db.query(models.Product)
            .filter(models.Product.id == order.product_id)
            .with_for_update()
            .first()
        )

        if product:
            product.inventory += order.quantity
            stock_transaction = models.StockTransaction(
                product_id=product.id,
                quantity_change=order.quantity,
                transaction_type="RESTOCK",
            )
            db.add(stock_transaction)

        # 3. Resilient Event Publishing with Circuit Breaker + Outbox Fallback
        producer = ResilientEventProducer(redis_client=redis_client)
        published_to_stream = await producer.publish_with_fallback(
            db=db,
            stream_name="orders:events",
            event_type="order.cancelled",
            payload={
                "order_id": order.id,
                "product_id": order.product_id,
                "quantity": order.quantity,
                "status": order.status
            }
        )

        if not published_to_stream:
            # Signal system degradation to client/gateway
            response.headers["X-System-Degraded"] = "true"

        # 4. Atomic Transaction Commit
        db.commit()
        db.refresh(order)

        return order

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error executing cancel_order for ID #{order_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while cancelling the order: {str(e)}",
        )