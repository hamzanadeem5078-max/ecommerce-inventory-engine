from pydantic import BaseModel, computed_field
from typing import Optional


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
    category_id: Optional[int]


class CategoryBase(BaseModel):
    name: str


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    id: int
    name: str

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    description: Optional[str] = None
    inventory: int
    category_id: int
    category: CategoryResponse  # Nested category response model

    


    low_stock_threshold: int = (
      5  # Default threshold for low stock warning
  )

    @computed_field
    @property
    def is_low_stock(self) -> bool:
        return self.inventory <= self.low_stock_threshold

    class Config:
            from_attributes = True