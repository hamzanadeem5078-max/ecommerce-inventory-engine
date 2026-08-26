from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from database import engine, Base
import models
import redis_db
from dependencies import rate_limit_guard
from routers import categories, products, inventory, health, orders

# Fires the machinery to look at models and build them in Postgres
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_db.redis_client.close()

# Initialize FastAPI once with BOTH lifespan and global rate limiting
app = FastAPI(
    lifespan=lifespan,
    dependencies=[Depends(rate_limit_guard)]
)

# Include routers
app.include_router(categories.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(health.router)
app.include_router(orders.router)

@app.get("/")
async def root():
    return {"message": "Welcome to the Flash Sale Engine!"}

@app.get("/redis-test")
async def test_redis():
    # Set a key in Redis
    await redis_db.redis_client.set("engine_status", "operational")
    
    # Read it back
    val = await redis_db.redis_client.get("engine_status")
    
    return {"redis_status": val}

# Route is already protected by the global dependency in app = FastAPI(...)
@app.get("/test-rate-limit")
async def test_rate_limit():
    return {"message": "Access granted!"}