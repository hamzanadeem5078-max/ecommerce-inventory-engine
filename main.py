from fastapi import FastAPI
from pydantic import BaseModel
from config import settings
from database import engine, Base
from models import Product # 1. This imports the database blueprint

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
async def set_product(payload: ProductSchema):
    return payload

# 4. Fires the machinery to look at 'Product' and build it in Postgres
Base.metadata.create_all(bind=engine)