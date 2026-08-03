from fastapi import FastAPI, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, joinedload
from config import settings
from database import engine, Base, get_db
import models
from schemas import ProductSchema, ProductUpdate, CategoryBase, CategoryCreate, CategoryResponse, ProductResponse
import categories

app = FastAPI()

# Include the category router
app.include_router(categories.router)


@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}


@app.post("/product", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def set_product(payload: ProductSchema, db: Session = Depends(get_db)):
    category = db.query(models.Category).filter(models.Category.id == payload.category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category with id {payload.category_id} does not exist"
        )
    new_product = models.Product(**payload.model_dump())
    
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    
    # Explicitly load the relationship for response validation
    db.refresh(new_product, attribute_names=['category'])
    return new_product


@app.get("/products", response_model=list[ProductResponse])
def get_products(
    category_id: int | None = None,
    db: Session = Depends(get_db),
    skip: int = Query(0, description="Number of records to skip for pagination"),
    limit: int = Query(10, le=100, description="Max number of records to return"),
    search: str | None = Query(None, description="Optional filter keyword"),
    sortBy: str = Query("created_at", description="Field to sort by"),
    order: str = Query("asc", description="Sort order: asc or desc"),
):
    query = db.query(models.Product).options(joinedload(models.Product.category))
    
    if category_id is not None:
        query = query.filter(models.Product.category_id == category_id)

    if search:
        query = query.filter(models.Product.name.contains(search))

    sort_column = getattr(models.Product, sortBy, models.Product.id)
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    products = query.offset(skip).limit(limit).all()
    return products


@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    db_product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )
    if not db_product:
        raise HTTPException(status_code=404, detail=f"Product with id {product_id} not found")

    return db_product


from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
# (Make sure to import your models, database session, schemas, etc. as configured in your project)

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    inventory: Optional[int] = None
    category_id: Optional[int] = None

@app.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    product_query = db.query(models.Product).options(joinedload(models.Product.category)).filter(models.Product.id == product_id)
    existing_product = product_query.first()
    
    if not existing_product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Extract only the fields that were actually passed in the Postman body
    update_data = payload.model_dump(exclude_unset=True)

    # Validate category existence only if category_id is part of the patch update
    if "category_id" in update_data and update_data["category_id"] is not None:
        category = db.query(models.Category).filter(models.Category.id == update_data["category_id"]).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id {update_data['category_id']} does not exist"
            )

    # Dynamically apply the updates to the existing record
    for key, value in update_data.items():
        setattr(existing_product, key, value)

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


@app.patch("/products/{product_id}", response_model=ProductResponse)
def patch_product(product_id: int, product_update: ProductUpdate, db: Session = Depends(get_db)):
    db_product = (
        db.query(models.Product)
        .options(joinedload(models.Product.category))
        .filter(models.Product.id == product_id)
        .first()
    )
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