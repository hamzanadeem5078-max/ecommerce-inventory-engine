from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session
from config import settings
from database import engine, Base, get_db
import models
from schemas import ProductSchema, ProductUpdate, CategoryBase, CategoryCreate, CategoryResponse
import categories

app = FastAPI()

# Include the category router
app.include_router(categories.router)


@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}


@app.post("/product")
async def set_product(payload: ProductSchema, db = Depends(get_db)):
    new_product = models.Product(**payload.model_dump())
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
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
    existing_product.category_id = payload.category_id

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


@app.patch("/products/{product_id}")
def patch_product(product_id: int, product_update: ProductUpdate, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = product_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_product, key, value)

    db.commit()
    db.refresh(db_product)
    return db_product


# Fires the machinery to look at models and build them in Postgres
Base.metadata.create_all(bind=engine)