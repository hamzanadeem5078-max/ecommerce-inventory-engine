from pydantic import BaseModel
from typing import Optional


class ProductSchema(BaseModel):
    name: str
    price: float
    category_id: int


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    stock: Optional[int] = None


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

    class Config:
        from_attributes = True