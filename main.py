from fastapi import FastAPI 
from pydantic import BaseModel


app = FastAPI() # making the department + door

@app.get("/") # front desk of the hotel lobby where rec is
async def root(): # welcome inside function
    return {"message": "Welcome to the Flash Sale Engine!"}
    

class Product(BaseModel):
    name: str
    price: float
    