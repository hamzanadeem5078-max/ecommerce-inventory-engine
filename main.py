from fastapi import FastAPI,Depends, HTTPException
from pydantic import BaseModel
from config import settings
from database import engine, Base
import models # 1. This imports the database blueprint
from database import get_db
from fastapi import Depends
from sqlalchemy.orm import Session
from fastapi import Query
from sqlalchemy import asc, desc




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
    new_product = models.Product(**payload.model_dump()) # converting payload object to correct dictionary format
    db.add(new_product) # row placed in temporary memory
    db.commit() # permenantly saves row in db table
    db.refresh(new_product)  # a unique number stampped on new product addition 
    return new_product


@app.get("/products")
def get_products(
    db: Session = Depends(get_db),
    skip: int = Query(0, description="Number of records to skip for pagination"),
    limit: int = Query(10, le=100, description="Max number of records to return"),
    search: str | None = Query(None, description="Optional filter keyword"),
    sortBy: str = Query("created_at", description="Field to sort by"),
    order: str = Query("asc", description="Sort order: asc or desc"),
):
    query = db.query(models.Product)
    if search:
        query = query.filter(models.Product.name.contains(search))

    sort_column = getattr(models.Product, sortBy, models.Product.created_at)
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    products = query.offset(skip).limit(limit).all()

    return products


    
@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail=f"Product with id {product_id} not found")

    return db_product

@app.put("/products/{product_id}")
def update_product(product_id: int, payload: ProductSchema, db: Session = Depends(get_db)):
    product_query = db.query(models.Product).filter(models.Product.id == product_id)
    existing_product = product_query.first()
    if not existing_product:
      raise HTTPException(status_code=404, detail="Product not found")

    existing_product.name = payload.name
    existing_product.price = payload.price

    db.commit()
    db.refresh(existing_product)
    return existing_product

@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product_check = db.get(models.Product, product_id)
    
    if not product_check:
        raise HTTPException(status_code=404, detail="Product not found")
        
    db.delete(product_check)
    db.commit()
    
    return {"message": "Product successfully deleted"}







# 4. Fires the machinery to look at 'Product' and build it in Postgres
Base.metadata.create_all(bind=engine)