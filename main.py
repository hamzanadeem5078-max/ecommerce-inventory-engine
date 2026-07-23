from fastapi import FastAPI,Depends, HTTPException
from pydantic import BaseModel
from config import settings
from database import engine, Base
import models # 1. This imports the database blueprint
from database import get_db
from fastapi import Depends
from sqlalchemy.orm import Session




app = FastAPI()

# 2. Renamed this to ProductSchema so it doesn't overwrite our database model!
class ProductSchema(BaseModel):
    name: str
    price: float

@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}

# 3. Updated the payload type to match the new schema name
@app.post("/product")
async def set_product(payload: ProductSchema, db = Depends(get_db)):
    new_product = models.Product(**payload.model_dump()) # making sure in correct table format and then converting payload object to correct dictionary format
    db.add(new_product) # row placed in temporary memory
    db.commit() # permenantly saves row in db table
    db.refresh(new_product)  # a unique number stampped on new product addition 
    return new_product


@app.get("/products")
def get_products(db: Session = Depends(get_db)):
    products = db.query(models.Product).all()
    return products

@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail=f"Product with id {product_id} not found")

    return db_product





# 4. Fires the machinery to look at 'Product' and build it in Postgres
Base.metadata.create_all(bind=engine)