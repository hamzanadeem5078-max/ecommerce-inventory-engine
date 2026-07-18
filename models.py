from database import Base
from sqlalchemy import Column, Integer, String, Boolean, Float

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String,primary_key=False,nullable=False)
    description = Column(String,primary_key=False,nullable=True)
    price = Column(Float,primary_key=False,nullable=False)
    inventory = Column(Integer,primary_key=False,server_default="0",nullable=False)
