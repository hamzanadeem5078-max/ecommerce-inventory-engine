from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Product(BaseModel):
    name: str
    price: float

@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}

@app.post("/product")
async def set_product(payload: Product):
    return payload