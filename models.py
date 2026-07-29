from database import Base
from sqlalchemy import Column, Integer, String, Boolean, Float,ForeignKey
from sqlalchemy.orm import relationship


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_order=True, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)

    # Establishes a virtual link to child products
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products" #__tablename__ a keyword not a variable
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String,primary_key=False,nullable=False)
    description = Column(String,primary_key=False,nullable=True)
    price = Column(Float,primary_key=False,nullable=False)
    inventory = Column(Integer,primary_key=False,server_default="0",nullable=False)

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    category = relationship("Category", back_populates="products")
    


