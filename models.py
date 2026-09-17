import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func, Enum, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

import database  # Explicit module import to maintain standard namespace access


class Category(database.Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    products = relationship("Product", back_populates="category")


class Product(database.Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    inventory = Column(Integer, server_default="0", nullable=False)
    low_stock_threshold = Column(Integer, server_default="5", default=5, nullable=False)

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    category = relationship("Category", back_populates="products")
    transactions = relationship("StockTransaction", back_populates="product", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="product", cascade="all, delete-orphan")


class TransactionTypeEnum(str, enum.Enum):
    RESTOCK = "RESTOCK"
    SALE = "SALE"
    ADJUSTMENT = "ADJUSTMENT"


class StockTransaction(database.Base):
    __tablename__ = "stock_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product = relationship("Product", back_populates="transactions")


class Order(database.Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    product = relationship("Product", back_populates="orders")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessedEvent(database.Base):
    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DEAD = "DEAD"


class OutboxEvent(database.Base):
    __tablename__ = "outbox_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(100), nullable=False, index=True)
    payload = Column(JSONB, nullable=False)
    status = Column(
        Enum(OutboxStatus, name="outbox_status_enum"), 
        nullable=False, 
        default=OutboxStatus.PENDING
    )
    retry_count = Column(String, default=lambda: "0", nullable=False)
    last_error = Column(Text, nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_outbox_status_created", "status", "created_at"),
    )