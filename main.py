from fastapi import FastAPI
from database import engine, Base
import models
from routers import categories, products, inventory,health,orders

# Fires the machinery to look at models and build them in Postgres
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Include routers
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(health.router)
app.include_router(orders.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}