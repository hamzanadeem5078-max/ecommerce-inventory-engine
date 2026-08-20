from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class CategoryBase(BaseModel):
  name: str


class CategoryCreate(CategoryBase):
  pass


class CategoryResponse(CategoryBase):
  id: int
  name: str

  class Config:
    from_attributes = True


class ProductSchema(BaseModel):
  name: str
  price: float
  category_id: int
  description: str
  inventory: int


class ProductUpdate(BaseModel):
  name: Optional[str] = None
  price: Optional[float] = None
  description: Optional[str] = None
  inventory: Optional[int] = None
  category_id: Optional[int] = None


class ProductResponse(BaseModel):
  id: int
  name: str
  price: float
  description: Optional[str] = None
  inventory: int
  category_id: int
  category: CategoryResponse
  low_stock_threshold: int = 5

  @computed_field
  @property
  def is_low_stock(self) -> bool:
    return self.inventory <= self.low_stock_threshold

  class Config:
    from_attributes = True


class InventoryResponse(BaseModel):
  id: int
  name: str
  inventory: int
  low_stock_threshold: int

  @computed_field
  @property
  def is_low_stock(self) -> bool:
    return self.inventory <= self.low_stock_threshold

  class Config:
    from_attributes = True


class TransactionTypeEnum(str, Enum):
  RESTOCK = "RESTOCK"
  SALE = "SALE"
  ADJUSTMENT = "ADJUSTMENT"


class StockTransactionCreate(BaseModel):
  quantity_change: int = Field(
      ..., description="Quantity delta: positive or negative"
  )
  transaction_type: TransactionTypeEnum


class StockTransactionResponse(BaseModel):
  id: int
  product_id: int
  quantity_change: int
  transaction_type: TransactionTypeEnum
  timestamp: datetime

  class Config:
    from_attributes = True



class OrderCreate(BaseModel):
  product_id: int
  quantity: int = Field(..., gt=0, description="Quantity must be greater than zero")



class OrderResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True



class HealthStatusResponse(BaseModel):
    status: str
    database: str


    
