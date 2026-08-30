import enum
from datetime import datetime
from database import Base
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func, Enum
from sqlalchemy.orm import relationship


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    inventory = Column(Integer, server_default="0", nullable=False)
    low_stock_threshold = Column(Integer, server_default="5", default=5, nullable=False)

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    category = relationship("Category", back_populates="products")
    transactions = relationship("StockTransaction", back_populates="product",cascade="all, delete-orphan")
    orders = relationship( "Order", back_populates="product", cascade="all, delete-orphan")


class TransactionTypeEnum(str, enum.Enum):
    RESTOCK = "RESTOCK"
    SALE = "SALE"
    ADJUSTMENT = "ADJUSTMENT"


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    transaction_type = Column(Enum(TransactionTypeEnum), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product = relationship("Product", back_populates="transactions")





class Order(Base):
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